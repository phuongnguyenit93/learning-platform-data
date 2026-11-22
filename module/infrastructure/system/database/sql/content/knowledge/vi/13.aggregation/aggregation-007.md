# Tổng hợp có điều kiện bằng CASE và FILTER theo phương ngữ

Trong một báo cáo SQL, ta thường cần **nhiều chỉ số tính trên những tập hàng khác nhau** nhưng muốn trình bày cùng một hàng kết quả. Chẳng hạn: mỗi khách hàng có bao nhiêu đơn đã thanh toán, bao nhiêu đơn đang chờ, tổng tiền của đơn đã thanh toán và tỷ lệ đơn đã thanh toán là bao nhiêu? Thay vì chỉ dùng `COUNT(*)` hoặc `SUM(amount)` trên tất cả các bản ghi, ta cần **tổng hợp có điều kiện** (*conditional aggregation*).

Hai kỹ thuật quan trọng:

- **`CASE` nằm trong hàm tổng hợp**: dùng `CASE WHEN ... THEN ... ELSE ... END` để chỉ đưa một số giá trị vào `SUM`, `COUNT`, `AVG`, `MAX`, `MIN` hoặc một hàm tổng hợp khác. Đây là cách rất phổ biến để viết SQL trên nhiều hệ quản trị.
- **`FILTER (WHERE ...)` gắn với từng hàm tổng hợp**: diễn đạt trực tiếp tập hàng mà **một hàm tổng hợp cụ thể** được phép nhìn thấy. PostgreSQL, SQLite và một số hệ hỗ trợ cú pháp này; các hệ khác như SQL Server hoặc MySQL thường dùng CASE hoặc hàm chuyên dụng.

**Điểm dễ nhầm:** `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` và `COUNT(CASE WHEN ... THEN 1 END)` thường cùng đếm các hàng thỏa điều kiện **khi có hàng đầu vào**, nhưng không phải mọi tình huống đều tương đương, nhất là khi **nhóm không có hàng**, giá trị `NULL`, nhánh `ELSE`, `DISTINCT` và `LEFT JOIN` tham gia. Chọn cấu trúc nào phải dựa trên ý nghĩa chỉ số chứ không chỉ vào độ ngắn của câu SQL.

Bài học thuộc chương **Tổng hợp dữ liệu** của Database SQL, sử dụng **PostgreSQL** cho các ví dụ chạy trực tiếp và đối chiếu với **SQL Server, MySQL, SQLite, BigQuery** cùng những khác biệt khác theo phương ngữ. Những phần có cú pháp riêng đều được ghi rõ; không giả định một hàm có mặt trên mọi DBMS.

## 1. Bộ dữ liệu thực hành: khách hàng và đơn hàng

Tạo hai bảng tạm trong **cùng một phiên PostgreSQL**, đủ để minh họa bản ghi có trạng thái `NULL`, số tiền bằng 0, số tiền chưa biết và khách chưa có đơn:

```sql
CREATE TEMP TABLE demo_customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL,
    region TEXT NOT NULL
);

CREATE TEMP TABLE demo_orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES demo_customers(customer_id),
    status TEXT NULL,
    amount NUMERIC(12, 2) NULL,
    payment_method TEXT NULL,
    created_on DATE NOT NULL
);

INSERT INTO demo_customers
    (customer_id, customer_name, region)
VALUES
    (1, 'An',   'NORTH'),
    (2, 'Binh', 'SOUTH'),
    (3, 'Chi',  'NORTH'),
    (4, 'Dung', 'SOUTH'),
    (5, 'Em',   'NORTH');

INSERT INTO demo_orders
    (order_id, customer_id, status, amount, payment_method, created_on)
VALUES
    (101, 1, 'PAID',      120.00, 'CARD',     DATE '2026-08-01'),
    (102, 1, 'PENDING',    80.00, 'CASH',     DATE '2026-08-02'),
    (103, 1, 'PAID',      200.00, 'CARD',     DATE '2026-08-03'),
    (104, 2, 'PAID',        0.00, 'TRANSFER', DATE '2026-08-01'),
    (105, 2, 'CANCELED',   50.00, 'CARD',     DATE '2026-08-04'),
    (106, 2, NULL,         70.00, NULL,      DATE '2026-08-05'),
    (107, 3, 'PAID',        NULL, 'CARD',     DATE '2026-08-02'),
    (108, 3, 'REFUNDED',   40.00, 'CARD',     DATE '2026-08-06'),
    (109, 4, 'PENDING',    60.00, 'CASH',     DATE '2026-08-03'),
    (110, 4, 'PAID',       90.00, 'TRANSFER', DATE '2026-08-06');
```

Dữ liệu gốc:

| order_id | Khách | status | amount | payment_method |
| ---: | --- | --- | ---: | --- |
| 101 | An | PAID | 120.00 | CARD |
| 102 | An | PENDING | 80.00 | CASH |
| 103 | An | PAID | 200.00 | CARD |
| 104 | Binh | PAID | 0.00 | TRANSFER |
| 105 | Binh | CANCELED | 50.00 | CARD |
| 106 | Binh | NULL | 70.00 | NULL |
| 107 | Chi | PAID | NULL | CARD |
| 108 | Chi | REFUNDED | 40.00 | CARD |
| 109 | Dung | PENDING | 60.00 | CASH |
| 110 | Dung | PAID | 90.00 | TRANSFER |

Khách **Em** tồn tại trong `demo_customers` nhưng chưa có đơn ở `demo_orders`.

Từ dữ liệu này, có thể xác định bằng mắt:

- Có **10** đơn, trong đó **5 PAID**, **2 PENDING**, **1 CANCELED**, **1 REFUNDED**, **1 có status NULL**.
- Tổng `amount` của **các đơn PAID có số tiền xác định** là **410.00**: `120 + 200 + 0 + 90`. Đơn 107 có status PAID nhưng amount NULL nên không thể cộng giá trị chưa biết vào tổng.
- Có **5 đơn PAID** nhưng chỉ **4 đơn PAID có amount khác NULL**.
- Tổng của **tất cả amount khác NULL** là **710.00**, vì một đơn amount NULL.
- Có **4 khách có ít nhất một đơn PAID**; khách Em không có đơn.

Những trường hợp khác nhau về status, amount và bản ghi thiếu được cố ý giữ trong dữ liệu để làm rõ đúng-nghĩa của từng hàm tổng hợp.

## 2. Từ tổng hợp thông thường đến tổng hợp có điều kiện

Tổng hợp toàn bảng:

```sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(amount) AS orders_with_known_amount,
    SUM(amount) AS total_known_amount,
    AVG(amount) AS avg_known_amount
FROM demo_orders;
```

`COUNT(*)` đếm **10 hàng**. `COUNT(amount)` đếm **9 hàng** có amount khác NULL. `SUM(amount)` trả **710.00**. `AVG(amount)` dùng **9** giá trị xác định, không chia cho 10.

Nếu viết:

```sql
SELECT COUNT(*) AS paid_orders
FROM demo_orders
WHERE status = 'PAID';
```

ta thu được **5**. Tuy nhiên, `WHERE` này loại tất cả đơn PENDING, CANCELED, REFUNDED và status NULL **khỏi toàn bộ truy vấn**. Nếu cùng một bảng báo cáo cần thêm `pending_orders`, `canceled_orders` và `paid_amount`, không thể tiếp tục tính chúng từ tập hàng đã bị WHERE loại.

**Tổng hợp có điều kiện** chuyển điều kiện vào **từng hàm tổng hợp**, để mỗi chỉ số có phạm vi lọc riêng:

```sql
SELECT
    COUNT(*) AS all_orders,
    SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END) AS paid_orders,
    SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END) AS pending_orders,
    SUM(CASE WHEN status = 'CANCELED' THEN 1 ELSE 0 END) AS canceled_orders
FROM demo_orders;
```

Kết quả: `all_orders = 10`, `paid_orders = 5`, `pending_orders = 2`, `canceled_orders = 1`. Các cột được tính trong **cùng một kết quả tổng hợp**, nhưng mỗi cột trả lời một câu hỏi riêng.

### 2.1. Cấu trúc logic

```text
                   10 hàng demo_orders
                           |
                           v
                    Nhóm / tập đầu vào
                           |
          +----------------+----------------+
          |                |                |
          v                v                v
      COUNT(*)      Tổng hợp PAID     Tổng hợp PENDING
          |                |                |
          +----------------+----------------+
                           |
                           v
          Một hàng với nhiều chỉ số có ý nghĩa
```

Điều kiện ở **bên trong hàm tổng hợp** khác với điều kiện `WHERE` của cả truy vấn. Về mặt kế hoạch vật lý, DBMS có thể thực hiện các phép tổng hợp theo nhiều cách; sơ đồ là cách đọc **ngữ nghĩa logic**, không phải cam kết “chỉ quét dữ liệu đúng một lần” trong mọi kế hoạch.

## 3. CASE trong hàm tổng hợp: hai mô hình đếm phổ biến

`CASE` có dạng thường dùng:

```sql
CASE
    WHEN condition THEN value_when_true
    ELSE value_otherwise
END
```

Nếu bỏ `ELSE`, các trường hợp không chọn nhánh WHEN sẽ trả **NULL**:

```sql
CASE WHEN status = 'PAID' THEN 1 END
```

Điều kiện `WHEN` chỉ chọn nhánh khi kết quả là **TRUE**; nếu FALSE hoặc **UNKNOWN** do NULL, nhánh WHEN không được chọn.

### 3.1. Cách A — SUM với 1 và 0

```sql
SELECT
    SUM(
        CASE
            WHEN status = 'PAID' THEN 1
            ELSE 0
        END
    ) AS paid_count
FROM demo_orders;
-- 5
```

Mỗi hàng PAID đóng góp **1**, hàng không PAID (bao gồm status NULL) đóng góp **0**. Tổng các giá trị ấy là số đơn PAID.

| status | Điều kiện `status = 'PAID'` | CASE trả về |
| --- | --- | ---: |
| PAID | TRUE | 1 |
| PENDING | FALSE | 0 |
| CANCELED | FALSE | 0 |
| NULL | UNKNOWN | 0 |

`ELSE 0` làm rõ rằng **hàng không khớp đóng góp số không**, không phải NULL.

### 3.2. Cách B — COUNT với 1 và NULL

```sql
SELECT
    COUNT(
        CASE
            WHEN status = 'PAID' THEN 1
        END
    ) AS paid_count
FROM demo_orders;
-- 5
```

`COUNT(expression)` chỉ đếm các kết quả **khác NULL**. Với PAID, CASE trả 1; với các hàng khác, CASE trả NULL và không được COUNT tính. Vì vậy trả **5**.

Không nên viết:

```sql
-- Sai nếu muốn đếm số đơn PAID.
SELECT COUNT(
    CASE WHEN status = 'PAID' THEN 1 ELSE 0 END
)
FROM demo_orders;
-- 10, vì cả 1 và 0 đều KHÁC NULL.
```

Đây là lỗi rất phổ biến. **COUNT không cộng giá trị**, mà đếm xem biểu thức có giá trị được xác định hay không. Số 0 vẫn được đếm như số 1.

### 3.3. Cách C — SUM(CASE ... THEN 1 END)

```sql
SELECT
    SUM(CASE WHEN status = 'PAID' THEN 1 END) AS paid_count
FROM demo_orders;
-- 5 trong dữ liệu mẫu có đơn PAID.
```

SUM bỏ qua NULL, nên nếu có ít nhất một hàng PAID, kết quả bằng số hàng khớp. Nhưng **nếu không có hàng PAID**, mọi giá trị CASE đều NULL và **SUM trả NULL**, không phải 0. Vì vậy, cấu trúc này không hoàn toàn tương đương với `COUNT(CASE...)` hoặc `SUM(CASE ... ELSE 0 END)`.

Muốn diễn đạt một chỉ số đếm luôn trả 0 khi không có hàng khớp, **COUNT(CASE WHEN ... THEN 1 END)** thường trực tiếp hơn, đặc biệt khi tập đầu vào có thể rỗng.

## 4. Phân biệt tập có hàng nhưng không khớp và tập hoàn toàn rỗng

Đây là khác biệt giữa hành vi **của COUNT** và **của SUM**:

```sql
SELECT
    COUNT(CASE WHEN status = 'RETURNED' THEN 1 END) AS count_case,
    SUM(CASE WHEN status = 'RETURNED' THEN 1 ELSE 0 END) AS sum_else_zero,
    SUM(CASE WHEN status = 'RETURNED' THEN 1 END) AS sum_without_else
FROM demo_orders;
```

Không có trạng thái `RETURNED` trong dữ liệu mẫu:

| Biểu thức | Kết quả | Lý do |
| --- | --- | --- |
| `COUNT(CASE WHEN ... THEN 1 END)` | **0** | Không có giá trị khác NULL được đếm |
| `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` | **0** | Có 10 hàng; mỗi hàng đóng góp số 0 |
| `SUM(CASE WHEN ... THEN 1 END)` | **NULL** | Không có giá trị đầu vào khác NULL cho SUM |

Nếu thêm một điều kiện **WHERE loại mọi hàng**:

```sql
SELECT
    COUNT(CASE WHEN status = 'PAID' THEN 1 END) AS count_case,
    SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END) AS sum_case
FROM demo_orders
WHERE order_id < 0;
```

Tập kết quả đầu vào giờ **không có hàng nào**. `COUNT(...)` vẫn trả **0**, còn `SUM(...)` trả **NULL**, ngay cả khi CASE có `ELSE 0`: **không có hàng để tạo ra số 0**.

Nếu cần giá trị mặc định theo nghiệp vụ, có thể:

```sql
SELECT
    COALESCE(
        SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END),
        0
    ) AS paid_count
FROM demo_orders
WHERE order_id < 0;
-- 0
```

Nhưng không nên dùng COALESCE một cách vô điều kiện với các phép tổng hợp mà NULL có nghĩa quan trọng, ví dụ **doanh thu đã biết** khác **doanh thu chưa có dữ liệu**.

## 5. SUM có điều kiện: chỉ tính giá trị của nhóm phù hợp

Đếm số hàng và cộng số tiền là hai câu hỏi khác nhau:

```sql
SELECT
    SUM(CASE
        WHEN status = 'PAID' THEN amount
    END) AS paid_amount,
    SUM(CASE
        WHEN status = 'PENDING' THEN amount
    END) AS pending_amount,
    SUM(CASE
        WHEN status = 'REFUNDED' THEN amount
    END) AS refunded_amount
FROM demo_orders;
```

Kết quả theo dữ liệu mẫu:

| Chỉ số | Kết quả | Giải thích |
| --- | ---: | --- |
| paid_amount | 410.00 | Các amount PAID có giá trị: 120, 200, 0, 90; một amount PAID NULL |
| pending_amount | 140.00 | 80 + 60 |
| refunded_amount | 40.00 | amount của đơn REFUNDED |

Ở đây không cần `ELSE 0`: hàng không khớp được CASE trả NULL và bị SUM bỏ qua. Khi **không có đơn nào khớp**, kết quả SUM là NULL, có thể là cách biểu đạt đúng “không có số liệu để cộng”.

### 5.1. Khi nào dùng ELSE 0 trong SUM?

```sql
SELECT
    SUM(CASE
        WHEN status = 'PAID' THEN amount
        ELSE 0
    END) AS paid_amount
FROM demo_orders;
```

Với dữ liệu hiện tại, kết quả vẫn là **410.00**. Sự khác biệt xuất hiện khi không có hàng PAID nhưng vẫn có hàng không PAID: `ELSE 0` cung cấp các giá trị số không để SUM trả **0**, thay vì NULL.

Tuy nhiên, nếu có đơn PAID nhưng **amount NULL**, số tiền của đơn ấy vẫn chưa biết; `ELSE 0` không khiến `THEN amount` trở thành 0. Khi các hàng PAID đều có amount NULL nhưng cũng tồn tại hàng không PAID, số 0 của các hàng không PAID có thể khiến báo cáo trả **0**, dễ che mất vấn đề dữ liệu tiền của đơn PAID chưa được ghi.

**Quy tắc khuyến nghị:** dùng `SUM(CASE WHEN predicate THEN amount END)` để chọn tập giá trị, và chỉ dùng `COALESCE(..., 0)` ở nơi đã quyết định rõ “không có tổng xác định thì hiển thị 0”.

### 5.2. Kiểm tra độ đầy đủ dữ liệu cùng với tổng tiền

```sql
SELECT
    COUNT(CASE WHEN status = 'PAID' THEN 1 END) AS paid_order_count,
    COUNT(CASE WHEN status = 'PAID' THEN amount END)
        AS paid_orders_with_amount,
    COUNT(CASE WHEN status = 'PAID' AND amount IS NULL THEN 1 END)
        AS paid_orders_missing_amount,
    SUM(CASE WHEN status = 'PAID' THEN amount END)
        AS paid_known_amount
FROM demo_orders;
```

Kết quả:

- `paid_order_count = 5`
- `paid_orders_with_amount = 4`
- `paid_orders_missing_amount = 1`
- `paid_known_amount = 410.00`

Báo cáo tiền chỉ có **410.00 từ bốn đơn đã biết amount**. Không được tuyên bố đây chắc chắn là doanh thu đầy đủ của năm đơn PAID khi một đơn còn thiếu số tiền.

## 6. AVG, MIN, MAX và các loại tổng hợp có điều kiện khác

### 6.1. Trung bình trên những hàng thỏa điều kiện

```sql
SELECT
    AVG(CASE WHEN status = 'PAID' THEN amount END)
        AS avg_known_paid_amount
FROM demo_orders;
```

AVG bỏ qua NULL. Bốn đơn PAID có số tiền xác định đóng góp **410 / 4 = 102.50**. Một đơn PAID amount NULL không tham gia mẫu số.

Nếu vô tình viết:

```sql
SELECT
    AVG(CASE
        WHEN status = 'PAID' THEN amount
        ELSE 0
    END) AS misleading_average
FROM demo_orders;
```

thì trung bình được tính trên **9 giá trị không NULL** do những đơn không PAID đóng góp 0 và đơn PAID amount NULL bị bỏ qua. Đây **không còn là giá trị trung bình của đơn PAID**, nên kết quả khác hẳn.

Nếu muốn trung bình trên **số đơn PAID** và coi số tiền NULL như 0 theo chính sách đã xác nhận, phải diễn đạt chính sách này riêng:

```sql
SELECT
    AVG(CASE
        WHEN status = 'PAID' THEN COALESCE(amount, 0)
    END) AS avg_paid_with_missing_assumed_zero
FROM demo_orders;
-- 410 / 5 = 82.00 với giả định amount NULL bằng 0.
```

Đây là một **giả định khác**, không phải cách mặc định của SQL.

### 6.2. Giá trị lớn nhất, nhỏ nhất của nhóm

```sql
SELECT
    MAX(CASE WHEN status = 'PAID' THEN amount END)
        AS largest_known_paid_order,
    MIN(CASE WHEN status = 'PAID' THEN amount END)
        AS smallest_known_paid_order
FROM demo_orders;
```

Kết quả `MAX = 200.00`, `MIN = 0.00`. Việc amount bằng 0 ở đơn PAID của Binh hoàn toàn hợp lệ về mặt dữ liệu mẫu và được MIN xem là giá trị số, không bị nhầm với NULL.

Các hàm tổng hợp thông thường như SUM, AVG, MIN, MAX loại NULL ở đầu vào. Mỗi hàm có cách xử lý riêng khi không có giá trị khác NULL; thông thường các hàm trên trả NULL, còn COUNT trả 0.

## 7. FILTER (WHERE ...): điều kiện của từng hàm tổng hợp

Trong **PostgreSQL**, cú pháp:

```sql
aggregate_function(arguments) FILTER (WHERE condition)
```

cho phép mỗi hàm tổng hợp sử dụng **chỉ các hàng mà điều kiện của nó TRUE**. Các hàm tổng hợp khác trong cùng SELECT có thể dùng tập hàng khác.

```sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_orders,
    COUNT(*) FILTER (WHERE status = 'PENDING') AS pending_orders,
    COUNT(*) FILTER (WHERE status = 'CANCELED') AS canceled_orders,
    COUNT(*) FILTER (WHERE status IS NULL) AS missing_status_orders
FROM demo_orders;
```

Kết quả lần lượt là **10, 5, 2, 1, 1**.

**FILTER không phải một WHERE thứ hai cho toàn bộ SELECT.** Nó chỉ giới hạn các hàng được chuyển tới **hàm tổng hợp gắn ngay trước FILTER**. Câu `COUNT(*)` không có FILTER vẫn nhìn toàn bộ 10 hàng.

### 7.1. Viết SUM/AVG dễ đọc hơn

```sql
SELECT
    SUM(amount) FILTER (WHERE status = 'PAID') AS paid_amount,
    SUM(amount) FILTER (WHERE status = 'PENDING') AS pending_amount,
    AVG(amount) FILTER (WHERE status = 'PAID') AS avg_paid_amount,
    MAX(amount) FILTER (WHERE status = 'PAID') AS max_paid_amount
FROM demo_orders;
```

Kết quả: **410.00**, **140.00**, **102.50**, **200.00**. Trong trường hợp này, `FILTER` thường dễ đọc hơn nhiều biểu thức CASE lồng trong hàm tổng hợp vì điều kiện lọc và đối số `amount` được tách rõ.

### 7.2. FILTER và NULL

```sql
SELECT
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_orders,
    COUNT(amount) FILTER (WHERE status = 'PAID')
        AS paid_orders_with_amount,
    SUM(amount) FILTER (WHERE status = 'PAID') AS paid_amount
FROM demo_orders;
```

`FILTER` trước tiên giữ **5 hàng PAID**, rồi:

- `COUNT(*)` đếm cả **5** hàng;
- `COUNT(amount)` đếm **4** hàng vì một amount là NULL;
- `SUM(amount)` cộng bốn giá trị xác định để được **410.00**.

**FILTER không thay đổi quy tắc xử lý NULL của hàm tổng hợp**. Một điều kiện FILTER trả UNKNOWN do NULL không được chọn (giống WHERE); nếu hàng đã qua FILTER nhưng đối số hàm là NULL, COUNT(cột), SUM và AVG vẫn xử lý theo quy tắc của mình.

### 7.3. Khi không có hàng thỏa FILTER

```sql
SELECT
    COUNT(*) FILTER (WHERE status = 'RETURNED') AS returned_count,
    SUM(amount) FILTER (WHERE status = 'RETURNED') AS returned_amount
FROM demo_orders;
```

Kết quả **0** và **NULL**, vì:

- COUNT đếm số hàng phù hợp, không có thì trả 0.
- SUM không có giá trị nào để cộng, nên trả NULL.

Nếu chính sách báo cáo coi “không có đơn RETURNED” là tổng tiền **0**, viết rõ:

```sql
SELECT
    COALESCE(
        SUM(amount) FILTER (WHERE status = 'RETURNED'),
        0
    ) AS returned_amount
FROM demo_orders;
```

Vẫn cần phân biệt **không có đơn** và **có đơn nhưng mọi amount NULL** trong những nghiệp vụ mà thiếu số liệu phải được cảnh báo.

## 8. Đối chiếu CASE và FILTER: tương đương khi nào?

Với PostgreSQL và các hệ hỗ trợ FILTER:

| Mục tiêu | CASE trong aggregate | FILTER |
| --- | --- | --- |
| Đếm đơn PAID | `COUNT(CASE WHEN status = 'PAID' THEN 1 END)` | `COUNT(*) FILTER (WHERE status = 'PAID')` |
| Cộng amount PAID | `SUM(CASE WHEN status = 'PAID' THEN amount END)` | `SUM(amount) FILTER (WHERE status = 'PAID')` |
| Trung bình amount PAID | `AVG(CASE WHEN status = 'PAID' THEN amount END)` | `AVG(amount) FILTER (WHERE status = 'PAID')` |
| Lớn nhất amount PAID | `MAX(CASE WHEN status = 'PAID' THEN amount END)` | `MAX(amount) FILTER (WHERE status = 'PAID')` |
| Đếm khách khác nhau có đơn PAID | `COUNT(DISTINCT CASE WHEN status = 'PAID' THEN customer_id END)` | `COUNT(DISTINCT customer_id) FILTER (WHERE status = 'PAID')` |

Các cặp trên có cùng ngữ nghĩa cho các tập dữ liệu và phép tổng hợp đã nêu. **Nhánh ELSE ngầm là NULL** đóng vai trò quan trọng: đừng tự thêm `ELSE 0` rồi coi luôn tương đương với FILTER.

### 8.1. Một trường hợp không tương đương dễ bị che giấu

```sql
SELECT
    COUNT(CASE WHEN status = 'PAID' THEN amount END) AS a,
    COUNT(*) FILTER (WHERE status = 'PAID') AS b
FROM demo_orders;
```

Kết quả `a = 4`, `b = 5`. Tại sao? Vì `a` yêu cầu **status PAID và amount khác NULL**, còn `b` chỉ cần **status PAID** để đếm hàng.

Muốn tương đương với `COUNT(amount) FILTER (WHERE status = 'PAID')`, dùng:

```sql
COUNT(CASE WHEN status = 'PAID' THEN amount END)
```

Muốn tương đương với `COUNT(*) FILTER (WHERE status = 'PAID')`, dùng:

```sql
COUNT(CASE WHEN status = 'PAID' THEN 1 END)
```

Chọn biểu thức CASE **khác NULL ở nhánh TRUE** nếu muốn đếm hàng, không nhất thiết dùng cột có thể NULL.

### 8.2. COUNT DISTINCT có điều kiện

```sql
SELECT
    COUNT(DISTINCT customer_id)
        FILTER (WHERE status = 'PAID') AS paid_customers,
    COUNT(DISTINCT CASE
        WHEN status = 'PAID' THEN customer_id
    END) AS paid_customers_case
FROM demo_orders;
```

Hai kết quả đều là **4**: An, Binh, Chi, Dung. Nếu An có ba đơn PAID, khách An vẫn chỉ được tính một lần trong COUNT DISTINCT.

Khi xây dựng chỉ số khác nhau, cần hỏi rõ **đếm đơn**, **đếm khách có đơn**, hay **đếm khách duy nhất có đơn PAID**. Cùng một điều kiện status nhưng độ hạt đối tượng khác nhau cho chỉ số khác nhau.

### 8.3. FILTER không chỉ dành cho COUNT và SUM

Trong PostgreSQL, các aggregate hỗ trợ FILTER có thể bao gồm các hàm tạo tập giá trị:

```sql
SELECT
    ARRAY_AGG(order_id ORDER BY order_id)
        FILTER (WHERE status = 'PAID') AS paid_order_ids
FROM demo_orders;
```

Kết quả là một mảng chứa các ID PAID theo thứ tự: **101, 103, 104, 107, 110**. Hàm `ARRAY_AGG` có thể trả NULL nếu không có giá trị đầu vào, khác `COUNT`. Khả năng gắn FILTER vào hàm tổng hợp phụ thuộc tính năng DBMS; không phải hệ nào cũng hỗ trợ ARRAY_AGG hay cùng cú pháp sắp xếp bên trong aggregate.

## 9. GROUP BY: nhiều chỉ số trên mỗi nhóm

Trong thực tế, báo cáo thường cần **một hàng cho mỗi khách**, mỗi vùng hoặc mỗi tháng. Kết hợp GROUP BY với CASE:

```sql
SELECT
    customer_id,
    COUNT(*) AS total_orders,
    COUNT(CASE WHEN status = 'PAID' THEN 1 END) AS paid_orders,
    COUNT(CASE WHEN status = 'PENDING' THEN 1 END) AS pending_orders,
    SUM(CASE WHEN status = 'PAID' THEN amount END) AS paid_amount
FROM demo_orders
GROUP BY customer_id
ORDER BY customer_id;
```

Trên PostgreSQL, có thể viết ngắn hơn bằng FILTER:

```sql
SELECT
    customer_id,
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_orders,
    COUNT(*) FILTER (WHERE status = 'PENDING') AS pending_orders,
    SUM(amount) FILTER (WHERE status = 'PAID') AS paid_amount
FROM demo_orders
GROUP BY customer_id
ORDER BY customer_id;
```

Cả hai cho cùng kết quả trên dữ liệu mẫu:

| customer_id | total_orders | paid_orders | pending_orders | paid_amount |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 3 | 2 | 1 | 320.00 |
| 2 | 3 | 1 | 0 | 0.00 |
| 3 | 2 | 1 | 0 | NULL |
| 4 | 2 | 1 | 1 | 90.00 |

Khách **5 (Em)** không xuất hiện, vì không có hàng ở bảng demo_orders để hình thành một nhóm customer_id = 5. Đây là hành vi đúng khi GROUP BY chỉ dựa trên bảng đơn hàng.

### 9.1. Sự khác nhau giữa số tiền bằng 0 và chưa biết

Hai dòng đặc biệt:

- Binh có một đơn PAID với **amount = 0**: paid_amount là **0.00**.
- Chi có một đơn PAID với **amount = NULL**: paid_amount là **NULL**.

Đó không phải hai tình huống tương đương. Nếu cứ COALESCE cả hai về 0 mà không có chỉ số chất lượng, báo cáo có thể khiến người đọc tưởng rằng tiền của Chi đã được xác nhận bằng 0. Một bảng báo cáo đáng tin cậy có thể hiển thị cả `paid_orders_missing_amount` để phân biệt.

## 10. LEFT JOIN: giữ cả nhóm không có bản ghi con

Muốn hiển thị **cả khách chưa có đơn**, phải bắt đầu từ `demo_customers` và LEFT JOIN:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS total_orders,
    COUNT(o.order_id) FILTER (WHERE o.status = 'PAID')
        AS paid_orders,
    COUNT(o.order_id) FILTER (WHERE o.status = 'PENDING')
        AS pending_orders,
    SUM(o.amount) FILTER (WHERE o.status = 'PAID')
        AS paid_amount
FROM demo_customers AS c
LEFT JOIN demo_orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Kết quả:

| Khách | total_orders | paid_orders | pending_orders | paid_amount |
| --- | ---: | ---: | ---: | ---: |
| An | 3 | 2 | 1 | 320.00 |
| Binh | 3 | 1 | 0 | 0.00 |
| Chi | 2 | 1 | 0 | NULL |
| Dung | 2 | 1 | 1 | 90.00 |
| Em | 0 | 0 | 0 | NULL |

`LEFT JOIN` tạo một **hàng bù** có các cột `o.*` là NULL cho khách Em. Vì vậy:

- `COUNT(o.order_id)` trả **0**, vì không có order_id thật.
- `COUNT(*)` trả **1** cho nhóm Em, do vẫn có một hàng kết quả LEFT JOIN.
- `SUM(o.amount) FILTER (WHERE o.status = 'PAID')` trả **NULL**, vì không có amount PAID để cộng.

### 10.1. Lỗi COUNT(*) sau LEFT JOIN

```sql
-- Không đúng nếu muốn đếm số đơn của mọi khách:
SELECT
    c.customer_name,
    COUNT(*) AS order_count
FROM demo_customers AS c
LEFT JOIN demo_orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name;
```

Khách Em nhận `order_count = 1` dù không có đơn. Sửa thành `COUNT(o.order_id)` với `order_id` là khóa chính NOT NULL của bảng đơn.

### 10.2. Đếm NULL của cột con mà không đếm hàng bù

```sql
SELECT
    c.customer_name,
    COUNT(o.order_id) FILTER (
        WHERE o.status IS NULL
    ) AS orders_with_missing_status
FROM demo_customers AS c
LEFT JOIN demo_orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Với bảng mẫu, Binh có **1** đơn status NULL (106), còn Em có **0** đơn status NULL vì không có đơn thật. Dùng `COUNT(o.order_id)` giúp không đếm hàng bù. Nếu viết `COUNT(*) FILTER (WHERE o.status IS NULL)`, hàng bù của Em **cũng thỏa `o.status IS NULL`** nên trả 1 sai với mục đích “đếm đơn có trạng thái thiếu”.

Cách CASE tương đương:

```sql
COUNT(CASE
    WHEN o.order_id IS NOT NULL AND o.status IS NULL THEN 1
END)
```

Đây là bài học quan trọng: khi kết hợp NULL với LEFT JOIN, luôn phân biệt **cột NULL của bản ghi thật** và **NULL do không có bản ghi khớp**.

### 10.3. WHERE ở bảng con có thể làm mất nhóm rỗng

```sql
-- Có thể làm khách không có đơn PAID biến mất:
SELECT c.customer_name, COUNT(o.order_id)
FROM demo_customers AS c
LEFT JOIN demo_orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
GROUP BY c.customer_id, c.customer_name;
```

`WHERE o.status = 'PAID'` loại hàng bù NULL của Em và những khách chỉ có đơn khác PAID, khiến LEFT JOIN có hiệu ứng như INNER JOIN đối với điều kiện này. Nếu mục tiêu là **giữ mọi khách và đếm đơn PAID**, hãy dùng **FILTER** hoặc **CASE bên trong COUNT**, thay vì đẩy điều kiện trạng thái xuống WHERE.

Một lựa chọn khác là đặt trạng thái trong ON:

```sql
SELECT
    c.customer_name,
    COUNT(o.order_id) AS paid_orders
FROM demo_customers AS c
LEFT JOIN demo_orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Câu này giữ mọi khách và đếm PAID, nhưng vì **nguồn JOIN đã chỉ gồm đơn PAID**, nó không còn phù hợp nếu cũng muốn tính tổng **mọi đơn**, PENDING hay REFUNDED từ cùng alias `o`. Khi cần nhiều chỉ số có điều kiện khác nhau, FILTER/CASE trong aggregate thường thể hiện cấu trúc rõ hơn.

## 11. CASE, FILTER và WHERE/HAVING khác nhau về phạm vi

Ba vị trí đặt điều kiện có mục đích khác nhau:

| Vị trí điều kiện | Phạm vi tác động | Ví dụ |
| --- | --- | --- |
| `WHERE` của SELECT | Loại hàng **trước khi tổng hợp** | Chỉ xét đơn từ tháng 8 |
| `FILTER (WHERE ...)` của aggregate | Chỉ chọn hàng cho **một hàm tổng hợp** | Đếm PAID nhưng vẫn tính COUNT tất cả |
| `CASE` bên trong aggregate | Biến đổi đối số của **một hàm** theo điều kiện | PAID đóng góp amount, hàng khác NULL |
| `HAVING` | Giữ hoặc loại **các nhóm sau tổng hợp** | Chỉ giữ khách có từ 2 đơn PAID |

Ví dụ báo cáo đơn tháng 8 và lọc khách có từ hai đơn PAID:

```sql
SELECT
    customer_id,
    COUNT(*) AS august_orders,
    COUNT(*) FILTER (WHERE status = 'PAID') AS august_paid_orders
FROM demo_orders
WHERE created_on >= DATE '2026-08-01'
  AND created_on <  DATE '2026-09-01'
GROUP BY customer_id
HAVING COUNT(*) FILTER (WHERE status = 'PAID') >= 2
ORDER BY customer_id;
```

Với dữ liệu mẫu, chỉ khách **An** có hai đơn PAID trong khoảng thời gian này. `WHERE` giới hạn tập đơn theo tháng, FILTER đếm PAID trong tập ấy, HAVING loại các nhóm không đạt ngưỡng.

Trong SQL Server/MySQL, biểu thức HAVING có thể dùng:

```sql
HAVING SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END) >= 2
```

Các dialect có thể hỗ trợ hoặc không hỗ trợ tham chiếu alias trong HAVING; nếu cần tính di động, viết lại biểu thức tổng hợp hoặc dùng CTE để lọc ở truy vấn ngoài. Không nhầm HAVING với WHERE chỉ vì đều chứa điều kiện.

## 12. Tỷ lệ có điều kiện và phép chia an toàn

Muốn tính **tỷ lệ đơn PAID trên toàn bộ đơn**, hai chỉ số phải cùng miền dữ liệu:

```sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_orders,
    ROUND(
        100.0 * (COUNT(*) FILTER (WHERE status = 'PAID'))
        / NULLIF(COUNT(*), 0),
        2
    ) AS paid_percent
FROM demo_orders;
```

Ở bảng mẫu, `5 / 10 * 100 = 50.00%`.

**Vì sao dùng `100.0` và `NULLIF`?**

- `100.0` giữ phép tính ở kiểu số thập phân phù hợp trong ví dụ PostgreSQL, tránh sai do chia số nguyên ở những DBMS/quy tắc kiểu có phép chia nguyên.
- `NULLIF(COUNT(*), 0)` trả NULL nếu mẫu số bằng 0, tránh chia cho 0. Khi tập dữ liệu hoàn toàn rỗng, tỷ lệ là **không xác định**, không tự động bằng 0%.
- `ROUND(..., 2)` diễn đạt cách trình bày hai chữ số sau dấu thập phân; quy tắc làm tròn và kiểu số của ROUND có thể khác tùy DBMS.

### 12.1. Tỷ lệ trên từng khách, kể cả khách không có đơn

```sql
SELECT
    c.customer_name,
    COUNT(o.order_id) AS total_orders,
    COUNT(o.order_id) FILTER (WHERE o.status = 'PAID')
        AS paid_orders,
    ROUND(
        100.0 * (
            COUNT(o.order_id) FILTER (WHERE o.status = 'PAID')
        ) / NULLIF(COUNT(o.order_id), 0),
        2
    ) AS paid_percent
FROM demo_customers AS c
LEFT JOIN demo_orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Kết quả tương ứng:

| Khách | Tổng đơn | Đơn PAID | paid_percent |
| --- | ---: | ---: | ---: |
| An | 3 | 2 | 66.67 |
| Binh | 3 | 1 | 33.33 |
| Chi | 2 | 1 | 50.00 |
| Dung | 2 | 1 | 50.00 |
| Em | 0 | 0 | NULL |

Với Em, tỷ lệ **0/0 không xác định**. Nếu sản phẩm muốn hiển thị “—”, “Không có dữ liệu” hoặc số 0 theo một chính sách báo cáo riêng, hãy xử lý tại tầng hiển thị hoặc CASE tường minh, không âm thầm cho rằng tỷ lệ có giá trị toán học bằng 0.

### 12.2. Mẫu số phải phản ánh yêu cầu nghiệp vụ

Ví dụ có một đơn status NULL. Nếu KPI là “tỷ lệ PAID trên **các đơn đã biết trạng thái**”, mẫu số phải là `COUNT(status)` hoặc `COUNT(*) FILTER (WHERE status IS NOT NULL)`, không phải `COUNT(*)`.

```sql
SELECT
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid,
    COUNT(status) AS known_status_orders,
    ROUND(
        100.0 * (COUNT(*) FILTER (WHERE status = 'PAID'))
        / NULLIF(COUNT(status), 0),
        2
    ) AS paid_among_known_percent
FROM demo_orders;
```

Trong dữ liệu mẫu, có 9 đơn đã biết trạng thái; tỷ lệ này là **5/9 ≈ 55.56%**, khác tỷ lệ 50% trên mọi đơn. Cả hai đều có thể đúng, tùy **câu hỏi báo cáo**. Quan trọng là tên metric và mẫu số phải nhất quán.

## 13. Đếm DISTINCT và các chỉ số nhiều chiều

### 13.1. Số khách đã thanh toán ít nhất một đơn

```sql
SELECT
    COUNT(DISTINCT customer_id)
        FILTER (WHERE status = 'PAID') AS paid_customers,
    COUNT(DISTINCT CASE
        WHEN status = 'PAID' THEN customer_id
    END) AS paid_customers_with_case
FROM demo_orders;
```

Hai cách đều trả **4**. Nếu chỉ dùng `COUNT(*) FILTER (WHERE status='PAID')`, kết quả là **5** vì đếm đơn chứ không đếm khách.

### 13.2. Tổng hợp theo vùng

```sql
SELECT
    c.region,
    COUNT(o.order_id) AS total_orders,
    COUNT(o.order_id) FILTER (WHERE o.status = 'PAID')
        AS paid_orders,
    COUNT(DISTINCT c.customer_id) FILTER (
        WHERE o.status = 'PAID'
    ) AS paying_customers,
    SUM(o.amount) FILTER (WHERE o.status = 'PAID')
        AS paid_known_amount
FROM demo_customers AS c
LEFT JOIN demo_orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.region
ORDER BY c.region;
```

Diễn giải:

- Vùng NORTH gồm An, Chi, Em: 5 đơn thật, 3 đơn PAID, 2 khách có đơn PAID, tổng amount PAID biết được là **320.00** (amount PAID của Chi còn NULL).
- Vùng SOUTH gồm Binh, Dung: 5 đơn thật, 2 đơn PAID, 2 khách có đơn PAID, tổng amount PAID biết được là **90.00**.

COUNT DISTINCT theo `c.customer_id` tránh đếm An hai lần do có hai đơn PAID. Cần chọn đúng khóa định danh (khóa khách, không phải tên người), vì tên có thể trùng.

### 13.3. Tổng hợp theo tháng với nhiều trạng thái

Với PostgreSQL:

```sql
SELECT
    DATE_TRUNC('month', created_on)::DATE AS order_month,
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_orders,
    COUNT(*) FILTER (WHERE status = 'PENDING') AS pending_orders,
    SUM(amount) FILTER (WHERE status = 'PAID') AS paid_amount
FROM demo_orders
GROUP BY DATE_TRUNC('month', created_on)::DATE
ORDER BY order_month;
```

Dữ liệu mẫu chỉ có tháng 08/2026, nên kết quả có một hàng. Trong dữ liệu sản xuất, nếu muốn hiển thị **những tháng không có đơn** với số 0, phải tạo danh sách tháng (ví dụ bằng `generate_series` ở PostgreSQL) rồi LEFT JOIN kết quả tổng hợp, hoặc dùng một bảng lịch. GROUP BY đơn hàng thông thường **không tự sinh ra tháng rỗng**.

Ngày giờ có múi giờ cần được quy về **múi giờ báo cáo** trước khi phân nhóm theo ngày/tháng; ví dụ dùng DATE trong bảng mẫu không có vấn đề chuyển ngày theo múi giờ.

## 14. FILTER trên aggregate cửa sổ: một khả năng hữu ích

PostgreSQL cho phép FILTER với **hàm tổng hợp được dùng như window aggregate**:

```sql
SELECT
    order_id,
    customer_id,
    status,
    COUNT(*) FILTER (WHERE status = 'PAID')
        OVER (PARTITION BY customer_id) AS paid_orders_of_customer
FROM demo_orders
ORDER BY customer_id, order_id;
```

Truy vấn không gom các đơn thành một hàng mỗi khách: **mỗi đơn vẫn xuất hiện**, kèm một cột cho biết tổng số đơn PAID của khách tương ứng trong partition. Với An, cả ba hàng đơn 101, 102, 103 cùng mang `paid_orders_of_customer = 2`.

Một cách dùng CASE mang ý nghĩa tương đương:

```sql
SELECT
    order_id,
    customer_id,
    COUNT(CASE WHEN status = 'PAID' THEN 1 END)
        OVER (PARTITION BY customer_id) AS paid_orders_of_customer
FROM demo_orders
ORDER BY customer_id, order_id;
```

Điểm cần lưu ý: `FILTER` gắn với **aggregate**, không phải một tùy chọn chèn bừa vào mọi hàm cửa sổ như `ROW_NUMBER()`. Những hàm cửa sổ không phải aggregate có quy tắc riêng, và khả năng hỗ trợ FILTER/OVER khác nhau giữa DBMS.

## 15. Chọn CASE hay FILTER theo phương ngữ SQL

Khả năng hỗ trợ không thống nhất:

| DBMS / dialect | `SUM/COUNT(CASE ...)` | `aggregate(...) FILTER (WHERE ...)` | Cách dùng thường gặp |
| --- | --- | --- | --- |
| **PostgreSQL** | Có | Có, từ PostgreSQL 9.4 | FILTER khi cần nhiều chỉ số, CASE cho logic ánh xạ phức tạp |
| **SQLite** | Có | Có, từ SQLite 3.30.0 | FILTER trên aggregate; chú ý hệ kiểu và phiên bản SQLite của ứng dụng |
| **DuckDB** | Có | Có | FILTER thuận tiện cho báo cáo và pivot có điều kiện |
| **Microsoft SQL Server** | Có | Không phải cú pháp T-SQL thông dụng được hỗ trợ | SUM/COUNT với CASE, hoặc PIVOT cho bài toán phù hợp |
| **MySQL** | Có | Không hỗ trợ dạng FILTER chuẩn trong cú pháp tổng hợp thông dụng | SUM/COUNT với CASE; có thể dùng IF() trong hệ này |
| **BigQuery (GoogleSQL)** | Có | Không giả định cú pháp FILTER chuẩn | COUNTIF, IF/CASE trong các aggregate |
| **Oracle Database** | Có | Khả năng và cú pháp tùy phiên bản/đích; kiểm tra tài liệu trước khi dùng | CASE trong aggregate là cách diễn đạt dễ nhận diện, còn có các tính năng pivot |

Khi thiết kế một ứng dụng dùng **nhiều DBMS**, cách CASE trong aggregate thường là lựa chọn dễ chuyển đổi ý tưởng hơn. Nhưng sự di động hoàn toàn vẫn phụ thuộc kiểu số, boolean, COUNT, NULL, cách viết identifier và các hàm được DBMS hỗ trợ. Không nhầm “dùng CASE nên mọi câu chạy nguyên vẹn trên mọi hệ”.

### 15.1. PostgreSQL: FILTER ngắn, rõ

```sql
SELECT
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_count,
    COUNT(*) FILTER (WHERE status = 'PENDING') AS pending_count,
    SUM(amount) FILTER (WHERE status = 'PAID') AS paid_amount
FROM demo_orders;
```

Kết quả **5, 2, 410.00**.

PostgreSQL còn hỗ trợ cú pháp `CASE` thông thường:

```sql
SELECT
    COUNT(CASE WHEN status = 'PAID' THEN 1 END) AS paid_count,
    COUNT(CASE WHEN status = 'PENDING' THEN 1 END) AS pending_count,
    SUM(CASE WHEN status = 'PAID' THEN amount END) AS paid_amount
FROM demo_orders;
```

Nên chọn một quy ước phù hợp nhóm dự án. FILTER được đánh giá cao khi nhiều aggregate khác nhau chia sẻ hoặc có điều kiện riêng, trong khi CASE linh hoạt cho **biến đổi giá trị nhiều nhánh** chứ không chỉ lọc hàng.

### 15.2. SQL Server: dùng CASE

Trong T-SQL của SQL Server:

```sql
SELECT
    COUNT(*) AS all_orders,
    SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END)
        AS paid_orders,
    COUNT(CASE WHEN status = 'PENDING' THEN 1 END)
        AS pending_orders,
    SUM(CASE WHEN status = 'PAID' THEN amount END)
        AS paid_amount
FROM dbo.orders;
```

Bảng `dbo.orders` là **bảng ví dụ giả định của SQL Server**, không phải bảng tạm PostgreSQL của mục 1. Với dữ liệu tương ứng, kết quả giống các chỉ số đã tính.

SQL Server có kiểu boolean logic dạng BIT cho cột lưu trữ; không nên mặc định `SUM(status = 'PAID')` là cú pháp số học dùng được như trong một số dialect. **CASE trả 1 hoặc 0** là cách rõ ràng và dễ kiểm soát hơn.

Trong trường hợp cần nhiều cột phân loại theo trạng thái, SQL Server còn có cú pháp `PIVOT`, nhưng PIVOT không tự giải quyết **tỷ lệ, DISTINCT, dữ liệu NULL hoặc nhiều loại phép tổng hợp**. CASE vẫn là nền tảng dễ mở rộng cho nhiều KPI khác nhau.

### 15.3. MySQL: CASE hoặc IF()

MySQL hỗ trợ:

```sql
SELECT
    COUNT(*) AS all_orders,
    SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END)
        AS paid_orders,
    SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END)
        AS pending_orders,
    SUM(CASE WHEN status = 'PAID' THEN amount END)
        AS paid_amount
FROM orders;
```

Ngoài ra MySQL có hàm `IF(condition, value_if_true, value_if_false)`:

```sql
SELECT
    SUM(IF(status = 'PAID', 1, 0)) AS paid_orders,
    SUM(IF(status = 'PAID', amount, NULL)) AS paid_amount
FROM orders;
```

Với các kiểu biểu thức số hoặc boolean, MySQL đôi khi cho phép dùng `SUM(status = 'PAID')`; nhưng nếu status NULL, biểu thức so sánh cũng có thể NULL, và SUM trên toàn giá trị NULL trả NULL. Dùng **CASE ... ELSE 0** hoặc **IF(...,1,0)** khi định đếm hàng giúp thể hiện rõ cách xử lý NULL và giảm rủi ro hiểu sai ngữ nghĩa.

Hàm IF của MySQL không phải cú pháp CASE chuẩn SQL ở mọi hệ. Khi viết SQL cần chuyển hệ, CASE thường dễ đọc và ít phụ thuộc dialect hơn.

### 15.4. SQLite: FILTER có điều kiện phiên bản

SQLite 3.30.0 trở lên hỗ trợ cú pháp FILTER trên aggregate:

```sql
SELECT
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_orders,
    SUM(amount) FILTER (WHERE status = 'PAID') AS paid_amount
FROM orders;
```

Nếu ứng dụng nhúng dùng một phiên bản SQLite cũ hơn, có thể dùng CASE:

```sql
SELECT
    COUNT(CASE WHEN status = 'PAID' THEN 1 END) AS paid_orders,
    SUM(CASE WHEN status = 'PAID' THEN amount END) AS paid_amount
FROM orders;
```

Lưu ý SQLite có **hệ kiểu linh hoạt** và quy tắc chuyển đổi số/văn bản khác PostgreSQL. Để aggregate amount chính xác, phải bảo đảm dữ liệu đã có kiểu và đơn vị phù hợp; cú pháp FILTER không sửa được dữ liệu lưu sai kiểu.

### 15.5. BigQuery: COUNTIF và IF bên trong aggregate

Trong **GoogleSQL của BigQuery**, `COUNTIF` thường là cách trực tiếp để đếm điều kiện TRUE:

```sql
SELECT
    COUNT(*) AS all_orders,
    COUNTIF(status = 'PAID') AS paid_orders,
    COUNTIF(status = 'PENDING') AS pending_orders,
    SUM(IF(status = 'PAID', amount, NULL)) AS paid_amount
FROM `project.dataset.orders`;
```

``project.dataset.orders`` là tên bảng ví dụ dạng đầy đủ của BigQuery; phải thay project/dataset/table theo môi trường. `COUNTIF` chỉ đếm các hàng có điều kiện TRUE, không coi FALSE hoặc NULL/UNKNOWN là TRUE. `IF` trong GoogleSQL nhận điều kiện, giá trị khi TRUE và giá trị khi không TRUE, cho phép ta quyết định nhánh không khớp là NULL hay 0.

Đếm khách PAID duy nhất bằng mẫu:

```sql
SELECT
    COUNT(DISTINCT IF(status = 'PAID', customer_id, NULL))
        AS paid_customers
FROM `project.dataset.orders`;
```

Đừng dùng `COUNTIF(DISTINCT ...)` với kỳ vọng nó thay thế COUNT DISTINCT theo định danh khách; hai phép đếm có ý nghĩa khác nhau. Cách `COUNT(DISTINCT IF(...))` làm rõ đối tượng duy nhất.

BigQuery có các hàm tổng hợp khác và cách kiểm soát NULL riêng; khi viết truy vấn đa hệ, không suy ra BigQuery hỗ trợ nguyên văn `FILTER (WHERE ...)` chỉ vì PostgreSQL hỗ trợ.

### 15.6. Oracle: CASE là phương án nền tảng

Một ví dụ Oracle dùng:

```sql
SELECT
    SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END)
        AS paid_orders,
    SUM(CASE WHEN status = 'PAID' THEN amount END)
        AS paid_amount,
    COUNT(DISTINCT CASE
        WHEN status = 'PAID' THEN customer_id
    END) AS paid_customers
FROM orders;
```

Oracle còn có các hàm và kỹ thuật như `DECODE`, `PIVOT` trong những bài toán phù hợp, nhưng CASE thường thể hiện rõ điều kiện phức tạp và dễ chuyển ý tưởng giữa các DBMS. Khả năng dùng FILTER, tên hàm và cú pháp aggregate phải được kiểm tra theo phiên bản Oracle đang triển khai; **không thay thế tất cả CASE bằng FILTER mà chưa xác minh hỗ trợ**.

## 16. CASE phức tạp: phân loại nhiều nhánh và trọng số

`FILTER` chọn hàng cho một aggregate, còn `CASE` có thể **tạo giá trị theo nhiều quy tắc** trước khi đưa vào aggregate. Ví dụ doanh nghiệp gán trọng số:

- PAID: tính toàn bộ amount.
- PENDING: chỉ dùng 30% amount để dự báo.
- CANCELED/REFUNDED: đóng góp 0.
- status NULL: chưa xác định, không đưa vào chỉ số dự báo.

```sql
SELECT
    SUM(
        CASE
            WHEN status = 'PAID' THEN amount
            WHEN status = 'PENDING' THEN amount * 0.30
            WHEN status IN ('CANCELED', 'REFUNDED') THEN 0
            ELSE NULL
        END
    ) AS weighted_forecast
FROM demo_orders;
```

Đây chỉ là **quy tắc giả định để minh họa CASE**, không phải công thức tài chính chuẩn. Tổng phụ thuộc vào cách xử lý amount NULL và trạng thái chưa biết; nếu dữ liệu thiếu ảnh hưởng đáng kể, cần đi kèm cảnh báo chất lượng.

Có thể kết hợp CASE và FILTER:

```sql
SELECT
    SUM(
        CASE
            WHEN status = 'PAID' THEN amount
            WHEN status = 'PENDING' THEN amount * 0.30
            ELSE 0
        END
    ) FILTER (WHERE status IS NOT NULL) AS weighted_forecast
FROM demo_orders;
```

Ở đây FILTER bỏ mọi hàng status NULL, CASE quyết định trọng số cho các hàng còn lại. Việc tách điều kiện lọc và tính toán có thể giúp người đọc theo dõi quy tắc khi nhiều nguồn dữ liệu phức tạp.

### 16.1. Tránh nhầm COUNT với tổng có trọng số

```sql
COUNT(CASE WHEN status = 'PAID' THEN amount END)
```

**không** phải là tổng tiền PAID, cũng không phải số đơn PAID nếu amount có thể NULL; nó chỉ đếm số hàng PAID có amount khác NULL. Khi chỉ số được gọi là doanh thu hoặc điểm số, cần dùng SUM trên giá trị số đúng ý nghĩa.

### 16.2. Khi nào nên dùng WHERE kết hợp CASE?

Nếu báo cáo chỉ quan tâm đơn trong một khoảng ngày và nhiều chỉ số theo status:

```sql
SELECT
    COUNT(*) AS august_orders,
    SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END)
        AS august_paid_orders,
    SUM(CASE WHEN status = 'PAID' THEN amount END)
        AS august_paid_amount
FROM demo_orders
WHERE created_on >= DATE '2026-08-01'
  AND created_on <  DATE '2026-09-01';
```

WHERE loại dữ liệu ngoài tháng theo **phạm vi báo cáo chung**; CASE lọc theo **phạm vi chỉ số**. Đây là cách phối hợp hợp lý, không phải lựa chọn “WHERE hoặc CASE” một cách tuyệt đối.

## 17. Tránh đếm trùng do JOIN trước khi tổng hợp

Tổng hợp có điều kiện **không tự khắc phục vấn đề JOIN nhân bản hàng**. Giả sử một đơn có hai dòng sản phẩm; nếu JOIN `orders` với `order_items`, mỗi đơn có thể xuất hiện nhiều lần:

```text
orders:
  order 101, PAID, amount=120

order_items:
  (101, line=1)
  (101, line=2)

Sau JOIN:
  (101, PAID, 120, line=1)
  (101, PAID, 120, line=2)
```

Nếu viết `SUM(CASE WHEN status='PAID' THEN o.amount END)` trên kết quả JOIN, amount **120 có thể bị cộng hai lần**. Thay CASE bằng FILTER cũng không sửa được lỗi này:

```sql
-- Ý tưởng dễ sai khi một đơn có nhiều dòng:
SELECT
    SUM(o.amount) FILTER (WHERE o.status = 'PAID')
FROM orders AS o
JOIN order_items AS i
    ON i.order_id = o.order_id;
```

Cần xác định **đơn vị của mỗi hàng sau JOIN** trước khi chọn chỉ số:

- Nếu KPI đếm đơn, nên tính trên bảng `orders`, hoặc dùng `COUNT(DISTINCT o.order_id)` khi điều kiện và độ hạt cho phép.
- Nếu KPI cộng **tổng tiền đơn**, nên tổng hợp mỗi đơn đúng **một lần**, chẳng hạn trong một CTE riêng trước khi JOIN với những dữ liệu nhiều-nhiều.
- Nếu KPI cộng tiền của dòng hàng, dùng `line_amount` từ bảng con và kiểm soát độ hạt theo dòng, thay vì cộng lặp cột `orders.amount`.

### 17.1. Phân biệt COUNT DISTINCT với SUM DISTINCT

`COUNT(DISTINCT o.order_id)` có thể giải quyết đếm đơn duy nhất, nhưng **`SUM(DISTINCT o.amount)` không phải giải pháp chung để khử nhân bản JOIN**. Hai đơn khác nhau cùng có amount = 120 sẽ bị SUM DISTINCT chỉ cộng một lần vì nó loại **giá trị tiền trùng**, không loại **bản ghi đơn trùng**.

Muốn tính đúng doanh thu, phải giải quyết độ hạt hoặc tổng hợp theo **khóa định danh đơn**, không chỉ theo giá trị amount.

## 18. Hiệu năng và kế hoạch thực thi

Nhiều chỉ số CASE/FILTER trong cùng SELECT thường thuận tiện vì dùng chung tập dữ liệu nguồn, nhưng không có bảo đảm mọi SQL có nhiều aggregate sẽ luôn nhanh hơn mọi phương án tách truy vấn. Hiệu năng phụ thuộc:

1. Số hàng được đọc sau điều kiện WHERE.
2. Kiểu GROUP BY và số nhóm.
3. Khối lượng và độ phức tạp của các điều kiện CASE/FILTER.
4. Số lượng `DISTINCT` và số giá trị phân biệt.
5. Chỉ mục, phân vùng, thống kê và lựa chọn của bộ tối ưu.
6. JOIN có làm nhân hàng hay không.

### 18.1. FILTER trong aggregate không thay thế WHERE có thể sử dụng index

Ví dụ:

```sql
SELECT
    COUNT(*) FILTER (WHERE status = 'PAID')
FROM demo_orders;
```

Về ngữ nghĩa, aggregate vẫn được gọi trên tập hàng đầu vào của câu truy vấn và quyết định hàng nào đi vào phép đếm. DBMS có thể tối ưu, nhưng **không nên giả định** viết FILTER sẽ luôn đọc ít hàng bằng một câu:

```sql
SELECT COUNT(*)
FROM demo_orders
WHERE status = 'PAID';
```

Trong câu thứ hai, `WHERE` giới hạn trực tiếp tập hàng truy vấn, có thể tạo điều kiện cho một index trên status. Nhưng nếu báo cáo cần **cả PAID lẫn PENDING** trong cùng một hàng, tách thành hai câu COUNT có thể có chi phí và yêu cầu đồng bộ riêng. Chọn theo ý nghĩa và kế hoạch đo được.

### 18.2. Chỉ mục và phân vùng

Một chỉ mục ví dụ cho báo cáo theo thời gian và trạng thái trong PostgreSQL:

```sql
CREATE INDEX idx_demo_orders_date_status
ON demo_orders (created_on, status);
```

Index có thể có lợi cho truy vấn có điều kiện lọc theo ngày và/hoặc status, nhưng hiệu quả phụ thuộc thứ tự cột, độ chọn lọc và cách DBMS dùng index. Với bảng chỉ có 10 dòng, Seq Scan có thể rẻ hơn index scan.

PostgreSQL còn hỗ trợ **partial index**:

```sql
CREATE INDEX idx_demo_orders_paid_date
ON demo_orders (created_on)
WHERE status = 'PAID';
```

Chỉ mục này hữu ích cho một số truy vấn có WHERE đủ rõ để bộ tối ưu suy ra điều kiện `status = 'PAID'`. Không được mặc định một câu COUNT FILTER với WHERE tổng thể không có điều kiện status luôn tự dùng partial index cho riêng phần PAID. Muốn biết, hãy dùng EXPLAIN.

### 18.3. EXPLAIN và dữ liệu đại diện

```sql
EXPLAIN
SELECT
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_orders,
    SUM(amount) FILTER (WHERE status = 'PAID') AS paid_amount
FROM demo_orders;
```

Khi kiểm tra trên môi trường phù hợp:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    customer_id,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_orders
FROM demo_orders
GROUP BY customer_id;
```

`EXPLAIN` trình bày kế hoạch ước lượng; `EXPLAIN (ANALYZE, BUFFERS)` trong PostgreSQL **thực sự chạy truy vấn** và cho thời gian, số hàng, thông tin buffer. Trên dữ liệu nhỏ, đây chỉ là cách quan sát các bước Agg/GroupAggregate/HashAggregate hoặc Scan chứ chưa kết luận hiệu năng ở hệ thống thật.

### 18.4. Tham số hóa điều kiện status

Thay vì ghép một trạng thái do người dùng nhập trực tiếp vào SQL:

```sql
-- Không nên nối chuỗi không kiểm soát:
-- "... FILTER (WHERE status = '" + input + "')"
```

hãy bind tham số:

```sql
-- PostgreSQL:
PREPARE count_status(TEXT) AS
SELECT
    COUNT(*) FILTER (WHERE status = $1) AS selected_status_orders
FROM demo_orders;

EXECUTE count_status('PAID');
```

Khi ứng dụng cần chọn **các chỉ số cố định** (PAID, PENDING, CANCELED), có thể hardcode điều kiện cố định theo nghiệp vụ và bind phạm vi ngày, tenant hoặc tham số người dùng thích hợp. Nếu người dùng được chọn tập trạng thái động, danh sách tên cột/biểu thức SQL phải được kiểm soát; không đưa identifier và logic SQL từ input chưa xác thực vào chuỗi query.

## 19. Những ngộ nhận và lỗi dễ gặp

| Nhầm lẫn | Hậu quả | Cách viết/giải thích phù hợp |
| --- | --- | --- |
| `COUNT(CASE WHEN p THEN 1 ELSE 0 END)` đếm hàng thỏa p | COUNT đếm cả 0, nên đếm mọi hàng | `COUNT(CASE WHEN p THEN 1 END)` |
| `SUM(CASE WHEN p THEN 1 END)` luôn trả 0 khi không khớp | Không có giá trị khác NULL -> SUM trả NULL | `COUNT(CASE WHEN p THEN 1 END)` hoặc COALESCE đúng nghiệp vụ |
| `SUM(CASE WHEN p THEN 1 ELSE 0 END)` luôn trả 0 cả tập rỗng | SUM trên 0 hàng trả NULL | COUNT hoặc COALESCE có chủ đích |
| `COUNT(CASE WHEN p THEN amount END)` đếm mọi hàng p | amount NULL sẽ bị bỏ | Dùng THEN 1 để đếm hàng |
| `SUM(... ELSE 0 END)` luôn an toàn cho báo cáo tiền | Có thể che tình trạng số tiền chưa biết | Kiểm tra missing amount và tách quy ước hiển thị |
| `AVG(CASE WHEN p THEN amount ELSE 0 END)` là trung bình nhóm p | Hàng không khớp đóng góp số 0 vào mẫu số | Bỏ ELSE để chúng thành NULL |
| FILTER loại NULL của đối số aggregate một cách đặc biệt | FILTER chỉ lọc hàng, hàm vẫn có quy tắc NULL riêng | Phân biệt COUNT(*) với COUNT(amount) |
| FILTER có trên mọi DBMS | Nhiều dialect không hỗ trợ cú pháp này | CASE hoặc hàm bản địa phù hợp |
| Đếm status IS NULL sau LEFT JOIN bằng `COUNT(*) FILTER` | Đếm cả hàng bù của khách chưa có đơn | Dùng `COUNT(o.order_id)` hoặc điều kiện có id thật |
| Đặt status PAID trong WHERE khi vẫn muốn mọi khách | Có thể làm khách chưa có PAID biến mất | Đặt điều kiện trong aggregate/ON theo yêu cầu |
| COALESCE paid_amount NULL thành 0 nghĩa là mọi tiền đã biết | Không phân biệt nhóm rỗng và tiền chưa biết | Thêm chỉ số chất lượng và quy ước báo cáo |
| `SUM(DISTINCT amount)` chữa lỗi JOIN nhân bản đơn | Hai đơn có amount bằng nhau có thể bị cộng thiếu | Tổng hợp theo khóa đơn đúng độ hạt |
| COUNT order_id và COUNT DISTINCT customer_id là cùng KPI | Một khách có nhiều đơn | Đặt tên chỉ số theo đối tượng cần đếm |
| FILTER mặc nhiên nhanh hơn CASE | DBMS có thể tối ưu khác nhau | Đọc kế hoạch và đo thực tế |
| `100 * paid / total` luôn là phần trăm chính xác | Có thể chia nguyên hoặc chia cho 0 | Dùng kiểu số phù hợp và NULLIF(total,0) |

## 20. Bài tập thực hành

Các bài dùng hai bảng tạm `demo_customers` và `demo_orders` ở mục 1. Hãy **dự đoán kết quả trước khi chạy** để phân biệt ý nghĩa của CASE/FILTER, COUNT/SUM và NULL.

### Bài 1 — Đếm theo ba trạng thái

Viết một câu SQL trả `all_orders`, `paid_orders`, `pending_orders`, `canceled_orders`. Hãy viết:

1. Một phiên bản **chỉ dùng CASE** trong COUNT hoặc SUM.
2. Một phiên bản PostgreSQL **dùng FILTER**.

Kết quả mong đợi với dữ liệu mẫu: **10, 5, 2, 1**.

### Bài 2 — COUNT và ELSE 0

Giải thích khác biệt giữa:

```sql
COUNT(CASE WHEN status = 'PAID' THEN 1 END)
```

và:

```sql
COUNT(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END)
```

Vì sao biểu thức thứ hai bằng 10 thay vì 5? Nếu thay COUNT bằng SUM, kết quả và trường hợp tập rỗng khác nhau thế nào?

### Bài 3 — Doanh thu biết được và dữ liệu thiếu

Viết một câu tổng hợp trả bốn thông tin: số đơn PAID, số đơn PAID có amount khác NULL, số đơn PAID bị thiếu amount, và tổng amount PAID đã biết. Thử cả CASE và FILTER. Với dữ liệu mẫu, các giá trị lần lượt là **5, 4, 1, 410.00**.

### Bài 4 — Trung bình và hai mẫu số

Tính `AVG(amount)` có điều kiện status PAID. Giải thích tại sao kết quả là **102.50**, không phải **82.00**. Nếu sản phẩm muốn giả định amount NULL bằng 0, cần thể hiện phép biến đổi nào, và làm cách nào ghi rõ giả định cho người đọc báo cáo?

### Bài 5 — Giữ khách không có đơn

Hãy dùng `LEFT JOIN` để liệt kê cả năm khách, trả:

- `customer_name`
- `total_orders`
- `paid_orders`
- `pending_orders`
- `paid_amount`

Khách Em phải có số đơn bằng 0, không phải 1. Vì sao `COUNT(*)` sau LEFT JOIN dễ bị sai? Nếu muốn phát hiện các đơn status NULL, vì sao `COUNT(*) FILTER (WHERE o.status IS NULL)` cũng có thể sai cho Em?

### Bài 6 — Khách thanh toán duy nhất

Viết:

```sql
COUNT(DISTINCT customer_id)
    FILTER (WHERE status = 'PAID')
```

bằng cú pháp CASE trong COUNT DISTINCT. Giải thích vì sao số khách PAID là **4**, dù tổng số đơn PAID là **5**. Nếu An có thêm ba đơn PAID, hai chỉ số thay đổi thế nào?

### Bài 7 — Tỷ lệ theo khách

Tính phần trăm đơn PAID trên mọi đơn của từng khách bằng LEFT JOIN. Khi một khách không có đơn, tỷ lệ phải là `NULL` hay `0` theo yêu cầu của bạn? Viết biểu thức có `NULLIF` để tránh phép chia cho 0 và giải thích việc đặt giá trị hiển thị không làm biến đổi nghĩa toán học.

### Bài 8 — Viết theo hai phương ngữ

Viết truy vấn tính `paid_orders`, `pending_orders`, `paid_amount` cho:

1. PostgreSQL với `FILTER`.
2. SQL Server hoặc MySQL với `CASE`.

Chú ý tên bảng, kiểu dữ liệu và cú pháp giả định của từng DBMS. Không dùng `FILTER` như thể SQL Server hỗ trợ cú pháp PostgreSQL.

### Bài 9 — BigQuery COUNTIF

Viết lại:

```sql
COUNT(*) FILTER (WHERE status = 'PAID')
```

bằng `COUNTIF` của BigQuery. Để tính số khách PAID duy nhất, dùng `COUNT(DISTINCT IF(...))`. Vì sao không thể thay “số đơn” bằng “số khách” chỉ bằng cách giữ COUNTIF mà không đổi đối tượng đếm?

### Bài 10 — JOIN nhân bản hàng

Một đơn có hai dòng chi tiết, mỗi dòng JOIN được với cùng một bản ghi orders có amount = 120. Nếu tổng hợp bằng `SUM(o.amount) FILTER (WHERE status='PAID')` sau JOIN, chuyện gì xảy ra? Vì sao `SUM(DISTINCT o.amount)` không giải quyết được mọi trường hợp? Đề xuất cách tổng hợp theo order_id hoặc loại bỏ JOIN không cần thiết.

### Bài 11 — Chọn đúng vị trí WHERE/HAVING/FILTER

Cần báo cáo **trong tháng 8/2026**, mỗi khách có bao nhiêu đơn, có bao nhiêu đơn PAID và chỉ giữ khách có ít nhất **hai** đơn PAID. Điều kiện thời gian đặt ở đâu? Điều kiện PAID trong COUNT đặt ở đâu? Điều kiện “tối thiểu hai đơn PAID” đặt ở WHERE hay HAVING?

Gợi ý: `WHERE` lọc thời gian, `FILTER` hoặc `CASE` tính chỉ số, `HAVING` giới hạn nhóm đã tổng hợp.

### Bài 12 — Tự đặt bài toán chất lượng dữ liệu

Trong báo cáo thật, nếu có 10 đơn PAID nhưng 3 đơn chưa biết amount, tổng `SUM(amount)` phải được đặt tên thế nào để không khiến người dùng tưởng đó là doanh thu hoàn chỉnh? Viết thêm `paid_orders_missing_amount`, đồng thời đề xuất quy tắc hiển thị khi chỉ số thiếu dữ liệu và quy trình xử lý bản ghi thiếu.

## 21. Tóm tắt: điều kiện thuộc về từng chỉ số

```text
Các hàng từ FROM/JOIN
        |
        v
WHERE chung: chọn phạm vi báo cáo (ngày, tenant, quyền...)
        |
        v
GROUP BY: mỗi khách / vùng / tháng / toàn bảng
        |
        +------------------------------+
        |                              |
        v                              v
COUNT(*)                         Aggregate có điều kiện
Tổng hàng trong nhóm             CASE hoặc FILTER
                                       |
                           +-----------+-----------+
                           |           |           |
                           v           v           v
                        PAID count  PENDING count  PAID amount
                           |           |           |
                           +-----------+-----------+
                                       |
                                       v
                         HAVING / ORDER BY / kết quả
```

**`CASE` trong hàm tổng hợp** là kỹ thuật linh hoạt và phổ biến giữa các phương ngữ SQL. **`FILTER (WHERE ...)`** làm điều kiện của từng aggregate ngắn gọn, rõ ràng ở PostgreSQL, SQLite và những hệ hỗ trợ. `COUNT(*) FILTER (...)` và `COUNT(CASE WHEN ... THEN 1 END)` đều đếm số hàng khớp, trong khi `COUNT(CASE WHEN ... THEN amount END)` đòi amount khác NULL; `SUM` có thể trả NULL khi không có giá trị để cộng. Đây là những khác biệt có ý nghĩa thực tế.

Nguyên tắc khi viết báo cáo: **xác định độ hạt của một hàng, phạm vi dữ liệu chung, điều kiện riêng của từng KPI, cách xử lý NULL và mẫu số thống kê, rồi chọn cú pháp phù hợp với DBMS**. Một câu SQL có nhiều chỉ số chỉ đáng tin khi mỗi con số đo đúng điều người dùng cần biết, kể cả nhóm không có dữ liệu và dữ liệu chưa được xác định.
