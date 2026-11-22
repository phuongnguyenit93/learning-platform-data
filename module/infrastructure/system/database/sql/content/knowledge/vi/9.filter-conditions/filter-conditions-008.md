# Lọc cột có NULL theo yêu cầu nghiệp vụ

Một đơn hàng chưa có ngày giao hàng có thể là đơn **chưa giao**, đơn **đã hủy**, hoặc đơn đã giao nhưng hệ thống **chưa ghi nhận ngày giao**. Tương tự, cột số tiền bằng `0` khác với cột số tiền có giá trị `NULL`: số 0 là một giá trị xác định, còn `NULL` biểu thị chưa có giá trị xác định trong ngữ cảnh dữ liệu.

Khi lọc dữ liệu SQL, câu hỏi quan trọng không chỉ là “cột này có `NULL` không?” mà còn là **“`NULL` của cột này có ý nghĩa nghiệp vụ gì, và nhóm bản ghi nào phải được giữ lại?”**. Bài học hướng dẫn chuyển các yêu cầu như “đơn đã thanh toán nhưng chưa gửi”, “đơn chưa có giá”, “đơn chưa được duyệt” và “đơn không có thông tin xác minh” thành điều kiện `WHERE` đúng với logic `NULL`.

Ví dụ thực hành dùng **PostgreSQL** và một bộ dữ liệu tạm. Những nguyên tắc chung như `IS NULL`, `IS NOT NULL` và logic ba giá trị cũng hữu ích trên các hệ quản trị SQL khác; các khác biệt cú pháp được giải thích ở phần riêng.

## 1. Phân biệt “không có giá trị” và một giá trị cụ thể

SQL dùng dấu hiệu đặc biệt **`NULL`** để biểu diễn sự vắng mặt của một giá trị SQL. Tùy quy tắc dữ liệu, điều này có thể có nghĩa “chưa biết”, “chưa nhập”, “không áp dụng” hoặc “chưa xảy ra”. `NULL` **không mặc định** có một nghĩa nghiệp vụ duy nhất.

| Giá trị trong cột | Ý nghĩa ở mức SQL | Ví dụ ý nghĩa nghiệp vụ |
| --- | --- | --- |
| `NULL` | Không có giá trị xác định trong cột | Chưa ghi nhận ngày gửi hàng |
| `0` | Có giá trị số bằng không | Phí vận chuyển bằng 0 đồng |
| `''` | Có giá trị chuỗi rỗng trong PostgreSQL | Người nhập để trống ô mã |
| `'N/A'` | Chuỗi ký tự gồm ba ký tự | Mã quy ước “không áp dụng” của hệ thống cũ |
| `FALSE` | Có giá trị boolean là sai | Đã đánh giá và kết luận “không đạt” |
| `DATE '2026-03-01'` | Có một giá trị ngày cụ thể | Đã ghi nhận ngày gửi là 01/03/2026 |

Ví dụ, nếu cột `reviewed` có ba trạng thái `TRUE`, `FALSE` và `NULL`, một thiết kế có thể định nghĩa:

- `TRUE`: nhân viên đã duyệt và kết quả là đạt.
- `FALSE`: nhân viên đã duyệt và kết quả là không đạt.
- `NULL`: chưa có kết quả duyệt.

Theo hợp đồng dữ liệu này, yêu cầu “chưa có kết quả duyệt” chỉ lấy `NULL`, còn yêu cầu “không đạt hoặc chưa có kết quả” lấy cả `FALSE` và `NULL`. Hai yêu cầu phải dùng điều kiện khác nhau.

**Trước khi viết `WHERE`, hãy xác định nghĩa của `NULL` cho từng cột**, kể cả khả năng dữ liệu có mã giả như chuỗi rỗng, `'N/A'` hoặc `-1`.

## 2. Tạo bộ dữ liệu thực hành có nhiều trạng thái thiếu

Các ví dụ chính được viết cho **PostgreSQL**. Hãy chạy trong database thực hành với tài khoản được phép tạo bảng tạm. `TEMP TABLE` chỉ tồn tại trong phiên kết nối. Nếu đã có bảng tạm cùng tên trong phiên, hãy mở một phiên mới hoặc chọn tên khác trước khi chạy lại.

```sql
CREATE TEMP TABLE orders_null_lab (
    order_id       INTEGER PRIMARY KEY,
    customer_name  TEXT NOT NULL,
    payment_status TEXT,
    shipped_at     DATE,
    delivered_at   DATE,
    cancelled_at   DATE,
    tracking_code  TEXT,
    order_total    NUMERIC(10, 2),
    reviewed       BOOLEAN
);

INSERT INTO orders_null_lab (
    order_id, customer_name, payment_status,
    shipped_at, delivered_at, cancelled_at,
    tracking_code, order_total, reviewed
)
VALUES
    (1, 'An',   'PAID',
        DATE '2026-03-01', DATE '2026-03-03', NULL,
        'DH001', 120.00, TRUE),

    (2, 'Bình', 'PAID',
        NULL, NULL, NULL,
        NULL, 80.00, NULL),

    (3, 'Chi',  'PENDING',
        NULL, NULL, NULL,
        NULL, 50.00, FALSE),

    (4, 'Dũng', NULL,
        NULL, NULL, NULL,
        '', 40.00, NULL),

    (5, 'Hà',   'PAID',
        DATE '2026-03-02', NULL, NULL,
        ' DH005 ', NULL, FALSE),

    (6, 'Lan',  'CANCELLED',
        NULL, NULL, DATE '2026-03-04',
        NULL, 0.00, TRUE),

    (7, 'Minh', 'PAID',
        DATE '2026-03-05', DATE '2026-03-06', NULL,
        NULL, 95.00, NULL),

    (8, 'Nga',  'PENDING',
        NULL, NULL, NULL,
        'N/A', NULL, NULL);
```

Xem dữ liệu:

```sql
SELECT order_id,
       customer_name,
       payment_status,
       shipped_at,
       delivered_at,
       cancelled_at,
       tracking_code,
       order_total,
       reviewed
FROM orders_null_lab
ORDER BY order_id;
```

Các trường hợp được cố ý tạo khác nhau:

| Đơn | Trạng thái nổi bật |
| --- | --- |
| 1 – An | Đã thanh toán, có ngày gửi và giao |
| 2 – Bình | Đã thanh toán nhưng chưa ghi nhận ngày gửi; `reviewed` là `NULL` |
| 3 – Chi | Chưa thanh toán; `reviewed = FALSE` |
| 4 – Dũng | Chưa xác định trạng thái thanh toán; mã vận đơn là chuỗi rỗng |
| 5 – Hà | Đã gửi, chưa ghi nhận ngày giao; thiếu giá trị `order_total` |
| 6 – Lan | Đã hủy; có tổng tiền bằng `0`; đã được đánh giá `TRUE` |
| 7 – Minh | Đã giao nhưng chưa có mã vận đơn trong dữ liệu |
| 8 – Nga | Chưa thanh toán; mã vận đơn có ký hiệu `'N/A'`; thiếu `order_total` |

Ngày và tình trạng trong bảng chỉ là **dữ liệu mẫu**. Trong hệ thống thực, “chưa ghi nhận ngày gửi” chưa đủ để khẳng định kiện hàng thực tế chưa được gửi; kết luận phải dựa trên quy định về nguồn dữ liệu và trạng thái đơn hàng.

## 3. Cú pháp đúng để lọc giá trị NULL

Hai phép kiểm tra cơ bản:

```sql
column_name IS NULL
column_name IS NOT NULL
```

Ví dụ tìm đơn chưa có ngày gửi:

```sql
SELECT order_id, customer_name
FROM orders_null_lab
WHERE shipped_at IS NULL
ORDER BY order_id;
```

Kết quả là đơn **2, 3, 4, 6, 8**. Câu SQL chỉ xác định cột `shipped_at` chưa có giá trị; danh sách vẫn có đơn chưa thanh toán và đơn đã hủy. Nếu yêu cầu là “đơn đã thanh toán nhưng chưa gửi”, cần thêm điều kiện nghiệp vụ ở phần sau.

Tìm các đơn đã có ngày gửi:

```sql
SELECT order_id, customer_name, shipped_at
FROM orders_null_lab
WHERE shipped_at IS NOT NULL
ORDER BY order_id;
```

Kết quả là đơn **1, 5, 7**.

### Vì sao `= NULL` không đúng?

Cách viết sau không lọc được các hàng `NULL` trong PostgreSQL:

```sql
-- Sai cách kiểm tra NULL
SELECT order_id
FROM orders_null_lab
WHERE shipped_at = NULL;
```

Tương tự:

```sql
-- Sai cách kiểm tra giá trị không NULL
SELECT order_id
FROM orders_null_lab
WHERE shipped_at <> NULL;
```

Trong SQL chuẩn, phép so sánh thông thường với `NULL` trả kết quả logic **UNKNOWN**. `WHERE` chỉ giữ hàng có điều kiện là **TRUE**, nên hai câu trên không chọn được hàng như ý định.

Để lọc:

| Ý định | Viết đúng |
| --- | --- |
| Giá trị bị thiếu | `column IS NULL` |
| Giá trị đã có | `column IS NOT NULL` |
| Giá trị cụ thể bằng `'PAID'` | `column = 'PAID'` |
| Giá trị khác `'PAID'` nhưng loại `NULL` | `column <> 'PAID'` |
| Khác `'PAID'` hoặc `NULL` | `column IS NULL OR column <> 'PAID'` |

Trong PostgreSQL còn có `IS DISTINCT FROM` để so sánh có xử lý `NULL` như một giá trị riêng; nội dung này sẽ được giải thích sau.

## 4. Logic ba giá trị quyết định hàng nào qua WHERE

Mệnh đề `WHERE` đánh giá điều kiện theo **TRUE**, **FALSE** và **UNKNOWN**. Chỉ kết quả `TRUE` được giữ.

Giả sử đang lọc `payment_status`:

| Giá trị `payment_status` | `payment_status = 'PAID'` | `payment_status <> 'PAID'` |
| --- | --- | --- |
| `'PAID'` | TRUE | FALSE |
| `'PENDING'` | FALSE | TRUE |
| `NULL` | UNKNOWN | UNKNOWN |

Với dữ liệu mẫu:

```sql
SELECT order_id, payment_status
FROM orders_null_lab
WHERE payment_status <> 'PAID'
ORDER BY order_id;
```

Kết quả gồm **3, 6, 8**, không có đơn **4** vì `payment_status` của đơn 4 là `NULL`.

Tương tự, thêm `NOT` không biến UNKNOWN thành TRUE:

```sql
SELECT order_id, payment_status
FROM orders_null_lab
WHERE NOT (payment_status = 'PAID')
ORDER BY order_id;
```

Kết quả vẫn là **3, 6, 8**. Về logic:

| Điều kiện `p` | `NOT p` |
| --- | --- |
| TRUE | FALSE |
| FALSE | TRUE |
| UNKNOWN | UNKNOWN |

Nếu yêu cầu là **“lấy mọi đơn không được ghi nhận là đã thanh toán, bao gồm cả trạng thái chưa biết”**, cần viết rõ:

```sql
SELECT order_id, payment_status
FROM orders_null_lab
WHERE payment_status <> 'PAID'
   OR payment_status IS NULL
ORDER BY order_id;
```

Kết quả lúc này gồm **3, 4, 6, 8**.

**Chú ý ý nghĩa:** “khác `PAID`” và “không xác nhận được là `PAID`” có thể là hai yêu cầu khác nhau. Nếu `NULL` có nghĩa “chưa nhận trạng thái từ cổng thanh toán”, đừng mặc định coi nó là “thất bại thanh toán”; có thể cần đưa vào hàng chờ kiểm tra riêng.

### Một vài phép toán logic với UNKNOWN

| `p` | `q` | Biểu thức | Kết quả |
| --- | --- | --- | --- |
| TRUE | UNKNOWN | `p AND q` | UNKNOWN |
| FALSE | UNKNOWN | `p AND q` | FALSE |
| TRUE | UNKNOWN | `p OR q` | TRUE |
| FALSE | UNKNOWN | `p OR q` | UNKNOWN |

Sự kết hợp giữa `AND`, `OR` và `NULL` quyết định nhóm hàng có được giữ hay không; không thể đọc điều kiện như logic hai trạng thái đơn giản của một ngôn ngữ lập trình thông thường.

## 5. Biến yêu cầu nghiệp vụ thành điều kiện lọc

### 5.1. “Đã thanh toán nhưng chưa ghi nhận ngày gửi”

Các điều kiện cần có:

1. Trạng thái thanh toán đã xác định là `PAID`.
2. Chưa có ngày gửi (`shipped_at IS NULL`).
3. Không có ngày hủy (`cancelled_at IS NULL`).

```sql
SELECT order_id, customer_name, payment_status
FROM orders_null_lab
WHERE payment_status = 'PAID'
  AND shipped_at IS NULL
  AND cancelled_at IS NULL
ORDER BY order_id;
```

Kết quả chỉ có **đơn 2 – Bình**.

Nếu chỉ lọc `shipped_at IS NULL`, bạn sẽ kéo vào báo cáo cả những đơn chưa được thanh toán hoặc đã hủy. Vì vậy một cột `NULL` cần được kết hợp với các trạng thái liên quan để trả lời đúng câu hỏi vận hành.

### 5.2. “Chưa xác nhận thanh toán hoặc đang chờ thanh toán”

Giả sử nhóm cần xem xét chỉ gồm đơn chưa có trạng thái thanh toán và đơn có trạng thái `PENDING`, đồng thời loại đơn đã hủy:

```sql
SELECT order_id, payment_status, cancelled_at
FROM orders_null_lab
WHERE cancelled_at IS NULL
  AND (
       payment_status IS NULL
       OR payment_status = 'PENDING'
  )
ORDER BY order_id;
```

Kết quả gồm **3, 4, 8**.

Nếu cần phân biệt hàng chưa nhận dữ liệu và hàng đang chờ:

```sql
SELECT order_id,
       CASE
           WHEN payment_status IS NULL THEN 'Chưa nhận trạng thái'
           WHEN payment_status = 'PENDING' THEN 'Đang chờ thanh toán'
           ELSE 'Trạng thái khác'
       END AS payment_group
FROM orders_null_lab
WHERE cancelled_at IS NULL
  AND (
       payment_status IS NULL
       OR payment_status = 'PENDING'
  )
ORDER BY order_id;
```

Kết quả truy vấn dùng `CASE` để hiển thị hai lý do riêng. Cột `payment_group` là cột kết quả, không sửa `payment_status` đã lưu.

### 5.3. “Chưa có tổng tiền” khác “tổng tiền bằng 0”

```sql
-- Đơn chưa có dữ liệu tổng tiền
SELECT order_id, order_total
FROM orders_null_lab
WHERE order_total IS NULL
ORDER BY order_id;

-- Đơn có tổng tiền đúng bằng 0
SELECT order_id, order_total
FROM orders_null_lab
WHERE order_total = 0
ORDER BY order_id;
```

Truy vấn đầu trả **5, 8**; truy vấn thứ hai trả **6**.

Dù tổng tiền 0 có thể cần xem xét thêm theo chính sách kinh doanh, `0` vẫn là một **giá trị đã được ghi**, khác với thiếu giá trị. Đừng dùng điều kiện `COALESCE(order_total,0) = 0` nếu mục tiêu là phân biệt “thiếu giá” và “giá bằng 0”: biểu thức đó gộp hai nhóm lại.

Muốn lọc **đơn đã có tổng tiền dương**:

```sql
SELECT order_id, order_total
FROM orders_null_lab
WHERE order_total IS NOT NULL
  AND order_total > 0
ORDER BY order_id;
```

Kết quả là **1, 2, 3, 4, 7**. Trong câu SQL này, điều kiện `order_total > 0` tự nó đã loại `NULL` do UNKNOWN, nhưng thêm `IS NOT NULL` có thể làm ý định nghiệp vụ rõ hơn.

### 5.4. “Chưa được đánh giá” khác “đánh giá không đạt”

Theo định nghĩa `reviewed` ở đầu bài:

```sql
-- Chỉ các đơn chưa có kết quả đánh giá
SELECT order_id, reviewed
FROM orders_null_lab
WHERE reviewed IS NULL
ORDER BY order_id;

-- Chỉ các đơn có kết quả đánh giá là FALSE
SELECT order_id, reviewed
FROM orders_null_lab
WHERE reviewed IS FALSE
ORDER BY order_id;
```

Các đơn chưa có kết quả là **2, 4, 7, 8**; các đơn được đánh giá `FALSE` là **3, 5**.

Nếu nghiệp vụ yêu cầu **“cần tiếp tục xử lý tất cả đơn chưa đạt điều kiện đã duyệt, kể cả chưa duyệt”**, PostgreSQL cho phép viết:

```sql
SELECT order_id, reviewed
FROM orders_null_lab
WHERE reviewed IS NOT TRUE
ORDER BY order_id;
```

Kết quả gồm **2, 3, 4, 5, 7, 8**. `IS NOT TRUE` nhận cả `FALSE` và `UNKNOWN` (giá trị cột `NULL`). Có thể viết tương đương cho cột boolean:

```sql
WHERE reviewed IS FALSE
   OR reviewed IS NULL
```

Cú pháp hỗ trợ boolean và cách dùng `IS [NOT] TRUE` có thể khác giữa các DBMS. Nếu hệ quản trị không có kiểu boolean SQL độc lập, quy ước `0/1/NULL` cần được mô tả và lọc đúng theo kiểu cột thực tế.

### 5.5. “Có ngày gửi nhưng chưa có mã vận đơn hợp lệ”

Mã vận đơn trong ví dụ có thể là `NULL`, chuỗi rỗng, chuỗi `'N/A'` hoặc mã chứa khoảng trắng.

Nếu chỉ kiểm tra `tracking_code IS NULL`, bạn sẽ bỏ sót các ô rỗng bằng chuỗi. Nếu doanh nghiệp quy định chuỗi rỗng và `'N/A'` đều có nghĩa “không có mã sử dụng được”, PostgreSQL có thể lọc:

```sql
SELECT order_id, shipped_at, tracking_code
FROM orders_null_lab
WHERE shipped_at IS NOT NULL
  AND NULLIF(
        NULLIF(UPPER(TRIM(tracking_code)), ''),
        'N/A'
      ) IS NULL
ORDER BY order_id;
```

Kết quả là **đơn 7 – Minh**.

Biểu thức hoạt động theo thứ tự:

- `TRIM` bỏ khoảng trắng ở hai đầu mã.
- `UPPER` dùng khi quy định mã `n/a` và `N/A` cùng ý nghĩa.
- `NULLIF(..., '')` đổi chuỗi rỗng thành `NULL`.
- `NULLIF(..., 'N/A')` đổi mã quy ước `N/A` thành `NULL`.
- `IS NULL` lọc các hàng cuối cùng không có mã sử dụng được.

Cách chuyển thành chữ hoa chỉ phù hợp nếu **nghiệp vụ không phân biệt hoa/thường** ở mã cần kiểm tra. Nếu mã `Ab12` khác `AB12`, phải thiết kế quy tắc nhận diện ký hiệu thiếu sao cho không thay đổi ý nghĩa các mã thật.

**Ghi nhớ:** chuẩn hóa trong điều kiện `WHERE` chỉ thay đổi cách kiểm tra; nó không tự sửa `tracking_code` trong bảng.

## 6. Dấu ngoặc khi kết hợp AND và OR

Toán tử `AND` có mức ưu tiên cao hơn `OR` trong SQL thông thường. Đây là nguồn lỗi rất hay gặp khi muốn lọc các hàng có `NULL`.

Yêu cầu: “Các đơn **chưa hủy** và có trạng thái thanh toán **đang chờ hoặc chưa xác định**”.

Viết đúng:

```sql
SELECT order_id
FROM orders_null_lab
WHERE cancelled_at IS NULL
  AND (payment_status = 'PENDING' OR payment_status IS NULL)
ORDER BY order_id;
```

Kết quả: **3, 4, 8**.

Nếu viết thiếu dấu ngoặc:

```sql
SELECT order_id
FROM orders_null_lab
WHERE cancelled_at IS NULL
  AND payment_status IS NULL
   OR payment_status = 'PENDING'
ORDER BY order_id;
```

SQL sẽ hiểu theo cấu trúc:

```text
(cancelled_at IS NULL AND payment_status IS NULL)
OR payment_status = 'PENDING'
```

Trong dữ liệu hiện tại, câu trên cũng trả 3, 4, 8 vì không có đơn `PENDING` đã hủy. Nhưng nếu ngày mai một đơn có `payment_status = 'PENDING'` và `cancelled_at IS NOT NULL`, nó sẽ bị câu thứ hai chọn nhầm. Hai câu không tương đương về nghiệp vụ dù tạm thời cho kết quả giống nhau trên dữ liệu mẫu.

Muốn minh họa khác biệt trên một hàng cụ thể mà không sửa bảng, thử:

```sql
WITH example(cancelled_at, payment_status) AS (
    VALUES (DATE '2026-03-04', 'PENDING'::TEXT)
)
SELECT
    cancelled_at IS NULL
      AND (payment_status = 'PENDING' OR payment_status IS NULL)
        AS correct_filter,
    cancelled_at IS NULL
      AND payment_status IS NULL
      OR payment_status = 'PENDING'
        AS filter_without_parentheses
FROM example;
```

Kết quả `correct_filter = FALSE` nhưng `filter_without_parentheses = TRUE`. Dấu ngoặc nên phản ánh **nhóm điều kiện trong yêu cầu**, thay vì trông chờ vào khả năng người đọc tự nhớ độ ưu tiên.

## 7. Khi cần so sánh khác nhau kể cả NULL: IS DISTINCT FROM

Ở PostgreSQL, biểu thức `IS DISTINCT FROM` so sánh hai giá trị theo cách cho ra kết quả TRUE/FALSE ngay cả khi có `NULL`:

```sql
SELECT order_id, payment_status
FROM orders_null_lab
WHERE payment_status IS DISTINCT FROM 'PAID'
ORDER BY order_id;
```

Kết quả: **3, 4, 6, 8**. Về ý nghĩa, truy vấn này tương đương:

```sql
WHERE payment_status <> 'PAID'
   OR payment_status IS NULL
```

Bảng so sánh:

| Giá trị a | Giá trị b | `a <> b` | `a IS DISTINCT FROM b` |
| --- | --- | --- | --- |
| `'PAID'` | `'PAID'` | FALSE | FALSE |
| `'PENDING'` | `'PAID'` | TRUE | TRUE |
| `NULL` | `'PAID'` | UNKNOWN | TRUE |
| `NULL` | `NULL` | UNKNOWN | FALSE |

Tương tự, `IS NOT DISTINCT FROM` diễn đạt “bằng nhau khi coi hai `NULL` là cùng trạng thái thiếu”:

```sql
SELECT NULL::TEXT IS NOT DISTINCT FROM NULL::TEXT
       AS two_missing_values_match;
```

Kết quả là `TRUE`. Điều này **không làm thay đổi** quy tắc của toán tử `=`: `NULL = NULL` vẫn là UNKNOWN.

`IS [NOT] DISTINCT FROM` là cú pháp từ SQL chuẩn và được nhiều hệ quản trị hiện đại hỗ trợ, nhưng mức độ hỗ trợ theo sản phẩm/phiên bản khác nhau. MySQL có toán tử so sánh bằng an toàn với `NULL` là `<=>`. Khi chuyển SQL, cần dùng cú pháp đúng của DBMS thay vì mặc định mọi hệ đều nhận cùng một dạng.

## 8. Lọc dữ liệu sau LEFT JOIN: NULL có thể đến từ hai nguồn

Trong truy vấn một bảng, `NULL` có thể là giá trị đã lưu trong hàng. Với **`LEFT JOIN`**, còn có một trường hợp khác: DBMS tạo các cột bên phải mang `NULL` khi **không tìm được hàng khớp**.

Tạo thêm bảng tạm ghi nhận tình trạng xác minh đơn:

```sql
CREATE TEMP TABLE order_flags_null_lab (
    order_id    INTEGER PRIMARY KEY,
    flag_status TEXT
);

INSERT INTO order_flags_null_lab (order_id, flag_status)
VALUES
    (1, 'VERIFIED'),
    (2, NULL),
    (3, 'REVIEW'),
    (5, 'VERIFIED'),
    (6, 'REVIEW');
```

Ở đây:

- Đơn **1, 5** có trạng thái xác minh `VERIFIED`.
- Đơn **2** có **bản ghi** xác minh nhưng `flag_status = NULL`.
- Đơn **3, 6** có bản ghi trạng thái `REVIEW`.
- Đơn **4, 7, 8** **không có hàng nào** trong bảng `order_flags_null_lab`.

### 8.1. Cột bên phải bằng NULL không chứng minh “không có bản ghi”

```sql
SELECT o.order_id, f.order_id AS matched_flag_id, f.flag_status
FROM orders_null_lab AS o
LEFT JOIN order_flags_null_lab AS f
  ON f.order_id = o.order_id
WHERE f.flag_status IS NULL
ORDER BY o.order_id;
```

Kết quả gồm **2, 4, 7, 8**:

- Đơn 2 có hàng `f` thật nhưng `flag_status` trong hàng đó là `NULL`.
- Đơn 4, 7, 8 không có hàng `f` tương ứng; `LEFT JOIN` tạo giá trị `NULL` phía bên phải.

Nếu yêu cầu là **“đơn chưa có bất cứ bản ghi xác minh nào”**, hãy kiểm tra khóa không nullable của bảng bên phải:

```sql
SELECT o.order_id
FROM orders_null_lab AS o
LEFT JOIN order_flags_null_lab AS f
  ON f.order_id = o.order_id
WHERE f.order_id IS NULL
ORDER BY o.order_id;
```

Kết quả chỉ có **4, 7, 8**. `f.order_id` là khóa chính `NOT NULL` nên một giá trị `NULL` tại đó sau `LEFT JOIN` biểu thị không có hàng khớp.

### 8.2. Chuyển điều kiện từ ON sang WHERE làm thay đổi kết quả

Câu sau:

```sql
SELECT o.order_id, f.flag_status
FROM orders_null_lab AS o
LEFT JOIN order_flags_null_lab AS f
  ON f.order_id = o.order_id
WHERE f.flag_status = 'VERIFIED'
ORDER BY o.order_id;
```

chỉ trả đơn **1, 5**. Mệnh đề `WHERE f.flag_status = 'VERIFIED'` loại các hàng không khớp do giá trị ở cột bên phải là `NULL`, nên kết quả trong trường hợp này giống một phép nối trong chỉ giữ hàng có trạng thái xác minh.

Trong khi đó:

```sql
SELECT o.order_id, f.flag_status
FROM orders_null_lab AS o
LEFT JOIN order_flags_null_lab AS f
  ON f.order_id = o.order_id
 AND f.flag_status = 'VERIFIED'
ORDER BY o.order_id;
```

vẫn trả **cả tám đơn**; chỉ những đơn có bản ghi `VERIFIED` mới có `f.flag_status` khác `NULL`. Điều kiện trong `ON` giới hạn **bản ghi được phép khớp**, còn `LEFT JOIN` vẫn giữ mọi hàng bên trái.

Nếu muốn tìm đơn **chưa có bản ghi VERIFIED**, bao gồm đơn chưa có cờ nào và đơn có cờ khác:

```sql
SELECT o.order_id
FROM orders_null_lab AS o
LEFT JOIN order_flags_null_lab AS f
  ON f.order_id = o.order_id
 AND f.flag_status = 'VERIFIED'
WHERE f.order_id IS NULL
ORDER BY o.order_id;
```

Kết quả: **2, 3, 4, 6, 7, 8**. Đây là một dạng **anti-join**: loại các đơn có bản ghi `VERIFIED`.

## 9. Dùng NOT EXISTS để tìm hàng chưa có quan hệ tương ứng

`NOT EXISTS` thích hợp khi yêu cầu nghiệp vụ nói về **sự tồn tại của bản ghi liên quan**, ví dụ “đơn chưa có bản ghi xác minh”.

```sql
SELECT o.order_id, o.customer_name
FROM orders_null_lab AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM order_flags_null_lab AS f
    WHERE f.order_id = o.order_id
)
ORDER BY o.order_id;
```

Kết quả: **4, 7, 8**.

`EXISTS` và `NOT EXISTS` quan tâm **truy vấn con có trả ít nhất một hàng hay không**, không cần biết cột bên trong của hàng đó có `NULL` hay không. Vì thế đây là cách diễn đạt tự nhiên khi tìm **thiếu bản ghi liên quan**.

### Cẩn thận với NOT IN và một giá trị NULL trong danh sách

Giả sử danh sách loại trừ vô tình chứa `NULL`:

```sql
SELECT order_id
FROM orders_null_lab
WHERE order_id NOT IN (1, NULL)
ORDER BY order_id;
```

Trong PostgreSQL, câu này **không trả hàng nào**. Với một `order_id` khác 1, biểu thức `order_id IN (1, NULL)` là UNKNOWN do còn phần so sánh với `NULL`; phủ định UNKNOWN vẫn là UNKNOWN nên `WHERE` loại hàng đó. Đơn 1 thì bị loại vì nằm trong danh sách.

Để lọc đơn không có bản ghi tương ứng, sử dụng `NOT EXISTS` như ví dụ trên. Nếu vẫn dùng `NOT IN (subquery)`, bạn cần đảm bảo cột ở truy vấn con không chứa `NULL` và hiểu rõ ngữ nghĩa so sánh.

Không nên khái quát rằng `NOT IN` luôn sai: khi danh sách là các giá trị **không NULL** và giá trị phía trái cũng được xử lý đúng, nó có thể hoạt động theo ý định. Rủi ro xuất hiện khi `NULL` tham gia.

## 10. Chuẩn hóa giá trị thiếu trước khi lọc

Có hai nguồn “thiếu” thường gặp:

1. Cột thực sự mang `NULL`.
2. Cột chứa một giá trị quy ước cho “thiếu”, ví dụ `''`, `'   '`, `'N/A'` hoặc `-1`.

`IS NULL` chỉ kiểm tra trường hợp thứ nhất. Muốn gộp các mã giả vào nhóm thiếu, cần xác định **quy tắc chuẩn hóa của cột đó**.

### Chuỗi rỗng và khoảng trắng

Trong PostgreSQL:

```sql
-- Chỉ phát hiện NULL thực sự
WHERE tracking_code IS NULL

-- Phát hiện cả NULL, chuỗi rỗng, chuỗi chỉ có khoảng trắng
WHERE NULLIF(TRIM(tracking_code), '') IS NULL
```

`TRIM(NULL)` trả `NULL`; `TRIM('   ')` trả chuỗi rỗng; `NULLIF('', '')` trả `NULL`. Vì thế câu thứ hai lọc cả hai trường hợp.

### Mã N/A

```sql
SELECT order_id, tracking_code
FROM orders_null_lab
WHERE NULLIF(
        NULLIF(UPPER(TRIM(tracking_code)), ''),
        'N/A'
      ) IS NULL
ORDER BY order_id;
```

Với dữ liệu mẫu, kết quả gồm **2, 3, 4, 6, 7, 8**. Đơn 1 có `DH001`; đơn 5 có `' DH005 '`, sau `TRIM` là mã hợp lệ.

Quy tắc `'N/A'` chỉ nên áp dụng khi dữ liệu nguồn thực sự dùng ký hiệu đó theo nghĩa thiếu. Nếu hệ thống cho phép một mã hàng hợp lệ là `N/A` thì không thể tự chuyển nó thành `NULL`.

### COALESCE có thể làm mất phân biệt

`COALESCE(expression, fallback)` trả giá trị đầu tiên khác `NULL`:

```sql
SELECT order_id,
       COALESCE(order_total, 0) AS display_total
FROM orders_null_lab
ORDER BY order_id;
```

Đây là cách tạo **giá trị hiển thị** khi báo cáo yêu cầu một con số. Nhưng nếu lọc:

```sql
SELECT order_id
FROM orders_null_lab
WHERE COALESCE(order_total, 0) = 0
ORDER BY order_id;
```

kết quả gồm **5, 6, 8**, vì đơn 5 và 8 có `NULL` bị thay bằng 0, còn đơn 6 có giá trị 0 thật. Nếu yêu cầu là “chưa có giá”, phải dùng `order_total IS NULL`. Nếu yêu cầu “giá bằng 0”, dùng `order_total = 0`.

**Nguyên tắc:** dùng `COALESCE` để thay `NULL` chỉ khi nghiệp vụ chấp nhận gộp giá trị thiếu vào một giá trị thay thế.

## 11. Lọc tham số tùy chọn: “tất cả”, “chưa có” hay “có giá trị”

Một màn hình tìm kiếm thường có bộ lọc theo trạng thái. Người dùng có thể chọn:

- **Tất cả**: không lọc theo trạng thái.
- **Thiếu trạng thái**: chỉ hàng có `payment_status IS NULL`.
- **Đã có trạng thái**: chỉ hàng có `payment_status IS NOT NULL`.
- **Bằng một trạng thái cụ thể**: ví dụ `'PAID'`.

Bốn ý định này không nên được diễn giải chỉ bằng một tham số `NULL`, vì `NULL` ở **tham số bộ lọc** có thể có nghĩa “không lọc”, trong khi `NULL` ở **cột dữ liệu** là “chưa có giá trị”.

Ví dụ PostgreSQL mô phỏng một bộ lọc có chế độ tường minh:

```sql
WITH filter_params AS (
    SELECT 'missing'::TEXT AS filter_mode,
           NULL::TEXT AS wanted_status
)
SELECT o.order_id, o.payment_status
FROM orders_null_lab AS o
CROSS JOIN filter_params AS p
WHERE p.filter_mode = 'all'
   OR (p.filter_mode = 'missing'
       AND o.payment_status IS NULL)
   OR (p.filter_mode = 'present'
       AND o.payment_status IS NOT NULL)
   OR (p.filter_mode = 'equals'
       AND o.payment_status = p.wanted_status)
ORDER BY o.order_id;
```

Với `filter_mode = 'missing'`, kết quả chỉ có **đơn 4**. Đổi `filter_mode` thành `'present'` sẽ lấy bảy đơn còn lại. Đổi thành `'equals'` và `wanted_status = 'PAID'` sẽ lấy đơn **1, 2, 5, 7**.

Một cách viết ứng dụng phổ biến là:

```sql
-- Mẫu ý tưởng: tham số NULL có nghĩa không áp dụng bộ lọc
WHERE (:status_filter IS NULL OR payment_status = :status_filter)
```

Đây **không phải cú pháp tham số PostgreSQL dùng trực tiếp trong psql**; ký hiệu `:status_filter` chỉ là minh họa cho tham số tên ở lớp ứng dụng/framework. Cách này có thể thích hợp cho lựa chọn “tất cả”, nhưng **không thể dùng chính `NULL` của tham số để đồng thời yêu cầu “chỉ lấy cột NULL”**. Khi cả hai chức năng cần tồn tại, hãy dùng một chế độ lọc riêng như ví dụ `filter_mode`.

Các truy vấn có nhiều điều kiện `OR` phụ thuộc tham số cũng có thể cần xem xét kế hoạch thực thi và thiết kế index trên dữ liệu lớn; cách biểu đạt rõ nghĩa là điểm khởi đầu trước khi tối ưu.

## 12. Đếm số lượng theo trạng thái NULL

Đôi khi yêu cầu không phải lấy từng hàng mà là **thống kê** số hàng có/không có giá trị.

### COUNT(*) khác COUNT(column)

```sql
SELECT COUNT(*)             AS total_orders,
       COUNT(payment_status) AS known_payment_statuses,
       COUNT(order_total)    AS orders_with_total
FROM orders_null_lab;
```

Với dữ liệu mẫu:

- `COUNT(*) = 8` vì đếm tất cả hàng.
- `COUNT(payment_status) = 7` vì bỏ qua đơn 4 có `payment_status IS NULL`.
- `COUNT(order_total) = 6` vì bỏ qua đơn 5 và 8 có `order_total IS NULL`.

Không dùng `COUNT(column)` nếu muốn đếm **mọi hàng** trong nhóm kể cả khi cột đó thiếu.

### Đếm điều kiện cụ thể

PostgreSQL hỗ trợ cú pháp `FILTER` trong hàm tổng hợp:

```sql
SELECT
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (WHERE payment_status IS NULL)
        AS missing_payment_status,
    COUNT(*) FILTER (WHERE order_total IS NULL)
        AS missing_order_total,
    COUNT(*) FILTER (WHERE reviewed IS NOT TRUE)
        AS not_confirmed_review,
    COUNT(*) FILTER (
        WHERE payment_status = 'PAID'
          AND shipped_at IS NULL
          AND cancelled_at IS NULL
    ) AS paid_without_shipped_date
FROM orders_null_lab;
```

Kết quả lần lượt là **8, 1, 2, 6, 1**. Điều kiện trong `FILTER` chỉ tính những hàng mà biểu thức là TRUE.

Nếu DBMS không hỗ trợ `FILTER`, có thể dùng `SUM(CASE WHEN ... THEN 1 ELSE 0 END)`:

```sql
SELECT SUM(
           CASE WHEN order_total IS NULL THEN 1 ELSE 0 END
       ) AS missing_order_total
FROM orders_null_lab;
```

Kết quả là **2** trên bộ dữ liệu này. Khi thống kê theo trạng thái nghiệp vụ, hãy đặt tên kết quả theo ý nghĩa thực tế, ví dụ `paid_without_shipped_date` thay vì một nhãn quá chung như `missing`.

## 13. Chọn điều kiện lọc sao cho phù hợp ý nghĩa thời điểm

Một trường ngày `NULL` có thể biểu diễn:

- Sự kiện **chưa xảy ra**, ví dụ chưa gửi hàng.
- Sự kiện **đã xảy ra nhưng chưa đồng bộ**, ví dụ hệ thống vận chuyển đã giao nhưng chưa gửi callback.
- Sự kiện **không áp dụng**, ví dụ đơn hủy trước khi gửi.
- Giá trị **không biết** do dữ liệu lịch sử thiếu.

Do đó điều kiện:

```sql
WHERE delivered_at IS NULL
```

chỉ diễn đạt chính xác “**chưa có ngày giao được ghi nhận**”. Nó chưa chắc tương đương “**đang giao hàng**” hoặc “**đơn sẽ được giao**”.

Yêu cầu **“đơn đã gửi, chưa ghi nhận ngày giao, chưa hủy”** nên có các trạng thái phối hợp:

```sql
SELECT order_id, shipped_at, delivered_at
FROM orders_null_lab
WHERE shipped_at IS NOT NULL
  AND delivered_at IS NULL
  AND cancelled_at IS NULL
ORDER BY order_id;
```

Kết quả là **đơn 5**.

Trong ứng dụng thực tế, nếu có thêm cột `shipping_status` hoặc bảng sự kiện giao nhận, cần quyết định nguồn nào là sự thật nghiệp vụ. Một giá trị `NULL` trong timestamp chỉ cung cấp bằng chứng **chưa có timestamp trong bảng này**.

Tương tự, nếu hệ thống dùng `deleted_at IS NULL` để biểu diễn “chưa bị xóa mềm”, điều kiện ấy chỉ đúng khi đó là quy ước dữ liệu được áp dụng nhất quán. Không phải cột ngày `NULL` nào cũng mang ý nghĩa “còn hiệu lực”.

## 14. Tính hiệu quả và tính dễ hiểu của bộ lọc

Mục tiêu đầu tiên là **đúng tập dữ liệu theo nghiệp vụ**. Sau đó mới tối ưu truy vấn với dữ liệu thật.

### Viết trực tiếp điều kiện có thể giúp DBMS dùng index

Ví dụ:

```sql
WHERE order_total IS NULL
```

diễn đạt trực tiếp cột cần lọc. Trong PostgreSQL, B-tree index có thể hỗ trợ một số truy vấn `IS NULL` / `IS NOT NULL` tùy dữ liệu, độ chọn lọc và kế hoạch thực thi.

Ngược lại:

```sql
WHERE COALESCE(order_total, 0) = 0
```

vừa có ngữ nghĩa khác, vừa áp dụng hàm lên cột. Việc đó có thể làm thay đổi cơ hội dùng index thông thường; một số DBMS hỗ trợ expression index, nhưng không nên tự thay thế điều kiện rõ ràng bằng biểu thức phức tạp khi không cần thiết.

Một index lọc một nhóm hoạt động thường xuyên trong PostgreSQL có thể được thiết kế theo truy vấn thực tế, chẳng hạn index từng phần trên các đơn đã thanh toán nhưng chưa gửi. Đây là lựa chọn phụ thuộc quy mô bảng, tỷ lệ hàng `NULL`, mẫu truy vấn và chi phí cập nhật; không cần tạo index chỉ để thực hành bài này.

### Không mặc định cột NOT NULL sẽ không bao giờ thiếu trong mọi nguồn

`NOT NULL` là ràng buộc của một cột trong bảng, nhưng các phép `LEFT JOIN`, biểu thức `CASE`, hàm chuyển đổi và dữ liệu truyền giữa hệ thống có thể tạo ra giá trị `NULL` **ở kết quả truy vấn**. Vì vậy cần xem xét nguồn của `NULL` tại vị trí đang lọc, không chỉ đọc cấu trúc cột gốc.

## 15. Một số khác biệt giữa các DBMS

| Chủ đề | PostgreSQL | Lưu ý khi chuyển hệ |
| --- | --- | --- |
| Kiểm tra thiếu giá trị | `IS NULL`, `IS NOT NULL` | Là cú pháp nền tảng phổ biến trong SQL |
| So sánh chứa `NULL` | `IS [NOT] DISTINCT FROM` | Mức hỗ trợ phụ thuộc DBMS/phiên bản; MySQL có `<=>` cho so sánh bằng an toàn với `NULL` |
| Boolean và UNKNOWN | `BOOLEAN`, `IS TRUE`, `IS FALSE`, `IS NOT TRUE` | SQL Server và một số hệ không có cùng kiểu boolean dùng trong cột hoặc biểu thức `SELECT` |
| Chuỗi rỗng | `''` khác `NULL` | Oracle Database thường coi chuỗi ký tự rỗng là `NULL` trong ngữ cảnh chuỗi ký tự, nên cách lọc cần điều chỉnh |
| Chuẩn hóa khoảng trắng | `TRIM(text)` | Cách xử lý ký tự/Unicode/collation có thể khác |
| Đếm có điều kiện | `COUNT(*) FILTER (WHERE condition)` | Một số DBMS dùng `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` thay thế |
| Join không tìm được hàng | Cột bên phải của `LEFT JOIN` là `NULL` | Nguyên tắc SQL chung, nhưng cần phân biệt với `NULL` thực sự có trong hàng bên phải |
| So sánh chuỗi | Theo kiểu/collation/cấu hình | Việc `'paid'` có bằng `'PAID'` hay không phụ thuộc hệ và collation |

Đừng tự suy ra rằng `NULL` ở các hệ đều có cùng “ý nghĩa nghiệp vụ”. DBMS quy định cách xử lý logic SQL; **ứng dụng mới là nơi quyết định một trường `NULL` có nghĩa “chưa biết”, “không áp dụng” hay “chưa xảy ra”**.

## 16. Những lỗi thường gặp

| Triệu chứng hoặc cách viết | Sai lệch có thể xảy ra | Cách viết hoặc hướng kiểm tra |
| --- | --- | --- |
| `WHERE col = NULL` | Không chọn hàng `NULL` như ý định | Dùng `WHERE col IS NULL` |
| `WHERE col <> 'X'` nhưng muốn bao gồm cả `NULL` | Hàng có `col IS NULL` bị loại vì UNKNOWN | Dùng `col <> 'X' OR col IS NULL` hoặc so sánh an toàn với `NULL` nếu DBMS hỗ trợ |
| `WHERE NOT (col = 'X')` | `NOT UNKNOWN` vẫn là UNKNOWN | Làm rõ chính sách đối với hàng `NULL` |
| Chỉ dùng `shipped_at IS NULL` cho “đơn cần gửi” | Lấy cả đơn chưa thanh toán/đã hủy | Thêm trạng thái thanh toán và hủy theo nghiệp vụ |
| `COALESCE(order_total,0) = 0` để tìm dữ liệu thiếu | Gộp thiếu giá với giá bằng 0 | Dùng `order_total IS NULL` nếu chỉ cần dữ liệu thiếu |
| `tracking_code IS NULL` | Bỏ sót chuỗi rỗng hoặc mã `N/A` | Chuẩn hóa theo đúng quy tắc nguồn trước khi lọc |
| `LEFT JOIN ... WHERE right.status IS NULL` để tìm “không có hàng liên quan” | Lấy cả hàng liên quan có `status = NULL` thật | Kiểm tra khóa phải `NOT NULL` hoặc dùng `NOT EXISTS` |
| Đưa điều kiện bảng phải của `LEFT JOIN` vào `WHERE` | Có thể làm mất các hàng trái không khớp | Quyết định rõ điều kiện thuộc `ON` hay `WHERE` |
| `NOT IN` với danh sách có `NULL` | Có thể loại mọi hàng do UNKNOWN | Cân nhắc `NOT EXISTS` khi tìm hàng thiếu quan hệ |
| Dùng `COUNT(column)` để đếm tất cả hàng | Hàng có `column IS NULL` không được tính | Dùng `COUNT(*)` |
| Ghép `AND` và `OR` không có ngoặc | Một nhóm điều kiện có thể vượt qua điều kiện loại trừ | Nhóm bằng ngoặc theo yêu cầu nghiệp vụ |

## 17. Bài tập tự luyện

Dùng hai bảng tạm `orders_null_lab` và `order_flags_null_lab` đã tạo trong bài. Nếu thực hành ở phiên kết nối mới, hãy tạo lại bảng và dữ liệu mẫu tương ứng.

### Bài 1. Đã thanh toán nhưng chưa gửi

Viết truy vấn lấy `order_id`, `customer_name` của những đơn có:

- `payment_status = 'PAID'`;
- `shipped_at IS NULL`;
- `cancelled_at IS NULL`.

Dự đoán số đơn trước khi chạy.

### Bài 2. Phân biệt trạng thái thiếu và trạng thái chờ

Viết hai truy vấn riêng: một lấy đơn có `payment_status IS NULL`, một lấy đơn có `payment_status = 'PENDING'`. Sau đó viết một truy vấn lấy cả hai nhóm nhưng **không lấy đơn đã hủy**.

### Bài 3. Phân biệt NULL, FALSE và TRUE

Với `reviewed`, trả lời ba câu hỏi:

1. Đơn nào chưa có kết quả đánh giá?
2. Đơn nào đã được đánh giá và có kết quả `FALSE`?
3. Đơn nào **chưa có kết quả `TRUE`**, bao gồm cả `FALSE` và `NULL`?

Không dùng `COALESCE` nếu phải giữ nguyên sự khác biệt giữa `NULL` và `FALSE`.

### Bài 4. Tổng tiền thiếu và bằng không

Viết câu truy vấn lấy các đơn không có `order_total`, rồi câu khác lấy đơn có `order_total = 0`. Giải thích vì sao không nên dùng chung `COALESCE(order_total,0) = 0` để trả lời hai câu hỏi.

### Bài 5. Đã gửi nhưng chưa ghi nhận ngày giao

Lọc đơn có `shipped_at IS NOT NULL`, `delivered_at IS NULL` và `cancelled_at IS NULL`. Hãy mô tả kết quả bằng lời **“chưa ghi nhận ngày giao”** và giải thích vì sao không nên khẳng định chắc chắn đơn đang trên đường giao.

### Bài 6. Thiếu bản ghi xác minh

Dùng `LEFT JOIN` hoặc `NOT EXISTS` để tìm đơn **không có hàng nào** trong `order_flags_null_lab`. So sánh với kết quả khi lọc `f.flag_status IS NULL` sau `LEFT JOIN`.

### Bài 7. Thiếu xác minh VERIFIED

Lọc những đơn **không có bản ghi `VERIFIED`**, kể cả các đơn có bản ghi xác minh trạng thái `REVIEW` hoặc `NULL`. Viết bằng `NOT EXISTS` với điều kiện `f.flag_status = 'VERIFIED'`.

### Bài 8. Chuẩn hóa mã vận đơn

Quy định các dạng `NULL`, `''`, chuỗi chỉ có khoảng trắng và `'N/A'` đều được xem là **thiếu mã vận đơn**. Viết truy vấn tìm những đơn **đã có ngày gửi nhưng vẫn thiếu mã**, xử lý `'n/a'` tương tự `'N/A'`.

### Bài 9. Đếm theo điều kiện

Trả các cột kết quả:

- `total_orders`;
- `missing_payment_status`;
- `missing_order_total`;
- `paid_without_shipped_date`.

Dùng `COUNT(*)` và `FILTER` hoặc `SUM(CASE...)`.

### Bài 10. Thiết kế bộ lọc trên giao diện

Một bộ lọc có các lựa chọn `all`, `missing`, `present` và `equals`. Hãy giải thích vì sao một tham số `NULL` không đủ để phân biệt `all` với `missing`, rồi viết điều kiện `WHERE` dùng một biến chế độ tách biệt.

## 18. Gợi ý đáp án

**Bài 1:**

```sql
SELECT order_id, customer_name
FROM orders_null_lab
WHERE payment_status = 'PAID'
  AND shipped_at IS NULL
  AND cancelled_at IS NULL
ORDER BY order_id;
```

Kết quả: **đơn 2**.

**Bài 2:**

```sql
SELECT order_id
FROM orders_null_lab
WHERE payment_status IS NULL
ORDER BY order_id;

SELECT order_id
FROM orders_null_lab
WHERE payment_status = 'PENDING'
ORDER BY order_id;

SELECT order_id
FROM orders_null_lab
WHERE cancelled_at IS NULL
  AND (payment_status IS NULL OR payment_status = 'PENDING')
ORDER BY order_id;
```

Kết quả lần lượt: **4**; **3, 8**; **3, 4, 8**.

**Bài 3:**

```sql
SELECT order_id FROM orders_null_lab
WHERE reviewed IS NULL ORDER BY order_id;

SELECT order_id FROM orders_null_lab
WHERE reviewed IS FALSE ORDER BY order_id;

SELECT order_id FROM orders_null_lab
WHERE reviewed IS NOT TRUE ORDER BY order_id;
```

Kết quả lần lượt: **2, 4, 7, 8**; **3, 5**; **2, 3, 4, 5, 7, 8**.

**Bài 4:**

```sql
SELECT order_id FROM orders_null_lab
WHERE order_total IS NULL ORDER BY order_id;

SELECT order_id FROM orders_null_lab
WHERE order_total = 0 ORDER BY order_id;
```

Kết quả: **5, 8** (thiếu tiền) và **6** (tiền bằng 0). `COALESCE` gộp hai trạng thái nên không thích hợp cho yêu cầu phân biệt.

**Bài 5:**

```sql
SELECT order_id, shipped_at
FROM orders_null_lab
WHERE shipped_at IS NOT NULL
  AND delivered_at IS NULL
  AND cancelled_at IS NULL
ORDER BY order_id;
```

Kết quả: **đơn 5**. Câu SQL xác định chưa có ngày giao được ghi vào cột, không chứng minh kiện hàng thực tế chưa đến nơi.

**Bài 6:**

```sql
SELECT o.order_id
FROM orders_null_lab AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM order_flags_null_lab AS f
    WHERE f.order_id = o.order_id
)
ORDER BY o.order_id;
```

Kết quả: **4, 7, 8**. Nếu dùng `f.flag_status IS NULL` sau `LEFT JOIN`, còn có **đơn 2** vì bản ghi của đơn này tồn tại nhưng trạng thái ở bản ghi đó là `NULL`.

**Bài 7:**

```sql
SELECT o.order_id
FROM orders_null_lab AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM order_flags_null_lab AS f
    WHERE f.order_id = o.order_id
      AND f.flag_status = 'VERIFIED'
)
ORDER BY o.order_id;
```

Kết quả: **2, 3, 4, 6, 7, 8**.

**Bài 8:**

```sql
SELECT order_id, shipped_at, tracking_code
FROM orders_null_lab
WHERE shipped_at IS NOT NULL
  AND NULLIF(
        NULLIF(UPPER(TRIM(tracking_code)), ''),
        'N/A'
      ) IS NULL
ORDER BY order_id;
```

Kết quả: **đơn 7**.

**Bài 9:**

```sql
SELECT COUNT(*) AS total_orders,
       COUNT(*) FILTER (WHERE payment_status IS NULL)
           AS missing_payment_status,
       COUNT(*) FILTER (WHERE order_total IS NULL)
           AS missing_order_total,
       COUNT(*) FILTER (
           WHERE payment_status = 'PAID'
             AND shipped_at IS NULL
             AND cancelled_at IS NULL
       ) AS paid_without_shipped_date
FROM orders_null_lab;
```

Kết quả: **8, 1, 2, 1**.

**Bài 10:** Dùng biến `filter_mode` để chỉ rõ `all` là không lọc, còn `missing` là `column IS NULL`. Một tham số `NULL` duy nhất không diễn đạt được cả hai ý định; có thể áp dụng truy vấn `WITH filter_params` ở mục 11.

Khi gặp yêu cầu lọc liên quan đến dữ liệu thiếu, hãy xác định: **cột `NULL` mang nghĩa gì, có mã thiếu khác `NULL` không, có cần giữ trạng thái chưa biết khi lọc phủ định không, và các điều kiện nghiệp vụ liên quan có được kết hợp đúng hay chưa**. Cách tiếp cận này giúp truy vấn lọc đúng nhóm dữ liệu, nhất là khi trạng thái đơn hàng thay đổi theo thời gian và khi dữ liệu từ nhiều hệ thống chưa đồng bộ đầy đủ.
