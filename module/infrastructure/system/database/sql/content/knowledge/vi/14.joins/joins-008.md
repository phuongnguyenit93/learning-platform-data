# JOIN theo nhiều cột và điều kiện ngoài phép bằng

Trong SQL, điều kiện nối bảng không nhất thiết chỉ là `a.id = b.id`. Dữ liệu thực tế thường cần **nhiều cột cùng khớp**, chẳng hạn cặp `(tenant_id, order_id)`, hoặc cần kiểm tra những quan hệ **không phải bằng nhau**, chẳng hạn “ngày đặt hàng nằm trong khoảng hiệu lực của bảng giá”, “giá trị nằm trong một khoảng chiết khấu”, “hai khoảng thời gian giao nhau” hay “lấy bản ghi gần nhất trước một thời điểm”.

Nếu bỏ sót một cột trong khóa ghép, một đơn hàng của khách thuê A có thể bị nối nhầm với dòng hàng của khách thuê B. Nếu dùng sai toán tử biên, ngày bắt đầu bảng giá mới có thể khớp với **hai** bảng giá. Nếu chuyển điều kiện của bảng phải từ `ON` xuống `WHERE` trong `LEFT JOIN`, những đơn không có dòng liên quan có thể biến mất khỏi báo cáo.

Bài học thuộc **Database SQL → Kết nối bảng**, tập trung vào cách diễn đạt, đọc hiểu và kiểm soát tính đúng đắn của **`JOIN` theo nhiều cột và `JOIN` với điều kiện ngoài phép bằng** (*non-equi join*). Ví dụ chạy trực tiếp chủ yếu dùng **PostgreSQL**; các nguyên tắc SQL chung và các điểm khác biệt hệ quản trị được phân biệt rõ.

## 1. Điều kiện nối là một biểu thức logic

Cấu trúc phổ biến:

```sql
SELECT ...
FROM table_a AS a
JOIN table_b AS b
  ON join_condition;
```

`ON join_condition` là một **biểu thức điều kiện**, không bắt buộc là duy nhất một phép so sánh bằng.

Ví dụ:

```sql
-- Nối theo hai cột bằng nhau
ON a.tenant_id = b.tenant_id
AND a.order_id  = b.order_id

-- Nối theo một cột bằng nhau và một khoảng giá trị
ON a.tenant_id = b.tenant_id
AND a.order_date >= b.valid_from
AND a.order_date <  b.valid_to

-- Nối theo điều kiện lớn hơn
ON a.amount >= b.minimum_amount

-- Nối theo điều kiện ghép nhiều quy tắc
ON a.category = b.category
AND a.amount >= b.minimum_amount
AND (a.amount < b.maximum_amount OR b.maximum_amount IS NULL)
```

Trong SQL, điều kiện `ON` được tính theo logic ba giá trị: **TRUE**, **FALSE**, **UNKNOWN**. Một cặp hàng được coi là khớp khi điều kiện nối là **TRUE**. `FALSE` hoặc `UNKNOWN` không tạo ra cặp khớp.

**Hai câu hỏi luôn phải trả lời:**

1. **Khớp theo tiêu chí nào?** Đó là nội dung điều kiện `ON`.
2. **Nếu không khớp thì có giữ hàng không?** Đó là quyết định loại nối: `INNER JOIN`, `LEFT JOIN`, `RIGHT JOIN` hoặc `FULL JOIN`.

Điều kiện giống nhau nhưng loại `JOIN` khác nhau có thể cho tập kết quả khác nhau.

## 2. Dữ liệu thực hành: đơn hàng nhiều tenant và bảng giá theo thời gian

Các ví dụ dưới đây dùng PostgreSQL, gồm ba bảng tạm để minh họa cùng một hệ thống đặt hàng:

- `join_orders_lab`: mỗi đơn hàng được nhận diện bởi **hai cột** `(tenant_id, order_id)`.
- `join_lines_lab`: các dòng sản phẩm thuộc đơn hàng; có cả dòng cố tình không tìm được đơn tương ứng để quan sát `JOIN`.
- `join_prices_lab`: bảng giá có khoảng thời gian hiệu lực; cùng sản phẩm có thể có nhiều phiên bản giá.

Hãy chạy các lệnh trong **một kết nối PostgreSQL thực hành**. `TEMP TABLE` tồn tại theo phiên; nếu tên bảng đã tồn tại trong cùng phiên, mở một phiên mới hoặc đổi tên trước khi chạy lại.

### 2.1. Bảng đơn hàng

```sql
CREATE TEMP TABLE join_orders_lab (
    tenant_id     TEXT NOT NULL,
    order_id      INTEGER NOT NULL,
    customer_name TEXT NOT NULL,
    ordered_on    DATE NOT NULL,
    order_status  TEXT NOT NULL,
    PRIMARY KEY (tenant_id, order_id)
);

INSERT INTO join_orders_lab
    (tenant_id, order_id, customer_name, ordered_on, order_status)
VALUES
    ('T1', 101, 'An',    DATE '2026-04-10', 'PAID'),
    ('T1', 102, 'Bình',  DATE '2026-04-15', 'PAID'),
    ('T1', 104, 'Hà',    DATE '2026-05-02', 'CANCELLED'),
    ('T2', 101, 'Cường', DATE '2026-04-12', 'PAID'),
    ('T2', 103, 'Dung',  DATE '2026-05-03', 'PENDING'),
    ('T3', 105, 'Linh',  DATE '2026-04-05', 'PAID');
```

Chú ý: **`order_id = 101` xuất hiện ở cả T1 và T2**. Đây không phải dữ liệu trùng khóa vì khóa chính của bảng là **cặp `(tenant_id, order_id)`**, không phải riêng `order_id`.

### 2.2. Bảng dòng hàng

```sql
CREATE TEMP TABLE join_lines_lab (
    line_id   INTEGER PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    order_id  INTEGER NOT NULL,
    sku       TEXT NOT NULL,
    quantity  INTEGER NOT NULL CHECK (quantity > 0)
);

INSERT INTO join_lines_lab
    (line_id, tenant_id, order_id, sku, quantity)
VALUES
    (1, 'T1', 101, 'P01', 2),
    (2, 'T1', 101, 'P02', 1),
    (3, 'T1', 102, 'P01', 3),
    (4, 'T2', 101, 'P01', 1),
    (5, 'T2', 103, 'P02', 2),
    (6, 'T1', 999, 'P01', 1),
    (7, 'T2', 999, 'P09', 1),
    (8, 'T1', 104, 'P02', 1);
```

Hai dòng `line_id = 6, 7` có `order_id = 999` và không có đơn hàng tương ứng. Trong bài tập, bảng `join_lines_lab` **không khai báo foreign key** để giữ lại ví dụ về hàng thiếu quan hệ; hệ thống sản xuất thường cần chính sách toàn vẹn dữ liệu phù hợp.

### 2.3. Bảng giá theo khoảng hiệu lực

```sql
CREATE TEMP TABLE join_prices_lab (
    price_id   INTEGER PRIMARY KEY,
    tenant_id  TEXT NOT NULL,
    sku        TEXT NOT NULL,
    valid_from DATE NOT NULL,
    valid_to   DATE,
    unit_price NUMERIC(12, 2) NOT NULL,
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);

INSERT INTO join_prices_lab
    (price_id, tenant_id, sku, valid_from, valid_to, unit_price)
VALUES
    (1, 'T1', 'P01', DATE '2026-01-01', DATE '2026-04-15', 10.00),
    (2, 'T1', 'P01', DATE '2026-04-15', NULL,              12.00),
    (3, 'T1', 'P02', DATE '2026-01-01', NULL,              30.00),
    (4, 'T2', 'P01', DATE '2026-01-01', NULL,              20.00),
    (5, 'T2', 'P02', DATE '2026-01-01', DATE '2026-05-01', 30.00),
    (6, 'T2', 'P02', DATE '2026-05-01', NULL,              35.00);
```

Quy ước của bảng giá:

- `valid_from` là **ngày bắt đầu có hiệu lực**, được tính vào khoảng.
- `valid_to` là **ngày kết thúc hiệu lực độc quyền**, **không** tính vào khoảng.
- `valid_to IS NULL` nghĩa là **chưa có giới hạn ngày kết thúc** theo hợp đồng dữ liệu của ví dụ.

Cách biểu diễn khoảng **`[valid_from, valid_to)`** gọi là khoảng *nửa mở*: bao gồm đầu trái, loại đầu phải. Nó giúp hai bảng giá nối tiếp nhau có thể chia sẻ một mốc biên mà không trùng ngày hiệu lực.

## 3. JOIN theo nhiều cột: khớp toàn bộ khóa ghép

### 3.1. Nối đúng theo tenant_id và order_id

```sql
SELECT
    o.tenant_id,
    o.order_id,
    o.customer_name,
    l.line_id,
    l.sku,
    l.quantity
FROM join_orders_lab AS o
JOIN join_lines_lab AS l
  ON o.tenant_id = l.tenant_id
 AND o.order_id  = l.order_id
ORDER BY o.tenant_id, o.order_id, l.line_id;
```

Kết quả gồm những dòng có đủ **cả hai** điều kiện:

| tenant_id | order_id | customer_name | line_id | sku | quantity |
| --- | ---: | --- | ---: | --- | ---: |
| T1 | 101 | An | 1 | P01 | 2 |
| T1 | 101 | An | 2 | P02 | 1 |
| T1 | 102 | Bình | 3 | P01 | 3 |
| T1 | 104 | Hà | 8 | P02 | 1 |
| T2 | 101 | Cường | 4 | P01 | 1 |
| T2 | 103 | Dung | 5 | P02 | 2 |

- Đơn T1–101 khớp hai dòng: 1 và 2.
- Đơn T2–101 chỉ khớp dòng 4.
- Đơn T3–105 không có dòng hàng nên không xuất hiện trong `INNER JOIN`.
- Dòng 6 và 7 không có đơn cha tương ứng nên không xuất hiện.

**Đặt nhiều điều kiện bằng `AND` có nghĩa là mọi điều kiện đều phải đúng trên cùng một cặp hàng.**

### 3.2. Điều gì xảy ra nếu chỉ nối theo order_id?

```sql
-- Cố ý thiếu điều kiện tenant_id: KHÔNG dùng cho dữ liệu đa tenant
SELECT o.tenant_id AS order_tenant,
       l.tenant_id AS line_tenant,
       o.order_id,
       l.line_id
FROM join_orders_lab AS o
JOIN join_lines_lab AS l
  ON o.order_id = l.order_id
ORDER BY o.order_id, o.tenant_id, l.line_id;
```

Khi `order_id = 101` tồn tại ở T1 và T2, mỗi đơn có thể nối với cả dòng hàng thuộc tenant khác:

- Đơn **T1–101** bị ghép thêm dòng **T2–101 / line 4**.
- Đơn **T2–101** bị ghép thêm các dòng **T1–101 / line 1, 2**.

Đây là lỗi **ghép sai dữ liệu**, không chỉ là vấn đề hiệu năng. Trong ứng dụng đa tenant, quên `tenant_id` ở điều kiện nối còn có thể khiến dữ liệu thuộc phạm vi khác bị đưa vào kết quả; phải thiết kế cả ràng buộc, quyền truy cập và điều kiện truy vấn phù hợp.

### 3.3. Khóa ghép khác với nhiều bộ lọc độc lập

Điều kiện:

```sql
ON o.tenant_id = l.tenant_id
AND o.order_id = l.order_id
```

được hiểu là “**cặp tenant/order của hai bảng phải cùng khớp**”. Không phải “chỉ cần tenant khớp hoặc order khớp”. Tránh dùng:

```sql
-- Sai nếu quan hệ yêu cầu khớp cặp khóa:
ON o.tenant_id = l.tenant_id
OR o.order_id = l.order_id
```

`OR` cho phép rất nhiều cặp hàng không phải cùng đơn, thậm chí dẫn đến kết quả phình lớn. Chỉ dùng `OR` khi chính quy tắc nghiệp vụ thực sự cho phép **một trong các quan hệ thay thế** và đã kiểm soát trường hợp một hàng khớp nhiều nhánh.

## 4. USING cho nhiều cột và giới hạn của USING

Khi hai bảng có **cùng tên cột** và quan hệ chỉ dùng phép bằng theo từng cặp cột, PostgreSQL hỗ trợ:

```sql
SELECT tenant_id,
       order_id,
       o.customer_name,
       l.line_id,
       l.sku
FROM join_orders_lab AS o
JOIN join_lines_lab AS l
USING (tenant_id, order_id)
ORDER BY tenant_id, order_id, line_id;
```

`USING (tenant_id, order_id)` diễn đạt điều kiện bằng giữa các cột cùng tên ở hai bảng. Trong PostgreSQL, kết quả `JOIN ... USING` trình bày các cột dùng chung theo dạng **cột kết quả gộp**, thay vì hai bản sao `tenant_id` và hai bản sao `order_id` khi dùng `SELECT *` với `ON` thông thường.

So sánh:

```sql
-- Có thể biểu diễn khóa ghép dưới dạng USING
JOIN join_lines_lab AS l
USING (tenant_id, order_id)

-- Có thể biểu diễn khóa ghép dưới dạng ON
JOIN join_lines_lab AS l
  ON o.tenant_id = l.tenant_id
 AND o.order_id  = l.order_id
```

`USING` **không thay thế được `ON`** khi cần so sánh cột khác tên hoặc điều kiện ngoài phép bằng:

```sql
-- Cần ON để biểu diễn so sánh theo thời gian
JOIN join_prices_lab AS p
  ON p.tenant_id = l.tenant_id
 AND p.sku = l.sku
 AND o.ordered_on >= p.valid_from
```

Không nên dùng `NATURAL JOIN` để tự động nối theo mọi cột trùng tên: nếu schema thay đổi hoặc hai cột trùng tên nhưng khác ý nghĩa, kết quả có thể thay đổi ngoài dự kiến.

## 5. Điều kiện nối ngoài phép bằng là gì?

**Non-equi join** là phép nối có điều kiện không chỉ dựa trên `=`. Các phép so sánh thường gặp gồm `<`, `<=`, `>`, `>=`, `<>`; ngoài ra có thể có `BETWEEN`, kiểm tra khoảng, toán tử chuỗi, các hàm hoặc toán tử chuyên biệt của DBMS.

Ví dụ một bảng chứa các dải điểm, một bảng chứa điểm của khách hàng. Ta muốn tìm dải điểm chứa điểm của từng khách:

```sql
WITH scores(customer_id, points) AS (
    VALUES
        (1, 45),
        (2, 50),
        (3, 99),
        (4, 100),
        (5, NULL::INTEGER)
),
levels(level_name, min_points, max_points) AS (
    VALUES
        ('bronze',   0,  50),
        ('silver',  50, 100),
        ('gold',   100, 1000000)
)
SELECT s.customer_id,
       s.points,
       l.level_name
FROM scores AS s
LEFT JOIN levels AS l
  ON s.points >= l.min_points
 AND s.points <  l.max_points
ORDER BY s.customer_id;
```

Kết quả:

| customer_id | points | level_name |
| ---: | ---: | --- |
| 1 | 45 | bronze |
| 2 | 50 | silver |
| 3 | 99 | silver |
| 4 | 100 | gold |
| 5 | `NULL` | `NULL` |

Ở đây không có cột khóa chung giữa hai bảng. Điều kiện `points >= min_points AND points < max_points` xác định dải chứa giá trị, còn `LEFT JOIN` giữ khách thứ 5 ngay cả khi không xác định được mức.

### Khoảng [min, max) khác BETWEEN

Trong SQL, `BETWEEN lower AND upper` thông thường **bao gồm cả hai biên**:

```sql
s.points BETWEEN l.min_points AND l.max_points
```

Điều này tương đương với:

```sql
s.points >= l.min_points
AND s.points <= l.max_points
```

Nếu hai mức liên tiếp là `[0,50]` và `[50,100]` theo `BETWEEN`, điểm **50** có thể khớp **cả hai**. Vì thế, khi các khoảng được thiết kế nối tiếp nhau không trùng biên, dùng **`>= min` và `< max`** thường dễ kiểm soát hơn.

**Không phải `BETWEEN` luôn sai:** nó phù hợp khi cả hai biên thực sự được tính vào khoảng theo hợp đồng dữ liệu, chẳng hạn một khoảng ngày đóng hai đầu và các khoảng đã được thiết kế không chồng nhau.

## 6. JOIN bảng giá theo thời gian: vừa nhiều cột vừa bất đẳng thức

Đây là ví dụ trung tâm kết hợp cả hai kỹ thuật:

1. Cùng tenant.
2. Cùng mã sản phẩm.
3. Ngày đặt hàng **không trước ngày bắt đầu giá**.
4. Ngày đặt hàng **trước ngày kết thúc giá**, hoặc bảng giá chưa có ngày kết thúc.

```sql
SELECT
    o.tenant_id,
    o.order_id,
    o.ordered_on,
    l.line_id,
    l.sku,
    l.quantity,
    p.price_id,
    p.unit_price,
    l.quantity * p.unit_price AS line_amount
FROM join_orders_lab AS o
JOIN join_lines_lab AS l
  ON o.tenant_id = l.tenant_id
 AND o.order_id  = l.order_id
LEFT JOIN join_prices_lab AS p
  ON p.tenant_id = l.tenant_id
 AND p.sku       = l.sku
 AND o.ordered_on >= p.valid_from
 AND (
      o.ordered_on < p.valid_to
      OR p.valid_to IS NULL
 )
ORDER BY o.tenant_id, o.order_id, l.line_id;
```

Kết quả theo dữ liệu mẫu:

| tenant | order_id | line_id | sku | ordered_on | price_id | unit_price | line_amount |
| --- | ---: | ---: | --- | --- | ---: | ---: | ---: |
| T1 | 101 | 1 | P01 | 2026-04-10 | 1 | 10.00 | 20.00 |
| T1 | 101 | 2 | P02 | 2026-04-10 | 3 | 30.00 | 30.00 |
| T1 | 102 | 3 | P01 | 2026-04-15 | 2 | 12.00 | 36.00 |
| T1 | 104 | 8 | P02 | 2026-05-02 | 3 | 30.00 | 30.00 |
| T2 | 101 | 4 | P01 | 2026-04-12 | 4 | 20.00 | 20.00 |
| T2 | 103 | 5 | P02 | 2026-05-03 | 6 | 35.00 | 70.00 |

**Mốc quan trọng:** đơn **T1–102** vào đúng `2026-04-15` lấy phiên bản giá `price_id = 2`, vì giá cũ có `valid_to = '2026-04-15'` và biên phải bị loại. Tương tự, đơn **T2–103** ngày `2026-05-03` lấy giá `35.00` từ phiên bản bắt đầu `2026-05-01`.

Lựa chọn `LEFT JOIN` với bảng giá cho phép dòng hàng vẫn xuất hiện nếu **không tìm được bảng giá hợp lệ**; cột `unit_price` và `line_amount` khi đó là `NULL`. Nếu ứng dụng đòi hỏi mỗi dòng luôn phải có giá, có thể dùng `INNER JOIN` để chỉ lấy dòng có giá **hoặc** giữ `LEFT JOIN` rồi báo lỗi dữ liệu thiếu giá trong cột trạng thái. Không nên âm thầm loại dòng hàng khỏi báo cáo doanh thu nếu đây là vấn đề chất lượng dữ liệu cần xử lý.

### Khi valid_to là NULL

Điều kiện:

```sql
o.ordered_on < p.valid_to OR p.valid_to IS NULL
```

được đặt trong ngoặc vì nó là **một phần của quy tắc hiệu lực giá**, không phải một nhánh `OR` độc lập cho toàn bộ phép nối. Nếu `valid_to` là `NULL`, phép `o.ordered_on < p.valid_to` trả UNKNOWN; `p.valid_to IS NULL` trả TRUE, nên điều kiện trong ngoặc trở thành TRUE.

Nếu thiếu ngoặc:

```sql
-- Sai: OR có thể bỏ qua điều kiện tenant, sku và valid_from
ON p.tenant_id = l.tenant_id
AND p.sku = l.sku
AND o.ordered_on >= p.valid_from
AND o.ordered_on < p.valid_to
OR p.valid_to IS NULL
```

SQL hiểu `AND` trước `OR`, tương đương:

```text
(đúng tenant
 AND đúng sku
 AND ngày >= valid_from
 AND ngày < valid_to)
OR valid_to IS NULL
```

Kết quả có thể ghép **mọi bản giá không có ngày kết thúc** vào mọi dòng hàng, kể cả khác tenant hay sản phẩm. Đây là một trong những lỗi non-equi join nguy hiểm nhất.

## 7. Kiểm tra các khoảng hiệu lực chồng nhau

Một câu `JOIN` theo ngày có thể tạo **nhiều hàng giá** cho cùng một dòng nếu dữ liệu bảng giá chứa các khoảng chồng lên nhau.

Ví dụ một sản phẩm có hai khoảng:

```text
Giá A: [2026-04-01, 2026-04-20)
Giá B: [2026-04-10, 2026-05-01)
                    ↑
         Ngày 2026-04-15 thuộc cả A và B
```

Khi nối ngày `2026-04-15`, cả hai bản giá đều hợp lệ theo điều kiện. SQL không tự chọn “bản mới hơn” hay “giá rẻ hơn”. Nếu có hai hàng khớp, kết quả thường có **hai hàng**.

Điều kiện giao nhau của hai khoảng nửa mở `[start_a,end_a)` và `[start_b,end_b)` có kết thúc hữu hạn là:

\[
start_a < end_b \quad\text{và}\quad start_b < end_a
\]

Có thể tìm cặp khoảng chồng nhau trong bảng giá bằng **self join**:

```sql
SELECT
    a.tenant_id,
    a.sku,
    a.price_id AS first_price_id,
    b.price_id AS second_price_id
FROM join_prices_lab AS a
JOIN join_prices_lab AS b
  ON a.tenant_id = b.tenant_id
 AND a.sku       = b.sku
 AND a.price_id  < b.price_id
 AND (a.valid_to IS NULL OR b.valid_from < a.valid_to)
 AND (b.valid_to IS NULL OR a.valid_from < b.valid_to)
ORDER BY a.tenant_id, a.sku, a.price_id, b.price_id;
```

Với dữ liệu mẫu ban đầu, truy vấn không trả hàng nào vì các phiên bản được thiết kế không chồng lên nhau.

Giải thích điều kiện:

- `a.price_id < b.price_id` chỉ lấy mỗi **cặp khác nhau một lần**, không nối một giá với chính nó.
- Hai điều kiện liên quan ngày xác định khoảng thời gian **giao nhau thật sự**, với `NULL` được hiểu là không có giới hạn kết thúc.
- Dùng `<` thay vì `<=` vì hai khoảng nửa mở chỉ **chạm tại một biên** chưa được coi là chồng nhau.

Điều kiện này dựa trên giả định `valid_from` không `NULL`, `valid_to` nếu có thì lớn hơn `valid_from` và `NULL` có nghĩa là kết thúc vô hạn. Nếu dữ liệu có khoảng không hợp lệ hoặc dùng khoảng đóng hai đầu, công thức cần được điều chỉnh.

### Phòng ngừa thay vì chỉ phát hiện

Đối với bảng giá theo lịch sử, có thể chọn một hoặc nhiều biện pháp:

- Định nghĩa rõ hợp đồng khoảng `[valid_from, valid_to)`.
- Dùng ràng buộc để không cho phép `valid_to <= valid_from`.
- Kiểm tra **không chồng khoảng** trong nghiệp vụ ghi dữ liệu.
- Dùng tính năng ràng buộc khoảng của DBMS khi phù hợp; PostgreSQL có kiểu `daterange`/`tsrange` và exclusion constraint, nhưng đó là thiết kế riêng cần triển khai chủ động.
- Nếu có nhiều hàng hợp lệ theo chính sách ưu tiên, quy định rõ thuật toán chọn: ưu tiên phiên bản nào, cách phá hòa khi ngày bắt đầu trùng nhau.

Đừng chữa lỗi trùng kết quả bằng `SELECT DISTINCT` một cách máy móc: có thể che triệu chứng mà vẫn giữ khả năng chọn sai giá và tính sai tổng.

## 8. ON và WHERE không thể thay thế tùy tiện trong OUTER JOIN

Đây là khác biệt cốt lõi giữa “**tiêu chí khớp hàng**” và “**tiêu chí giữ kết quả**”.

### 8.1. INNER JOIN: thường có thể chuyển điều kiện lọc đơn giản

Với `INNER JOIN`, hai câu sau thường tương đương về **tập kết quả** khi điều kiện là các biểu thức SQL xác định thông thường:

```sql
-- Điều kiện trong ON
SELECT o.tenant_id, o.order_id, l.line_id
FROM join_orders_lab AS o
JOIN join_lines_lab AS l
  ON o.tenant_id = l.tenant_id
 AND o.order_id = l.order_id
 AND l.quantity >= 2;
```

```sql
-- Điều kiện cùng ý nghĩa trong WHERE của INNER JOIN
SELECT o.tenant_id, o.order_id, l.line_id
FROM join_orders_lab AS o
JOIN join_lines_lab AS l
  ON o.tenant_id = l.tenant_id
 AND o.order_id = l.order_id
WHERE l.quantity >= 2;
```

Cả hai chỉ giữ dòng hàng có `quantity >= 2` và khớp đơn cha theo cặp khóa. Trên ví dụ, đó là **line 1, 3, 5**.

Vẫn nên đặt **quan hệ khớp khóa** trong `ON` và **bộ lọc báo cáo** ở `WHERE` khi có thể, để người đọc dễ hiểu mục đích. Ngoại lệ có thể phát sinh với biểu thức không thuần, hàm có tác dụng phụ hoặc cách DBMS tối ưu truy vấn; không dùng quy tắc chuyển vị trí như một phép biến đổi tùy tiện cho mọi SQL.

### 8.2. LEFT JOIN: điều kiện trong ON giữ lại hàng không khớp

```sql
SELECT
    o.tenant_id,
    o.order_id,
    l.line_id,
    l.quantity
FROM join_orders_lab AS o
LEFT JOIN join_lines_lab AS l
  ON o.tenant_id = l.tenant_id
 AND o.order_id  = l.order_id
 AND l.quantity >= 2
ORDER BY o.tenant_id, o.order_id, l.line_id;
```

Điều kiện `l.quantity >= 2` chỉ cho phép các dòng hàng có số lượng đủ lớn **khớp vào đơn**. Mọi đơn bên trái vẫn được giữ, kể cả khi không có dòng đủ điều kiện; khi đó `l.line_id` và `l.quantity` là `NULL`.

Ở dữ liệu mẫu:

- T1–101 khớp line 1 (`quantity = 2`), line 2 bị loại khỏi quan hệ khớp.
- T1–102 khớp line 3 (`quantity = 3`).
- T2–103 khớp line 5 (`quantity = 2`).
- T1–104, T2–101 và T3–105 vẫn có hàng kết quả nhưng phần `l` là `NULL`.

### 8.3. Đưa điều kiện bảng phải xuống WHERE có thể loại hàng bên trái

```sql
SELECT
    o.tenant_id,
    o.order_id,
    l.line_id,
    l.quantity
FROM join_orders_lab AS o
LEFT JOIN join_lines_lab AS l
  ON o.tenant_id = l.tenant_id
 AND o.order_id = l.order_id
WHERE l.quantity >= 2
ORDER BY o.tenant_id, o.order_id, l.line_id;
```

Các hàng không có dòng khớp hoặc có dòng `quantity < 2` bị loại sau khi nối. Trong ví dụ này, kết quả chỉ còn **3 dòng: line 1, 3, 5**.

Bảng so sánh:

| Cách đặt điều kiện `l.quantity >= 2` | Có giữ đơn không có dòng ≥ 2? | Ý nghĩa |
| --- | --- | --- |
| `LEFT JOIN ... ON ... AND l.quantity >= 2` | Có | Giữ tất cả đơn, đính kèm những dòng đủ điều kiện |
| `LEFT JOIN ... ON ... WHERE l.quantity >= 2` | Không | Chỉ giữ các đơn/dòng có dòng đủ điều kiện |

Quy tắc này đặc biệt quan trọng khi `ON` chứa so sánh khoảng ngày hay giới hạn phiên bản: đưa predicate về `WHERE` có thể làm mất các hàng **thiếu bảng giá** mà doanh nghiệp đang cần phát hiện.

### 8.4. Muốn tìm hàng thiếu quan hệ, dùng kiểm tra khóa hoặc NOT EXISTS

Tìm đơn **chưa có bất kỳ dòng hàng nào**:

```sql
SELECT o.tenant_id, o.order_id
FROM join_orders_lab AS o
LEFT JOIN join_lines_lab AS l
  ON o.tenant_id = l.tenant_id
 AND o.order_id  = l.order_id
WHERE l.line_id IS NULL
ORDER BY o.tenant_id, o.order_id;
```

Kết quả là **T3–105**. `line_id` là khóa chính không `NULL` của bảng dòng hàng nên `l.line_id IS NULL` sau `LEFT JOIN` có nghĩa không có hàng khớp.

Cách diễn đạt tương đương bằng `NOT EXISTS`:

```sql
SELECT o.tenant_id, o.order_id
FROM join_orders_lab AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM join_lines_lab AS l
    WHERE l.tenant_id = o.tenant_id
      AND l.order_id  = o.order_id
)
ORDER BY o.tenant_id, o.order_id;
```

`NOT EXISTS` thường rõ nghĩa hơn khi mục tiêu là “**không tồn tại dòng thỏa điều kiện**” và không tạo bản sao hàng bên trái khi có nhiều dòng bên phải. Nó cũng có thể được dùng với điều kiện bất đẳng thức.

## 9. Điều kiện lọc theo thời gian trong ON và WHERE

Một yêu cầu thường gặp:

> Lấy **tất cả đơn hàng**, kèm những dòng hàng nếu có, nhưng chỉ lấy bảng giá có hiệu lực vào ngày đặt.

Để không mất đơn không có dòng hoặc thiếu giá, cần suy nghĩ theo từng cấp `LEFT JOIN`:

```sql
SELECT
    o.tenant_id,
    o.order_id,
    l.line_id,
    l.sku,
    p.unit_price
FROM join_orders_lab AS o
LEFT JOIN join_lines_lab AS l
  ON o.tenant_id = l.tenant_id
 AND o.order_id  = l.order_id
LEFT JOIN join_prices_lab AS p
  ON p.tenant_id = l.tenant_id
 AND p.sku       = l.sku
 AND o.ordered_on >= p.valid_from
 AND (o.ordered_on < p.valid_to OR p.valid_to IS NULL)
ORDER BY o.tenant_id, o.order_id, l.line_id;
```

Với dòng không có giá, `p.unit_price` là `NULL` nhưng hàng của đơn/dòng vẫn tồn tại. Với đơn T3–105 không có dòng hàng, các cột `l` và `p` đều là `NULL`.

Nếu thêm điều kiện:

```sql
WHERE p.unit_price > 0
```

thì mọi hàng không có giá bị loại vì `NULL > 0` là UNKNOWN. Khi cần phát hiện những dòng thiếu giá, không nên lọc như vậy rồi kết luận bảng dữ liệu đầy đủ.

Có thể trả cột trạng thái:

```sql
SELECT o.tenant_id, o.order_id, l.line_id,
       CASE
           WHEN l.line_id IS NULL THEN 'no_line'
           WHEN p.price_id IS NULL THEN 'missing_price'
           ELSE 'priced'
       END AS join_status
FROM join_orders_lab AS o
LEFT JOIN join_lines_lab AS l
  ON o.tenant_id = l.tenant_id
 AND o.order_id  = l.order_id
LEFT JOIN join_prices_lab AS p
  ON p.tenant_id = l.tenant_id
 AND p.sku = l.sku
 AND o.ordered_on >= p.valid_from
 AND (o.ordered_on < p.valid_to OR p.valid_to IS NULL)
ORDER BY o.tenant_id, o.order_id, l.line_id;
```

Cột trạng thái giúp phân biệt **không có dòng hàng** và **có dòng hàng nhưng chưa có giá**. Bảng mẫu hiện không có dòng hợp lệ thuộc đơn cha mà thiếu giá; nếu dữ liệu thật có trường hợp đó, nhánh `missing_price` sẽ nhận diện.

## 10. JOIN bằng khoảng thời gian giao nhau

Một loại non-equi join khác không hỏi “mốc thời gian nằm trong khoảng nào?” mà hỏi **“hai khoảng thời gian có giao nhau không?”**.

Ví dụ cần xác định một ca làm việc chồng với một khoảng bảo trì. Với quy ước khoảng nửa mở, hai khoảng `[a_start,a_end)` và `[b_start,b_end)` có giao nhau thật sự khi:

```sql
a.start_at < b.end_at
AND b.start_at < a.end_at
```

Thực hành trên các khoảng ngày, không cần tạo bảng lâu dài:

```sql
WITH shifts(shift_id, start_on, end_on) AS (
    VALUES
        (1, DATE '2026-06-01', DATE '2026-06-04'),
        (2, DATE '2026-06-04', DATE '2026-06-07'),
        (3, DATE '2026-06-06', DATE '2026-06-09')
),
maintenance(maintenance_id, start_on, end_on) AS (
    VALUES
        (10, DATE '2026-06-03', DATE '2026-06-05'),
        (11, DATE '2026-06-09', DATE '2026-06-10')
)
SELECT
    s.shift_id,
    m.maintenance_id
FROM shifts AS s
JOIN maintenance AS m
  ON s.start_on < m.end_on
 AND m.start_on < s.end_on
ORDER BY s.shift_id, m.maintenance_id;
```

Kết quả là hai cặp: **(1,10)** và **(2,10)**.

- Shift 1 `[06-01,06-04)` giao với bảo trì 10 `[06-03,06-05)`.
- Shift 2 `[06-04,06-07)` cũng giao với bảo trì 10.
- Shift 3 kết thúc `06-09`, bảo trì 11 bắt đầu `06-09`; hai khoảng **chạm biên nhưng không giao** theo quy ước nửa mở.

Với hệ thống thực dùng `TIMESTAMP` hoặc `TIMESTAMPTZ`, phải xác định thời điểm, múi giờ, tính bao gồm biên và cách xử lý đầu mút `NULL`. Sai lệch một dấu `<`/`<=` có thể dẫn đến đặt trùng lịch hoặc bỏ sót giao nhau.

### Toán tử khoảng chuyên biệt của PostgreSQL

PostgreSQL có các kiểu `daterange`, `tsrange`, `tstzrange` và toán tử chồng khoảng `&&`. Ví dụ minh họa:

```sql
SELECT
    daterange(DATE '2026-06-01', DATE '2026-06-04', '[)')
    &&
    daterange(DATE '2026-06-03', DATE '2026-06-05', '[)')
    AS overlaps;
```

Kết quả là `TRUE`. Đây là tính năng **PostgreSQL-specific**, không phải cú pháp SQL phổ quát. Các phép so sánh `<` ở trên vẫn là điểm khởi đầu dễ hiểu và có thể áp dụng rộng.

## 11. JOIN lớn hơn/nhỏ hơn và nguy cơ sinh rất nhiều cặp

Xét hai tập:

```sql
WITH thresholds(minimum_score) AS (
    VALUES (20), (50), (80)
),
students(student_id, score) AS (
    VALUES (1, 30), (2, 60), (3, 90)
)
SELECT
    s.student_id,
    s.score,
    t.minimum_score
FROM students AS s
JOIN thresholds AS t
  ON s.score >= t.minimum_score
ORDER BY s.student_id, t.minimum_score;
```

Kết quả:

| student_id | score | minimum_score |
| ---: | ---: | ---: |
| 1 | 30 | 20 |
| 2 | 60 | 20 |
| 2 | 60 | 50 |
| 3 | 90 | 20 |
| 3 | 90 | 50 |
| 3 | 90 | 80 |

Một học sinh có thể đạt **nhiều ngưỡng cùng lúc**. `JOIN` không tự chọn ngưỡng cao nhất.

Nếu mục tiêu là **“lấy ngưỡng cao nhất mà mỗi học sinh đạt được”**, có thể tổng hợp:

```sql
WITH thresholds(minimum_score) AS (
    VALUES (20), (50), (80)
),
students(student_id, score) AS (
    VALUES (1, 30), (2, 60), (3, 90)
)
SELECT s.student_id,
       MAX(t.minimum_score) AS highest_reached_threshold
FROM students AS s
LEFT JOIN thresholds AS t
  ON s.score >= t.minimum_score
GROUP BY s.student_id
ORDER BY s.student_id;
```

Kết quả các ngưỡng cao nhất là **20, 50, 80**. Dùng `LEFT JOIN` giúp giữ học sinh không đạt bất kỳ ngưỡng nào với kết quả `NULL`.

**Quy tắc:** non-equi join thường tạo quan hệ **một-nhiều** hoặc **nhiều-nhiều**. Trước khi tính `SUM` hay `COUNT` trên kết quả, cần xác định một hàng nguồn được phép ghép với bao nhiêu hàng đích.

## 12. Chọn một bản ghi phù hợp thay vì tất cả bản ghi phù hợp

Một bài toán phổ biến là *as-of join*: với mỗi sự kiện, tìm cấu hình hoặc bản ghi có mốc hiệu lực mới nhất **không vượt quá thời điểm sự kiện**.

Giả sử bảng cấu hình có nhiều phiên bản nhưng **không có valid_to**, chỉ có `effective_from`:

```sql
WITH events(event_id, occurred_on) AS (
    VALUES
        (1, DATE '2026-04-10'),
        (2, DATE '2026-04-15'),
        (3, DATE '2026-05-03')
),
config_versions(version_id, effective_from, rate) AS (
    VALUES
        (1, DATE '2026-01-01', 0.05::NUMERIC),
        (2, DATE '2026-04-15', 0.08::NUMERIC),
        (3, DATE '2026-05-01', 0.10::NUMERIC)
)
SELECT e.event_id,
       e.occurred_on,
       c.version_id,
       c.rate
FROM events AS e
LEFT JOIN LATERAL (
    SELECT v.version_id, v.rate
    FROM config_versions AS v
    WHERE v.effective_from <= e.occurred_on
    ORDER BY v.effective_from DESC, v.version_id DESC
    LIMIT 1
) AS c ON TRUE
ORDER BY e.event_id;
```

Kết quả:

| event_id | occurred_on | version_id | rate |
| ---: | --- | ---: | ---: |
| 1 | 2026-04-10 | 1 | 0.05 |
| 2 | 2026-04-15 | 2 | 0.08 |
| 3 | 2026-05-03 | 3 | 0.10 |

Giải thích:

- `v.effective_from <= e.occurred_on` là điều kiện **ngoài phép bằng**.
- `LATERAL` cho phép truy vấn con tham chiếu hàng `e` đang được xử lý.
- `ORDER BY v.effective_from DESC, v.version_id DESC LIMIT 1` chọn một phiên bản mới nhất; tiêu chí thứ hai giúp phá hòa nếu có nhiều phiên bản cùng ngày.
- `LEFT JOIN ... ON TRUE` giữ sự kiện không tìm được phiên bản trước nó; các cột `c` khi đó là `NULL`.

Đây là ví dụ **riêng cho PostgreSQL** (cũng có hỗ trợ `LATERAL` ở một số hệ khác). SQL Server thường có `OUTER APPLY` cho mẫu truy vấn tương tự; DBMS khác có thể dùng hàm cửa sổ `ROW_NUMBER` hoặc subquery tùy cú pháp.

Không nên dùng `LIMIT 1` mà thiếu `ORDER BY`: khi nhiều bản ghi khớp, kết quả được chọn có thể không ổn định.

## 13. NULL trong điều kiện nối nhiều cột

Khi so sánh bằng thông thường:

```sql
a.optional_code = b.optional_code
```

nếu một hoặc cả hai giá trị là `NULL`, phép so sánh không trả TRUE mà trả **UNKNOWN**. Vì thế, hai hàng đều có `optional_code IS NULL` **không được xem là khớp** chỉ bởi điều kiện `=`.

Ví dụ:

```sql
WITH a(id, code) AS (
    VALUES (1, NULL::TEXT), (2, 'X'::TEXT)
),
b(id, code) AS (
    VALUES (10, NULL::TEXT), (20, 'X'::TEXT)
)
SELECT a.id AS a_id,
       b.id AS b_id
FROM a
JOIN b ON a.code = b.code
ORDER BY a.id, b.id;
```

Kết quả chỉ có **(2,20)**.

### Muốn coi hai NULL là cùng trạng thái để khớp

PostgreSQL hỗ trợ `IS NOT DISTINCT FROM`:

```sql
WITH a(id, code) AS (
    VALUES (1, NULL::TEXT), (2, 'X'::TEXT)
),
b(id, code) AS (
    VALUES (10, NULL::TEXT), (20, 'X'::TEXT)
)
SELECT a.id AS a_id,
       b.id AS b_id
FROM a
JOIN b
  ON a.code IS NOT DISTINCT FROM b.code
ORDER BY a.id, b.id;
```

Kết quả gồm **(1,10)** và **(2,20)**.

Toán tử này trả TRUE cho hai giá trị `NULL`; nó hữu ích nếu nghiệp vụ **thực sự quy định** “hai mã cùng thiếu được xem là cùng nhóm”. Tuy nhiên, nếu `NULL` có nghĩa là “không biết mã” thì ghép hai hàng chưa biết mã với nhau có thể là sai về mặt dữ liệu.

Một cách viết khác, rõ ràng nhưng dài:

```sql
ON (
     a.code = b.code
     OR (a.code IS NULL AND b.code IS NULL)
   )
```

Không nên dùng bừa:

```sql
ON COALESCE(a.code, 'UNKNOWN') = COALESCE(b.code, 'UNKNOWN')
```

nếu chuỗi `'UNKNOWN'` có thể xuất hiện như một mã thật. Khi đó, một `NULL` sẽ nối nhầm với mã `'UNKNOWN'`. Ngoài ra, áp dụng hàm lên cột cũng có thể ảnh hưởng cách sử dụng index.

### NULL trong điều kiện khoảng

Trong non-equi join:

```sql
ON a.date_value >= b.valid_from
AND a.date_value < b.valid_to
```

nếu `b.valid_to IS NULL`, điều kiện thứ hai là UNKNOWN, nên cặp hàng không khớp. Muốn `NULL` đại diện “không có ngày kết thúc”, phải **viết quy tắc đó rõ ràng**:

```sql
AND (a.date_value < b.valid_to OR b.valid_to IS NULL)
```

Không thể suy ra mọi cột ngày kết thúc `NULL` đều có nghĩa “vô hạn”; trong hệ khác nó có thể là “chưa biết”, và cách xử lý phải theo quy định dữ liệu.

## 14. Đếm kết quả nối: phân biệt số hàng trái và số cặp khớp

Một điều kiện `JOIN` đúng vẫn có thể trả nhiều hàng hơn dự đoán do quan hệ một-nhiều.

Ví dụ:

```sql
SELECT
    o.tenant_id,
    o.order_id,
    COUNT(l.line_id) AS matched_line_count
FROM join_orders_lab AS o
LEFT JOIN join_lines_lab AS l
  ON o.tenant_id = l.tenant_id
 AND o.order_id  = l.order_id
GROUP BY o.tenant_id, o.order_id
ORDER BY o.tenant_id, o.order_id;
```

Kết quả:

| tenant_id | order_id | matched_line_count |
| --- | ---: | ---: |
| T1 | 101 | 2 |
| T1 | 102 | 1 |
| T1 | 104 | 1 |
| T2 | 101 | 1 |
| T2 | 103 | 1 |
| T3 | 105 | 0 |

`COUNT(l.line_id)` đếm **dòng hàng thực sự khớp**. Nếu dùng `COUNT(*)`, đơn T3–105 vẫn có `COUNT(*) = 1` vì `LEFT JOIN` tạo một hàng bảo toàn bên trái với các cột `l` là `NULL`.

### Chú ý khi tính SUM sau JOIN nhiều-bên

Giả sử nối đơn hàng, dòng hàng và **hai** bản ghi bảng giá cùng khớp. Một dòng hàng có thể trở thành hai hàng kết quả; nếu làm:

```sql
SUM(l.quantity * p.unit_price)
```

thì thành tiền có thể bị **nhân đôi hoặc tính theo hai mức giá**, tùy dữ liệu. Trước khi tổng hợp, phải xác định:

- Một dòng hàng có thể có **bao nhiêu** bản giá hợp lệ?
- Có ràng buộc tránh chồng khoảng hay quy tắc chọn một phiên bản không?
- Các bản ghi có phải là những dòng chi tiết hợp lệ hay là các bản sao do điều kiện nối thiếu?
- `SUM` đang được tính ở cấp dòng, đơn hay nhóm?

`DISTINCT` không phải phương án sửa tổng quát: hai dòng hàng thật có thể cùng số lượng và số tiền, nhưng vẫn phải được tính hai lần.

## 15. Hiệu năng của điều kiện nhiều cột và non-equi join

`JOIN` theo nhiều cột có thể tận dụng index và thống kê dữ liệu nếu thiết kế phù hợp. Nhưng không có một quy tắc “cứ thêm index là nhanh”; cần quan sát truy vấn thực tế, số lượng hàng, độ chọn lọc, phân bố dữ liệu và kế hoạch tối ưu.

### 15.1. Index nhiều cột cho khóa ghép

Với hai cột `tenant_id` và `order_id` thường được nối cùng nhau:

```sql
-- Ví dụ minh họa; không bắt buộc tạo cho bài thực hành
CREATE INDEX ON join_lines_lab (tenant_id, order_id);
```

Trong bảng `join_orders_lab`, khóa chính `PRIMARY KEY (tenant_id, order_id)` đã tạo cấu trúc hỗ trợ tính duy nhất và truy cập khóa theo cơ chế PostgreSQL. Bảng dòng hàng không có foreign key để phục vụ ví dụ; với hệ thống thật, có thể bổ sung khóa ngoại ghép:

```sql
-- Phác thảo cấu trúc cho một hệ thống thật:
-- FOREIGN KEY (tenant_id, order_id)
-- REFERENCES orders (tenant_id, order_id)
```

Không áp dụng trực tiếp khóa ngoại đó vào `join_lines_lab` khi dữ liệu mẫu còn hai dòng cố ý không có đơn cha, vì ràng buộc sẽ từ chối dữ liệu minh họa.

**Thứ tự cột trong index ghép** ảnh hưởng những điều kiện lọc nào được hưởng lợi; ví dụ index `(tenant_id, order_id)` và `(order_id, tenant_id)` không hoàn toàn tương đương trong mọi kế hoạch truy vấn. Xác định thứ tự từ các điều kiện `WHERE`, `JOIN` và mẫu truy cập thường dùng.

### 15.2. Kết hợp bằng và bất đẳng thức

Một trường hợp bảng giá:

```sql
ON p.tenant_id = l.tenant_id
AND p.sku = l.sku
AND p.valid_from <= o.ordered_on
```

có thể phù hợp với index kiểu:

```sql
-- Ví dụ hướng thiết kế index ở PostgreSQL
CREATE INDEX ON join_prices_lab (tenant_id, sku, valid_from);
```

Các cột bằng thường là phần thuận lợi để giới hạn tập ứng viên, sau đó điều kiện ngày có thể thu hẹp thêm. Tuy nhiên, điều kiện `valid_to IS NULL OR ...`, số phiên bản giá, tính chồng khoảng và cách optimizer chọn join algorithm đều ảnh hưởng hiệu năng. Không nên tuyên bố index này luôn tối ưu cho mọi dữ liệu.

### 15.3. Tập ứng viên có thể rất lớn

Một điều kiện đơn giản:

```sql
ON a.value < b.value
```

có thể tạo rất nhiều cặp hàng, đặc biệt khi không có khóa bằng để giới hạn ứng viên. Hai bảng mỗi bảng có `n` và `m` hàng có thể tạo tối đa `n × m` cặp trước khi áp dụng điều kiện; kết quả đủ lớn sẽ tốn bộ nhớ, CPU và thời gian truyền dữ liệu.

Với truy vấn cần “một kết quả tốt nhất”, hãy cân nhắc `LATERAL`, `ROW_NUMBER` hoặc tổng hợp phù hợp thay vì lấy tất cả cặp rồi chọn thủ công ở ứng dụng.

### 15.4. Kiểm tra kế hoạch với EXPLAIN

Trong PostgreSQL, có thể dùng:

```sql
EXPLAIN
SELECT o.tenant_id, o.order_id, l.line_id
FROM join_orders_lab AS o
JOIN join_lines_lab AS l
  ON o.tenant_id = l.tenant_id
 AND o.order_id  = l.order_id;
```

`EXPLAIN` thường hiển thị kế hoạch dự kiến như hash join, merge join hoặc nested loop, tùy thống kê và kích thước dữ liệu. Với bộ dữ liệu tạm rất nhỏ, PostgreSQL hoàn toàn có thể chọn quét tuần tự mà vẫn hợp lý; không suy từ ví dụ nhỏ rằng truy vấn không thể tối ưu ở quy mô lớn.

`EXPLAIN ANALYZE` còn thực thi truy vấn để thu số liệu thực tế; chỉ sử dụng khi an toàn với loại câu lệnh và môi trường đang làm việc.

## 16. Những khác biệt theo hệ quản trị SQL

| Tính năng | PostgreSQL | Điểm cần nhớ khi chuyển hệ |
| --- | --- | --- |
| `JOIN ... ON a.x=b.x AND a.y=b.y` | Hỗ trợ | Ngữ nghĩa nền tảng phổ biến của SQL |
| Bất đẳng thức trong `ON` | Hỗ trợ `<`, `<=`, `>`, `>=` và biểu thức logic | Phổ biến; optimizer và chỉ mục có thể khác |
| `USING (col1,col2)` | Hỗ trợ, gộp cột cùng tên ở đầu ra | SQL Server không dùng cú pháp `JOIN ... USING` thông dụng; cần `ON` |
| `IS NOT DISTINCT FROM` | Hỗ trợ so sánh an toàn với `NULL` | MySQL có toán tử `<=>`; mức hỗ trợ `IS [NOT] DISTINCT FROM` phụ thuộc hệ/phiên bản |
| Kiểu khoảng và `&&` | Có `daterange`, `tsrange`, `tstzrange` | Không phải cú pháp SQL di chuyển trực tiếp |
| `JOIN LATERAL` | Hỗ trợ truy vấn con tương quan trong `FROM` | SQL Server dùng `CROSS APPLY`/`OUTER APPLY`; hệ khác có cú pháp và hạn chế khác |
| `LIMIT 1` trong truy vấn con | Hỗ trợ | SQL Server thường dùng `TOP (1)`, một số hệ dùng `FETCH FIRST 1 ROW ONLY` |
| Index đa cột | Hỗ trợ | Kiểu index, thứ tự cột, thống kê và cách tối ưu phụ thuộc DBMS |

Đặc biệt với kiểu ngày và thời gian:

- `DATE` phù hợp khi nghiệp vụ có độ phân giải là **ngày**.
- `TIMESTAMP` và `TIMESTAMPTZ` cần quy tắc rõ về thời điểm, múi giờ và giới hạn khoảng.
- Khi giá được cập nhật giữa ngày, chỉ lưu `DATE` có thể không đủ để phân biệt hai phiên bản trong cùng ngày.
- So sánh `<`/`<=` trong khoảng thời gian nên thống nhất về việc hai đầu mút có được tính hay không.

## 17. Lỗi thường gặp khi JOIN nhiều cột và điều kiện ngoài phép bằng

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Đơn T1 bị ghép dòng T2 | Chỉ nối `order_id`, bỏ `tenant_id` | Nối đủ cặp khóa theo phạm vi dữ liệu |
| Kết quả tăng vọt khi thêm `OR` | `OR` cho phép nhiều cặp không đúng quan hệ; thiếu ngoặc | Nhóm điều kiện và kiểm tra nghĩa từng nhánh `OR` |
| Một ngày khớp hai bảng giá | Dùng `BETWEEN` hoặc `<= valid_to` khi các khoảng chung biên | Chọn quy ước `[from,to)`, dùng `>=` và `<` |
| Dòng hàng xuất hiện nhiều lần sau nối bảng giá | Các khoảng giá chồng nhau hoặc điều kiện nối thiếu cột | Kiểm tra dữ liệu giá, khóa tenant/sku và khoảng hiệu lực |
| `LEFT JOIN` mất đơn không có dòng đủ điều kiện | Đưa predicate của bảng phải vào `WHERE` | Nếu cần giữ tất cả đơn, đặt điều kiện khớp trong `ON` |
| `COUNT(*)` trả 1 cho đơn không có dòng | `LEFT JOIN` tạo một hàng bảo toàn bên trái | Đếm khóa không `NULL` của bảng phải |
| `NULL` không khớp với `NULL` ở khóa tùy chọn | Toán tử `=` trả UNKNOWN khi có `NULL` | Quyết định có cần `IS NOT DISTINCT FROM` không |
| Hàng giá `valid_to IS NULL` không khớp | Điều kiện `date < NULL` là UNKNOWN | Viết tường minh quy tắc “không có ngày kết thúc” |
| Tổng thành tiền bị nhân đôi | Một dòng nguồn có nhiều bản ghi bên phải phù hợp | Xác định tính duy nhất và xử lý chồng khoảng trước tổng hợp |
| Muốn bản ghi mới nhất nhưng JOIN trả nhiều bản | Bất đẳng thức khớp toàn bộ lịch sử | Dùng `LATERAL`/window/tổng hợp có quy tắc chọn bản rõ |
| `NOT IN` loại ngoài dự kiến khi có `NULL` | Logic ba giá trị trong so sánh với `NULL` | Cân nhắc `NOT EXISTS` để diễn đạt “không tồn tại bản khớp” |
| Truy vấn non-equi quá chậm | Số cặp ứng viên lớn, thiếu điều kiện bằng hoặc index phù hợp | Thu hẹp ứng viên, kiểm tra cardinality và `EXPLAIN` |

## 18. Bài tập tự luyện

Dùng bảng tạm `join_orders_lab`, `join_lines_lab` và `join_prices_lab` ở mục 2 trên PostgreSQL. Với mỗi bài, hãy dự đoán **số hàng đầu ra** và kiểm tra xem có ghép sai tenant hoặc nhân bản dòng hàng hay không.

### Bài 1. Nối theo khóa ghép

Trả `tenant_id`, `order_id`, `customer_name`, `line_id` và `sku` của các dòng hàng khớp đơn cha bằng **cả `tenant_id` và `order_id`**. Sắp xếp theo `tenant_id`, `order_id`, `line_id`.

Câu hỏi: vì sao `T1–101` có hai dòng và `T2–101` chỉ có một dòng?

### Bài 2. Quan sát JOIN thiếu tenant

Thử nối chỉ theo `order_id`. Dùng hai cột alias `order_tenant` và `line_tenant` để phát hiện các hàng có tenant khác nhau. Viết điều kiện `WHERE` lọc ra các hàng khớp sai tenant để quan sát.

### Bài 3. Giữ đơn không có dòng hàng

Viết `LEFT JOIN` trả tất cả đơn và số dòng hàng khớp `COUNT(l.line_id)`. Đơn nào có số dòng bằng 0?

### Bài 4. So sánh điều kiện trong ON với WHERE

Lọc những dòng hàng có `quantity >= 2`. Viết hai câu `LEFT JOIN`:

1. Đặt `l.quantity >= 2` trong `ON`.
2. Đặt `l.quantity >= 2` trong `WHERE`.

Giải thích tại sao số hàng kết quả khác nhau.

### Bài 5. Bảng giá tại ngày đặt

Nối đơn với dòng hàng theo cặp khóa, rồi nối bảng giá theo tenant, sku và khoảng `[valid_from, valid_to)`. Trả `tenant_id`, `order_id`, `sku`, `quantity`, `unit_price`, `line_amount`.

Giá của dòng `T1–102 / P01` phải là bao nhiêu? Tại sao không lấy giá cũ?

### Bài 6. Tính tiền theo từng đơn

Từ kết quả nối bảng giá, tính tổng `SUM(quantity * unit_price)` cho mỗi đơn có dòng hàng. Chú ý không gộp đơn T1–101 với T2–101.

### Bài 7. Tìm dòng hàng không có đơn cha

Dùng `NOT EXISTS` với **hai điều kiện khóa** để liệt kê `line_id` của các dòng hàng không thuộc đơn nào. Có bao nhiêu dòng như vậy?

### Bài 8. Phát hiện khoảng giá chồng nhau

Tự nối `join_prices_lab` để tìm hai hàng cùng tenant, cùng sku và có khoảng `[valid_from, valid_to)` giao nhau. Không so một bản giá với chính nó; mỗi cặp chỉ trả một lần. Truy vấn có kết quả nào với dữ liệu mẫu không?

### Bài 9. Phân loại theo khoảng điểm

Dùng ba dải `[0,50)`, `[50,100)`, `[100,1000000)` và điểm 49, 50, 100. Hãy dùng non-equi join để xác định dải cho từng điểm. Giải thích vì sao dùng `BETWEEN` với các biên đó có thể gây trùng.

### Bài 10. Tìm ngưỡng cao nhất

Với danh sách ngưỡng `20, 50, 80` và học sinh có điểm `30, 60, 90`, hãy trả **một ngưỡng cao nhất** cho mỗi học sinh thay vì tất cả ngưỡng đã đạt. Bạn có thể dùng `MAX` trên các hàng khớp.

### Bài 11. NULL trong cột khóa tùy chọn

Cho hai tập mã `[NULL, 'X']` và `[NULL, 'X']`. Hãy so sánh kết quả khi nối bằng `a.code = b.code` với nối bằng `a.code IS NOT DISTINCT FROM b.code`. Trong tình huống nào không nên coi hai mã `NULL` là khớp?

### Bài 12. As-of join

Một bảng cấu hình có ngày hiệu lực `2026-01-01`, `2026-04-15` và `2026-05-01`. Với các sự kiện ngày `2026-04-10`, `2026-04-15` và `2026-05-03`, hãy lấy **phiên bản mới nhất có ngày hiệu lực không sau ngày sự kiện**. Dùng `LEFT JOIN LATERAL` và `ORDER BY ... DESC LIMIT 1` của PostgreSQL.

## 19. Gợi ý lời giải

### Bài 1

```sql
SELECT o.tenant_id, o.order_id, o.customer_name,
       l.line_id, l.sku
FROM join_orders_lab AS o
JOIN join_lines_lab AS l
  ON o.tenant_id = l.tenant_id
 AND o.order_id  = l.order_id
ORDER BY o.tenant_id, o.order_id, l.line_id;
```

Có **6** dòng khớp. Đơn `T1–101` có hai dòng hàng 1, 2; `T2–101` chỉ có dòng 4.

### Bài 2

```sql
SELECT o.tenant_id AS order_tenant,
       l.tenant_id AS line_tenant,
       o.order_id,
       l.line_id
FROM join_orders_lab AS o
JOIN join_lines_lab AS l
  ON o.order_id = l.order_id
WHERE o.tenant_id <> l.tenant_id
ORDER BY o.order_id, o.tenant_id, l.line_id;
```

Truy vấn phát hiện ba trường hợp ghép sai tenant: T1–101 với line 4, và T2–101 với line 1 và line 2.

### Bài 3

```sql
SELECT o.tenant_id, o.order_id,
       COUNT(l.line_id) AS line_count
FROM join_orders_lab AS o
LEFT JOIN join_lines_lab AS l
  ON o.tenant_id = l.tenant_id
 AND o.order_id = l.order_id
GROUP BY o.tenant_id, o.order_id
ORDER BY o.tenant_id, o.order_id;
```

Đơn **T3–105** có `line_count = 0`. Không dùng `COUNT(*)` để đếm dòng bên phải trong trường hợp này.

### Bài 4

Đặt điều kiện trong `ON`:

```sql
SELECT o.tenant_id, o.order_id, l.line_id
FROM join_orders_lab AS o
LEFT JOIN join_lines_lab AS l
  ON o.tenant_id = l.tenant_id
 AND o.order_id = l.order_id
 AND l.quantity >= 2;
```

Đặt điều kiện trong `WHERE`:

```sql
SELECT o.tenant_id, o.order_id, l.line_id
FROM join_orders_lab AS o
LEFT JOIN join_lines_lab AS l
  ON o.tenant_id = l.tenant_id
 AND o.order_id = l.order_id
WHERE l.quantity >= 2;
```

Cách thứ nhất vẫn giữ **6 đơn** (mỗi đơn một hàng trong bộ dữ liệu này sau áp điều kiện khớp); cách thứ hai chỉ còn **3 dòng** có `line_id = 1, 3, 5`.

### Bài 5

```sql
SELECT o.tenant_id, o.order_id,
       l.sku, l.quantity,
       p.unit_price,
       l.quantity * p.unit_price AS line_amount
FROM join_orders_lab AS o
JOIN join_lines_lab AS l
  ON o.tenant_id = l.tenant_id
 AND o.order_id  = l.order_id
LEFT JOIN join_prices_lab AS p
  ON p.tenant_id = l.tenant_id
 AND p.sku = l.sku
 AND o.ordered_on >= p.valid_from
 AND (o.ordered_on < p.valid_to OR p.valid_to IS NULL)
ORDER BY o.tenant_id, o.order_id, l.line_id;
```

`T1–102 / P01` ngày `2026-04-15` có giá **12.00** vì phiên bản cũ kết thúc **độc quyền** vào ngày đó.

### Bài 6

```sql
SELECT o.tenant_id, o.order_id,
       SUM(l.quantity * p.unit_price) AS order_total
FROM join_orders_lab AS o
JOIN join_lines_lab AS l
  ON o.tenant_id = l.tenant_id
 AND o.order_id = l.order_id
LEFT JOIN join_prices_lab AS p
  ON p.tenant_id = l.tenant_id
 AND p.sku = l.sku
 AND o.ordered_on >= p.valid_from
 AND (o.ordered_on < p.valid_to OR p.valid_to IS NULL)
GROUP BY o.tenant_id, o.order_id
ORDER BY o.tenant_id, o.order_id;
```

Kết quả theo dữ liệu mẫu:

| tenant_id | order_id | order_total |
| --- | ---: | ---: |
| T1 | 101 | 50.00 |
| T1 | 102 | 36.00 |
| T1 | 104 | 30.00 |
| T2 | 101 | 20.00 |
| T2 | 103 | 70.00 |

Lưu ý: bài này tính tổng của **mọi đơn có dòng hàng**, kể cả `CANCELLED` và `PENDING` để thực hành phép nối. Nếu yêu cầu là doanh thu được công nhận, phải lọc trạng thái nghiệp vụ riêng. Đồng thời, `SUM` bỏ qua `NULL` nên khi có dòng thiếu giá, cần báo trạng thái thiếu dữ liệu thay vì mặc định tổng là đầy đủ.

### Bài 7

```sql
SELECT l.line_id, l.tenant_id, l.order_id
FROM join_lines_lab AS l
WHERE NOT EXISTS (
    SELECT 1
    FROM join_orders_lab AS o
    WHERE o.tenant_id = l.tenant_id
      AND o.order_id = l.order_id
)
ORDER BY l.line_id;
```

Kết quả là **line 6 và line 7**.

### Bài 8

```sql
SELECT a.price_id, b.price_id
FROM join_prices_lab AS a
JOIN join_prices_lab AS b
  ON a.tenant_id = b.tenant_id
 AND a.sku = b.sku
 AND a.price_id < b.price_id
 AND (a.valid_to IS NULL OR b.valid_from < a.valid_to)
 AND (b.valid_to IS NULL OR a.valid_from < b.valid_to)
ORDER BY a.price_id, b.price_id;
```

Không có cặp nào với dữ liệu ban đầu.

### Bài 9

```sql
WITH points(point_id, score) AS (
    VALUES (1, 49), (2, 50), (3, 100)
),
bands(band, low, high) AS (
    VALUES
        ('low', 0, 50),
        ('medium', 50, 100),
        ('high', 100, 1000000)
)
SELECT p.point_id, p.score, b.band
FROM points AS p
JOIN bands AS b
  ON p.score >= b.low
 AND p.score < b.high
ORDER BY p.point_id;
```

Các điểm lần lượt thuộc `low`, `medium`, `high`. `BETWEEN low AND high` tính cả biên trên nên điểm 50 và 100 có thể khớp hai dải tiếp giáp.

### Bài 10

```sql
WITH students(student_id, score) AS (
    VALUES (1, 30), (2, 60), (3, 90)
),
thresholds(minimum_score) AS (
    VALUES (20), (50), (80)
)
SELECT s.student_id,
       MAX(t.minimum_score) AS highest_threshold
FROM students AS s
LEFT JOIN thresholds AS t
  ON s.score >= t.minimum_score
GROUP BY s.student_id
ORDER BY s.student_id;
```

Ngưỡng cao nhất tương ứng là `20, 50, 80`.

### Bài 11

`a.code = b.code` chỉ khớp hai giá trị `'X'` vì `NULL = NULL` là UNKNOWN. `a.code IS NOT DISTINCT FROM b.code` khớp thêm cặp `NULL/NULL`. Không nên ghép hai giá trị `NULL` nếu chúng đại diện mã **không biết**, bởi “cùng chưa biết” không chứng minh chúng thuộc cùng một thực thể.

### Bài 12

```sql
WITH events(event_id, occurred_on) AS (
    VALUES
        (1, DATE '2026-04-10'),
        (2, DATE '2026-04-15'),
        (3, DATE '2026-05-03')
),
config_versions(version_id, effective_from, rate) AS (
    VALUES
        (1, DATE '2026-01-01', 0.05::NUMERIC),
        (2, DATE '2026-04-15', 0.08::NUMERIC),
        (3, DATE '2026-05-01', 0.10::NUMERIC)
)
SELECT e.event_id, e.occurred_on,
       c.version_id, c.rate
FROM events AS e
LEFT JOIN LATERAL (
    SELECT v.version_id, v.rate
    FROM config_versions AS v
    WHERE v.effective_from <= e.occurred_on
    ORDER BY v.effective_from DESC, v.version_id DESC
    LIMIT 1
) AS c ON TRUE
ORDER BY e.event_id;
```

Các phiên bản được chọn là `1, 2, 3` tương ứng với ba sự kiện.

## 20. Cách suy nghĩ trước khi viết JOIN phức tạp

Thay vì bắt đầu bằng cú pháp, hãy làm rõ **hợp đồng dữ liệu và số lượng hàng mong đợi**:

1. **Mỗi hàng được định danh bằng gì?** Một cột `id` hay cặp `(tenant_id, id)`, thậm chí nhiều cột hơn?
2. **Quan hệ có cần tất cả khóa cùng khớp không?** Nếu có, diễn đạt bằng các điều kiện `AND` trong `ON`.
3. **Có thêm điều kiện giá trị hay thời gian không?** Ví dụ lớn hơn ngưỡng, nằm trong khoảng, chồng khoảng hoặc hiệu lực tại thời điểm.
4. **Khoảng có bao gồm mốc đầu/cuối không?** Chọn `BETWEEN` hay `>=`/`<` theo đúng quy tắc; tránh mơ hồ ở biên.
5. **`NULL` có ý nghĩa gì?** Chưa biết, không áp dụng hay kết thúc vô hạn? Chỉ xử lý `NULL` theo hợp đồng dữ liệu, không tự xem nó là giá trị khớp.
6. **Nếu không có bản ghi khớp, có giữ hàng nguồn không?** Chọn `INNER JOIN` hay `LEFT JOIN` trước khi đặt predicate ở `ON` hoặc `WHERE`.
7. **Một hàng nguồn được phép khớp tối đa bao nhiêu hàng đích?** Nếu kỳ vọng một bản giá mà truy vấn trả hai bản, phải tìm nguyên nhân trước khi tổng hợp.
8. **Có cần chọn một bản phù hợp nhất không?** Với quan hệ nhiều phiên bản, phải quy định ưu tiên và tiêu chí phá hòa.
9. **Có cần kiểm tra bản ghi không có quan hệ?** `NOT EXISTS` hoặc `LEFT JOIN ... IS NULL` trên khóa không `NULL` có thể thích hợp.
10. **Khi đã đúng về ngữ nghĩa, hiệu năng thế nào?** Dùng index và `EXPLAIN` phù hợp với DBMS, kích thước và phân bố dữ liệu.

Điểm quan trọng nhất: **`JOIN` theo nhiều cột bảo đảm đúng danh tính của quan hệ; non-equi join diễn đạt đúng điều kiện giá trị hoặc thời gian; còn loại `JOIN` và vị trí `ON`/`WHERE` quyết định hàng nào được giữ.** Chỉ khi cả ba phần đúng, kết quả nối bảng mới đáng tin cậy để tiếp tục lọc, tổng hợp và xây dựng báo cáo.
