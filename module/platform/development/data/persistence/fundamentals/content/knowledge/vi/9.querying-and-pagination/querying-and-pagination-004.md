# Kết hợp dữ liệu và tổng hợp ở mức khái niệm

## 1. Một câu hỏi nghiệp vụ có thể cần nhiều bảng

Ứng dụng Java quản lý đơn hàng thường lưu **khách hàng**, **đơn hàng** và **dòng hàng** trong các bảng khác nhau. Cách tách bảng này giúp biểu diễn quan hệ và tránh lặp thông tin: tên khách hàng không cần sao chép vào mọi dòng hàng, còn một đơn có thể chứa nhiều sản phẩm.

Khi hiển thị trang “Khách hàng và tổng doanh thu đơn đã thanh toán”, ứng dụng phải trả lời đồng thời ba câu hỏi:

1. **Khách hàng nào** thuộc tổ chức đang đăng nhập?
2. **Đơn hàng nào** thuộc mỗi khách hàng và đáp ứng điều kiện đã thanh toán?
3. **Có bao nhiêu đơn và tổng số tiền là bao nhiêu** cho từng khách hàng?

Đó là bài toán **kết hợp dữ liệu (JOIN)** và **tổng hợp dữ liệu (aggregation)**. Trong SQL, JOIN xây dựng tập hàng biểu diễn quan hệ giữa các nguồn; các hàm như `COUNT`, `SUM`, `AVG` kết hợp nhiều hàng thành thông tin ở mức nhóm.

Nếu làm thiếu cẩn thận, ứng dụng có thể:

- Không hiển thị khách hàng chưa có đơn vì chọn sai loại JOIN.
- Đếm một đơn nhiều lần khi JOIN thêm các dòng hàng.
- Trả sai tổng tiền dù từng câu SQL riêng lẻ đều chạy thành công.
- Lọc dữ liệu tenant khác ở Java sau khi đã tải vào bộ nhớ.
- Phân trang trên **dòng kết quả JOIN** thay vì trên **khách hàng hoặc đơn hàng**.
- Gọi một truy vấn con cho từng hàng cha và gây N+1.

Bài học thuộc chương **Truy vấn và phân trang** trong module **DATA_PERSISTENCE_FUNDAMENTALS**. Mục tiêu là hiểu ý nghĩa của kết hợp/tổng hợp trước khi tối ưu, đồng thời thấy chúng liên quan thế nào tới thiết kế schema, ranh giới persistence trong Java, an toàn dữ liệu, nhất quán và hiệu năng.

> **Câu hỏi nền tảng trước mọi truy vấn:** “Một hàng trong kết quả cuối biểu diễn **một đối tượng gì** — một khách hàng, một đơn, một dòng hàng hay một nhóm thống kê?” Nếu không xác định được **mức hạt (granularity)**, truy vấn rất dễ đếm hoặc cộng sai.

## 2. Tư duy theo tập hợp thay vì lặp từng phần tử trong Java

Trong code hướng đối tượng, người mới thường suy nghĩ:

```text
Lấy danh sách khách hàng
  -> với từng khách: tìm các đơn đã thanh toán
      -> với từng đơn: tìm các dòng hàng
          -> cộng tiền, đếm số đơn
```

Cách viết này dễ hiểu ở quy mô nhỏ nhưng có thể tạo **N+1 truy vấn**: một SELECT khách hàng cộng thêm một SELECT cho từng khách, rồi cho từng đơn. Database quan hệ lại mạnh ở các phép xử lý **tập hợp**:

```text
Nguồn A (khách hàng) --JOIN theo khóa--> Nguồn B (đơn hàng)
                                        |
                                  WHERE / ON
                                        |
                                   GROUP BY
                                        |
                                  COUNT / SUM
                                        |
                               ORDER BY / LIMIT
                                        |
                                   DTO Java
```

SQL biểu đạt **điều kiện và kết quả mong muốn**, còn bộ tối ưu truy vấn quyết định nhiều chi tiết thực thi như dùng chỉ mục, hash join hay nested loop. Ứng dụng Java vẫn quan trọng: xác thực tenant, định nghĩa use case, giao dịch, ánh xạ DTO, xử lý lỗi và quyết định dữ liệu tổng hợp có đủ mới hay không.

**Không phải cứ một SQL là nhanh nhất.** Một JOIN tạo hàng triệu hàng hoặc một phép tổng hợp quét toàn bảng cũng có thể đắt. Nhưng nên bắt đầu bằng **mô hình kết quả đúng và truy vấn theo tập hợp**, rồi đo và điều chỉnh thay vì đem toàn bộ dữ liệu về JVM.

## 3. Bộ dữ liệu minh họa có thể thực hành trên PostgreSQL

Ta dùng ba bảng thuộc cùng một tenant hoặc nhiều tenant:

- `demo_customers`: mỗi hàng là một khách hàng.
- `demo_orders`: mỗi hàng là một đơn, thuộc một khách hàng.
- `demo_order_lines`: mỗi hàng là một dòng sản phẩm thuộc một đơn.

Mỗi bảng có `tenant_id`. Khóa ghép giúp diễn đạt quan hệ trong phạm vi tenant, tránh một dòng hàng của tenant này trỏ tới đơn của tenant khác.

```sql
-- Chỉ chạy trong database học tập/có thể hủy.
CREATE TABLE demo_customers (
    tenant_id BIGINT NOT NULL,
    id BIGINT NOT NULL,
    display_name TEXT NOT NULL,
    PRIMARY KEY (tenant_id, id)
);

CREATE TABLE demo_orders (
    tenant_id BIGINT NOT NULL,
    id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    total NUMERIC(18, 2) NOT NULL CHECK (total >= 0),
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, id),
    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES demo_customers(tenant_id, id)
);

CREATE TABLE demo_order_lines (
    tenant_id BIGINT NOT NULL,
    id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(18, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (tenant_id, id),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES demo_orders(tenant_id, id)
);
```

### Tạo fixture có kết quả dễ tự tính

```sql
INSERT INTO demo_customers(tenant_id, id, display_name)
VALUES
    (1, 101, 'An'),
    (1, 102, 'Binh'),
    (1, 103, 'Chi'),
    (2, 201, 'Dung');

INSERT INTO demo_orders(
    tenant_id, id, customer_id, status, total, created_at
)
VALUES
    (1, 1001, 101, 'PAID', 120.00, '2026-01-10T09:00:00Z'),
    (1, 1002, 101, 'NEW',   50.00, '2026-01-11T09:00:00Z'),
    (1, 1003, 102, 'PAID',  90.00, '2026-01-12T09:00:00Z'),
    (2, 2001, 201, 'PAID',  99.00, '2026-01-13T09:00:00Z');

INSERT INTO demo_order_lines(
    tenant_id, id, order_id, sku, quantity, unit_price
)
VALUES
    (1, 1101, 1001, 'BOOK',    2, 50.00),
    (1, 1102, 1001, 'PEN',     1, 20.00),
    (1, 1201, 1002, 'BAG',     1, 50.00),
    (1, 1301, 1003, 'MUG',     3, 30.00),
    (2, 2101, 2001, 'BOOK',    1, 99.00);
```

Đây là các số tiền **giả định để học truy vấn**. Chưa xét thuế, mã giảm giá, vận chuyển, hoàn tiền hay tỷ giá. Trong nghiệp vụ thật, phải xác định `total` có nghĩa gì trước khi dùng nó trong báo cáo.

Để theo dõi kết quả, ghi nhớ tập dữ liệu của **tenant 1**:

| Khách | Đơn | Trạng thái | Tổng đơn | Số dòng hàng |
| --- | --- | --- | ---: | ---: |
| An (101) | 1001 | PAID | 120 | 2 |
| An (101) | 1002 | NEW | 50 | 1 |
| Binh (102) | 1003 | PAID | 90 | 1 |
| Chi (103) | *Chưa có* | — | — | 0 |

Khách `Dung` và đơn `2001` thuộc **tenant 2**, nên không xuất hiện trong báo cáo của tenant 1.

## 4. Hiểu “mức hạt” của từng kết quả

Trước khi JOIN hay GROUP BY, xác định một hàng có nghĩa gì:

| Tập dữ liệu | Một hàng đại diện | Ví dụ khóa xác định |
| --- | --- | --- |
| `demo_customers` | Một khách hàng trong tenant | `(tenant_id, id)` |
| `demo_orders` | Một đơn hàng trong tenant | `(tenant_id, id)` |
| `demo_order_lines` | Một dòng sản phẩm trong tenant | `(tenant_id, id)` |
| Khách JOIN đơn | Một cặp khách–đơn phù hợp | Có thể nhiều hàng cho cùng khách |
| Đơn JOIN dòng hàng | Một cặp đơn–dòng hàng phù hợp | Có thể nhiều hàng cho cùng đơn |
| Báo cáo GROUP BY khách | Một nhóm khách | `(tenant_id, customer_id)` |

Giữa khách và đơn là **một-nhiều**: một khách có thể có nhiều đơn. Giữa đơn và dòng hàng cũng là **một-nhiều**. Khi JOIN, database thường tạo một hàng cho **mỗi cặp khớp điều kiện** chứ không tự giới hạn “một khách một hàng”.

Đây không nhất thiết là trùng dữ liệu lỗi. Với An, hai hàng kết quả JOIN khách–đơn là đúng vì khách thực sự có hai đơn. Chỉ khi một báo cáo **yêu cầu mỗi khách đúng một hàng** mà ta quên tổng hợp/khử fan-out thì mới có vấn đề.

## 5. INNER JOIN: chỉ lấy các cặp có quan hệ khớp

`INNER JOIN` lấy những cặp hàng từ hai nguồn thỏa điều kiện `ON`:

```sql
SELECT c.id AS customer_id,
       c.display_name,
       o.id AS order_id,
       o.status,
       o.total
FROM demo_customers AS c
INNER JOIN demo_orders AS o
    ON o.tenant_id = c.tenant_id
   AND o.customer_id = c.id
WHERE c.tenant_id = 1
ORDER BY c.id, o.id;
```

Kết quả dự kiến:

| customer_id | display_name | order_id | status | total |
| ---: | --- | ---: | --- | ---: |
| 101 | An | 1001 | PAID | 120 |
| 101 | An | 1002 | NEW | 50 |
| 102 | Binh | 1003 | PAID | 90 |

**Chi không xuất hiện** vì chưa có đơn nào khớp. `INNER JOIN` có thể viết gọn `JOIN` trong SQL; ý nghĩa ở đây giống nhau.

### Điều kiện `ON` phải chứa quan hệ đúng

`o.customer_id = c.id` chưa đủ nếu ID khách chỉ duy nhất **trong một tenant**. Điều kiện đầy đủ cần cả `o.tenant_id = c.tenant_id`. Nếu bỏ điều kiện tenant và hai tổ chức đều có khách `id = 101`, JOIN có thể ghép nhầm dữ liệu và gây lộ thông tin.

Không dùng `ON 1=1` hoặc bỏ điều kiện JOIN rồi hy vọng `WHERE` ở Java sửa lại: đó là nguy cơ **tích Descartes** — số hàng trung gian có thể gần tích số hàng của hai nguồn.

### JOIN không có nghĩa là “gộp object”

SQL trả các hàng. ORM/JDBC có thể ánh xạ các hàng đó thành object phẳng, hoặc gom thành cấu trúc khách có danh sách đơn. Đây là quyết định của tầng mapping, **không phải điều SQL tự hiểu**. Cần xác định API muốn nhiều dòng hay object cha–con.

## 6. LEFT JOIN: giữ cả khách chưa có đơn

Nếu màn hình phải hiển thị **mọi khách hàng** kèm số đơn, `INNER JOIN` sẽ làm mất Chi. Dùng `LEFT JOIN`:

```sql
SELECT c.id AS customer_id,
       c.display_name,
       o.id AS order_id,
       o.status
FROM demo_customers AS c
LEFT JOIN demo_orders AS o
    ON o.tenant_id = c.tenant_id
   AND o.customer_id = c.id
WHERE c.tenant_id = 1
ORDER BY c.id, o.id;
```

Kết quả:

| customer_id | display_name | order_id | status |
| ---: | --- | ---: | --- |
| 101 | An | 1001 | PAID |
| 101 | An | 1002 | NEW |
| 102 | Binh | 1003 | PAID |
| 103 | Chi | NULL | NULL |

Với Chi, các cột từ nguồn bên phải (`o`) là `NULL` do **không có hàng khớp**. Điều này khác với “có đơn nhưng status null”; trong schema mẫu, `status` không null nên dễ phân biệt hơn.

**LEFT JOIN có nghĩa:** giữ từng hàng của nguồn trái **ít nhất một lần**, gắn hàng bên phải nếu khớp; nếu không có hàng bên phải, gắn `NULL` cho những cột đó.

### JOIN và NULL có phải khái niệm như nhau?

Không. `NULL` có thể biểu thị giá trị chưa biết/không có theo mô hình dữ liệu. Trong `LEFT JOIN`, `NULL` ở cột phía phải còn biểu thị **không tìm thấy quan hệ phù hợp**. Phải đặt câu hỏi “có hàng bên phải hay không” dựa trên **khóa không null** của bên phải, chẳng hạn `o.id`, thay vì mặc định mọi giá trị `NULL` đều có cùng nghĩa.

## 7. Bẫy kinh điển: bộ lọc trong WHERE làm mất hàng LEFT JOIN

Giả sử muốn **mọi khách** kèm các **đơn đã thanh toán**.

Cách viết dễ sai:

```sql
SELECT c.id, c.display_name, o.id AS order_id
FROM demo_customers c
LEFT JOIN demo_orders o
    ON o.tenant_id = c.tenant_id
   AND o.customer_id = c.id
WHERE c.tenant_id = 1
  AND o.status = 'PAID';
```

Điều kiện `o.status = 'PAID'` ở `WHERE` làm hàng “Chi + NULL” bị loại vì phép so với `NULL` không cho kết quả TRUE. Với bộ dữ liệu mẫu, chỉ còn An và Binh. Nghĩa nghiệp vụ đã vô tình đổi thành “khách có đơn PAID”, không còn “mọi khách”.

Đặt điều kiện liên quan **hàng bên phải muốn khớp** vào `ON`:

```sql
SELECT c.id, c.display_name, o.id AS paid_order_id
FROM demo_customers c
LEFT JOIN demo_orders o
    ON o.tenant_id = c.tenant_id
   AND o.customer_id = c.id
   AND o.status = 'PAID'
WHERE c.tenant_id = 1
ORDER BY c.id;
```

Khi đó:

| Khách | paid_order_id |
| --- | ---: |
| An | 1001 |
| Binh | 1003 |
| Chi | NULL |

Không phải **mọi điều kiện** của `LEFT JOIN` đều phải nằm trong `ON`: điều kiện lọc **nguồn trái** như `c.tenant_id = 1` vẫn ở `WHERE` rất phù hợp. Sự khác biệt nằm ở việc điều kiện **trên nguồn phải** có được phép loại các hàng trái không có quan hệ hay không.

## 8. Cần chọn kiểu JOIN nào?

| Nhu cầu | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Chỉ lấy đơn có khách hợp lệ | `INNER JOIN` | Chỉ quan tâm những cặp khớp |
| Liệt kê mọi khách kể cả chưa mua | `LEFT JOIN` | Giữ các hàng nguồn trái |
| Liệt kê mọi đơn kể cả không có dòng hàng | `LEFT JOIN` từ đơn sang dòng | Cho phép tổng dòng bằng 0 |
| Tìm khách **đã có ít nhất một** đơn PAID | `EXISTS` hoặc JOIN phù hợp | Chỉ cần biết có quan hệ, không cần nhân hàng |
| Tìm khách **chưa có** đơn PAID | `NOT EXISTS` hoặc anti-join phù hợp | Diễn đạt điều kiện vắng mặt |
| Kết hợp các giá trị không có quan hệ khóa | `CROSS JOIN` nếu có chủ đích | Tạo mọi cặp, dễ tăng số hàng rất nhanh |

Ví dụ `EXISTS` để tìm khách đã mua:

```sql
SELECT c.id, c.display_name
FROM demo_customers c
WHERE c.tenant_id = 1
  AND EXISTS (
      SELECT 1
      FROM demo_orders o
      WHERE o.tenant_id = c.tenant_id
        AND o.customer_id = c.id
        AND o.status = 'PAID'
  )
ORDER BY c.id;
```

`EXISTS` không cần trả một hàng cho mỗi đơn. Ngược lại, dùng `JOIN` rồi `DISTINCT c.id` có thể cũng cho danh sách khách duy nhất, nhưng ý nghĩa là **tạo cặp trước, sau đó khử trùng**. Bộ tối ưu có thể chọn kế hoạch tốt trong cả hai trường hợp; nên ưu tiên cách biểu đạt đúng câu hỏi nghiệp vụ và kiểm tra query plan.

Ví dụ khách chưa có đơn đã thanh toán:

```sql
SELECT c.id, c.display_name
FROM demo_customers c
WHERE c.tenant_id = 1
  AND NOT EXISTS (
      SELECT 1
      FROM demo_orders o
      WHERE o.tenant_id = c.tenant_id
        AND o.customer_id = c.id
        AND o.status = 'PAID'
  )
ORDER BY c.id;
-- Kỳ vọng: Chi; nếu khách chỉ có đơn NEW thì cũng thuộc kết quả.
```

Tránh tự đổi `NOT EXISTS` thành `NOT IN` khi cột con có thể `NULL` mà chưa hiểu SQL three-valued logic. Trong nhiều bài toán quan hệ “không tồn tại bản ghi phù hợp”, `NOT EXISTS` dễ diễn đạt đúng hơn.

## 9. Tổng hợp: từ nhiều hàng thành một thông tin

Các hàm aggregate phổ biến:

| Hàm | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `COUNT(*)` | Số hàng trong nhóm | Đếm cả hàng có giá trị NULL ở cột khác |
| `COUNT(column)` | Số hàng mà `column` không null | Khác `COUNT(*)` khi cột nullable hoặc LEFT JOIN |
| `COUNT(DISTINCT column)` | Số giá trị không null khác nhau của cột | Có thể tốn thêm thao tác dedup |
| `SUM(column)` | Tổng các giá trị không null | Không có hàng phù hợp có thể trả NULL |
| `AVG(column)` | Trung bình các giá trị không null | Không được đồng nhất với trung bình của trung bình nếu trọng số khác |
| `MIN(column)` / `MAX(column)` | Giá trị nhỏ/lớn nhất không null | Cần hiểu kiểu dữ liệu và collation |

Trên bảng đơn **chưa JOIN thêm dòng hàng**:

```sql
SELECT status,
       COUNT(*) AS order_count,
       SUM(total) AS total_amount,
       AVG(total) AS average_amount
FROM demo_orders
WHERE tenant_id = 1
GROUP BY status
ORDER BY status;
```

Kết quả dự kiến:

| status | order_count | total_amount | average_amount |
| --- | ---: | ---: | ---: |
| NEW | 1 | 50 | 50 |
| PAID | 2 | 210 | 105 |

**GROUP BY status** đổi mức hạt từ **một hàng = một đơn** sang **một hàng = một trạng thái trong tập đã lọc**. Tên `total_amount` là tổng trên các đơn ở nhóm tương ứng; nếu chỉ muốn doanh thu đã thanh toán, phải giới hạn trạng thái và xác định thêm quy tắc hoàn tiền.

### SQL tổng hợp toàn tập mà không GROUP BY

```sql
SELECT COUNT(*) AS paid_orders,
       COALESCE(SUM(total), 0) AS paid_amount
FROM demo_orders
WHERE tenant_id = 1 AND status = 'PAID';
-- Kỳ vọng: 2 đơn; tổng 210.
```

Khi không có `GROUP BY` và chỉ dùng aggregate, truy vấn tổng hợp toàn bộ tập được chọn thành **một nhóm logic**; với các aggregate thông thường sẽ trả một hàng, dù không có đơn nào khớp.

## 10. COUNT(*) và COUNT(o.id) khác nhau sau LEFT JOIN

Xét truy vấn từ khách sang đơn:

```sql
SELECT c.id AS customer_id,
       c.display_name,
       COUNT(*) AS joined_rows,
       COUNT(o.id) AS actual_orders
FROM demo_customers c
LEFT JOIN demo_orders o
    ON o.tenant_id = c.tenant_id
   AND o.customer_id = c.id
WHERE c.tenant_id = 1
GROUP BY c.tenant_id, c.id, c.display_name
ORDER BY c.id;
```

Kết quả:

| Khách | joined_rows | actual_orders |
| --- | ---: | ---: |
| An | 2 | 2 |
| Binh | 1 | 1 |
| Chi | 1 | 0 |

Vì sao Chi có `joined_rows = 1`? `LEFT JOIN` vẫn tạo **một hàng** cho Chi với `o.id = NULL`, nên `COUNT(*)` đếm 1. Còn `COUNT(o.id)` bỏ qua NULL và trả 0.

**Quy tắc thực hành:** Khi đếm **số hàng con tồn tại** sau `LEFT JOIN`, thường dùng `COUNT(child.primary_key)`. Đừng dùng `COUNT(*)` nếu yêu cầu là “khách này có bao nhiêu đơn”.

## 11. GROUP BY khách: đếm đơn và tính tổng tiền đúng

Mục tiêu: mỗi khách thuộc tenant 1 có **một hàng**, gồm số đơn và tổng số tiền đơn đã thanh toán:

```sql
SELECT c.id AS customer_id,
       c.display_name,
       COUNT(o.id) AS paid_order_count,
       COALESCE(SUM(o.total), 0) AS paid_total
FROM demo_customers c
LEFT JOIN demo_orders o
    ON o.tenant_id = c.tenant_id
   AND o.customer_id = c.id
   AND o.status = 'PAID'
WHERE c.tenant_id = 1
GROUP BY c.tenant_id, c.id, c.display_name
ORDER BY paid_total DESC, c.id ASC;
```

Kết quả:

| customer_id | display_name | paid_order_count | paid_total |
| ---: | --- | ---: | ---: |
| 101 | An | 1 | 120 |
| 102 | Binh | 1 | 90 |
| 103 | Chi | 0 | 0 |

Tư duy từng bước:

1. `FROM demo_customers c` lấy tập khách.
2. `LEFT JOIN ... o.status = 'PAID'` ghép **chỉ các đơn PAID**, nhưng giữ khách không có đơn PAID.
3. `WHERE c.tenant_id = 1` giới hạn tổ chức có quyền.
4. `GROUP BY ... c.id ...` gom mọi hàng đã ghép của cùng khách.
5. `COUNT(o.id)` đếm đúng số đơn đã thanh toán.
6. `SUM(o.total)` cộng tiền theo đơn; `COALESCE(..., 0)` chuyển kết quả null của khách không có đơn thành 0.
7. `ORDER BY paid_total DESC, c.id ASC` sắp xếp có khóa phụ để ổn định.

Với mô hình thực tế, tên `paid_total` chỉ chính xác nếu `total` thực sự là số tiền nghiệp vụ cần cộng, đơn đã thanh toán không bị hoàn tiền ngoài mô hình, và mọi đơn dùng cùng đơn vị tiền. Nếu mỗi đơn có currency khác nhau, **không cộng trực tiếp nhiều loại tiền** mà thiếu phép quy đổi/chính sách.

## 12. WHERE và HAVING: lọc hàng khác lọc nhóm

`WHERE` lọc **các hàng đầu vào trước khi tính nhóm**, còn `HAVING` lọc **các nhóm sau khi aggregate đã được tính**.

Ví dụ tìm khách có ít nhất hai đơn ở tenant 1, bất kể trạng thái:

```sql
SELECT c.id,
       c.display_name,
       COUNT(o.id) AS order_count
FROM demo_customers c
LEFT JOIN demo_orders o
    ON o.tenant_id = c.tenant_id
   AND o.customer_id = c.id
WHERE c.tenant_id = 1
GROUP BY c.tenant_id, c.id, c.display_name
HAVING COUNT(o.id) >= 2
ORDER BY c.id;
-- Kỳ vọng: chỉ An (2 đơn).
```

Nếu muốn khách có **ít nhất hai đơn PAID**, phải thêm `o.status = 'PAID'` vào `ON` trước tổng hợp; với fixture hiện tại không có khách nào đạt điều kiện.

Một sơ đồ tư duy:

```text
WHERE  -> câu hỏi về từng hàng: "Đơn này thuộc tenant 1 và PAID?"
GROUP  -> gom hàng theo khóa: "Các đơn này thuộc khách nào?"
HAVING -> câu hỏi về nhóm: "Khách này có >= 2 đơn?"
```

Không đặt `COUNT(o.id) >= 2` trong `WHERE` của cùng mức truy vấn vì đó là điều kiện aggregate của nhóm. Ngoại lệ là khi đã tổng hợp trong subquery/CTE, tầng SQL bên ngoài có thể dùng `WHERE` trên giá trị kết quả được sinh từ truy vấn con.

## 13. Một JOIN một-nhiều có thể làm cộng tiền sai

Đây là lỗi cần nhận biết khi kết hợp **JOIN và SUM**.

Giả sử cần tổng tiền đơn của An. Nếu JOIN từ khách → đơn → dòng hàng rồi cộng `o.total`:

```sql
-- SAI về ý nghĩa nghiệp vụ nếu muốn cộng mỗi đơn đúng một lần.
SELECT c.id AS customer_id,
       COUNT(o.id) AS naive_order_count,
       SUM(o.total) AS naive_orders_total
FROM demo_customers c
JOIN demo_orders o
    ON o.tenant_id = c.tenant_id
   AND o.customer_id = c.id
JOIN demo_order_lines l
    ON l.tenant_id = o.tenant_id
   AND l.order_id = o.id
WHERE c.tenant_id = 1 AND c.id = 101
GROUP BY c.id;
```

Vì An có:

- Đơn 1001 tổng **120**, chứa **2 dòng hàng** ⇒ JOIN tạo hai hàng đều mang `o.total = 120`.
- Đơn 1002 tổng **50**, chứa **1 dòng hàng** ⇒ JOIN tạo một hàng mang `o.total = 50`.

Kết quả sai: `naive_order_count = 3` và `naive_orders_total = 120 + 120 + 50 = 290`.

Trong khi đúng là **2 đơn**, tổng tiền đơn **170**.

Sơ đồ mức hạt:

```text
Trước JOIN dòng hàng:
  O1001(total=120)    O1002(total=50)

Sau JOIN dòng hàng:
  O1001 + L1101 -> total=120
  O1001 + L1102 -> total=120
  O1002 + L1201 -> total=50

SUM(o.total) sau JOIN = 290  <-- cộng lặp!
```

Đây là **row multiplication/fan-out**. SQL không tính sai; truy vấn đã yêu cầu cộng trên một tập kết quả có nhiều hàng cho một đơn.

### COUNT(DISTINCT) chỉ giải quyết một phần

`COUNT(DISTINCT o.id)` có thể trả đúng 2 **đơn khác nhau** trong trường hợp này, nhưng `SUM(DISTINCT o.total)` **không** phải công thức tổng tiền đúng nói chung. Nếu hai đơn hợp lệ cùng có tổng 50, `SUM(DISTINCT o.total)` chỉ cộng 50 một lần.

**Đừng sửa lỗi nhân hàng bằng `DISTINCT` trên số tiền.** Hãy tổng hợp tại mức hạt đúng hoặc tránh JOIN gây nhân hàng khi không cần dữ liệu con.

## 14. Cách sửa: tính mỗi chỉ số ở đúng mức hạt

### Cách A: không JOIN dòng hàng nếu chỉ cần tiền đơn

Muốn tổng tiền đã lưu trong `demo_orders` theo khách, truy vấn ở mục 11 là đủ. **Không JOIN thêm bảng con không liên quan tới phép tính**.

### Cách B: tổng hợp dòng hàng thành một hàng trên mỗi đơn trước

Khi cần cả tiền đơn và **tổng giá trị dòng hàng** để đối chiếu:

```sql
WITH line_summary AS (
    SELECT l.tenant_id,
           l.order_id,
           COUNT(*) AS line_count,
           SUM(l.quantity::numeric * l.unit_price) AS lines_subtotal
    FROM demo_order_lines l
    GROUP BY l.tenant_id, l.order_id
)
SELECT o.tenant_id,
       o.id AS order_id,
       o.status,
       o.total AS stored_order_total,
       COALESCE(s.line_count, 0) AS line_count,
       COALESCE(s.lines_subtotal, 0) AS lines_subtotal
FROM demo_orders o
LEFT JOIN line_summary s
    ON s.tenant_id = o.tenant_id
   AND s.order_id = o.id
WHERE o.tenant_id = 1
ORDER BY o.id;
```

`line_summary` có đúng **một hàng cho mỗi (tenant_id, order_id)**. JOIN nó vào `demo_orders` không làm một đơn bị nhân theo số dòng hàng nữa.

Kết quả minh họa:

| order_id | stored_order_total | line_count | lines_subtotal |
| ---: | ---: | ---: | ---: |
| 1001 | 120 | 2 | 120 |
| 1002 | 50 | 1 | 50 |
| 1003 | 90 | 1 | 90 |

### Cách C: tổng hợp ở hai cấp khi báo cáo cần nhiều mức

Giả sử báo cáo yêu cầu mỗi khách có số đơn, tổng tiền đơn và tổng số dòng:

```sql
WITH per_order AS (
    SELECT o.tenant_id,
           o.id AS order_id,
           o.customer_id,
           o.total,
           COUNT(l.id) AS line_count
    FROM demo_orders o
    LEFT JOIN demo_order_lines l
        ON l.tenant_id = o.tenant_id
       AND l.order_id = o.id
    WHERE o.tenant_id = 1
    GROUP BY o.tenant_id, o.id, o.customer_id, o.total
)
SELECT c.id AS customer_id,
       c.display_name,
       COUNT(p.order_id) AS order_count,
       COALESCE(SUM(p.total), 0) AS total_amount,
       COALESCE(SUM(p.line_count), 0) AS total_lines
FROM demo_customers c
LEFT JOIN per_order p
    ON p.tenant_id = c.tenant_id
   AND p.customer_id = c.id
WHERE c.tenant_id = 1
GROUP BY c.tenant_id, c.id, c.display_name
ORDER BY c.id;
```

Trong `per_order`, dữ liệu đã được **co lại thành một hàng cho mỗi đơn**. Tầng ngoài mới gom tiếp **một hàng cho mỗi khách**. Cách này giúp tránh cộng `total` lặp, đồng thời giữ khách Chi không có đơn.

**Lưu ý hiệu năng:** CTE trên là mô hình viết SQL dễ đọc; PostgreSQL có thể tối ưu/inlining khác nhau tùy phiên bản và nội dung. Nếu bảng lớn, cần xem `EXPLAIN` để quyết định có nên lọc tập đơn từ sớm hơn, thêm index hay phân trang trước.

## 15. Tổng hợp từ dòng hàng không tự bằng số tiền đã thanh toán

`SUM(l.quantity * l.unit_price)` trong dữ liệu mẫu bằng `o.total`. Nhưng đó chỉ là **điều kiện của fixture**:

```text
Giá trị dòng hàng (subtotal) = Σ(quantity × unit_price)
Tổng phải trả có thể =
    subtotal
  - discount
  + shipping
  + tax
  - refund / credit adjustments theo định nghĩa nghiệp vụ
```

Nếu hệ thống còn trạng thái “đã thanh toán một phần”, nhiều đơn vị tiền tệ hoặc hoàn trả, hai trường có thể không bao giờ nên bằng nhau. Không dùng một truy vấn JOIN để tự suy ra quy tắc kế toán.

Với tiền, trong SQL dùng `NUMERIC/DECIMAL` theo độ chính xác cần thiết; Java dùng `BigDecimal`. Chọn quy tắc làm tròn, loại tiền và thời điểm quy đổi tại **ranh giới nghiệp vụ**, không âm thầm đổi sang `double` trong DTO.

## 16. Thứ tự xử lý logic của SQL giải thích nhiều lỗi

Một câu truy vấn có thể được hình dung theo **thứ tự logic**, không phải thứ tự engine bắt buộc thực thi vật lý:

```text
FROM / JOIN
    -> ON (điều kiện ghép)
    -> WHERE (lọc các hàng)
    -> GROUP BY (tạo nhóm)
    -> HAVING (lọc nhóm)
    -> SELECT (chọn/tính biểu thức kết quả)
    -> DISTINCT (nếu yêu cầu)
    -> ORDER BY (sắp xếp kết quả)
    -> LIMIT / OFFSET (giới hạn phần kết quả)
```

Thứ tự này giải thích:

- `WHERE` không được trực tiếp lọc kết quả `COUNT` của cùng một mức aggregate, vì nhóm chưa hình thành tại bước đó.
- `HAVING` có thể kiểm tra `COUNT(*) >= 2`, vì nhóm đã được tính.
- `LEFT JOIN` có thể mất các hàng nguồn trái khi `WHERE` loại những hàng mà phía phải là `NULL`.
- `ORDER BY` cần diễn đạt rõ thứ tự trước `LIMIT`; nếu không, “20 khách đầu tiên” không có ý nghĩa ổn định.
- `LIMIT` sau JOIN có thể giới hạn **hàng đã nhân** chứ không phải số đối tượng cha.

Đây là mô hình **ngữ nghĩa logic**, không phải khẳng định PostgreSQL luôn đọc từng bảng/nhóm đúng thứ tự này trên CPU. Query planner có thể đẩy filter, đổi join order, dùng index và rewrite tương đương để tiết kiệm công việc trong khi vẫn giữ kết quả theo semantics SQL.

## 17. Phân trang là giới hạn mức hạt nào?

Tương tự JOIN, phân trang cần xác định một hàng tương ứng **đối tượng gì**.

### Trang khách hàng đã tổng hợp

Nếu mỗi hàng kết quả là **một khách** với số đơn PAID, có thể phân trang **sau khi tổng hợp**:

```sql
SELECT c.id AS customer_id,
       c.display_name,
       COUNT(o.id) AS paid_order_count
FROM demo_customers c
LEFT JOIN demo_orders o
    ON o.tenant_id = c.tenant_id
   AND o.customer_id = c.id
   AND o.status = 'PAID'
WHERE c.tenant_id = 1
GROUP BY c.tenant_id, c.id, c.display_name
ORDER BY paid_order_count DESC, c.id ASC
LIMIT 2 OFFSET 0;
```

Vì `GROUP BY` đã tạo **một hàng trên mỗi khách**, `LIMIT 2` giới hạn đúng hai khách. Dữ liệu mẫu có ba khách, nên trang kế tiếp (offset 2) gồm một khách.

Nhưng để tính tổng số đơn của mọi khách, database vẫn có thể phải đọc và tổng hợp nhiều hàng trước khi chọn hai nhóm đầu. Giới hạn số hàng **trả về** khác với giới hạn **công việc cần xử lý**.

### Trang đơn rồi JOIN dòng hàng: bẫy LIMIT

```sql
-- NGUY HIỂM nếu mục tiêu là đúng 2 đơn, mỗi đơn đủ mọi dòng hàng.
SELECT o.id, l.id AS line_id
FROM demo_orders o
LEFT JOIN demo_order_lines l
    ON l.tenant_id = o.tenant_id
   AND l.order_id = o.id
WHERE o.tenant_id = 1
ORDER BY o.created_at DESC, o.id DESC
LIMIT 2;
```

Nếu một đơn có nhiều dòng, `LIMIT 2` áp lên **hai hàng JOIN**, không chắc là hai đơn; còn có nguy cơ chỉ lấy một phần các dòng của một đơn. Đây là một lỗi cấu trúc, không được sửa bằng cách tăng `LIMIT` theo cảm tính.

## 18. Phân trang cha trước, lấy dữ liệu con sau

Giải pháp phổ biến cho trang **2 đơn với các dòng hàng đầy đủ** là chọn tập đơn trước rồi mới JOIN:

```sql
WITH page_orders AS (
    SELECT tenant_id, id, customer_id, status, total, created_at
    FROM demo_orders
    WHERE tenant_id = 1
    ORDER BY created_at DESC, id DESC
    LIMIT 2 OFFSET 0
)
SELECT p.id AS order_id,
       p.status,
       p.total,
       l.id AS line_id,
       l.sku,
       l.quantity,
       l.unit_price
FROM page_orders p
LEFT JOIN demo_order_lines l
    ON l.tenant_id = p.tenant_id
   AND l.order_id = p.id
ORDER BY p.created_at DESC, p.id DESC, l.id ASC;
```

`page_orders` đã chọn **hai đơn** theo thứ tự mới nhất. JOIN bên ngoài có thể trả hơn hai hàng do mỗi đơn có nhiều dòng, nhưng **phạm vi đơn** không bị cắt cụt ở mức dòng.

Ứng dụng Java có thể nhóm kết quả theo `order_id` thành DTO:

```text
OrderDto
  id: 1003
  status: PAID
  lines: [MUG]

OrderDto
  id: 1002
  status: NEW
  lines: [BAG]
```

Trong fixture này, hai đơn mới nhất là 1003 rồi 1002. Nếu trang chọn đơn 1001, JOIN sẽ trả **hai hàng** cho đơn đó; mapper cần gộp về một `OrderDto` với hai dòng.

### Hai truy vấn thay vì một JOIN cũng có thể hợp lý

1. Query trang ID của đơn từ `demo_orders`.
2. Query dòng hàng bằng `WHERE tenant_id = ? AND order_id IN (...)`.
3. Nhóm dòng hàng theo `order_id` ở Java, dựng DTO theo **thứ tự ID trang đầu**.

Số SQL thường là hai thay vì `1 + N`. Nếu các quan hệ con lớn hoặc cần nhiều collection độc lập, hai truy vấn có thể tránh **nhân hàng kiểu tích Descartes** do fetch join quá nhiều collection.

Không giả định `IN (ids)` giữ thứ tự ID đầu vào: muốn thứ tự trang, phải `ORDER BY` phù hợp hoặc sắp lại sau khi nhóm.

## 19. GROUP BY và điều kiện tổng hợp có tác động tới phân trang

Hai nhu cầu sau **không tương đương**:

1. **Trang khách hàng**, mỗi khách hiển thị tổng đơn đã thanh toán.
2. **Trang 20 đơn đã thanh toán**, rồi trong trang đó hiển thị thống kê khách.

Ở (1), aggregation diễn ra trên toàn bộ tập đơn khớp điều kiện, rồi giới hạn **khách hàng**. Ở (2), chỉ có tối đa 20 đơn được lấy trước, nên tổng theo khách sẽ là **tổng trong trang**, không phải tổng theo lịch sử đầy đủ.

Ví dụ dễ sai:

```sql
-- Chỉ tổng hợp trên 2 đơn mới nhất, KHÔNG phải tất cả đơn.
WITH recent_orders AS (
    SELECT tenant_id, customer_id, total
    FROM demo_orders
    WHERE tenant_id = 1
    ORDER BY created_at DESC, id DESC
    LIMIT 2
)
SELECT customer_id, SUM(total) AS total_in_recent_page
FROM recent_orders
GROUP BY customer_id;
```

Tên `total_in_recent_page` cố ý nói rõ mức hạt và phạm vi. Nếu UI ghi nhãn “Tổng chi tiêu toàn thời gian”, truy vấn này sẽ gây hiểu lầm.

**Câu hỏi kiểm tra:** Tổng đang tính trên **mọi đơn đủ điều kiện** hay **các đơn được phân trang trước**? Thứ tự lọc, tổng hợp và phân trang là một phần của **định nghĩa chỉ số**, không chỉ là tối ưu.

## 20. Đếm nhóm và đếm hàng là hai con số khác nhau

Giả sử API trả trang tổng tiền theo khách. Có thể cần:

- `totalOrders`: số đơn đã thanh toán.
- `totalCustomers`: số khách có hoặc không có đơn tùy yêu cầu.
- `totalGroups`: số nhóm được tạo bởi `GROUP BY`.

Chúng khác nhau. Với tenant 1:

- Có **3 khách**.
- Có **3 đơn** ở mọi trạng thái, **2 đơn PAID**.
- Có **2 khách có ít nhất một đơn PAID**.
- Có **3 nhóm khách** nếu dùng `LEFT JOIN` giữ cả Chi.

Nếu trang báo cáo có một hàng cho mỗi khách, tổng số trang nên dựa vào **số nhóm khách phù hợp điều kiện**, không phải số đơn hay số hàng đã JOIN.

Ví dụ đếm **khách có đơn PAID**:

```sql
SELECT COUNT(*) AS paid_customer_count
FROM demo_customers c
WHERE c.tenant_id = 1
  AND EXISTS (
      SELECT 1
      FROM demo_orders o
      WHERE o.tenant_id = c.tenant_id
        AND o.customer_id = c.id
        AND o.status = 'PAID'
  );
-- Kỳ vọng: 2.
```

Nếu trang hiển thị cả khách chưa mua, tổng số nhóm là số khách thuộc tenant (3), không phải 2. Điều kiện `COUNT` của API phải tương ứng **chính xác với tập đối tượng được phân trang**.

## 21. Ranh giới tenant và SQL injection không được lùi về Java

Trong hệ đa tenant, truy vấn chỉ có nghĩa nếu bảo toàn phạm vi đọc:

```sql
SELECT c.id, c.display_name, COUNT(o.id) AS order_count
FROM demo_customers c
LEFT JOIN demo_orders o
    ON o.tenant_id = c.tenant_id
   AND o.customer_id = c.id
WHERE c.tenant_id = :authenticated_tenant_id
GROUP BY c.tenant_id, c.id, c.display_name
ORDER BY c.id;
```

`:authenticated_tenant_id` là named parameter minh họa; trong JDBC thuần dùng `?`. **Giá trị tenant** phải được lấy từ phiên/danh tính đã xác thực và kiểm tra quyền, không tin `tenantId` tự khai trong URL hoặc body.

Những nguyên tắc:

1. Dùng bind parameter cho tenant, trạng thái, giới hạn trang và các giá trị lọc.
2. Trong JOIN giữa bảng có khóa ghép theo tenant, ghép **cả tenant lẫn khóa nghiệp vụ/khóa ngoại**.
3. Không mang hàng từ tenant khác về JVM rồi mới lọc bằng `Stream.filter()`.
4. Khi truy vấn hai bước (cha rồi con), áp dụng scope tenant cả ở câu thứ hai.
5. Không ghép tên cột `ORDER BY` do client gửi tùy ý; dùng allowlist của API.
6. Không coi `COUNT` hay `SUM` là “ít rủi ro” vì chỉ trả con số: một phép đếm thiếu tenant có thể tiết lộ mức hoạt động của tổ chức khác.
7. Nếu hệ dùng Row-Level Security, cần kiểm thử cấu hình role/session và policy thực tế; RLS bổ sung chứ không xóa nhu cầu thiết kế quyền tại ứng dụng.

## 22. Java/JDBC: trả báo cáo dạng DTO thay vì tải toàn bộ entity

Một lớp repository có thể trả đúng tập thống kê mà API cần, không phải trả mọi đơn rồi dùng vòng lặp cộng ở Java.

Ví dụ Java 17 với `DataSource` và `PreparedStatement`:

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

public final class CustomerReportRepository {
    private final DataSource dataSource;

    public record CustomerSpendRow(
            long customerId,
            String displayName,
            long paidOrderCount,
            BigDecimal paidTotal) {}

    public CustomerReportRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public List<CustomerSpendRow> findPaidSummary(
            long authenticatedTenantId, int maxCustomers)
            throws SQLException {
        if (authenticatedTenantId <= 0
                || maxCustomers < 1 || maxCustomers > 100) {
            throw new IllegalArgumentException("Invalid report scope");
        }

        String sql = """
            SELECT c.id AS customer_id,
                   c.display_name,
                   COUNT(o.id) AS paid_order_count,
                   COALESCE(SUM(o.total), 0) AS paid_total
            FROM demo_customers c
            LEFT JOIN demo_orders o
                ON o.tenant_id = c.tenant_id
               AND o.customer_id = c.id
               AND o.status = 'PAID'
            WHERE c.tenant_id = ?
            GROUP BY c.tenant_id, c.id, c.display_name
            ORDER BY paid_total DESC, c.id ASC
            LIMIT ?
            """;

        List<CustomerSpendRow> rows = new ArrayList<>();
        try (Connection conn = dataSource.getConnection();
             PreparedStatement stmt = conn.prepareStatement(sql)) {
            stmt.setLong(1, authenticatedTenantId);
            stmt.setInt(2, maxCustomers);

            try (ResultSet rs = stmt.executeQuery()) {
                while (rs.next()) {
                    rows.add(new CustomerSpendRow(
                        rs.getLong("customer_id"),
                        rs.getString("display_name"),
                        rs.getLong("paid_order_count"),
                        rs.getBigDecimal("paid_total")));
                }
            }
        }
        return List.copyOf(rows);
    }
}
```

Điều đoạn mã minh họa:

- `DataSource` quản lý kết nối; `try-with-resources` đóng connection/statement/result set ngay cả khi lỗi.
- `PreparedStatement` bind giá trị tenant và giới hạn trang; Java không tự xây điều kiện SQL từ chuỗi không tin cậy.
- Database thực hiện `JOIN + GROUP BY + SUM + ORDER BY + LIMIT`; Java chỉ ánh xạ mỗi hàng kết quả thành một DTO.
- `BigDecimal` phù hợp cho số tiền `NUMERIC` hơn `double`.
- Không có vòng lặp truy vấn riêng cho từng khách, nên tránh một dạng N+1.
- Result set có tối đa 100 **nhóm khách**, dù database có nhiều đơn.

Với dữ liệu lớn, việc `LIMIT 100` **không bảo đảm** DB chỉ đọc 100 đơn; aggregation vẫn có thể cần xét mọi đơn phù hợp của tenant trước khi sắp xếp nhóm. Đo plan, thêm index hoặc thiết kế báo cáo tổng hợp vật hóa nếu sản phẩm có nhu cầu.

**Giới hạn:** Đây là ví dụ đọc báo cáo, chưa triển khai paging cursor hoặc transaction snapshot cho nhiều SELECT. Tầng API phải xác định tenant từ authentication, timeout, quyền và độ mới dữ liệu. Không suy rằng gọi `Connection.setReadOnly(true)` sẽ tự định tuyến sang read replica.

## 23. JOIN và GROUP BY trong JPA/Hibernate

JPA hỗ trợ JPQL để JOIN các quan hệ entity và tạo projection. Giả sử mapping có `CustomerEntity.orders` và `OrderEntity.status/total`, ta có thể viết:

```java
public record CustomerSummary(
        Long customerId,
        String name,
        Long paidOrders,
        java.math.BigDecimal paidTotal) {}
```

JPQL minh họa khi entity mapping, tên package và constructor expression đã được cấu hình đúng:

```java
List<CustomerSummary> results = entityManager.createQuery(
        """
        SELECT new com.example.api.CustomerSummary(
            c.id, c.displayName,
            COUNT(o.id), COALESCE(SUM(o.total), 0)
        )
        FROM CustomerEntity c
        LEFT JOIN c.orders o ON o.status = 'PAID'
        WHERE c.tenantId = :tenantId
        GROUP BY c.id, c.displayName
        ORDER BY COUNT(o.id) DESC, c.id ASC
        """,
        CustomerSummary.class)
    .setParameter("tenantId", authenticatedTenantId)
    .setMaxResults(100)
    .getResultList();
```

Ví dụ là **fragment giáo dục**, không phải lớp Java độc lập: `CustomerEntity`, `CustomerSummary`, `entityManager` và package `com.example.api` cần tồn tại trong dự án; kiểu `c.id`/`COUNT`/`SUM` phải khớp constructor DTO. Khả năng dùng `JOIN ... ON` trong JPQL và cách provider biên dịch truy vấn phụ thuộc mapping, Jakarta Persistence và phiên bản ORM.

### Không dùng `JOIN FETCH` khi chỉ cần COUNT/SUM

`JOIN FETCH` được dùng để tải quan hệ entity (theo fetch plan), không phải “bật tăng tốc” cho aggregate. Nếu báo cáo chỉ cần một DTO mỗi khách, projection theo SQL/JPQL giúp tránh tải toàn bộ graph entity và tránh N+1 do serializer chạm lazy relation.

Đồng thời, `EAGER` không đảm bảo ORM chỉ phát một SELECT; một fetch plan không hợp lý có thể nạp quan hệ thừa. Tốt hơn là xác định **mức hạt và trường dữ liệu cần thiết** ngay từ thiết kế query.

## 24. Query plan, index và chi phí thực thi

JOIN và aggregate đúng về mặt logic vẫn có thể chạy chậm nếu dữ liệu lớn hoặc thiếu index phù hợp. Các index ứng viên cho schema minh họa:

```sql
CREATE INDEX ix_demo_orders_tenant_customer
ON demo_orders(tenant_id, customer_id);

CREATE INDEX ix_demo_orders_tenant_status_customer
ON demo_orders(tenant_id, status, customer_id);

CREATE INDEX ix_demo_orders_tenant_recent
ON demo_orders(tenant_id, created_at DESC, id DESC);

CREATE INDEX ix_demo_lines_tenant_order
ON demo_order_lines(tenant_id, order_id);
```

**Không tạo tất cả các index này vô điều kiện** trong hệ thống thật: nhiều index trùng công dụng làm tăng dung lượng, WAL và chi phí ghi. Lựa chọn dựa trên tần suất truy vấn, mức chọn lọc, kế hoạch JOIN, số hàng/tenant, cập nhật thống kê và tải sản xuất.

Để xem cách PostgreSQL dự kiến thực thi:

```sql
-- Chạy trên môi trường có dữ liệu thử nghiệm/được phép.
EXPLAIN (ANALYZE, BUFFERS)
SELECT c.id,
       COUNT(o.id) AS paid_orders,
       COALESCE(SUM(o.total), 0) AS paid_total
FROM demo_customers c
LEFT JOIN demo_orders o
    ON o.tenant_id = c.tenant_id
   AND o.customer_id = c.id
   AND o.status = 'PAID'
WHERE c.tenant_id = 1
GROUP BY c.tenant_id, c.id
ORDER BY c.id;
```

Khi đọc plan, xem:

- **Rows estimated/actual:** số hàng sau JOIN và sau GROUP BY có đúng kỳ vọng không?
- **Join strategy:** nested loop, hash join hay merge join; lựa chọn phụ thuộc số hàng và chỉ mục.
- **Aggregate strategy:** hash aggregate hoặc group aggregate; có sort/hash dùng bộ nhớ lớn không?
- **Buffers và I/O:** đọc bao nhiêu dữ liệu, có spill/temp files không?
- **Sort và LIMIT:** database sắp xếp bao nhiêu nhóm trước khi trả trang?
- **Execution time:** phân biệt thời gian DB với network và xây DTO ở Java.

`EXPLAIN ANALYZE` **thực thi truy vấn** để đo. Với câu `SELECT` minh họa, thao tác đọc vẫn tiêu CPU/I/O; tránh chạy phân tích nặng trên primary production không được phép. **Số SQL ít** không đồng nghĩa **ít hàng hoặc ít công việc**, giống như việc chỉ nhìn số dòng code Java không chứng minh thuật toán tối ưu.

## 25. Nhất quán của kết quả tổng hợp

Một báo cáo có thể gồm **hai truy vấn**:

1. SELECT trang khách kèm `paid_total`.
2. SELECT số nhóm để tính tổng số trang.

Ở PostgreSQL `READ COMMITTED`, hai câu `SELECT` thông thường có snapshot theo từng statement. Nếu giữa chúng có đơn mới được commit, trang và tổng số nhóm/tổng tiền **có thể phản ánh hai thời điểm khác nhau**.

Lựa chọn tùy yêu cầu:

- **Dashboard gần thời gian thực:** chấp nhận biến động nhỏ, công bố độ mới và xử lý UI phù hợp.
- **Báo cáo tài chính/báo cáo chốt kỳ:** dùng snapshot/transaction isolation tương ứng hoặc dữ liệu snapshot đã chốt theo nghiệp vụ.
- **Read replica:** có thể trễ so với primary; phép `SUM` trên replica không tự bằng giá trị vừa commit ở primary.
- **Materialized view/precomputed summary:** giảm chi phí đọc nhưng phải có chiến lược refresh, invalidation, đối soát và nêu rõ độ trễ.

Nếu cần **cùng snapshot cho nhiều truy vấn trong một lượt xử lý**, một transaction PostgreSQL `REPEATABLE READ` có thể phù hợp; tuy nhiên giữ transaction dài tạo chi phí MVCC/connection và không nên dùng để giữ snapshot xuyên nhiều request HTTP thông thường.

**Aggregation đúng theo SQL chưa chắc đúng nghiệp vụ nếu nguồn dữ liệu đã không nhất quán**, ví dụ đơn đã thanh toán nhưng event hoàn tiền chưa được áp dụng. Cần kiểm chứng ranh giới dữ liệu có thẩm quyền và hành vi transaction/outbox khi xây dựng chỉ số quan trọng.

## 26. Những sai lầm thiết kế thường gặp

1. **JOIN khách–đơn nhưng quên khách chưa có đơn.** Dùng `INNER JOIN` khi màn hình yêu cầu mọi khách sẽ làm thiếu khách Chi.
2. **Lọc bảng phải của `LEFT JOIN` ở `WHERE` ngoài ý định.** Điều kiện `o.status = 'PAID'` có thể loại khách không có đơn.
3. **Dùng `COUNT(*)` để đếm con sau LEFT JOIN.** Khách không có đơn vẫn có một hàng ghép với NULL.
4. **Dùng `SUM(o.total)` sau khi JOIN thêm dòng hàng.** Một đơn có nhiều dòng bị cộng lại nhiều lần.
5. **Dùng `SUM(DISTINCT o.total)` để chữa nhân hàng.** Hai đơn hợp lệ có cùng tổng tiền sẽ bị coi như một giá trị.
6. **GROUP BY quá nhiều cột làm mức hạt thay đổi.** Muốn một hàng mỗi khách nhưng lại group cả `o.id` sẽ ra nhiều hàng trên khách.
7. **Thiếu điều kiện tenant khi JOIN khóa ghép.** Nguy cơ ghép nhầm dữ liệu hoặc rò rỉ chéo tổ chức.
8. **Nhầm `WHERE` với `HAVING`.** Điều kiện nhóm phải được tính sau khi gom hàng.
9. **Dùng `LIMIT` trên JOIN cha–con để phân trang cha.** Số hàng JOIN không bằng số cha.
10. **Lọc/phân trang sau khi tải toàn bộ trong Java.** Tạo N+1, chuyển dữ liệu thừa và chiếm heap.
11. **Lấy `COUNT(*)` của đơn làm số nhóm khách.** Số đơn và số khách không phải cùng mức hạt.
12. **Không có `ORDER BY` ổn định trước phân trang.** Các trang có thể thiếu/lặp khi thứ tự không xác định.
13. **Cộng các loại tiền hoặc trạng thái chưa đúng nghĩa “doanh thu”.** SQL cộng số chính xác nhưng chỉ số nghiệp vụ vẫn sai.
14. **Cho rằng `COALESCE(SUM(...), 0)` làm xuất hiện các nhóm không có hàng.** Nó chỉ thay giá trị null trên **một hàng kết quả đã tồn tại**; cần LEFT JOIN nếu muốn giữ khách không có đơn.
15. **Tin rằng một query JOIN luôn nhanh hơn hai query.** Fan-out lớn, sort/aggregate và network bytes có thể làm truy vấn một lần rất tốn kém.
16. **Tin rằng aggregate có thể được tính từ cache/replica mà không cần quy định độ mới.** Báo cáo có thể lệch với primary ngay sau commit.
17. **Dùng `SELECT *` trong báo cáo.** Tải cột thừa, dễ phát sinh phụ thuộc schema và khó hiểu mức hạt.
18. **Tin rằng cùng số hàng tức là cùng dữ liệu.** Khi kiểm thử, cần so business key, aggregate đúng và tenant scope, không chỉ tổng `COUNT(*)`.

## 27. Thực hành có hướng dẫn: từng bước từ JOIN đến báo cáo

**Bước 1 — Quan sát dữ liệu gốc.** Chạy:

```sql
SELECT id, display_name FROM demo_customers
WHERE tenant_id = 1 ORDER BY id;

SELECT id, customer_id, status, total FROM demo_orders
WHERE tenant_id = 1 ORDER BY id;

SELECT id, order_id, quantity, unit_price FROM demo_order_lines
WHERE tenant_id = 1 ORDER BY id;
```

Kỳ vọng: **3 khách, 3 đơn và 4 dòng hàng** của tenant 1.

**Bước 2 — INNER JOIN khách với đơn.** Quan sát An xuất hiện hai lần, Chi không xuất hiện.

**Bước 3 — LEFT JOIN khách với đơn.** Xác minh Chi xuất hiện và `o.id` là NULL.

**Bước 4 — Đếm khách có đơn.** So `COUNT(*)` với `COUNT(o.id)`. Giải thích vì sao Chi có 1 và 0.

**Bước 5 — Tổng hợp đơn PAID theo khách.** Dùng điều kiện status trong `ON`; kết quả An 120, Binh 90, Chi 0.

**Bước 6 — Tạo lỗi fan-out có chủ đích.** JOIN thêm `demo_order_lines`, chạy `SUM(o.total)` cho An và quan sát tổng sai 290 thay vì 170.

**Bước 7 — Sửa bằng mức hạt.** Bỏ JOIN dòng hàng hoặc tiền tổng hợp đơn trước; kiểm chứng tổng 170.

**Bước 8 — Phân trang theo đối tượng đúng.** Thử `LIMIT 2` sau GROUP BY khách và so với `LIMIT 2` trực tiếp trên JOIN đơn–dòng hàng.

**Bước 9 — Đưa kết quả vào Java.** Ánh xạ DTO bằng `PreparedStatement`, kiểm tra giới hạn page size và tenant lấy từ authentication.

**Bước 10 — Kiểm thử tính đúng và hiệu năng.** Assert số hàng, tổng, tenant, thứ tự, query plan, khả năng thay đổi khi thêm đơn mới và tác động trên dữ liệu lớn hơn.

Với bài thực hành khác, nên tự thiết kế một báo cáo theo `SKU` hoặc `ngày` và luôn viết trước: **khóa nhóm, mức hạt, điều kiện lọc, các trạng thái được tính, cách xử lý không có hàng và thứ tự trang**.

## 28. Bài tập tự kiểm tra

**Câu 1.** Với tenant 1, `INNER JOIN` khách và đơn trả mấy hàng? Vì sao Chi không có trong kết quả?

**Câu 2.** `LEFT JOIN` khách và đơn trả bao nhiêu hàng? Hàng của Chi có `order_id` là gì?

**Câu 3.** Khi dùng `LEFT JOIN`, vì sao `COUNT(*)` của Chi bằng 1 nhưng `COUNT(o.id)` bằng 0?

**Câu 4.** Muốn mọi khách kèm **chỉ các đơn PAID**, nên đặt `o.status = 'PAID'` trong `ON` hay `WHERE`? Vì sao?

**Câu 5.** Viết ý nghĩa của `GROUP BY status` trên bảng đơn của tenant 1. Kết quả có bao nhiêu nhóm?

**Câu 6.** Tổng các đơn `PAID` của tenant 1 là bao nhiêu, và có bao nhiêu đơn thuộc trạng thái đó?

**Câu 7.** Vì sao `SUM(o.total)` của An thành 290 khi JOIN thêm `demo_order_lines`? Tổng đúng của hai đơn An là bao nhiêu?

**Câu 8.** Có nên dùng `SUM(DISTINCT o.total)` để sửa tổng ở câu 7 không? Nêu một phản ví dụ.

**Câu 9.** `HAVING COUNT(o.id) >= 2` khác `WHERE o.status = 'PAID'` ở điểm nào?

**Câu 10.** Viết cấu trúc SQL để giữ khách không có đơn và trả `paid_total = 0` cho họ.

**Câu 11.** Một đơn có 10 dòng hàng. `LEFT JOIN` đơn với dòng rồi `LIMIT 5` có chắc trả đủ đơn đó cùng 10 dòng hàng không?

**Câu 12.** Một trang gồm 20 khách có tổng chi tiêu; để phân trang **khách**, nên áp `LIMIT` ở mức hàng JOIN hay ở mức nhóm khách?

**Câu 13.** Sau `JOIN`, điều kiện `o.customer_id = c.id` nhưng thiếu `o.tenant_id = c.tenant_id`. Rủi ro là gì?

**Câu 14.** Muốn tìm khách **không có đơn PAID**, `NOT EXISTS` có lợi thế gì về ý nghĩa so với JOIN rồi lọc/khử trùng?

**Câu 15.** Một report tính tổng tiền đơn sau khi đã chọn `LIMIT 20` đơn gần nhất. Chỉ số đó có phải tổng tiền toàn bộ lịch sử không?

**Câu 16.** Nếu trang kết quả có một hàng mỗi khách, tại sao không dùng `COUNT(*) FROM demo_orders` để tính số trang?

**Câu 17.** Tại sao `COALESCE(SUM(o.total), 0)` không tự làm một khách biến mất bởi `INNER JOIN` quay lại kết quả?

**Câu 18.** Một báo cáo trả An 120 ở thời điểm T1; khách vừa thanh toán đơn mới trên primary nhưng report dùng read replica ở T2 vẫn 120. Đó có chắc là lỗi `SUM` không?

**Câu 19.** Trong JDBC, vì sao dùng `PreparedStatement` và `BigDecimal` cho một report có tenant và tổng tiền?

**Câu 20.** Nếu báo cáo có 10.000 đơn nhưng chỉ trả 20 nhóm, `LIMIT 20` có đảm bảo DB chỉ đọc 20 đơn không? Cần công cụ gì để quan sát công việc thực tế?

### Gợi ý đáp án

1. **3 hàng**: An có hai đơn, Binh có một; Chi không có đơn nên không khớp INNER JOIN.
2. **4 hàng**: hai của An, một của Binh, một của Chi với `order_id = NULL`.
3. `COUNT(*)` đếm cả hàng “Chi + NULL” mà LEFT JOIN tạo; `COUNT(o.id)` không đếm NULL.
4. **Trong `ON`** để vẫn giữ khách không có đơn PAID; đặt trong WHERE loại hàng có phía phải là NULL.
5. Gom các đơn tenant 1 thành **2 nhóm**: `NEW` và `PAID`.
6. **2 đơn PAID**, tổng **210** (= 120 + 90).
7. Đơn 1001 có 2 dòng khiến 120 được lặp hai lần; cộng thêm đơn 1002 là 50 thành 290; tổng đúng **170**.
8. **Không.** Nếu hai đơn độc lập cùng có `total = 50`, `SUM(DISTINCT total)` chỉ cộng 50 một lần.
9. `WHERE` lọc hàng trước nhóm; `HAVING` lọc nhóm dựa trên giá trị aggregate đã tính.
10. `FROM customers c LEFT JOIN orders o ON ... AND o.status='PAID' WHERE c.tenant_id=? GROUP BY c.id...`, dùng `COUNT(o.id)` và `COALESCE(SUM(o.total),0)`.
11. **Không.** LIMIT áp vào hàng JOIN, có thể chỉ trả 5/10 dòng của một đơn.
12. Áp `LIMIT` **sau khi nhóm theo khách**, hoặc chọn page khách trước rồi tính aggregate cho đúng tập khách.
13. Có thể ghép sai dữ liệu giữa các tenant khi ID không duy nhất toàn hệ; đây vừa là lỗi kết quả vừa là lỗi bảo mật.
14. `NOT EXISTS` trực tiếp diễn đạt “không có quan hệ thỏa điều kiện”, không bị nhân hàng bởi nhiều đơn.
15. **Không.** Đó là tổng trên **20 đơn trong trang**; phải ghi rõ phạm vi chỉ số.
16. Một khách có thể có nhiều đơn; số hàng đơn khác số nhóm khách được phân trang.
17. `COALESCE` chỉ thay NULL trên **hàng kết quả đang tồn tại**; INNER JOIN đã loại khách không có đơn trước đó.
18. **Không chắc.** Read replica có thể chưa replay commit; cần xác minh nguồn đọc, độ trễ và hợp đồng read-your-writes.
19. `PreparedStatement` bind tenant/lọc an toàn, `BigDecimal` giữ độ chính xác thập phân của `NUMERIC` khi tính tiền.
20. **Không.** DB có thể phải JOIN/aggregate rất nhiều hàng trước khi giới hạn nhóm; dùng `EXPLAIN (ANALYZE, BUFFERS)` và đo rows/buffers/latency.

## Kết luận

**JOIN** trả lời “những dữ liệu nào liên hệ với nhau?”, còn **GROUP BY và các hàm tổng hợp** trả lời “muốn tính chỉ số gì trên những nhóm nào?”. Khi kết hợp chúng, yếu tố quan trọng nhất là **mức hạt của từng hàng**: một khách, một đơn, một dòng hàng hay một nhóm báo cáo. Sai mức hạt sẽ dẫn tới đếm trùng, cộng lặp và phân trang sai ngay cả khi SQL không có lỗi cú pháp.

Trong **DATA_PERSISTENCE_FUNDAMENTALS**, hãy luôn xác định **khóa quan hệ, phạm vi tenant, loại JOIN, chỗ đặt điều kiện, khóa GROUP BY, ý nghĩa COUNT/SUM, cách xử lý NULL và mức hạt của LIMIT** trước khi đưa kết quả tới Java. Chỉ chọn các cột cần thiết, ưu tiên DTO projection, dùng SQL theo tập hợp để tránh N+1, giữ ranh giới transaction/độ mới phù hợp và kiểm chứng bằng dữ liệu mẫu cùng query plan. Khi hiểu đúng các phép kết hợp và tổng hợp ở mức khái niệm, bạn mới có nền tảng vững để thiết kế truy vấn thực tế, phân trang và tối ưu persistence mà không làm thay đổi ý nghĩa nghiệp vụ.
