# CASE, COALESCE và NULLIF trong truy vấn PostgreSQL

Khi viết truy vấn thực tế, dữ liệu không phải lúc nào cũng đầy đủ, và một cột không phải lúc nào cũng có giá trị phù hợp để hiển thị trực tiếp. Một đơn hàng có thể chưa được thanh toán, một khách hàng có thể không cung cấp số điện thoại, hoặc một phép tính trung bình có thể gặp mẫu số bằng 0. Ta cũng thường phải biến mã trạng thái thành nhãn dễ đọc, xếp khách hàng vào nhóm, hoặc tính tổng tiền theo từng điều kiện.

Trong PostgreSQL, ba biểu thức rất quan trọng để xử lý những tình huống này là:

- **`CASE`:** lựa chọn kết quả theo một hoặc nhiều điều kiện, tương tự cấu trúc rẽ nhánh trong ngôn ngữ lập trình.
- **`COALESCE`:** lấy **giá trị đầu tiên khác `NULL`** trong một danh sách biểu thức.
- **`NULLIF`:** trả về `NULL` nếu hai biểu thức bằng nhau, ngược lại trả về biểu thức thứ nhất.

Chúng đều là **biểu thức SQL**, không phải câu lệnh độc lập chỉ dùng trong `SELECT`. Ta có thể kết hợp chúng trong `WHERE`, `ORDER BY`, `GROUP BY`, `HAVING`, `UPDATE`, phép tổng hợp và nhiều ngữ cảnh khác.

Bài học đi từ cú pháp và cơ chế `NULL` đến các ví dụ có dữ liệu chạy được, ứng dụng trong báo cáo bán hàng, xử lý chia cho 0, lựa chọn kiểu dữ liệu, khác biệt giữa `CASE` đơn giản và `CASE` theo điều kiện, hiệu năng và các lỗi thiết kế phổ biến.

## 1. Ôn lại NULL và logic ba giá trị trong PostgreSQL

Trước khi dùng `CASE`, `COALESCE` hoặc `NULLIF`, cần hiểu rằng **`NULL` không phải số 0, không phải chuỗi rỗng và cũng không phải boolean `FALSE`**. `NULL` biểu thị giá trị không có mặt hoặc chưa được biết theo ngữ nghĩa của cột.

Ví dụ:

~~~sql
SELECT
    NULL::integer AS unknown_number,
    0 AS known_zero,
    ''::text AS empty_text,
    FALSE AS known_false;
~~~

Các giá trị này có ý nghĩa khác nhau:

| Giá trị | Ý nghĩa thông thường | Có phải `NULL`? |
| --- | --- | --- |
| `NULL` | Chưa biết, thiếu, hoặc không áp dụng | Có |
| `0` | Số đã biết bằng không | Không |
| `''` | Chuỗi độ dài bằng không | Không |
| `'   '` | Chuỗi gồm các dấu cách | Không |
| `FALSE` | Giá trị logic sai | Không |

### 1.1. Tại sao không dùng = NULL?

Trong SQL, so sánh thông thường với `NULL` không trả `TRUE` hoặc `FALSE` mà thường trả **`UNKNOWN`**:

~~~sql
SELECT
    (NULL::integer = NULL::integer) AS null_equals_null,
    (10 = NULL::integer) AS ten_equals_null,
    (10 <> NULL::integer) AS ten_differs_from_null;
~~~

Ba biểu thức đều trả `NULL` (đại diện kết quả logic UNKNOWN). Do đó:

~~~sql
-- Sai mục đích: không tìm được dòng NULL như mong muốn.
SELECT *
FROM some_table
WHERE some_column = NULL;
~~~

Trong truy vấn thực tế, hãy dùng:

~~~sql
WHERE some_column IS NULL
~~~

hoặc:

~~~sql
WHERE some_column IS NOT NULL
~~~

`WHERE` chỉ giữ các hàng mà điều kiện là **TRUE**; cả `FALSE` và `UNKNOWN` đều không được chọn.

### 1.2. AND, OR, NOT và UNKNOWN

Với logic ba giá trị:

| Biểu thức | Kết quả |
| --- | --- |
| `TRUE AND NULL` | UNKNOWN (`NULL`) |
| `FALSE AND NULL` | FALSE |
| `TRUE OR NULL` | TRUE |
| `FALSE OR NULL` | UNKNOWN (`NULL`) |
| `NOT NULL::boolean` | UNKNOWN (`NULL`) |

Điều này liên quan trực tiếp tới **`CASE WHEN`**: nhánh `WHEN` được chọn chỉ khi biểu thức điều kiện là `TRUE`; một điều kiện `UNKNOWN` không được xem như TRUE.

### 1.3. IS DISTINCT FROM: so sánh có xét NULL

PostgreSQL hỗ trợ:

~~~sql
SELECT
    NULL::integer IS NOT DISTINCT FROM NULL::integer AS same_nulls,
    10 IS DISTINCT FROM NULL::integer AS different_values,
    10 IS NOT DISTINCT FROM 10 AS same_numbers;
~~~

Khác phép `=` thông thường, `IS [NOT] DISTINCT FROM` trả kết quả boolean xác định khi gặp `NULL`:

- `a IS NOT DISTINCT FROM b`: xem hai `NULL` là tương đương cho mục đích so sánh này.
- `a IS DISTINCT FROM b`: nhận biết giá trị khác nhau, bao gồm trường hợp một bên là `NULL`.

Đây là công cụ bổ trợ quan trọng khi cần kiểm tra hai cột nullable đã thay đổi hay chưa. Nó **không thay thế** ý nghĩa của `NULLIF`, vì `NULLIF` trả về một giá trị/NULL chứ không trả về boolean.

## 2. Chuẩn bị dữ liệu thực hành

Các ví dụ dùng một bộ đơn hàng đủ nhỏ để dễ tự kiểm chứng bằng mắt. Hãy chạy phần tạo bảng trên **database học tập** mà bạn có quyền quản lý. Không xóa hoặc tạo lại schema có dữ liệu thật.

### 2.1. Tạo schema và hai bảng

~~~sql
CREATE SCHEMA expr_lab_135;

CREATE TABLE expr_lab_135.customers (
    customer_id BIGINT PRIMARY KEY,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    phone TEXT NULL,
    loyalty_tier TEXT NULL
);

CREATE TABLE expr_lab_135.orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NULL
        REFERENCES expr_lab_135.customers(customer_id),
    ordered_at TIMESTAMPTZ NOT NULL,
    subtotal NUMERIC(12, 2) NOT NULL CHECK (subtotal >= 0),
    discount_amount NUMERIC(12, 2) NULL
        CHECK (discount_amount >= 0),
    shipping_fee NUMERIC(12, 2) NULL
        CHECK (shipping_fee >= 0),
    item_count INTEGER NOT NULL CHECK (item_count >= 0),
    status TEXT NULL,
    paid_at TIMESTAMPTZ NULL,
    customer_note TEXT NULL
);
~~~

Ý nghĩa:

- `orders.customer_id` được phép `NULL` để biểu diễn đơn không gắn khách hàng đăng ký (guest order).
- `discount_amount` và `shipping_fee` có thể `NULL` để mô phỏng dữ liệu chưa nhập/không có thông tin.
- `item_count = 0` là dữ liệu cố ý để giải thích chia cho 0; số 0 không bị tự chuyển thành `NULL`.
- `status` có thể `NULL` để quan sát nhánh `ELSE` trong `CASE`.
- `paid_at` chỉ có giá trị ở các đơn được ghi nhận đã trả tiền.

Trong hệ thống production, mỗi cột nullable cần **quy tắc nghiệp vụ rõ ràng**: `NULL` là chưa biết, chưa tính, không áp dụng hay chưa nhập? Không nên tùy tiện xem mọi `NULL` là số 0 nếu sự khác nhau ảnh hưởng tiền hoặc báo cáo.

### 2.2. Thêm khách hàng

~~~sql
INSERT INTO expr_lab_135.customers
    (customer_id, full_name, email, phone, loyalty_tier)
VALUES
    (1, 'Nguyễn An',   'an@example.test',   '0901111111', 'GOLD'),
    (2, 'Trần Bình',   'binh@example.test', NULL,         'SILVER'),
    (3, 'Lê Chi',      'chi@example.test',  '',           NULL),
    (4, 'Phạm Dũng',   'dung@example.test', '   ',        'GOLD');
~~~

Các số điện thoại được chọn để minh họa ba trường hợp cần phân biệt: có giá trị, `NULL` và chuỗi rỗng/dấu cách. Chúng là **dữ liệu giả**, không phải thông tin liên hệ thật.

### 2.3. Thêm đơn hàng

~~~sql
INSERT INTO expr_lab_135.orders
    (
        order_id, customer_id, ordered_at,
        subtotal, discount_amount, shipping_fee,
        item_count, status, paid_at, customer_note
    )
VALUES
    (
        101, 1, '2026-11-10 09:00:00+07',
        100000, 10000, NULL,
        2, 'PAID', '2026-11-10 09:10:00+07', NULL
    ),
    (
        102, 1, '2026-11-11 14:00:00+07',
        250000, NULL, 15000,
        5, 'NEW', NULL, ''
    ),
    (
        103, 2, '2026-11-11 16:00:00+07',
        80000, 0, 10000,
        1, 'CANCELLED', NULL, 'Khách đổi ý'
    ),
    (
        104, 3, '2026-11-12 10:30:00+07',
        120000, 20000, NULL,
        0, NULL, NULL, '   '
    ),
    (
        105, NULL, '2026-11-12 11:00:00+07',
        70000, NULL, NULL,
        1, 'PAID', '2026-11-12 11:20:00+07', NULL
    ),
    (
        106, 4, '2026-11-13 08:15:00+07',
        1000000, 100000, 25000,
        10, 'PAID', '2026-11-13 08:30:00+07', 'Giao sớm'
    );
~~~

### 2.4. Xem dữ liệu gốc

~~~sql
SELECT
    order_id, customer_id, subtotal, discount_amount,
    shipping_fee, item_count, status, customer_note
FROM expr_lab_135.orders
ORDER BY order_id;
~~~

| Đơn | Khách | Tạm tính | Giảm giá | Vận chuyển | Số món | Trạng thái |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 101 | 1 | 100.000 | 10.000 | `NULL` | 2 | `PAID` |
| 102 | 1 | 250.000 | `NULL` | 15.000 | 5 | `NEW` |
| 103 | 2 | 80.000 | 0 | 10.000 | 1 | `CANCELLED` |
| 104 | 3 | 120.000 | 20.000 | `NULL` | 0 | `NULL` |
| 105 | `NULL` | 70.000 | `NULL` | `NULL` | 1 | `PAID` |
| 106 | 4 | 1.000.000 | 100.000 | 25.000 | 10 | `PAID` |

Điều cần giữ trong đầu: hàng **103 có giảm giá bằng số 0**; hàng 102 và 105 **chưa có giá trị giảm giá** (`NULL`). Hai trường hợp có thể được xử lý giống nhau trong phép tính tạm tính nhưng **không có cùng ý nghĩa dữ liệu**.

## 3. CASE là biểu thức rẽ nhánh trong SQL

`CASE` trả về một giá trị dựa trên điều kiện. Trong PostgreSQL có hai dạng phổ biến:

1. **Searched CASE**: mỗi nhánh kiểm tra một điều kiện boolean có thể khác nhau.
2. **Simple CASE**: so sánh một biểu thức đầu vào với nhiều giá trị `WHEN`.

Cả hai đều có thể dùng ở bất kỳ nơi nào PostgreSQL chấp nhận biểu thức SQL phù hợp.

### 3.1. Searched CASE: kiểm tra từng điều kiện

~~~sql
CASE
    WHEN condition_1 THEN result_1
    WHEN condition_2 THEN result_2
    ...
    ELSE default_result
END
~~~

PostgreSQL xét các điều kiện theo thứ tự; **nhánh đầu tiên có điều kiện TRUE** quyết định kết quả. Nếu không có nhánh nào TRUE:

- Có `ELSE`: dùng kết quả `ELSE`.
- Không có `ELSE`: kết quả là `NULL`.

Ví dụ không cần bảng:

~~~sql
SELECT
    CASE
        WHEN 85 >= 90 THEN 'Xuất sắc'
        WHEN 85 >= 70 THEN 'Đạt'
        ELSE 'Cần cải thiện'
    END AS assessment;
-- Đạt
~~~

Điều kiện thứ hai đúng; PostgreSQL trả `Đạt` và không chọn `ELSE`.

### 3.2. Dùng CASE để phân loại đơn theo trạng thái

~~~sql
SELECT
    order_id,
    status,
    CASE
        WHEN status = 'PAID' THEN 'Đã thanh toán'
        WHEN status = 'NEW' THEN 'Mới tạo'
        WHEN status = 'CANCELLED' THEN 'Đã hủy'
        WHEN status IS NULL THEN 'Chưa có trạng thái'
        ELSE 'Trạng thái khác'
    END AS status_label
FROM expr_lab_135.orders
ORDER BY order_id;
~~~

Trong dữ liệu mẫu:

| `status` | `status_label` |
| --- | --- |
| `PAID` | Đã thanh toán |
| `NEW` | Mới tạo |
| `CANCELLED` | Đã hủy |
| `NULL` | Chưa có trạng thái |

Nhánh `status IS NULL` rất quan trọng. Viết `WHEN status = NULL` sẽ **không chọn được** hàng có `NULL`.

### 3.3. CASE cho điều kiện nhiều cột và khoảng giá trị

~~~sql
SELECT
    order_id,
    subtotal,
    item_count,
    CASE
        WHEN subtotal >= 500000 AND item_count >= 5
            THEN 'Đơn lớn, nhiều món'
        WHEN subtotal >= 200000
            THEN 'Đơn giá trị cao'
        WHEN item_count = 0
            THEN 'Đơn chưa có món'
        ELSE 'Đơn thông thường'
    END AS order_group
FROM expr_lab_135.orders
ORDER BY order_id;
~~~

Searched CASE thích hợp cho các điều kiện chồng lấn hoặc có phép so sánh lớn hơn/nhỏ hơn. **Thứ tự nhánh là một phần của quy tắc nghiệp vụ**: nếu `subtotal >= 200000` được đặt trước điều kiện có `subtotal >= 500000`, các đơn lớn cũng có thể bị nhánh rộng hơn bắt mất.

### 3.4. Simple CASE: so một biểu thức với nhiều giá trị

~~~sql
CASE expression
    WHEN value_1 THEN result_1
    WHEN value_2 THEN result_2
    ...
    ELSE default_result
END
~~~

Ví dụ tương đương việc ánh xạ trạng thái:

~~~sql
SELECT
    order_id,
    CASE status
        WHEN 'PAID' THEN 'Đã thanh toán'
        WHEN 'NEW' THEN 'Mới tạo'
        WHEN 'CANCELLED' THEN 'Đã hủy'
        ELSE 'Chưa xác định'
    END AS status_label
FROM expr_lab_135.orders
ORDER BY order_id;
~~~

Simple CASE ngắn gọn khi chỉ có một biểu thức được so bằng với các giá trị. Tuy nhiên **simple CASE không chọn được hàng `status IS NULL` bằng cú pháp `WHEN NULL`**:

~~~sql
SELECT
    CASE NULL::text
        WHEN NULL::text THEN 'Hai NULL giống nhau?'
        ELSE 'Không khớp theo phép so sánh thông thường'
    END AS result;
-- Không khớp theo phép so sánh thông thường
~~~

Muốn phân biệt `NULL` với trạng thái lạ, dùng **searched CASE với `IS NULL`**, hoặc chuẩn hóa giá trị đầu vào theo quy tắc rõ ràng.

### 3.5. Searched CASE và simple CASE: chọn dạng nào?

| Mục tiêu | Dạng nên dùng |
| --- | --- |
| Ánh xạ mã `PAID`, `NEW`, `CANCELLED` | Simple CASE nếu không cần xử lý `NULL` riêng |
| Xử lý `NULL`/`IS NOT NULL` | Searched CASE |
| Phân nhóm theo `>=`, `BETWEEN` hoặc nhiều cột | Searched CASE |
| Nhiều điều kiện chồng lấn, cần thứ tự ưu tiên | Searched CASE |
| Ánh xạ một biểu thức vào vài giá trị cố định | Simple CASE |

### 3.6. CASE không có ELSE

~~~sql
SELECT
    order_id,
    CASE
        WHEN status = 'PAID' THEN 'Đã thu tiền'
    END AS payment_note
FROM expr_lab_135.orders
ORDER BY order_id;
~~~

Với các đơn không `PAID`, kết quả `payment_note` sẽ là `NULL`. Đây có thể là chủ ý để những hàm tổng hợp bỏ qua, nhưng trong giao diện người dùng, một nhãn `NULL` chưa chắc hữu ích. Nên ghi `ELSE` rõ ràng khi cần một giá trị mặc định.

## 4. CASE và quy tắc thứ tự ưu tiên

Một lỗi hay gặp là đặt điều kiện rộng lên trước điều kiện hẹp.

Ví dụ phân hạng đơn:

~~~sql
SELECT
    order_id,
    subtotal,
    CASE
        WHEN subtotal >= 100000 THEN 'Đơn trên 100 nghìn'
        WHEN subtotal >= 500000 THEN 'Đơn trên 500 nghìn'
        ELSE 'Đơn nhỏ'
    END AS incorrect_tier
FROM expr_lab_135.orders
WHERE order_id = 106;
~~~

Đơn `106` có `subtotal = 1000000` nhưng bị phân loại thành “Đơn trên 100 nghìn”, vì **nhánh đầu đã TRUE**.

Sửa theo thứ tự từ mức cao xuống thấp:

~~~sql
SELECT
    order_id,
    subtotal,
    CASE
        WHEN subtotal >= 500000 THEN 'Rất lớn'
        WHEN subtotal >= 100000 THEN 'Trung bình hoặc lớn'
        ELSE 'Nhỏ'
    END AS correct_tier
FROM expr_lab_135.orders
WHERE order_id = 106;
-- Rất lớn
~~~

Không phải mọi điều kiện đều có thể sắp xếp hoàn toàn theo ngưỡng. Khi có ưu tiên giữa nhiều thuộc tính, hãy ghi rõ thứ tự nghiệp vụ và thiết kế bộ test gồm cả những hàng thỏa **nhiều điều kiện cùng lúc**.

## 5. CASE với NULL và UNKNOWN

Điều kiện `WHEN` chỉ được chọn khi biểu thức là **TRUE**. Nếu kết quả là `NULL`/UNKNOWN, PostgreSQL thử nhánh tiếp theo.

~~~sql
SELECT
    CASE
        WHEN NULL::integer > 0 THEN 'Dương'
        WHEN NULL::integer <= 0 THEN 'Không dương'
        ELSE 'Không đủ dữ liệu'
    END AS classify_null;
-- Không đủ dữ liệu
~~~

Điều này khiến một biểu thức tưởng như đầy đủ:

~~~sql
CASE
    WHEN score >= 50 THEN 'Đạt'
    ELSE 'Không đạt'
END
~~~

phân loại **`score IS NULL` thành “Không đạt”**. Nếu `NULL` nghĩa là chưa có điểm, đó có thể là lỗi nghiệp vụ. Cách rõ ràng:

~~~sql
CASE
    WHEN score IS NULL THEN 'Chưa chấm'
    WHEN score >= 50 THEN 'Đạt'
    ELSE 'Không đạt'
END
~~~

**`ELSE` không chỉ chứa “điều kiện sai” mà còn nhận các tình huống UNKNOWN**. Mỗi khi làm việc với cột nullable, cần xét ngữ nghĩa của nhánh mặc định.

### 5.1. Biểu thức boolean trong CASE

~~~sql
SELECT
    order_id,
    CASE
        WHEN status = 'PAID' AND paid_at IS NOT NULL
            THEN 'Đã xác nhận thanh toán'
        WHEN status = 'PAID' AND paid_at IS NULL
            THEN 'Cần đối soát'
        WHEN status IS NULL
            THEN 'Chưa nhập trạng thái'
        ELSE 'Chưa thanh toán'
    END AS payment_state
FROM expr_lab_135.orders
ORDER BY order_id;
~~~

Ví dụ cho thấy `CASE` không giới hạn ở phép so sánh một cột; có thể kết hợp các kiểm tra logic như `IS NULL`, `AND`, `OR` hoặc `EXISTS` khi phù hợp.

## 6. COALESCE: chọn giá trị đầu tiên không NULL

Cú pháp:

~~~sql
COALESCE(value_1, value_2, ..., value_n)
~~~

`COALESCE` xét các biểu thức theo thứ tự và trả về **giá trị đầu tiên khác `NULL`**. Nếu tất cả đều `NULL`, kết quả là `NULL`.

~~~sql
SELECT
    COALESCE(NULL::text, 'Dự phòng A', 'Dự phòng B')
        AS first_available,
    COALESCE(NULL::integer, NULL::integer, 42)
        AS first_number,
    COALESCE(NULL::text, NULL::text)
        AS all_missing;
~~~

Kết quả lần lượt:

~~~text
first_available = Dự phòng A
first_number    = 42
all_missing     = NULL
~~~

### 6.1. Giá trị 0, FALSE và chuỗi rỗng vẫn được chọn

~~~sql
SELECT
    COALESCE(0, 100) AS zero_is_present,
    COALESCE(FALSE, TRUE) AS false_is_present,
    COALESCE(''::text, 'Dự phòng') AS empty_is_present;
~~~

Kết quả lần lượt: `0`, `FALSE` và chuỗi rỗng `''`.

**COALESCE không tìm “giá trị có ý nghĩa nghiệp vụ”; nó chỉ tìm giá trị khác `NULL`.** Muốn coi chuỗi rỗng là không hợp lệ, cần kết hợp `NULLIF` hoặc một bước làm sạch khác.

### 6.2. Thay NULL trong phép tính

Phép cộng/trừ thông thường với `NULL` cũng cho `NULL`:

~~~sql
SELECT
    100000::numeric - NULL::numeric AS unknown_total,
    100000::numeric - COALESCE(NULL::numeric, 0)
        AS defaulted_total;
~~~

Kết quả:

- `unknown_total` → `NULL`.
- `defaulted_total` → `100000`.

Ứng dụng trên bảng đơn hàng:

~~~sql
SELECT
    order_id,
    subtotal,
    discount_amount,
    shipping_fee,
    subtotal
        - COALESCE(discount_amount, 0)
        + COALESCE(shipping_fee, 0)
        AS estimated_payable_amount
FROM expr_lab_135.orders
ORDER BY order_id;
~~~

| Đơn | Tạm tính | Giảm giá đã thay NULL bằng 0 | Vận chuyển đã thay NULL bằng 0 | Tổng tính |
| --- | ---: | ---: | ---: | ---: |
| 101 | 100.000 | 10.000 | 0 | 90.000 |
| 102 | 250.000 | 0 | 15.000 | 265.000 |
| 103 | 80.000 | 0 | 10.000 | 90.000 |
| 104 | 120.000 | 20.000 | 0 | 100.000 |
| 105 | 70.000 | 0 | 0 | 70.000 |
| 106 | 1.000.000 | 100.000 | 25.000 | 925.000 |

Tên cột được đặt là **`estimated_payable_amount`** để nhấn mạnh đây chỉ là một **quy ước giả định**: khi giảm giá/vận chuyển `NULL`, bài học tạm tính như 0. Nếu `NULL` nghĩa là “chưa xác định phí”, tổng phải trả thực tế **chưa thể xác nhận**; khi đó không được thay 0 chỉ để có con số.

### 6.3. COALESCE cho nhiều nguồn dữ liệu

Ví dụ một API muốn hiển thị tên phù hợp:

~~~sql
SELECT
    customer_id,
    COALESCE(
        full_name,
        email,
        'Khách chưa xác định'
    ) AS display_name
FROM expr_lab_135.customers;
~~~

Trong bảng mẫu `full_name` là `NOT NULL` nên phương án dự phòng không được dùng. Trong hệ thống có nickname, company name hoặc full name nullable, chuỗi fallback mới thể hiện giá trị.

Thứ tự có ý nghĩa: `COALESCE(preferred_name, legal_name, email)` ưu tiên tên gọi trước tên pháp lý, không phải chọn ngẫu nhiên cột có dữ liệu.

### 6.4. COALESCE trong LEFT JOIN

`LEFT JOIN` giữ các đơn chưa có dòng khách phù hợp. Với guest order `105`:

~~~sql
SELECT
    o.order_id,
    o.customer_id,
    COALESCE(c.full_name, 'Khách vãng lai')
        AS customer_display_name
FROM expr_lab_135.orders AS o
LEFT JOIN expr_lab_135.customers AS c
    ON c.customer_id = o.customer_id
ORDER BY o.order_id;
~~~

Trong hàng `105`, vì `customer_id IS NULL`, phần bảng `customers` không có dòng match, nên `c.full_name` là `NULL` và `COALESCE` trả “Khách vãng lai”.

Lưu ý: một hàng không match sau `LEFT JOIN` và một hàng match nhưng cột nullable ở bảng phải `NULL` có thể cho biểu thức tương tự. Nếu cần phân biệt hai trường hợp, hãy kiểm tra một khóa `NOT NULL` của bảng phải, ví dụ `c.customer_id IS NULL`, thay vì chỉ nhìn `COALESCE(c.full_name, ...)`.

### 6.5. COALESCE trong ORDER BY

Khi cần đẩy các bản ghi chưa có điểm ưu tiên xuống cuối:

~~~sql
-- Ví dụ giả định bảng tasks(priority) tồn tại:
-- ORDER BY COALESCE(priority, 999) ASC
~~~

PostgreSQL cũng có cú pháp chuyên biệt:

~~~sql
-- ORDER BY priority ASC NULLS LAST
~~~

Nếu mục tiêu chỉ là đặt `NULL` trước/sau khi sắp xếp, **`NULLS FIRST`/`NULLS LAST` thường diễn đạt rõ hơn** và không cần gán một giá trị sentinel như 999 có thể trùng với dữ liệu thật.

## 7. NULLIF: đổi giá trị “không hợp lệ” thành NULL khi hai vế bằng nhau

Cú pháp:

~~~sql
NULLIF(expression_1, expression_2)
~~~

Quy tắc:

- Nếu hai biểu thức **bằng nhau** theo toán tử so sánh được PostgreSQL lựa chọn, trả về `NULL`.
- Nếu **không bằng nhau**, trả về giá trị của biểu thức thứ nhất (sau quy tắc phân giải kiểu).

Ví dụ:

~~~sql
SELECT
    NULLIF(0, 0) AS zero_equals_zero,
    NULLIF(15, 0) AS fifteen_not_zero,
    NULLIF('N/A'::text, 'N/A'::text) AS missing_marker,
    NULLIF('Đang xử lý'::text, 'N/A'::text) AS valid_text;
~~~

| Biểu thức | Kết quả |
| --- | --- |
| `NULLIF(0, 0)` | `NULL` |
| `NULLIF(15, 0)` | 15 |
| `NULLIF('N/A', 'N/A')` | `NULL` |
| `NULLIF('Đang xử lý', 'N/A')` | `Đang xử lý` |

Có thể hiểu gần đúng bằng `CASE`:

~~~sql
CASE
    WHEN expression_1 = expression_2 THEN NULL
    ELSE expression_1
END
~~~

Đây là cách diễn giải **logic**, không phải cam kết PostgreSQL thực thi `NULLIF` như một đoạn `CASE` với số lần đánh giá các biểu thức y hệt; đặc biệt không nên dựa vào việc biểu thức chứa hàm biến đổi liên tục/volatile chỉ được tính số lần mình đoán.

### 7.1. NULLIF không phải “IS DISTINCT FROM”

~~~sql
SELECT
    NULLIF(NULL::integer, NULL::integer) AS both_null,
    NULLIF(NULL::integer, 0) AS left_null,
    NULLIF(0, NULL::integer) AS right_null;
~~~

Kết quả `NULL`, `NULL` và `0` tương ứng. Khi một bên là `NULL`, phép so sánh `=` là UNKNOWN chứ không TRUE, nên về cơ bản `NULLIF` trả giá trị bên trái; nếu bên trái vốn là `NULL`, kết quả vẫn là `NULL`.

Không dùng `NULLIF(a,b) IS NULL` như một phép kiểm tra chính xác rằng `a` và `b` bằng nhau trong mọi trường hợp; nó cũng có thể `NULL` vì **`a` vốn `NULL`**.

### 7.2. Chia cho 0 an toàn trong biểu thức số

Trong PostgreSQL, phép chia số cho 0 thường gây lỗi:

~~~sql
-- Cố ý sai: có thể báo division_by_zero (SQLSTATE 22012).
-- SELECT 100::numeric / 0;
~~~

Để mẫu số bằng 0 thành `NULL`:

~~~sql
SELECT
    100::numeric / NULLIF(0, 0) AS safe_division;
-- NULL
~~~

Vì `NULLIF(0,0)` là `NULL`, phép chia cho `NULL` trả `NULL` thay vì chia cho 0. Với mẫu số khác 0, phép tính vẫn chạy:

~~~sql
SELECT
    100::numeric / NULLIF(4, 0) AS valid_division;
-- 25
~~~

### 7.3. Tính giá trị trung bình trên mỗi món

~~~sql
SELECT
    order_id,
    subtotal,
    item_count,
    subtotal / NULLIF(item_count, 0) AS amount_per_item
FROM expr_lab_135.orders
ORDER BY order_id;
~~~

Với đơn `104`, `item_count = 0`, nên `amount_per_item` trả `NULL`. Đây là lựa chọn hợp lý nếu “trung bình trên mỗi món” **không được định nghĩa** khi không có món nào.

Nếu giao diện thật sự muốn hiển thị 0 thay vì “chưa xác định”, có thể:

~~~sql
SELECT
    order_id,
    COALESCE(
        subtotal / NULLIF(item_count, 0),
        0
    ) AS amount_per_item_for_display
FROM expr_lab_135.orders
ORDER BY order_id;
~~~

Nhưng hãy cân nhắc **mặt nghĩa**: số 0 trong dashboard có thể bị hiểu nhầm rằng “giá trị trung bình bằng 0”, trong khi thực ra mẫu số bằng 0 và phép chia không có ý nghĩa. Để phân tích dữ liệu, thường nên giữ `NULL` hoặc hiển thị “Không áp dụng”.

### 7.4. Loại bỏ chuỗi rỗng và chuỗi toàn dấu cách

`NULLIF(phone, '')` chỉ xử lý chuỗi rỗng chính xác:

~~~sql
SELECT
    NULLIF(''::text, ''::text) AS empty_is_missing,
    NULLIF('   '::text, ''::text) AS spaces_are_not_empty;
~~~

Để coi chuỗi toàn dấu cách thông thường là không có dữ liệu, kết hợp `btrim`:

~~~sql
SELECT
    customer_id,
    phone,
    NULLIF(btrim(phone), '') AS cleaned_phone,
    COALESCE(
        NULLIF(btrim(phone), ''),
        'Chưa cung cấp'
    ) AS phone_for_display
FROM expr_lab_135.customers
ORDER BY customer_id;
~~~

Với bốn khách hàng:

| Khách | `phone` gốc | Sau `NULLIF(btrim(phone), '')` | Hiển thị |
| --- | --- | --- | --- |
| 1 | `0901111111` | `0901111111` | `0901111111` |
| 2 | `NULL` | `NULL` | Chưa cung cấp |
| 3 | `''` | `NULL` | Chưa cung cấp |
| 4 | `'   '` | `NULL` | Chưa cung cấp |

`btrim` theo mặc định xử lý những ký tự dấu cách theo quy tắc của nó; nếu dữ liệu chứa tab, Unicode whitespace hoặc ký tự điều khiển, cần quy tắc làm sạch thích hợp thay vì giả định mọi loại whitespace đều được xử lý giống nhau.

### 7.5. Chuẩn hóa giá trị đánh dấu thiếu dữ liệu

Hệ thống import có thể dùng `'N/A'`, `'-'` hoặc `'unknown'` để biểu thị thông tin thiếu:

~~~sql
SELECT
    COALESCE(
        NULLIF('N/A'::text, 'N/A'),
        'Chưa có thông tin'
    ) AS readable_value;
~~~

Nếu có nhiều sentinel khác nhau, một `CASE` rõ ràng có thể dễ đọc hơn chuỗi `NULLIF` lồng nhau:

~~~sql
SELECT
    CASE
        WHEN raw_value IS NULL THEN NULL
        WHEN lower(btrim(raw_value)) IN ('', 'n/a', 'unknown', '-')
            THEN NULL
        ELSE btrim(raw_value)
    END AS normalized_value
FROM (
    VALUES
        ('N/A'::text),
        (' UNKNOWN '::text),
        ('Hợp lệ'::text),
        (NULL::text)
) AS src(raw_value);
~~~

Không loại giá trị `'0'`, `'-'` hoặc `'unknown'` một cách máy móc nếu chúng là **giá trị thực sự hợp lệ** trong một miền nghiệp vụ khác. Việc chuẩn hóa phải dựa trên dữ liệu nguồn và tài liệu quy ước.

## 8. Kết hợp CASE, COALESCE và NULLIF trong một truy vấn

Ba biểu thức thường phối hợp theo một chuỗi:

~~~text
Dữ liệu thô
   |
   +--> NULLIF: biến giá trị sentinel thành NULL
   |
   +--> COALESCE: chọn giá trị dự phòng nếu cần
   |
   +--> CASE: phân loại hoặc diễn giải theo điều kiện
   |
   v
Biểu thức kết quả cho báo cáo hoặc API
~~~

Ví dụ đồng thời phân loại trạng thái, làm sạch ghi chú và tính tiền:

~~~sql
SELECT
    o.order_id,
    CASE
        WHEN o.status IS NULL THEN 'Chưa nhập'
        WHEN o.status = 'PAID' THEN 'Đã thanh toán'
        WHEN o.status = 'NEW' THEN 'Đang chờ'
        WHEN o.status = 'CANCELLED' THEN 'Đã hủy'
        ELSE 'Khác'
    END AS status_label,
    COALESCE(
        NULLIF(btrim(o.customer_note), ''),
        'Không có ghi chú'
    ) AS normalized_note,
    o.subtotal
        - COALESCE(o.discount_amount, 0)
        + COALESCE(o.shipping_fee, 0)
        AS estimated_payable,
    CASE
        WHEN o.item_count = 0 THEN 'Chưa có món'
        WHEN o.subtotal / NULLIF(o.item_count, 0) >= 100000
            THEN 'Giá trị trung bình cao'
        ELSE 'Thông thường'
    END AS item_value_group
FROM expr_lab_135.orders AS o
ORDER BY o.order_id;
~~~

Trong bài toán này:

- `CASE` làm rõ ý nghĩa của trạng thái `NULL` thay vì nhập chung vào “khác”.
- `NULLIF(btrim(...), '')` đổi ghi chú trống/chỉ dấu cách thành `NULL`.
- `COALESCE(..., 'Không có ghi chú')` tạo nhãn hiển thị.
- `COALESCE(..., 0)` cung cấp quy ước tính tiền giả định.
- `NULLIF(item_count, 0)` ngăn phép chia không hợp lệ.

Đối với điều kiện `item_count = 0`, nhánh đầu tiên xử lý tình huống không có món. `NULLIF` vẫn là lớp biểu thức an toàn hữu ích nếu sau này logic thay đổi hoặc phép chia được dùng ở nơi khác.

## 9. CASE để tổng hợp có điều kiện

Một trong những ứng dụng quan trọng nhất của `CASE` là **conditional aggregation**: dùng `CASE` bên trong `SUM`, `COUNT` hoặc `AVG` để tính các chỉ số theo điều kiện.

### 9.1. Đếm số đơn theo trạng thái

~~~sql
SELECT
    COUNT(*) AS total_orders,
    SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END)
        AS paid_orders,
    SUM(CASE WHEN status = 'NEW' THEN 1 ELSE 0 END)
        AS new_orders,
    SUM(CASE WHEN status = 'CANCELLED' THEN 1 ELSE 0 END)
        AS cancelled_orders,
    SUM(CASE WHEN status IS NULL THEN 1 ELSE 0 END)
        AS missing_status_orders
FROM expr_lab_135.orders;
~~~

Từ dữ liệu mẫu:

| Chỉ số | Số lượng |
| --- | ---: |
| Tất cả đơn | 6 |
| `PAID` | 3 |
| `NEW` | 1 |
| `CANCELLED` | 1 |
| `NULL` | 1 |

Mỗi hàng được chuyển thành 1 hoặc 0 trước khi cộng. Nếu thiếu `ELSE 0`, các hàng không thỏa điều kiện trả `NULL` và `SUM` bỏ qua chúng; khi không có hàng nào thỏa, kết quả có thể `NULL` thay vì 0.

### 9.2. COUNT(CASE WHEN...) hoạt động ra sao?

~~~sql
SELECT
    COUNT(
        CASE WHEN status = 'PAID' THEN 1 END
    ) AS paid_orders
FROM expr_lab_135.orders;
~~~

`COUNT(expression)` đếm **các giá trị khác `NULL`**. Ở đây, chỉ đơn `PAID` trả 1, các đơn khác trả `NULL` do không có `ELSE`, nên kết quả bằng 3.

So sánh các mẫu:

~~~sql
SELECT
    COUNT(*) AS every_row,
    COUNT(status) AS rows_with_status,
    COUNT(CASE WHEN status = 'PAID' THEN 1 END)
        AS paid_by_case,
    COUNT(*) FILTER (WHERE status = 'PAID')
        AS paid_by_filter
FROM expr_lab_135.orders;
~~~

| Biểu thức | Kết quả |
| --- | ---: |
| `COUNT(*)` | 6 |
| `COUNT(status)` | 5 |
| `COUNT(CASE WHEN status = 'PAID' THEN 1 END)` | 3 |
| `COUNT(*) FILTER (WHERE status = 'PAID')` | 3 |

PostgreSQL hỗ trợ cú pháp **`FILTER (WHERE ...)`** cho hàm tổng hợp. Khi chỉ cần đếm hoặc tổng hợp theo điều kiện, `FILTER` thường ngắn gọn và rõ nghĩa hơn `SUM(CASE WHEN ...)`. Tuy nhiên, `CASE` vẫn hữu ích cho những phép tính có nhiều giá trị khác nhau theo từng nhánh.

### 9.3. Tổng doanh thu theo trạng thái

~~~sql
SELECT
    SUM(
        CASE
            WHEN status = 'PAID'
                THEN subtotal - COALESCE(discount_amount, 0)
                     + COALESCE(shipping_fee, 0)
            ELSE 0
        END
    ) AS paid_order_value
FROM expr_lab_135.orders;
~~~

Kết quả với dữ liệu mẫu là **1.085.000** (đơn 101: 90.000; 105: 70.000; 106: 925.000).

Đây là **giá trị tính theo quy ước bài tập**, không đồng nghĩa doanh thu đã được xác nhận về kế toán, hoàn tiền hoặc thuế. Để báo cáo tài chính, cần xác định cách xử lý các đơn hủy/hoàn, thời điểm ghi nhận và các khoản phí chưa xác định.

### 9.4. Tránh lỗi “COUNT(CASE ... ELSE 0 END)”

Một lỗi logic thường gặp:

~~~sql
SELECT
    COUNT(
        CASE WHEN status = 'PAID' THEN 1 ELSE 0 END
    ) AS wrong_paid_count
FROM expr_lab_135.orders;
-- 6, không phải 3!
~~~

Vì **0 cũng không phải `NULL`**, `COUNT` đếm cả nhánh `ELSE 0`.

Muốn đếm bằng CASE, chọn một trong hai cách:

~~~sql
COUNT(CASE WHEN condition THEN 1 END)
~~~

hoặc:

~~~sql
SUM(CASE WHEN condition THEN 1 ELSE 0 END)
~~~

Trong PostgreSQL, `COUNT(*) FILTER (WHERE condition)` cũng là lựa chọn rất rõ ràng.

## 10. CASE trong GROUP BY và HAVING

`CASE` có thể nhóm các bản ghi theo một **phân loại tính toán**, thay vì chỉ theo một cột gốc.

~~~sql
SELECT
    CASE
        WHEN subtotal >= 500000 THEN 'Lớn'
        WHEN subtotal >= 100000 THEN 'Trung bình'
        ELSE 'Nhỏ'
    END AS order_band,
    COUNT(*) AS order_count,
    SUM(subtotal) AS subtotal_sum
FROM expr_lab_135.orders
GROUP BY order_band
ORDER BY
    CASE order_band
        WHEN 'Lớn' THEN 1
        WHEN 'Trung bình' THEN 2
        ELSE 3
    END;
~~~

Ở PostgreSQL, `GROUP BY` có thể tham chiếu alias của một biểu thức trong select list ở những trường hợp phù hợp. Nếu một alias xung đột với tên cột đầu vào, quy tắc phân giải có thể gây bất ngờ; nên chọn alias rõ ràng hoặc dùng **CTE** để tách bước tính.

### 10.1. CTE giúp đọc logic phân loại

~~~sql
WITH classified AS (
    SELECT
        order_id,
        subtotal,
        CASE
            WHEN subtotal >= 500000 THEN 'Lớn'
            WHEN subtotal >= 100000 THEN 'Trung bình'
            ELSE 'Nhỏ'
        END AS order_band
    FROM expr_lab_135.orders
)
SELECT
    order_band,
    COUNT(*) AS order_count,
    SUM(subtotal) AS subtotal_sum
FROM classified
GROUP BY order_band
HAVING COUNT(*) >= 1
ORDER BY order_band;
~~~

`HAVING` lọc **nhóm sau khi tổng hợp**, còn `WHERE` lọc **hàng trước khi tổng hợp**. `CASE` có thể dùng ở cả hai giai đoạn, nhưng ý nghĩa và mức chi phí có thể khác.

### 10.2. Nhóm khách hàng có và không có mã loyalty

~~~sql
SELECT
    COALESCE(loyalty_tier, 'UNASSIGNED')
        AS loyalty_group,
    COUNT(*) AS customer_count
FROM expr_lab_135.customers
GROUP BY COALESCE(loyalty_tier, 'UNASSIGNED')
ORDER BY loyalty_group;
~~~

Vì `COALESCE` làm việc trên giá trị nhóm, người dùng có thể thấy nhóm `UNASSIGNED` thay vì `NULL`. Tuy nhiên, nếu dữ liệu thật có giá trị `loyalty_tier = 'UNASSIGNED'` được lưu chính thức, cách nhóm này sẽ gộp **hai ý nghĩa khác nhau**. Khi cần phân biệt, hãy nhóm theo cột gốc hoặc tạo phân loại có nhãn không nhập nhằng.

## 11. CASE trong ORDER BY: sắp xếp theo quy tắc nghiệp vụ

Giả sử muốn ưu tiên:

1. Đơn `NEW`.
2. Đơn `PAID`.
3. Đơn `CANCELLED`.
4. Đơn thiếu trạng thái hoặc giá trị lạ.

Sắp theo chữ cái không đáp ứng thứ tự này. Dùng CASE:

~~~sql
SELECT
    order_id,
    status,
    ordered_at
FROM expr_lab_135.orders
ORDER BY
    CASE
        WHEN status = 'NEW' THEN 1
        WHEN status = 'PAID' THEN 2
        WHEN status = 'CANCELLED' THEN 3
        ELSE 4
    END,
    ordered_at DESC;
~~~

`CASE` trả về một **sort key số**, còn `ordered_at DESC` giải quyết thứ tự giữa các đơn cùng mức ưu tiên.

### 11.1. COALESCE để đưa tên khách thiếu về một nhãn

~~~sql
SELECT
    o.order_id,
    COALESCE(c.full_name, 'Khách vãng lai')
        AS customer_name
FROM expr_lab_135.orders AS o
LEFT JOIN expr_lab_135.customers AS c
    ON c.customer_id = o.customer_id
ORDER BY customer_name, o.order_id;
~~~

Tuy nhiên, nếu muốn **dòng guest cuối cùng** thay vì trộn theo chữ cái của nhãn, có thể dùng:

~~~sql
ORDER BY c.full_name ASC NULLS LAST, o.order_id
~~~

Điều này thể hiện rõ ý định sắp xếp `NULL`, tránh phụ thuộc vào tên nhãn dự phòng.

## 12. CASE trong WHERE: khi nào cần và khi nào không?

Vì `CASE` trả về một giá trị, có thể dùng nó trong `WHERE` khi kết quả là boolean:

~~~sql
SELECT order_id, status, subtotal
FROM expr_lab_135.orders
WHERE
    CASE
        WHEN status = 'PAID' THEN subtotal >= 100000
        WHEN status = 'NEW' THEN subtotal >= 200000
        ELSE FALSE
    END
ORDER BY order_id;
~~~

Với dữ liệu mẫu, đơn `106` được chọn vì `PAID` và tạm tính cao; đơn `102` được chọn vì `NEW` và tạm tính 250.000; đơn `101` cũng có `PAID` và tạm tính 100.000. Kết quả gồm **101, 102, 106**.

Nhưng cùng logic thường diễn đạt rõ bằng boolean:

~~~sql
SELECT order_id, status, subtotal
FROM expr_lab_135.orders
WHERE
    (status = 'PAID' AND subtotal >= 100000)
    OR
    (status = 'NEW' AND subtotal >= 200000)
ORDER BY order_id;
~~~

**Không phải cứ có điều kiện là nên bọc CASE.** Dùng `AND`/`OR` trực tiếp trong `WHERE` thường dễ hiểu hơn và có thể tạo điều kiện để query planner khai thác index/sargability. CASE phù hợp khi cần **tính một giá trị theo nhánh**, không phải thay mọi biểu thức boolean.

### 12.1. COALESCE trong WHERE có thể thay đổi ý nghĩa

~~~sql
SELECT order_id, status
FROM expr_lab_135.orders
WHERE COALESCE(status, 'NEW') = 'NEW';
~~~

Truy vấn này chọn **cả đơn `NEW` lẫn đơn `status IS NULL`** vì chủ động xem thiếu trạng thái như NEW.

Nếu nghiệp vụ chỉ muốn trạng thái thật sự là NEW:

~~~sql
WHERE status = 'NEW'
~~~

Nếu muốn cả hai nhóm nhưng giữ điều kiện rõ:

~~~sql
WHERE status = 'NEW' OR status IS NULL
~~~

Không nên dùng `COALESCE` để lấp dữ liệu thiếu mà quên nó làm thay đổi tập bản ghi được chọn.

## 13. Kiểu dữ liệu của kết quả CASE và COALESCE

PostgreSQL cần chọn **một kiểu dữ liệu đầu ra** cho biểu thức. Các nhánh `THEN`/`ELSE` của `CASE` và các đối số của `COALESCE` phải có kiểu **có thể được phân giải tương thích** theo quy tắc PostgreSQL.

### 13.1. CASE có các nhánh cùng kiểu

~~~sql
SELECT
    CASE
        WHEN TRUE THEN 100::numeric
        ELSE 0::numeric
    END AS numeric_result,
    pg_typeof(
        CASE WHEN TRUE THEN 100::numeric ELSE 0::numeric END
    ) AS result_type;
~~~

Ở đây kiểu đầu ra là `numeric`.

### 13.2. Không trộn số với text tùy tiện

~~~sql
-- Không phải thiết kế phù hợp:
-- SELECT CASE
--     WHEN status = 'PAID' THEN subtotal
--     ELSE 'Chưa trả tiền'
-- END
-- FROM expr_lab_135.orders;
~~~

Một nhánh là số `NUMERIC`, nhánh còn lại là chuỗi mô tả. PostgreSQL có thể cố ép chuỗi sang kiểu số và báo lỗi, hoặc không thể phân giải kiểu theo cách mong muốn.

Nếu muốn **nhãn hiển thị text**, chuyển số thành text tường minh:

~~~sql
SELECT
    order_id,
    CASE
        WHEN status = 'PAID' THEN subtotal::text
        ELSE 'Chưa trả tiền'
    END AS display_value
FROM expr_lab_135.orders
ORDER BY order_id;
~~~

Nếu muốn **kết quả dùng cho phép tính**, giữ tất cả nhánh là số:

~~~sql
SELECT
    order_id,
    CASE
        WHEN status = 'PAID' THEN subtotal
        ELSE 0::numeric
    END AS paid_subtotal
FROM expr_lab_135.orders;
~~~

**Không trộn tiền với chuỗi trong một cột chỉ để giao diện dễ hiển thị**, nếu sau đó ứng dụng còn tổng hợp hoặc sắp xếp theo số.

### 13.3. COALESCE cũng cần kiểu tương thích

~~~sql
SELECT
    COALESCE(NULL::numeric, 0::numeric) AS amount_zero,
    COALESCE(NULL::text, 'Chưa có') AS text_default;
~~~

Đối với chuỗi chứa chữ số và số:

~~~sql
-- Tránh dựa vào ép kiểu ngầm định khó đoán:
-- COALESCE(total_amount, '0')

-- Diễn đạt ý định kiểu rõ ràng:
COALESCE(total_amount, 0::numeric)
~~~

Đoạn cuối là biểu thức minh họa dùng trong một câu SQL có cột `total_amount` kiểu `numeric`; không chạy riêng dòng đó ngoài truy vấn nếu chưa có cột tương ứng.

### 13.4. NULLIF có thể trả kiểu được nâng lên

`NULLIF` dùng phép so sánh bằng nhau sau khi phân giải toán tử phù hợp. Kiểu của kết quả **không phải lúc nào cũng chính xác là kiểu nguyên thủy của đối số thứ nhất** nếu PostgreSQL phải nâng kiểu để sử dụng toán tử so sánh.

Ví dụ:

~~~sql
SELECT
    pg_typeof(NULLIF(1, 2)) AS integer_result_type,
    pg_typeof(NULLIF(1, 2.2)) AS promoted_result_type;
~~~

Trong trường hợp thường gặp, `NULLIF(1, 2)` có kiểu integer, còn biểu thức có `2.2` có thể được phân giải sang `numeric`. Khi truyền dữ liệu qua JDBC, tạo view hoặc hợp đồng API, nên dùng **ép kiểu tường minh** nếu kiểu đầu ra là một phần quan trọng của giao diện.

### 13.5. Typed NULL và literal NULL

~~~sql
SELECT
    COALESCE(NULL::integer, 5) AS int_default,
    COALESCE(NULL::text, 'N/A') AS text_default,
    CASE WHEN FALSE THEN 1 ELSE NULL::integer END
        AS nullable_integer;
~~~

Việc ghi rõ `NULL::integer` hoặc `NULL::text` giúp database và người đọc biết nhánh `NULL` thuộc miền dữ liệu nào. Nó cũng giúp tránh những lỗi phân giải kiểu khi biểu thức được dùng trong `UNION`, view, function hoặc prepared statement.

## 14. Giới hạn “chỉ đánh giá nhánh cần thiết”

`CASE` và `COALESCE` thường giúp tránh đánh giá những biểu thức không cần để tạo kết quả. Tuy vậy, **không được coi đây là cam kết tuyệt đối rằng mọi biểu thức trong nhánh không chọn sẽ không bao giờ được PostgreSQL xử lý ở mọi giai đoạn**.

### 14.1. Phép chia có điều kiện

~~~sql
SELECT
    order_id,
    CASE
        WHEN item_count = 0 THEN NULL::numeric
        ELSE subtotal / item_count
    END AS average_per_item
FROM expr_lab_135.orders;
~~~

Ở truy vấn thông thường, PostgreSQL chọn nhánh có điều kiện phù hợp; với đơn `104`, `item_count = 0` nên kết quả `NULL` và không cần tính phép chia ở nhánh còn lại.

Mẫu tương đương ngắn và phù hợp hơn khi chia:

~~~sql
SELECT
    order_id,
    subtotal / NULLIF(item_count, 0) AS average_per_item
FROM expr_lab_135.orders;
~~~

### 14.2. Vì sao không dựa vào CASE để che mọi lỗi biểu thức?

PostgreSQL có thể **rút gọn biểu thức hằng tại thời điểm lập kế hoạch**. Vì vậy một biểu thức không hợp lệ như `1 / 0` đặt ở một nhánh tưởng như không chạy vẫn có thể bị planner đánh giá sớm trong một số tình huống.

Ví dụ sau **không phải mẫu an toàn để xử lý mọi lỗi chia cho 0**:

~~~sql
-- Không chạy như một cách kiểm soát lỗi chung:
-- SELECT CASE WHEN FALSE THEN 1 / 0 ELSE 0 END;
~~~

Ngoài ra, các biểu thức aggregate có thể được tính **trước khi CASE ở select list quyết định nhánh**, nên không thể dùng `CASE` bao ngoài một phép tổng hợp sai để đảm bảo nó sẽ không được thực hiện.

Ví dụ khái niệm nguy hiểm:

~~~sql
-- Không nên chỉ tin rằng CASE bao ngoài sẽ chặn phép chia lỗi
-- nếu aggregate có thể được xử lý trước biểu thức CASE:
-- SELECT CASE
--          WHEN MIN(denominator) = 0 THEN 0
--          ELSE MAX(numerator / denominator)
--        END
-- FROM some_table;
~~~

Hướng tốt hơn là xử lý mẫu số **ngay bên trong biểu thức chia**:

~~~sql
SELECT
    MAX(subtotal / NULLIF(item_count, 0))
        AS max_amount_per_item
FROM expr_lab_135.orders;
~~~

Phép chia với mẫu số 0 trở thành `NULL`; `MAX` bỏ qua các giá trị `NULL`. Dù vậy, đây chỉ là quyết định **tránh lỗi số học**; nghiệp vụ vẫn phải quyết định có bỏ qua đơn không có món trong chỉ số tối đa hay không.

### 14.3. Không dùng thứ tự AND/OR để buộc phép tính an toàn

Một điều kiện như:

~~~sql
-- Không nên coi thứ tự từ trái sang phải là bảo đảm chung:
-- WHERE item_count <> 0 AND subtotal / item_count > 100000
~~~

không nên được xem như một “short circuit guard” tuyệt đối vì optimizer có quyền tổ chức lại biểu thức boolean theo cách phù hợp ngữ nghĩa SQL. Với phép chia có khả năng gặp 0, dùng:

~~~sql
WHERE subtotal / NULLIF(item_count, 0) > 100000
~~~

Khi `item_count = 0`, phép chia cho `NULL` cho `NULL`, điều kiện `WHERE` là UNKNOWN và hàng đó không được chọn.

## 15. NULLIF và COALESCE trong báo cáo tỷ lệ

Các chỉ số phần trăm thường có dạng:

\[
\text{Tỷ lệ (\%)} = \frac{\text{Số sự kiện phù hợp}}{\text{Tổng số sự kiện}} \times 100
\]

Nếu tổng số sự kiện bằng 0, không thể thực hiện phép chia thông thường.

### 15.1. Tỷ lệ đơn đã thanh toán

~~~sql
SELECT
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (WHERE status = 'PAID')
        AS paid_orders,
    100.0
        * COUNT(*) FILTER (WHERE status = 'PAID')
        / NULLIF(COUNT(*), 0)
        AS paid_percentage
FROM expr_lab_135.orders;
~~~

Dữ liệu mẫu có 3/6 đơn `PAID` nên tỷ lệ là **50%**.

Ở đây:

- `COUNT(*)` trả 0 nếu bảng không có hàng.
- `NULLIF(COUNT(*), 0)` trả `NULL` nếu mẫu số bằng 0.
- `100.0` giúp biểu thức dùng số thập phân trong tính toán theo kiểu thích hợp, tránh nhầm với phép chia số nguyên.

Nếu bảng rỗng, `paid_percentage` trả `NULL`, thể hiện **không có mẫu để tính tỷ lệ**. Nếu dashboard yêu cầu số 0 trong trường hợp không có dữ liệu, có thể bọc thêm `COALESCE` nhưng phải ghi rõ quy ước.

### 15.2. Tỷ lệ theo nhóm và nhóm rỗng

~~~sql
SELECT
    customer_id,
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (WHERE status = 'PAID')
        AS paid_orders,
    ROUND(
        100.0
            * COUNT(*) FILTER (WHERE status = 'PAID')
            / NULLIF(COUNT(*), 0),
        2
    ) AS paid_percent
FROM expr_lab_135.orders
GROUP BY customer_id
ORDER BY customer_id NULLS LAST;
~~~

Khi `GROUP BY` lấy dữ liệu thực tế từ bảng, nhóm được trả về sẽ có ít nhất một dòng; `COUNT(*)` trong nhóm không bằng 0. Nhưng nếu tính tỷ lệ ở một bảng tổng hợp có nhóm sinh ra từ `LEFT JOIN` hoặc danh sách kỳ báo cáo không có sự kiện, `NULLIF` bảo vệ phép chia trong công thức chung.

### 15.3. Không lấy trung bình các tỷ lệ nhóm nếu trọng số khác nhau

Giả sử nhóm A có 1 đơn thanh toán trên 1 đơn, nhóm B có 1 đơn thanh toán trên 9 đơn. Trung bình của **100%** và **11,11%** không bằng tỷ lệ tổng thể **2/10 = 20%**. `CASE`/`NULLIF` giúp tính toán có điều kiện, nhưng không tự chọn đúng **mẫu số thống kê**. Cần xác định cấp tổng hợp và trọng số theo yêu cầu nghiệp vụ.

## 16. COALESCE và các hàm tổng hợp: thứ tự áp dụng rất quan trọng

Các hàm tổng hợp trong PostgreSQL có quy tắc xử lý `NULL` riêng:

- `COUNT(*)` đếm số hàng.
- `COUNT(expression)` đếm số giá trị không `NULL`.
- `SUM(expression)` bỏ qua giá trị `NULL`, nhưng trên tập không có giá trị không-NULL có thể trả `NULL`.
- `AVG(expression)` bỏ qua giá trị `NULL`.

### 16.1. SUM(COALESCE(x,0)) và COALESCE(SUM(x),0)

So sánh:

~~~sql
SELECT
    SUM(COALESCE(discount_amount, 0))
        AS sum_with_row_defaults,
    COALESCE(SUM(discount_amount), 0)
        AS sum_with_aggregate_default
FROM expr_lab_135.orders;
~~~

Trên một bảng có ít nhất một giá trị hợp lệ, cả hai có thể cùng trả **130.000** cho dữ liệu ví dụ (10.000 + 0 + 20.000 + 100.000).

Nhưng về mặt ngữ nghĩa:

- `SUM(COALESCE(x,0))` **thay mọi giá trị thiếu trong từng hàng thành 0 trước khi cộng**.
- `COALESCE(SUM(x),0)` **để SUM bỏ qua NULL**, rồi chỉ thay kết quả tổng hợp `NULL` thành 0 khi không có giá trị được cộng.

Hai biểu thức có thể khác khi phối hợp với `AVG`, `COUNT`, các phép tính khác hoặc khi cần phân biệt “không biết” với “bằng 0”.

### 16.2. AVG(COALESCE(x,0)) khác AVG(x)

~~~sql
SELECT
    AVG(discount_amount) AS average_known_discounts,
    AVG(COALESCE(discount_amount, 0))
        AS average_with_missing_as_zero,
    COUNT(discount_amount) AS known_discount_rows,
    COUNT(*) AS all_orders
FROM expr_lab_135.orders;
~~~

Dữ liệu mẫu có các giảm giá biết được: `10000`, `0`, `20000`, `100000`. Hai dòng còn lại không có giảm giá; thực tế có **6 đơn và 4 giá trị discount đã biết**.

- `AVG(discount_amount)` tính trung bình trên **4 giá trị đã biết**: **32.500**.
- `AVG(COALESCE(discount_amount,0))` tính trung bình trên **6 đơn** sau khi coi thiếu là 0: khoảng **21.666,67**.

Cả hai công thức có thể hợp lệ tùy mục tiêu, nhưng **không được âm thầm thay dữ liệu thiếu bằng 0 rồi gọi đó là trung bình của các giá trị quan sát được**.

### 16.3. Chỉ số không có dữ liệu và chỉ số thật sự bằng 0

Ví dụ một kỳ báo cáo không có đơn:

~~~sql
SELECT
    SUM(subtotal) AS no_rows_sum,
    COALESCE(SUM(subtotal), 0) AS zero_for_display,
    COUNT(*) AS no_rows_count
FROM expr_lab_135.orders
WHERE order_id < 0;
~~~

`SUM(subtotal)` trả `NULL` vì không có hàng, `COALESCE(SUM(...),0)` trả 0, `COUNT(*)` trả 0. Cần cân nhắc việc hiển thị “0 doanh thu” có phù hợp với “không có dữ liệu trong kỳ” hay không.

## 17. CASE khi UPDATE dữ liệu

Ba biểu thức không chỉ xuất hiện trong truy vấn đọc. `CASE` có thể tính giá trị mới trong `UPDATE`:

~~~sql
-- Ví dụ thực hành trong transaction; ROLLBACK để giữ seed ban đầu.
BEGIN;

UPDATE expr_lab_135.orders
SET status = CASE
    WHEN status IS NULL THEN 'NEW'
    ELSE status
END
WHERE status IS NULL;

SELECT order_id, status
FROM expr_lab_135.orders
WHERE order_id = 104;
-- NEW trong transaction này.

ROLLBACK;
~~~

Nếu chỉ muốn điền mặc định cho `NULL`, `COALESCE` ngắn hơn:

~~~sql
BEGIN;

UPDATE expr_lab_135.orders
SET status = COALESCE(status, 'NEW')
WHERE status IS NULL;

ROLLBACK;
~~~

Nhưng **thao tác làm sạch hàng loạt dữ liệu thật không nên tự động chạy** chỉ vì biểu thức SQL dễ viết. `status IS NULL` có thể biểu thị lỗi đồng bộ, chưa kiểm duyệt hoặc trạng thái chưa xác nhận, không nhất thiết là NEW.

### 17.1. Chuẩn hóa chuỗi khi ghi

~~~sql
BEGIN;

UPDATE expr_lab_135.customers
SET phone = NULLIF(btrim(phone), '')
WHERE phone IS NOT NULL;

ROLLBACK;
~~~

Sau khi đã xác định nghiệp vụ coi chuỗi trắng là thiếu, có thể áp dụng rule ở tầng ingestion/application hoặc migration. Tránh dọn dữ liệu theo cách mất thông tin khi chưa có kế hoạch backup và kiểm thử.

### 17.2. CASE trong UPSERT

PostgreSQL hỗ trợ `INSERT ... ON CONFLICT DO UPDATE`. Trong một trường hợp đồng bộ thông tin, có thể dùng `COALESCE` để giữ giá trị cũ nếu đầu vào mới bị `NULL`:

~~~sql
-- Minh họa ý tưởng, giả định customer_id=1 tồn tại:
BEGIN;

INSERT INTO expr_lab_135.customers
    (customer_id, full_name, email, phone, loyalty_tier)
VALUES
    (1, 'Nguyễn An', 'an@example.test', NULL, NULL)
ON CONFLICT (customer_id) DO UPDATE
SET
    phone = COALESCE(
        EXCLUDED.phone,
        expr_lab_135.customers.phone
    );

ROLLBACK;
~~~

Ở đây `EXCLUDED.phone` là giá trị đầu vào từ bản ghi đang chèn. Nếu nó `NULL`, câu lệnh giữ giá trị `phone` cũ. **Đây là một quy ước update**: không thể dùng biểu thức này nếu `NULL` đầu vào có nghĩa là **người dùng muốn xóa số điện thoại**. API nên phân biệt rõ “không gửi trường” và “gửi trường với null để xóa” khi nghiệp vụ yêu cầu.

## 18. CASE, COALESCE và NULLIF trong VIEW

Một view có thể gom những biểu thức hiển thị thường dùng để ứng dụng không lặp lại logic:

~~~sql
CREATE VIEW expr_lab_135.v_order_display AS
SELECT
    o.order_id,
    o.ordered_at,
    COALESCE(c.full_name, 'Khách vãng lai')
        AS customer_display_name,
    CASE
        WHEN o.status IS NULL THEN 'Chưa nhập'
        WHEN o.status = 'PAID' THEN 'Đã thanh toán'
        WHEN o.status = 'NEW' THEN 'Đang xử lý'
        WHEN o.status = 'CANCELLED' THEN 'Đã hủy'
        ELSE 'Khác'
    END AS status_label,
    COALESCE(
        NULLIF(btrim(o.customer_note), ''),
        'Không có ghi chú'
    ) AS customer_note_display,
    o.subtotal
        - COALESCE(o.discount_amount, 0)
        + COALESCE(o.shipping_fee, 0)
        AS estimated_payable
FROM expr_lab_135.orders AS o
LEFT JOIN expr_lab_135.customers AS c
    ON c.customer_id = o.customer_id;
~~~

Tra cứu:

~~~sql
SELECT *
FROM expr_lab_135.v_order_display
ORDER BY order_id;
~~~

**View không tự biến quy ước thành sự thật**. Nếu phí vận chuyển đang chờ tính, view trên vẫn giả định 0. Muốn tái sử dụng kết quả trong production, nên thảo luận tên trường, cách xử lý `NULL`, loại tiền tệ và trách nhiệm cập nhật định nghĩa view qua migration.

### 18.1. Khi thay đổi quy tắc báo cáo

Giả sử sau này cần phân biệt `UNKNOWN` với `NEW`. Vì `CASE` ở view là một phần logic dùng chung, thay đổi view có thể ảnh hưởng nhiều client. Phải quản lý version/migration và kiểm tra khả năng tương thích thay vì chỉ sửa trực tiếp trên production.

## 19. CASE trong SELECT và tính toán số tiền có điều kiện

Ví dụ tính mức phí dựa trên giá trị đơn:

~~~sql
SELECT
    order_id,
    subtotal,
    CASE
        WHEN subtotal >= 500000 THEN 0::numeric
        WHEN subtotal >= 200000 THEN 15000::numeric
        ELSE 30000::numeric
    END AS proposed_shipping_fee
FROM expr_lab_135.orders
ORDER BY order_id;
~~~

Các nhánh đều có kiểu numeric, thuận tiện sử dụng trong phép cộng tiền. Đây là **bảng giá ví dụ**, không thay thế phí vận chuyển thực đã được thỏa thuận, tính theo địa chỉ hoặc ghi nhận kế toán.

### 19.1. CASE để tách dữ liệu bất thường

~~~sql
SELECT
    order_id,
    status,
    paid_at,
    CASE
        WHEN status = 'PAID' AND paid_at IS NULL
            THEN 'Bất thường: đã trả nhưng thiếu thời điểm'
        WHEN status <> 'PAID' AND paid_at IS NOT NULL
            THEN 'Cần kiểm tra trạng thái và thời điểm'
        WHEN status IS NULL
            THEN 'Thiếu trạng thái'
        ELSE 'Không phát hiện vấn đề theo quy tắc mẫu'
    END AS data_quality_note
FROM expr_lab_135.orders
ORDER BY order_id;
~~~

Khi `status IS NULL` và `paid_at IS NOT NULL`, biểu thức `status <> 'PAID'` là UNKNOWN, không TRUE; nhánh `status IS NULL` phía sau mới bắt được trường hợp. Nếu muốn cảnh báo chính xác mọi tổ hợp tình trạng, cần viết thêm điều kiện cho những trường hợp dự kiến.

## 20. Hiệu năng và khả năng sử dụng index

`CASE`, `COALESCE` và `NULLIF` rất tiện, nhưng một biểu thức đặt **trên cột được lọc** có thể làm kế hoạch truy vấn khác so với việc so sánh cột gốc.

### 20.1. Lọc trên cột gốc và lọc trên biểu thức

Giả sử có index:

~~~sql
CREATE INDEX idx_orders_status_135
ON expr_lab_135.orders(status);
~~~

Hai truy vấn có ngữ nghĩa khác nhau:

~~~sql
-- Chỉ chọn status PAID:
SELECT *
FROM expr_lab_135.orders
WHERE status = 'PAID';
~~~

~~~sql
-- Chọn status PAID hoặc NULL khi quy ước NULL = PAID:
SELECT *
FROM expr_lab_135.orders
WHERE COALESCE(status, 'PAID') = 'PAID';
~~~

Truy vấn thứ hai đặt một hàm trên cột `status`. Một index B-tree thông thường trên `status` **không tự bảo đảm** được dùng theo cách giống điều kiện đầu. Nếu cần tập điều kiện bao gồm null, có thể viết:

~~~sql
WHERE status = 'PAID' OR status IS NULL
~~~

hoặc cân nhắc **expression index** khi biểu thức và workload thực sự cần, nhưng quyết định index phải dựa trên thống kê, số hàng và chi phí ghi.

### 20.2. Expression index có thể hữu ích

Ví dụ một hệ thống tìm số điện thoại sau khi chuẩn hóa:

~~~sql
-- Ví dụ học tập; cân nhắc chính sách lưu chuẩn hóa thật.
CREATE INDEX idx_customers_clean_phone_135
ON expr_lab_135.customers (
    NULLIF(btrim(phone), '')
);
~~~

Index biểu thức có thể hỗ trợ một số truy vấn dùng biểu thức tương ứng:

~~~sql
SELECT customer_id, full_name
FROM expr_lab_135.customers
WHERE NULLIF(btrim(phone), '') = '0901111111';
~~~

Trên bảng chỉ có bốn dòng, PostgreSQL có thể chọn sequential scan vì nó rẻ hơn, kể cả có index. **Index tồn tại không có nghĩa planner phải dùng index**. Với dữ liệu lớn, nên dùng `EXPLAIN (ANALYZE, BUFFERS)` trên môi trường an toàn để đo tác động thực tế.

### 20.3. Cân nhắc normalization trước khi tạo expression index

Nếu mọi truy vấn đều phải `btrim`/`NULLIF`/`lower` một cột để tìm kiếm, có thể tốt hơn khi **làm sạch dữ liệu ở thời điểm ghi** hoặc dùng cột chuẩn hóa riêng. Expression index giúp một số workload nhưng tăng chi phí cập nhật index và không giải quyết được mọi lỗi về nguồn dữ liệu.

### 20.4. CASE không tự tăng tốc phép JOIN

~~~sql
SELECT
    o.order_id,
    COALESCE(c.full_name, 'Guest')
FROM expr_lab_135.orders AS o
LEFT JOIN expr_lab_135.customers AS c
    ON c.customer_id = o.customer_id;
~~~

`COALESCE` chỉ quyết định giá trị hiển thị. Kế hoạch JOIN, index trên khóa và số dòng vẫn là yếu tố chính ảnh hưởng tốc độ. Không nên dùng CASE trong điều kiện JOIN để “vá” khóa ngoại sai nếu mục tiêu thực sự là sửa dữ liệu liên kết.

## 21. Những lỗi thường gặp

| Cách hiểu/cách viết sai | Vấn đề | Cách phù hợp |
| --- | --- | --- |
| `CASE WHEN col = NULL` | Phép `= NULL` không TRUE | `WHEN col IS NULL` |
| `CASE col WHEN NULL` | Simple CASE không match NULL như mong đợi | Searched CASE và `IS NULL` |
| Bỏ `ELSE` nhưng kỳ vọng 0 | Không nhánh nào đúng sẽ trả NULL | Thêm `ELSE 0` khi có chủ đích |
| Đặt `WHEN amount >= 100` trước `>= 500` | Nhánh rộng bắt mất nhánh hẹp | Thứ tự ưu tiên rõ ràng |
| Xem `COALESCE(0, 100)` là 100 | 0 khác NULL | Kết quả thật là 0 |
| Xem `COALESCE('', 'N/A')` là N/A | Chuỗi rỗng khác NULL trong PostgreSQL | `COALESCE(NULLIF(value,''), 'N/A')` |
| `COALESCE(amount, 0)` ở mọi nơi | Có thể che dữ liệu tiền chưa xác định | Thống nhất ngữ nghĩa NULL |
| `NULLIF(a,b)` là phép so sánh boolean | Hàm trả a hoặc NULL | Dùng `=` hoặc `IS [NOT] DISTINCT FROM` |
| `100 / 0` rồi bọc CASE tùy ý | Có thể lỗi chia cho 0 ở một giai đoạn đánh giá | Bảo vệ mẫu số `NULLIF(denominator,0)` |
| `COUNT(CASE WHEN cond THEN 1 ELSE 0 END)` | COUNT đếm cả 0 | `SUM(CASE... ELSE 0 END)` hoặc `COUNT(*) FILTER` |
| `AVG(COALESCE(value,0))` khi cần average của giá trị đã biết | Thay đổi mẫu số thống kê | Dùng `AVG(value)` nếu muốn bỏ qua NULL |
| Trộn `numeric` và `text` trong CASE | Có thể lỗi ép kiểu hoặc hợp đồng mơ hồ | Chọn kiểu đầu ra nhất quán |
| Nhầm `NULLIF(phone,'')` xử lý dấu cách | `'   '` không bằng `''` | `NULLIF(btrim(phone), '')` với quy ước rõ |
| Dùng `CASE` cho mọi điều kiện WHERE | Rườm rà, có thể làm khó tối ưu | Dùng boolean trực tiếp khi thích hợp |
| Cho rằng CASE bảo đảm mọi nhánh không chọn không bao giờ được planner tính | Rút gọn hằng/aggregate có ngoại lệ | Thiết kế biểu thức an toàn ngay tại điểm tính |
| Gộp `NULL` với một trạng thái có thật mà không công bố | Làm sai báo cáo và phân loại | Đặt nhãn/rule rõ và kiểm chứng |
| Dùng chuỗi nhãn trong cột tiền của CASE | Khó tổng hợp/sắp xếp kiểu số | Giữ numeric, trình bày nhãn ở cột khác |

## 22. Bài tập thực hành

### Bài 1 — Ánh xạ trạng thái với CASE

Viết truy vấn trả `order_id`, `status` và nhãn:

- `PAID` → “Đã trả”.
- `NEW` → “Chờ xử lý”.
- `CANCELLED` → “Đã hủy”.
- `NULL` → “Chưa nhập”.
- Giá trị khác → “Không xác định”.

**Gợi ý:** dùng searched CASE và đặt `WHEN status IS NULL` tường minh.

~~~sql
SELECT
    order_id,
    CASE
        WHEN status IS NULL THEN 'Chưa nhập'
        WHEN status = 'PAID' THEN 'Đã trả'
        WHEN status = 'NEW' THEN 'Chờ xử lý'
        WHEN status = 'CANCELLED' THEN 'Đã hủy'
        ELSE 'Không xác định'
    END AS label
FROM expr_lab_135.orders
ORDER BY order_id;
~~~

### Bài 2 — Phân nhóm theo tiền

Dùng CASE phân loại `subtotal`:

- Từ 500.000 trở lên: `HIGH`.
- Từ 100.000 đến dưới 500.000: `MEDIUM`.
- Dưới 100.000: `LOW`.

**Câu hỏi:** nếu viết nhánh `>=100000` trước nhánh `>=500000` thì đơn `106` thuộc nhóm nào, và vì sao?

### Bài 3 — Tính tiền với COALESCE

Tính `subtotal - discount_amount + shipping_fee` và thay `NULL` của hai khoản phụ bằng 0. Với đơn `101`, kết quả phải là **90.000**. Với đơn `102`, kết quả là **265.000**.

**Câu hỏi thêm:** trong một hệ thống thanh toán thực, vì sao phải xác nhận rằng `NULL` của `shipping_fee` thật sự có thể tính như 0?

### Bài 4 — Làm sạch số điện thoại

Viết truy vấn trả:

~~~text
phone gốc -> đã btrim -> NULLIF(...,'') -> COALESCE(...,'Chưa cung cấp')
~~~

Với khách `3` và `4`, nhãn cuối phải là **Chưa cung cấp**. Giải thích vì sao chỉ dùng `COALESCE(phone,...)` không đủ.

### Bài 5 — Chia cho 0

Trả giá trị trung bình `subtotal / item_count` cho mỗi đơn. Khi `item_count=0`, phải trả `NULL` thay vì lỗi. Dùng:

~~~sql
SELECT
    order_id,
    subtotal / NULLIF(item_count, 0) AS per_item
FROM expr_lab_135.orders
ORDER BY order_id;
~~~

**Câu hỏi:** vì sao thay `NULL` bằng 0 ở `per_item` có thể làm sai ý nghĩa thống kê?

### Bài 6 — Đếm trạng thái đúng cách

So sánh ba câu:

~~~sql
SELECT
    COUNT(CASE WHEN status = 'PAID' THEN 1 END)
        AS count_by_case,
    SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END)
        AS sum_by_case,
    COUNT(*) FILTER (WHERE status = 'PAID')
        AS count_by_filter
FROM expr_lab_135.orders;
~~~

Cả ba phải trả **3**. Sau đó thử tự phân tích vì sao `COUNT(CASE ... ELSE 0 END)` trả **6**.

### Bài 7 — Trung bình discount với và không COALESCE

Tính `AVG(discount_amount)` và `AVG(COALESCE(discount_amount,0))`. Giải thích sự khác nhau về mẫu số, số dòng dữ liệu thiếu và tại sao không nên chọn công thức chỉ dựa vào việc kết quả trông “đẹp”.

### Bài 8 — Sắp thứ tự ưu tiên

Viết `ORDER BY CASE` để xếp `NEW` trước `PAID`, sau đó `CANCELLED` và cuối cùng là `NULL`. Nếu hai đơn cùng nhóm, xếp theo `ordered_at DESC`.

### Bài 9 — Phân loại payment_state

Trả:

- `PAID` có `paid_at` → “Hợp lệ”.
- `PAID` nhưng `paid_at IS NULL` → “Thiếu thời điểm thanh toán”.
- `status IS NULL` → “Thiếu trạng thái”.
- Còn lại → “Cần thanh toán/đối soát”.

**Gợi ý:** kết hợp `IS NULL` và `AND` trong searched CASE. Nếu dùng nhánh `status <> 'PAID'`, nhớ rằng `NULL` khiến biểu thức là UNKNOWN.

### Bài 10 — CASE trong báo cáo theo nhóm

Nhóm đơn thành `HIGH`/`MEDIUM`/`LOW` theo bài 2, trả:

~~~text
order_band | number_of_orders | subtotal_sum | paid_order_count
~~~

Sử dụng CTE để tính `order_band` rồi `GROUP BY`; dùng `COUNT(*) FILTER (WHERE status='PAID')` hoặc `SUM(CASE...)` cho số đơn đã thanh toán.

### Bài 11 — NULL và phép so sánh

Chạy:

~~~sql
SELECT
    NULL::integer = NULL::integer AS eq_null,
    NULL::integer IS NOT DISTINCT FROM NULL::integer
        AS null_safe_equal,
    NULLIF(0, 0) AS nullified_zero,
    COALESCE(NULLIF(0, 0), 99) AS fallback_after_nullif;
~~~

Giải thích vì sao `eq_null` là `NULL`, `null_safe_equal` là `TRUE`, `nullified_zero` là `NULL` và biểu thức cuối là `99`.

### Bài 12 — Tìm lỗi trong một truy vấn báo cáo

Đoạn sau chứa nhiều vấn đề:

~~~sql
-- Mẫu lỗi để phân tích, không dùng làm báo cáo production:
SELECT
    COUNT(
        CASE WHEN status = 'PAID' THEN 1 ELSE 0 END
    ) AS paid_orders,
    AVG(COALESCE(discount_amount, 0)) AS avg_discount,
    COALESCE(customer_note, 'Không có ghi chú')
        AS note_display
FROM expr_lab_135.orders
GROUP BY customer_note;
~~~

Hãy xác định:

1. Vì sao `paid_orders` không đếm đúng đơn PAID?
2. Khi nào `AVG(COALESCE(discount_amount,0))` hợp lệ, khi nào sai ý nghĩa?
3. Vì sao `customer_note = ''` hoặc `'   '` không được thay bằng nhãn?
4. Tại sao nhóm theo ghi chú gốc có thể tạo nhiều nhóm hiển thị khác nhau dù giao diện trông như “Không có ghi chú”?

### Bài 13 — Thiết kế quy ước NULL trong API

Một API trả:

~~~text
discount_amount
shipping_fee
payment_ratio
customer_phone
~~~

Hãy viết bảng mô tả `NULL` của từng trường có nghĩa là “không có”, “chưa biết”, hay “không áp dụng”. Sau đó quyết định khi nào:

- Giữ nguyên `NULL`.
- Dùng `COALESCE` để hiển thị.
- Dùng `NULLIF` để chuẩn hóa đầu vào.
- Dùng `CASE` để tạo nhãn chi tiết cho người dùng.

Điều quan trọng là **không dùng cùng một quy tắc cho mọi cột**, đặc biệt với tiền và tỷ lệ.

## 23. Thực hành từ đơn giản đến ứng dụng

Khi xây một truy vấn có điều kiện, hãy triển khai theo thứ tự:

1. **Đọc dữ liệu gốc** bằng `SELECT` để xác định những cột có `NULL`, chuỗi rỗng hoặc sentinel.
2. **Viết biểu thức ngắn, kiểm tra từng phần**: `NULLIF(btrim(...),'')`; `COALESCE(...,...)`; `CASE...END`.
3. **Chọn kiểu đầu ra tường minh**: numeric cho tiền và tỷ lệ, text cho nhãn.
4. **Kiểm tra điều kiện biên**: không có hàng, mọi giá trị `NULL`, mẫu số 0, giá trị âm và trạng thái mới.
5. **Chọn vị trí hợp lý của biểu thức**: `SELECT` để hiển thị, `GROUP BY` để phân nhóm, `FILTER`/`CASE` để tổng hợp, `WHERE` để lọc.
6. **Đánh giá ảnh hưởng hiệu năng** nếu biểu thức nằm trên cột dùng làm điều kiện lọc hoặc join của bảng lớn.
7. **Đưa quy ước vào tài liệu/migration** nếu truy vấn tạo view dùng chung hoặc làm logic nghiệp vụ chính thức.

Ví dụ truy vấn tích hợp cuối cùng:

~~~sql
WITH normalized AS (
    SELECT
        o.order_id,
        o.status,
        o.subtotal,
        o.item_count,
        COALESCE(c.full_name, 'Khách vãng lai')
            AS customer_label,
        COALESCE(
            NULLIF(btrim(o.customer_note), ''),
            'Không có ghi chú'
        ) AS note_label,
        o.subtotal
            - COALESCE(o.discount_amount, 0)
            + COALESCE(o.shipping_fee, 0)
            AS estimated_payable
    FROM expr_lab_135.orders AS o
    LEFT JOIN expr_lab_135.customers AS c
        ON c.customer_id = o.customer_id
)
SELECT
    order_id,
    customer_label,
    CASE
        WHEN status = 'PAID' THEN 'Đã thanh toán'
        WHEN status = 'NEW' THEN 'Mới'
        WHEN status = 'CANCELLED' THEN 'Đã hủy'
        WHEN status IS NULL THEN 'Chưa có trạng thái'
        ELSE 'Khác'
    END AS status_label,
    note_label,
    estimated_payable,
    CASE
        WHEN item_count = 0 THEN NULL::numeric
        ELSE estimated_payable / NULLIF(item_count, 0)
    END AS payable_per_item
FROM normalized
ORDER BY order_id;
~~~

Truy vấn này dùng cả ba biểu thức nhưng tách lớp bằng CTE để dễ đọc. Kết quả `payable_per_item` của đơn 104 là `NULL` vì không có món; các trường hợp khác tính được theo giả định tiền của bài. Việc phân lớp truy vấn giúp kiểm tra và bảo trì, **không đảm bảo PostgreSQL luôn materialize CTE hay nhanh hơn**; planner có thể tối ưu/inline CTE tùy phiên bản và tính chất truy vấn.

## 24. Tài liệu tham khảo PostgreSQL

Để xem cú pháp và quy tắc phân giải biểu thức theo đúng PostgreSQL đang dùng:

- [Conditional Expressions — CASE, COALESCE, NULLIF](https://www.postgresql.org/docs/current/functions-conditional.html): cú pháp, xử lý nhánh và những lưu ý về đánh giá biểu thức.
- [Comparison Functions and Operators](https://www.postgresql.org/docs/current/functions-comparison.html): phép so sánh với `NULL`, `IS NULL` và `IS DISTINCT FROM`.
- [Type Conversion — UNION, CASE, and Related Constructs](https://www.postgresql.org/docs/current/typeconv-union-case.html): cách PostgreSQL chọn kiểu chung cho `CASE` và các cấu trúc liên quan.
- [Aggregate Functions](https://www.postgresql.org/docs/current/functions-aggregate.html): `COUNT`, `SUM`, `AVG` và cách chúng xử lý `NULL`.
- [SELECT](https://www.postgresql.org/docs/current/sql-select.html): cách phối hợp biểu thức trong `WHERE`, `GROUP BY`, `HAVING` và `ORDER BY`.

Các liên kết `/docs/current/` chỉ phiên bản tài liệu ổn định hiện hành. Nếu hệ thống sử dụng một major version xác định, nên đọc tài liệu tương ứng với bản đang triển khai.

## 25. Tổng kết

**`CASE` dùng để tạo giá trị theo nhánh điều kiện**: searched CASE xử lý mọi biểu thức boolean, còn simple CASE thích hợp để ánh xạ một biểu thức sang các giá trị bằng nhau. Thứ tự `WHEN` quyết định nhánh được chọn, và `UNKNOWN` do `NULL` không được tính là TRUE. Khi không có nhánh phù hợp, kết quả là `ELSE` hoặc `NULL` nếu bỏ `ELSE`.

**`COALESCE` lấy giá trị đầu tiên khác `NULL`**. Nó hữu ích để tạo nhãn dự phòng hoặc một quy ước tính toán, nhưng không biến **0**, **FALSE** hay **chuỗi rỗng** thành dữ liệu thiếu. **`NULLIF` trả `NULL` khi hai biểu thức bằng nhau**, đặc biệt hữu ích để đổi sentinel thành `NULL` và bảo vệ mẫu số trong phép chia với `NULLIF(denominator,0)`.

Kết hợp ba biểu thức giúp viết truy vấn rõ ràng hơn, tính chỉ số có điều kiện và hiển thị dữ liệu thiếu một cách có chủ đích. Điều quyết định là **hiểu ngữ nghĩa của `NULL`, chọn kiểu dữ liệu đầu ra đúng, kiểm tra các tình huống biên và không che mất dữ liệu chưa biết bằng một giá trị mặc định tùy tiện**. Với các nguyên tắc này, `CASE`, `COALESCE` và `NULLIF` trở thành công cụ nền tảng để viết truy vấn PostgreSQL vừa dễ đọc vừa đáng tin cậy.
