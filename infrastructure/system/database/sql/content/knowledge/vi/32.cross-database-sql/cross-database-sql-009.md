# UPDATE JOIN, DELETE JOIN và cú pháp thay thế

Trong ứng dụng, dữ liệu cần cập nhật thường nằm ở nhiều bảng. Ví dụ trạng thái đơn hàng nằm trong `orders`, còn trạng thái vận chuyển mới nhất nằm trong `shipment_updates`. Ta muốn đồng bộ `orders.status` theo bảng vận chuyển. Hoặc sau khi import thành công, ta muốn xóa những dòng staging tương ứng mà không xóa nhầm dữ liệu chính.

Các thao tác đó thường được gọi là **UPDATE JOIN** và **DELETE JOIN**: cập nhật hoặc xóa một bảng dựa trên điều kiện nối với bảng khác. Tuy nhiên, không phải hệ quản trị nào cũng dùng cùng cú pháp. MySQL có `UPDATE ... JOIN`; SQL Server có `UPDATE ... FROM`; PostgreSQL có `UPDATE ... FROM` và `DELETE ... USING`; SQLite có `UPDATE ... FROM` ở phiên bản mới nhưng không có `DELETE JOIN` trực tiếp; Oracle thường dùng `MERGE` hoặc correlated subquery.

Bài học **“UPDATE JOIN, DELETE JOIN và cú pháp thay thế”**, thuộc chương **SQL đa hệ quản trị** của module **Database SQL**, giải thích cách hiểu chung và cách viết theo từng DBMS, đồng thời chỉ ra những khác biệt có thể làm câu SQL chạy sai hoặc cập nhật/xóa nhiều dòng ngoài dự kiến.

Sau bài học, bạn cần:

- Hiểu target table, source table, join condition và điều kiện lọc.
- Viết UPDATE JOIN và DELETE JOIN theo cú pháp MySQL, SQL Server, PostgreSQL, SQLite và Oracle.
- Chọn cú pháp thay thế bằng `EXISTS`, correlated subquery, CTE hoặc `MERGE`.
- Tránh cập nhật một dòng đích từ nhiều dòng nguồn không xác định.
- Dự đoán đúng ảnh hưởng của `INNER JOIN`, `LEFT JOIN`, `NULL`, `NOT EXISTS` và khóa ngoại.
- Thực hiện preview, transaction, kiểm tra row count, rollback hoặc commit an toàn.

> **Nguyên tắc trung tâm:** Hãy xác định rõ **bảng nào là target**, **bảng nào cung cấp dữ liệu/điều kiện**, và **mỗi dòng target có thể khớp bao nhiêu dòng source**. Cú pháp khác nhau giữa DBMS, nhưng ba câu hỏi này luôn quan trọng.

## 1. UPDATE JOIN và DELETE JOIN là gì?

Giả sử có hai bảng:

```text
orders
┌──────────┬─────────────┬─────────┐
│ order_id │ customer_id│ status  │
├──────────┼─────────────┼─────────┤
│ 1001     │ 10          │ PENDING │
│ 1002     │ 20          │ PENDING │
│ 1003     │ 10          │ PAID    │
└──────────┴─────────────┴─────────┘

shipment_updates
┌──────────┬──────────────┬────────────┐
│ order_id │ new_status   │ shipped_at │
├──────────┼──────────────┼────────────┤
│ 1001     │ SHIPPED      │ ...        │
│ 1002     │ DELIVERED    │ ...        │
└──────────┴──────────────┴────────────┘
```

Muốn cập nhật `orders.status` theo dữ liệu giao hàng, ta cần:

1. Chọn dòng `orders` là **target**.
2. Nối với `shipment_updates` bằng `order_id`.
3. Chỉ cập nhật các đơn đang `PENDING`.
4. Gán trạng thái mới và thời điểm vận chuyển.

Về mặt ý tưởng:

```sql
UPDATE orders
SET status = shipment_updates.new_status
FROM/JOIN shipment_updates
WHERE orders.order_id = shipment_updates.order_id;
```

Đây chỉ là **mô tả ý tưởng**, chưa phải cú pháp chạy được trên mọi DBMS. Cách đặt `FROM`, `JOIN`, alias và tên target thay đổi theo hệ quản trị.

### 1.1. UPDATE JOIN

`UPDATE JOIN` là cách gọi nhóm câu lệnh cập nhật target dựa trên dữ liệu nối từ một hoặc nhiều bảng source. Thường dùng để đồng bộ trạng thái, tính lại giá/thuế/số lượng, cập nhật khách hàng theo bảng tổng hợp hoặc áp dữ liệu đã xác thực từ staging.

### 1.2. DELETE JOIN

`DELETE JOIN` là cách gọi nhóm câu lệnh xóa target khi có dòng source thỏa điều kiện nối. Thường dùng để xóa dòng staging đã import, cleanup dữ liệu tạm, xóa bản ghi trùng theo quy tắc chọn dòng giữ lại hoặc xóa dữ liệu hết hạn.

**Tên gọi “DELETE JOIN” không phải cú pháp chuẩn dùng chung.** Cần viết theo DBMS.

## 2. Phân biệt target và source

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Target table | Bảng bị thay đổi | `orders` |
| Source table | Bảng cung cấp dữ liệu/điều kiện | `shipment_updates` |
| Join key | Cột dùng ghép dòng | `order_id` |
| Join condition | Điều kiện xác định source tương ứng | `o.order_id = s.order_id` |
| Update assignment | Cột target nhận giá trị mới | `o.status = s.new_status` |
| Filter condition | Giới hạn dòng được thay đổi | `o.status = 'PENDING'` |

```text
orders o                    shipment_updates s
┌──────────┬─────────┐      ┌──────────┬─────────────┐
│ order_id │ status  │      │ order_id │ new_status  │
├──────────┼─────────┤      ├──────────┼─────────────┤
│ 1001     │ PENDING │ ───► │ 1001     │ SHIPPED     │
│ 1002     │ PENDING │ ───► │ 1002     │ DELIVERED   │
│ 1003     │ PAID    │      │          │             │
└──────────┴─────────┘      └──────────┴─────────────┘
        Target                         Source
```

Trong SQL Server:

```sql
UPDATE o
SET status = s.new_status
FROM dbo.orders AS o
INNER JOIN dbo.shipment_updates AS s
    ON s.order_id = o.order_id;
```

Target là `o` (`orders`). `shipment_updates` chỉ cung cấp `new_status`. Dù JOIN tạo ra nhiều dòng kết hợp, câu lệnh chỉ thay đổi target được chỉ định (trừ cú pháp multi-table update riêng của MySQL).

## 3. Bộ dữ liệu thực hành

Các ví dụ dùng mô hình đơn hàng và dữ liệu vận chuyển. Hãy chạy trên database test riêng. DDL sau gần với PostgreSQL; khi thực hành trên DBMS khác, điều chỉnh kiểu số, timestamp, identity và boolean theo hệ quản trị.

### 3.1. Tạo bảng

```sql
CREATE TABLE customers (
    customer_id BIGINT PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL,
    customer_tier VARCHAR(20) NOT NULL DEFAULT 'STANDARD'
);

CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount NUMERIC(12,2) NOT NULL,
    shipped_at TIMESTAMP NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id),
    CONSTRAINT ck_orders_status
        CHECK (status IN (
            'PENDING', 'PAID', 'SHIPPED',
            'DELIVERED', 'CANCELLED'
        )),
    CONSTRAINT ck_orders_amount
        CHECK (total_amount >= 0)
);

CREATE TABLE shipment_updates (
    order_id BIGINT PRIMARY KEY,
    new_status VARCHAR(20) NOT NULL,
    new_shipped_at TIMESTAMP NULL,
    received_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_shipment_update_order
        FOREIGN KEY (order_id)
        REFERENCES orders(order_id)
);

CREATE TABLE import_stage (
    stage_id BIGINT PRIMARY KEY,
    batch_id VARCHAR(40) NOT NULL,
    order_id BIGINT NOT NULL,
    imported BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Khóa chính `shipment_updates.order_id` bảo đảm tối đa một dòng source cho mỗi đơn trong ví dụ cơ bản. Đây là lựa chọn thiết kế quan trọng để UPDATE không phải đoán khi có nhiều source match.

### 3.2. Nạp dữ liệu

```sql
INSERT INTO customers
    (customer_id, customer_name, customer_tier)
VALUES
    (10, 'An', 'STANDARD'),
    (20, 'Binh', 'STANDARD'),
    (30, 'Chi', 'STANDARD');

INSERT INTO orders
    (order_id, customer_id, status, total_amount)
VALUES
    (1001, 10, 'PENDING', 150.00),
    (1002, 20, 'PENDING', 320.00),
    (1003, 10, 'PAID',     90.00),
    (1004, 30, 'CANCELLED', 50.00),
    (1005, 20, 'PENDING', 500.00);

INSERT INTO shipment_updates
    (order_id, new_status, new_shipped_at)
VALUES
    (1001, 'SHIPPED',   TIMESTAMP '2026-11-10 09:00:00'),
    (1002, 'DELIVERED', TIMESTAMP '2026-11-11 10:30:00'),
    (1005, 'SHIPPED',   TIMESTAMP '2026-11-12 15:00:00');

INSERT INTO import_stage
    (stage_id, batch_id, order_id, imported)
VALUES
    (1, 'BATCH-A', 1001, TRUE),
    (2, 'BATCH-A', 1002, TRUE),
    (3, 'BATCH-A', 1003, FALSE),
    (4, 'BATCH-B', 1004, TRUE),
    (5, 'BATCH-B', 1005, FALSE);
```

### 3.3. Kiểm tra dữ liệu

```sql
SELECT * FROM customers ORDER BY customer_id;
SELECT * FROM orders ORDER BY order_id;
SELECT * FROM shipment_updates ORDER BY order_id;
SELECT * FROM import_stage ORDER BY stage_id;
```

Các đơn `1001`, `1002`, `1005` đang `PENDING` và có trạng thái vận chuyển mới. Đơn `1003` đã `PAID`; đơn `1004` đã `CANCELLED`. Batch `BATCH-A` có hai dòng `imported=TRUE`.

## 4. Quy tắc an toàn trước UPDATE JOIN hoặc DELETE JOIN

Trước khi thay đổi dữ liệu, hãy chạy `SELECT` dùng cùng điều kiện join/filter để biết chính xác những dòng sẽ bị tác động.

### 4.1. Preview UPDATE

```sql
SELECT
    o.order_id,
    o.status AS old_status,
    s.new_status,
    o.shipped_at AS old_shipped_at,
    s.new_shipped_at
FROM orders AS o
INNER JOIN shipment_updates AS s
    ON s.order_id = o.order_id
WHERE o.status = 'PENDING'
ORDER BY o.order_id;
```

Dự kiến ba đơn `1001`, `1002`, `1005`.

### 4.2. Preview DELETE

```sql
SELECT
    st.stage_id, st.batch_id, st.order_id, st.imported
FROM import_stage AS st
JOIN shipment_updates AS s
    ON s.order_id = st.order_id
WHERE st.batch_id = 'BATCH-A'
  AND st.imported = TRUE
  AND s.new_status IN ('SHIPPED', 'DELIVERED')
ORDER BY st.stage_id;
```

Preview trả hai dòng `stage_id=1` và `stage_id=2`, dựa trên trạng thái vận chuyển mới sẽ được áp dụng cho các đơn tương ứng.

### 4.3. Đặt điều kiện đủ hẹp

Một câu:

```sql
UPDATE orders
SET status = 'CANCELLED';
```

không có `WHERE` sẽ cập nhật **mọi dòng** trong bảng. Với UPDATE/DELETE dựa trên JOIN, điều kiện join cũng có thể quá rộng hoặc thiếu một phần khóa.

Hãy kiểm tra:

- Join có đủ các cột định danh không?
- Có cần thêm tenant/company/account ID để cách ly dữ liệu không?
- Có cần lọc trạng thái hiện tại để tránh ghi đè cập nhật mới hơn không?
- Source có thể có nhiều dòng cho một target không?
- Có cần giới hạn batch, thời gian hoặc partition không?

### 4.4. Preview không phải khóa dữ liệu

Một `SELECT COUNT(*)` trước UPDATE hữu ích để preview, nhưng dữ liệu có thể thay đổi giữa preview và thực thi. Nếu cần invariant mạnh hơn, dùng transaction, isolation/locking phù hợp và kiểm tra row count sau câu lệnh.

## 5. UPDATE JOIN trong MySQL

MySQL hỗ trợ cú pháp UPDATE có `JOIN` ngay sau target table.

### 5.1. Cú pháp tổng quát

```sql
UPDATE target_table AS t
JOIN source_table AS s
    ON s.join_key = t.join_key
SET
    t.target_column = s.source_column
WHERE condition;
```

`JOIN` có thể là `INNER JOIN`, `LEFT JOIN` hoặc loại join mà MySQL hỗ trợ trong `table_references`.

### 5.2. Cập nhật trạng thái đơn

```sql
UPDATE orders AS o
INNER JOIN shipment_updates AS s
    ON s.order_id = o.order_id
SET
    o.status = s.new_status,
    o.shipped_at = s.new_shipped_at,
    o.updated_at = CURRENT_TIMESTAMP
WHERE o.status = 'PENDING';
```

Với dữ liệu mẫu, ba đơn `1001`, `1002`, `1005` được cập nhật.

### 5.3. UPDATE JOIN nhiều bảng

```sql
UPDATE orders AS o
JOIN shipment_updates AS s
    ON s.order_id = o.order_id
JOIN customers AS c
    ON c.customer_id = o.customer_id
SET
    o.status = s.new_status,
    o.updated_at = CURRENT_TIMESTAMP
WHERE c.customer_tier = 'GOLD'
  AND o.status = 'PENDING';
```

Chỉ cập nhật đơn có khách hàng thuộc tier `GOLD` và trạng thái còn `PENDING`.

### 5.4. UPDATE với LEFT JOIN

Nếu muốn xét tất cả đơn đang `PENDING`, kể cả đơn chưa có shipment update:

```sql
UPDATE orders AS o
LEFT JOIN shipment_updates AS s
    ON s.order_id = o.order_id
SET o.shipped_at = s.new_shipped_at
WHERE o.status = 'PENDING';
```

Đơn không có source match sẽ nhận NULL cho `shipped_at`, có thể xóa giá trị cũ ngoài ý muốn. Nếu muốn giữ giá trị cũ:

```sql
SET o.shipped_at =
    COALESCE(s.new_shipped_at, o.shipped_at)
```

`COALESCE` chỉ đúng nếu NULL từ source có nghĩa “không cung cấp giá trị mới”. Nếu NULL có nghĩa “xóa thời gian”, cách này không đúng.

### 5.5. Cập nhật nhiều bảng trong MySQL

MySQL có cú pháp multi-table update:

```sql
UPDATE orders AS o
JOIN shipment_updates AS s
    ON s.order_id = o.order_id
SET
    o.status = s.new_status,
    s.received_at = CURRENT_TIMESTAMP
WHERE o.status = 'PENDING';
```

Cả `orders` và `shipment_updates` đều là target. Đây là khả năng đặc thù MySQL, không phải cú pháp portable. Khi nhiều thay đổi phụ thuộc nhau, tách thành các câu lệnh có transaction thường dễ kiểm soát hơn.

### 5.6. UPDATE JOIN với aggregate source

Tính tổng các đơn đã thanh toán trước, tạo một dòng cho mỗi khách:

```sql
UPDATE customers AS c
JOIN (
    SELECT
        customer_id,
        SUM(total_amount) AS paid_total
    FROM orders
    WHERE status IN ('PAID', 'SHIPPED', 'DELIVERED')
    GROUP BY customer_id
) AS totals
    ON totals.customer_id = c.customer_id
SET c.customer_tier =
    CASE
        WHEN totals.paid_total >= 1000 THEN 'GOLD'
        WHEN totals.paid_total >= 300 THEN 'SILVER'
        ELSE 'STANDARD'
    END;
```

Subquery `totals` có tối đa một dòng cho mỗi `customer_id` nhờ `GROUP BY`, nên không có source duplicate cho một target.

## 6. DELETE JOIN trong MySQL

MySQL cho phép chỉ rõ alias target cần xóa ngay sau `DELETE`.

### 6.1. Cú pháp tổng quát

```sql
DELETE t
FROM target_table AS t
JOIN source_table AS s
    ON s.join_key = t.join_key
WHERE condition;
```

### 6.2. Xóa dòng staging đã import

```sql
DELETE st
FROM import_stage AS st
WHERE st.batch_id = 'BATCH-A'
  AND st.imported = TRUE;
```

Khi cần join với bảng khác:

```sql
DELETE st
FROM import_stage AS st
INNER JOIN orders AS o
    ON o.order_id = st.order_id
WHERE st.batch_id = 'BATCH-A'
  AND st.imported = TRUE
  AND o.status IN ('SHIPPED', 'DELIVERED');
```

Chỉ xóa `import_stage`, không xóa `orders`.

### 6.3. Xóa nhiều bảng cùng lúc

```sql
DELETE st, audit
FROM import_stage AS st
JOIN import_audit AS audit
    ON audit.stage_id = st.stage_id
WHERE st.batch_id = 'BATCH-A'
  AND st.imported = TRUE;
```

Cả `st` và `audit` là target. Chỉ dùng khi thật sự muốn xóa cả hai và hiểu quan hệ khóa ngoại.

### 6.4. DELETE với LEFT JOIN để xóa dòng không có match

```sql
DELETE st
FROM import_stage AS st
LEFT JOIN orders AS o
    ON o.order_id = st.order_id
WHERE o.order_id IS NULL;
```

Xóa staging rows không có đơn tương ứng. Điều kiện `o.order_id IS NULL` an toàn vì `order_id` là khóa chính, không thể NULL khi có match. Không kiểm tra một cột nullable như `o.shipped_at IS NULL` để suy ra không có source row.

## 7. UPDATE FROM và DELETE trong SQL Server

SQL Server thường viết UPDATE target, sau đó đưa các bảng source/join vào `FROM`.

### 7.1. UPDATE FROM

```sql
UPDATE t
SET
    target_column = s.source_column
FROM dbo.target_table AS t
INNER JOIN dbo.source_table AS s
    ON s.join_key = t.join_key
WHERE condition;
```

### 7.2. Cập nhật trạng thái đơn

```sql
UPDATE o
SET
    status = s.new_status,
    shipped_at = s.new_shipped_at,
    updated_at = SYSUTCDATETIME()
FROM dbo.orders AS o
INNER JOIN dbo.shipment_updates AS s
    ON s.order_id = o.order_id
WHERE o.status = 'PENDING';
```

`UPDATE o` xác định target alias. `FROM` mô tả tập dòng kết hợp. `SYSUTCDATETIME()` trả thời điểm UTC hiện tại của SQL Server.

### 7.3. UPDATE JOIN nhiều bảng

```sql
UPDATE o
SET status = s.new_status
FROM dbo.orders AS o
INNER JOIN dbo.shipment_updates AS s
    ON s.order_id = o.order_id
INNER JOIN dbo.customers AS c
    ON c.customer_id = o.customer_id
WHERE c.customer_tier = 'GOLD'
  AND o.status = 'PENDING';
```

### 7.4. OUTPUT để xem các dòng đã thay đổi

```sql
UPDATE o
SET
    status = s.new_status,
    updated_at = SYSUTCDATETIME()
OUTPUT
    inserted.order_id,
    deleted.status AS old_status,
    inserted.status AS new_status
FROM dbo.orders AS o
INNER JOIN dbo.shipment_updates AS s
    ON s.order_id = o.order_id
WHERE o.status = 'PENDING';
```

- `deleted` biểu diễn giá trị trước update.
- `inserted` biểu diễn giá trị sau update.

`OUTPUT` hữu ích cho audit hoặc thu kết quả trong cùng statement. Nếu ghi audit ra nơi khác, phải gắn nó với transaction đúng; dữ liệu OUTPUT quan sát được không tự chứng minh transaction đã commit.

### 7.5. DELETE JOIN trong SQL Server

```sql
DELETE st
FROM dbo.import_stage AS st
INNER JOIN dbo.orders AS o
    ON o.order_id = st.order_id
WHERE st.batch_id = 'BATCH-A'
  AND st.imported = 1
  AND o.status IN ('SHIPPED', 'DELIVERED');
```

Alias `st` là target bị xóa.

### 7.6. DELETE OUTPUT

```sql
DELETE st
OUTPUT
    deleted.stage_id,
    deleted.batch_id,
    deleted.order_id
FROM dbo.import_stage AS st
WHERE st.batch_id = 'BATCH-A'
  AND st.imported = 1;
```

SQL Server dùng `deleted` để lấy dòng bị xóa. Có thể dùng `OUTPUT ... INTO` để ghi audit trong database.

### 7.7. Cẩn thận với source match nhiều dòng

SQL Server cảnh báo kết quả UPDATE không xác định nếu `FROM` không bảo đảm chỉ một giá trị source cho mỗi cột target cần cập nhật. Hãy đảm bảo source có unique key hoặc tổng hợp/chọn một dòng trước.

## 8. UPDATE FROM và DELETE USING trong PostgreSQL

PostgreSQL hỗ trợ `UPDATE ... FROM`. Target được nêu sau `UPDATE`; bảng source được đưa vào `FROM`.

### 8.1. UPDATE FROM

```sql
UPDATE target_table AS t
SET target_column = s.source_column
FROM source_table AS s
WHERE s.join_key = t.join_key
  AND condition;
```

Ví dụ:

```sql
UPDATE orders AS o
SET
    status = s.new_status,
    shipped_at = s.new_shipped_at,
    updated_at = CURRENT_TIMESTAMP
FROM shipment_updates AS s
WHERE s.order_id = o.order_id
  AND o.status = 'PENDING'
RETURNING
    o.order_id,
    o.status,
    o.shipped_at;
```

Điểm cú pháp:

- `orders AS o` là target.
- `shipment_updates AS s` nằm trong `FROM`.
- Join condition nằm trong `WHERE`.
- Phía trái của `SET` viết tên cột target, không đặt alias trước cột đích trong PostgreSQL.
- `RETURNING` trả các dòng đã được cập nhật.

### 8.2. UPDATE FROM với nhiều source

```sql
UPDATE orders AS o
SET status = src.new_status
FROM (
    SELECT
        s.order_id,
        s.new_status
    FROM shipment_updates AS s
    JOIN orders AS source_order
        ON source_order.order_id = s.order_id
    JOIN customers AS c
        ON c.customer_id = source_order.customer_id
    WHERE c.customer_tier = 'GOLD'
) AS src
WHERE src.order_id = o.order_id
  AND o.status = 'PENDING';
```

Subquery làm rõ tập source đủ điều kiện trước khi update.

### 8.3. DELETE USING

PostgreSQL dùng `USING` thay cho `JOIN` trực tiếp sau target:

```sql
DELETE FROM import_stage AS st
USING orders AS o
WHERE o.order_id = st.order_id
  AND st.batch_id = 'BATCH-A'
  AND st.imported = TRUE
  AND o.status IN ('SHIPPED', 'DELIVERED')
RETURNING st.stage_id, st.order_id;
```

`USING` đưa source table vào điều kiện xóa. Target là `import_stage`.

### 8.4. Xóa theo NOT EXISTS

```sql
DELETE FROM import_stage AS st
WHERE st.batch_id = 'BATCH-A'
  AND NOT EXISTS (
      SELECT 1
      FROM orders AS o
      WHERE o.order_id = st.order_id
  )
RETURNING st.stage_id, st.order_id;
```

### 8.5. RETURNING

PostgreSQL hỗ trợ `RETURNING` cho UPDATE và DELETE, hữu ích để biết dòng nào đã thay đổi, lấy khóa để audit hoặc trả dữ liệu cho ứng dụng trong cùng statement. `RETURNING` không tự commit transaction.

### 8.6. Cảnh báo nhiều dòng source

Nếu một target row nối với nhiều source row trong `UPDATE ... FROM`, PostgreSQL chỉ dùng một source row để cập nhật nhưng **không bảo đảm source row nào được chọn**. Không được dựa vào thứ tự tình cờ của execution plan.

## 9. UPDATE FROM và DELETE trong SQLite

SQLite hỗ trợ `UPDATE FROM` từ phiên bản **3.33.0**.

### 9.1. UPDATE FROM

```sql
UPDATE orders AS o
SET
    status = s.new_status,
    shipped_at = s.new_shipped_at,
    updated_at = CURRENT_TIMESTAMP
FROM shipment_updates AS s
WHERE s.order_id = o.order_id
  AND o.status = 'PENDING';
```

Target nằm sau `UPDATE`; source nằm trong `FROM`. Nếu cần self-join, phải dùng alias cho instance source riêng theo cú pháp SQLite.

Nếu source join tạo nhiều dòng cho một target row, SQLite chọn một dòng source tùy ý; lựa chọn có thể thay đổi theo lần chạy hoặc phiên bản. Hãy bảo đảm source một-một hoặc tạo source đã tổng hợp.

### 9.2. DELETE JOIN không có trực tiếp

SQLite không có cú pháp `DELETE target FROM ... JOIN ...` như MySQL/SQL Server và không có `DELETE ... USING` như PostgreSQL. Cách thay thế phổ biến là `EXISTS`:

```sql
DELETE FROM import_stage AS st
WHERE st.batch_id = 'BATCH-A'
  AND st.imported = 1
  AND EXISTS (
      SELECT 1
      FROM orders AS o
      WHERE o.order_id = st.order_id
        AND o.status IN ('SHIPPED', 'DELIVERED')
  );
```

SQLite từ phiên bản **3.35.0** hỗ trợ `RETURNING` cho nhiều câu DML:

```sql
DELETE FROM import_stage AS st
WHERE st.batch_id = 'BATCH-A'
  AND st.imported = 1
RETURNING stage_id, order_id;
```

Hãy kiểm tra version SQLite được nhúng trong ứng dụng, không chỉ version công cụ CLI trên máy.

## 10. Oracle: correlated UPDATE, EXISTS và MERGE

Oracle có cú pháp `UPDATE ... SET ...` và `DELETE ... WHERE ...`; khi cần dùng dữ liệu bảng khác, các cách phổ biến là scalar/correlated subquery, `EXISTS` hoặc `MERGE`.

### 10.1. UPDATE bằng correlated subquery

```sql
UPDATE orders o
SET
    (status, shipped_at) = (
        SELECT
            s.new_status,
            s.new_shipped_at
        FROM shipment_updates s
        WHERE s.order_id = o.order_id
    )
WHERE EXISTS (
    SELECT 1
    FROM shipment_updates s
    WHERE s.order_id = o.order_id
)
AND o.status = 'PENDING';
```

`EXISTS` bảo đảm chỉ cập nhật những đơn có source match. Nếu bỏ `EXISTS`, scalar subquery không trả dòng có thể làm các cột đích nhận NULL.

### 10.2. Scalar subquery phải trả tối đa một dòng

Nếu subquery trả nhiều dòng cho cùng target, Oracle báo lỗi scalar subquery có nhiều dòng (thường `ORA-01427`). Đây là dấu hiệu source không duy nhất; hãy thiết kế unique key hoặc aggregate trước.

### 10.3. UPDATE bằng MERGE

```sql
MERGE INTO orders o
USING shipment_updates s
ON (o.order_id = s.order_id)
WHEN MATCHED THEN
    UPDATE SET
        o.status = s.new_status,
        o.shipped_at = s.new_shipped_at,
        o.updated_at = CURRENT_TIMESTAMP
    WHERE o.status = 'PENDING';
```

`MERGE` đối chiếu target và source theo `ON`, sau đó thực hiện hành động khi match. Có thể dùng thêm `WHEN NOT MATCHED THEN INSERT` nếu nghiệp vụ cần upsert.

### 10.4. Lưu ý với MERGE

- Source cần được chuẩn hóa để một target không bị nhiều source cạnh tranh cập nhật.
- Oracle có giới hạn về cột được cập nhật trong `ON` condition; không thể tùy ý thay đổi cột dùng để xác định match.
- `MERGE` không tự giải quyết mọi race condition hoặc duplicate; unique constraint vẫn quan trọng.
- Cú pháp và khả năng `MERGE` khác nhau theo phiên bản Oracle và DBMS khác.

### 10.5. DELETE bằng EXISTS

```sql
DELETE FROM import_stage st
WHERE st.batch_id = 'BATCH-A'
  AND st.imported = 1
  AND EXISTS (
      SELECT 1
      FROM orders o
      WHERE o.order_id = st.order_id
        AND o.status IN ('SHIPPED', 'DELIVERED')
  );
```

### 10.6. MERGE DELETE không phải DELETE JOIN tổng quát

Oracle `MERGE` có mệnh đề `DELETE WHERE` trong nhánh matched update ở các phiên bản hỗ trợ, nhưng nó chỉ xóa những dòng target **đã được cập nhật bởi MERGE** và thỏa điều kiện delete. Nó không phải cú pháp tổng quát để xóa mọi target row có source match. Nếu yêu cầu chỉ là xóa target theo điều kiện tồn tại ở bảng khác, `DELETE ... WHERE EXISTS` thường rõ ràng hơn.

## 11. Bảng so sánh cú pháp giữa các DBMS

| DBMS | UPDATE dựa trên JOIN | DELETE dựa trên JOIN | Cách thay thế phổ biến |
|---|---|---|---|
| MySQL | `UPDATE t JOIN s ON ... SET ...` | `DELETE t FROM t JOIN s ...` | `EXISTS`, subquery |
| SQL Server | `UPDATE t SET ... FROM t JOIN s ...` | `DELETE t FROM t JOIN s ...` | `EXISTS`, CTE, `MERGE` |
| PostgreSQL | `UPDATE t SET ... FROM s WHERE ...` | `DELETE FROM t USING s WHERE ...` | `EXISTS`, CTE |
| SQLite 3.33+ | `UPDATE t SET ... FROM s WHERE ...` | Không có DELETE JOIN trực tiếp | `DELETE ... WHERE EXISTS` |
| Oracle | Correlated subquery hoặc `MERGE` | `DELETE ... WHERE EXISTS` | `MERGE` cho upsert/matched update |

Không có một cú pháp UPDATE JOIN chuẩn dùng được ở mọi nơi:

```sql
UPDATE t JOIN s ON ... SET ...;   -- MySQL
UPDATE t SET ... FROM t JOIN s;  -- SQL Server
UPDATE t SET ... FROM s WHERE;   -- PostgreSQL / SQLite
UPDATE t SET col = (SELECT ...); -- Oracle và nhiều DBMS
```

Khi viết ứng dụng hỗ trợ nhiều DBMS, không đặt một chuỗi SQL UPDATE JOIN vào repository rồi kỳ vọng mọi driver thực thi được.

## 12. Cú pháp thay thế 1 — Correlated subquery

Khi DBMS không có UPDATE JOIN theo cú pháp mong muốn, correlated subquery là một lựa chọn:

```sql
UPDATE orders o
SET status = (
    SELECT s.new_status
    FROM shipment_updates s
    WHERE s.order_id = o.order_id
)
WHERE EXISTS (
    SELECT 1
    FROM shipment_updates s
    WHERE s.order_id = o.order_id
)
AND o.status = 'PENDING';
```

Nếu chỉ viết:

```sql
UPDATE orders o
SET status = (
    SELECT s.new_status
    FROM shipment_updates s
    WHERE s.order_id = o.order_id
);
```

thì target không có source match có thể nhận NULL từ scalar subquery. Nếu cột NOT NULL, statement có thể lỗi; nếu nullable, dữ liệu có thể bị xóa giá trị ngoài ý muốn. `WHERE EXISTS` giới hạn update vào target có source.

Scalar subquery được kỳ vọng trả tối đa một giá trị. Nếu trả nhiều dòng, các DBMS phổ biến thường báo lỗi thay vì chọn ngẫu nhiên một giá trị. Điều này hữu ích để phát hiện source không duy nhất.

PostgreSQL/Oracle hỗ trợ tuple assignment theo cú pháp riêng:

```sql
UPDATE orders o
SET (status, shipped_at) = (
    SELECT s.new_status, s.new_shipped_at
    FROM shipment_updates s
    WHERE s.order_id = o.order_id
)
WHERE EXISTS (
    SELECT 1
    FROM shipment_updates s
    WHERE s.order_id = o.order_id
);
```

Không giả định tuple assignment portable; các DBMS khác thường viết từng cột trong `SET` theo grammar riêng.

## 13. Cú pháp thay thế 2 — EXISTS và NOT EXISTS

`EXISTS` hỏi liệu subquery có ít nhất một dòng hay không. Nó phù hợp khi **giá trị source không cần được gán**, chỉ cần biết có match.

### 13.1. DELETE nếu có source match

```sql
DELETE FROM import_stage st
WHERE st.batch_id = 'BATCH-A'
  AND st.imported = TRUE
  AND EXISTS (
      SELECT 1
      FROM orders o
      WHERE o.order_id = st.order_id
        AND o.status IN ('SHIPPED', 'DELIVERED')
  );
```

Đây là cách diễn đạt khá portable.

### 13.2. DELETE nếu không có source match

```sql
DELETE FROM import_stage st
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.order_id = st.order_id
);
```

### 13.3. Vì sao NOT EXISTS thường an toàn hơn NOT IN?

```sql
DELETE FROM import_stage
WHERE order_id NOT IN (
    SELECT order_id FROM orders
);
```

Nếu subquery có một giá trị NULL, logic của `NOT IN` có thể trở thành UNKNOWN và không xóa dòng như mong đợi. `NOT EXISTS` diễn tả trực tiếp “không có dòng nào thỏa điều kiện” và tránh bẫy NULL của `NOT IN`.

### 13.4. NOT EXISTS không tự sửa dữ liệu sai

Nếu `import_stage.order_id` NULL, `NOT EXISTS` có thể đúng vì không có `o.order_id = NULL`. Nếu muốn xóa dòng thiếu ID, hãy viết rõ:

```sql
WHERE st.order_id IS NULL
   OR NOT EXISTS (...)
```

Nếu cột không được phép NULL, tốt hơn là đặt `NOT NULL` ngay từ schema.

## 14. Cú pháp thay thế 3 — CTE để làm rõ source

CTE (`WITH`) giúp tách bước tính source khỏi bước update/delete. Cú pháp DML kết hợp CTE khác nhau theo DBMS/phiên bản; ví dụ sau là PostgreSQL.

### 14.1. Tạo source đã tổng hợp

```sql
WITH totals AS (
    SELECT
        customer_id,
        SUM(total_amount) AS paid_total
    FROM orders
    WHERE status IN ('PAID', 'SHIPPED', 'DELIVERED')
    GROUP BY customer_id
)
UPDATE customers AS c
SET customer_tier =
    CASE
        WHEN t.paid_total >= 1000 THEN 'GOLD'
        WHEN t.paid_total >= 300 THEN 'SILVER'
        ELSE 'STANDARD'
    END
FROM totals AS t
WHERE t.customer_id = c.customer_id
RETURNING c.customer_id, c.customer_tier;
```

Ưu điểm:

- Logic source có tên và dễ đọc.
- Có thể kiểm tra riêng CTE bằng SELECT.
- Aggregate bảo đảm một dòng source mỗi customer.
- Dễ thêm điều kiện hoặc tính toán trước khi update.

CTE là cách tổ chức câu truy vấn, không mặc định tạo bảng tạm vật lý hoặc khóa dữ liệu. Muốn bảo đảm concurrency, cần chọn isolation/locking riêng.

### 14.2. CTE và DELETE

```sql
WITH old_rows AS (
    SELECT stage_id
    FROM import_stage
    WHERE batch_id = 'BATCH-A'
      AND imported = TRUE
)
DELETE FROM import_stage AS st
USING old_rows AS x
WHERE x.stage_id = st.stage_id
RETURNING st.stage_id;
```

Nếu mục tiêu chỉ là `DELETE WHERE EXISTS`, không cần thêm CTE cho phức tạp.

## 15. Cú pháp thay thế 4 — MERGE

`MERGE` kết hợp thao tác dựa trên quan hệ match giữa target và source. Tùy DBMS, nó có thể hỗ trợ UPDATE, INSERT và đôi khi DELETE trong cùng statement.

```text
Source ─────┐
            ├── MATCH với target
Target ─────┘
               │
       ┌───────┴────────┐
       ▼                ▼
    MATCHED          NOT MATCHED
       │                │
       ▼                ▼
     UPDATE           INSERT
```

### 15.1. PostgreSQL 15+

PostgreSQL hỗ trợ `MERGE` từ phiên bản 15:

```sql
MERGE INTO orders AS o
USING shipment_updates AS s
ON (o.order_id = s.order_id)
WHEN MATCHED AND o.status = 'PENDING' THEN
    UPDATE SET
        status = s.new_status,
        shipped_at = s.new_shipped_at,
        updated_at = CURRENT_TIMESTAMP;
```

### 15.2. SQL Server và Oracle

SQL Server và Oracle cũng hỗ trợ `MERGE`, nhưng grammar, giới hạn và hành vi đồng thời không giống hệt nhau. Đặc biệt, SQL Server `MERGE` cần được dùng thận trọng với concurrency, trigger và constraint; trong một số hệ thống, `UPDATE`/`INSERT` riêng với transaction rõ ràng dễ kiểm soát hơn.

### 15.3. MySQL

MySQL không có câu lệnh `MERGE INTO` tương đương đầy đủ theo cú pháp Oracle/SQL Server/PostgreSQL. Thường dùng:

```sql
INSERT ... ON DUPLICATE KEY UPDATE
```

cho upsert theo unique/primary key, hoặc UPDATE JOIN/INSERT riêng tùy nhu cầu.

### 15.4. MERGE không phải DELETE JOIN tổng quát

MERGE tập trung vào đồng bộ target với source. Khả năng delete chỉ có trong một số DBMS và thường bị giới hạn bởi điều kiện match/update. Nếu yêu cầu là “xóa target có source thỏa predicate”, `DELETE ... WHERE EXISTS` thường rõ hơn.

## 16. Một source match nhiều target hay một target match nhiều source?

Đây là vấn đề quan trọng nhất về tính đúng đắn.

### 16.1. Một source cập nhật nhiều target

Một dòng source có thể hợp lệ dùng để cập nhật nhiều dòng target, ví dụ một chương trình giảm giá áp dụng cho nhiều sản phẩm. Điều đó không sai nếu là quy tắc nghiệp vụ.

### 16.2. Nhiều source cùng khớp một target

Ví dụ:

```text
orders
order_id = 1001

shipment_updates
order_id = 1001, new_status = SHIPPED
order_id = 1001, new_status = DELIVERED
```

Nếu UPDATE cần gán `status` từ source, có hai giá trị ứng viên. Kết quả có thể không xác định hoặc câu lệnh có thể lỗi tùy DBMS.

| DBMS/cú pháp | Nhiều source match một target |
|---|---|
| PostgreSQL `UPDATE FROM` | Một source row được dùng nhưng không bảo đảm row nào |
| SQLite `UPDATE FROM` | Chọn một source row tùy ý |
| SQL Server `UPDATE FROM` | Kết quả không xác định nếu có nhiều giá trị source cho cột cập nhật |
| Oracle scalar subquery | Thường lỗi nếu subquery trả nhiều dòng |
| MySQL UPDATE JOIN | Target row được cập nhật một lần; không dựa vào source match bất kỳ để quyết định giá trị |

Kết luận thực tế: **đừng viết logic phụ thuộc vào việc database tình cờ chọn một source row**.

### 16.3. Ràng buộc unique nếu nghiệp vụ yêu cầu một-một

```sql
ALTER TABLE shipment_updates
ADD CONSTRAINT pk_shipment_updates
PRIMARY KEY (order_id);
```

Nếu lịch sử cần nhiều shipment event trên một đơn, không thể dùng `order_id` làm unique. Khi đó cần chọn đúng **một event đại diện**.

### 16.4. Chọn source mới nhất bằng ROW_NUMBER

Giả sử có bảng:

```sql
shipment_history (
    shipment_event_id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    new_status VARCHAR(20) NOT NULL,
    event_time TIMESTAMP NOT NULL
)
```

Tạo source một dòng mỗi order:

```sql
WITH ranked AS (
    SELECT
        h.order_id,
        h.new_status,
        h.event_time,
        ROW_NUMBER() OVER (
            PARTITION BY h.order_id
            ORDER BY h.event_time DESC, h.shipment_event_id DESC
        ) AS rn
    FROM shipment_history AS h
),
latest AS (
    SELECT order_id, new_status, event_time
    FROM ranked
    WHERE rn = 1
)
UPDATE orders AS o
SET
    status = l.new_status,
    shipped_at = l.event_time
FROM latest AS l
WHERE l.order_id = o.order_id;
```

Đây là cú pháp PostgreSQL. `ROW_NUMBER` có trên nhiều DBMS hiện đại, nhưng phần CTE+DML cần chuyển theo hệ quản trị. `ORDER BY event_time DESC, shipment_event_id DESC` có tie-breaker để khi hai event cùng thời điểm, vẫn có thứ tự xác định.

### 16.5. Aggregate source khi cần tổng hợp

```sql
WITH item_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS total_amount
    FROM order_items
    GROUP BY order_id
)
UPDATE orders AS o
SET total_amount = t.total_amount
FROM item_totals AS t
WHERE t.order_id = o.order_id;
```

`GROUP BY order_id` bảo đảm một dòng source cho mỗi order.

## 17. INNER JOIN, LEFT JOIN và NULL trong UPDATE

Loại join quyết định dòng target nào được xét.

### 17.1. INNER JOIN

Chỉ target có source match mới được cập nhật:

```sql
-- MySQL
UPDATE orders o
JOIN shipment_updates s ON s.order_id = o.order_id
SET o.status = s.new_status;
```

### 17.2. LEFT JOIN

Giữ target dù không có source. Các cột source trở thành NULL:

```sql
-- MySQL
UPDATE orders o
LEFT JOIN shipment_updates s ON s.order_id = o.order_id
SET o.shipped_at = s.new_shipped_at;
```

Điều này có thể ghi NULL vào target. Nếu muốn chỉ cập nhật khi source có:

```sql
WHERE s.order_id IS NOT NULL
```

Khi thêm điều kiện này, kết quả về tập target gần với inner join.

### 17.3. COALESCE không phải lúc nào cũng đúng

```sql
SET o.shipped_at = COALESCE(s.new_shipped_at, o.shipped_at)
```

giữ thời gian cũ khi source không có giá trị. Nhưng có thể không cho phép xóa thời gian có chủ đích. Phải phân biệt:

- Không có source row.
- Có source row nhưng `new_shipped_at` là NULL.
- Có source row với timestamp thật.

Nếu ba trạng thái cần khác nhau, hãy kiểm tra sự tồn tại của source riêng.

### 17.4. Tránh điều kiện sai với nullable source key

Khi dùng anti-join:

```sql
LEFT JOIN source s ON ...
WHERE s.some_column IS NULL
```

chỉ an toàn nếu `some_column` không thể NULL trên dòng match. Ưu tiên kiểm tra primary key của source.

## 18. DELETE JOIN và khóa ngoại

Xóa target có thể bị ngăn bởi foreign key. Ví dụ:

```text
orders(order_id PRIMARY KEY)
order_items(order_id REFERENCES orders(order_id))
```

Nếu xóa `orders` trong khi vẫn còn `order_items`, database có thể trả lỗi FK.

### 18.1. Không dùng DELETE JOIN để bỏ qua quan hệ dữ liệu

```sql
DELETE o
FROM orders AS o
JOIN shipment_updates AS s
    ON s.order_id = o.order_id;
```

Nếu `order_items` tham chiếu các đơn đó, xóa có thể thất bại. Tùy schema, cần:

- Xóa child trước rồi parent trong cùng transaction.
- Dùng `ON DELETE CASCADE` nếu nghiệp vụ thật sự muốn xóa dây chuyền.
- Không xóa bản ghi chính mà chuyển sang soft delete.

### 18.2. ON DELETE CASCADE

```sql
FOREIGN KEY (order_id)
REFERENCES orders(order_id)
ON DELETE CASCADE
```

Khi xóa parent, child được database xóa theo. Đây là hành vi mạnh; không bật cascade chỉ để làm cho câu DELETE JOIN chạy được.

### 18.3. Soft delete

Thay vì xóa vật lý:

```sql
UPDATE orders
SET deleted_at = CURRENT_TIMESTAMP,
    status = 'CANCELLED'
WHERE order_id = 1001;
```

Soft delete giữ lịch sử và các quan hệ. Nhưng mọi query đọc phải lọc đúng `deleted_at IS NULL`, và cần chính sách retention/ẩn dữ liệu rõ.

### 18.4. Xóa dữ liệu theo retention

```sql
DELETE FROM import_stage
WHERE imported = TRUE
  AND created_at < TIMESTAMP '2026-01-01 00:00:00';
```

Nếu bảng rất lớn, nên xóa theo batch/partition hoặc retention partition thay vì một câu DELETE khổng lồ.

## 19. Transaction và khóa khi UPDATE/DELETE JOIN

UPDATE/DELETE là thao tác ghi; database phải bảo vệ dòng được thay đổi theo isolation và locking rules của DBMS.

### 19.1. Preview và thực thi trong transaction

PostgreSQL:

```sql
BEGIN;

SELECT
    o.order_id,
    o.status AS old_status,
    s.new_status
FROM orders AS o
JOIN shipment_updates AS s
    ON s.order_id = o.order_id
WHERE o.status = 'PENDING'
ORDER BY o.order_id;

UPDATE orders AS o
SET status = s.new_status,
    updated_at = CURRENT_TIMESTAMP
FROM shipment_updates AS s
WHERE s.order_id = o.order_id
  AND o.status = 'PENDING'
RETURNING o.order_id, o.status;

-- Kiểm tra kết quả.
-- Nếu sai: ROLLBACK;
-- Nếu đúng: COMMIT;
```

Transaction giúp preview và thay đổi nằm trong cùng phạm vi transaction, nhưng ở `READ COMMITTED`, câu SELECT và UPDATE vẫn có thể nhìn snapshot khác nhau. Nếu cần invariant mạnh hơn, cân nhắc khóa/isolation hoặc điều kiện update nguyên tử.

### 19.2. SQL Server

```sql
BEGIN TRANSACTION;

UPDATE o
SET status = s.new_status
FROM dbo.orders AS o
JOIN dbo.shipment_updates AS s
    ON s.order_id = o.order_id
WHERE o.status = 'PENDING';

SELECT @@ROWCOUNT AS affected_rows;

-- COMMIT TRANSACTION;
-- ROLLBACK TRANSACTION;
```

### 19.3. MySQL/InnoDB

```sql
START TRANSACTION;

UPDATE orders AS o
JOIN shipment_updates AS s
    ON s.order_id = o.order_id
SET o.status = s.new_status
WHERE o.status = 'PENDING';

SELECT ROW_COUNT() AS affected_rows;

-- COMMIT;
-- ROLLBACK;
```

### 19.4. SQLite

```sql
BEGIN;

UPDATE orders AS o
SET status = s.new_status
FROM shipment_updates AS s
WHERE s.order_id = o.order_id
  AND o.status = 'PENDING';

-- Kiểm tra changes() hoặc kết quả ứng dụng.
-- COMMIT;
-- ROLLBACK;
```

SQLite có mô hình khóa ghi riêng; không giả định concurrency behavior giống PostgreSQL/MySQL.

### 19.5. Oracle

```sql
SAVEPOINT before_sync;

MERGE INTO orders o
USING shipment_updates s
ON (o.order_id = s.order_id)
WHEN MATCHED THEN
    UPDATE SET o.status = s.new_status;

-- COMMIT;
-- ROLLBACK TO before_sync;
```

Oracle transaction bắt đầu ngầm khi chạy DML; `SAVEPOINT` có thể tạo điểm quay lui.

## 20. Kiểm tra số dòng bị ảnh hưởng

Sau DML, cần so sánh số dòng thực tế với kỳ vọng.

| DBMS | Cách phổ biến |
|---|---|
| MySQL | JDBC `executeUpdate()`, SQL `ROW_COUNT()` |
| SQL Server | JDBC update count, `@@ROWCOUNT`, `OUTPUT` |
| PostgreSQL | JDBC update count, `RETURNING` |
| SQLite | JDBC update count, `changes()` hoặc `RETURNING` theo phiên bản |
| Oracle | JDBC update count, `SQL%ROWCOUNT` trong PL/SQL |

### 20.1. Update count bằng 0 có thể có nhiều nghĩa

- Không có target row.
- Không có source match.
- Target có source nhưng không thỏa filter trạng thái.
- Dữ liệu đã được cập nhật trước đó.

Đừng luôn trả “database lỗi” khi count bằng 0. Hãy định nghĩa rõ API muốn coi đó là not found, no-op hay concurrency conflict.

### 20.2. Update count lớn hơn kỳ vọng

Nếu dự kiến 3 đơn mà cập nhật 30.000 dòng:

- Không commit vội.
- Kiểm tra join key và filter.
- Rollback nếu còn trong transaction.
- Xem xét thiếu tenant ID, điều kiện ngày hoặc status.

### 20.3. Update count không nhất thiết là số giá trị thực sự đổi

Một số driver/DBMS đếm dòng match; một số cấu hình có thể phân biệt dòng thực sự thay đổi. Nếu gán giá trị cũ bằng giá trị mới, update count có thể không giống điều ứng dụng suy đoán. Xem tài liệu driver và không dùng row count như phép so sánh giá trị.

## 21. UPDATE JOIN với dữ liệu lịch sử: chọn đúng dòng mới nhất

Một bảng lịch sử vận chuyển có thể có nhiều event:

```text
shipment_history
┌───────────────────┬──────────┬────────────┬─────────────────────┐
│ shipment_event_id │ order_id │ new_status │ event_time          │
├───────────────────┼──────────┼────────────┼─────────────────────┤
│ 1                 │ 1001     │ SHIPPED    │ 2026-11-10 09:00:00 │
│ 2                 │ 1001     │ DELIVERED  │ 2026-11-11 12:00:00 │
│ 3                 │ 1002     │ SHIPPED    │ 2026-11-12 08:00:00 │
└───────────────────┴──────────┴────────────┴─────────────────────┘
```

Không thể nối thẳng `orders` với `shipment_history` rồi lấy `new_status` nếu cần trạng thái mới nhất. Hãy định nghĩa “mới nhất” bằng timestamp và tie-breaker.

### 21.1. Window function

```sql
WITH ranked AS (
    SELECT
        shipment_event_id,
        order_id,
        new_status,
        event_time,
        ROW_NUMBER() OVER (
            PARTITION BY order_id
            ORDER BY event_time DESC, shipment_event_id DESC
        ) AS rn
    FROM shipment_history
),
latest AS (
    SELECT order_id, new_status, event_time
    FROM ranked
    WHERE rn = 1
)
UPDATE orders AS o
SET status = l.new_status,
    shipped_at = l.event_time
FROM latest AS l
WHERE l.order_id = o.order_id;
```

Đây là cú pháp PostgreSQL. `ROW_NUMBER` có trên nhiều DBMS hiện đại, nhưng phần CTE+DML cần chuyển cú pháp ngoài theo hệ quản trị.

### 21.2. Oracle

```sql
MERGE INTO orders o
USING (
    SELECT order_id, new_status, event_time
    FROM (
        SELECT
            h.order_id,
            h.new_status,
            h.event_time,
            ROW_NUMBER() OVER (
                PARTITION BY h.order_id
                ORDER BY h.event_time DESC,
                         h.shipment_event_id DESC
            ) AS rn
        FROM shipment_history h
    )
    WHERE rn = 1
) latest
ON (latest.order_id = o.order_id)
WHEN MATCHED THEN
    UPDATE SET
        o.status = latest.new_status,
        o.shipped_at = latest.event_time;
```

Tie-breaker là cần thiết nếu timestamp có thể trùng; nếu chỉ `ORDER BY event_time DESC`, thứ tự giữa các event cùng thời điểm không được xác định.

## 22. UPDATE JOIN với aggregate và dữ liệu chi tiết

Ví dụ tính tổng dòng hàng rồi cập nhật tổng đơn:

```sql
WITH totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS calculated_total
    FROM order_items
    GROUP BY order_id
)
UPDATE orders AS o
SET total_amount = t.calculated_total
FROM totals AS t
WHERE t.order_id = o.order_id;
```

### 22.1. Vì sao aggregate trước?

Nếu một đơn có 5 item, join sẽ tạo 5 dòng kết hợp cho một đơn. Aggregate source trước giúp có một dòng `calculated_total` cho mỗi order.

### 22.2. Đơn không có item

`INNER JOIN` với `totals` chỉ cập nhật đơn có ít nhất một item. Nếu muốn đặt total về 0 cho đơn không có item, cần diễn đạt rõ bằng correlated subquery:

```sql
UPDATE orders AS o
SET total_amount = COALESCE((
    SELECT SUM(i.quantity * i.unit_price)
    FROM order_items AS i
    WHERE i.order_id = o.order_id
), 0);
```

`SUM` trên tập rỗng trả NULL, nên `COALESCE(...,0)` đặt total bằng 0. Chỉ làm vậy nếu quy tắc nghiệp vụ xác định đơn không item có total bằng 0.

## 23. Xóa dữ liệu trùng lặp bằng DELETE dựa trên EXISTS

Một bảng import có thể có dữ liệu trùng:

```text
customer_import
┌─────────┬───────────┬─────────────────────┐
│ row_id  │ email     │ imported_at         │
├─────────┼───────────┼─────────────────────┤
│ 1       │ a@x.test  │ 2026-11-01 09:00:00 │
│ 2       │ a@x.test  │ 2026-11-02 09:00:00 │
│ 3       │ b@x.test  │ 2026-11-01 10:00:00 │
└─────────┴───────────┴─────────────────────┘
```

Muốn giữ dòng mới nhất theo `imported_at`, chọn các dòng cũ hơn để xóa.

### 23.1. Preview

```sql
SELECT old.row_id, old.email, old.imported_at
FROM customer_import AS old
WHERE EXISTS (
    SELECT 1
    FROM customer_import AS newer
    WHERE newer.email = old.email
      AND (
          newer.imported_at > old.imported_at
          OR (
              newer.imported_at = old.imported_at
              AND newer.row_id > old.row_id
          )
      )
);
```

### 23.2. DELETE

```sql
DELETE FROM customer_import AS old
WHERE EXISTS (
    SELECT 1
    FROM customer_import AS newer
    WHERE newer.email = old.email
      AND (
          newer.imported_at > old.imported_at
          OR (
              newer.imported_at = old.imported_at
              AND newer.row_id > old.row_id
          )
      )
);
```

Đây là cách diễn đạt tương đối portable. Nó giữ dòng có timestamp mới nhất; nếu timestamp bằng nhau thì giữ `row_id` lớn hơn.

Nếu `email` nullable, phép `newer.email = old.email` không match hai giá trị NULL. Cần quyết định NULL có được coi là cùng nhóm không. Có thể dùng `IS NOT DISTINCT FROM` ở DBMS hỗ trợ hoặc viết:

```sql
newer.email = old.email
OR (newer.email IS NULL AND old.email IS NULL)
```

Nếu email bắt buộc, tốt hơn là `NOT NULL` và unique constraint sau khi đã dọn dữ liệu.

## 24. Cú pháp DELETE theo anti-join

Để xóa các dòng không có bản ghi cha:

```sql
DELETE FROM import_stage AS st
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.order_id = st.order_id
);
```

Trong MySQL/SQL Server, có thể dùng:

```sql
DELETE st
FROM import_stage AS st
LEFT JOIN orders AS o
    ON o.order_id = st.order_id
WHERE o.order_id IS NULL;
```

Đây là anti-join. Chọn cột kiểm tra là primary key `order_id`, không phải cột nullable.

## 25. Index cho UPDATE JOIN và DELETE JOIN

Join DML có thể phải đọc nhiều dòng source và target. Index phù hợp giúp tìm match hiệu quả.

### 25.1. Index join key

```sql
CREATE INDEX idx_shipment_updates_order
    ON shipment_updates(order_id);
```

Nếu `order_id` đã là primary key, index thường đã tồn tại; không tạo index trùng lặp không cần thiết.

### 25.2. Index trên filter

```sql
CREATE INDEX idx_orders_status
    ON orders(status);

CREATE INDEX idx_import_stage_batch_imported
    ON import_stage(batch_id, imported);
```

Thứ tự cột cần cân nhắc theo predicate, selectivity và workload. Không phải cứ đưa mọi cột WHERE vào một index là tốt.

### 25.3. Index cho lịch sử

```sql
CREATE INDEX idx_shipment_history_order_time
    ON shipment_history(order_id, event_time DESC, shipment_event_id DESC);
```

Có thể hỗ trợ truy vấn lấy event mới nhất theo order, tùy plan và DBMS.

### 25.4. Index làm tăng chi phí ghi

UPDATE/DELETE phải cập nhật index liên quan; index quá nhiều có thể làm DML chậm và tăng storage/WAL/redo. Tạo index theo truy vấn thực và kiểm tra execution plan.

### 25.5. Xem execution plan

PostgreSQL:

```sql
EXPLAIN
UPDATE orders AS o
SET status = s.new_status
FROM shipment_updates AS s
WHERE s.order_id = o.order_id
  AND o.status = 'PENDING';
```

Không chạy `EXPLAIN ANALYZE` trên DML production chỉ để xem plan: `ANALYZE` thực sự **thực thi** statement. Nếu cần đo trên dữ liệu thử, dùng transaction rollback và hiểu side effect/trigger.

SQL Server dùng execution plan/`SET SHOWPLAN...` hoặc công cụ tương ứng; MySQL có `EXPLAIN` với khả năng DML phụ thuộc version; SQLite dùng `EXPLAIN QUERY PLAN` cho truy vấn phù hợp. Cú pháp không giống nhau.

## 26. UPDATE/DELETE JOIN trên bảng lớn

Một câu DML ảnh hưởng hàng triệu dòng có thể:

- Giữ row lock lâu.
- Tạo lượng WAL/redo lớn.
- Làm transaction log tăng.
- Gây replication lag.
- Tạo vacuum/undo pressure.
- Chặn request khác.
- Làm rollback tốn thời gian nếu phát hiện sai.

### 26.1. Chia batch trong PostgreSQL

```sql
WITH batch AS (
    SELECT o.order_id
    FROM orders AS o
    JOIN shipment_updates AS s
        ON s.order_id = o.order_id
    WHERE o.status = 'PENDING'
    ORDER BY o.order_id
    LIMIT 500
    FOR UPDATE OF o SKIP LOCKED
)
UPDATE orders AS o
SET status = s.new_status,
    updated_at = CURRENT_TIMESTAMP
FROM batch AS b
JOIN shipment_updates AS s
    ON s.order_id = b.order_id
WHERE o.order_id = b.order_id
RETURNING o.order_id;
```

Worker có thể lặp lại đến khi không còn dòng. Đây là ví dụ PostgreSQL, cần transaction phù hợp; `SKIP LOCKED` giúp nhiều worker tránh chờ trên dòng đã được worker khác khóa.

### 26.2. DELETE theo batch trong PostgreSQL

```sql
WITH batch AS (
    SELECT st.stage_id
    FROM import_stage AS st
    WHERE st.batch_id = 'BATCH-A'
      AND st.imported = TRUE
    ORDER BY st.stage_id
    LIMIT 500
    FOR UPDATE SKIP LOCKED
)
DELETE FROM import_stage AS st
USING batch AS b
WHERE st.stage_id = b.stage_id
RETURNING st.stage_id;
```

### 26.3. Batch không tự bảo đảm không bỏ sót

Nếu điều kiện lọc thay đổi giữa các batch hoặc có dòng mới được thêm, cần quy tắc xác định phạm vi: batch ID cố định, mốc thời gian/ID tối đa, trạng thái chuyển đổi có điều kiện, checkpoint và idempotency.

### 26.4. Không commit mỗi dòng nếu không cần

Commit từng dòng làm tăng round-trip và transaction overhead. Nhưng transaction khổng lồ cũng có chi phí. Chọn kích thước batch theo throughput, rollback cost, lock duration và yêu cầu atomicity.

## 27. PreparedStatement và SQL injection

Giá trị điều kiện nên truyền bằng parameter:

```java
String sql = """
    UPDATE orders AS o
    SET status = s.new_status
    FROM shipment_updates AS s
    WHERE s.order_id = o.order_id
      AND o.status = ?
      AND o.customer_id = ?
    """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, "PENDING");
    statement.setLong(2, customerId);
    int updated = statement.executeUpdate();
}
```

Đây là cú pháp PostgreSQL. Tham số hóa bảo vệ **giá trị**; nó không thể thay tên bảng/cột hoặc từ khóa SQL. Nếu ứng dụng cho phép chọn cột sort hoặc tên bảng động, hãy whitelist identifier theo danh sách cố định, không nối chuỗi tùy ý từ người dùng.

PreparedStatement không tự làm câu UPDATE an toàn về mặt nghiệp vụ. Vẫn phải xác định đúng join key, tenant, status và row count.

## 28. Quy trình chạy DML an toàn

1. Xác định target và source.
2. Kiểm tra source có unique/aggregate theo target key chưa.
3. Viết SELECT preview với cùng join/filter.
4. Kiểm tra số dòng và mẫu dữ liệu.
5. Kiểm tra FK, trigger, cascade và side effect.
6. Mở transaction hoặc dùng batch phù hợp.
7. Chạy DML có điều kiện đủ hẹp.
8. Kiểm tra update count/`RETURNING`/`OUTPUT`.
9. Nếu lệch kỳ vọng, rollback; nếu đúng, commit.
10. Ghi audit/metrics và theo dõi lock/replication/transaction log.

Preview SELECT không ngăn transaction khác thay đổi dòng sau đó. Nếu điều kiện cần ổn định, hãy dùng transaction isolation, row lock, version check hoặc viết điều kiện nguyên tử trong DML.

Với delete hàng loạt, cần biết có thể phục hồi từ backup/PITR không, có audit/bản sao staging không, có thể soft-delete trước không và có thể xóa theo batch để kiểm tra từng đợt không.

## 29. So sánh các phương án thay thế

| Nhu cầu | Cách thường phù hợp | Lưu ý |
|---|---|---|
| Cập nhật target từ một dòng source | UPDATE JOIN/FROM | Bảo đảm một source cho mỗi target |
| Chỉ cần biết có source match | `EXISTS` | Không cần join để lấy cột |
| Xóa target có source match | DELETE JOIN/USING hoặc `EXISTS` | Chọn đúng target |
| Xóa target không có source | `NOT EXISTS` | Tránh bẫy NULL của `NOT IN` |
| Source có nhiều dòng cần tổng hợp | Aggregate subquery/CTE | `GROUP BY` theo target key |
| Chọn source mới nhất | `ROW_NUMBER()`/subquery | Có tie-breaker |
| Upsert source vào target | `MERGE` hoặc DB-specific upsert | Khác biệt lớn giữa DBMS |
| Chỉ cập nhật một bảng theo điều kiện | UPDATE với `WHERE EXISTS` | Dễ portable |
| Xóa theo retention | DELETE theo range/batch/partition | Cân nhắc log và lock |
| Xóa mềm, cần lịch sử | UPDATE `deleted_at` | Query đọc phải lọc đúng |

### 29.1. Khi nào nên chọn EXISTS thay vì JOIN?

Nếu không cần lấy cột source mà chỉ muốn kiểm tra điều kiện tồn tại:

```sql
UPDATE orders AS o
SET status = 'READY'
WHERE o.status = 'PENDING'
  AND EXISTS (
      SELECT 1
      FROM shipment_updates AS s
      WHERE s.order_id = o.order_id
  );
```

Đây là cách thể hiện ý định rõ: “cập nhật đơn có ít nhất một shipment update”. Nhiều optimizer chuyển EXISTS thành semi-join hiệu quả.

### 29.2. Khi nào correlated subquery phù hợp?

Khi cần gán một hoặc vài scalar source và muốn database báo lỗi nếu source có nhiều dòng. Phải đảm bảo `WHERE EXISTS` để target không match không bị gán NULL ngoài ý muốn.

### 29.3. Khi nào MERGE phù hợp?

Khi nghiệp vụ thực sự là đồng bộ/upsert theo match condition và DBMS hỗ trợ phiên bản/semantics phù hợp. Không dùng MERGE chỉ vì nó có vẻ “mạnh hơn UPDATE”.

## 30. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng cú pháp MySQL trên PostgreSQL | Syntax error | Chuyển sang `UPDATE ... FROM` |
| Dùng `DELETE t FROM` trên PostgreSQL | Syntax error | Dùng `DELETE FROM t USING ...` |
| Dùng `DELETE JOIN` trên SQLite/Oracle | Không có grammar tương ứng | Dùng `EXISTS` |
| Nhầm target alias | Xóa/cập nhật nhầm bảng | Đọc alias target ngay sau UPDATE/DELETE |
| Thiếu điều kiện join đầy đủ | Cập nhật nhiều dòng sai | Dùng khóa duy nhất/tenant key |
| Nhiều source match một target | Giá trị source không xác định hoặc lỗi | Aggregate, unique key, ROW_NUMBER |
| Dùng LEFT JOIN rồi gán NULL | Xóa giá trị target ngoài ý muốn | Kiểm tra source tồn tại hoặc policy NULL |
| Dùng cột nullable để phát hiện no match | Nhận nhầm dòng có match | Kiểm tra PK source |
| Dùng NOT IN có NULL | Không xóa như mong đợi | `NOT EXISTS` |
| Xóa parent khi còn child | FK violation | Xóa child, cascade có chủ đích hoặc soft delete |
| Không preview | Không biết phạm vi thay đổi | SELECT cùng join/filter trước |
| Nghĩ SELECT preview khóa dòng | Dữ liệu có thể đổi trước DML | Transaction/locking/version |
| Không kiểm tra update count | Bỏ sót/no-op hoặc tác động quá rộng | So với kỳ vọng |
| Gán cùng giá trị rồi hiểu row count là “đã đổi” | Sai diễn giải count | Kiểm tra semantics driver/DBMS |
| UPDATE hàng triệu dòng trong một transaction | Lock/log/replication pressure | Batch hoặc partition |
| Dùng MERGE như cú pháp portable | Lỗi syntax/semantics | Viết adapter theo DBMS |
| Dùng MERGE mà source duplicate | Duplicate/ambiguous match | Chuẩn hóa source |
| Dùng CTE nghĩ dữ liệu tự khóa | Race vẫn có thể xảy ra | Chọn isolation/locking riêng |
| Dùng parameter cho tên cột | Không hoạt động | Whitelist identifier |
| Dùng ON DELETE CASCADE chỉ để né lỗi | Xóa dây chuyền ngoài ý muốn | Thiết kế FK theo nghiệp vụ |

## 31. Bài tập tự luyện

Các bài tập dùng schema `customers`, `orders`, `shipment_updates`, `import_stage` ở mục 3. Chạy các câu SQL trên database test tương ứng; không chạy DELETE/UPDATE mẫu trên production.

### Bài 1 — Xác định target

Trong yêu cầu “cập nhật `orders.status` theo `shipment_updates.new_status`”, bảng nào là target, bảng nào là source? Join key là gì?

### Bài 2 — UPDATE JOIN MySQL

Viết câu MySQL cập nhật trạng thái và `shipped_at` cho các đơn đang `PENDING`, dựa trên `shipment_updates`.

### Bài 3 — UPDATE FROM SQL Server

Viết lại bài 2 bằng SQL Server, dùng alias `o` và `s`. Thêm `OUTPUT` để trả ID và trạng thái cũ/mới.

### Bài 4 — UPDATE FROM PostgreSQL

Viết lại bài 2 bằng PostgreSQL và dùng `RETURNING` trả các dòng đã cập nhật.

### Bài 5 — UPDATE FROM SQLite

Viết câu SQLite 3.33+ tương ứng. Khác biệt chính của vị trí source table trong cú pháp là gì?

### Bài 6 — Oracle correlated UPDATE

Viết câu Oracle cập nhật `status`, `shipped_at` bằng scalar subquery. Vì sao cần `WHERE EXISTS`?

### Bài 7 — Oracle MERGE

Viết `MERGE INTO orders` từ `shipment_updates` để cập nhật các đơn match và đang `PENDING`.

### Bài 8 — DELETE JOIN MySQL

Viết câu xóa staging rows của `BATCH-A` đã import và có đơn ở trạng thái `SHIPPED` hoặc `DELIVERED`.

### Bài 9 — DELETE JOIN SQL Server

Viết câu tương ứng cho SQL Server. Alias nào là target?

### Bài 10 — DELETE USING PostgreSQL

Viết câu tương ứng cho PostgreSQL và thêm `RETURNING stage_id`.

### Bài 11 — DELETE EXISTS SQLite/Oracle

Viết cách thay thế bằng `DELETE ... WHERE EXISTS`.

### Bài 12 — Anti-join

Xóa staging rows không có order tương ứng bằng `NOT EXISTS`. Vì sao cách này thường an toàn hơn `NOT IN`?

### Bài 13 — Source duplicate

Nếu `shipment_updates` có hai dòng cùng `order_id=1001` nhưng `new_status` khác nhau, điều gì có thể xảy ra trong UPDATE FROM PostgreSQL? Đề xuất hai cách xử lý.

### Bài 14 — Aggregate source

Viết CTE tính tổng `order_items.quantity * unit_price` theo `order_id`, rồi cập nhật `orders.total_amount` bằng PostgreSQL.

### Bài 15 — LEFT JOIN và NULL

Trong MySQL, viết UPDATE dùng LEFT JOIN nhưng chỉ giữ `shipped_at` cũ khi source không có timestamp. Khi nào `COALESCE` không đúng nghiệp vụ?

### Bài 16 — Multi-table UPDATE MySQL

Viết câu MySQL cập nhật cả `orders.status` và `shipment_updates.received_at`. Vì sao không nên giả định cú pháp này portable?

### Bài 17 — SQL Server OUTPUT

Giải thích `deleted.status` và `inserted.status` trong `OUTPUT` của UPDATE.

### Bài 18 — PostgreSQL RETURNING

`RETURNING` có thể trả những gì sau UPDATE/DELETE? Nó có tự commit transaction không?

### Bài 19 — CHECK preview

Viết SELECT preview chính xác các dòng sẽ bị xóa từ `import_stage` theo `BATCH-A`, `imported=TRUE` và order đã giao. Sau đó viết DELETE PostgreSQL.

### Bài 20 — NOT IN và NULL

Giải thích tại sao một NULL trong subquery có thể khiến `NOT IN` không trả dòng nào như dự kiến.

### Bài 21 — Oracle scalar subquery

Điều gì xảy ra nếu scalar subquery của Oracle trả hai dòng cho một target? Làm sao bảo đảm source một dòng?

### Bài 22 — ROW_NUMBER

Viết truy vấn lấy shipment event mới nhất theo từng order bằng `ROW_NUMBER()`. Vì sao cần tie-breaker?

### Bài 23 — Cú pháp MERGE

Nêu những DBMS trong bài có `MERGE` và vì sao MySQL không dùng cùng cú pháp `MERGE INTO` như Oracle/PostgreSQL.

### Bài 24 — Foreign key

Xóa một order có `order_items` tham chiếu. Nêu ba cách xử lý và rủi ro của `ON DELETE CASCADE`.

### Bài 25 — Row count

Một câu UPDATE dự kiến 3 dòng nhưng JDBC trả update count 30.000. Bạn làm gì trước khi commit?

### Bài 26 — Concurrency

Vì sao SELECT preview trước UPDATE không ngăn transaction khác sửa dữ liệu? Nêu các cơ chế bảo vệ.

### Bài 27 — Batch DML

Một DELETE cần xóa 10 triệu staging rows. Nêu lợi ích và rủi ro khi chia batch 500 dòng/transaction.

### Bài 28 — Chọn cú pháp

Ghép mỗi DBMS với cú pháp phù hợp:

| DBMS | Cú pháp |
|---|---|
| MySQL | ? |
| SQL Server | ? |
| PostgreSQL | ? |
| SQLite | ? |
| Oracle | ? |

<details>
<summary>Gợi ý đáp án và lời giải</summary>

**Bài 1:** `orders` là target; `shipment_updates` là source; join key `order_id`.

**Bài 2 — MySQL:**

```sql
UPDATE orders AS o
JOIN shipment_updates AS s
    ON s.order_id = o.order_id
SET
    o.status = s.new_status,
    o.shipped_at = s.new_shipped_at,
    o.updated_at = CURRENT_TIMESTAMP
WHERE o.status = 'PENDING';
```

**Bài 3 — SQL Server:**

```sql
UPDATE o
SET
    status = s.new_status,
    shipped_at = s.new_shipped_at,
    updated_at = SYSUTCDATETIME()
OUTPUT
    inserted.order_id,
    deleted.status AS old_status,
    inserted.status AS new_status
FROM dbo.orders AS o
JOIN dbo.shipment_updates AS s
    ON s.order_id = o.order_id
WHERE o.status = 'PENDING';
```

`o` là target; `deleted` là giá trị trước và `inserted` là giá trị sau update.

**Bài 4 — PostgreSQL:**

```sql
UPDATE orders AS o
SET status = s.new_status,
    shipped_at = s.new_shipped_at,
    updated_at = CURRENT_TIMESTAMP
FROM shipment_updates AS s
WHERE s.order_id = o.order_id
  AND o.status = 'PENDING'
RETURNING o.order_id, o.status, o.shipped_at;
```

**Bài 5 — SQLite 3.33+:**

```sql
UPDATE orders AS o
SET status = s.new_status,
    shipped_at = s.new_shipped_at,
    updated_at = CURRENT_TIMESTAMP
FROM shipment_updates AS s
WHERE s.order_id = o.order_id
  AND o.status = 'PENDING';
```

Target nằm sau `UPDATE`; source nằm trong `FROM`.

**Bài 6 — Oracle:**

```sql
UPDATE orders o
SET (status, shipped_at) = (
    SELECT s.new_status, s.new_shipped_at
    FROM shipment_updates s
    WHERE s.order_id = o.order_id
)
WHERE o.status = 'PENDING'
  AND EXISTS (
      SELECT 1 FROM shipment_updates s
      WHERE s.order_id = o.order_id
  );
```

`EXISTS` ngăn target không match bị scalar subquery trả NULL và ghi đè cột.

**Bài 7 — Oracle MERGE:**

```sql
MERGE INTO orders o
USING shipment_updates s
ON (o.order_id = s.order_id)
WHEN MATCHED THEN
    UPDATE SET
        o.status = s.new_status,
        o.shipped_at = s.new_shipped_at
    WHERE o.status = 'PENDING';
```

**Bài 8 — MySQL:**

```sql
DELETE st
FROM import_stage AS st
JOIN orders AS o
    ON o.order_id = st.order_id
WHERE st.batch_id = 'BATCH-A'
  AND st.imported = TRUE
  AND o.status IN ('SHIPPED', 'DELIVERED');
```

**Bài 9 — SQL Server:**

```sql
DELETE st
FROM dbo.import_stage AS st
JOIN dbo.orders AS o
    ON o.order_id = st.order_id
WHERE st.batch_id = 'BATCH-A'
  AND st.imported = 1
  AND o.status IN ('SHIPPED', 'DELIVERED');
```

`st` là target bị xóa.

**Bài 10 — PostgreSQL:**

```sql
DELETE FROM import_stage AS st
USING orders AS o
WHERE o.order_id = st.order_id
  AND st.batch_id = 'BATCH-A'
  AND st.imported = TRUE
  AND o.status IN ('SHIPPED', 'DELIVERED')
RETURNING st.stage_id;
```

**Bài 11 — SQLite/Oracle:**

```sql
DELETE FROM import_stage st
WHERE st.batch_id = 'BATCH-A'
  AND st.imported = 1
  AND EXISTS (
      SELECT 1
      FROM orders o
      WHERE o.order_id = st.order_id
        AND o.status IN ('SHIPPED', 'DELIVERED')
  );
```

**Bài 12:** `NOT EXISTS` diễn đạt không có dòng match. `NOT IN` với một NULL trong subquery có thể tạo UNKNOWN, khiến điều kiện WHERE không đúng TRUE.

**Bài 13:** PostgreSQL có thể dùng một source row không xác định cho target. Giải pháp: unique constraint nếu một-một; hoặc aggregate/`ROW_NUMBER()` với tie-breaker để chỉ còn một source row.

**Bài 14:**

```sql
WITH totals AS (
    SELECT order_id,
           SUM(quantity * unit_price) AS total
    FROM order_items
    GROUP BY order_id
)
UPDATE orders AS o
SET total_amount = t.total
FROM totals AS t
WHERE t.order_id = o.order_id;
```

**Bài 15 — MySQL:**

```sql
UPDATE orders AS o
LEFT JOIN shipment_updates AS s
    ON s.order_id = o.order_id
SET o.shipped_at = COALESCE(s.new_shipped_at, o.shipped_at)
WHERE o.status = 'PENDING';
```

Không dùng `COALESCE` nếu NULL từ source có nghĩa xóa giá trị cũ hoặc cần phân biệt source không tồn tại với source có giá trị NULL.

**Bài 16 — MySQL:**

```sql
UPDATE orders AS o
JOIN shipment_updates AS s
    ON s.order_id = o.order_id
SET o.status = s.new_status,
    s.received_at = CURRENT_TIMESTAMP
WHERE o.status = 'PENDING';
```

MySQL có multi-table UPDATE; các DBMS khác thường chỉ cập nhật target đã chỉ định.

**Bài 17:** `deleted` là row image trước UPDATE; `inserted` là row image sau UPDATE.

**Bài 18:** PostgreSQL `RETURNING` trả các cột/biểu thức của dòng vừa thay đổi; không tự commit. Transaction vẫn do caller quản lý.

**Bài 19:**

```sql
SELECT st.stage_id, st.order_id
FROM import_stage st
JOIN orders o ON o.order_id = st.order_id
WHERE st.batch_id = 'BATCH-A'
  AND st.imported = TRUE
  AND o.status IN ('SHIPPED', 'DELIVERED');

DELETE FROM import_stage st
USING orders o
WHERE o.order_id = st.order_id
  AND st.batch_id = 'BATCH-A'
  AND st.imported = TRUE
  AND o.status IN ('SHIPPED', 'DELIVERED')
RETURNING st.stage_id;
```

**Bài 20:** `NOT IN` so sánh với tập có NULL có thể cho UNKNOWN. `WHERE` chỉ giữ TRUE nên không chọn các dòng dự định. `NOT EXISTS` tránh bẫy này.

**Bài 21:** Oracle báo scalar subquery trả nhiều dòng (thường ORA-01427). Tạo unique key, aggregate hoặc `ROW_NUMBER() ... WHERE rn=1`.

**Bài 22:**

```sql
SELECT *
FROM (
    SELECT h.*,
           ROW_NUMBER() OVER (
               PARTITION BY order_id
               ORDER BY event_time DESC, shipment_event_id DESC
           ) AS rn
    FROM shipment_history h
) ranked
WHERE rn = 1;
```

Tie-breaker đảm bảo thứ tự xác định khi timestamp trùng.

**Bài 23:** Oracle, SQL Server và PostgreSQL 15+ có `MERGE`; MySQL dùng `INSERT ... ON DUPLICATE KEY UPDATE` và các dạng UPDATE/INSERT riêng, không dùng cùng grammar `MERGE INTO`.

**Bài 24:** Có thể xóa child trước parent trong transaction; dùng `ON DELETE CASCADE` nếu nghiệp vụ muốn xóa dây chuyền; hoặc soft delete. Cascade có thể xóa rất nhiều dữ liệu phụ thuộc ngoài dự kiến nếu thiết kế sai.

**Bài 25:** Không commit. Kiểm tra target/source, điều kiện join/filter, tenant key và preview; rollback nếu transaction vẫn mở và phạm vi sai.

**Bài 26:** Preview SELECT không khóa dữ liệu; transaction khác có thể thay đổi trước DML. Cân nhắc row lock, isolation, optimistic version hoặc update có điều kiện nguyên tử.

**Bài 27:** Batch nhỏ giảm thời gian lock, log và rollback mỗi transaction; nhưng tăng số transaction/round-trip, cần checkpoint và bảo đảm không bỏ sót. Batch 500 là điểm khởi đầu cần đo, không phải con số tối ưu cố định.

**Bài 28:**

| DBMS | Cú pháp |
|---|---|
| MySQL | `UPDATE t JOIN s ON ... SET ...`; `DELETE t FROM t JOIN s ...` |
| SQL Server | `UPDATE t SET ... FROM t JOIN s ...`; `DELETE t FROM t JOIN s ...` |
| PostgreSQL | `UPDATE t SET ... FROM s WHERE ...`; `DELETE FROM t USING s WHERE ...` |
| SQLite | `UPDATE t SET ... FROM s WHERE ...`; DELETE bằng `WHERE EXISTS` |
| Oracle | UPDATE bằng correlated subquery/MERGE; DELETE bằng `WHERE EXISTS` |

</details>

## 32. Checklist chọn cú pháp theo DBMS

Trước khi viết câu lệnh cho một ứng dụng hỗ trợ nhiều database, hãy xác định:

1. Database và phiên bản cụ thể là gì?
2. Target table là bảng nào?
3. Source table có khóa duy nhất theo target key không?
4. Cần gán giá trị từ source hay chỉ kiểm tra source tồn tại?
5. Có thể dùng `EXISTS` để viết rõ hơn không?
6. Nếu cần nhiều source, phải aggregate hoặc chọn một dòng mới nhất theo quy tắc nào?
7. Cú pháp DML có `JOIN`, `FROM`, `USING`, `MERGE` hay correlated subquery?
8. Có `RETURNING`/`OUTPUT` để lấy dòng thay đổi không?
9. NULL từ source có nghĩa giữ, xóa hay không hợp lệ?
10. Foreign key/trigger/cascade có tác động gì?
11. Số dòng dự kiến và update count thực tế có khớp không?
12. Có cần transaction, row lock, optimistic version hoặc batch không?
13. Index nào hỗ trợ join key và filter?
14. Có integration test trên đúng DBMS/driver không?

### 32.1. Quy tắc ghi nhớ nhanh

- **MySQL:** `UPDATE target JOIN source ... SET ...`; `DELETE target_alias FROM ... JOIN ...`.
- **SQL Server:** `UPDATE alias SET ... FROM target alias JOIN source`; `DELETE alias FROM ... JOIN ...`.
- **PostgreSQL:** `UPDATE target SET ... FROM source WHERE ...`; `DELETE FROM target USING source WHERE ...`.
- **SQLite:** `UPDATE target SET ... FROM source WHERE ...` từ 3.33; DELETE dùng `EXISTS`.
- **Oracle:** UPDATE bằng correlated subquery hoặc `MERGE`; DELETE dùng `EXISTS`.

## 33. Kết luận

UPDATE JOIN và DELETE JOIN giúp thay đổi một bảng dựa trên dữ liệu từ bảng khác. Chúng hữu ích trong đồng bộ trạng thái, tổng hợp dữ liệu, import và cleanup. Nhưng cú pháp không đồng nhất giữa các hệ quản trị:

```text
MySQL       UPDATE ... JOIN ... SET ...
SQL Server  UPDATE ... SET ... FROM ... JOIN ...
PostgreSQL  UPDATE ... SET ... FROM ...
SQLite      UPDATE ... SET ... FROM ...   (3.33+)
Oracle      UPDATE ... SET (subquery) / MERGE

MySQL       DELETE target FROM ... JOIN ...
SQL Server  DELETE target FROM ... JOIN ...
PostgreSQL  DELETE FROM target USING ...
SQLite      DELETE FROM target WHERE EXISTS (...)
Oracle      DELETE FROM target WHERE EXISTS (...)
```

Hãy nhớ bốn nguyên tắc:

1. **Xác định đúng target và source:** câu lệnh phải làm rõ bảng nào thay đổi và bảng nào chỉ cung cấp dữ liệu/điều kiện.
2. **Bảo đảm một source row phù hợp cho mỗi target khi cần gán giá trị:** dùng unique key, aggregate hoặc `ROW_NUMBER()` có tie-breaker; đừng dựa vào một dòng được chọn ngẫu nhiên.
3. **Dùng cú pháp phù hợp DBMS:** khi cần tính portable, ưu tiên `EXISTS`, `NOT EXISTS` hoặc correlated subquery nếu đáp ứng semantics; không giả định UPDATE JOIN/DELETE JOIN là chuẩn chung.
4. **Preview và kiểm soát transaction:** kiểm tra dòng sẽ bị tác động, row count, FK, lock và side effect; rollback khi phạm vi sai, commit khi kết quả đã được xác nhận.

Một câu UPDATE/DELETE tốt không chỉ đúng cú pháp. Nó phải thay đổi **đúng bảng, đúng dòng, đúng giá trị và đúng số lượng**, đồng thời có thể được kiểm tra và khôi phục khi kết quả không như dự kiến.
