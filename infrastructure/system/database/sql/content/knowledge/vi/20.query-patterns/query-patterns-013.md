# Phát hiện dữ liệu thiếu, trùng và bất thường bằng SQL

Một báo cáo có thể chạy đúng cú pháp nhưng vẫn cho kết quả sai vì **dữ liệu đầu vào không đạt chất lượng**. Ví dụ: mã khách hàng bỏ trống, một đơn hàng được nhập hai lần, bản ghi thanh toán tham chiếu đơn không tồn tại, số tiền âm, hoặc trạng thái `PAID` nhưng tiền thực thu chưa đủ. Những vấn đề này không phải lúc nào cũng được phát hiện bằng một câu `SELECT` thông thường.

Trong thực tế, người làm việc với cơ sở dữ liệu cần những **mẫu truy vấn kiểm tra chất lượng dữ liệu** (*data quality checks*) có thể đọc, điều chỉnh và chạy lặp lại. Các mẫu đó thường thuộc ba nhóm:

1. **Dữ liệu thiếu (*missing data*)**: cột bắt buộc là `NULL` hoặc rỗng; thiếu hàng tương ứng ở bảng liên quan; thiếu sự kiện dự kiến.
2. **Dữ liệu trùng (*duplicate data*)**: nhiều hàng có cùng khóa nghiệp vụ, cùng thông tin sau khi chuẩn hóa, hoặc cùng một sự kiện bị ghi nhận nhiều lần.
3. **Dữ liệu bất thường (*anomalous data*)**: giá trị nằm ngoài miền hợp lệ, vi phạm quy tắc nghiệp vụ, chênh lệch giữa các nguồn, hay cực đoan so với phân bố thông thường.

Không phải mọi dấu hiệu bất thường đều chứng minh dữ liệu sai. Một đơn 5 triệu có thể là đơn thật; một ngày không có đơn có thể là ngày nghỉ; hai người cùng email có thể là tài khoản dùng chung. Vì vậy, mục tiêu của các truy vấn ở đây là **phát hiện và phân loại trường hợp cần kiểm tra**, không tự động sửa hoặc xóa dữ liệu chỉ vì nó khác số đông.

Bài học tập trung vào các mẫu SQL dùng được trong quy trình kiểm tra dữ liệu, với ví dụ chính trên **PostgreSQL**. Một số cú pháp như `FILTER`, `generate_series`, `PERCENTILE_CONT`, `BTRIM` hoặc `IS DISTINCT FROM` có khác biệt theo hệ quản trị; cuối bài có hướng chuyển đổi phương ngữ.

## 1. Bắt đầu bằng quy tắc chất lượng dữ liệu, không bắt đầu bằng truy vấn

“Thiếu”, “trùng” và “bất thường” chỉ có ý nghĩa khi biết **yêu cầu đối với dữ liệu**.

Giả sử hệ thống bán hàng quy định:

| Mã quy tắc | Quy tắc nghiệp vụ | Loại phát hiện |
|---|---|---|
| `CUS_REQUIRED_CODE` | Khách phải có mã không `NULL`, không chỉ gồm khoảng trắng | Thiếu |
| `CUS_REQUIRED_NAME` | Khách phải có tên không rỗng sau khi bỏ khoảng trắng thừa | Thiếu |
| `CUS_EMAIL_REQUIRED` | Email khách phải có giá trị dùng được | Thiếu |
| `CUS_CODE_UNIQUE` | Một mã khách không được dùng cho nhiều hàng khách nguồn | Trùng |
| `CUS_EMAIL_UNIQUE` | Email sau chuẩn hóa được kỳ vọng không trùng trong bộ dữ liệu này | Trùng có điều kiện |
| `ORD_REF_REQUIRED` | Mỗi đơn phải có mã tham chiếu `order_ref` | Thiếu |
| `ORD_REF_UNIQUE` | Mỗi mã đơn nghiệp vụ chỉ đại diện một đơn | Trùng |
| `ORD_CUSTOMER_EXISTS` | Mã khách của đơn phải trỏ đến khách tồn tại | Thiếu quan hệ |
| `ORD_AMOUNT_NONNEGATIVE` | Số tiền đơn không được âm | Bất thường |
| `ORD_PAID_AMOUNT` | Đơn `PAID` phải có số tiền xác định và lớn hơn 0 trong ví dụ này | Bất thường nghiệp vụ |
| `ORD_STATUS_ALLOWED` | Trạng thái phải thuộc `NEW`, `PAID`, `CANCELLED` | Bất thường |
| `PAY_ORDER_EXISTS` | Khoản thanh toán phải tham chiếu mã đơn tồn tại | Thiếu quan hệ |
| `PAY_PAID_RECONCILED` | Tổng tiền thanh toán `CAPTURED` của đơn `PAID` phải bằng tiền đơn | Đối soát |

**Lưu ý:** những quy tắc trên là **giả định minh họa của bộ dữ liệu thực hành**, không phải chuẩn bắt buộc cho mọi hệ thống. Chẳng hạn, một doanh nghiệp có thể cho phép email dùng chung hoặc đơn `PAID` trị giá 0 trong chương trình khuyến mãi. Khi triển khai thật, phải xác nhận quy tắc với bên sở hữu dữ liệu.

### 1.1. Phân biệt lỗi chắc chắn và trường hợp cần xem xét

Một cách phân loại hữu ích:

- **Lỗi cấu trúc**: mã bắt buộc `NULL`, khóa nghiệp vụ trùng khi quy tắc yêu cầu duy nhất.
- **Lỗi quan hệ**: một mã đơn tham chiếu khách không có trong danh mục khách đã xác nhận đầy đủ.
- **Lỗi nghiệp vụ**: đơn `PAID` nhưng tổng tiền thực thu không đúng theo quy tắc thanh toán.
- **Cảnh báo thống kê**: số tiền quá lớn so với đa số đơn, tần suất sự kiện thay đổi đột ngột.

Hai loại đầu thường có quy tắc kiểm tra rõ. Với bất thường thống kê, SQL thường chỉ tạo **danh sách ứng viên**; vẫn cần người hiểu nghiệp vụ quyết định.

## 2. Bộ dữ liệu mẫu: ba bảng dữ liệu nguồn cố ý có vấn đề

Ta dùng ba bảng `customers_stage`, `orders_stage`, `payments_stage`. Từ `stage` nhấn mạnh đây là **dữ liệu nhập thô/staging**: các trường có thể thiếu hoặc sai trước khi được làm sạch và đưa vào bảng nghiệp vụ chính.

Thực hiện trong **database thực hành riêng**, không chạy các lệnh khởi tạo trên dữ liệu sản xuất. Ví dụ sử dụng PostgreSQL.

### 2.1. Tạo bảng

```sql
CREATE TABLE customers_stage (
    customer_row_id INTEGER PRIMARY KEY,
    customer_code TEXT,
    full_name TEXT,
    email TEXT,
    created_on DATE
);

CREATE TABLE orders_stage (
    raw_id INTEGER PRIMARY KEY,
    order_ref TEXT,
    customer_code TEXT,
    ordered_on DATE,
    status TEXT,
    amount NUMERIC(12, 2),
    loaded_at TIMESTAMP NOT NULL
);

CREATE TABLE payments_stage (
    payment_id INTEGER PRIMARY KEY,
    order_ref TEXT,
    payment_status TEXT,
    amount NUMERIC(12, 2)
);
```

Thiết kế **cố ý không áp dụng `NOT NULL`, `UNIQUE` hay khóa ngoại** lên các cột nghiệp vụ trong staging, để có thể nạp và phát hiện bản ghi sai. Trong bảng giao dịch đã chuẩn hóa, nhiều quy tắc ở mục 1 nên được **thực thi bằng ràng buộc database** khi phù hợp. Truy vấn kiểm tra không thay thế ràng buộc khi bản chất quy tắc có thể được ràng buộc trực tiếp.

Ba cột `customer_row_id`, `raw_id` và `payment_id` là **khóa kỹ thuật của hàng nguồn**, để nhận diện từng bản ghi dù khóa nghiệp vụ bị trùng hoặc thiếu. Chúng không đồng nghĩa mã khách hay mã đơn trong ứng dụng.

### 2.2. Nạp khách hàng

```sql
INSERT INTO customers_stage
    (customer_row_id, customer_code, full_name, email, created_on)
VALUES
    (1,  'C001', 'An',              'An@Example.com',           DATE '2025-03-01'),
    (2,  'C002', 'Binh',            'binh@example.com',         DATE '2025-03-02'),
    (3,  'C003', 'Chi',             'chi@example.com',          DATE '2025-03-03'),
    (4,  'C004', '  Dung  ',        NULL,                       DATE '2025-03-04'),
    (5,  'C005', 'Em',              ' em@example.com ',         DATE '2025-03-05'),
    (6,  'C006', 'Giang',           'AN@example.com',           DATE '2025-03-06'),
    (7,  'C007', 'Ha',              '   ',                      DATE '2025-03-07'),
    (8,  'C002', 'Binh (reimport)', 'binh-new@example.com',     DATE '2025-03-02'),
    (9,  NULL,   'Unknown',         'unknown@example.com',      DATE '2025-03-08'),
    (10, 'C008', '   ',             'khoa@example.com',         DATE '2025-03-09');
```

Các tình huống đã cài vào dữ liệu:

- Hàng **9** thiếu `customer_code`.
- Hàng **10** có `full_name` chỉ gồm khoảng trắng.
- Hàng **4** có `email = NULL`; hàng **7** có email chỉ gồm khoảng trắng.
- Hàng **2 và 8** cùng `customer_code = 'C002'`.
- Hàng **1 và 6** có email khác nhau về chữ hoa/chữ thường, nhưng cùng giá trị nếu dùng quy tắc chuẩn hóa `LOWER(BTRIM(email))`.
- Hàng **5** có email chứa khoảng trắng thừa ở đầu và cuối.

### 2.3. Nạp đơn hàng

```sql
INSERT INTO orders_stage
    (raw_id, order_ref, customer_code, ordered_on, status, amount, loaded_at)
VALUES
    (101, 'O001', 'C001', DATE '2025-03-01', 'PAID',      120.00, TIMESTAMP '2025-03-02 08:00:00'),
    (102, 'O002', 'C002', DATE '2025-03-02', 'NEW',        80.00, TIMESTAMP '2025-03-03 08:00:00'),
    (103, 'O003', 'C003', DATE '2025-03-03', 'PAID',      200.00, TIMESTAMP '2025-03-04 08:00:00'),
    (104, 'O003', 'C003', DATE '2025-03-03', 'PAID',      200.00, TIMESTAMP '2025-03-05 08:00:00'),
    (105, 'O004', 'C404', DATE '2025-03-04', 'PAID',      150.00, TIMESTAMP '2025-03-05 08:00:00'),
    (106, 'O005', 'C004', DATE '2025-03-05', 'PAID',        NULL, TIMESTAMP '2025-03-06 08:00:00'),
    (107, 'O006', 'C005', DATE '2025-03-06', 'NEW',       -20.00, TIMESTAMP '2025-03-07 08:00:00'),
    (108, 'O007', NULL,   DATE '2025-03-07', 'CANCELLED',   0.00, TIMESTAMP '2025-03-08 08:00:00'),
    (109, 'O008', 'C006', DATE '2025-03-08', 'PAID',     5000.00, TIMESTAMP '2025-03-09 08:00:00'),
    (110, 'O009', 'C007', DATE '2025-03-09', 'PAID',       75.00, TIMESTAMP '2025-03-10 08:00:00'),
    (111, 'O010', 'C002', DATE '2025-03-10', 'PAID',        0.00, TIMESTAMP '2025-03-11 08:00:00'),
    (112, NULL,   'C003', DATE '2025-03-11', 'NEW',        30.00, TIMESTAMP '2025-03-12 08:00:00'),
    (113, 'O011', 'C008', DATE '2025-04-05', 'NEW',        40.00, TIMESTAMP '2025-03-12 08:00:00'),
    (114, 'O012', 'C003', DATE '2025-03-12', 'UNKNOWN',    20.00, TIMESTAMP '2025-03-13 08:00:00');
```

Có **14 hàng nguồn** nhưng chỉ **12 mã đơn `order_ref` phân biệt và không `NULL`** (`O001` đến `O012`). Hai hàng 103 và 104 cùng mã `O003`; hàng 112 có mã đơn `NULL`. Các vấn đề chính gồm:

- `O003` bị nhập hai lần dù một mã đơn phải duy nhất.
- `O004` trỏ đến mã khách `C404`, không tồn tại trong `customers_stage`.
- `O005` ở trạng thái `PAID` nhưng `amount` thiếu.
- `O006` có tiền âm.
- `O007` thiếu mã khách.
- `O008` có số tiền 5.000, cao nổi bật so với phần còn lại.
- `O010` có trạng thái `PAID` và số tiền 0, trái quy tắc minh họa.
- Hàng 112 thiếu mã đơn.
- `O011` có ngày đặt `2025-04-05`, là ngày tương lai nếu kiểm tra “as of” `2025-03-15`.
- `O012` mang trạng thái không được công nhận `UNKNOWN`.

### 2.4. Nạp thanh toán

```sql
INSERT INTO payments_stage
    (payment_id, order_ref, payment_status, amount)
VALUES
    (201, 'O001', 'CAPTURED', 120.00),
    (202, 'O002', 'PENDING',   80.00),
    (203, 'O003', 'CAPTURED', 200.00),
    (204, 'O004', 'CAPTURED', 150.00),
    (205, 'O005', 'CAPTURED',  60.00),
    (206, 'O008', 'CAPTURED',1000.00),
    (207, 'O009', 'CAPTURED',  75.00),
    (208, 'O010', 'CAPTURED',   0.00),
    (209, 'O999', 'CAPTURED',  20.00),
    (210, 'O003', 'FAILED',   200.00);
```

Trong dữ liệu này:

- Thanh toán **209** tham chiếu `O999`, không có trong bảng đơn.
- `O008` đã ghi nhận `CAPTURED = 1.000`, nhưng `amount = 5.000` và `status = 'PAID'`.
- `O003` có một thanh toán thành công 200 và một thanh toán thất bại 200; **không** được cộng thanh toán thất bại vào tiền thực thu.
- `O002` mới `PENDING`; không được coi là `CAPTURED`.

### 2.5. Vì sao cần giữ cả dữ liệu thô?

Trong quy trình dữ liệu, bảng nguồn thường lưu thêm **mã bản ghi, thời điểm nạp, tên tệp, hệ thống nguồn, batch ID**. Chúng giúp truy ngược chính xác một lỗi. Nếu vội dùng `DISTINCT` hoặc xóa bản ghi trùng trong lần nhập đầu tiên, ta có thể mất bằng chứng vì sao dữ liệu bị nhân đôi.

Trong bài này, `raw_id` và `loaded_at` hỗ trợ xác định hai lần nhập `O003`. **Không cập nhật hay xóa các hàng sai trong lúc đọc bài**; các truy vấn chủ yếu là `SELECT` để phát hiện.

## 3. Mẫu 1 — Phát hiện NULL, chuỗi rỗng và khoảng trắng

### 3.1. IS NULL: tìm giá trị thật sự không tồn tại

```sql
SELECT customer_row_id, customer_code, full_name, email
FROM customers_stage
WHERE customer_code IS NULL
   OR full_name IS NULL
   OR email IS NULL
ORDER BY customer_row_id;
```

Kết quả có **hàng 4** (email `NULL`) và **hàng 9** (mã khách `NULL`). Hàng 7 có email gồm khoảng trắng và hàng 10 có tên gồm khoảng trắng **không bị truy vấn này phát hiện**, bởi khoảng trắng vẫn là một chuỗi, không phải SQL `NULL`.

Không dùng:

```sql
-- Sai:
WHERE email = NULL

-- Sai:
WHERE email <> NULL
```

Trong SQL thông thường, so sánh với `NULL` bằng `=` hoặc `<>` cho `UNKNOWN`. Phải dùng `IS NULL` và `IS NOT NULL`.

### 3.2. NULLIF + BTRIM: coi chuỗi chỉ có khoảng trắng là thiếu

Trong PostgreSQL, `BTRIM(text)` bỏ các dấu cách thường ở hai đầu chuỗi; `NULLIF(x, '')` biến chuỗi rỗng thành `NULL`:

```sql
SELECT customer_row_id, customer_code, full_name, email
FROM customers_stage
WHERE NULLIF(BTRIM(email), '') IS NULL
ORDER BY customer_row_id;
```

Kết quả: **hàng 4 và 7**.

Giải thích:

- Hàng 4: `email` là `NULL`, nên biểu thức sau chuẩn hóa vẫn là `NULL`.
- Hàng 7: `'   '` trở thành `''` sau `BTRIM`, rồi `NULLIF('', '')` trả `NULL`.
- Hàng 5: `' em@example.com '` trở thành `'em@example.com'`, không được xem là thiếu.

Tương tự với tên:

```sql
SELECT customer_row_id, full_name
FROM customers_stage
WHERE NULLIF(BTRIM(full_name), '') IS NULL
ORDER BY customer_row_id;
-- Hàng 10
```

Với mã khách:

```sql
SELECT customer_row_id
FROM customers_stage
WHERE NULLIF(BTRIM(customer_code), '') IS NULL;
-- Hàng 9
```

**Giới hạn của cách kiểm tra:** `BTRIM` mặc định xử lý dấu cách thông thường, không nhất thiết nhận diện mọi ký tự trắng Unicode như tab, non-breaking space, zero-width space. Nếu dữ liệu nhập có những dạng này, cần quy tắc chuẩn hóa phù hợp với nguồn, encoding và DBMS; không coi `BTRIM` mặc định là bộ làm sạch mọi ký tự vô hình.

### 3.3. Đếm tỷ lệ thiếu của từng cột

Một báo cáo chất lượng có thể cần cả **số lượng** và **tỷ lệ**:

```sql
SELECT
    COUNT(*) AS total_customers,
    COUNT(*) FILTER (
        WHERE NULLIF(BTRIM(customer_code), '') IS NULL
    ) AS missing_customer_code,
    COUNT(*) FILTER (
        WHERE NULLIF(BTRIM(full_name), '') IS NULL
    ) AS missing_name,
    COUNT(*) FILTER (
        WHERE NULLIF(BTRIM(email), '') IS NULL
    ) AS missing_email,
    ROUND(
        100.0 * COUNT(*) FILTER (
            WHERE NULLIF(BTRIM(email), '') IS NULL
        ) / NULLIF(COUNT(*), 0),
        2
    ) AS missing_email_pct
FROM customers_stage;
```

Kết quả:

| total_customers | missing_customer_code | missing_name | missing_email | missing_email_pct |
|---:|---:|---:|---:|---:|
| 10 | 1 | 1 | 2 | 20.00 |

Mệnh đề `FILTER (WHERE ...)` của PostgreSQL cho phép đặt điều kiện riêng cho từng hàm tổng hợp. `NULLIF(COUNT(*), 0)` đề phòng chia cho 0 nếu bảng nguồn rỗng; lúc đó tỷ lệ có thể là `NULL` và phải được diễn giải là **không đủ mẫu để tính**, không mặc nhiên là 0%.

Nếu DBMS không hỗ trợ `FILTER`, dùng:

```sql
SUM(
    CASE WHEN NULLIF(TRIM(email), '') IS NULL
         THEN 1 ELSE 0 END
) AS missing_email
```

trong một `SELECT` tổng hợp tương đương.

### 3.4. Cột thiếu có thật sự là lỗi?

`NULL` có thể mang nhiều nghĩa: chưa được thu thập, không áp dụng, chưa biết, hoặc cố ý ẩn. Một người không có số điện thoại phụ không nhất thiết tạo lỗi chất lượng. Chỉ đánh dấu **bắt buộc** khi đã biết quy tắc của cột ở đúng thời điểm và trạng thái bản ghi.

Ví dụ, nếu một đơn `CANCELLED` được phép thiếu mã khách, quy tắc kiểm tra phải thể hiện ngoại lệ:

```sql
SELECT raw_id, order_ref, customer_code, status
FROM orders_stage
WHERE status <> 'CANCELLED'
  AND NULLIF(BTRIM(customer_code), '') IS NULL;
```

Với dữ liệu mẫu, `O007` là `CANCELLED` nên không xuất hiện ở truy vấn **ngoại lệ cho phép thiếu mã khách** này. Ngược lại, nếu quy định mọi đơn đều cần mã khách, dùng kiểm tra thiếu **không có điều kiện ngoại lệ**:

```sql
SELECT raw_id, order_ref
FROM orders_stage
WHERE NULLIF(BTRIM(customer_code), '') IS NULL;
-- raw_id 108, order_ref O007
```

Hai câu trả lời đều có thể đúng đối với **hai quy tắc khác nhau**.

## 4. Mẫu 2 — Phát hiện hàng liên quan bị thiếu

Một bản ghi có thể đầy đủ các cột nhưng **tham chiếu tới bản ghi không tồn tại**. Đây là lỗi liên kết dữ liệu hoặc dữ liệu nguồn chưa được nạp đầy đủ.

### 4.1. NOT EXISTS để tìm đơn có mã khách không tìm thấy

```sql
SELECT o.raw_id, o.order_ref, o.customer_code
FROM orders_stage AS o
WHERE o.customer_code IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM customers_stage AS c
      WHERE c.customer_code = o.customer_code
  )
ORDER BY o.raw_id;
```

Kết quả: **raw_id 105, đơn O004, mã C404**.

Truy vấn con được **tương quan** bằng `c.customer_code = o.customer_code`: mỗi hàng đơn được kiểm tra xem có bất kỳ khách nào có cùng mã không. `NOT EXISTS` trả `TRUE` nếu không tìm thấy.

Điều kiện `o.customer_code IS NOT NULL` giúp tách **thiếu giá trị khóa** khỏi **khóa có giá trị nhưng không tìm thấy đối tác**. Nếu bỏ điều kiện này, đơn có `customer_code = NULL` cũng có thể bị liệt kê là không tìm thấy khách, vì `NULL = c.customer_code` không cho `TRUE`.

**Lưu ý khi nguồn khách bị trùng:** mã `C002` có hai hàng trong `customers_stage`. `NOT EXISTS` vẫn chỉ hỏi “có ít nhất một khách không?”, nên không làm nhân đôi hàng đơn. Nhưng việc tìm thấy **một hoặc nhiều** khách không có nghĩa quan hệ đã hợp lệ nếu mã khách đáng lẽ phải duy nhất. Phải kiểm tra quy tắc trùng khóa riêng.

### 4.2. LEFT JOIN ... IS NULL

Cùng mục tiêu có thể viết:

```sql
SELECT o.raw_id, o.order_ref, o.customer_code
FROM orders_stage AS o
LEFT JOIN customers_stage AS c
    ON c.customer_code = o.customer_code
WHERE o.customer_code IS NOT NULL
  AND c.customer_row_id IS NULL
ORDER BY o.raw_id;
```

`c.customer_row_id` là khóa chính không `NULL`. Khi `LEFT JOIN` không tìm thấy khách, SQL bổ sung `NULL` cho các cột phía khách, nên `c.customer_row_id IS NULL` cho biết **không có hàng khách khớp**.

Không nên kiểm tra một cột khách **được phép `NULL`** như `c.email IS NULL` để kết luận không có khách. Khách C004 tồn tại nhưng email `NULL`; nếu dùng `c.email IS NULL`, có thể đánh dấu nhầm đơn O005 là đơn thiếu khách.

### 4.3. Phát hiện thanh toán không có đơn

```sql
SELECT p.payment_id, p.order_ref, p.payment_status, p.amount
FROM payments_stage AS p
WHERE p.order_ref IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM orders_stage AS o
      WHERE o.order_ref = p.order_ref
  )
ORDER BY p.payment_id;
```

Kết quả: **payment_id 209, order_ref O999**.

Tại đây nguồn đơn đang có `O003` trùng, nhưng `NOT EXISTS` chỉ quan tâm tồn tại ít nhất một hàng. Trong một hệ thống thực, cần làm rõ **nguồn nào là danh sách đối chiếu đáng tin cậy**. Nếu bảng đơn mới nạp được một phần, thanh toán tham chiếu đơn chưa nạp có thể là **lệch thời điểm đồng bộ** chứ chưa phải dữ liệu hỏng.

### 4.4. Tìm bản ghi ở bảng cha chưa có bản ghi con

Đôi khi “thiếu” không phải khóa sai, mà là **chưa có hoạt động**.

```sql
SELECT c.customer_row_id, c.customer_code, c.full_name
FROM customers_stage AS c
WHERE c.customer_code IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM orders_stage AS o
      WHERE o.customer_code = c.customer_code
  )
ORDER BY c.customer_row_id;
```

Với dữ liệu hiện tại, mọi mã khách không `NULL` từ `C001` đến `C008` đều có ít nhất một đơn tương ứng, nên truy vấn trả **0 hàng**. Điều đó không có nghĩa “mọi khách đều mua hàng” về mặt nghiệp vụ nếu bảng nguồn còn các bản ghi trùng và mã trống. Hàng khách 9 thiếu mã nên bị loại để tránh trộn hai loại vấn đề.

**Không có đơn** chỉ là lỗi nếu yêu cầu nghiệp vụ nói một khách bắt buộc phải có đơn trong khoảng thời gian cụ thể. Với danh sách người vừa đăng ký, không có đơn là điều bình thường.

## 5. Mẫu 3 — Phát hiện mã đơn hoặc mã khách bị trùng

### 5.1. GROUP BY ... HAVING COUNT(*) > 1

Để tìm khóa nghiệp vụ bị sử dụng nhiều lần:

```sql
SELECT
    order_ref,
    COUNT(*) AS row_count,
    MIN(raw_id) AS first_raw_id,
    MAX(raw_id) AS last_raw_id
FROM orders_stage
WHERE order_ref IS NOT NULL
GROUP BY order_ref
HAVING COUNT(*) > 1
ORDER BY row_count DESC, order_ref;
```

Kết quả:

| order_ref | row_count | first_raw_id | last_raw_id |
|---|---:|---:|---:|
| O003 | 2 | 103 | 104 |

Điều kiện `WHERE order_ref IS NOT NULL` quan trọng: nếu có nhiều đơn **thiếu mã**, `GROUP BY` sẽ gom chúng vào một nhóm `NULL`. Nhưng “nhiều mã trống” không nhất thiết là **cùng một đơn bị nhập hai lần**. Nên có phép kiểm tra **thiếu khóa** riêng.

Tìm mã khách trùng:

```sql
SELECT customer_code, COUNT(*) AS row_count
FROM customers_stage
WHERE NULLIF(BTRIM(customer_code), '') IS NOT NULL
GROUP BY customer_code
HAVING COUNT(*) > 1
ORDER BY customer_code;
```

Kết quả: **C002 có 2 hàng**.

### 5.2. Lấy đầy đủ chi tiết của các hàng trùng

`GROUP BY` chỉ cho biết khóa nào trùng và số bản sao, chưa cho thấy nội dung từng hàng. Có thể nối lại với danh sách khóa:

```sql
WITH duplicated_refs AS (
    SELECT order_ref
    FROM orders_stage
    WHERE order_ref IS NOT NULL
    GROUP BY order_ref
    HAVING COUNT(*) > 1
)
SELECT
    o.raw_id,
    o.order_ref,
    o.customer_code,
    o.ordered_on,
    o.status,
    o.amount,
    o.loaded_at
FROM orders_stage AS o
JOIN duplicated_refs AS d
    ON d.order_ref = o.order_ref
ORDER BY o.order_ref, o.loaded_at, o.raw_id;
```

Kết quả là **hai hàng 103 và 104** của `O003`, cùng thông tin nghiệp vụ nhưng khác `raw_id` và `loaded_at`. Đây là bằng chứng cho khả năng **nạp trùng**.

### 5.3. Trùng khóa khác trùng toàn bộ nội dung

Hai trường hợp cần phân biệt:

- **Trùng khóa nghiệp vụ**: hai hàng có cùng `order_ref` dù `amount`, `status` hoặc ngày khác nhau. Có thể là lỗi nhập hoặc hai phiên bản thay đổi của cùng đơn.
- **Trùng nội dung nghiệp vụ**: hai hàng giống nhau trên tập cột được chọn, dù mang `raw_id` khác nhau. Có thể là gửi lại cùng sự kiện.

Để kiểm tra trùng nội dung trên năm cột nghiệp vụ:

```sql
SELECT
    order_ref,
    customer_code,
    ordered_on,
    status,
    amount,
    COUNT(*) AS copies
FROM orders_stage
GROUP BY
    order_ref,
    customer_code,
    ordered_on,
    status,
    amount
HAVING COUNT(*) > 1
ORDER BY copies DESC, order_ref;
```

Kết quả gồm nhóm **`O003, C003, 2025-03-03, PAID, 200.00` với 2 bản sao**. Hai hàng có `raw_id` khác nhưng cùng các trường được coi là nội dung nghiệp vụ.

**Nhắc lại về `NULL`:** `GROUP BY` đặt các giá trị `NULL` cùng vị trí vào một nhóm. Nếu có hai đơn không có `order_ref` và mọi cột còn lại giống nhau, chúng có thể được báo là trùng nội dung; đó là **ứng viên** cần phân tích, không có nghĩa hai bản ghi chắc chắn là một giao dịch.

### 5.4. Dùng hàm cửa sổ để thấy từng hàng thuộc nhóm trùng

`COUNT(*) OVER (PARTITION BY order_ref)` cho biết tần suất ngay cạnh mỗi hàng:

```sql
SELECT
    raw_id,
    order_ref,
    loaded_at,
    COUNT(*) OVER (
        PARTITION BY order_ref
    ) AS copies_of_ref
FROM orders_stage
WHERE order_ref IS NOT NULL
ORDER BY order_ref, loaded_at, raw_id;
```

Hai hàng `O003` sẽ có `copies_of_ref = 2`. Ưu điểm là vẫn **giữ đầy đủ chi tiết của từng hàng**, không phải nối ngược sau `GROUP BY`.

Để chỉ xem hàng trùng, cần lọc **cấp ngoài**:

```sql
WITH marked AS (
    SELECT
        raw_id,
        order_ref,
        loaded_at,
        COUNT(*) OVER (
            PARTITION BY order_ref
        ) AS copies_of_ref
    FROM orders_stage
    WHERE order_ref IS NOT NULL
)
SELECT *
FROM marked
WHERE copies_of_ref > 1
ORDER BY order_ref, loaded_at, raw_id;
```

Không đặt trực tiếp `WHERE COUNT(*) OVER (...) > 1` ở cùng cấp truy vấn trong PostgreSQL, vì hàm cửa sổ không được dùng trong `WHERE` cùng cấp.

## 6. Mẫu 4 — Trùng sau khi chuẩn hóa: chữ hoa, khoảng trắng và biểu diễn

Không phải dữ liệu trùng nào cũng giống hệt từng byte.

Ví dụ, `'An@Example.com'` và `'AN@example.com'` khác nhau khi so chuỗi phân biệt hoa/thường; `' em@example.com '` và `'em@example.com'` khác nhau vì khoảng trắng. Nếu quy tắc nghiệp vụ yêu cầu **email không được lặp sau khi chuẩn hóa**, phải dùng biểu thức chuẩn hóa nhất quán.

### 6.1. Tạo khóa email chuẩn hóa

```sql
SELECT
    customer_row_id,
    email,
    NULLIF(LOWER(BTRIM(email)), '') AS normalized_email
FROM customers_stage
ORDER BY customer_row_id;
```

Ví dụ:

| customer_row_id | email gốc | normalized_email |
|---:|---|---|
| 1 | An@Example.com | an@example.com |
| 5 | `' em@example.com '` | em@example.com |
| 6 | AN@example.com | an@example.com |
| 7 | `'   '` | `NULL` |

`LOWER` và `BTRIM` là **quy tắc đơn giản cho ví dụ**. Chuẩn hóa email thật có các vấn đề phức tạp về tên miền quốc tế, Unicode, quy tắc phân biệt chữ hoa ở local-part, dấu chấm/dấu cộng ở một số nhà cung cấp và chính sách tài khoản dùng chung. Không tự ý xóa hoặc gộp người dùng chỉ vì hai email giống nhau theo `LOWER`.

### 6.2. Tìm email chuẩn hóa bị trùng

```sql
WITH normalized AS (
    SELECT
        customer_row_id,
        NULLIF(LOWER(BTRIM(email)), '') AS normalized_email
    FROM customers_stage
)
SELECT
    normalized_email,
    COUNT(*) AS copies,
    ARRAY_AGG(customer_row_id ORDER BY customer_row_id) AS source_rows
FROM normalized
WHERE normalized_email IS NOT NULL
GROUP BY normalized_email
HAVING COUNT(*) > 1
ORDER BY normalized_email;
```

Kết quả: **`an@example.com` có 2 bản ghi, source_rows = `{1,6}`**.

`ARRAY_AGG` là cú pháp tổng hợp mảng của PostgreSQL. Nếu DBMS không có, có thể chỉ trả email và số bản sao, sau đó nối lại với bảng nguồn để lấy danh sách ID.

**Tách hai quy tắc:** một email `NULL`/trống là **thiếu**, không phải cùng một “email trùng” với mọi email `NULL` khác. Vì thế truy vấn trên loại `normalized_email IS NULL` trước khi đếm trùng.

### 6.3. Định nghĩa chuẩn hóa cần cố định

Một quy tắc thường gặp:

```sql
NULLIF(LOWER(BTRIM(customer_code)), '')
```

Nhưng nếu mã khách là **case-sensitive** theo nghiệp vụ thì `'Ab01'` và `'AB01'` có thể là hai mã khác nhau. Chuẩn hóa quá mạnh sẽ báo trùng sai. Tương tự, thay toàn bộ ký tự trắng, bỏ dấu tiếng Việt hay loại dấu câu đều cần quyết định nghiệp vụ riêng.

Khi tạo báo cáo chất lượng, nên hiển thị **giá trị gốc và giá trị chuẩn hóa** cạnh nhau, để người kiểm tra biết hai bản ghi bị ghép vào cùng nhóm vì quy tắc nào.

## 7. Mẫu 5 — Chọn một bản ghi đại diện trong tập trùng

**Phát hiện trùng** không đồng nghĩa **xóa trùng**. Trong các tập nguồn có cập nhật theo phiên bản, hai hàng cùng mã đơn có thể chứa hai trạng thái khác nhau, và hàng mới nhất chưa chắc là hàng đúng theo nghiệp vụ.

Nếu có yêu cầu rõ: “đối với mỗi `order_ref`, chọn phiên bản nạp gần nhất; nếu trùng thời điểm thì lấy `raw_id` lớn hơn”, có thể dùng `ROW_NUMBER`.

### 7.1. Tạo tập đơn đại diện, không thay đổi bảng nguồn

```sql
WITH ranked_orders AS (
    SELECT
        o.*,
        ROW_NUMBER() OVER (
            PARTITION BY o.order_ref
            ORDER BY o.loaded_at DESC, o.raw_id DESC
        ) AS rn
    FROM orders_stage AS o
    WHERE o.order_ref IS NOT NULL
)
SELECT
    raw_id,
    order_ref,
    customer_code,
    ordered_on,
    status,
    amount,
    loaded_at
FROM ranked_orders
WHERE rn = 1
ORDER BY order_ref;
```

Kết quả giữ **raw_id 104** làm đại diện cho `O003` vì `loaded_at` của nó mới hơn raw_id 103. Những mã đơn khác chỉ có một hàng nên vẫn được giữ. Tập này gồm **12 hàng**, mỗi mã đơn không `NULL` tối đa một hàng.

Hàng 112 thiếu `order_ref` được **loại khỏi tập đại diện để xử lý riêng**. Nếu bỏ `WHERE o.order_ref IS NOT NULL`, các hàng thiếu mã đều nằm trong một partition `NULL`; `ROW_NUMBER = 1` có thể giữ một hàng và làm mất các hàng thiếu khóa còn lại một cách âm thầm.

### 7.2. Vì sao phải có tie-breaker?

Nếu hai bản ghi cùng `order_ref` có cùng `loaded_at`, câu:

```sql
ORDER BY loaded_at DESC
```

không xác định chắc hàng nào nhận `rn = 1`. Thêm `raw_id DESC` — khóa kỹ thuật duy nhất trong bảng — tạo quy tắc chọn rõ ràng.

Tuy nhiên, **“mới được nạp” không phải lúc nào cũng là “đúng nhất”**: một lô nạp lại dữ liệu cũ có thể đến sau dữ liệu đã sửa. Trong hệ thống có lịch sử phiên bản, có thể cần cột `source_version`, `effective_at`, độ ưu tiên nguồn hoặc trạng thái xác nhận để chọn bản ghi chuẩn.

### 7.3. DISTINCT không tự chọn phiên bản đúng

`SELECT DISTINCT order_ref, amount, status FROM orders_stage` chỉ loại các hàng **giống nhau trên toàn bộ cột chọn**. Nếu một đơn có hai phiên bản khác tiền, hai hàng vẫn xuất hiện; nếu chỉ `DISTINCT order_ref` thì mất các cột khác cần cho việc đối soát. Khi cần **một hàng đầy đủ có ưu tiên xác định**, dùng `ROW_NUMBER` và tiêu chí cụ thể hoặc `DISTINCT ON` của PostgreSQL với `ORDER BY` phù hợp.

### 7.4. Không xóa bản ghi trùng một cách vội vàng

Ví dụ bảng staging chứa hai `O003`, có thể đó là hai lần nạp cùng một đơn. Nhưng trước khi `DELETE`:

- Xác định **khóa nghiệp vụ** và ngoại lệ.
- Giữ nguồn gốc, batch ID, lý do chọn phiên bản được giữ.
- Kiểm tra các bảng khác có tham chiếu `raw_id` hay không.
- Cân nhắc hiệu ứng đồng thời và giao dịch.
- Phân biệt **bản ghi trùng** với **sự kiện lặp hợp lệ**; hai khoản thanh toán cùng tiền không tự nhiên là bản sao.

Bài này chỉ minh họa **truy vấn chọn bản ghi đại diện**, không tiến hành xóa dữ liệu nguồn.

## 8. Mẫu 6 — Phát hiện giá trị ngoài miền hợp lệ

Đây là lớp kiểm tra dễ chuyển thành `CHECK` constraint ở bảng nghiệp vụ chính, nhưng vẫn cần kiểm tra khi nhận dữ liệu staging.

### 8.1. Số tiền âm, bằng 0 hoặc chưa xác định

Theo quy tắc minh họa, một đơn không được âm tiền:

```sql
SELECT raw_id, order_ref, amount
FROM orders_stage
WHERE amount < 0
ORDER BY raw_id;
-- raw_id 107, O006, amount = -20
```

Nhưng một câu truy vấn như `WHERE amount < 0` **không tìm ra `NULL`**, vì `NULL < 0` cho `UNKNOWN`. Nếu tiền là bắt buộc:

```sql
SELECT raw_id, order_ref, status, amount
FROM orders_stage
WHERE amount IS NULL
   OR amount < 0
ORDER BY raw_id;
-- O005 (NULL), O006 (-20)
```

Đối với đơn `PAID`, ví dụ quy định tiền phải **lớn hơn 0**:

```sql
SELECT raw_id, order_ref, status, amount
FROM orders_stage
WHERE status = 'PAID'
  AND (
      amount IS NULL
      OR amount <= 0
  )
ORDER BY raw_id;
-- O005 (NULL), O010 (0)
```

**Tại sao không chỉ viết `NOT (amount > 0)`?** Với `NULL`, `amount > 0` là `UNKNOWN` và phủ định vẫn `UNKNOWN`; `WHERE` sẽ không giữ hàng thiếu tiền. Khi `NULL` là một trường hợp lỗi, phải viết `IS NULL` tường minh hoặc dùng biểu thức null-safe phù hợp.

### 8.2. Trạng thái nằm ngoài tập cho phép

```sql
SELECT raw_id, order_ref, status
FROM orders_stage
WHERE status IS NULL
   OR status NOT IN ('NEW', 'PAID', 'CANCELLED')
ORDER BY raw_id;
-- raw_id 114, O012, status = UNKNOWN
```

Tập literal của `NOT IN` trong truy vấn này **không chứa `NULL`**, nên điều kiện `status NOT IN (...)` dùng được cho các trạng thái đã biết; ta thêm `status IS NULL` để bắt cả trạng thái thiếu.

Trong trường hợp giá trị hợp lệ nằm ở một bảng danh mục riêng có thể chứa `NULL`, `NOT EXISTS` tương quan thường tránh bẫy `NOT IN` có phần tử `NULL`.

### 8.3. Ngày nằm ngoài cửa sổ nghiệp vụ

Để có kết quả **cố định và tái lập**, lấy mốc kiểm tra `DATE '2025-03-15'` thay vì mặc định dùng ngày máy chủ:

```sql
WITH parameters AS (
    SELECT DATE '2025-03-15' AS as_of_date
)
SELECT
    o.raw_id,
    o.order_ref,
    o.ordered_on,
    p.as_of_date
FROM orders_stage AS o
CROSS JOIN parameters AS p
WHERE o.ordered_on > p.as_of_date
ORDER BY o.raw_id;
-- O011, ordered_on = 2025-04-05
```

Mốc `as_of_date` được chọn cho bài tập, **không phải ngày hiện tại** của người đọc. Khi kiểm tra dữ liệu thực, có thể thay bằng ngày chốt báo cáo, thời gian watermark hoặc một tham số do quy trình nạp truyền vào.

Một ngày tương lai có thể là **đơn đặt trước** hợp lệ. Chỉ đánh dấu lỗi nếu hợp đồng dữ liệu nói `ordered_on` là ngày giao dịch đã xảy ra, không phải ngày dự kiến.

### 8.4. Kiểm tra quan hệ giữa các cột thời gian

Ví dụ quy tắc: thời điểm nạp không được sớm hơn ngày ghi nhận giao dịch, trừ khi ứng dụng hỗ trợ đơn đặt trước.

```sql
SELECT raw_id, order_ref, ordered_on, loaded_at
FROM orders_stage
WHERE ordered_on IS NOT NULL
  AND loaded_at < ordered_on::TIMESTAMP
ORDER BY raw_id;
-- O011 trong bộ dữ liệu mẫu
```

Đoạn trên so `TIMESTAMP` với đầu ngày của `ordered_on`. Nếu dữ liệu thời gian đi qua nhiều múi giờ, phải chuyển về **cùng chuẩn thời gian** trước khi so. Không nhầm ngày nghiệp vụ, ngày ghi nhận giao dịch, ngày dự kiến và ngày nạp vào kho dữ liệu.

## 9. Mẫu 7 — Phát hiện giá trị cực đoan bằng ngưỡng

Một giá trị quá lớn không tự động sai. Trước khi áp dụng thống kê, hãy hỏi: **có giới hạn nghiệp vụ cứng hay chỉ có phân bố thường gặp?**

### 9.1. Ngưỡng nghiệp vụ cố định

Giả sử màn hình chỉ xử lý đơn không vượt 1.000 đơn vị tiền và muốn kiểm tra những trường hợp lớn hơn:

```sql
SELECT raw_id, order_ref, amount
FROM orders_stage
WHERE amount > 1000
ORDER BY amount DESC, raw_id;
-- O008, 5000
```

Đây là **cảnh báo theo ngưỡng minh họa**. Nếu ngưỡng 1.000 là hạn mức phê duyệt, đơn 5.000 cần **duyệt thủ công**; chưa đủ căn cứ khẳng định số tiền 5.000 là dữ liệu sai.

### 9.2. So với phân bố bằng khoảng tứ phân vị (IQR)

Khi không có ngưỡng cứng, ta có thể dùng **IQR**:

\[
\mathrm{IQR}=Q_3-Q_1
\]

Một quy tắc phát hiện ứng viên bất thường phía trên có dạng:

\[
\text{upper fence}=Q_3+3\times\mathrm{IQR}
\]

Hệ số `3` ở đây là lựa chọn thận trọng để gắn cờ cực trị; tùy yêu cầu có thể dùng `1.5` hoặc một ngưỡng khác. Không có hệ số chung đúng cho mọi lĩnh vực.

Với PostgreSQL, có thể tính tứ phân vị bằng `PERCENTILE_CONT`. Để tránh tính lặp đơn `O003`, ta chọn một hàng đại diện cho mỗi mã đơn trước, rồi chỉ đưa tiền dương đã biết vào phân bố:

```sql
WITH ranked AS (
    SELECT
        o.*,
        ROW_NUMBER() OVER (
            PARTITION BY order_ref
            ORDER BY loaded_at DESC, raw_id DESC
        ) AS rn
    FROM orders_stage AS o
    WHERE order_ref IS NOT NULL
),
canonical_orders AS (
    SELECT order_ref, amount
    FROM ranked
    WHERE rn = 1
),
known_positive AS (
    SELECT order_ref, amount
    FROM canonical_orders
    WHERE amount > 0
),
quartiles AS (
    SELECT
        PERCENTILE_CONT(0.25) WITHIN GROUP (
            ORDER BY amount::DOUBLE PRECISION
        ) AS q1,
        PERCENTILE_CONT(0.75) WITHIN GROUP (
            ORDER BY amount::DOUBLE PRECISION
        ) AS q3
    FROM known_positive
)
SELECT
    k.order_ref,
    k.amount,
    q.q1,
    q.q3,
    q.q3 + 3 * (q.q3 - q.q1) AS upper_fence
FROM known_positive AS k
CROSS JOIN quartiles AS q
WHERE q.q1 IS NOT NULL
  AND q.q3 IS NOT NULL
  AND k.amount > q.q3 + 3 * (q.q3 - q.q1)
ORDER BY k.amount DESC, k.order_ref;
```

Với bộ dữ liệu mẫu sau khi loại trùng `O003`, khoản **O008 = 5.000** là ứng viên nổi bật. Truy vấn này chỉ giúp **phát hiện**; lý do thực tế có thể là đơn giá trị lớn hợp lệ.

### 9.3. Những giới hạn của thống kê đơn giản

- Một vài giá trị cực đoan có thể làm phân bố méo, đặc biệt ở tập rất nhỏ.
- Nhóm có quá ít mẫu không nên được đánh giá bằng ngưỡng thống kê cứng.
- Nếu `IQR = 0` do đa số giá trị bằng nhau, cần quy tắc riêng để tránh gắn cờ quá mức.
- Nên so các đơn cùng **đơn vị tiền, kênh bán, phân khúc, loại giao dịch**, thay vì trộn mọi đối tượng không đồng nhất.
- Dữ liệu có mùa vụ, xu hướng hoặc chiến dịch khuyến mãi có thể làm số tiền “bình thường” thay đổi theo thời gian.

Đây là lý do bất thường thống kê nên có mức **cảnh báo cần xác minh** thay vì mặc định sửa số tiền hoặc hủy đơn.

## 10. Mẫu 8 — Đối soát hai bảng để phát hiện bất thường nghiệp vụ

Đối soát thường mạnh hơn kiểm tra một cột đơn lẻ. Ví dụ: một đơn ở trạng thái `PAID` nhưng tổng tiền thanh toán đã thực thu chưa bằng số tiền đơn.

### 10.1. Vì sao phải chuẩn hóa mức chi tiết trước khi JOIN?

Trong dữ liệu nguồn:

- `orders_stage` có **hai hàng cùng `order_ref = 'O003'`**.
- `payments_stage` có **hai dòng cho `O003`**, một `CAPTURED` và một `FAILED`.

Nếu nối thẳng `orders_stage` với `payments_stage` rồi `SUM(p.amount)`, nhiều hàng nguồn có thể làm **nhân bản dòng thanh toán**. Ngoài ra, nếu không lọc `CAPTURED`, ta sẽ cộng cả khoản thất bại.

Vì thế, cách đối soát gồm ba bước:

1. Chọn **một hàng đại diện cho mỗi mã đơn** theo quy tắc rõ ràng.
2. Tổng hợp **tiền thực thu** ở bảng thanh toán thành **một hàng mỗi mã đơn**.
3. Nối hai tập đã thống nhất mức chi tiết, rồi so sánh theo quy tắc nghiệp vụ.

### 10.2. CTE đối soát thanh toán

```sql
WITH ranked_orders AS (
    SELECT
        o.*,
        ROW_NUMBER() OVER (
            PARTITION BY order_ref
            ORDER BY loaded_at DESC, raw_id DESC
        ) AS rn
    FROM orders_stage AS o
    WHERE order_ref IS NOT NULL
),
canonical_orders AS (
    SELECT order_ref, status, amount
    FROM ranked_orders
    WHERE rn = 1
),
captured_by_order AS (
    SELECT
        p.order_ref,
        SUM(p.amount) AS captured_amount
    FROM payments_stage AS p
    WHERE p.payment_status = 'CAPTURED'
    GROUP BY p.order_ref
)
SELECT
    o.order_ref,
    o.status,
    o.amount AS order_amount,
    COALESCE(p.captured_amount, 0) AS captured_amount,
    o.amount - COALESCE(p.captured_amount, 0) AS difference
FROM canonical_orders AS o
LEFT JOIN captured_by_order AS p
    ON p.order_ref = o.order_ref
WHERE o.status = 'PAID'
  AND o.amount IS NOT NULL
  AND o.amount <> COALESCE(p.captured_amount, 0)
ORDER BY o.order_ref;
```

Kết quả theo dữ liệu mẫu:

| order_ref | status | order_amount | captured_amount | difference |
|---|---|---:|---:|---:|
| O008 | PAID | 5000.00 | 1000.00 | 4000.00 |

Đơn **O008** bị gắn cờ vì ở trạng thái `PAID` nhưng tổng tiền đã ghi nhận là **1.000**, thiếu **4.000** so với số tiền đơn **5.000**.

Các trường hợp khác:

- `O001`: 120 so với 120 — khớp.
- `O003`: 200 so với 200 — khớp sau khi loại trùng bản ghi đơn và chỉ cộng `CAPTURED`.
- `O004`: 150 so với 150 — khớp về số tiền, **nhưng vẫn có lỗi mã khách C404 không tồn tại**.
- `O005`: `amount = NULL` — **không được phép** để phép đối soát coi là một khoản tiền 0; truy vấn có chủ đích loại hàng này vì phải được báo trong **kiểm tra thiếu tiền** riêng.
- `O010`: 0 so với 0 — khớp số học, **nhưng vi phạm quy tắc `PAID` phải lớn hơn 0** trong bài.

**Kết quả đối soát bằng 0 không chứng minh bản ghi hợp lệ về mọi mặt.** Mỗi quy tắc kiểm tra phải được diễn giải trong phạm vi riêng.

### 10.3. Phân biệt thiếu thanh toán với chênh lệch tiền

Trong câu trên, `COALESCE(p.captured_amount, 0)` coi “không có dòng `CAPTURED`” là 0 để phục vụ phép trừ. Đây là **quy tắc nghiệp vụ minh họa**, không phải lúc nào cũng phù hợp: với hệ thống dữ liệu đồng bộ trễ, chưa có dòng thanh toán có thể nghĩa là **chưa nhận dữ liệu**, không phải chắc chắn đã thu 0.

Có thể tách hai vấn đề:

```sql
WITH canonical AS (
    SELECT *
    FROM (
        SELECT
            o.*,
            ROW_NUMBER() OVER (
                PARTITION BY order_ref
                ORDER BY loaded_at DESC, raw_id DESC
            ) AS rn
        FROM orders_stage AS o
        WHERE order_ref IS NOT NULL
    ) AS ranked
    WHERE rn = 1
)
SELECT o.order_ref
FROM canonical AS o
WHERE o.status = 'PAID'
  AND NOT EXISTS (
      SELECT 1
      FROM payments_stage AS p
      WHERE p.order_ref = o.order_ref
        AND p.payment_status = 'CAPTURED'
  )
ORDER BY o.order_ref;
```

Với dữ liệu mẫu, **không có** đơn `PAID` nào thiếu *hoàn toàn* dòng `CAPTURED`; nhưng vẫn có đơn **O008 thiếu tiền** và đơn **O005 thiếu số tiền đơn**. Sự khác biệt cho thấy phải kiểm tra **sự tồn tại của bản ghi** và **giá trị tổng hợp** như hai câu hỏi riêng.

### 10.4. Kiểm tra hai chiều

Đối soát giữa hai nguồn thường cần cả:

- **Đơn có thanh toán không phù hợp**: bắt đầu từ tập đơn để kiểm tra tiền thực thu.
- **Thanh toán không có đơn**: bắt đầu từ bảng thanh toán và dùng `NOT EXISTS` để tìm `O999`.

Nếu chỉ chạy một chiều, có thể bỏ sót những hàng **chỉ có trong bảng thanh toán** hoặc **chỉ có trong bảng đơn**. Đó là nguyên tắc tương tự phép hiệu hai tập: `A EXCEPT B` và `B EXCEPT A` có thể cho kết quả khác nhau.

## 11. Mẫu 9 — Phát hiện dữ liệu thiếu theo lịch hoặc chuỗi thời gian

Một ngày không xuất hiện trong dữ liệu không nhất thiết là ngày thiếu. Để phát hiện “không có dữ liệu ngày X”, phải có một tập **ngày được kỳ vọng**.

### 11.1. Tạo các ngày kỳ vọng bằng generate_series

Trong PostgreSQL, ví dụ quy trình báo cáo yêu cầu ít nhất **một đơn mỗi ngày từ 01/03 đến 15/03/2025**:

```sql
WITH expected_days AS (
    SELECT d::DATE AS business_day
    FROM GENERATE_SERIES(
        DATE '2025-03-01',
        DATE '2025-03-15',
        INTERVAL '1 day'
    ) AS g(d)
),
observed_days AS (
    SELECT DISTINCT ordered_on AS business_day
    FROM orders_stage
    WHERE ordered_on IS NOT NULL
      AND ordered_on >= DATE '2025-03-01'
      AND ordered_on <= DATE '2025-03-15'
)
SELECT e.business_day
FROM expected_days AS e
LEFT JOIN observed_days AS o
    ON o.business_day = e.business_day
WHERE o.business_day IS NULL
ORDER BY e.business_day;
```

Kết quả: **2025-03-13, 2025-03-14, 2025-03-15**, vì các ngày 01/03–12/03 đều có ít nhất một đơn trong dữ liệu mẫu.

Đây **chỉ** là thiếu dữ liệu nếu có **quy tắc rằng ngày nào cũng phải có đơn**. Với hệ thống bán lẻ ít giao dịch, ngày không có đơn có thể bình thường. Nếu muốn kiểm tra lịch nạp ETL, nên đối chiếu **danh sách batch dự kiến** và **batch hoàn thành** thay vì suy ra từ sự có mặt của đơn hàng.

### 11.2. Không nhầm ngày thiếu với mã ID không liên tục

Các khóa tự tăng thường có **khoảng trống** do giao dịch rollback, xóa bản ghi, cấp phát trước hoặc phân phối nhiều node. Ví dụ `raw_id` thiếu 115 chưa đủ chứng minh một đơn bị mất.

Nếu nghiệp vụ thực sự yêu cầu **số chứng từ liên tục**, hãy kiểm tra đúng **chuỗi số chứng từ có quy tắc cấp phát xác nhận**; không suy luận từ một khóa kỹ thuật nội bộ.

### 11.3. LAG để xem khoảng cách giữa các sự kiện

Khi muốn phát hiện khoảng thời gian dài bất thường giữa các đơn của cùng khách:

```sql
WITH canonical AS (
    SELECT order_ref, customer_code, ordered_on
    FROM (
        SELECT
            o.*,
            ROW_NUMBER() OVER (
                PARTITION BY order_ref
                ORDER BY loaded_at DESC, raw_id DESC
            ) AS rn
        FROM orders_stage AS o
        WHERE order_ref IS NOT NULL
          AND customer_code IS NOT NULL
          AND ordered_on IS NOT NULL
    ) AS ranked
    WHERE rn = 1
),
with_previous AS (
    SELECT
        customer_code,
        order_ref,
        ordered_on,
        LAG(ordered_on) OVER (
            PARTITION BY customer_code
            ORDER BY ordered_on, order_ref
        ) AS previous_ordered_on
    FROM canonical
)
SELECT
    customer_code,
    order_ref,
    previous_ordered_on,
    ordered_on,
    ordered_on - previous_ordered_on AS gap_days
FROM with_previous
WHERE previous_ordered_on IS NOT NULL
ORDER BY customer_code, ordered_on, order_ref;
```

Trong PostgreSQL, trừ hai giá trị kiểu `DATE` trả số ngày. Có thể bổ sung `AND ordered_on - previous_ordered_on > 30` để gắn cờ khoảng cách hơn 30 ngày.

Ở đây **LAG** giúp xem khoảng thời gian giữa **những giao dịch có mặt trong dữ liệu**, không tự tạo ra bản ghi của ngày bị thiếu. Khách có một đơn không có hàng trước để tính khoảng cách; khách chưa có đơn cũng không xuất hiện. Muốn kiểm tra tính đầy đủ theo ngày, cần một **lịch kỳ vọng** như mục 11.1.

## 12. Mẫu 10 — Tạo danh sách cảnh báo có mã quy tắc và nguồn gốc

Khi số quy tắc tăng lên, sẽ khó quản lý nếu mỗi kiểm tra trả một cấu trúc cột riêng. Một cách đơn giản là chuẩn hóa kết quả về các cột:

| Cột | Ý nghĩa |
|---|---|
| `rule_code` | Mã kiểm tra ổn định, ví dụ `ORD_REF_REQUIRED` |
| `record_type` | Loại bản ghi: `CUSTOMER`, `ORDER`, `PAYMENT` |
| `record_id` | Khóa kỹ thuật của hàng nguồn |
| `detail` | Mô tả ngắn hoặc giá trị liên quan |

Ví dụ hợp nhất ba phép kiểm tra bằng `UNION ALL`:

```sql
WITH issues AS (
    SELECT
        'CUS_EMAIL_REQUIRED'::TEXT AS rule_code,
        'CUSTOMER'::TEXT AS record_type,
        c.customer_row_id::TEXT AS record_id,
        'Email missing or blank'::TEXT AS detail
    FROM customers_stage AS c
    WHERE NULLIF(BTRIM(c.email), '') IS NULL

    UNION ALL

    SELECT
        'ORD_REF_REQUIRED'::TEXT AS rule_code,
        'ORDER'::TEXT AS record_type,
        o.raw_id::TEXT AS record_id,
        'Order reference missing or blank'::TEXT AS detail
    FROM orders_stage AS o
    WHERE NULLIF(BTRIM(o.order_ref), '') IS NULL

    UNION ALL

    SELECT
        'ORD_AMOUNT_NONNEGATIVE'::TEXT AS rule_code,
        'ORDER'::TEXT AS record_type,
        o.raw_id::TEXT AS record_id,
        'Negative amount: ' || o.amount::TEXT AS detail
    FROM orders_stage AS o
    WHERE o.amount < 0
)
SELECT rule_code, record_type, record_id, detail
FROM issues
ORDER BY rule_code, record_type, record_id;
```

Kết quả có **4 cảnh báo**:

| rule_code | record_type | record_id | detail |
|---|---|---|---|
| CUS_EMAIL_REQUIRED | CUSTOMER | 4 | Email missing or blank |
| CUS_EMAIL_REQUIRED | CUSTOMER | 7 | Email missing or blank |
| ORD_AMOUNT_NONNEGATIVE | ORDER | 107 | Negative amount: -20.00 |
| ORD_REF_REQUIRED | ORDER | 112 | Order reference missing or blank |

Một bản ghi có thể vi phạm **nhiều quy tắc**, nên dùng `UNION ALL` để **giữ từng cảnh báo**, không dùng `UNION` vô tình loại những hàng báo cáo giống nhau trên các cột được chọn.

### 12.1. Đếm số trường hợp của từng quy tắc

Trên cùng CTE `issues`:

```sql
SELECT
    rule_code,
    COUNT(*) AS issue_count,
    COUNT(DISTINCT record_type || ':' || record_id) AS affected_rows
FROM issues
GROUP BY rule_code
ORDER BY rule_code;
```

`issue_count` đếm số dòng cảnh báo; `affected_rows` đếm số **khóa bản ghi nguồn phân biệt** theo quy tắc. Trong ví dụ mỗi hàng chỉ có một cảnh báo trên mỗi quy tắc, nên hai số giống nhau.

Nếu muốn số **bản ghi có ít nhất một vấn đề trên tất cả quy tắc**, phải lấy `COUNT(DISTINCT record_type || ':' || record_id)` trên toàn bộ `issues`, không cộng số bản ghi của các quy tắc riêng lẻ vì một hàng có thể vi phạm nhiều quy tắc.

### 12.2. Chú ý việc ghép chuỗi để tạo khóa cảnh báo

Mẫu `record_type || ':' || record_id` chỉ an toàn khi giá trị đầu vào được xác định và quy ước phân tách không gây va chạm. Ở ví dụ, `record_id` được ép từ khóa số nguyên không `NULL` nên phù hợp. Với khóa nhiều cột có thể chứa dấu phân cách, cần dùng kiểu dữ liệu có cấu trúc, các cột khóa riêng hoặc cơ chế mã hóa không nhập nhằng.

Trong hệ thống thật, nên thêm `batch_id`, `source_system`, `observed_at`, mức độ nghiêm trọng và trạng thái xử lý để truy ngược lỗi và đo xu hướng theo thời gian. Những trường đó là **thiết kế báo cáo chất lượng**, không tự tạo bởi `UNION ALL`.

## 13. Mẫu 11 — Kiểm tra tỷ lệ và phát hiện biến động bất thường theo kỳ

Không phải lúc nào cần xem từng hàng; đôi khi vấn đề xuất hiện qua **xu hướng**. Ví dụ số bản ghi thiếu email tăng từ 1% lên 25% sau khi đổi quy trình nhập liệu.

### 13.1. Tỷ lệ thiếu theo ngày nạp

Trên bảng khách có `created_on`:

```sql
SELECT
    created_on,
    COUNT(*) AS total_rows,
    SUM(
        CASE WHEN NULLIF(BTRIM(email), '') IS NULL
             THEN 1 ELSE 0 END
    ) AS missing_email_rows,
    ROUND(
        100.0 * SUM(
            CASE WHEN NULLIF(BTRIM(email), '') IS NULL
                 THEN 1 ELSE 0 END
        ) / NULLIF(COUNT(*), 0),
        2
    ) AS missing_pct
FROM customers_stage
GROUP BY created_on
ORDER BY created_on;
```

Ở dữ liệu nhỏ, tỷ lệ theo từng ngày dễ nhảy rất mạnh chỉ vì một hàng. Trong vận hành, nên đặt **mức mẫu tối thiểu**, so với **cùng loại nguồn**, và cân nhắc chu kỳ ngày/tuần/tháng theo tần suất dữ liệu.

### 13.2. Gắn cờ một kỳ vượt ngưỡng

Ví dụ giả định tỷ lệ thiếu email cho phép không quá 10% trong một batch:

```sql
WITH by_day AS (
    SELECT
        created_on,
        COUNT(*) AS total_rows,
        COUNT(*) FILTER (
            WHERE NULLIF(BTRIM(email), '') IS NULL
        ) AS missing_rows
    FROM customers_stage
    GROUP BY created_on
)
SELECT
    created_on,
    total_rows,
    missing_rows,
    ROUND(100.0 * missing_rows / NULLIF(total_rows, 0), 2)
        AS missing_pct
FROM by_day
WHERE total_rows >= 1
  AND 1.0 * missing_rows / NULLIF(total_rows, 0) > 0.10
ORDER BY created_on;
```

`WHERE total_rows >= 1` chỉ để minh họa; trong thực tế một ngày có đúng một khách và một email thiếu tạo tỷ lệ 100%, nhưng mẫu quá nhỏ không đủ để kết luận chất lượng quy trình xấu. Hệ thống thật thường sử dụng ngưỡng mẫu tối thiểu lớn hơn, so sánh lịch sử và phân loại nguyên nhân.

### 13.3. LAG để so chỉ số giữa hai kỳ

Từ một bảng tổng hợp chất lượng theo ngày hoặc batch, có thể dùng `LAG`:

```sql
WITH daily AS (
    SELECT
        created_on,
        COUNT(*) AS total_rows,
        COUNT(*) FILTER (
            WHERE NULLIF(BTRIM(email), '') IS NULL
        ) AS missing_rows
    FROM customers_stage
    GROUP BY created_on
),
rates AS (
    SELECT
        created_on,
        1.0 * missing_rows / NULLIF(total_rows, 0) AS missing_rate
    FROM daily
)
SELECT
    created_on,
    missing_rate,
    LAG(missing_rate) OVER (
        ORDER BY created_on
    ) AS previous_rate
FROM rates
ORDER BY created_on;
```

`LAG` trả tỷ lệ của **kỳ có bản ghi trước đó** trong kết quả. Nếu ngày 04/03 không có hàng trong bảng tổng hợp, `LAG` của 05/03 so với ngày xuất hiện trước, không nhất thiết là **ngày lịch liền kề**. Muốn so theo từng ngày, có thể cần **calendar table** và lựa chọn cách biểu diễn ngày không có dữ liệu.

## 14. Những điểm kỹ thuật dễ làm sai kết quả kiểm tra

### 14.1. NULL khác với giá trị 0 và chuỗi 'NULL'

| Giá trị | Ý nghĩa kỹ thuật |
|---|---|
| SQL `NULL` | Không có giá trị xác định |
| Số `0` | Một giá trị số có thật |
| Chuỗi `''` | Chuỗi rỗng (trên PostgreSQL) |
| Chuỗi `'NULL'` | Bốn ký tự văn bản N-U-L-L |
| Chuỗi `'   '` | Chuỗi gồm khoảng trắng |

Không tự thay `NULL` bằng 0 trong mọi phép kiểm tra. Ví dụ đơn `O005` chưa biết `amount` và đơn `O010` có `amount = 0` cần được phân loại khác nhau.

### 14.2. COUNT(*) khác COUNT(cột)

`COUNT(*)` đếm **mọi hàng**, gồm những hàng mà cột quan tâm là `NULL`. `COUNT(email)` chỉ đếm các hàng có `email` **không `NULL`** nhưng vẫn đếm chuỗi rỗng và khoảng trắng.

```sql
SELECT
    COUNT(*) AS rows_total,
    COUNT(email) AS non_null_emails,
    COUNT(*) FILTER (
        WHERE NULLIF(BTRIM(email), '') IS NOT NULL
    ) AS usable_emails
FROM customers_stage;
```

Với dữ liệu mẫu: **10** hàng tổng, **9** email khác `NULL`, nhưng chỉ **8** email không rỗng sau `BTRIM`. Đếm email dùng được không đồng nghĩa email có cấu trúc hợp lệ; muốn kiểm tra định dạng cần quy tắc khác.

### 14.3. JOIN có thể làm nhân hàng khi nguồn có khóa trùng

Nếu `orders_stage` có một đơn của `C002` nhưng `customers_stage` có **hai** hàng `C002`, phép:

```sql
SELECT o.raw_id, o.order_ref, c.customer_row_id
FROM orders_stage AS o
JOIN customers_stage AS c
    ON c.customer_code = o.customer_code
WHERE o.order_ref = 'O002'
ORDER BY c.customer_row_id;
```

trả **hai hàng** cho cùng đơn `O002`, do bảng khách có hai bản ghi mã C002. Nếu dùng `COUNT(*)` hoặc `SUM(o.amount)` trên kết quả nối đó, có nguy cơ **đếm/cộng trùng**.

Khi chỉ cần hỏi “khách có tồn tại không?”, `EXISTS`/`NOT EXISTS` tránh làm nhân số hàng ngoài. Khi cần thông tin khách, phải có quy tắc **chọn bản ghi khách chuẩn** hoặc sửa dữ liệu trùng ở nguồn đáng tin cậy trước khi nối.

### 14.4. COUNT(DISTINCT ...) không phải thuốc chữa mọi lỗi JOIN

`COUNT(DISTINCT order_ref)` có thể đếm số mã đơn phân biệt, nhưng:

- Không cho biết **hàng nào** bị nhân và nguyên nhân.
- Có thể bỏ qua `NULL` trong các giá trị được đếm.
- Không sửa sai khi `SUM(amount)` đã cộng lặp.
- Có thể gộp nhầm các sự kiện thật sự khác nhau nếu khóa nghiệp vụ chọn sai.

Để đối soát tiền, thường cần **chuẩn hóa đúng mức chi tiết** ở từng nhánh trước khi nối, như mục 10.

### 14.5. Không dùng NOT IN tùy tiện khi truy vấn con chứa NULL

Giả sử:

```sql
WHERE o.customer_code NOT IN (
    SELECT c.customer_code
    FROM customers_stage AS c
)
```

Truy vấn con có hàng khách 9 với `customer_code = NULL`. Khi tập `NOT IN` chứa `NULL`, phép so sánh phủ định có thể cho `UNKNOWN` và làm bỏ sót những đơn có mã khách **thực sự không tìm thấy**, như `C404`.

Với bài toán **không có bản ghi liên quan**, ưu tiên:

```sql
WHERE o.customer_code IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM customers_stage AS c
      WHERE c.customer_code = o.customer_code
  )
```

Đoạn này cũng diễn đạt rõ rằng **khóa ngoài bị thiếu** được xử lý bằng một phép kiểm tra khác.

### 14.6. Làm sạch dữ liệu trước khi kiểm tra có thể che mất lỗi

Nếu ngay khi nhập dữ liệu đã tự:

- Thay mọi email thiếu bằng chuỗi `'unknown@example.com'`.
- Chuyển mọi số tiền âm thành giá trị tuyệt đối.
- Dùng `DISTINCT` loại bản sao.
- Thay mọi trạng thái lạ bằng `NEW`.

thì báo cáo kiểm tra có thể **không còn thấy lỗi gốc**. Một quy trình tốt thường lưu dữ liệu nguồn hoặc nhật ký biến đổi và cho biết **quy tắc nào đã chỉnh sửa gì**. Chuẩn hóa phục vụ so khớp nên được ghi nhận, không lặng lẽ làm mất thông tin.

## 15. Thiết kế kiểm tra chất lượng khi đưa vào quy trình thật

Một bộ mẫu SQL hữu ích chỉ là bước đầu. Để kiểm tra có thể vận hành lặp lại, cần thiết kế thêm **phạm vi dữ liệu, ngưỡng cảnh báo, lịch chạy và cách xử lý kết quả**.

### 15.1. Chọn đúng tập dữ liệu cần kiểm tra

Các câu `SELECT` trong bài chạy trên **toàn bộ bảng staging**. Trong hệ thống thật, dữ liệu có thể được nạp theo batch. Nên biết:

- Kiểm tra **lô mới nhất** hay toàn bộ lịch sử?
- Dữ liệu có thể đến trễ bao nhiêu?
- Nguồn đã hoàn thành nạp hay chưa?
- Có nhiều phiên bản của cùng khóa nghiệp vụ không?
- Các bảng cần đối soát đã được chốt ở **cùng một thời điểm** chưa?

Nếu thanh toán về sau đơn hàng một giờ, chạy đối soát tức thì có thể báo “thiếu thanh toán” giả. Có thể cần một **watermark** hoặc khoảng chờ theo quy trình đồng bộ.

### 15.2. Phân loại mức nghiêm trọng

Một gợi ý:

| Mức | Ví dụ | Hành động thường phù hợp |
|---|---|---|
| **Error** | Mã đơn bắt buộc thiếu; khóa nghiệp vụ trùng trái ràng buộc | Cách ly hoặc chặn bản ghi khỏi bước nhập chính |
| **Warning** | Đơn trị giá rất lớn; email có thể trùng người dùng khác | Đưa vào hàng chờ xác minh |
| **Info** | Ngày không có giao dịch, nhưng không có lịch bắt buộc | Theo dõi hoặc chỉ hiển thị |

Mức thực tế do **chủ dữ liệu và yêu cầu nghiệp vụ** quyết định. Một cảnh báo chỉ nên chặn pipeline khi hậu quả của việc đi tiếp được đánh giá rõ.

### 15.3. Chỉ số nên theo dõi

Các chỉ số phổ biến:

- **Completeness**: tỷ lệ trường bắt buộc có giá trị sử dụng được.
- **Uniqueness**: số khóa nghiệp vụ trùng, số hàng trong nhóm trùng.
- **Validity**: tỷ lệ giá trị thuộc miền/định dạng hợp lệ.
- **Referential integrity**: số mã tham chiếu không tìm thấy đối tác.
- **Consistency**: chênh lệch giữa các nguồn, ví dụ tiền đơn và tiền thanh toán.
- **Timeliness**: độ trễ dữ liệu so với kỳ vọng.

Nên lưu cả **mẫu số** và **số lượng lỗi**. Một ngày có 10 lỗi trên 100 bản ghi và một ngày có 10 lỗi trên 1 triệu bản ghi có ý nghĩa khác nhau.

### 15.4. Tách phát hiện, xác minh và sửa dữ liệu

Quy trình gợi ý:

```text
Nguồn dữ liệu thô
      |
      v
Truy vấn kiểm tra (SELECT)
      |
      v
Danh sách lỗi + số lượng + batch/source
      |
      v
Phân loại: lỗi chắc chắn / nghi ngờ / hợp lệ có ngoại lệ
      |
      v
Xác minh với quy tắc và nguồn gốc
      |
      v
Sửa dữ liệu qua quy trình kiểm soát, hoặc chấp nhận ngoại lệ
      |
      v
Chạy lại kiểm tra + lưu kết quả
```

Không tự thêm `DELETE` hoặc `UPDATE` vào các câu kiểm tra chỉ vì chúng đã tìm được hàng sai. Việc sửa cần bảo đảm khóa, giao dịch, ảnh hưởng bảng liên quan, quyền thao tác và khả năng truy vết.

### 15.5. Các ràng buộc database vẫn rất quan trọng

Truy vấn kiểm tra giúp phát hiện lỗi đã có hoặc lỗi từ nguồn nhập. Nhưng với bảng nghiệp vụ đã kiểm soát, nhiều lỗi nên bị ngăn ngay từ đầu:

```sql
-- Minh họa ý tưởng thiết kế bảng chuẩn; không áp vào bảng staging ở bài.
CREATE TABLE clean_orders_example (
    order_id BIGINT PRIMARY KEY,
    order_ref TEXT NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    status TEXT NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED'))
);
```

Một hệ thống có bảng khách chuẩn còn có thể dùng `FOREIGN KEY (customer_id) REFERENCES customers(id)`. Ràng buộc `UNIQUE`, `NOT NULL`, `CHECK` và `FOREIGN KEY` thường bảo vệ dữ liệu tốt hơn việc chỉ chạy báo cáo lỗi sau khi đã ghi. Nhưng một số quy tắc như **khớp tổng tiền thanh toán**, **giới hạn theo nghiệp vụ nhiều bảng**, hoặc **mức bất thường thống kê** cần thêm cơ chế kiểm tra.

## 16. Hiệu năng và cách viết truy vấn kiểm tra trên bảng lớn

Với bộ dữ liệu ví dụ vài chục hàng, mọi câu SQL đều nhỏ. Nhưng trong kho dữ liệu nhiều triệu bản ghi, chi phí có thể cao.

### 16.1. Chỉ mục cho tìm trùng và tìm thiếu quan hệ

Các phép kiểm tra trùng và đối chiếu khóa thường truy cập `order_ref` hoặc `customer_code`:

```sql
CREATE INDEX idx_orders_stage_order_ref
ON orders_stage (order_ref);

CREATE INDEX idx_orders_stage_customer_code
ON orders_stage (customer_code);

CREATE INDEX idx_customers_stage_customer_code
ON customers_stage (customer_code);

CREATE INDEX idx_payments_stage_order_ref
ON payments_stage (order_ref);
```

Những chỉ mục này có thể hỗ trợ `GROUP BY`, `JOIN` hoặc `NOT EXISTS` tùy kế hoạch. Chúng cũng làm tăng chi phí ghi và lưu trữ. Trong hệ thống staging chủ yếu được nạp hàng loạt rồi đọc quét toàn bảng, tạo nhiều chỉ mục không phải lúc nào cũng tối ưu.

Đối với chuẩn hóa email:

```sql
-- PostgreSQL: chỉ mục biểu thức nếu truy vấn này thường xuyên được dùng.
CREATE INDEX idx_customers_stage_normalized_email
ON customers_stage ((LOWER(BTRIM(email))));
```

Chỉ tạo chỉ mục biểu thức sau khi quy tắc chuẩn hóa đã được xác nhận và dữ liệu/truy vấn thực sự cần nó. Nếu hệ thống dùng `NULLIF(...)`, collation hoặc biểu thức khác, bộ tối ưu có thể cần biểu thức chỉ mục tương ứng.

### 16.2. Quét toàn bộ vẫn cần thiết cho kiểm tra toàn bộ

Một truy vấn tìm **mọi giá trị âm hoặc mọi bản ghi trùng** trong cả bảng có thể cần đọc phần lớn dữ liệu. Không nên kỳ vọng có chỉ mục sẽ làm mọi bài toán chất lượng dữ liệu trở thành truy vấn thời gian hằng số.

Nếu nguồn nạp theo batch, có thể kiểm tra **lô hiện tại** cho các quy tắc nội bộ lô, nhưng vẫn phải cân nhắc **trùng xuyên lô**. Ví dụ cùng `order_ref` xuất hiện ở lô hôm qua và hôm nay sẽ không bị phát hiện nếu chỉ `GROUP BY` trong lô mới. Có thể cần bảng khóa canonical hoặc cơ chế duy nhất ở toàn hệ thống.

### 16.3. Dùng EXPLAIN có mục đích

PostgreSQL có:

```sql
EXPLAIN
SELECT order_ref, COUNT(*)
FROM orders_stage
WHERE order_ref IS NOT NULL
GROUP BY order_ref
HAVING COUNT(*) > 1;
```

`EXPLAIN` giúp quan sát kế hoạch dự kiến. `EXPLAIN ANALYZE` đo thực thi thật và cần dùng thận trọng với lệnh thay đổi dữ liệu. Với báo cáo chất lượng, các phép tổng hợp, sắp xếp, kiểm tra tồn tại và số lượng bản ghi đầu vào thường là yếu tố đáng quan tâm.

## 17. Khác biệt phương ngữ giữa PostgreSQL, MySQL, SQL Server, SQLite và Oracle

Ý tưởng phát hiện lỗi chủ yếu dựa trên SQL cơ bản, nhưng có các khác biệt cú pháp:

| Nhu cầu | PostgreSQL | MySQL | SQL Server | SQLite | Oracle |
|---|---|---|---|---|---|
| Kiểm tra `NULL` | `IS NULL` | `IS NULL` | `IS NULL` | `IS NULL` | `IS NULL` |
| Bỏ khoảng trắng | `BTRIM` hoặc `TRIM` | `TRIM` | `TRIM` trên phiên bản phù hợp | `TRIM` | `TRIM` |
| Đếm có điều kiện | `COUNT(*) FILTER (WHERE ...)` hoặc `SUM(CASE ...)` | `SUM(CASE ...)` | `SUM(CASE ...)` | `FILTER` trên phiên bản hỗ trợ hoặc `SUM(CASE ...)` | `SUM(CASE ...)` |
| Đánh số bản sao | `ROW_NUMBER() OVER(...)` | MySQL 8.0+ | SQL Server hỗ trợ | SQLite 3.25.0+ | Hỗ trợ hàm phân tích |
| Ngày kỳ vọng | `generate_series` | CTE đệ quy hoặc calendar table | CTE/tally/calendar table | CTE đệ quy hoặc calendar table | Calendar table hoặc cách tạo dãy phù hợp |
| Tứ phân vị | `PERCENTILE_CONT` | Tùy phiên bản/tính năng; có thể tự tính theo thứ hạng | `PERCENTILE_CONT` dạng cửa sổ | Không có hàm tương đương mặc định trong mọi bản | `PERCENTILE_CONT` theo cú pháp Oracle |
| So sánh NULL-safe | `IS NOT DISTINCT FROM` | `<=>` | Phụ thuộc phiên bản; có thể dùng biểu thức tương đương | `IS` hoặc `IS NOT DISTINCT FROM` theo phiên bản | Có cú pháp/biểu thức tương đương tùy phiên bản |

### 17.1. Những khác biệt cần chú ý

- **Chuỗi rỗng**: PostgreSQL phân biệt `''` với `NULL`. Oracle coi chuỗi ký tự rỗng là `NULL` trong nhiều ngữ cảnh ký tự. Vì vậy kiểm tra “rỗng sau trim” có thể có hành vi khác, dù ý định nghiệp vụ không đổi.
- **So sánh chữ hoa/chữ thường**: collation có thể khiến `'An'` và `'AN'` được xem là bằng nhau trong một DBMS hoặc cột nhưng khác nhau trong DBMS khác. Khi kiểm tra trùng, phải chọn quy tắc chuẩn hóa/collation tường minh.
- **Ngày giờ**: các hệ có kiểu `DATE`, `DATETIME`, `TIMESTAMP` và quy tắc múi giờ khác. Đừng dùng so sánh chuỗi thời gian thiếu chuẩn hóa rồi tin đó là so sánh thời điểm chính xác.
- **Tỷ lệ phần trăm**: phép chia số nguyên có thể gây mất phần thập phân tùy DBMS. Sử dụng số thập phân như `100.0` hoặc `CAST` thích hợp, và `NULLIF(denominator, 0)` để tránh chia cho 0.
- **Cú pháp gom danh sách ID**: PostgreSQL dùng `ARRAY_AGG`; DBMS khác có thể dùng `STRING_AGG`, `GROUP_CONCAT`, `LISTAGG` hoặc chỉ giữ bảng chi tiết và nối ở ứng dụng.
- **CTE và window functions**: nếu phiên bản rất cũ chưa hỗ trợ, có thể dùng derived table hoặc bảng trung gian, nhưng không giả định các lựa chọn đều có hiệu năng tương đương.

Khi triển khai trên một hệ cụ thể, dùng **tài liệu của đúng DBMS và phiên bản** để chọn cú pháp phù hợp. Đừng sao chép nguyên lệnh PostgreSQL có `FILTER`, `ARRAY_AGG`, `BTRIM` hay `generate_series` vào hệ khác mà chưa chuyển đổi.

## 18. Những lỗi thường gặp

### Lỗi 1 — Dùng = NULL để tìm giá trị thiếu

`email = NULL` không cho `TRUE`. Dùng `email IS NULL`. Nếu muốn phát hiện chuỗi chỉ có khoảng trắng, cần thêm bước `TRIM/BTRIM` và `NULLIF`.

### Lỗi 2 — Chỉ kiểm tra NULL mà bỏ chuỗi rỗng

`'   '` vẫn là một chuỗi trong PostgreSQL. Hàng email toàn khoảng trắng sẽ lọt qua `IS NULL`; cần quy tắc chuẩn hóa.

### Lỗi 3 — Gom tất cả NULL thành một bản ghi trùng

`GROUP BY order_ref` gom các hàng có `order_ref = NULL` vào cùng nhóm. Nhiều đơn thiếu mã không có nghĩa chắc chắn là **cùng một đơn**. Tách quy tắc **thiếu khóa** và **trùng khóa có giá trị**.

### Lỗi 4 — Dùng SELECT DISTINCT để “xử lý trùng” mà không biết khóa

`DISTINCT` chỉ loại trùng trên danh sách cột được chọn. Nó không chọn được bản ghi chuẩn khi các phiên bản cùng khóa có giá trị khác nhau, và có thể che bằng chứng bản sao trong staging.

### Lỗi 5 — Lấy bất kỳ một bản ghi trong nhóm trùng

`ROW_NUMBER` chỉ xác định bản ghi đại diện ổn định khi `ORDER BY` đủ phân định. Ngay cả khi ổn định, quy tắc “nạp gần nhất” vẫn cần được xác nhận có đúng nghiệp vụ hay không.

### Lỗi 6 — Dùng NOT IN với tập chứa NULL để tìm quan hệ thiếu

Một `NULL` trong tập con có thể khiến kết quả `NOT IN` thành `UNKNOWN`. Với quan hệ khóa, `NOT EXISTS` tương quan thường diễn đạt rõ và dễ tránh bẫy này hơn.

### Lỗi 7 — Kiểm tra cột bên phải được phép NULL để kết luận JOIN không khớp

`LEFT JOIN ... WHERE c.email IS NULL` có thể chọn cả khách thật nhưng thiếu email. Dùng khóa không `NULL` ở phía nối, ví dụ `c.customer_row_id IS NULL`, để nhận diện không có hàng khớp.

### Lỗi 8 — Cộng tiền sau khi JOIN dữ liệu trùng

Bảng khách C002 bị trùng, đơn O003 cũng bị trùng. Nối không kiểm soát có thể làm nhân số hàng và tổng tiền. Hãy đưa từng nguồn về **grain đã xác định** trước khi đối soát.

### Lỗi 9 — Coi số tiền cực đoan chắc chắn là sai

`amount = 5000` vượt xa đa số giá trị, nhưng có thể hợp lệ. Cần gắn cảnh báo, xác minh ngữ cảnh và ngưỡng nghiệp vụ thay vì tự sửa.

### Lỗi 10 — Dùng COALESCE thay mọi giá trị thiếu bằng 0

`COALESCE(amount, 0)` có thể biến “không biết tiền” thành “tiền bằng 0”. Trên O005, điều đó che mất lỗi thiếu số tiền đơn. Chỉ dùng `COALESCE` khi **0 là giá trị thay thế được nghiệp vụ chấp nhận**, ví dụ diễn giải “không có khoản CAPTURED nào” là 0 cho một phép đối soát cụ thể.

### Lỗi 11 — Coi không có dữ liệu ngày nào đó là pipeline lỗi

Trước khi báo thiếu ngày, phải có **lịch kỳ vọng** và biết kỳ dữ liệu đã chốt. Một ngày không có đơn có thể hoàn toàn bình thường nếu số đơn thấp.

### Lỗi 12 — Tin rằng kết quả kiểm tra trên snapshot cũ luôn đúng ở thời điểm sửa

Giữa lúc kiểm tra và lúc sửa, dữ liệu có thể thay đổi. Với thao tác ghi thật, cần giao dịch, khóa hoặc kiểm tra lại điều kiện khi cập nhật.

### Lỗi 13 — Chỉ kiểm tra một chiều quan hệ

Kiểm tra “đơn nào thiếu thanh toán” không phát hiện thanh toán `O999` thiếu đơn. Cần đối chiếu hai chiều khi câu hỏi nghiệp vụ yêu cầu dữ liệu khớp đủ ở cả hai nguồn.

### Lỗi 14 — Không lưu danh tính bản ghi vi phạm

Một báo cáo chỉ có `COUNT(*) = 5` cho biết có năm lỗi nhưng không giúp xử lý. Hãy trả thêm khóa kỹ thuật, khóa nghiệp vụ, mã quy tắc và thông tin nguồn/batch để có thể truy vết.

## 19. Bài tập thực hành có đáp án

Hãy sử dụng đúng dữ liệu ở mục 2. Dự đoán kết quả trước khi chạy từng truy vấn. Các đáp án dưới đây dựa trên **trạng thái bảng ban đầu**, chưa chỉnh sửa bất kỳ hàng nào.

### Bài 1 — Email thiếu

Viết truy vấn tìm khách có `email` là `NULL` hoặc chỉ gồm khoảng trắng.

```sql
SELECT customer_row_id, email
FROM customers_stage
WHERE NULLIF(BTRIM(email), '') IS NULL
ORDER BY customer_row_id;
```

**Đáp án:** **4 và 7**. Chỉ dùng `email IS NULL` sẽ bỏ sót 7.

### Bài 2 — Thiếu mã khách và thiếu tên

Viết hai phép kiểm tra riêng cho `customer_code` và `full_name`.

**Đáp án:** mã khách thiếu ở **customer_row_id 9**; tên thiếu sau `BTRIM` ở **customer_row_id 10**.

### Bài 3 — Mã khách trùng

```sql
SELECT customer_code, COUNT(*) AS copies
FROM customers_stage
WHERE customer_code IS NOT NULL
GROUP BY customer_code
HAVING COUNT(*) > 1;
```

**Đáp án:** `C002` có **2 hàng**: customer_row_id **2 và 8**.

### Bài 4 — Email trùng sau chuẩn hóa

Tính `NULLIF(LOWER(BTRIM(email)), '')`, loại `NULL` rồi `GROUP BY`.

**Đáp án:** email chuẩn hóa `an@example.com` trùng ở hai hàng **1 và 6**. Vì sao không xóa ngay một khách chỉ từ kết quả này?

### Bài 5 — Mã đơn bị nhập trùng

```sql
SELECT order_ref, COUNT(*) AS copies
FROM orders_stage
WHERE order_ref IS NOT NULL
GROUP BY order_ref
HAVING COUNT(*) > 1;
```

**Đáp án:** `O003` có **2 hàng nguồn**, raw_id **103 và 104**.

### Bài 6 — Chọn phiên bản mới nhất của đơn trùng

Sử dụng `ROW_NUMBER() OVER (PARTITION BY order_ref ORDER BY loaded_at DESC, raw_id DESC)` để chọn một hàng đại diện cho mỗi `order_ref` không `NULL`.

**Đáp án:** chọn **raw_id 104** cho `O003`; tập đại diện có **12 hàng** tương ứng mã `O001–O012`. Hàng thiếu mã đơn 112 phải xử lý riêng.

### Bài 7 — Đơn có mã khách không tồn tại

Viết `NOT EXISTS` từ `orders_stage` sang `customers_stage` và chỉ xét `customer_code` không `NULL`.

**Đáp án:** **O004**, raw_id **105**, mã khách **C404**. Mã `C002` có hai hàng khách nhưng không phải mã không tồn tại.

### Bài 8 — Thanh toán không có đơn

Viết `NOT EXISTS` từ `payments_stage` sang `orders_stage`.

**Đáp án:** **payment_id 209**, mã đơn **O999**.

### Bài 9 — Tiền âm và tiền thiếu

Viết một truy vấn tìm `amount < 0`, một truy vấn tìm `amount IS NULL`.

**Đáp án:** tiền âm ở **O006** (raw_id 107, -20); tiền thiếu ở **O005** (raw_id 106).

### Bài 10 — Đơn PAID không có tiền dương

```sql
SELECT raw_id, order_ref, amount
FROM orders_stage
WHERE status = 'PAID'
  AND (amount IS NULL OR amount <= 0)
ORDER BY raw_id;
```

**Đáp án:** **O005** có `NULL` và **O010** có 0. Giải thích vì sao `NOT (amount > 0)` không tìm đủ cả hai.

### Bài 11 — Trạng thái không hợp lệ

```sql
SELECT raw_id, order_ref, status
FROM orders_stage
WHERE status IS NULL
   OR status NOT IN ('NEW', 'PAID', 'CANCELLED');
```

**Đáp án:** **O012**, trạng thái `UNKNOWN`.

### Bài 12 — Ngày đặt tương lai so với mốc chốt

Giả sử `as_of_date = DATE '2025-03-15'`. Tìm đơn có `ordered_on > as_of_date`.

**Đáp án:** **O011** (2025-04-05). Đây chỉ là lỗi nếu `ordered_on` bắt buộc biểu thị ngày giao dịch đã xảy ra; nếu đó là đơn đặt trước, cần quy tắc khác.

### Bài 13 — Đối soát tiền PAID với tiền CAPTURED

Chọn một hàng đơn đại diện cho mỗi `order_ref`, tổng hợp `payments_stage` chỉ với `payment_status = 'CAPTURED'`, rồi tìm đơn `PAID` có tiền xác định nhưng không khớp tổng.

**Đáp án:** **O008** có tiền đơn 5.000, đã ghi nhận 1.000, chênh **4.000**. Vì sao O005 và O010 cần những kiểm tra nghiệp vụ riêng ngoài phép đối soát bằng số?

### Bài 14 — Ngày không có bản ghi đơn

Giả sử mỗi ngày từ **01/03 đến 15/03/2025** phải có ít nhất một đơn. Dùng `generate_series` và `LEFT JOIN` tập ngày có đơn.

**Đáp án:** thiếu **13/03, 14/03, 15/03/2025** theo lịch kỳ vọng giả định. Nếu không có quy tắc phải có đơn mỗi ngày, không thể kết luận ba ngày này là dữ liệu lỗi.

### Bài 15 — Tại sao JOIN làm nhân đơn?

Chạy:

```sql
SELECT o.order_ref, c.customer_row_id
FROM orders_stage AS o
JOIN customers_stage AS c
    ON c.customer_code = o.customer_code
WHERE o.order_ref = 'O002'
ORDER BY c.customer_row_id;
```

**Đáp án:** có hai hàng cho `O002` vì `C002` tương ứng **hai khách nguồn** 2 và 8. Dùng `EXISTS` nếu chỉ cần kiểm tra có khách; nếu cần tên khách, phải xử lý bản ghi khách trùng bằng quy tắc xác định.

### Bài 16 — Phân biệt thiếu khóa và khóa tham chiếu sai

Viết hai truy vấn:

1. Đơn **không có customer_code**.
2. Đơn **có customer_code nhưng mã khách đó không tồn tại**.

**Đáp án:** nhóm 1 có **O007** (raw_id 108); nhóm 2 có **O004** (raw_id 105, C404). Không gộp hai vấn đề vào một thông báo mơ hồ “missing customer” nếu cần cách sửa khác nhau.

### Bài 17 — Đếm bản ghi ảnh hưởng theo từng quy tắc

Tạo CTE `issues` bằng `UNION ALL` gồm ba quy tắc `CUS_EMAIL_REQUIRED`, `ORD_REF_REQUIRED`, `ORD_AMOUNT_NONNEGATIVE` ở mục 12.

**Đáp án:** tổng **4 dòng cảnh báo**: email thiếu ở khách 4, 7; mã đơn thiếu ở raw_id 112; số tiền âm ở raw_id 107. Muốn lưu kết quả vào bảng chất lượng thật, nên bổ sung thời điểm, batch và định danh nguồn.

### Bài 18 — Tại sao NOT IN có thể bỏ sót C404?

Trong bảng khách có một hàng `customer_code = NULL`. Xét:

```sql
SELECT o.order_ref
FROM orders_stage AS o
WHERE o.customer_code NOT IN (
    SELECT c.customer_code
    FROM customers_stage AS c
);
```

**Đáp án:** tập con chứa `NULL` nên `NOT IN` có thể cho `UNKNOWN` đối với mã không trùng `C404`; `WHERE` loại hàng đó. Dùng `NOT EXISTS` tương quan và kiểm tra `o.customer_code IS NOT NULL` để diễn đạt “mã đã có giá trị nhưng không tồn tại trong bảng khách”.

## 20. Bảng ghi nhớ nhanh

| Dấu hiệu cần tìm | Mẫu SQL thường dùng | Điều cần tránh |
|---|---|---|
| Cột bắt buộc `NULL` | `col IS NULL` | `col = NULL` |
| Chuỗi rỗng hoặc chỉ có khoảng trắng | `NULLIF(TRIM(col), '') IS NULL` | Chỉ dùng `IS NULL` |
| Tỷ lệ thiếu | `COUNT(*) FILTER (...)` hoặc `SUM(CASE...)` | Chia cho 0; không rõ mẫu số |
| Khóa tham chiếu không tồn tại | `NOT EXISTS` tương quan | `NOT IN` có `NULL`; nhầm khóa thiếu |
| Khóa nghiệp vụ bị trùng | `GROUP BY key HAVING COUNT(*) > 1` | Gom các khóa `NULL` thành bản ghi trùng |
| Xem từng hàng thuộc nhóm trùng | `COUNT(*) OVER (PARTITION BY key)` | Lọc hàm cửa sổ trong `WHERE` cùng cấp |
| Trùng sau chuẩn hóa | `GROUP BY LOWER(TRIM(value))` | Chuẩn hóa quá mạnh, gộp nhầm |
| Chọn một bản ghi đại diện | `ROW_NUMBER() OVER (PARTITION BY key ORDER BY priority, unique_id)` | Chọn ngẫu nhiên; xóa nguồn ngay |
| Giá trị ngoài miền | `col < min OR col > max` và `IS NULL` khi cần | Nghĩ `NULL` tự thỏa điều kiện |
| Trạng thái ngoài tập | `status NOT IN (...) OR status IS NULL` | Tập `NOT IN` có `NULL` |
| Giá trị cực đoan | Ngưỡng nghiệp vụ, IQR/percentile | Coi outlier chắc chắn là sai |
| Chênh lệch giữa hai nguồn | Chuẩn hóa grain rồi `JOIN`/`SUM` | Nối nhiều-một/nhiều-nhiều làm nhân giá trị |
| Thiếu ngày hoặc sự kiện kỳ vọng | Calendar/reference table + `LEFT JOIN`/`NOT EXISTS` | Tự coi mọi ngày rỗng là lỗi |
| Theo dõi xu hướng lỗi | `GROUP BY` kỳ + `LAG` | So kỳ không liền nhau, mẫu quá nhỏ |
| Hợp nhất báo cáo lỗi | `UNION ALL` với `rule_code` và source ID | Chỉ báo tổng số mà không có bản ghi để tra |

## Kết luận

Để **phát hiện dữ liệu thiếu, trùng và bất thường bằng SQL**, điều quan trọng nhất không phải thuộc thật nhiều cú pháp, mà là **biến quy tắc chất lượng thành điều kiện kiểm tra có thể giải thích**:

- Với **dữ liệu thiếu**, dùng `IS NULL`, `TRIM`/`BTRIM`, `NULLIF`, `NOT EXISTS` và đối chiếu với bảng/lịch kỳ vọng.
- Với **dữ liệu trùng**, dùng `GROUP BY ... HAVING COUNT(*) > 1`, hàm cửa sổ `COUNT(*) OVER (...)` và chuẩn hóa giá trị có kiểm soát; nếu chọn bản ghi đại diện, `ROW_NUMBER` phải có tiêu chí ưu tiên xác định.
- Với **dữ liệu bất thường**, dùng điều kiện miền hợp lệ, quy tắc nghiệp vụ, kiểm tra ngày, ngưỡng thống kê và đối soát giữa các bảng sau khi thống nhất **mức chi tiết của dữ liệu**.
- Với **báo cáo vận hành**, nên trả về mã quy tắc, khóa bản ghi nguồn, mức độ và số lượng ảnh hưởng; giữ dấu vết để xác minh và sửa đúng nguồn.

Một bản ghi có thể **khớp một phép kiểm tra nhưng vẫn sai ở phép khác**: đơn O004 khớp tiền thanh toán nhưng có mã khách không tồn tại; đơn O010 có tổng tiền khớp 0 nhưng vi phạm quy tắc `PAID` phải có tiền dương; đơn O008 có tiền cực đoan và đồng thời bị thiếu tiền thanh toán. Vì vậy, các mẫu SQL nên được xây dựng thành **bộ quy tắc bổ sung cho nhau**, thay vì một câu truy vấn duy nhất quyết định mọi hàng “đúng hay sai”.

Hãy dùng truy vấn để **phát hiện**, dùng hiểu biết nghiệp vụ để **xác minh**, và dùng giao dịch cùng cơ chế quản trị dữ liệu để **sửa chữa an toàn**. Đó là nền tảng của việc bảo đảm chất lượng dữ liệu đáng tin cậy trong hệ thống SQL.
