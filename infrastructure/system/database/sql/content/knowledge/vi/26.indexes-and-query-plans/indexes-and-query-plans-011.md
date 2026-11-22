# Đối chiếu tính tương đương của kết quả trước khi tối ưu

Khi một truy vấn SQL chạy chậm, chúng ta thường nghĩ đến **tạo chỉ mục**, **đổi thứ tự JOIN**, **đẩy điều kiện xuống sớm**, **đưa subquery thành JOIN**, **thay phép tổng hợp**, hoặc **chuyển DISTINCT thành GROUP BY**. Những cách này có thể làm execution plan nhẹ hơn, nhưng có một điều kiện quan trọng phải được giữ trước tiên: **truy vấn mới phải trả đúng kết quả mà nghiệp vụ cần**.

Ví dụ, hai truy vấn có thể chạy rất nhanh và có cùng số lượng hàng, nhưng một truy vấn tính trùng đơn hàng vì JOIN với nhiều dòng chi tiết, còn truy vấn kia bỏ mất khách hàng chưa có đơn. Một chỉ mục mới có thể làm thứ tự các hàng thay đổi; nếu ứng dụng vốn dùng `LIMIT 10` mà không có `ORDER BY` đủ xác định, trang đầu có thể chứa những hàng khác dù dữ liệu không thay đổi. Một rewrite `NOT IN` thành `NOT EXISTS` có thể đổi kết quả nếu subquery chứa `NULL`.

Vì vậy, quy tắc tối ưu SQL có thể viết gọn:

> **Chứng minh hoặc kiểm chứng tính tương đương của kết quả trước, đo hiệu năng sau.** Một execution plan nhanh hơn không có giá trị nếu nó trả sai hàng, thiếu hàng, nhân bản hàng, sai giá trị, hoặc thay đổi thứ tự/phạm vi mà API đã cam kết.

Bài học thuộc **Database SQL → Chỉ mục và kế hoạch**. Nội dung sử dụng PostgreSQL làm hệ thực hành, xây dựng bộ dữ liệu tự chứa, đối chiếu hai truy vấn bằng `EXCEPT ALL` theo **đa tập (bag/multiset)**, phân tích những phép biến đổi không luôn tương đương, xác định hợp đồng kết quả, rồi mới đến `EXPLAIN (ANALYZE, BUFFERS)`, kế hoạch thử nghiệm và lưu ý theo hệ quản trị.

## 1. Trước khi tối ưu: “cùng kết quả” nghĩa là gì?

Hai SQL có thể được coi là tương đương trong một ngữ cảnh khi, trên **cùng trạng thái dữ liệu phù hợp và cùng các giả thiết được khai báo**, chúng trả kết quả thỏa **cùng hợp đồng quan sát được**.

Hợp đồng ấy không chỉ gồm các con số ở cuối câu `SELECT`. Tùy nghiệp vụ, nó còn bao gồm:

| Khía cạnh | Cần đối chiếu | Ví dụ |
| --- | --- | --- |
| **Số hàng** | Có thiếu hoặc nhân hàng không? | Danh sách 100 đơn trở thành 110 đơn sau JOIN |
| **Tập hàng và số lần xuất hiện** | Mỗi hàng có multiplicity giống nhau? | Hai đơn cùng `amount=100` không được gộp thành một |
| **Giá trị từng cột** | Có sai tính toán hoặc điều kiện? | `SUM` khác do NULL hay fanout |
| **NULL** | NULL có giữ nguyên ngữ nghĩa? | `COUNT(*)` khác `COUNT(amount)` |
| **Kiểu dữ liệu** | Đầu ra có còn là integer/decimal/text/date? | Chia nguyên làm mất phần thập phân |
| **Thứ tự** | Có `ORDER BY` và tie-breaker? | `LIMIT 10` chọn sai 10 hàng |
| **Phân trang** | Cùng tập hàng mỗi trang, cùng cursor? | Offset thay đổi khi có ghi đồng thời |
| **Mức chi tiết (grain)** | Một hàng đại diện cho đối tượng nào? | Một hàng/đơn hay một hàng/chi tiết đơn |
| **Phạm vi lọc** | Tenant, soft delete, thời gian, status | Quên lọc khách active |
| **Trạng thái snapshot** | Hai phiên đọc cùng dữ liệu hay không? | A đọc trước COMMIT, B đọc sau COMMIT |
| **Lỗi và tác dụng khác** | Có bỏ lỗi hoặc đổi side effect không? | `SELECT` chứa hàm volatile |

### 1.1. Ba mức so sánh cần phân biệt

1. **Tương đương tập hợp (set):** bỏ qua số lần xuất hiện trùng. Có ích nếu kết quả thật sự là tập các khóa duy nhất.
2. **Tương đương đa tập (bag/multiset):** mỗi hàng phải xuất hiện đúng số lần như nhau. Đây là mô hình thường gặp của `SELECT` trong SQL khi không dùng `DISTINCT`.
3. **Tương đương chuỗi hàng có thứ tự:** ngoài cùng bag còn phải giữ thứ tự theo yêu cầu `ORDER BY`, bao gồm cách xử lý những hàng có khóa sắp xếp bằng nhau.

Hai truy vấn trả **cùng tập DISTINCT** chưa chắc tương đương như một danh sách SQL thông thường. Ngược lại, hai truy vấn có cùng bag nhưng **khác thứ tự** có thể vẫn tương đương với báo cáo không đòi thứ tự, nhưng **không tương đương** với một API sử dụng trang/cursor theo thứ tự.

### 1.2. Tương đương với bộ dữ liệu thử chưa phải định lý phổ quát

Một test trên 100 hàng có thể không chứa `NULL`, dữ liệu trùng, khách không có đơn hoặc ngày ở ranh giới. Hai truy vấn cùng kết quả trên test đó **không chứng minh** chúng sẽ luôn tương đương với mọi dữ liệu hợp lệ.

Nên kết hợp:

- **Lập luận ngữ nghĩa:** quy tắc SQL nào bảo đảm phép biến đổi đúng?
- **Giả thiết schema:** khóa duy nhất, NOT NULL, FK, CHECK, mối quan hệ một-nhiều.
- **Bộ dữ liệu phản ví dụ:** cố ý chứa NULL, duplicate, LEFT JOIN không khớp và giá trị ở biên.
- **So sánh kết quả thật:** hai hướng chênh lệch trên cùng snapshot.
- **Kiểm thử hồi quy:** chạy lại khi schema, phiên bản, cấu hình hoặc dữ liệu thay đổi.

## 2. Hệ dữ liệu PostgreSQL tự chứa để thực hành

Chạy một lần trong một phiên PostgreSQL. Dùng bảng tạm để bài học không cần dữ liệu bên ngoài.

```sql
CREATE TEMP TABLE demo_eq_customers (
    customer_id INTEGER PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    full_name TEXT NOT NULL,
    region TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TEMP TABLE demo_eq_orders (
    order_id INTEGER PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    customer_id INTEGER NOT NULL REFERENCES demo_eq_customers(customer_id),
    status TEXT NOT NULL CHECK (status IN ('PAID', 'PENDING', 'CANCELED')),
    amount NUMERIC(12, 2),
    created_at TIMESTAMPTZ NOT NULL,
    deleted_at TIMESTAMPTZ
);

CREATE TEMP TABLE demo_eq_items (
    order_id INTEGER NOT NULL REFERENCES demo_eq_orders(order_id),
    line_no INTEGER NOT NULL,
    sku TEXT NOT NULL,
    line_amount NUMERIC(12, 2) NOT NULL,
    PRIMARY KEY (order_id, line_no)
);

INSERT INTO demo_eq_customers
    (customer_id, tenant_id, full_name, region, is_active)
VALUES
    (1, 10, 'An',   'Bắc', TRUE),
    (2, 10, 'Bình', 'Nam', TRUE),
    (3, 10, 'Chi',  'Bắc', TRUE),
    (4, 10, 'Dũng', NULL,  TRUE),
    (5, 10, 'Em',   'Nam', FALSE),
    (6, 10, 'Hoa',  'Nam', TRUE),
    (7, 10, 'Lan',  'Nam', TRUE);

INSERT INTO demo_eq_orders
    (order_id, tenant_id, customer_id, status, amount, created_at, deleted_at)
VALUES
    (101,10,1,'PAID',    100.00,'2026-10-01 08:00:00+07',NULL),
    (102,10,1,'PAID',    100.00,'2026-10-01 08:00:00+07',NULL),
    (103,10,1,'PENDING',  50.00,'2026-10-02 09:00:00+07',NULL),
    (104,10,2,'PAID',      NULL,'2026-10-02 09:00:00+07',NULL),
    (105,10,3,'PAID',    200.00,'2026-10-03 10:00:00+07',NULL),
    (106,10,3,'CANCELED',  0.00,'2026-10-04 10:00:00+07',NULL),
    (107,10,4,'PAID',     60.00,'2026-10-04 11:00:00+07',NULL),
    (108,10,5,'PAID',     80.00,'2026-10-05 09:00:00+07',NULL),
    (109,10,6,'PAID',    100.00,'2026-10-05 09:00:00+07',NULL),
    (110,10,6,'PAID',    100.00,'2026-10-06 09:00:00+07',
        '2026-10-07 10:00:00+07');

INSERT INTO demo_eq_items
    (order_id, line_no, sku, line_amount)
VALUES
    (101,1,'PEN', 60.00),
    (101,2,'PAD', 40.00),
    (102,1,'BOX',100.00),
    (105,1,'BAG',120.00),
    (105,2,'TAG', 80.00),
    (107,1,'PEN', 60.00),
    (109,1,'BOX',100.00);
```

Trong bộ mẫu:

- Có **7 khách**, trong đó khách 5 không active; khách 7 active **không có đơn**.
- Có **10 đơn**, bao gồm đơn PENDING, CANCELED, đơn PAID của khách không active và đơn đã soft delete.
- Đơn 104 đã PAID nhưng `amount IS NULL`.
- Đơn 101 và 102 cùng có số tiền 100; đơn 109 cũng có số tiền 100: **hai/nhiều hàng khác nhau có thể cùng giá trị**.
- Đơn 101 và 105 có **hai dòng chi tiết**; JOIN trực tiếp sẽ nhân hàng đơn.
- Đơn 101 và 102 có **cùng created_at**, thích hợp thử chuyện `ORDER BY` có tie.

### 2.1. Một định nghĩa nghiệp vụ dùng xuyên suốt

Ví dụ, yêu cầu:

> “Lấy đơn PAID **chưa bị xóa mềm** của khách **active** trong tenant 10.”

Truy vấn tham chiếu:

```sql
SELECT
    o.order_id,
    c.customer_id,
    c.full_name,
    o.amount,
    o.created_at
FROM demo_eq_orders AS o
JOIN demo_eq_customers AS c
  ON c.customer_id = o.customer_id
 AND c.tenant_id = o.tenant_id
WHERE o.tenant_id = 10
  AND c.is_active = TRUE
  AND o.deleted_at IS NULL
  AND o.status = 'PAID';
```

Trong bộ mẫu, đó là các đơn **101, 102, 104, 105, 107, 109**: **6 hàng**. Trong sáu đơn này có **một amount NULL**, và tổng các amount có giá trị bằng **560.00** (100 + 100 + 200 + 60 + 100).

Mốc tham chiếu ở trên dành cho mục tiêu **đơn còn hiệu lực của khách active**. Nếu một báo cáo tài chính phải tính cả đơn lịch sử của khách archived, điều kiện `c.is_active` có thể không thuộc hợp đồng báo cáo ấy. Không dùng một công thức chung cho mọi nghiệp vụ.

### 2.2. Tại sao cần bộ dữ liệu có “góc cạnh”?

Một bộ chỉ gồm các khách đều active, mỗi khách một đơn, amount không NULL và thời gian khác nhau sẽ không phát hiện được nhiều lỗi rewrite. Chúng ta cố ý giữ:

| Góc cạnh | Hàng mẫu | Lỗi có thể phơi bày |
| --- | --- | --- |
| Không có bản ghi con | Khách 7 | LEFT JOIN bị biến thành INNER JOIN |
| Khách không active | Khách 5, đơn 108 | Quên lọc trạng thái cha |
| Đơn đã xóa mềm | Đơn 110 | Quên lọc trạng thái con |
| Amount NULL | Đơn 104 | COUNT/AVG/COALESCE thay đổi |
| Amount trùng | Đơn 101, 102, 109 | DISTINCT/UNION đánh mất multiplicity |
| Nhiều dòng chi tiết | Đơn 101, 105 | JOIN fanout, SUM bị nhân |
| Timestamp bằng nhau | Đơn 101, 102 | LIMIT/pagination thiếu tie-breaker |
| Region NULL | Khách 4 | So sánh nhóm và bộ lọc NULL |

## 3. SQL mặc định có ngữ nghĩa đa tập (bag)

Một phép `SELECT` thông thường trả các hàng, **không tự loại bỏ những hàng trùng hoàn toàn**.

```sql
SELECT amount
FROM demo_eq_orders
WHERE order_id IN (101, 102);
```

Kết quả là **hai hàng**:

```text
amount
------
100.00
100.00
```

Thêm `DISTINCT`:

```sql
SELECT DISTINCT amount
FROM demo_eq_orders
WHERE order_id IN (101, 102);
```

chỉ còn **một hàng 100.00**. Nếu đầu ra yêu cầu “mỗi đơn hàng là một hàng” thì hai truy vấn **không tương đương**, dù tập giá trị amount khác nhau không xuất hiện.

### 3.1. UNION và UNION ALL

```sql
SELECT amount FROM demo_eq_orders WHERE order_id = 101
UNION
SELECT amount FROM demo_eq_orders WHERE order_id = 102;
```

`UNION` loại trùng, cho một hàng 100.00.

```sql
SELECT amount FROM demo_eq_orders WHERE order_id = 101
UNION ALL
SELECT amount FROM demo_eq_orders WHERE order_id = 102;
```

`UNION ALL` giữ hai hàng 100.00. Một rewrite từ `UNION ALL` sang `UNION` có thể làm kế hoạch khác đi **và đổi dữ liệu**.

### 3.2. Vì sao so sánh set có thể bỏ sót lỗi?

Đặt:

```sql
WITH a AS (
    SELECT amount
    FROM demo_eq_orders
    WHERE order_id IN (101, 102)
),
b AS (
    SELECT amount
    FROM demo_eq_orders
    WHERE order_id = 101
)
SELECT * FROM a
EXCEPT
SELECT * FROM b;
```

Kết quả **rỗng**, vì `EXCEPT` ở đây làm việc theo ngữ nghĩa set và chỉ biết hai bên có giá trị 100.00. Nhưng A có hai hàng còn B chỉ một.

**Không kết luận hai truy vấn tương đương chỉ vì `A EXCEPT B` rỗng**; ngay cả kiểm tra cả hai chiều bằng `EXCEPT` (không ALL) cũng không phát hiện multiplicity.

## 4. EXCEPT ALL: đối chiếu đa tập theo hai chiều

PostgreSQL hỗ trợ `EXCEPT ALL`: trừ **số lần xuất hiện** của mỗi hàng.

```sql
WITH a AS (
    SELECT amount
    FROM demo_eq_orders
    WHERE order_id IN (101, 102)
),
b AS (
    SELECT amount
    FROM demo_eq_orders
    WHERE order_id = 101
)
SELECT * FROM a
EXCEPT ALL
SELECT * FROM b;
```

Truy vấn này trả **một hàng 100.00**, vì A có 2 bản còn B có 1. Ngược lại:

```sql
WITH a AS (
    SELECT amount
    FROM demo_eq_orders
    WHERE order_id IN (101, 102)
),
b AS (
    SELECT amount
    FROM demo_eq_orders
    WHERE order_id = 101
)
SELECT * FROM b
EXCEPT ALL
SELECT * FROM a;
```

trả **0 hàng**.

### 4.1. Mẫu kiểm tra hai chiều

Thay hai CTE bằng truy vấn cần đối chiếu và giữ **cùng cấu trúc cột**:

```sql
WITH
old_result AS (
    -- Truy vấn gốc: thứ tự và kiểu cột được giữ cố định.
    SELECT order_id, customer_id, amount
    FROM demo_eq_orders
    WHERE status = 'PAID'
      AND deleted_at IS NULL
),
new_result AS (
    -- Ví dụ rewrite tương đương để minh họa cú pháp.
    SELECT o.order_id, o.customer_id, o.amount
    FROM demo_eq_orders AS o
    WHERE o.deleted_at IS NULL
      AND o.status IN ('PAID')
),
old_minus_new AS (
    SELECT * FROM old_result
    EXCEPT ALL
    SELECT * FROM new_result
),
new_minus_old AS (
    SELECT * FROM new_result
    EXCEPT ALL
    SELECT * FROM old_result
)
SELECT 'OLD_ONLY' AS side, d.*
FROM old_minus_new AS d
UNION ALL
SELECT 'NEW_ONLY' AS side, d.*
FROM new_minus_old AS d;
```

Kỳ vọng **0 hàng** với mẫu rewrite trên. Khi so sánh thực tế:

- **OLD_ONLY**: hàng có mặt ở truy vấn cũ nhiều hơn truy vấn mới.
- **NEW_ONLY**: hàng có mặt ở truy vấn mới nhiều hơn truy vấn cũ.
- Nếu cả hai rỗng, các hàng và multiplicity tương đương theo quy tắc so sánh của PostgreSQL **trên snapshot hiện tại**.

Không dùng `SELECT *` tùy tiện trong hai truy vấn gốc nếu schema có nguy cơ đổi; ở template này `SELECT *` chỉ được dùng **sau khi hai CTE đã khai báo cùng thứ tự cột**.

### 4.2. Vì sao phải kiểm cả hai chiều?

Nếu chỉ `A EXCEPT ALL B` rỗng, vẫn có thể B chứa **thêm** hàng. Ví dụ A trả 10 đơn, B trả 11 đơn thì A trừ B có thể rỗng còn B trừ A có thêm một hàng. Kiểm hai chiều bảo đảm phát hiện cả mất lẫn thừa, khi hai kết quả thật sự được so sánh theo cùng cấu trúc.

### 4.3. Không so sánh hai lần chạy không cùng snapshot

Nếu dữ liệu thay đổi giữa lúc lấy kết quả A và B, khác biệt có thể do **giao dịch khác COMMIT**, không phải do rewrite. Cách viết cả A và B trong **một statement PostgreSQL** thường giúp hai phần đọc cùng snapshot của statement khi dùng isolation phù hợp.

Khi đối chiếu ở nhiều statement, có thể dùng transaction `REPEATABLE READ READ ONLY` để giữ snapshot thống nhất theo quy tắc PostgreSQL. Lưu ý rằng những hàm volatile hoặc truy vấn có side effect đặc biệt không nhất thiết trở thành tương đương chỉ vì snapshot giống nhau.

## 5. Đếm số lần xuất hiện bằng GROUP BY: phương án không phụ thuộc EXCEPT ALL

Một số hệ quản trị không hỗ trợ `EXCEPT ALL`. Ta có thể **gắn nhãn nguồn, UNION ALL, nhóm theo toàn bộ cột kết quả rồi so sánh số lần xuất hiện**.

```sql
WITH a AS (
    SELECT amount
    FROM demo_eq_orders
    WHERE order_id IN (101, 102)
),
b AS (
    SELECT amount
    FROM demo_eq_orders
    WHERE order_id = 101
),
tagged AS (
    SELECT amount, 'A' AS side FROM a
    UNION ALL
    SELECT amount, 'B' AS side FROM b
),
counts AS (
    SELECT
        amount,
        SUM(CASE WHEN side = 'A' THEN 1 ELSE 0 END) AS count_a,
        SUM(CASE WHEN side = 'B' THEN 1 ELSE 0 END) AS count_b
    FROM tagged
    GROUP BY amount
)
SELECT amount, count_a, count_b
FROM counts
WHERE count_a <> count_b;
```

Kết quả chỉ ra `amount=100.00` xuất hiện **2 lần ở A, 1 lần ở B**.

### 5.1. Ưu điểm của mẫu nhóm số lần xuất hiện

- Phát hiện được hàng thiếu, hàng thừa **và số lần xuất hiện khác nhau**.
- Với `GROUP BY`, các giá trị NULL thường được gom trong cùng một nhóm theo quy tắc SQL; không cần dùng `a.col = b.col` để ghép NULL.
- Có thể hiển thị số đếm của hai bên để chẩn đoán.
- Có thể mở rộng đến nhiều cột kết quả bằng cách đưa **toàn bộ cột** vào phần `SELECT` và `GROUP BY`.

### 5.2. Các giới hạn

- Phải giữ **đúng cột, đúng thứ tự, kiểu dữ liệu và ý nghĩa** ở hai nhánh.
- Những kiểu dữ liệu không nhóm/so sánh được theo DBMS có thể cần cơ chế xử lý riêng.
- Tập kết quả rất lớn có thể khiến phép đối chiếu tốn bộ nhớ/CPU; nên chạy trên bản sao/khung dữ liệu kiểm thử theo chính sách.
- So sánh giá trị database không tự xác nhận metadata/client serialization giống nhau, ví dụ `NUMERIC` và `FLOAT` có thể hiển thị giống ở vài dòng nhưng có sai khác về độ chính xác.

Không thay việc kiểm giá trị bằng **hash** một cách thiếu thận trọng: hash có xác suất va chạm, còn cách chuẩn hóa chuỗi/NULL/type có thể làm mất phân biệt giá trị. Hash hữu ích để chia vùng nghi ngờ, nhưng khi cần bằng chứng chính xác, phải so sánh dữ liệu gốc hoặc có cơ chế collision handling.

## 6. Ba tầng kiểm tra: schema, aggregate, từng hàng

Một pipeline tối ưu hóa nên có nhiều tầng đối chiếu:

### Tầng 1 — Cấu trúc đầu ra

- Số cột, tên cột, thứ tự cột.
- Kiểu dữ liệu và độ chính xác/scale.
- Khả năng NULL của giá trị; format timestamp/timezone.
- Định nghĩa từng cột, ví dụ `revenue_net` khác `revenue_gross`.

Nếu một truy vấn đổi `amount NUMERIC(12,2)` thành `DOUBLE PRECISION`, phép so sánh vài số có thể bằng nhau nhưng API dùng decimal chính xác đã thay đổi hợp đồng. Cần kiểm schema/metadata bên cạnh dữ liệu.

### Tầng 2 — Kiểm aggregate

Ví dụ:

```sql
SELECT
    COUNT(*) AS rows,
    COUNT(DISTINCT order_id) AS distinct_orders,
    COUNT(amount) AS rows_with_known_amount,
    COALESCE(SUM(amount), 0) AS total_amount
FROM demo_eq_orders
WHERE status = 'PAID'
  AND deleted_at IS NULL;
```

Aggregate có thể bắt được fanout hoặc NULL, nhưng hai tập khác nhau có thể vẫn có cùng COUNT/SUM. Do đó **COUNT/SUM bằng nhau chỉ là dấu hiệu, không phải bằng chứng cuối**.

### Tầng 3 — So sánh đa tập hai chiều

Dùng `EXCEPT ALL` hoặc grouping multiplicity như hai mục trên. Nếu có khóa nghiệp vụ duy nhất, thêm phép `FULL OUTER JOIN` theo khóa để chỉ ra **hàng nào đổi giá trị**; nhưng vẫn phải phát hiện key trùng nếu nguồn không bảo đảm unique.

### 6.1. Ví dụ so sánh theo khóa

Giả sử hai truy vấn đều trả mỗi `order_id` **đúng một hàng**, có thể ghép:

```sql
WITH old_result AS (
    SELECT order_id, amount
    FROM demo_eq_orders
    WHERE status = 'PAID'
),
new_result AS (
    SELECT order_id, amount
    FROM demo_eq_orders
    WHERE status IN ('PAID')
)
SELECT
    o.order_id AS old_id,
    n.order_id AS new_id,
    o.amount AS old_amount,
    n.amount AS new_amount
FROM old_result AS o
FULL OUTER JOIN new_result AS n USING (order_id)
WHERE o.order_id IS NULL
   OR n.order_id IS NULL
   OR o.amount IS DISTINCT FROM n.amount;
```

PostgreSQL có `IS DISTINCT FROM`, phép so sánh **NULL-safe**: NULL so với NULL được coi là không khác; NULL so với một số là khác. Nếu thay bằng `o.amount <> n.amount`, một phía NULL khiến điều kiện thành UNKNOWN, có thể **bỏ sót thay đổi**.

**Điều kiện tiên quyết:** `order_id` duy nhất trong **cả hai kết quả**. Nếu một truy vấn JOIN nhân order_id, phép FULL JOIN theo key có thể nhân tiếp hàng và làm đối chiếu khó hiểu. Hãy kiểm uniqueness đầu ra trước.

## 7. NULL và logic ba giá trị: nơi rewrite thường sai

Trong SQL, điều kiện có thể là **TRUE, FALSE hoặc UNKNOWN**. Khi một toán hạng NULL tham gia `=`, `<>`, `<`, `>` trong ngữ cảnh thông thường, kết quả thường là UNKNOWN; `WHERE` chỉ giữ các hàng có điều kiện TRUE.

### 7.1. `= NULL` không tương đương `IS NULL`

Sai:

```sql
SELECT order_id
FROM demo_eq_orders
WHERE amount = NULL;
```

Đúng để tìm hàng thiếu amount:

```sql
SELECT order_id
FROM demo_eq_orders
WHERE amount IS NULL;
-- Đơn 104.
```

### 7.2. `<> 0` không tương đương “kể cả NULL”

```sql
SELECT order_id
FROM demo_eq_orders
WHERE amount <> 0;
```

Hàng amount NULL bị loại vì điều kiện UNKNOWN. Trong PostgreSQL:

```sql
SELECT order_id
FROM demo_eq_orders
WHERE amount IS DISTINCT FROM 0;
```

thì amount NULL **được giữ** (NULL được coi khác 0). Đây là hai hợp đồng khác nhau.

### 7.3. `NOT IN` và `NOT EXISTS` không luôn tương đương

Ví dụ:

```sql
SELECT 2 AS value
WHERE 2 NOT IN (1, NULL);
-- Không trả hàng trong PostgreSQL.
```

Vì danh sách có NULL, biểu thức `2 NOT IN (1, NULL)` là UNKNOWN, không phải TRUE. Nếu thay bằng:

```sql
SELECT 2 AS value
WHERE NOT EXISTS (
    SELECT 1
    FROM (VALUES (1), (NULL)) AS t(x)
    WHERE t.x = 2
);
-- Trả giá trị 2.
```

thì `NOT EXISTS` xét có hàng nào **thỏa `t.x = 2`** hay không. NULL không thỏa, nên kết quả khác.

Để rewrite `NOT IN` sang `NOT EXISTS` một cách đúng đắn, cần chứng minh ràng buộc `NOT NULL` và ngữ nghĩa NULL ở **cả bên trái và subquery** theo yêu cầu, hoặc viết điều kiện xử lý NULL tường minh.

### 7.4. `COALESCE` có thể thay nghĩa

```sql
WHERE amount > 0
```

không tự tương đương:

```sql
WHERE COALESCE(amount, 0) >= 0
```

Câu đầu loại 0 và NULL; câu sau giữ cả 0 và NULL. Dù kết quả có thể gần giống trong dữ liệu không có NULL, chúng không bảo toàn logic.

## 8. COUNT, SUM, AVG: NULL tạo những khác biệt kín đáo

Trong tập đơn PAID chưa deleted của khách active ở tenant 10, có **6 đơn** nhưng một amount NULL.

```sql
SELECT
    COUNT(*) AS paid_orders,
    COUNT(o.amount) AS paid_orders_with_amount,
    SUM(o.amount) AS paid_amount,
    AVG(o.amount) AS avg_known_amount
FROM demo_eq_orders AS o
JOIN demo_eq_customers AS c
  ON c.customer_id = o.customer_id
 AND c.tenant_id = o.tenant_id
WHERE o.tenant_id = 10
  AND o.status = 'PAID'
  AND o.deleted_at IS NULL
  AND c.is_active = TRUE;
```

Kết quả:

| Chỉ số | Giá trị |
| --- | ---: |
| `COUNT(*)` | 6 |
| `COUNT(o.amount)` | 5 |
| `SUM(o.amount)` | 560.00 |
| `AVG(o.amount)` | 112.00 |

`AVG(amount)` bỏ qua NULL ở tử số **và mẫu số**, nên ở ví dụ là 560/5 = 112, không phải 560/6.

### 8.1. Tối ưu nhầm sang `AVG(COALESCE(amount,0))`

```sql
AVG(COALESCE(o.amount, 0))
```

coi amount NULL như 0, nên kết quả trở thành 560/6 ≈ 93.33. Hai công thức **không tương đương** trừ khi đã có giả thiết amount không NULL hoặc nghiệp vụ định nghĩa NULL là 0.

### 8.2. SUM trên tập không có hàng

`SUM(amount)` trả NULL nếu không có giá trị không NULL để tổng hợp; `COUNT(*)` trả 0 khi không có hàng. Vì vậy:

```sql
SUM(amount)
```

và:

```sql
COALESCE(SUM(amount), 0)
```

không có cùng giá trị trên nhóm rỗng/toàn NULL. Dùng cách nào tùy hợp đồng “không có dữ liệu” có được coi là 0 không.

### 8.3. COUNT(*) sau LEFT JOIN

Một khách không có đơn vẫn có thể tạo **một hàng NULL-extended** sau LEFT JOIN. `COUNT(*)` sẽ bằng 1, còn `COUNT(o.order_id)` bằng 0. Rewrite hai biểu thức vì muốn “truy vấn đơn giản hơn” có thể làm báo cáo sai.

## 9. INNER JOIN và LEFT JOIN không thay thế tùy tiện

Giả sử muốn liệt kê **mọi khách active**, kèm số đơn PAID còn hiệu lực của họ. Khách 7 chưa có đơn vẫn phải xuất hiện.

Truy vấn đúng:

```sql
SELECT
    c.customer_id,
    c.full_name,
    COUNT(o.order_id) AS paid_order_count
FROM demo_eq_customers AS c
LEFT JOIN demo_eq_orders AS o
  ON o.customer_id = c.customer_id
 AND o.tenant_id = c.tenant_id
 AND o.status = 'PAID'
 AND o.deleted_at IS NULL
WHERE c.tenant_id = 10
  AND c.is_active = TRUE
GROUP BY c.customer_id, c.full_name
ORDER BY c.customer_id;
```

Khách 7 xuất hiện với `paid_order_count = 0`; các khách khác có số đơn tương ứng.

### 9.1. Đẩy điều kiện từ ON xuống WHERE có thể đổi kết quả

Phiên bản dễ sai:

```sql
SELECT
    c.customer_id,
    c.full_name,
    COUNT(o.order_id) AS paid_order_count
FROM demo_eq_customers AS c
LEFT JOIN demo_eq_orders AS o
  ON o.customer_id = c.customer_id
 AND o.tenant_id = c.tenant_id
WHERE c.tenant_id = 10
  AND c.is_active = TRUE
  AND o.status = 'PAID'
  AND o.deleted_at IS NULL
GROUP BY c.customer_id, c.full_name;
```

Ở khách không có đơn, `o.status` là NULL, điều kiện `o.status='PAID'` là UNKNOWN nên WHERE loại hàng ấy. Truy vấn mới không còn giữ toàn bộ khách active.

Với khách chỉ có đơn PENDING, LEFT JOIN tạo hàng khớp nhưng WHERE loại vì status khác PAID; cũng không tạo lại hàng bù.

### 9.2. Một ngoại lệ phải hiểu, không chỉ học mẹo

Trong **INNER JOIN**, chuyển một điều kiện chỉ tham chiếu bảng phải từ ON sang WHERE thường giữ cùng kết quả theo ngữ nghĩa logic quan hệ nếu không có yếu tố đặc biệt. Nhưng với **OUTER JOIN**, ON quyết định **hàng khớp**, còn WHERE lọc **kết quả sau khi tạo hàng NULL-extended**.

Chính vì vậy, optimizer có thể pushdown hoặc đổi join loại trong những trường hợp **được chứng minh an toàn**, nhưng người viết SQL không được giả định mọi rewrite ấy đều tương đương.

## 10. JOIN fanout: dữ liệu đúng nhưng số tiền bị nhân

Bảng chi tiết `demo_eq_items` có:

```text
Order 101 -> 2 dòng chi tiết
Order 102 -> 1 dòng
Order 105 -> 2 dòng
```

Một truy vấn tưởng hợp lý:

```sql
SELECT SUM(o.amount) AS paid_amount
FROM demo_eq_orders AS o
JOIN demo_eq_customers AS c
  ON c.customer_id = o.customer_id
 AND c.tenant_id = o.tenant_id
JOIN demo_eq_items AS i
  ON i.order_id = o.order_id
WHERE o.tenant_id = 10
  AND o.status = 'PAID'
  AND o.deleted_at IS NULL
  AND c.is_active = TRUE;
```

Truy vấn trên **không tương đương** với SUM từ bảng đơn:

- Mỗi dòng chi tiết làm bản sao của amount ở hàng đơn.
- Đơn 101 có amount 100 nhưng hai chi tiết, nên 100 bị cộng **hai lần**.
- Đơn 105 có amount 200 và hai chi tiết, nên 200 bị cộng **hai lần**.
- Đơn không có chi tiết không xuất hiện trong INNER JOIN.

Nếu muốn SUM amount cấp **đơn hàng**, không JOIN trực tiếp sang cấp **dòng chi tiết** rồi SUM giá đơn.

### 10.1. Sửa bằng cách giữ đúng grain

Nếu chỉ muốn **đơn có ít nhất một chi tiết**, dùng EXISTS:

```sql
SELECT SUM(o.amount) AS paid_amount
FROM demo_eq_orders AS o
JOIN demo_eq_customers AS c
  ON c.customer_id = o.customer_id
 AND c.tenant_id = o.tenant_id
WHERE o.tenant_id = 10
  AND o.status = 'PAID'
  AND o.deleted_at IS NULL
  AND c.is_active = TRUE
  AND EXISTS (
      SELECT 1
      FROM demo_eq_items AS i
      WHERE i.order_id = o.order_id
  );
```

EXISTS không nhân bản đơn khi có nhiều dòng chi tiết. Nhưng truy vấn này **chỉ chọn đơn có chi tiết**, không phải mọi đơn PAID. Nó chỉ tương đương với câu gốc nếu **mục tiêu nghiệp vụ** có đúng điều kiện ấy.

Nếu chỉ cần tổng giá đơn PAID, cách đơn giản hơn là **không JOIN items**.

### 10.2. Vì sao `SUM(DISTINCT o.amount)` không phải cách chữa tổng quát?

Trong mẫu có nhiều đơn hợp lệ cùng `amount=100`. `SUM(DISTINCT o.amount)` coi các giá trị 100 chỉ một lần, dù đó là **nhiều đơn thật**. Muốn khử fanout phải giữ khóa **order_id**, không khử các giá trị tiền trùng nhau.

Giải pháp thường là:

- Dùng EXISTS cho điều kiện “có dòng chi tiết”.
- Tổng hợp items về **một hàng/đơn** trước khi JOIN.
- Lấy danh sách order_id duy nhất theo quy tắc trước khi tính SUM cấp đơn.
- Bảo vệ cardinality bằng UNIQUE/FK và đối chiếu count distinct order_id.

## 11. DISTINCT, GROUP BY và window function

Các kỹ thuật sau có thể đều trả “một hàng/khách” trên một bộ dữ liệu nhỏ, nhưng **không luôn chọn cùng giá trị**:

```sql
SELECT DISTINCT customer_id
FROM demo_eq_orders;
```

trả các ID khách duy nhất, không chọn một đơn cụ thể.

```sql
SELECT customer_id, MAX(created_at) AS latest_order_time
FROM demo_eq_orders
GROUP BY customer_id;
```

trả thời điểm mới nhất mỗi khách, nhưng không tự cho biết order_id ứng với thời điểm đó khi có tie.

```sql
SELECT customer_id, order_id, created_at
FROM (
    SELECT
        customer_id,
        order_id,
        created_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY created_at DESC, order_id DESC
        ) AS rn
    FROM demo_eq_orders
) AS ranked
WHERE rn = 1;
```

trả một **đơn xác định mỗi khách** theo thứ tự thời gian rồi order_id. Đó là một hợp đồng khác với `MAX(created_at)` riêng lẻ.

### 11.1. ROW_NUMBER, RANK và DENSE_RANK

Nếu hai đơn có cùng created_at:

- `ROW_NUMBER()` luôn gán số 1, 2... nhưng **không có tie-breaker thì hàng nào nhận số 1 có thể không ổn định**.
- `RANK()` cho các hàng đồng hạng cùng rank và có khoảng trống về rank tiếp theo.
- `DENSE_RANK()` cho các hàng đồng hạng cùng rank và không để khoảng trống.

Đổi `ROW_NUMBER() = 1` sang `RANK() = 1` có thể trả **nhiều hàng mỗi khách** khi tie.

### 11.2. PostgreSQL DISTINCT ON

```sql
SELECT DISTINCT ON (customer_id)
    customer_id, order_id, created_at
FROM demo_eq_orders
ORDER BY customer_id, created_at DESC, order_id DESC;
```

Đây là cú pháp PostgreSQL chọn **một hàng đầu tiên mỗi nhóm** dựa trên ORDER BY. Có thể tương đương với `ROW_NUMBER() ... WHERE rn=1` khi partition và tiêu chí thứ tự khớp, có tie-breaker đủ xác định và cột cùng ngữ nghĩa.

Không mang `DISTINCT ON` sang SQL Server/MySQL như SQL chuẩn; tính tương đương phải chứng minh theo dialect.

## 12. ORDER BY: execution plan không cam kết thứ tự mặc định

Một truy vấn:

```sql
SELECT order_id, amount
FROM demo_eq_orders
WHERE status = 'PAID';
```

**không có thứ tự được SQL cam kết**. Trước khi tạo index, PostgreSQL có thể quét bảng theo một cách; sau khi tạo index, nó có thể chọn đường đi khác và trả các hàng theo thứ tự khác.

Hai kết quả cùng bag nhưng thứ tự khác nhau **không nhất thiết là lỗi optimizer**. Lỗi thường là ứng dụng đã dựa vào thứ tự không được khai báo.

### 12.1. `ORDER BY` chỉ trên cột không duy nhất

```sql
SELECT order_id, created_at
FROM demo_eq_orders
ORDER BY created_at DESC
LIMIT 3;
```

Nếu nhiều hàng có cùng created_at nằm ở biên LIMIT, SQL không có tie-breaker để xác định hàng nào trong nhóm bằng nhau được chọn trước. Tối ưu hóa có thể thay đổi kết quả trang dù mọi giá trị đều hợp lệ theo ORDER BY ấy.

Thêm khóa duy nhất:

```sql
SELECT order_id, created_at
FROM demo_eq_orders
ORDER BY created_at DESC, order_id DESC
LIMIT 3;
```

Khi `order_id` duy nhất, thứ tự đầy đủ ổn định đối với **một snapshot cố định**. Nhưng nếu có INSERT/DELETE đồng thời giữa các lần tải trang, offset pagination vẫn có thể bị trượt.

### 12.2. LIMIT/OFFSET phải gắn với cùng hợp đồng

```sql
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 20
```

không tương đương với:

```sql
ORDER BY order_id DESC
LIMIT 20 OFFSET 20
```

dù hai biểu thức đều có index hỗ trợ. Thay thứ tự để nhanh hơn là **thay kết quả nghiệp vụ**.

### 12.3. Keyset pagination

Một kỹ thuật cho truy vấn theo thời gian:

```sql
SELECT order_id, created_at
FROM demo_eq_orders
WHERE (created_at, order_id)
    < (TIMESTAMPTZ '2026-10-05 09:00:00+07', 109)
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Mẫu PostgreSQL này dùng tuple comparison cho cursor với hai cột NOT NULL. Nó có thể nhanh và ổn định hơn OFFSET trong nhiều tình huống, nhưng **không tương đương ở mọi khía cạnh** với việc chọn trang thứ N bằng OFFSET khi dữ liệu thay đổi. Cần định nghĩa pagination/cursor contract và chốt cách xử lý hàng mới, xóa, cập nhật khóa sort.

## 13. Predicate pushdown: phải xét outer join và NULL

**Predicate pushdown** là ý tưởng đưa điều kiện lọc gần nguồn dữ liệu để giảm lượng hàng phải xử lý. Optimizer tự làm được nhiều trường hợp, nhưng không phải mọi vị trí điều kiện đều tương đương.

### 13.1. Điều kiện trên bảng bên trong INNER JOIN

```sql
SELECT o.order_id, c.full_name
FROM demo_eq_orders AS o
JOIN demo_eq_customers AS c
  ON o.customer_id = c.customer_id
WHERE c.is_active = TRUE;
```

Trong INNER JOIN thông thường, đưa `c.is_active = TRUE` vào ON:

```sql
JOIN demo_eq_customers AS c
  ON o.customer_id = c.customer_id
 AND c.is_active = TRUE
```

giữ tập hàng theo ngữ nghĩa, với những giả thiết thông thường. Nhưng không vì thế suy rộng sang LEFT JOIN.

### 13.2. LEFT JOIN cần giữ hàng không khớp

Nếu muốn **mọi khách active kể cả không có đơn PAID**, điều kiện PAID của order phải nằm trong ON, như mục 9. Đẩy xuống WHERE có thể loại khách không có đơn.

### 13.3. Điều kiện có thể thay đổi số hàng trước GROUP BY

Nếu điều kiện `status='PAID'` được áp dụng **trước GROUP BY** thì số hàng tham gia aggregation thay đổi. Nếu đổi thành HAVING trên kết quả group mà không bảo toàn biểu thức, semantics có thể khác.

Ví dụ:

```sql
SELECT customer_id, COUNT(*) AS paid_count
FROM demo_eq_orders
WHERE status = 'PAID'
GROUP BY customer_id;
```

khác với:

```sql
SELECT customer_id, COUNT(*) AS all_count
FROM demo_eq_orders
GROUP BY customer_id
HAVING COUNT(*) > 0;
```

Câu sau đếm **tất cả status**, chỉ loại nhóm rỗng vốn không xuất hiện trong GROUP BY nguồn. Không được xem HAVING là vị trí thay thế cho WHERE bất kỳ.

## 14. WHERE, HAVING và FILTER trong aggregate

Giả sử cần mỗi khách một hàng với số đơn PAID và tổng amount, đồng thời muốn khách không có đơn vẫn hiện.

PostgreSQL:

```sql
SELECT
    c.customer_id,
    COUNT(o.order_id) FILTER (
        WHERE o.status = 'PAID'
          AND o.deleted_at IS NULL
    ) AS paid_count,
    COALESCE(
        SUM(o.amount) FILTER (
            WHERE o.status = 'PAID'
              AND o.deleted_at IS NULL
        ),
        0
    ) AS paid_amount
FROM demo_eq_customers AS c
LEFT JOIN demo_eq_orders AS o
  ON o.customer_id = c.customer_id
 AND o.tenant_id = c.tenant_id
WHERE c.tenant_id = 10
  AND c.is_active = TRUE
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

So sánh với mẫu dùng CASE:

```sql
COUNT(CASE
    WHEN o.status = 'PAID' AND o.deleted_at IS NULL
    THEN o.order_id
END)
```

và:

```sql
SUM(CASE
    WHEN o.status = 'PAID' AND o.deleted_at IS NULL
    THEN o.amount
END)
```

Trong nhiều trường hợp chúng có semantics giống FILTER, **nhưng cần kiểm tra riêng NULL và giá trị ELSE**.

### 14.1. `SUM(CASE ... ELSE 0 END)` khác khi nhóm không có hàng phù hợp

```sql
SUM(CASE WHEN predicate THEN amount ELSE 0 END)
```

thường trả 0 khi nhóm tồn tại nhưng không có hàng thỏa predicate, trong khi:

```sql
SUM(amount) FILTER (WHERE predicate)
```

có thể trả NULL. Nếu mục tiêu là 0, dùng `COALESCE` bên ngoài sau khi định nghĩa semantics phù hợp. Đừng đổi chỉ để planner trông đẹp mà không kiểm đầu ra cho nhóm rỗng.

### 14.2. Đếm có điều kiện

```sql
COUNT(*) FILTER (WHERE status = 'PAID')
```

đếm các hàng PAID, còn:

```sql
COUNT(amount) FILTER (WHERE status = 'PAID')
```

chỉ đếm hàng PAID có amount **không NULL**. Hai truy vấn khác nhau với đơn 104.

## 15. Điều kiện ngày/giờ: ranh giới và múi giờ

Một rewrite thường thấy:

```sql
WHERE created_at::DATE = DATE '2026-10-01'
```

sang:

```sql
WHERE created_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND created_at <  TIMESTAMPTZ '2026-10-02 00:00:00+07'
```

Hai cách **chỉ tương đương** nếu cách `created_at::DATE` diễn giải timezone của session khớp với vùng giờ +07 được dùng để dựng khoảng. Trong PostgreSQL, chuyển TIMESTAMPTZ sang DATE phụ thuộc timezone của session. Nếu session dùng UTC, những mốc gần nửa đêm có thể bị gán sang ngày khác.

### 15.1. Nên dùng khoảng nửa mở khi truy vấn theo ngày

Với hợp đồng một ngày của timezone đã định:

```sql
created_at >= :start_instant
AND created_at < :next_day_start_instant
```

định nghĩa khoảng **[bắt đầu, đầu ngày sau)**. Cách này có thể thân thiện với index trên timestamp hơn một biểu thức cast trên cột, nhưng trước khi tối ưu, cần bảo đảm mốc đầu/cuối **đúng múi giờ và DST** của nghiệp vụ.

### 15.2. BETWEEN có biên bao gồm

```sql
created_at BETWEEN :start AND :end
```

bao gồm **cả hai đầu**. Nếu `end` là 00:00 ngày hôm sau, BETWEEN có thể tính cả event đúng 00:00 ngày kế tiếp. Không đổi `< :end` thành `<= :end` mà không xét biên.

### 15.3. Date, timestamp và clock functions

Các hàm thời gian như `CURRENT_TIMESTAMP`, `clock_timestamp()`, `NOW()` có tính chất đánh giá khác nhau theo DBMS/transaction. Một rewrite gọi hàm nhiều lần hoặc di chuyển giữa các tầng query có thể ảnh hưởng kết quả nếu hàm phụ thuộc thời điểm chạy.

Khi đo tương đương, hãy **cố định mốc :as_of** từ application hoặc CTE thích hợp nếu mục tiêu là cùng một thời điểm nghiệp vụ, thay vì để mỗi truy vấn quyết định “bây giờ” độc lập.

## 16. Kiểu dữ liệu: ép kiểu có thể thay đổi số

Ví dụ chia nguyên:

```sql
SELECT 1 / 2 AS integer_division;
```

Trong PostgreSQL, với literal integer theo kiểu suy luận tương ứng, phép chia nguyên cho kết quả **0**. Nếu ép sang numeric:

```sql
SELECT 1::NUMERIC / 2 AS decimal_division;
```

cho kết quả **0.5**. Một rewrite bỏ `::NUMERIC` để “bớt cast” có thể làm sai tỷ lệ.

### 16.1. Decimal khác floating point

`NUMERIC/DECIMAL` biểu diễn số thập phân theo độ chính xác phù hợp, còn `REAL/DOUBLE PRECISION` có đặc tính floating point nhị phân. Khi tính tiền, `SUM` hoặc `AVG` trên kiểu khác có thể cho kết quả khác do làm tròn/độ chính xác.

Một refactor:

```sql
SUM(amount::DOUBLE PRECISION)
```

không được mặc định tương đương tuyệt đối với:

```sql
SUM(amount)
```

nếu hợp đồng đầu ra đòi kết quả decimal chính xác.

### 16.2. Tràn số và kiểu trả về

Kiểu kết quả của `COUNT`, `SUM`, phép nhân, `CASE` và `UNION` phụ thuộc DBMS và kiểu input. Một rewrite có thể tạo integer overflow hoặc giảm precision dù giá trị trên bộ mẫu nhỏ giống nhau.

Kiểm tra **schema output** và các ranh giới lớn, không chỉ test vài số nhỏ.

## 17. Collation và chuỗi: không phải mọi so sánh tên đều giống nhau

Hai DB có collation khác nhau có thể so sánh chữ hoa/thường, dấu tiếng Việt và Unicode theo các quy tắc khác nhau. Ví dụ điều kiện:

```sql
WHERE lower(email) = lower(:email)
```

không luôn tương đương với:

```sql
WHERE email = :email
```

trừ khi collation/constraint và quy tắc chuẩn hóa bảo đảm điều đó.

### 17.1. DISTINCT và GROUP BY phụ thuộc ngữ nghĩa equality

Nếu hai chuỗi được collation coi là bằng nhau, `DISTINCT`, `GROUP BY` và thứ tự có thể chịu ảnh hưởng. Tối ưu sang một index với collation hoặc biểu thức khác phải giữ hợp đồng so sánh nghiệp vụ.

### 17.2. Unicode normalization

Hai chuỗi nhìn giống nhau có thể được mã hóa bằng Unicode composed và decomposed sequences. Tùy DBMS/collation, chúng có thể được xem là bằng hoặc khác. Không tự giả định `LOWER` giải quyết toàn bộ normalization.

### 17.3. NULL và chuỗi rỗng

Trong Oracle, chuỗi rỗng có ngữ nghĩa NULL trong nhiều ngữ cảnh; PostgreSQL/MySQL/SQL Server thường phân biệt NULL với chuỗi rỗng. Do đó một phép rewrite về chuỗi cần kiểm chứng **trên chính dialect**.

## 18. Các phép biến đổi logic cần điều kiện phụ

Tối ưu SQL không chỉ là đổi từ khóa; nhiều phép biến đổi chỉ đúng nếu có **ràng buộc dữ liệu**.

### 18.1. Bỏ JOIN vì “không dùng cột của bảng phụ”

Giả sử:

```sql
SELECT o.order_id
FROM demo_eq_orders AS o
JOIN demo_eq_customers AS c
  ON c.customer_id = o.customer_id;
```

Bỏ JOIN và chỉ lấy `o.order_id` có thể tương đương **nếu** mọi order đều có đúng một customer hợp lệ và JOIN không có bộ lọc khác. Trong schema mẫu có FK customer và customer_id NOT NULL, customer_id là PK, nên giả thiết đó có cơ sở.

Nhưng nếu bảng customer là một-dòng-nhiều phiên bản, hoặc JOIN đang lọc `c.is_active`, bỏ JOIN sẽ thay kết quả.

### 18.2. INNER JOIN với bảng lookup có thể nhân hàng

Nếu cột JOIN của bảng phụ không UNIQUE, một order có thể khớp nhiều hàng lookup. Bỏ JOIN hoặc đổi thành EXISTS làm giảm số hàng. Muốn phép biến đổi đúng, cần biết **multiplicity** của quan hệ.

### 18.3. OR thành UNION ALL

```sql
WHERE status = 'PAID' OR amount >= 100
```

không mặc nhiên tương đương với:

```sql
SELECT ... WHERE status = 'PAID'
UNION ALL
SELECT ... WHERE amount >= 100
```

vì một đơn vừa PAID vừa amount >= 100 xuất hiện **hai lần** trong UNION ALL. Nếu dùng UNION để loại trùng, có thể lại làm mất các hàng nghiệp vụ khác nhau trùng tất cả cột projection. Phải chia nhánh **không giao nhau** hoặc so sánh theo khóa và số lần xuất hiện.

### 18.4. LEFT JOIN thành INNER JOIN

Chỉ tương đương nếu có cơ sở chứng minh **mọi hàng bên trái đều có hàng khớp** theo toàn bộ điều kiện ON và hợp đồng không cần giữ hàng không khớp. FK có thể bảo đảm tồn tại hàng tham chiếu, nhưng thêm điều kiện status/active hoặc thời gian lên bảng phải có thể làm hàng khớp biến mất.

### 18.5. Điều kiện từ HAVING xuống WHERE

Một điều kiện lọc trực tiếp giá trị **khóa GROUP BY** có thể đẩy xuống WHERE trong một số trường hợp. Nhưng điều kiện dùng aggregate như `HAVING COUNT(*) >= 2` không thể thay tùy tiện bằng WHERE trên từng hàng. Phải xét liệu phép biến đổi làm thay đổi **tập hàng đầu vào của aggregate** không.

## 19. Các hàm không xác định và dữ liệu biến động

Một số truy vấn dùng:

- `random()`
- `clock_timestamp()`
- UUID generator
- hàm người dùng có side effect
- đọc trạng thái bên ngoài hoặc phụ thuộc session
- các biểu thức không xác định/không ổn định khi đổi thứ tự tính toán

Ví dụ:

```sql
SELECT random() AS sample_value;
```

Hai lần chạy gần nhau bình thường trả hai số khác nhau, không thể dùng equality đơn giản để nói một rewrite sai. Nhiều DBMS còn có các loại **volatility/determinism** để planner quyết định an toàn của biến đổi.

### 19.1. Cố định tham số biến động khi có thể

Nếu nghiệp vụ cần một mốc thời gian `as_of`, hãy truyền tham số cố định. Nếu cần lấy mẫu ngẫu nhiên, phải so sánh **phân phối và hợp đồng lấy mẫu**, không đòi từng hàng giống nhau khi thuật toán chủ ý random.

### 19.2. LIMIT và hàm volatile

Đổi vị trí `LIMIT` so với hàm xử lý đắt tiền có thể làm khác số lần hàm được gọi, kết quả hoặc side effect nếu hàm volatile. Không cho phép một tối ưu “đẩy LIMIT vào sớm” chỉ dựa vào việc planner nhanh hơn mà không xét ngữ nghĩa.

### 19.3. SELECT không phải luôn hoàn toàn vô hại

Một `SELECT` có thể gọi hàm tạo side effect do người dùng định nghĩa, lock hàng bằng `FOR UPDATE` hoặc sử dụng sequence. Khi chạy `EXPLAIN ANALYZE` hoặc chạy cả truy vấn cũ và mới để so sánh, **cẩn trọng với việc câu SQL thực sự được thực thi**.

## 20. Snapshot nhất quán khi so sánh

Nếu chạy:

```text
T0: Query A -> 1000 hàng
T1: transaction khác INSERT/COMMIT 5 hàng
T2: Query B -> 1005 hàng
```

thì không thể kết luận B sai vì 5 hàng thừa.

### 20.1. Một statement so sánh hai CTE

Trong PostgreSQL READ COMMITTED, mỗi statement `SELECT` thông thường có snapshot nhất quán cho việc đọc, nên mẫu `WITH old_result, new_result` trong **cùng statement** hữu ích. Tuy nhiên, nếu CTE gọi hàm volatile hay có tác dụng phụ, cần phân tích riêng.

### 20.2. Một transaction READ ONLY REPEATABLE READ

Khi phải thu kết quả bằng nhiều statement:

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

-- Chạy truy vấn cũ, ghi nhận kết quả.
-- Chạy truy vấn mới, ghi nhận kết quả.
-- So sánh trong cùng snapshot theo quy tắc PostgreSQL.

COMMIT;
```

Những câu lệnh cần chạy trong cùng **connection/transaction**. Nếu hai query dùng hai connection, mở BEGIN trên A không làm B tự dùng snapshot của A.

### 20.3. Đừng giữ snapshot rất lâu trong production

Trong PostgreSQL, các transaction kéo dài có thể giữ các phiên bản MVCC cũ, ảnh hưởng VACUUM và hiệu năng. Nếu so sánh hai query mất hàng giờ, cân nhắc bản sao dữ liệu, môi trường staging hoặc snapshot/quy trình kiểm thử thích hợp thay vì giữ transaction mở trên DB đang phục vụ người dùng.

### 20.4. Phân biệt khác dữ liệu với khác plan

Execution plan có thể thay đổi theo thống kê, index, tham số, bộ nhớ, cardinality ước tính và version DBMS. Nếu query trả kết quả khác vì dữ liệu đang bị INSERT/DELETE, đó là **thay đổi input**, không phải tự thân lỗi plan.

## 21. “Index giúp nhanh” phải đứng sau correctness gate

Chỉ mục thường thay đổi **cách tìm hàng**, không chủ ý thay đổi tập hàng được trả bởi một `SELECT` thuần deterministic. Nhưng index có thể làm:

- Planner chuyển từ sequential scan sang index scan.
- Thứ tự trả hàng **không có ORDER BY** thay đổi.
- Kế hoạch JOIN khác, làm lộ lỗi application vốn dựa vào thứ tự ngẫu nhiên.
- Một biến thể rewrite mới dùng index nhưng vô tình bỏ điều kiện hoặc thay JOIN.

### 21.1. Tạo index ví dụ

Trong PostgreSQL lab:

```sql
CREATE INDEX idx_demo_eq_paid_active
ON demo_eq_orders (tenant_id, customer_id, created_at DESC)
WHERE status = 'PAID'
  AND deleted_at IS NULL;
```

Index này chỉ chứa order có `status='PAID'` và `deleted_at IS NULL`. Nó **không thay** điều kiện `c.is_active` của bảng customer và không tự chọn đúng metric doanh thu. Index tối ưu đường truy cập; **định nghĩa truy vấn vẫn quyết định kết quả**.

### 21.2. Chỉ mục biểu thức cũng cần bảo toàn nghĩa

Nếu truy vấn lọc `lower(email)` và tạo index trên biểu thức đó, có thể nhanh hơn cho điều kiện tương ứng. Nhưng đổi điều kiện thành so sánh raw email để tận dụng index khác có thể đổi semantics case-sensitive/collation.

### 21.3. Index partial/filtered

PostgreSQL hỗ trợ partial index với `WHERE predicate`. SQL Server có filtered index. MySQL không có cùng cú pháp partial index thông dụng và có phương án expression/generated columns trong một số trường hợp. Khi di chuyển dialect, phải giữ **ý nghĩa predicate** và kiểm tính tương đương của query, không sao chép cú pháp máy móc.

## 22. EXPLAIN sau khi hai kết quả đã tương đương

Trên PostgreSQL:

```sql
EXPLAIN
SELECT order_id, customer_id, amount
FROM demo_eq_orders
WHERE tenant_id = 10
  AND status = 'PAID'
  AND deleted_at IS NULL;
```

`EXPLAIN` không có `ANALYZE` hiển thị kế hoạch **dự kiến**. Nó cho biết các node như Seq Scan, Index Scan, Bitmap Heap Scan, Hash Join, Nested Loop, Sort, Aggregate và ước tính cost/rows.

Khi muốn đo thực thi trên môi trường phù hợp:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, customer_id, amount
FROM demo_eq_orders
WHERE tenant_id = 10
  AND status = 'PAID'
  AND deleted_at IS NULL;
```

Kết quả có thể cho:

- **Actual time** theo các node.
- **Actual rows / loops**.
- **Buffers** đọc/ghi theo cơ chế engine.
- **Planning Time** và **Execution Time**.
- Khoảng cách giữa **estimated rows** và **actual rows**.

### 22.1. Không nhầm plan nhanh với query đúng

Nếu một rewrite bỏ `c.is_active`, nó có thể đọc ít bảng hơn và chạy nhanh hơn, nhưng kết quả chứa cả đơn của khách archived. Dù EXPLAIN cho kết quả đẹp, rewrite **không hợp lệ** nếu hợp đồng yêu cầu khách active.

### 22.2. EXPLAIN ANALYZE thực sự chạy statement

Với `SELECT` thuần, điều này thường phù hợp trong môi trường test. Với `UPDATE`, `DELETE`, `INSERT`, `EXPLAIN ANALYZE` sẽ **thực thi DML**; cần transaction và `ROLLBACK` khi dùng trên dữ liệu thử, đồng thời xét side effect ngoài transaction.

Không chạy mù `EXPLAIN ANALYZE DELETE...` trên production rồi cho rằng nó chỉ giải thích kế hoạch.

### 22.3. Dữ liệu lab nhỏ không đánh giá được index thật

Với 10 order, PostgreSQL có thể chọn Seq Scan vì rẻ hơn index scan; điều đó không chứng minh index vô dụng trên 100 triệu order. Tối ưu cần dữ liệu và thống kê đại diện, đồng thời đo nhiều lần để giảm ảnh hưởng của cache và nhiễu môi trường.

## 23. Quy trình tối ưu có cổng kiểm tra tính đúng

Một quy trình có thể chia thành sáu giai đoạn.

### Giai đoạn 1 — Xác định yêu cầu

Ghi rõ:

```text
Input:
  tenant_id = ...
  date range = [start, end)
  status và điều kiện active = ...

Output:
  Mỗi hàng là một order? customer? hay order-item?
  Cột, kiểu, NULL semantics
  Có yêu cầu ORDER BY/pagination?
  Count/Sum/AVG có bao gồm record soft deleted?
  As-of snapshot hay dữ liệu mới nhất?
```

Nếu không biết một hàng đại diện cho gì, không thể biết đổi JOIN làm tăng số hàng là đúng hay sai.

### Giai đoạn 2 — Giữ truy vấn gốc làm tham chiếu

Lưu bản query ban đầu, tham số, phiên bản schema, session settings và điều kiện dữ liệu. Không vừa sửa query gốc, vừa sửa dữ liệu test, vừa đổi cấu hình, khiến không còn mốc so sánh.

### Giai đoạn 3 — Thiết kế bộ kiểm tra

Bộ dữ liệu cần có:

- Giá trị NULL ở từng cột quan trọng.
- Duplicate business values và có/không có khóa duy nhất.
- Hàng không có bản ghi JOIN khớp.
- Một-nhiều ở bảng con gây fanout.
- Soft-deleted/inactive/tenant khác.
- Ngày/giờ ở sát biên, timezone/DST nếu liên quan.
- Các nhóm rỗng, amount 0/âm, số rất lớn.
- Tie ở cột ORDER BY và trang LIMIT/OFFSET.

### Giai đoạn 4 — So sánh tập kết quả

- Kiểm tra output schema.
- Kiểm COUNT, COUNT DISTINCT và tổng hợp đối chứng.
- Dùng `EXCEPT ALL` hai chiều hoặc multiplicity grouping.
- Với result có thứ tự, kiểm `ORDER BY` và tie-breaker.
- Dùng cùng snapshot/isolation khi cần.
- Bổ sung test trên dữ liệu đại diện mà được phép sử dụng.

### Giai đoạn 5 — Chỉ khi đúng mới đo plan

- `EXPLAIN`, sau đó `EXPLAIN (ANALYZE, BUFFERS)` ở môi trường phù hợp.
- Đo execution time, actual rows/loops, buffers, sort/spill và resource usage.
- Kiểm sự thay đổi plan theo tham số, cardinality và thống kê.
- Đo end-to-end latency nếu ứng dụng truyền nhiều hàng qua mạng.

### Giai đoạn 6 — Triển khai có giám sát và rollback

- Triển khai sau test hồi quy/đối chiếu.
- Theo dõi số hàng/giá trị ở sản phẩm thực khi được phép, không log PII.
- Theo dõi latency, timeout, CPU/I/O, errors và plan regressions.
- Có đường quay lại query gốc hoặc feature flag nếu kết quả/KPI bất thường.

Không chọn rewrite chỉ vì một lần `EXPLAIN ANALYZE` báo nhanh hơn trong điều kiện không đại diện.

## 24. Quy tắc chứng minh thay đổi JOIN bằng khóa và ràng buộc

Trước khi đổi một JOIN, hãy kiểm:

1. Bảng bên phải có **UNIQUE/PRIMARY KEY** trên đúng cột JOIN không?
2. Bảng bên trái có FK và cột FK **NOT NULL** không?
3. Có điều kiện bổ sung `active`, `deleted_at`, thời gian hiệu lực hoặc tenant làm hàng không khớp?
4. Có thể có **nhiều hàng hợp lệ** ở bảng right không (history/SCD Type 2)?
5. JOIN là INNER hay LEFT/RIGHT/FULL?
6. Có GROUP BY, DISTINCT, LIMIT hoặc window phụ thuộc multiplicity không?

### 24.1. Ví dụ một-nhiều

`demo_eq_orders.order_id` là PRIMARY KEY, nhưng `demo_eq_items.order_id` không UNIQUE vì mỗi đơn có nhiều item. Một INNER JOIN từ order sang item có thể làm một order thành nhiều hàng. Nếu SELECT chỉ có `o.order_id`, kết quả vẫn **có duplicate order_id**.

### 24.2. FK không đồng nghĩa INNER JOIN với mọi điều kiện

FK chỉ bảo đảm tham chiếu tồn tại vật lý theo constraint tương ứng. Nếu thêm:

```sql
AND c.is_active = TRUE
```

thì order của khách inactive có thể không khớp nữa, dù FK hợp lệ. Bỏ JOIN customer khi query có điều kiện active vì thấy FK là **mất filter nghiệp vụ**.

### 24.3. Versioned lookup

Nếu bảng giá có nhiều phiên bản:

```text
product_id, valid_from, valid_to, price
```

JOIN theo `product_id` đơn thuần có thể nhân hàng. Phải JOIN thêm điều kiện ngày hiệu lực và đảm bảo không chồng khoảng. Việc optimizer chọn Hash Join hay Nested Loop không tự giải quyết một điều kiện JOIN thiếu.

## 25. Khả năng tương đương theo hệ quản trị

| Khía cạnh | PostgreSQL | SQL Server | MySQL | SQLite | Oracle |
| --- | --- | --- | --- | --- | --- |
| `EXCEPT` tập hợp | Có | Có | Hỗ trợ tùy phiên bản | Có | Có dạng `MINUS`/`EXCEPT` tùy phiên bản |
| `EXCEPT ALL` | Có | Không dùng như cú pháp phổ quát | Hỗ trợ/giới hạn tùy phiên bản | Không theo cú pháp phổ quát | Phụ thuộc phiên bản |
| `FULL OUTER JOIN` | Có | Có | Cần giải pháp khác nếu phiên bản không hỗ trợ | Phụ thuộc phiên bản | Có |
| `IS DISTINCT FROM` | Có | Có ở những phiên bản hiện đại | Có toán tử NULL-safe với cú pháp riêng | Có ở phiên bản hiện đại | Phụ thuộc phiên bản |
| Index partial/filtered | Partial index | Filtered index | Không cùng cú pháp | Partial index | Có thể dùng expression/function-based |
| `EXPLAIN` | EXPLAIN/ANALYZE | Execution plan/SHOWPLAN | EXPLAIN/EXPLAIN ANALYZE theo phiên bản | EXPLAIN QUERY PLAN | EXPLAIN PLAN/DBMS_XPLAN |
| Tính năng so sánh theo bag | `EXCEPT ALL` hai chiều | Group counts hoặc giải pháp khác | Group counts | Group counts | Group counts hoặc tính năng phiên bản |

Bảng này là định hướng khái niệm, **không phải khẳng định một cú pháp luôn chạy trên mọi phiên bản**. Tên toán tử, support của EXCEPT ALL, NULL-safe equality, kiểu dữ liệu, collations và query hints cần tra theo DBMS cụ thể.

### 25.1. SQL Server: so sánh multiset

Nếu không có `EXCEPT ALL`, dùng mẫu:

```sql
WITH tagged AS (
    SELECT key_col, value_col, 'OLD' AS src FROM old_result
    UNION ALL
    SELECT key_col, value_col, 'NEW' AS src FROM new_result
),
counts AS (
    SELECT
        key_col, value_col,
        SUM(CASE WHEN src='OLD' THEN 1 ELSE 0 END) AS old_count,
        SUM(CASE WHEN src='NEW' THEN 1 ELSE 0 END) AS new_count
    FROM tagged
    GROUP BY key_col, value_col
)
SELECT *
FROM counts
WHERE old_count <> new_count;
```

Ở đây `old_result` và `new_result` là **nguồn/CTE giả định** do người dùng thay bằng truy vấn của mình. Cần so sánh đúng types/collations; với các kiểu không group được, thiết kế phương án khác.

### 25.2. MySQL: NULL-safe equality

MySQL có toán tử `<=>` để kiểm tra equality kể cả NULL trong các phiên bản hỗ trợ, khác với `IS DISTINCT FROM` của PostgreSQL. Nhưng dùng `GROUP BY` để so sánh multiplicity đôi khi tránh được nhu cầu join bằng một biểu thức NULL-safe trên từng cột.

### 25.3. SQLite: EXPLAIN QUERY PLAN

SQLite `EXPLAIN QUERY PLAN` cho thông tin về đường truy cập như SCAN/SEARCH và index được dùng; nó không có giao diện/độ chi tiết giống PostgreSQL `EXPLAIN (ANALYZE, BUFFERS)`. Khi kiểm tính đúng, vẫn cần so sánh dữ liệu theo cùng ngữ nghĩa của SQLite, đặc biệt kiểu dữ liệu linh hoạt, NULL và collations.

### 25.4. Oracle: MINUS, NULL và kiểu dữ liệu

Oracle có cú pháp set difference truyền thống `MINUS`; các bản mới có thể hỗ trợ thêm dạng `EXCEPT`. Hỗ trợ biến thể ALL và cách xử lý NULL phụ thuộc version. Oracle còn có đặc điểm chuỗi rỗng thường được coi như NULL trong nhiều ngữ cảnh. Không copy nguyên bộ kiểm thử PostgreSQL sang Oracle mà bỏ qua semantics này.

## 26. Những lỗi phổ biến khi so sánh trước/sau tối ưu

| Lỗi | Hậu quả | Cách ngăn |
| --- | --- | --- |
| Chỉ nhìn execution time | Query sai vẫn có thể rất nhanh | Correctness gate trước EXPLAIN |
| Chỉ so sánh `COUNT(*)` | Hai tập hàng khác nhau vẫn có cùng count | So sánh multiset/giá trị |
| Chỉ so sánh `SUM(amount)` | Sai hàng có thể bù tổng, fanout khó thấy | So sánh theo khóa và bag |
| Chỉ dùng `EXCEPT` không ALL | Không phát hiện số lần duplicate khác nhau | `EXCEPT ALL` hai chiều hoặc group multiplicity |
| Kiểm một chiều A trừ B | Có thể bỏ sót hàng thừa ở B | Kiểm hai chiều |
| Chỉ test dữ liệu sạch | Không phát hiện NULL, duplicate, orphan | Thêm edge cases |
| Nhầm `COUNT(*)` và `COUNT(col)` | NULL làm đếm khác | Xác định chỉ số đúng |
| Đổi `AVG(x)` thành `AVG(COALESCE(x,0))` | Mẫu số thay đổi | Giữ NULL semantics |
| Đẩy predicate từ ON xuống WHERE của LEFT JOIN | Mất hàng trái không khớp | Xác minh outer join semantics |
| SUM sau JOIN một-nhiều | Nhân tiền theo số dòng con | Giữ đúng grain/aggregate trước |
| Dùng `SUM(DISTINCT amount)` khử fanout | Gộp những đơn khác nhau cùng tiền | Dedup bằng khóa nghiệp vụ |
| `UNION ALL` thành `UNION` | Mất multiplicity | Chứng minh có/không có duplicate |
| OR thành UNION ALL mà hai nhánh giao nhau | Nhân hàng thỏa cả hai | Làm hai nhánh rời nhau |
| `NOT IN` thành `NOT EXISTS` không xét NULL | Bộ lọc có thể đổi kết quả | Xác minh NOT NULL/logic |
| Bỏ JOIN dựa vào FK nhưng JOIN còn lọc active | Lộ hàng không active | Kiểm điều kiện đầy đủ |
| Dùng `LIMIT` không ORDER BY | Tập trang phụ thuộc plan | Thứ tự xác định với tie-breaker |
| ORDER BY cột không unique | Tie khiến trang không ổn định | Thêm khóa unique |
| So sánh hai query trên hai snapshot | Chênh do dữ liệu thay đổi | Cùng statement/snapshot |
| Đổi `< end` thành `<= end` | Sai hàng đúng biên | Khoảng nửa mở và test biên |
| Cast TIMESTAMPTZ sang DATE mà quên timezone | Lệch ngày | Chốt vùng giờ và mốc |
| Bỏ cast decimal | Chia nguyên/precision khác | Kiểm kiểu và scale |
| Bỏ `LOWER` hoặc đổi collation | So sánh chữ khác | Xác minh quy tắc normalization |
| So sánh hash mà không đối chiếu raw | Va chạm/encoding khiến bỏ sót | Hash chỉ dùng sàng lọc |
| `EXPLAIN ANALYZE` trên DML production | Thực thi thay đổi dữ liệu | Dùng test/transaction phù hợp |
| Chỉ test 10 hàng | Không phản ánh plan với dữ liệu lớn | Benchmark đại diện sau correctness |
| Bỏ qua tenant/soft delete | Query nhanh hơn nhưng lộ/sai dữ liệu | Hợp đồng phạm vi đầu ra |

## 27. Bài tập thực hành

Các bài dùng bảng `demo_eq_customers`, `demo_eq_orders` và `demo_eq_items` ở mục 2. Nên chạy trong cùng phiên PostgreSQL vì các bảng là TEMP. Không cần sửa dữ liệu để làm phần lớn bài tập.

### Bài 1 — Phát biểu hợp đồng kết quả

Viết bằng lời định nghĩa “đơn PAID chưa soft-delete của khách active tenant 10”: mỗi hàng biểu diễn điều gì, gồm những cột nào, có bao nhiêu hàng và có chấp nhận amount NULL không?

### Bài 2 — Đa tập và tập hợp

So sánh `SELECT amount` của order 101 và 102 với `SELECT DISTINCT amount`. Có bao nhiêu hàng ở mỗi kết quả? Vì sao DISTINCT thay đổi ý nghĩa dù giá trị amount đều là 100?

### Bài 3 — EXCEPT không phát hiện duplicate

Dùng A gồm hai order amount 100, B gồm một order amount 100. Chạy A EXCEPT B và B EXCEPT A. Sau đó chạy EXCEPT ALL hai chiều. Phương án nào phát hiện số lần xuất hiện khác nhau?

### Bài 4 — Mẫu GROUP BY đếm multiplicity

Dùng CTE `tagged` với nhãn OLD/NEW, UNION ALL hai phía rồi GROUP BY cột amount. Viết HAVING hoặc WHERE trên counts để chỉ ra A xuất hiện 2 lần, B 1 lần.

### Bài 5 — Null-safe so sánh

Tạo hai CTE có cùng order_id nhưng amount NULL ở một phía và amount 0 ở phía kia. Vì sao `a.amount <> b.amount` không phát hiện như mong đợi? Dùng `IS DISTINCT FROM` trong PostgreSQL.

### Bài 6 — COUNT và AVG

Tính số đơn PAID active-customer, COUNT(amount), SUM(amount), AVG(amount). Vì sao kết quả lần lượt là 6, 5, 560.00 và 112.00? Nếu thay AVG thành AVG(COALESCE(amount,0)), điều gì đổi?

### Bài 7 — Khách không có đơn

LEFT JOIN khách active với đơn PAID active, đặt điều kiện đơn trong ON. Vì sao khách 7 có số đơn 0? Nếu đẩy `o.status='PAID'` xuống WHERE, khách 7 còn không?

### Bài 8 — LEFT JOIN và COUNT(*)

Với khách 7, so sánh `COUNT(*)` và `COUNT(o.order_id)` sau LEFT JOIN. Chỉ số nào đúng khi muốn số đơn thực?

### Bài 9 — JOIN fanout

JOIN order 101 với demo_eq_items. Có bao nhiêu hàng? SUM(o.amount) bằng bao nhiêu? Vì sao 200 không phải số tiền thật của order 101?

### Bài 10 — DISTINCT không sửa fanout

Có nhiều đơn amount 100. Nếu viết SUM(DISTINCT amount), bạn sẽ bỏ mất khoản tiền hợp lệ nào? Đề xuất cách giữ một hàng mỗi order bằng khóa order_id.

### Bài 11 — OR và UNION ALL

So sánh `status='PAID' OR amount>=100` với UNION ALL của hai điều kiện. Những đơn nào nằm trong cả hai nhánh? Cách nào sửa UNION ALL để nhánh rời nhau?

### Bài 12 — NOT IN và NOT EXISTS

Thực thi hai ví dụ mục 7.3 có NULL trong danh sách. Vì sao 2 NOT IN (1,NULL) không cho TRUE nhưng NOT EXISTS lại trả 2? Cần giả thiết nào để rewrite an toàn?

### Bài 13 — ORDER BY và LIMIT

Hai order 101,102 có cùng created_at. Viết truy vấn chọn order mới nhất của customer 1 dùng ROW_NUMBER. Vì sao cần thêm `order_id DESC` để chọn cùng một hàng trên snapshot cố định?

### Bài 14 — ROW_NUMBER và RANK

Xếp hạng order của mỗi khách theo created_at DESC, không có tie-breaker. So sánh lọc ROW_NUMBER=1 và RANK=1 cho customer 1; số hàng có thể khác nhau thế nào?

### Bài 15 — DISTINCT ON

Viết truy vấn PostgreSQL DISTINCT ON(customer_id) để chọn đơn mới nhất, ORDER BY customer_id, created_at DESC, order_id DESC. Đối chiếu với ROW_NUMBER theo cùng thứ tự.

### Bài 16 — Date boundary

So sánh `created_at::DATE` với khoảng [start,end) định nghĩa theo +07. Nếu session PostgreSQL dùng UTC, vì sao kết quả có thể khác ở gần nửa đêm? Đề xuất tham số UTC instants được tính đúng.

### Bài 17 — BETWEEN vs khoảng nửa mở

Một event đúng 00:00 ngày sau có thuộc `BETWEEN start AND next_day_start` không? Nó có thuộc `created_at < next_day_start` không? Giải thích quy tắc biên.

### Bài 18 — Type semantics

So sánh `SELECT 1/2` với `SELECT 1::NUMERIC/2` trong PostgreSQL. Vì sao bỏ cast có thể thay đổi tỷ lệ báo cáo?

### Bài 19 — Hai hướng đối chiếu

Lấy truy vấn tham chiếu ở mục 2.1. Tạo một rewrite dùng CTE lọc orders trước rồi JOIN customers. Dùng EXCEPT ALL hai chiều để kiểm tra cùng result bag.

### Bài 20 — Bỏ filter sai

Trong rewrite của bài 19, cố ý bỏ `c.is_active`. Dùng EXCEPT ALL hai chiều xem order nào xuất hiện thêm. Vì sao tốc độ nhanh hơn không biện minh cho sai khác ấy?

### Bài 21 — Snapshot isolation

Giả sử một request đang INSERT/COMMIT đơn mới giữa hai lần chạy query. Làm sao phân biệt chênh lệch do dữ liệu đổi với do rewrite? Viết transaction REPEATABLE READ READ ONLY để so sánh.

### Bài 22 — Index rồi EXPLAIN

Tạo index `idx_demo_eq_paid_active` ở mục 21, xem EXPLAIN trước/sau cho điều kiện PAID chưa deleted. Tại sao bảng 10 hàng có thể vẫn dùng Seq Scan? Việc index có được dùng có chứng minh query đúng không?

### Bài 23 — Plan của JOIN

Viết hai query tương đương theo key customer/order, xem EXPLAIN thay đổi join strategy. Giải thích vì sao Hash Join và Nested Loop có thể cho cùng bag nhưng thứ tự hàng không được cam kết khi thiếu ORDER BY.

### Bài 24 — Báo cáo tài chính và soft delete

Giả sử doanh thu lịch sử cần tính cả order của khách inactive. Truy vấn tham chiếu active-customer có còn đúng? Định nghĩa lại hợp đồng và chỉ ra tại sao “tối ưu” bỏ điều kiện active có thể đúng với báo cáo này nhưng sai với API khách active.

### Bài 25 — Thiết kế kiểm thử tổng thể

Bạn được giao tối ưu truy vấn 5 triệu dòng, có JOIN nhiều bảng và LIMIT phân trang. Hãy thiết kế:

1. Hợp đồng result grain, type, NULL, tenant, active status, order.
2. Bộ dữ liệu biên với duplicate/NULL/no-match/fanout/ties.
3. So sánh đa tập hai chiều và schema output.
4. Snapshot đồng nhất và điều kiện tránh volatile functions.
5. EXPLAIN/ANALYZE, actual rows, loops, buffers, benchmark.
6. Giám sát production và đường rollback khi query khác kết quả.

## 28. Checklist trước khi chấp nhận một tối ưu SQL

### Hợp đồng

- [ ] Mỗi hàng đại diện đúng grain nghiệp vụ?
- [ ] Số cột, tên cột, kiểu dữ liệu và NULL semantics không đổi?
- [ ] Tenant, trạng thái active, soft delete, thời gian hiệu lực đúng?
- [ ] Có yêu cầu ORDER BY hoặc pagination không?
- [ ] Phép tổng hợp có đúng mẫu số, NULL và nhóm rỗng không?

### Đối chiếu

- [ ] Hai query chạy trên cùng snapshot/điều kiện tương đương?
- [ ] Kiểm COUNT/SUM để có dấu hiệu nhanh?
- [ ] Kiểm **multiset** hai chiều, không chỉ set hoặc COUNT?
- [ ] Có duplicate, NULL, outer join no-match, fanout, boundary, tie trong test?
- [ ] Có xem sự khác nhau về kiểu, collation, timezone và volatile functions?

### Hiệu năng

- [ ] Qua correctness gate rồi mới đo EXPLAIN/ANALYZE?
- [ ] Query có dùng index phù hợp với predicate và ORDER BY?
- [ ] Estimated rows vs actual rows có sai lệch lớn?
- [ ] Join order, sort, aggregate, spill, buffers, memory được xem xét?
- [ ] Dữ liệu và tham số benchmark đại diện cho workload thật?

### Triển khai

- [ ] Có regression tests cố định?
- [ ] Có quan sát kết quả/KPI sau deploy mà không làm lộ dữ liệu nhạy cảm?
- [ ] Có feature flag/rollback plan?
- [ ] Có xác minh DBMS version, collation, isolation và schema constraints?

## 29. Sơ đồ tư duy

```text
             TRUY VẤN GỐC ĐANG CHẬM
                       |
                       v
           Định nghĩa hợp đồng kết quả
             grain, NULL, duplicates,
             scope, types, ORDER BY
                       |
                       v
          Chọn rewrite / index / strategy
                       |
                       v
           Cùng snapshot và edge cases
                       |
                       v
             So sánh schema đầu ra
                       |
                       v
        EXCEPT ALL hai chiều / group counts
                       |
           +-----------+------------+
           |                        |
         Khác                    Tương đương
           |                        |
           v                        v
   DỪNG: tìm nguyên nhân       EXPLAIN / ANALYZE
   NULL, JOIN, bag, type,           |
   ORDER BY, thời gian             v
                            Benchmark workload
                                   |
                                   v
                           Deploy có giám sát
                                   |
                                   v
                              Regression tests
```

## 30. Kết luận

**Tính tương đương của kết quả là điều kiện tiên quyết của tối ưu truy vấn.** SQL thường vận hành theo ngữ nghĩa **đa tập**, vì vậy hai truy vấn trả cùng tập DISTINCT chưa chắc trả cùng số lần xuất hiện của mỗi hàng. NULL, LEFT JOIN, quan hệ một-nhiều, aggregate, GROUP BY, DISTINCT, LIMIT/ORDER BY, kiểu số, collation, timezone và hàm không xác định là những nơi rewrite rất dễ thay đổi dữ liệu mà không tạo lỗi cú pháp.

Một quy trình đáng tin bắt đầu bằng **hợp đồng kết quả và giả thiết schema**, chạy hai query trên **cùng snapshot**, đối chiếu **hai chiều bằng EXCEPT ALL hoặc số lần xuất hiện theo GROUP BY**, kiểm tra cột/kiểu/thứ tự khi cần. Chỉ khi qua được cổng correctness mới phân tích `EXPLAIN`, index, join strategies, số hàng ước tính/thực tế và các chỉ số hiệu năng.

Mục tiêu cuối cùng không phải chỉ khiến một SQL chạy ít mili giây hơn, mà là **trả đúng dữ liệu với chi phí thấp hơn**. Một kế hoạch thực thi đẹp không sửa được truy vấn sai; còn một kiểm thử tương đương có tính đến multiplicity, NULL, snapshot và ranh giới nghiệp vụ giúp biến tối ưu từ “hy vọng không đổi kết quả” thành một thay đổi có thể kiểm chứng và vận hành an toàn.
