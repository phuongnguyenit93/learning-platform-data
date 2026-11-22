# `IN`, `NOT IN` và danh sách giá trị

Trong SQL, điều kiện **`IN`** kiểm tra xem một giá trị có khớp với **ít nhất một phần tử của một tập giá trị** hay không. Điều kiện **`NOT IN`** kiểm tra phủ định của phép kiểm tra ấy. Đây là những công cụ lọc thường dùng trong `WHERE`, `HAVING`, điều kiện `JOIN` và biểu thức `CASE` khi bài toán có nhiều giá trị được chấp nhận hoặc bị loại.

Ví dụ, thay vì viết `status = 'PAID' OR status = 'SHIPPED'`, có thể viết `status IN ('PAID', 'SHIPPED')`. Nhưng không nên vội suy luận rằng `NOT IN` luôn lấy tất cả các hàng còn lại: trong SQL, **`NULL` khiến kết quả so sánh có thể là `UNKNOWN`**, và `WHERE` chỉ giữ các hàng có điều kiện `TRUE`. Chính đặc điểm này tạo ra một trong những bẫy phổ biến nhất khi dùng `NOT IN` với danh sách hoặc truy vấn con.

Bài học thuộc nhóm **Điều kiện lọc** trong Database SQL, trình bày ý nghĩa, cú pháp, khác biệt với `OR`/`AND`, tương tác với `NULL`, truy vấn con, danh sách động, cách truyền tham số và những điều cần lưu ý khi tối ưu. Ví dụ thực hành dùng **PostgreSQL**; các nguyên tắc logic cơ bản áp dụng cho SQL nói chung, còn cú pháp mảng hoặc cách truyền tham số có thể khác giữa các hệ quản trị.

## 1. Cú pháp căn bản: chọn và loại các giá trị

Cú pháp phổ biến:

```sql
expression IN (value_1, value_2, value_3, ...)

expression NOT IN (value_1, value_2, value_3, ...)
```

Nếu đang truy vấn bảng đơn hàng:

```sql
-- Chọn đơn có trạng thái được thanh toán hoặc đã giao.
SELECT order_id, status
FROM orders
WHERE status IN ('PAID', 'SHIPPED');

-- Loại đơn có trạng thái hủy hoặc chờ xử lý.
SELECT order_id, status
FROM orders
WHERE status NOT IN ('CANCELED', 'PENDING');
```

Trong cả hai trường hợp, SQL so sánh **giá trị biểu thức bên trái** với các giá trị trong danh sách bên phải. Danh sách phải được đặt trong dấu ngoặc đơn. Một phần tử có thể là hằng số, tham số, biểu thức trả về giá trị tương thích hoặc tập giá trị do truy vấn con cung cấp.

### 1.1. `IN` gần với nhiều điều kiện `OR`

Với các toán hạng không chứa `NULL` và cùng ngữ nghĩa so sánh, câu:

```sql
WHERE status IN ('PAID', 'SHIPPED')
```

tương đương về logic với:

```sql
WHERE status = 'PAID'
   OR status = 'SHIPPED'
```

Vì vậy, `IN` thường dễ đọc hơn khi kiểm tra nhiều giá trị của **cùng một biểu thức**. Thêm phần tử vào danh sách không cần lặp lại tên cột.

### 1.2. `NOT IN` gần với nhiều điều kiện `AND`

Với danh sách giá trị xác định:

```sql
WHERE status NOT IN ('CANCELED', 'PENDING')
```

tương đương:

```sql
WHERE status <> 'CANCELED'
  AND status <> 'PENDING'
```

Điểm then chốt là **`AND`**, không phải `OR`. Nếu dùng `OR` trong biểu thức phủ định, gần như mọi trạng thái xác định đều thỏa:

```sql
-- Sai với mục đích loại cả hai trạng thái:
WHERE status <> 'CANCELED'
   OR status <> 'PENDING'
```

Một đơn có trạng thái `CANCELED` vẫn khác `PENDING` nên vế thứ hai TRUE; một đơn `PENDING` vẫn khác `CANCELED` nên vế thứ nhất TRUE. `NOT IN` diễn đạt đúng “không thuộc bất kỳ phần tử bị cấm nào” khi danh sách không làm phát sinh bẫy `NULL`.

## 2. Bộ dữ liệu PostgreSQL tự chứa

Để quan sát chính xác các trường hợp, tạo hai bảng tạm trong một phiên PostgreSQL:

```sql
CREATE TEMP TABLE demo_customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL
);

CREATE TEMP TABLE demo_orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES demo_customers(customer_id),
    status TEXT NULL,
    payment_method TEXT NULL,
    total_amount NUMERIC(12, 2) NOT NULL
        CHECK (total_amount >= 0),
    order_date DATE NOT NULL
);

INSERT INTO demo_customers (customer_id, customer_name)
VALUES
    (1, 'An'),
    (2, 'Binh'),
    (3, 'Chi'),
    (4, 'Dung');

INSERT INTO demo_orders
    (order_id, customer_id, status, payment_method, total_amount, order_date)
VALUES
    (101, 1, 'PAID',     'CARD',     150.00, DATE '2026-05-01'),
    (102, 1, 'PENDING',  'CASH',      50.00, DATE '2026-05-02'),
    (103, 2, 'SHIPPED',  'CARD',     250.00, DATE '2026-05-03'),
    (104, 2, 'CANCELED', NULL,       300.00, DATE '2026-05-04'),
    (105, 3, 'PAID',     'TRANSFER', 100.00, DATE '2026-05-05'),
    (106, 3, NULL,       'CASH',      75.00, DATE '2026-05-06'),
    (107, 4, 'PENDING',  NULL,        25.00, DATE '2026-05-07'),
    (108, 4, 'PAID',     'CASH',       80.00, DATE '2026-05-08');
```

Tóm tắt dữ liệu:

| order_id | Khách | status | payment_method | total_amount |
| ---: | --- | --- | --- | ---: |
| 101 | An | PAID | CARD | 150.00 |
| 102 | An | PENDING | CASH | 50.00 |
| 103 | Binh | SHIPPED | CARD | 250.00 |
| 104 | Binh | CANCELED | NULL | 300.00 |
| 105 | Chi | PAID | TRANSFER | 100.00 |
| 106 | Chi | NULL | CASH | 75.00 |
| 107 | Dung | PENDING | NULL | 25.00 |
| 108 | Dung | PAID | CASH | 80.00 |

Trong bảng minh họa, `NULL` là SQL NULL thật, không phải chuỗi `'NULL'`. Dữ liệu cố ý có một đơn **chưa biết trạng thái** và hai đơn **chưa có phương thức thanh toán**, để thấy khác biệt giữa “không khớp giá trị đã liệt kê” và “không đủ thông tin để kết luận”.

## 3. `IN` với danh sách hằng số

Để lấy đơn thuộc nhóm PAID hoặc SHIPPED:

```sql
SELECT order_id, status, total_amount
FROM demo_orders
WHERE status IN ('PAID', 'SHIPPED')
ORDER BY order_id;
```

Kết quả:

| order_id | status | total_amount |
| ---: | --- | ---: |
| 101 | PAID | 150.00 |
| 103 | SHIPPED | 250.00 |
| 105 | PAID | 100.00 |
| 108 | PAID | 80.00 |

`IN` không làm phát sinh thêm hàng. Nó chỉ quyết định mỗi hàng có thỏa điều kiện lọc hay không. Nếu danh sách lặp lại một phần tử:

```sql
WHERE status IN ('PAID', 'PAID', 'SHIPPED')
```

kết quả xét tính thành viên vẫn giống `IN ('PAID', 'SHIPPED')`. Hai lần xuất hiện `'PAID'` không nhân đôi hàng đơn hàng.

### 3.1. Danh sách có một phần tử

```sql
WHERE status IN ('PAID')
```

tương đương `status = 'PAID'` theo phép so sánh thông thường. Với điều kiện cố định chỉ có một giá trị, dấu `=` thường đơn giản hơn. Tuy nhiên, ứng dụng sinh SQL có thể dùng `IN` để thống nhất với trường hợp một hoặc nhiều giá trị; cần xử lý riêng khi danh sách rỗng.

### 3.2. Danh sách có kiểu dữ liệu tương thích

Với `customer_id` là số nguyên:

```sql
SELECT order_id, customer_id
FROM demo_orders
WHERE customer_id IN (1, 3)
ORDER BY order_id;
```

Các phần tử trong danh sách cần có **kiểu tương thích** với biểu thức cần so sánh. Đối với kiểu số, nên dùng giá trị số hoặc bind tham số đúng kiểu. Đối với ngày, có thể dùng literal có kiểu rõ ràng:

```sql
SELECT order_id, order_date
FROM demo_orders
WHERE order_date IN (DATE '2026-05-01', DATE '2026-05-05')
ORDER BY order_id;
```

Không nên dựa vào việc DBMS tự suy đoán hoặc tự chuyển đổi mọi chuỗi thành số/ngày; khả năng ép kiểu và quy tắc so sánh khác nhau giữa các hệ.

### 3.3. `IN` không kiểm tra chuỗi con

```sql
WHERE status IN ('PAID', 'SHIPPED')
```

kiểm tra **giá trị bằng một phần tử**; nó không có nghĩa status có chứa chữ “PAID” hoặc có tiền tố “SHIP”. Khi cần khớp mẫu văn bản, xem `LIKE`, `ILIKE` (PostgreSQL) hoặc các công cụ tìm kiếm văn bản phù hợp:

```sql
-- Ví dụ khớp tiền tố, một bài toán khác với IN:
WHERE status LIKE 'SHIP%'
```

Tương tự, `IN ('1,2,3')` là **một chuỗi văn bản**, không phải ba phần tử số 1, 2 và 3.

## 4. `NOT IN` với danh sách không chứa NULL

Để loại trạng thái CANCELED và PENDING:

```sql
SELECT order_id, status
FROM demo_orders
WHERE status NOT IN ('CANCELED', 'PENDING')
ORDER BY order_id;
```

Kết quả:

| order_id | status |
| ---: | --- |
| 101 | PAID |
| 103 | SHIPPED |
| 105 | PAID |
| 108 | PAID |

Đơn 106 có status NULL **không xuất hiện**. Điều này không phải vì NULL bằng CANCELED hoặc PENDING, mà vì SQL không thể khẳng định giá trị chưa biết “khác cả hai”. `NOT IN` với một vế trái NULL có thể trả UNKNOWN.

Nếu mục tiêu là “không thuộc nhóm bị loại **và phải có trạng thái xác định**”, có thể làm rõ:

```sql
SELECT order_id, status
FROM demo_orders
WHERE status IS NOT NULL
  AND status NOT IN ('CANCELED', 'PENDING')
ORDER BY order_id;
```

Với dữ liệu mẫu, kết quả giống truy vấn trước, nhưng **ý định xử lý NULL được viết tường minh**, nên dễ hiểu hơn khi đọc quy tắc nghiệp vụ.

Nếu mục tiêu khác, chẳng hạn “trạng thái chưa biết cũng được giữ để rà soát”, phải ghi rõ:

```sql
SELECT order_id, status
FROM demo_orders
WHERE status NOT IN ('CANCELED', 'PENDING')
   OR status IS NULL
ORDER BY order_id;
```

Truy vấn này lấy thêm đơn **106**. Chọn điều kiện nào phải dựa trên yêu cầu nghiệp vụ, không nên coi việc giữ hoặc loại NULL là quyết định thuần cú pháp.

## 5. Logic ba giá trị giải thích mọi bẫy NULL

SQL có ba kết quả logic: **TRUE**, **FALSE** và **UNKNOWN**. Khi so sánh bằng một giá trị NULL:

```sql
SELECT
    'PAID' = 'PAID'    AS certainly_true,   -- TRUE
    'PAID' = 'PENDING' AS certainly_false,  -- FALSE
    'PAID' = NULL     AS unknown_compare,  -- NULL / UNKNOWN
    NULL = NULL       AS also_unknown;     -- NULL / UNKNOWN
```

`WHERE` và `HAVING` chỉ giữ điều kiện TRUE; điều kiện FALSE hoặc UNKNOWN đều bị loại khỏi kết quả. Phủ định UNKNOWN không biến thành TRUE:

| Giá trị điều kiện | `NOT` điều kiện |
| --- | --- |
| TRUE | FALSE |
| FALSE | TRUE |
| UNKNOWN | UNKNOWN |

### 5.1. `IN` có một NULL trong danh sách

```sql
SELECT
    'PAID'    IN ('PAID', NULL) AS paid_match,
    'SHIPPED' IN ('PAID', NULL) AS shipped_match,
    NULL::TEXT IN ('PAID', NULL) AS null_match;
```

Kết quả theo thứ tự là:

- `'PAID' IN ('PAID', NULL)` → **TRUE**, vì đã tìm thấy phần tử khớp; UNKNOWN ở phần tử khác không thay đổi kết luận.
- `'SHIPPED' IN ('PAID', NULL)` → **UNKNOWN**, vì không khớp PAID và chưa thể quyết định so sánh với NULL.
- `NULL IN ('PAID', NULL)` → **UNKNOWN**, vì không có phép so sánh bằng nào có thể xác nhận TRUE.

Do đó, nếu viết:

```sql
SELECT order_id, status
FROM demo_orders
WHERE status IN ('PAID', NULL)
ORDER BY order_id;
```

truy vấn **chỉ lấy các đơn PAID**, không lấy đơn 106 có status NULL. Để chọn cả trạng thái PAID và trạng thái thiếu, cần:

```sql
WHERE status IN ('PAID')
   OR status IS NULL
```

**Một NULL đặt trong danh sách IN không phải cú pháp thay thế cho `IS NULL`.**

### 5.2. `NOT IN` với NULL: danh sách “nhiễm UNKNOWN”

```sql
SELECT
    'PAID' NOT IN ('CANCELED', NULL)     AS paid_not_in,
    'CANCELED' NOT IN ('CANCELED', NULL) AS canceled_not_in,
    NULL::TEXT NOT IN ('CANCELED', NULL) AS null_not_in;
```

Kết quả:

| Biểu thức | Giá trị logic |
| --- | --- |
| `'PAID' NOT IN ('CANCELED', NULL)` | UNKNOWN |
| `'CANCELED' NOT IN ('CANCELED', NULL)` | FALSE |
| `NULL NOT IN ('CANCELED', NULL)` | UNKNOWN |

Lý do: `x NOT IN ('CANCELED', NULL)` gần với `x <> 'CANCELED' AND x <> NULL`. Phép `x <> NULL` cho UNKNOWN. Nếu x đã bằng CANCELED, vế đầu FALSE nên cả AND là FALSE; nếu x không bằng CANCELED, vế đầu TRUE và kết quả AND là UNKNOWN. **Không trường hợp nào cho TRUE**, vì vậy WHERE không giữ hàng nào.

Thử trên bảng:

```sql
SELECT order_id, status
FROM demo_orders
WHERE status NOT IN ('CANCELED', NULL);
-- Không có hàng nào với dữ liệu mẫu.
```

Kết luận quan trọng: **một NULL ở tập giá trị bên phải có thể khiến NOT IN không chọn được cả những giá trị hoàn toàn khác các phần tử đã biết**. Đây là lý do phải kiểm soát NULL trước khi sử dụng danh sách do người khác hoặc truy vấn con cung cấp.

### 5.3. Bảng chân trị khi danh sách có hai phần tử

| Giá trị bên trái | `IN ('PAID','SHIPPED')` | `NOT IN ('PAID','SHIPPED')` | `IN ('PAID',NULL)` | `NOT IN ('PAID',NULL)` |
| --- | --- | --- | --- | --- |
| `'PAID'` | TRUE | FALSE | TRUE | FALSE |
| `'SHIPPED'` | TRUE | FALSE | UNKNOWN | UNKNOWN |
| `'PENDING'` | FALSE | TRUE | UNKNOWN | UNKNOWN |
| NULL | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

Lưu ý: bảng giả định danh sách bên phải **không rỗng**, nên mọi trường hợp có vế trái NULL đều tạo UNKNOWN khi so sánh thông thường. Danh sách rỗng có ngữ nghĩa riêng, xem mục 9.

## 6. `IN` với truy vấn con (subquery)

Danh sách có thể không được viết cố định. Ta có thể dùng một truy vấn con trả về **một cột** làm tập giá trị:

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM demo_customers AS c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM demo_orders AS o
    WHERE o.status = 'PAID'
)
ORDER BY c.customer_id;
```

Truy vấn con trả về customer_id của các đơn PAID: 1, 3, 4. Kết quả cuối gồm **An, Chi và Dung**. Khách An có một đơn PAID, Dung có một đơn PAID, và dù một khách có nhiều đơn PAID, truy vấn ngoài chỉ lấy **một hàng trên mỗi hàng của bảng customers**.

### 6.1. Vì sao `IN (subquery)` không tự nhân bản hàng?

Nếu truy vấn con trả:

```text
customer_id
-----------
1
1
3
4
```

thì kiểm tra `c.customer_id IN (...)` vẫn chỉ trả TRUE/FALSE/UNKNOWN cho từng hàng `c`. **Các giá trị lặp ở truy vấn con không nhân bản hàng của truy vấn ngoài**.

Vì vậy, `DISTINCT` trong truy vấn con thường **không cần thiết để đảm bảo đúng ngữ nghĩa thành viên**:

```sql
-- DISTINCT không cần thiết cho ngữ nghĩa IN ở ví dụ này.
SELECT c.customer_name
FROM demo_customers AS c
WHERE c.customer_id IN (
    SELECT DISTINCT o.customer_id
    FROM demo_orders AS o
    WHERE o.status = 'PAID'
);
```

Bộ tối ưu có thể xử lý loại trùng, semi-join hoặc phương án khác; việc thêm DISTINCT có cải thiện hiệu năng hay không tùy kế hoạch và dữ liệu, không nên coi đó là yêu cầu bắt buộc của IN.

### 6.2. Truy vấn con phải có đúng số cột tương thích

Với một biểu thức đơn bên trái:

```sql
WHERE customer_id IN (
    SELECT customer_id
    FROM demo_orders
)
```

truy vấn con phải cung cấp **một cột** có kiểu tương thích. Viết `SELECT customer_id, status` trong trường hợp này là không phù hợp vì vế trái chỉ có một giá trị, còn vế phải là hai cột. Phép so sánh hàng nhiều cột có cú pháp riêng, sẽ giới thiệu ở mục 10.

### 6.3. `IN` và `EXISTS` có thể diễn đạt cùng yêu cầu

Bài toán “khách có ít nhất một đơn PAID” cũng có thể dùng `EXISTS`:

```sql
SELECT c.customer_id, c.customer_name
FROM demo_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM demo_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
```

`EXISTS` trả TRUE nếu truy vấn con có **ít nhất một hàng**; nó không cần so sánh một biểu thức bên trái với một tập giá trị đầu ra. Ở ví dụ này, cả `IN` và `EXISTS` có cùng kết quả vì khóa khách không NULL và điều kiện tương ứng rõ ràng.

Không nên kết luận vô điều kiện rằng EXISTS luôn nhanh hơn IN hoặc ngược lại. PostgreSQL và các DBMS hiện đại thường có thể biến đổi nhiều truy vấn kiểu này thành dạng **semi-join** hoặc kế hoạch tương đương. Cần quan sát EXPLAIN trên dữ liệu thực tế nếu hiệu năng là vấn đề.

## 7. `NOT IN (subquery)`: nguồn lỗi thường gặp nhất

Giả sử một bảng chứa các trạng thái muốn loại, nhưng cột này lại cho phép NULL:

```sql
CREATE TEMP TABLE demo_blocked_statuses (
    status_code TEXT NULL
);

INSERT INTO demo_blocked_statuses (status_code)
VALUES ('CANCELED'), (NULL);
```

Ta muốn tìm đơn không thuộc trạng thái bị cấm:

```sql
SELECT o.order_id, o.status
FROM demo_orders AS o
WHERE o.status NOT IN (
    SELECT b.status_code
    FROM demo_blocked_statuses AS b
)
ORDER BY o.order_id;
```

Vì truy vấn con trả ra `('CANCELED', NULL)`, **kết quả không có hàng nào**. Tất cả trạng thái khác CANCELED đều gặp UNKNOWN ở phép so sánh với NULL; trạng thái CANCELED cho FALSE; trạng thái NULL cũng không cho TRUE. Đây có thể là sai sót lớn nếu ứng dụng mong đợi danh sách đơn hợp lệ.

### 7.1. Cách 1: loại NULL ở phía truy vấn con

Nếu quy ước nghiệp vụ là **bỏ qua giá trị thiếu trong danh sách trạng thái bị cấm**, có thể viết:

```sql
SELECT o.order_id, o.status
FROM demo_orders AS o
WHERE o.status NOT IN (
    SELECT b.status_code
    FROM demo_blocked_statuses AS b
    WHERE b.status_code IS NOT NULL
)
ORDER BY o.order_id;
```

Điều này bỏ trạng thái NULL của bảng danh sách cấm, nhưng vẫn **không chọn đơn 106 có status NULL ở vế trái**, vì `NULL NOT IN ('CANCELED')` trả UNKNOWN. Nếu cần chỉ xử lý các đơn đã biết trạng thái, nên ghi rõ:

```sql
WHERE o.status IS NOT NULL
  AND o.status NOT IN (
      SELECT b.status_code
      FROM demo_blocked_statuses AS b
      WHERE b.status_code IS NOT NULL
  )
```

Trong trường hợp này, kết quả là các đơn có status PAID, PENDING hoặc SHIPPED, không có CANCELED và không có NULL. Lọc NULL trong truy vấn con **chỉ đúng khi** NULL thực sự không đại diện một trạng thái cần bị cấm theo logic hệ thống.

### 7.2. Cách 2: dùng `NOT EXISTS` để diễn đạt “không có bản ghi cấm khớp”

```sql
SELECT o.order_id, o.status
FROM demo_orders AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM demo_blocked_statuses AS b
    WHERE b.status_code = o.status
)
ORDER BY o.order_id;
```

`NOT EXISTS` kiểm tra liệu có hàng `b` nào mà `b.status_code = o.status` trả **TRUE**. Với so sánh `=`, bản ghi b.status_code NULL không khớp với status nào. Câu trên vì vậy loại CANCELED nhưng **giữ cả đơn 106 có status NULL**.

Điều này không có nghĩa `NOT EXISTS` “tự động sửa đúng mọi vấn đề NULL”; nó diễn đạt **một điều kiện nghiệp vụ khác**. Nếu muốn chỉ lấy các đơn có status đã biết:

```sql
SELECT o.order_id, o.status
FROM demo_orders AS o
WHERE o.status IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM demo_blocked_statuses AS b
      WHERE b.status_code = o.status
  )
ORDER BY o.order_id;
```

Nếu trạng thái NULL cũng được coi là một phần tử **bị cấm** khi danh sách có NULL, PostgreSQL hỗ trợ phép so sánh null-safe:

```sql
SELECT o.order_id, o.status
FROM demo_orders AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM demo_blocked_statuses AS b
    WHERE b.status_code IS NOT DISTINCT FROM o.status
)
ORDER BY o.order_id;
```

Khi đó một hàng `b.status_code IS NULL` sẽ khớp một đơn có `o.status IS NULL`, nên đơn 106 cũng bị loại. `IS NOT DISTINCT FROM` coi hai NULL là tương ứng cho phép so sánh này, khác với toán tử `=` thông thường.

### 7.3. Bảng lựa chọn `NOT IN` và `NOT EXISTS`

| Mục tiêu | Cách diễn đạt có thể dùng |
| --- | --- |
| Loại một danh sách **hằng số chắc chắn không NULL**; trạng thái thiếu không được lấy | `status NOT IN ('CANCELED', 'PENDING')` |
| Loại danh sách cấm lấy từ bảng có thể có NULL; **bỏ qua bản ghi cấm NULL** và chỉ nhận trạng thái nguồn đã biết | `status IS NOT NULL AND status NOT IN (SELECT code ... WHERE code IS NOT NULL)` |
| Chỉ loại những dòng có **bản ghi cấm khớp theo dấu `=`**; cho phép dòng nguồn có NULL tồn tại | `NOT EXISTS (SELECT 1 ... WHERE b.code = o.status)` |
| Xem hai NULL là tương ứng khi đối chiếu cấm | `NOT EXISTS (... WHERE b.code IS NOT DISTINCT FROM o.status)` |
| Muốn mọi trường hợp chưa biết được đánh dấu riêng thay vì lẫn vào danh sách hợp lệ | Xử lý `IS NULL` bằng nhánh nghiệp vụ riêng (`CASE`, `WHERE`, trạng thái đối soát) |

**Trước khi đổi `NOT IN` thành `NOT EXISTS`, hãy quyết định rõ xử lý NULL ở cả hai phía**. Hai cấu trúc không tương đương trong mọi trường hợp.

## 8. Quan hệ với `AND`, `OR` và dấu ngoặc

`IN` là một điều kiện có thể kết hợp với nhiều điều kiện khác:

```sql
SELECT order_id, status, total_amount
FROM demo_orders
WHERE status IN ('PAID', 'SHIPPED')
  AND total_amount >= 100
ORDER BY order_id;
```

Kết quả gồm đơn 101, 103, 105. Đơn 108 có status PAID nhưng tổng tiền 80 nên bị loại.

### 8.1. Tránh sai độ ưu tiên của AND và OR

Trong SQL, `AND` có độ ưu tiên cao hơn `OR`. Câu:

```sql
WHERE status IN ('PAID', 'SHIPPED')
  AND total_amount >= 100
   OR customer_id = 2
```

được hiểu như:

```sql
WHERE (
    status IN ('PAID', 'SHIPPED')
    AND total_amount >= 100
)
OR customer_id = 2
```

Như vậy mọi đơn của khách 2 có thể được lấy, **kể cả đơn CANCELED 104**. Nếu ý định là chỉ chọn PAID/SHIPPED và đồng thời tổng tiền đủ lớn **hoặc** thuộc khách 2, cần:

```sql
WHERE status IN ('PAID', 'SHIPPED')
  AND (total_amount >= 100 OR customer_id = 2)
```

Hai câu có kết quả khác nhau. Đừng dựa vào cách xuống dòng hoặc căn lề để thay cho dấu ngoặc xác định nhóm điều kiện.

### 8.2. Kết hợp nhiều `IN` ở các cột khác nhau

```sql
SELECT order_id, status, payment_method
FROM demo_orders
WHERE status IN ('PAID', 'SHIPPED')
  AND payment_method IN ('CARD', 'TRANSFER')
ORDER BY order_id;
```

Điều kiện này yêu cầu **cả hai**: trạng thái thuộc nhóm cho phép và phương thức thanh toán thuộc nhóm cho phép. Với dữ liệu mẫu, đơn 101, 103, 105 khớp; đơn 108 PAID nhưng CASH nên bị loại.

Một điều kiện `IN` với `payment_method` NULL trả UNKNOWN nếu không có khớp xác định; trong biểu thức AND, giá trị TRUE của trạng thái kết hợp với UNKNOWN của phương thức cho UNKNOWN, nên hàng bị WHERE loại.

## 9. Danh sách rỗng: không thể viết `IN ()` trong PostgreSQL

Một bộ lọc động có thể nhận tập trạng thái người dùng chọn. Ví dụ họ chọn ba trạng thái, một trạng thái hoặc **không chọn trạng thái nào**.

Trong PostgreSQL và nhiều DBMS:

```sql
-- Sai cú pháp trong PostgreSQL:
SELECT order_id FROM demo_orders WHERE status IN ();

-- Cũng sai cú pháp:
SELECT order_id FROM demo_orders WHERE status NOT IN ();
```

Không được ghép chuỗi thành `IN ()` rồi gửi lên database. Với danh sách rỗng, ứng dụng phải định nghĩa ý nghĩa mong muốn:

- **“Không chọn giá trị nào” nghĩa là không lấy bản ghi nào:** dùng điều kiện luôn FALSE cho `IN`, chẳng hạn `WHERE FALSE`.
- **“Không có giá trị bị cấm” nghĩa là không loại vì danh sách cấm:** dùng điều kiện luôn TRUE cho `NOT IN`, chẳng hạn bỏ điều kiện lọc ấy.
- **“Không chọn bộ lọc” nghĩa là lấy toàn bộ các trạng thái:** bỏ điều kiện `IN` chứ không phải coi nó là tập rỗng. Đây là một chính sách UI/API khác.

Về mặt logic tập hợp, `x IN` tập rỗng cho FALSE còn `x NOT IN` tập rỗng cho TRUE, **kể cả khi x là NULL**, vì không tồn tại phần tử nào để so sánh. Nhưng cú pháp `IN ()` không được PostgreSQL chấp nhận; cần thể hiện bằng SQL hợp lệ.

### 9.1. Truy vấn con trả không hàng vẫn hợp lệ

```sql
SELECT order_id
FROM demo_orders
WHERE customer_id IN (
    SELECT customer_id
    FROM demo_customers
    WHERE FALSE
);
-- Không có kết quả: truy vấn con trả tập rỗng.
```

Khác với `IN ()`, truy vấn con có thể trả **0 hàng** mà vẫn hợp lệ. `NOT IN (subquery trả tập rỗng)` cho TRUE với mọi hàng ở ngoài. Đây là tình huống cần phân biệt với danh sách **chứa NULL**; một tập rỗng không có giá trị NULL nào để gây UNKNOWN.

### 9.2. Mảng và `ANY`/`ALL` trong PostgreSQL

PostgreSQL cho phép một cách diễn đạt tiện khi danh sách do ứng dụng truyền có số phần tử thay đổi:

```sql
-- Tìm trạng thái thuộc mảng.
SELECT order_id, status
FROM demo_orders
WHERE status = ANY (ARRAY['PAID', 'SHIPPED']::TEXT[])
ORDER BY order_id;

-- Loại trạng thái thuộc mảng.
SELECT order_id, status
FROM demo_orders
WHERE status <> ALL (ARRAY['CANCELED', 'PENDING']::TEXT[])
ORDER BY order_id;
```

`status = ANY(array)` có ngữ nghĩa gần với `status IN (...)`; `status <> ALL(array)` gần với `status NOT IN (...)` đối với so sánh bằng/khác. Chúng vẫn tuân theo **logic NULL**; nếu mảng có phần tử NULL, phép loại bằng `<> ALL` có thể cho UNKNOWN giống bẫy NOT IN.

Mảng rỗng có thể được truyền hợp lệ:

```sql
SELECT
    'PAID' = ANY ('{}'::TEXT[])   AS in_empty_array,     -- FALSE
    'PAID' <> ALL ('{}'::TEXT[])  AS not_in_empty_array; -- TRUE
```

Điều này cũng đúng với NULL bên trái khi mảng rỗng, vì không có phần tử nào cần so sánh. Một **mảng SQL NULL** (chẳng hạn `NULL::TEXT[]`) khác với một **mảng rỗng** (`'{}'::TEXT[]`): không nên đồng nhất hai tình huống.

`ANY`/`ALL` với mảng là tính năng PostgreSQL hữu ích cho tham số hóa. Các DBMS khác có cú pháp bảng giá trị, tham số bảng (*table-valued parameters*) hoặc kỹ thuật khác.

## 10. `IN` với nhiều cột: so sánh hàng (row-value)

Không phải mọi điều kiện IN chỉ có một cột. PostgreSQL hỗ trợ so sánh **bộ giá trị**:

```sql
SELECT order_id, customer_id, status
FROM demo_orders
WHERE (customer_id, status) IN (
    (1, 'PAID'),
    (3, 'PAID')
)
ORDER BY order_id;
```

Kết quả là đơn 101 (khách 1, PAID) và đơn 105 (khách 3, PAID). Điều kiện này kiểm tra **cặp (customer_id, status)**, không phải kiểm tra độc lập `customer_id IN (1, 3) AND status = 'PAID'` theo mọi tổ hợp chỉ khi các cặp được liệt kê vốn bao phủ toàn bộ tổ hợp. Ví dụ:

```sql
WHERE (customer_id, status) IN (
    (1, 'PAID'),
    (2, 'SHIPPED')
)
```

chỉ chọn hai tổ hợp được liệt kê. Nếu tách thành `customer_id IN (1, 2) AND status IN ('PAID', 'SHIPPED')`, truy vấn có thể chọn **bốn tổ hợp** thay vì hai khi dữ liệu tồn tại.

### 10.1. Row-value và NULL

Phép so sánh hai hàng xét các thành phần. Nếu một cặp cột đã có sự khác biệt chắc chắn, cả hai hàng không bằng nhau; nếu không có sự khác biệt chắc chắn nhưng còn thành phần NULL, kết quả so sánh bằng có thể UNKNOWN.

```sql
SELECT
    ROW(1, NULL::TEXT) = ROW(1, NULL::TEXT)
        AS both_unknown,           -- NULL / UNKNOWN
    ROW(1, NULL::TEXT) = ROW(2, NULL::TEXT)
        AS definitely_different;   -- FALSE
```

Vì vậy bẫy NULL trong row-wise `IN`/`NOT IN` cũng cần xét tới, nhưng không thể đơn giản phát biểu rằng “bất kỳ NULL ở bất kỳ thành phần nào cũng làm mọi hàng đều UNKNOWN”: các cột khác nhau rõ ràng có thể đủ để kết luận FALSE cho so sánh từng cặp.

Nếu bài toán cần so sánh nhiều thuộc tính đồng thời và coi NULL theo quy tắc cụ thể, có thể dùng `IS [NOT] DISTINCT FROM` từng cột hoặc xây dựng điều kiện EXISTS rõ nghĩa.

## 11. Tham số hóa danh sách giá trị an toàn

Danh sách IN trong ứng dụng thường đến từ bộ lọc nhiều lựa chọn trên giao diện hoặc từ một danh sách ID nghiệp vụ. Không nên nối trực tiếp nội dung người dùng vào chuỗi SQL:

```text
Không nên:
sql = "SELECT ... WHERE status IN (" + userInput + ")"
```

Cách này có nguy cơ **SQL injection**, lỗi quote, lỗi kiểu dữ liệu và lỗi cú pháp khi danh sách rỗng. Chỉ nên đưa giá trị vào truy vấn thông qua **tham số được binding theo kiểu phù hợp**.

### 11.1. Placeholder riêng cho từng giá trị

Với danh sách có đúng ba phần tử:

```sql
SELECT order_id, status
FROM demo_orders
WHERE status IN (?, ?, ?);
```

Trong JDBC, có thể lần lượt gán ba tham số bằng `PreparedStatement.setString(...)`. Mỗi dấu `?` đại diện **một giá trị**, không phải cả một danh sách SQL.

Do đó:

```sql
WHERE status IN (?)
```

và binding chuỗi `'PAID,SHIPPED'` sẽ so sánh status với **một chuỗi duy nhất** `PAID,SHIPPED`, chứ không tự tách thành hai giá trị. Kết quả sẽ khác với `IN ('PAID', 'SHIPPED')`.

Với danh sách dài biến động, ứng dụng có thể tạo **số lượng placeholder** tương ứng từ số phần tử đã được xác định, rồi binding từng giá trị; cần xử lý **danh sách rỗng** theo chính sách đã nêu. Đừng cho phép nội dung người dùng kiểm soát trực tiếp cú pháp SQL, tên bảng/cột hoặc dấu quote.

### 11.2. Ví dụ `PREPARE` cho mảng PostgreSQL

Trong PostgreSQL, có thể giữ một tham số mảng có kiểu rõ ràng:

```sql
PREPARE find_orders_by_status(TEXT[]) AS
SELECT order_id, status
FROM demo_orders
WHERE status = ANY ($1)
ORDER BY order_id;

EXECUTE find_orders_by_status(
    ARRAY['PAID', 'SHIPPED']::TEXT[]
);

-- Mảng rỗng: không có đơn nào khớp.
EXECUTE find_orders_by_status('{}'::TEXT[]);
```

Ở tầng Java/JDBC với driver PostgreSQL, có thể tạo SQL array và gán vào `PreparedStatement` qua các API như `Connection.createArrayOf` và `PreparedStatement.setArray` nếu driver và kiểu dữ liệu hỗ trợ. Ví dụ nguyên tắc:

```java
String sql = """
    SELECT order_id, status
    FROM demo_orders
    WHERE status = ANY (?)
    ORDER BY order_id
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    Array statuses = connection.createArrayOf(
        "text", new String[] {"PAID", "SHIPPED"}
    );
    try {
        ps.setArray(1, statuses);
        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                int orderId = rs.getInt("order_id");
                String status = rs.getString("status");
                // Ánh xạ kết quả vào đối tượng cần dùng.
            }
        }
    } finally {
        statuses.free();
    }
}
```

Đoạn Java minh họa giả định có `Connection connection` và các import `java.sql.Array`, `PreparedStatement`, `ResultSet`. Đây không phải ứng dụng chạy độc lập; hãy dùng khả năng driver thực tế, thư viện quản lý kết nối và quy tắc lỗi của dự án. Mảng PostgreSQL hỗ trợ danh sách có độ dài bất kỳ, kể cả rỗng, nhưng vẫn cần xác định **NULL trong mảng và NULL của cột** được xử lý thế nào.

### 11.3. Danh sách ID lớn

Khi người dùng lọc theo hàng nghìn hoặc hàng chục nghìn ID, một danh sách IN quá dài có thể gây tốn công phân tích cú pháp, kích thước truy vấn lớn, giới hạn số tham số hoặc kế hoạch không ổn định. Tùy hệ thống, có thể cân nhắc:

- Mảng tham số và `= ANY(...)` trong PostgreSQL;
- Bảng tạm chứa ID cùng kiểu dữ liệu và ràng buộc/chỉ mục phù hợp;
- Một bảng staging hoặc bảng liên kết nếu danh sách là dữ liệu nghiệp vụ thực sự cần lưu;
- `JOIN`, `EXISTS` hoặc semi-join trên một tập ID đã được kiểm soát;
- Giới hạn số ID đầu vào ở API nếu nghiệp vụ cho phép.

**Không có một ngưỡng cố định** mà tại đó IN phải đổi thành JOIN. Chi phí phụ thuộc số phần tử, số hàng bảng, độ chọn lọc, thống kê, cách binding và chỉ mục thực tế.

## 12. `IN` khác `JOIN` khi tập giá trị có phần tử trùng

Giả sử danh sách trạng thái mong muốn có hai hàng đều là `PAID`:

```sql
WITH selected_statuses(status) AS (
    VALUES ('PAID'), ('PAID')
)
SELECT o.order_id, o.status
FROM demo_orders AS o
JOIN selected_statuses AS s
    ON s.status = o.status
ORDER BY o.order_id;
```

Mỗi đơn PAID sẽ được ghép với **hai hàng** selected_statuses, nên xuất hiện hai lần trong kết quả JOIN. Ngược lại:

```sql
SELECT order_id, status
FROM demo_orders
WHERE status IN ('PAID', 'PAID')
ORDER BY order_id;
```

mỗi đơn PAID chỉ xuất hiện **một lần** theo số hàng gốc. Điều kiện IN là **kiểm tra thành viên**, còn JOIN là **kết hợp các hàng**; chúng có thể khác số dòng nếu nguồn JOIN có trùng.

Nếu dùng bảng danh sách để lọc, có thể chọn `EXISTS` để giữ ngữ nghĩa không nhân bản hàng, hoặc làm tập khóa duy nhất bằng ràng buộc hay bước chuẩn hóa được kiểm soát. Không dùng `DISTINCT` tùy tiện ở kết quả JOIN để che lỗi quan hệ mà chưa hiểu độ hạt dữ liệu.

## 13. Hiệu năng và kế hoạch thực thi

Một câu truy vấn:

```sql
SELECT order_id, status, total_amount
FROM demo_orders
WHERE status IN ('PAID', 'SHIPPED');
```

có thể được thực thi bằng quét bảng, quét chỉ mục, bitmap index scan hoặc cách tối ưu khác tùy kích thước và phân bố dữ liệu. Trong PostgreSQL, nhiều điều kiện IN có thể được diễn đạt hoặc tối ưu thông qua **ScalarArrayOpExpr** và các phép toán chỉ mục tương đương; không nên từ cú pháp IN suy ra một kế hoạch vật lý cố định.

### 13.1. Chỉ mục trên cột được lọc

Với bảng lớn và điều kiện đủ chọn lọc, chỉ mục có thể hữu ích:

```sql
CREATE INDEX idx_demo_orders_status
ON demo_orders (status);
```

DBMS vẫn có thể chọn **Seq Scan** nếu bảng rất nhỏ (như dữ liệu mẫu tám dòng), nếu phần lớn hàng thỏa điều kiện hoặc nếu chi phí dùng chỉ mục cao hơn. Tạo chỉ mục làm tăng chi phí lưu trữ và duy trì khi INSERT/UPDATE/DELETE, nên không tạo chỉ mục chỉ vì nhìn thấy IN.

### 13.2. `NOT IN` có thể kém chọn lọc

Trong bảng có nhiều trạng thái khác CANCELED, điều kiện:

```sql
WHERE status NOT IN ('CANCELED')
```

có thể chọn phần lớn hàng. Một chỉ mục trên status không nhất thiết rẻ hơn việc quét toàn bộ bảng. Nếu ứng dụng thường lấy một tập trạng thái nhỏ được phép, `IN` có thể thể hiện rõ yêu cầu và có tính chọn lọc khác, nhưng **chỉ đổi khi đúng ngữ nghĩa nghiệp vụ**, không thay `NOT IN` bằng `IN` vì mục tiêu tối ưu đơn thuần.

### 13.3. So sánh kế hoạch bằng EXPLAIN

```sql
EXPLAIN
SELECT order_id, status, total_amount
FROM demo_orders
WHERE status IN ('PAID', 'SHIPPED')
ORDER BY order_id;
```

Trong môi trường dữ liệu đại diện, có thể quan sát thực thi:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, status, total_amount
FROM demo_orders
WHERE status IN ('PAID', 'SHIPPED')
ORDER BY order_id;
```

`EXPLAIN` thông thường cho kế hoạch dự kiến; `EXPLAIN ANALYZE` **thực sự chạy truy vấn** và cung cấp số liệu runtime. Khi đọc cần xem kiểu scan, số hàng ước lượng và thực tế, điều kiện lọc nằm ở đâu, buffer/I/O và thời gian. Với SELECT trên bảng demo nhỏ, kết quả chỉ mang tính thử nghiệm cơ chế, không đủ kết luận cho dữ liệu sản xuất.

Đối với `IN (subquery)` và `EXISTS`, bộ tối ưu có thể tạo semi-join, hash, nested-loop hoặc các biến thể khác. Với `NOT IN`, vấn đề NULL làm phép biến đổi thành anti-join không đơn giản trong mọi trường hợp; phải bảo toàn **logic ba giá trị**. Vì vậy, nên lựa chọn cấu trúc **đúng ngữ nghĩa trước**, sau đó dùng kế hoạch thực tế để tối ưu.

## 14. Những sai lầm thường gặp

| Sai lầm / giả định | Vì sao có vấn đề? | Cách xử lý |
| --- | --- | --- |
| `IN ('PAID', 'SHIPPED')` được hiểu là tìm chuỗi chứa “PAID” | IN so sánh giá trị bằng nhau, không tìm chuỗi con | Dùng LIKE hoặc công cụ tìm kiếm văn bản khi cần mẫu |
| `NOT IN ('A','B')` tương đương `<> 'A' OR <> 'B'` | OR gần như luôn TRUE với giá trị xác định | Dùng AND trong biểu thức phủ định, hoặc NOT IN |
| `IN ('PAID', NULL)` chọn hàng có status NULL | `NULL = NULL` là UNKNOWN | Thêm `OR status IS NULL` nếu cần |
| `NOT IN ('CANCELED', NULL)` chọn các trạng thái còn lại | NULL ở danh sách có thể làm điều kiện UNKNOWN | Không đưa NULL không chủ ý vào danh sách; xem NOT EXISTS |
| `NOT IN (SELECT code ...)` an toàn khi code nullable | Một NULL do subquery trả có thể loại hết kết quả | Xử lý NULL trong subquery hoặc dùng NOT EXISTS với ý nghĩa rõ |
| Thay NOT IN bằng NOT EXISTS là luôn tương đương | NULL ở cột trái có thể khiến hai cách trả kết quả khác | Quy định hành vi cho NULL ở cả hai phía |
| `IN ()` là cách hợp lệ khi danh sách rỗng | PostgreSQL báo lỗi cú pháp | Xử lý rỗng ở ứng dụng, hoặc dùng mảng/quan hệ rỗng |
| `IN (?)` với chuỗi `'1,2,3'` là ba phần tử | Placeholder là **một giá trị** | Bind từng phần tử hoặc dùng tham số mảng |
| Ghép nguyên danh sách do người dùng nhập vào SQL | Có nguy cơ SQL injection và sai kiểu | Dùng prepared statement và binding |
| JOIN với bảng danh sách luôn giống IN | Tập giá trị trùng có thể nhân số dòng JOIN | Dùng EXISTS/IN hoặc bảo đảm tập khóa duy nhất |
| IN luôn chạy nhanh hơn OR hay EXISTS | Kế hoạch phụ thuộc thống kê, chỉ mục và kích thước | Đọc EXPLAIN, đo trên dữ liệu đại diện |
| Danh sách có 1, 2, 3 là một giá trị chuỗi `'1,2,3'` | Kiểu và số phần tử khác nhau | Dùng `IN (1, 2, 3)` với kiểu số phù hợp |
| Dùng IN để kiểm tra cùng lúc mọi tổ hợp hai cột | `row IN ((a,b),(c,d))` khác hai điều kiện IN độc lập | Chọn điều kiện theo các cặp hợp lệ thực sự |

## 15. Bài tập thực hành

Các bài tập dùng bảng `demo_customers`, `demo_orders` và khi cần, `demo_blocked_statuses` trong các mục trước. Hãy **dự đoán kết quả trước khi chạy** để kiểm tra cách hiểu ngữ nghĩa.

### Bài 1 — Chọn hai trạng thái

Viết truy vấn lấy `order_id`, `status`, `total_amount` cho các đơn PAID hoặc SHIPPED, sắp theo `order_id`. Sau đó viết lại bằng hai phép so sánh `=` kết hợp `OR`. Kết quả có giống nhau khi status của một hàng là NULL không?

Gợi ý: với danh sách xác định không NULL, hai cách có cùng ngữ nghĩa ba giá trị. Hàng status NULL không được WHERE giữ.

### Bài 2 — Loại nhiều trạng thái

Lấy những đơn không thuộc CANCELED hoặc PENDING, và chỉ chấp nhận đơn đã biết trạng thái. So sánh:

```sql
WHERE status NOT IN ('CANCELED', 'PENDING')
```

với:

```sql
WHERE status <> 'CANCELED'
  AND status <> 'PENDING'
  AND status IS NOT NULL
```

Điểm khác nhau về **ý định biểu đạt** khi thêm `IS NOT NULL` là gì? Hãy giải thích đơn 106.

### Bài 3 — Dòng NULL bị bỏ sót

Vì sao:

```sql
WHERE status IN ('PAID', NULL)
```

không lấy đơn 106 có status NULL? Viết lại điều kiện cho phép cả PAID và NULL mà không đưa NULL vào danh sách IN.

### Bài 4 — Bẫy `NOT IN` của truy vấn con

Thử:

```sql
SELECT order_id
FROM demo_orders
WHERE status NOT IN (
    SELECT status_code
    FROM demo_blocked_statuses
);
```

Giải thích tại sao không có hàng nào khi bảng cấm chứa `('CANCELED', NULL)`. Sau đó viết hai truy vấn:

1. Bỏ qua NULL ở bảng cấm, đồng thời **loại** những đơn có status NULL.
2. Chỉ loại khi có một hàng cấm khớp theo phép `=`, vì vậy **giữ** đơn có status NULL.

Gợi ý: cách 1 dùng điều kiện `IS NOT NULL` hai phía hoặc dạng tương đương; cách 2 dùng `NOT EXISTS`.

### Bài 5 — Khách đã thanh toán

Lấy danh sách khách có ít nhất một đơn PAID bằng `IN (SELECT customer_id ...)`. Viết lại bằng `EXISTS` có tương quan theo customer_id. Giải thích vì sao nếu một khách có ba đơn PAID, truy vấn ngoài không tự lặp khách ba lần.

### Bài 6 — Danh sách rỗng trong API

Một API nhận danh sách trạng thái cần lọc. Hãy mô tả rõ hành vi khi:

1. Danh sách gồm `['PAID', 'SHIPPED']`.
2. Danh sách gồm một giá trị `['PAID']`.
3. Danh sách rỗng `[]`.
4. Tham số **không được gửi**.

Không mặc định 3 và 4 giống nhau: điều này phụ thuộc hợp đồng API. Hãy viết cách tạo SQL hợp lệ trong trường hợp 3, hoặc dùng `= ANY` với mảng rỗng của PostgreSQL.

### Bài 7 — Kiểm tra hai cột theo từng cặp

Viết điều kiện chọn đúng các tổ hợp `(customer_id, status)` sau: `(1, 'PAID')` và `(2, 'SHIPPED')`. Vì sao tách thành `customer_id IN (1,2) AND status IN ('PAID','SHIPPED')` có thể lấy nhiều tổ hợp hơn dự kiến?

### Bài 8 — Danh sách trùng và JOIN

Cho bảng danh sách có hai hàng cùng giá trị PAID. So sánh số dòng khi dùng:

```sql
WHERE status IN ('PAID', 'PAID')
```

và khi JOIN bảng đơn hàng với bảng hai hàng PAID. Cơ chế nào nhân bản bản ghi? Nếu cần lọc bằng bảng danh sách nhưng vẫn giữ một lần mỗi đơn, hãy đề xuất dùng EXISTS hoặc ràng buộc duy nhất cho danh sách.

### Bài 9 — Tham số hóa an toàn

Một người dùng nhập chuỗi `"PAID,SHIPPED"` ở bộ lọc. Vì sao bind nguyên chuỗi đó vào `IN (?)` không tương đương với hai tham số riêng? Hãy nêu cách dùng các placeholder hoặc `= ANY` trên PostgreSQL, đồng thời giải thích cách tránh xây dựng SQL bằng nối chuỗi không kiểm soát.

## 16. Tóm tắt: hiểu tập giá trị trước khi chọn toán tử

Có thể nhớ `IN` và `NOT IN` theo sơ đồ:

```text
Biểu thức x và tập giá trị S
        |
        +-- Có phần tử s trong S mà x = s là TRUE?
        |        +-- Có  -> x IN S = TRUE
        |        +-- Không
        |
        +-- Có phép so sánh x = s cho UNKNOWN?
        |        +-- Có  -> x IN S = UNKNOWN
        |        +-- Không -> x IN S = FALSE
        |
        +-- x NOT IN S = NOT (x IN S)
                 TRUE -> FALSE
                 FALSE -> TRUE
                 UNKNOWN -> UNKNOWN
```

Sơ đồ này cũng giải thích trường hợp tập rỗng: không có phần tử khớp và không có phép so sánh UNKNOWN, nên `IN` là FALSE còn `NOT IN` là TRUE. Cần nhớ rằng trong PostgreSQL **cú pháp `IN ()` không hợp lệ**, dù quan hệ rỗng hoặc mảng rỗng vẫn có ý nghĩa logic đó.

**Nguyên tắc áp dụng:** dùng `IN` khi muốn kiểm tra một giá trị thuộc tập cho phép; dùng `NOT IN` khi tập cấm **không chứa NULL theo quy tắc có kiểm soát**. Với tập giá trị lấy từ bảng hoặc dữ liệu ngoài, phải xét NULL ở cả hai phía và cân nhắc `EXISTS`/`NOT EXISTS` đúng nghĩa. Khi danh sách do ứng dụng tạo, luôn xử lý trường hợp rỗng và binding từng giá trị/mảng theo kiểu dữ liệu. Sau khi ngữ nghĩa đã đúng, mới đo kế hoạch thực thi để quyết định cách tối ưu.
