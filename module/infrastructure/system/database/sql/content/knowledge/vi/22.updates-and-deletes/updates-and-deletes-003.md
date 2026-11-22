# UPDATE từ truy vấn con hoặc bảng khác

Một cửa hàng đang có bảng sản phẩm. Bộ phận kho gửi danh sách **số lượng tồn cần bổ sung**; nhà cung cấp gửi **bảng giá mới**; hệ thống bán hàng lưu **những giao dịch đã phát sinh**. Thay vì cập nhật từng sản phẩm bằng một giá trị viết cứng, ta muốn lấy **dữ liệu từ một bảng khác hoặc từ một truy vấn con** làm nguồn cho câu lệnh `UPDATE`.

Ví dụ, yêu cầu nghiệp vụ có thể là:

- Cập nhật số lượng tồn theo kế hoạch đã được phê duyệt.
- Tính giá bán mới từ **báo giá được duyệt gần nhất** của mỗi sản phẩm.
- Ghi tổng số lượng bán trong tháng vào cột thống kê.
- Đánh dấu những sản phẩm **không có báo giá hợp lệ** để nhân viên rà soát.

Trong SQL, mỗi yêu cầu có thể được diễn đạt bằng những hình thức liên quan:

1. **`UPDATE ... FROM`**: nối bảng đích với bảng/truy vấn nguồn để lấy giá trị cập nhật.
2. **Truy vấn con trong `SET`**: tính một giá trị cho mỗi hàng của bảng đích, thường có điều kiện tương quan.
3. **Truy vấn con trong `WHERE`**: dùng `EXISTS`, `NOT EXISTS`, `IN` hoặc giá trị tổng hợp để quyết định hàng nào được sửa.
4. **CTE (`WITH`) kết hợp `UPDATE`**: chuẩn bị và kiểm soát dữ liệu nguồn trước khi cập nhật.

**Điểm khó nhất không phải cú pháp `SET`.** Đó là xác định **mỗi hàng đích phải nhận đúng một giá trị nguồn**, tránh cập nhật ngoài phạm vi và hiểu cách xử lý khi không tìm thấy bản ghi liên quan.

Bài thuộc **Database SQL → Cập nhật và xóa**, dùng **PostgreSQL** làm hệ quản trị chính. Các khác biệt của MySQL, SQL Server, SQLite và Oracle được trình bày riêng.

## 1. Tư duy cơ bản: hàng đích, nguồn dữ liệu và điều kiện ghép

Một phép cập nhật lấy dữ liệu bên ngoài có ba thành phần:

~~~text
                       DU LIEU NGUON
                 (bang, CTE, truy van con)
                           |
                           | khoa lien ket / dieu kien
                           v
                      HANG DICH
                  (bang trong UPDATE)
                           |
                           | SET cot = gia tri moi
                           v
                    HANG SAU CAP NHAT
~~~

| Thành phần | Câu hỏi |
| --- | --- |
| **Bảng đích** (*target*) | Bảng nào thực sự bị sửa? |
| **Khóa ghép** | Nguồn nào thuộc đúng hàng đích này? |
| **Giá trị nguồn** | Cột hoặc biểu thức nào cung cấp giá trị mới? |
| **Điều kiện lọc** | Những hàng đích nào được phép cập nhật? |
| **Bội số khớp** (*cardinality*) | Một hàng đích có đúng **một** hàng nguồn, **nhiều** hàng nguồn hay **không có** hàng nguồn? |
| **Cách xác minh** | Trước khi sửa, có thể xem bản cũ và giá trị dự kiến không? |

Với PostgreSQL, mẫu `UPDATE ... FROM` thường là:

~~~sql
UPDATE target_table AS t
SET target_column = s.source_value
FROM source_table AS s
WHERE s.business_key = t.business_key
  AND dieu_kien_cap_nhat;
~~~

Mẫu truy vấn con trong `SET`:

~~~sql
UPDATE target_table AS t
SET target_column = (
    SELECT mot_gia_tri
    FROM source_table AS s
    WHERE s.business_key = t.business_key
)
WHERE dieu_kien_cap_nhat;
~~~

Cả hai có thể tạo cùng giá trị sau cập nhật, nhưng **khác nhau về hành vi khi nguồn thiếu hoặc trả nhiều hàng**. Vì vậy không nên chuyển đổi chúng một cách máy móc.

## 2. Tạo dữ liệu thực hành PostgreSQL

Bài dùng bốn bảng: **sản phẩm**, **kế hoạch bổ sung tồn kho**, **báo giá nhà cung cấp** và **dòng bán hàng**.

Hãy chạy phần khởi tạo **một lần** trong database PostgreSQL **thực hành riêng**, khi chưa có những bảng `lab_up274_*`. Tránh dùng database sản xuất, vì `CREATE TABLE`, `INSERT` và `UPDATE` đều có thể thay đổi dữ liệu thật.

### 2.1. Bảng sản phẩm: đích của các câu UPDATE

~~~sql
CREATE TABLE lab_up274_products (
    product_id INTEGER PRIMARY KEY,
    sku VARCHAR(20) NOT NULL UNIQUE,
    product_name VARCHAR(80) NOT NULL,
    category VARCHAR(20) NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    stock_qty INTEGER NOT NULL CHECK (stock_qty >= 0),
    reorder_level INTEGER NOT NULL CHECK (reorder_level >= 0),
    status VARCHAR(12) NOT NULL
        CHECK (status IN ('ACTIVE', 'INACTIVE')),
    sold_qty_oct BIGINT NOT NULL DEFAULT 0,
    price_review_required BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

`product_id` là khóa chính. `stock_qty` là tồn kho, `reorder_level` là ngưỡng gợi ý bổ sung hàng. `sold_qty_oct` là cột **thống kê tháng 10/2026** để thực hành cập nhật từ kết quả tổng hợp; việc lưu cột thống kê như vậy trong hệ thống thật cần quy trình đồng bộ riêng.

~~~sql
INSERT INTO lab_up274_products (
    product_id, sku, product_name, category,
    unit_price, stock_qty, reorder_level, status
)
VALUES
    (101, 'PEN',      'Bút bi',     'STATIONERY',  12000.00,  4, 10, 'ACTIVE'),
    (102, 'NOTEBOOK', 'Sổ tay',    'STATIONERY',  35000.00, 25, 12, 'ACTIVE'),
    (103, 'BACKPACK', 'Ba lô',     'ACCESSORY',  220000.00,  3,  5, 'ACTIVE'),
    (104, 'MOUSE',    'Chuột',     'ELECTRONIC', 180000.00,  0,  4, 'ACTIVE'),
    (105, 'KEYBOARD', 'Bàn phím',  'ELECTRONIC', 300000.00,  8,  6, 'ACTIVE'),
    (106, 'USB',      'USB',       'ELECTRONIC',  90000.00, 12,  8, 'INACTIVE'),
    (107, 'PRINTER',  'Máy in',    'ELECTRONIC',2200000.00,  2,  2, 'ACTIVE');
~~~

### 2.2. Kế hoạch nhập thêm hàng: mỗi sản phẩm tối đa một kế hoạch

~~~sql
CREATE TABLE lab_up274_restock_plan (
    product_id INTEGER PRIMARY KEY
        REFERENCES lab_up274_products(product_id),
    target_stock INTEGER NOT NULL CHECK (target_stock >= 0),
    approved BOOLEAN NOT NULL,
    plan_note TEXT
);

INSERT INTO lab_up274_restock_plan
    (product_id, target_stock, approved, plan_note)
VALUES
    (101, 18, TRUE,  'Bổ sung bút'),
    (102, 20, TRUE,  'Không cần giảm tồn'),
    (103, 10, TRUE,  'Bổ sung ba lô'),
    (104,  6, TRUE,  'Bổ sung chuột'),
    (105, 20, FALSE, 'Chưa phê duyệt'),
    (106, 30, TRUE,  'Sản phẩm đã ngừng bán');
~~~

`product_id` vừa là **khóa chính** của kế hoạch, vừa là **khóa ngoại** tới sản phẩm. Vì vậy, một sản phẩm có **tối đa một hàng kế hoạch**. Đây là điều kiện thuận lợi cho `UPDATE ... FROM`: tránh tình trạng một hàng đích ghép nhiều hàng nguồn.

### 2.3. Báo giá: một sản phẩm có thể có nhiều hàng nguồn

~~~sql
CREATE TABLE lab_up274_supplier_quotes (
    quote_id INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL
        REFERENCES lab_up274_products(product_id),
    supplier_name VARCHAR(40) NOT NULL,
    offered_price NUMERIC(12, 2) NOT NULL CHECK (offered_price >= 0),
    valid_from DATE NOT NULL,
    approval_status VARCHAR(12) NOT NULL
        CHECK (approval_status IN ('APPROVED', 'PENDING', 'REJECTED'))
);

INSERT INTO lab_up274_supplier_quotes
    (quote_id, product_id, supplier_name, offered_price,
     valid_from, approval_status)
VALUES
    ( 1, 101, 'NCC-A',  10500.00, DATE '2026-10-01', 'APPROVED'),
    ( 2, 101, 'NCC-B',  10800.00, DATE '2026-10-12', 'APPROVED'),
    ( 3, 102, 'NCC-A',  30000.00, DATE '2026-10-05', 'APPROVED'),
    ( 4, 103, 'NCC-B', 195000.00, DATE '2026-10-08', 'APPROVED'),
    ( 5, 103, 'NCC-C', 190000.00, DATE '2026-10-11', 'APPROVED'),
    ( 6, 104, 'NCC-A', 160000.00, DATE '2026-10-15', 'PENDING'),
    ( 7, 105, 'NCC-B', 265000.00, DATE '2026-10-13', 'APPROVED'),
    ( 8, 105, 'NCC-C', 270000.00, DATE '2026-10-13', 'APPROVED'),
    ( 9, 106, 'NCC-A',  80000.00, DATE '2026-10-01', 'APPROVED'),
    (10, 101, 'NCC-C',  11000.00, DATE '2026-10-20', 'REJECTED');
~~~

Một sản phẩm có thể có **nhiều báo giá**, trong đó có báo giá chưa duyệt hoặc bị từ chối. Khi chọn “báo giá được duyệt gần nhất”, ta phải xác định:

1. Chỉ xét `approval_status = 'APPROVED'`.
2. Ngày hiệu lực `valid_from` **mới nhất** đứng trước.
3. Nếu nhiều báo giá cùng ngày, dùng `quote_id` **lớn hơn** để phân định.

Ví dụ sản phẩm 105 có **hai báo giá duyệt cùng ngày**, cần chọn **quote_id 8**, không được chọn tùy ý 7 hay 8.

### 2.4. Dòng bán hàng: nguồn để tổng hợp

~~~sql
CREATE TABLE lab_up274_sales (
    sale_id INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL
        REFERENCES lab_up274_products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    sold_on DATE NOT NULL,
    sale_status VARCHAR(12) NOT NULL
        CHECK (sale_status IN ('POSTED', 'CANCELLED'))
);

INSERT INTO lab_up274_sales
    (sale_id, product_id, quantity, sold_on, sale_status)
VALUES
    (1001, 101, 3, DATE '2026-10-02', 'POSTED'),
    (1002, 101, 2, DATE '2026-10-08', 'POSTED'),
    (1003, 102, 6, DATE '2026-10-04', 'POSTED'),
    (1004, 103, 2, DATE '2026-10-06', 'POSTED'),
    (1005, 103, 5, DATE '2026-10-11', 'CANCELLED'),
    (1006, 104, 1, DATE '2026-10-20', 'POSTED'),
    (1007, 105, 4, DATE '2026-10-10', 'POSTED'),
    (1008, 105, 3, DATE '2026-10-18', 'POSTED'),
    (1009, 106, 8, DATE '2026-10-12', 'POSTED'),
    (1010, 101, 9, DATE '2026-09-30', 'POSTED'),
    (1011, 105, 2, DATE '2026-11-01', 'POSTED');
~~~

Dữ liệu có những tình huống để thử: hàng `CANCELLED` không được tính là bán thành công; giao dịch tháng 9 và tháng 11 không thuộc **tháng 10**; sản phẩm 107 chưa có dòng bán hàng.

### 2.5. Kiểm tra dữ liệu ban đầu

~~~sql
SELECT
    product_id, sku, unit_price, stock_qty, reorder_level,
    status, sold_qty_oct, price_review_required
FROM lab_up274_products
ORDER BY product_id;
~~~

| product_id | sku | unit_price | stock_qty | reorder_level | status |
| ---: | --- | ---: | ---: | ---: | --- |
| 101 | PEN | 12000.00 | 4 | 10 | ACTIVE |
| 102 | NOTEBOOK | 35000.00 | 25 | 12 | ACTIVE |
| 103 | BACKPACK | 220000.00 | 3 | 5 | ACTIVE |
| 104 | MOUSE | 180000.00 | 0 | 4 | ACTIVE |
| 105 | KEYBOARD | 300000.00 | 8 | 6 | ACTIVE |
| 106 | USB | 90000.00 | 12 | 8 | INACTIVE |
| 107 | PRINTER | 2200000.00 | 2 | 2 | ACTIVE |

`sold_qty_oct = 0` và `price_review_required = FALSE` trên tất cả bảy hàng do các giá trị mặc định của `CREATE TABLE`.

**Cách thực hành được khuyến nghị:** mỗi ví dụ `UPDATE` bên dưới được giải thích **độc lập trên dữ liệu ban đầu**. Khi muốn thử mà không thay đổi dữ liệu cho các ví dụ sau, dùng:

~~~sql
BEGIN;
-- Dat mot cau UPDATE can thu tai day.
-- Co the SELECT trong cung giao dich de xem ket qua tam thoi.
ROLLBACK;
~~~

Trong các mẫu tiếp theo, những khối có `BEGIN ... ROLLBACK` là bản thực hành an toàn cho **một ví dụ**. Nếu bạn chủ động muốn lưu thay đổi, chỉ `COMMIT` khi đã xác nhận đúng hàng, đúng giá trị và giao dịch phù hợp.

## 3. UPDATE ... FROM: lấy giá trị từ bảng khác

Yêu cầu đầu tiên: “Với **sản phẩm đang hoạt động**, nếu có **kế hoạch được phê duyệt** và `target_stock` lớn hơn tồn kho hiện tại, cập nhật tồn kho thành mức trong kế hoạch”.

### 3.1. Xem trước phép ghép và giá trị sẽ sửa

Trước khi viết `UPDATE`, có thể dùng câu `SELECT` có cùng điều kiện ghép:

~~~sql
SELECT
    p.product_id,
    p.product_name,
    p.stock_qty AS old_stock,
    r.target_stock AS proposed_stock
FROM lab_up274_products AS p
JOIN lab_up274_restock_plan AS r
    ON r.product_id = p.product_id
WHERE r.approved = TRUE
  AND p.status = 'ACTIVE'
  AND r.target_stock > p.stock_qty
ORDER BY p.product_id;
~~~

Kết quả xem trước:

| product_id | product_name | old_stock | proposed_stock |
| ---: | --- | ---: | ---: |
| 101 | Bút bi | 4 | 18 |
| 103 | Ba lô | 3 | 10 |
| 104 | Chuột | 0 | 6 |

Không có hàng 102 vì `target_stock = 20` **nhỏ hơn** tồn thực tế 25. Hàng 105 chưa được phê duyệt; 106 là sản phẩm INACTIVE; 107 không có kế hoạch.

### 3.2. UPDATE FROM trong PostgreSQL

~~~sql
BEGIN;

UPDATE lab_up274_products AS p
SET
    stock_qty = r.target_stock,
    updated_at = CURRENT_TIMESTAMP
FROM lab_up274_restock_plan AS r
WHERE r.product_id = p.product_id
  AND r.approved = TRUE
  AND p.status = 'ACTIVE'
  AND r.target_stock > p.stock_qty
RETURNING
    p.product_id,
    p.sku,
    p.stock_qty AS new_stock;

ROLLBACK;
~~~

Lệnh `UPDATE` chỉ sửa bảng `lab_up274_products`. Bảng `lab_up274_restock_plan` được đưa vào `FROM` để **cung cấp dữ liệu nguồn**, không bị sửa.

Các hàng `RETURNING` trong transaction có giá trị tồn kho mới:

| product_id | sku | new_stock |
| ---: | --- | ---: |
| 101 | PEN | 18 |
| 103 | BACKPACK | 10 |
| 104 | MOUSE | 6 |

**Thứ tự hàng do `RETURNING` trả ra không được bảo đảm.** Bảng trên được sắp theo ID chỉ để trình bày. Nếu cần kết quả hiển thị theo thứ tự, một truy vấn `SELECT ... ORDER BY` sau đó sẽ rõ ràng hơn.

Vì có `ROLLBACK`, ba thay đổi này **không được giữ lại sau khi khối thực hành kết thúc**.

### 3.3. Đọc từng phần câu UPDATE

~~~sql
UPDATE lab_up274_products AS p       -- Bang dich, bi sua
SET stock_qty = r.target_stock       -- Lay gia tri tu hang nguon
FROM lab_up274_restock_plan AS r     -- Bang nguon
WHERE r.product_id = p.product_id    -- Ghep dung khoa
  AND r.approved = TRUE              -- Chi ke hoach duyet
  AND p.status = 'ACTIVE'            -- Chi san pham dang hoat dong
  AND r.target_stock > p.stock_qty;  -- Chi tang ton, khong giam
~~~

Trong PostgreSQL, khi đã dùng bí danh bảng đích `p`, các biểu thức ở `WHERE` và phía phải `SET` có thể tham chiếu `p.stock_qty`, `r.target_stock`. Nhưng phía **trái** của phép gán trong `SET` thường viết **tên cột đích không có tiền tố bí danh**:

~~~sql
-- Cach viet dung trong PostgreSQL:
SET stock_qty = r.target_stock

-- Khong viet nhu mot qualified column target trong PostgreSQL:
-- SET p.stock_qty = r.target_stock
~~~

Ở một số hệ quản trị khác, cách ghi tiền tố bảng trong `SET` có quy tắc riêng; phần so sánh dialect nằm ở cuối bài.

### 3.4. Điều kiện ghép trong WHERE là bắt buộc về ngữ nghĩa

Nếu bỏ `r.product_id = p.product_id`, một sản phẩm có thể kết hợp với **nhiều kế hoạch không liên quan**. Khi ấy hệ quản trị có thể cập nhật hàng đích từ dữ liệu nguồn không đúng sản phẩm.

Đặc biệt cảnh giác với mẫu sai:

~~~sql
-- SAI VE NGHIEP VU: thieu dieu kien noi khoa.
-- KHONG CHAY.
UPDATE lab_up274_products AS p
SET stock_qty = r.target_stock
FROM lab_up274_restock_plan AS r
WHERE r.approved = TRUE;
~~~

Đây là lỗi có thể **không làm câu SQL báo lỗi cú pháp**, nhưng có thể sửa rất nhiều hàng bằng giá trị của kế hoạch không liên quan. Phải kiểm tra điều kiện ghép khi dùng `UPDATE FROM`.

## 4. Điều kiện quan trọng: một hàng đích có bao nhiêu hàng nguồn?

`UPDATE FROM` hoạt động rõ ràng khi **mỗi hàng đích có tối đa một hàng nguồn phù hợp**. Trong ví dụ tồn kho, `restock_plan.product_id` là `PRIMARY KEY` nên điều kiện ghép theo `product_id` đảm bảo tối đa một kế hoạch cho mỗi sản phẩm.

Tuy nhiên, bảng `supplier_quotes` là quan hệ **một–nhiều**: mỗi sản phẩm có thể có nhiều báo giá. Hãy xem:

~~~sql
SELECT
    product_id,
    COUNT(*) AS approved_quote_count
FROM lab_up274_supplier_quotes
WHERE approval_status = 'APPROVED'
GROUP BY product_id
ORDER BY product_id;
~~~

| product_id | approved_quote_count |
| ---: | ---: |
| 101 | 2 |
| 102 | 1 |
| 103 | 2 |
| 105 | 2 |
| 106 | 1 |

Sản phẩm 101, 103, 105 **mỗi sản phẩm có hai báo giá được duyệt**.

### 4.1. UPDATE FROM khớp nhiều hàng là nguy hiểm

Không nên dùng trực tiếp câu sau:

~~~sql
-- KHONG CHAY: mot san pham co the khop nhieu bao gia.
UPDATE lab_up274_products AS p
SET unit_price = ROUND(q.offered_price * 1.20, 2)
FROM lab_up274_supplier_quotes AS q
WHERE q.product_id = p.product_id
  AND q.approval_status = 'APPROVED'
  AND p.status = 'ACTIVE';
~~~

Với PostgreSQL, nếu một hàng đích khớp **nhiều hàng trong `FROM`**, chỉ một hàng ghép được dùng cho cập nhật, nhưng **không nên dựa vào việc hàng nguồn nào được chọn**. PostgreSQL không bảo đảm rằng “báo giá mới nhất”, “báo giá đầu tiên” hay “giá thấp nhất” được chọn tự động.

Trong các hệ quản trị khác, cách xử lý một hàng đích khớp nhiều hàng nguồn cũng có thể khác. Vì thế, nguyên tắc an toàn là **biến bảng nguồn thành một hàng duy nhất cho mỗi khóa đích trước khi cập nhật**.

### 4.2. Cách nhận biết nguồn không duy nhất

~~~sql
SELECT
    q.product_id,
    COUNT(*) AS matches
FROM lab_up274_supplier_quotes AS q
WHERE q.approval_status = 'APPROVED'
GROUP BY q.product_id
HAVING COUNT(*) > 1
ORDER BY q.product_id;
~~~

Kết quả gồm **101, 103, 105**. Truy vấn này chỉ cho thấy bội số nguồn; khi viết `UPDATE` cụ thể còn phải đối chiếu **đúng điều kiện lọc và khóa ghép** để biết các hàng có thực sự cùng khớp một đích hay không.

### 4.3. Chọn quy tắc duy nhất có ý nghĩa nghiệp vụ

Ví dụ: “Dùng **báo giá APPROVED có `valid_from` mới nhất**; nếu cùng ngày, dùng `quote_id` lớn hơn”.

Đây là một quy tắc **toàn phần** trên tập báo giá của từng sản phẩm, vì `quote_id` là khóa chính duy nhất. Bây giờ truy vấn có thể chọn **chính xác một hàng nguồn** thay vì tùy tiện lấy bất kỳ báo giá nào.

## 5. UPDATE bằng truy vấn con trong SET

Trong PostgreSQL, phía phải `SET` có thể là một **truy vấn con scalar**: một truy vấn `SELECT` được dùng như một biểu thức, trả **không quá một hàng và một cột** tại từng hàng đích.

Cấu trúc:

~~~sql
UPDATE target AS t
SET some_column = (
    SELECT value
    FROM source AS s
    WHERE s.target_key = t.target_key
)
WHERE dieu_kien;
~~~

Điều kiện `s.target_key = t.target_key` làm truy vấn con **tương quan** (*correlated subquery*) với hàng đích hiện tại.

### 5.1. Chọn báo giá được duyệt gần nhất bằng ORDER BY + LIMIT 1

Giả sử giá bán mong muốn bằng **120% giá chào của nhà cung cấp**. Với dữ liệu mẫu, ta muốn sửa **sản phẩm ACTIVE có báo giá APPROVED**:

~~~sql
BEGIN;

UPDATE lab_up274_products AS p
SET
    unit_price = (
        SELECT ROUND(q.offered_price * 1.20, 2)
        FROM lab_up274_supplier_quotes AS q
        WHERE q.product_id = p.product_id
          AND q.approval_status = 'APPROVED'
        ORDER BY q.valid_from DESC, q.quote_id DESC
        LIMIT 1
    ),
    updated_at = CURRENT_TIMESTAMP
WHERE p.status = 'ACTIVE'
  AND EXISTS (
      SELECT 1
      FROM lab_up274_supplier_quotes AS q
      WHERE q.product_id = p.product_id
        AND q.approval_status = 'APPROVED'
  )
RETURNING
    p.product_id,
    p.sku,
    p.unit_price AS new_price;

ROLLBACK;
~~~

Theo dữ liệu ban đầu, các giá mới là:

| product_id | Báo giá được chọn | Giá nguồn | Giá mới sau nhân 1.20 |
| ---: | ---: | ---: | ---: |
| 101 | quote 2 | 10800.00 | 12960.00 |
| 102 | quote 3 | 30000.00 | 36000.00 |
| 103 | quote 5 | 190000.00 | 228000.00 |
| 105 | quote 8 | 270000.00 | 324000.00 |

Sản phẩm **104** có báo giá nhưng chỉ ở trạng thái PENDING, nên không cập nhật. **107** không có báo giá; **106** có báo giá APPROVED nhưng sản phẩm INACTIVE, cũng không cập nhật.

Trong truy vấn con:

- `q.product_id = p.product_id`: giới hạn báo giá thuộc **đúng sản phẩm**.
- `q.approval_status = 'APPROVED'`: bỏ báo giá đang chờ hoặc bị từ chối.
- `ORDER BY q.valid_from DESC, q.quote_id DESC`: chọn ngày mới nhất rồi ID lớn nhất khi trùng ngày.
- `LIMIT 1`: bảo đảm **tối đa một hàng**, phù hợp với vị trí scalar.
- `ROUND(..., 2)`: giữ giá đến hai chữ số thập phân như kiểu `NUMERIC(12,2)` của cột đích.

**Ghi chú nghiệp vụ:** công thức “giá bán = 120% báo giá” chỉ là quy tắc thực hành. Trong hệ thống thật, giá bán có thể phụ thuộc thuế, chiết khấu, tỷ suất lợi nhuận, đồng tiền và thời hạn hiệu lực.

### 5.2. Vì sao cần EXISTS nếu đã có LIMIT 1?

`LIMIT 1` chỉ đảm bảo **không quá một hàng**; nó **không** đảm bảo **có một hàng**. Nếu không có báo giá APPROVED, truy vấn con scalar sẽ không trả dòng nào và biểu thức của nó nhận `NULL`.

Vì `unit_price` trong bảng sản phẩm có ràng buộc `NOT NULL`, lệnh sau **không an toàn**:

~~~sql
-- KHONG CHAY: san pham khong co bao gia APPROVED
-- se nhan NULL tu scalar subquery va vi pham NOT NULL.
UPDATE lab_up274_products AS p
SET unit_price = (
    SELECT q.offered_price
    FROM lab_up274_supplier_quotes AS q
    WHERE q.product_id = p.product_id
      AND q.approval_status = 'APPROVED'
    ORDER BY q.valid_from DESC, q.quote_id DESC
    LIMIT 1
);
~~~

`WHERE EXISTS (...)` ở câu đúng chỉ cập nhật những sản phẩm có nguồn hợp lệ. Một cách khác là dùng `COALESCE(subquery, p.unit_price)` nếu nghiệp vụ muốn **giữ nguyên giá cũ khi không có báo giá**; nhưng hai cách khác nhau về số hàng thực sự được cập nhật và có thể khác tác động tới trigger, cột thời gian, log hoặc khóa hàng.

### 5.3. Truy vấn con trả nhiều hàng sẽ báo lỗi

~~~sql
-- KHONG CHAY: san pham 101, 103, 105 co hon mot bao gia duyet.
UPDATE lab_up274_products AS p
SET unit_price = (
    SELECT q.offered_price
    FROM lab_up274_supplier_quotes AS q
    WHERE q.product_id = p.product_id
      AND q.approval_status = 'APPROVED'
);
~~~

Trong PostgreSQL, scalar subquery được dùng làm một giá trị trong `SET` mà trả nhiều hàng sẽ lỗi gần nghĩa **“more than one row returned by a subquery used as an expression”**. Không thể sửa bằng cách thêm `LIMIT 1` không có `ORDER BY` rồi gọi đó là “báo giá mới nhất”.

Hãy chọn một quy tắc rõ ràng: `MAX`/`MIN` nếu thật sự cần cực trị, `ORDER BY ... LIMIT 1` nếu cần hàng mới nhất, hoặc tổng hợp theo đúng khóa trước khi cập nhật.

## 6. UPDATE FROM nguồn đã xếp hạng: ROW_NUMBER và CTE

Khi muốn cập nhật nhiều sản phẩm từ **một tập báo giá được chuẩn bị trước**, ta có thể dùng hàm cửa sổ `ROW_NUMBER()` để chọn một báo giá cho mỗi sản phẩm.

### 6.1. Xem trước hàng báo giá được chọn

~~~sql
WITH ranked_quotes AS (
    SELECT
        q.quote_id,
        q.product_id,
        q.offered_price,
        q.valid_from,
        ROW_NUMBER() OVER (
            PARTITION BY q.product_id
            ORDER BY q.valid_from DESC, q.quote_id DESC
        ) AS rn
    FROM lab_up274_supplier_quotes AS q
    WHERE q.approval_status = 'APPROVED'
)
SELECT
    product_id,
    quote_id,
    offered_price,
    valid_from
FROM ranked_quotes
WHERE rn = 1
ORDER BY product_id;
~~~

Kết quả có một báo giá cho mỗi sản phẩm có báo giá được duyệt:

| product_id | quote_id | offered_price |
| ---: | ---: | ---: |
| 101 | 2 | 10800.00 |
| 102 | 3 | 30000.00 |
| 103 | 5 | 190000.00 |
| 105 | 8 | 270000.00 |
| 106 | 9 | 80000.00 |

Sản phẩm 104 và 107 không có hàng nguồn hợp lệ; 106 vẫn xuất hiện trong nguồn nhưng sẽ bị loại khỏi cập nhật bởi điều kiện `p.status = 'ACTIVE'`.

### 6.2. UPDATE FROM CTE đã bảo đảm một hàng trên mỗi khóa

~~~sql
BEGIN;

WITH ranked_quotes AS (
    SELECT
        q.product_id,
        q.quote_id,
        q.offered_price,
        ROW_NUMBER() OVER (
            PARTITION BY q.product_id
            ORDER BY q.valid_from DESC, q.quote_id DESC
        ) AS rn
    FROM lab_up274_supplier_quotes AS q
    WHERE q.approval_status = 'APPROVED'
),
latest_quotes AS (
    SELECT
        product_id,
        ROUND(offered_price * 1.20, 2) AS proposed_price
    FROM ranked_quotes
    WHERE rn = 1
)
UPDATE lab_up274_products AS p
SET
    unit_price = latest.proposed_price,
    updated_at = CURRENT_TIMESTAMP
FROM latest_quotes AS latest
WHERE latest.product_id = p.product_id
  AND p.status = 'ACTIVE'
  AND p.unit_price IS DISTINCT FROM latest.proposed_price
RETURNING
    p.product_id,
    p.sku,
    p.unit_price AS new_price;

ROLLBACK;
~~~

Kết quả cập nhật cũng là **101, 102, 103, 105** với giá mới như mục 5.

Vì `ROW_NUMBER` gán đúng một hàng có `rn = 1` cho mỗi `product_id`, CTE `latest_quotes` tạo nguồn **tối đa một hàng cho mỗi khóa sản phẩm**. Điều đó giải quyết bội số mà `UPDATE FROM` trực tiếp không tự giải quyết.

### 6.3. IS DISTINCT FROM giúp tránh cập nhật không cần thiết

Điều kiện:

~~~sql
AND p.unit_price IS DISTINCT FROM latest.proposed_price
~~~

nghĩa là chỉ sửa những hàng mà giá hiện tại **khác** giá dự kiến. Trong PostgreSQL, `IS DISTINCT FROM` so được cả trường hợp `NULL` một cách xác định: hai `NULL` được xem là không khác; một phía `NULL` và phía kia có giá trị thì khác.

Ở bảng mẫu, `unit_price NOT NULL` nên toán tử `<>` cũng có thể so đúng hai giá trị số không-null, nhưng `IS DISTINCT FROM` hữu ích và rõ nghĩa khi chuyển mẫu này sang những cột **cho phép `NULL`**.

Việc bỏ qua hàng không đổi còn có thể tránh các tác động phụ không cần thiết, ví dụ thay đổi `updated_at` hoặc kích hoạt cơ chế theo dõi cập nhật.

## 7. PostgreSQL DISTINCT ON: cách khác để chọn một bản ghi nguồn

PostgreSQL có cú pháp `DISTINCT ON`, thường được dùng để lấy một hàng đại diện cho mỗi nhóm, theo thứ tự xác định:

~~~sql
SELECT DISTINCT ON (q.product_id)
    q.product_id,
    q.quote_id,
    q.offered_price,
    q.valid_from
FROM lab_up274_supplier_quotes AS q
WHERE q.approval_status = 'APPROVED'
ORDER BY
    q.product_id,
    q.valid_from DESC,
    q.quote_id DESC;
~~~

Kết quả cùng các báo giá được chọn ở mục 6. `ORDER BY` bắt đầu bằng `product_id` để phân nhóm, sau đó ưu tiên ngày mới hơn và ID lớn hơn.

Có thể đưa truy vấn này vào `FROM` hoặc CTE làm nguồn của `UPDATE`:

~~~sql
BEGIN;

WITH latest_quotes AS (
    SELECT DISTINCT ON (q.product_id)
        q.product_id,
        ROUND(q.offered_price * 1.20, 2) AS proposed_price
    FROM lab_up274_supplier_quotes AS q
    WHERE q.approval_status = 'APPROVED'
    ORDER BY
        q.product_id,
        q.valid_from DESC,
        q.quote_id DESC
)
UPDATE lab_up274_products AS p
SET unit_price = l.proposed_price
FROM latest_quotes AS l
WHERE l.product_id = p.product_id
  AND p.status = 'ACTIVE'
  AND p.unit_price IS DISTINCT FROM l.proposed_price
RETURNING p.product_id, p.unit_price;

ROLLBACK;
~~~

**Lưu ý phương ngữ:** `DISTINCT ON` là tính năng đặc thù PostgreSQL, không được hỗ trợ với cùng cú pháp trên các hệ quản trị SQL phổ biến khác. `ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...)` có tính di động cao hơn trong nhiều hệ hỗ trợ window functions.

## 8. UPDATE từ kết quả tổng hợp: SUM, GROUP BY và CTE

Yêu cầu: “Ghi vào `sold_qty_oct` số lượng đã bán trong **tháng 10/2026**, chỉ tính các dòng `POSTED`”.

Dữ liệu đầu vào có nhiều dòng bán cho cùng sản phẩm, nên `JOIN` trực tiếp sẽ tạo **nhiều hàng nguồn**. Ta phải **tổng hợp về một hàng cho mỗi sản phẩm** trước khi cập nhật.

### 8.1. Tính báo cáo nguồn bằng SELECT

~~~sql
SELECT
    s.product_id,
    SUM(s.quantity) AS sold_quantity
FROM lab_up274_sales AS s
WHERE s.sale_status = 'POSTED'
  AND s.sold_on >= DATE '2026-10-01'
  AND s.sold_on < DATE '2026-11-01'
GROUP BY s.product_id
ORDER BY s.product_id;
~~~

Kết quả:

| product_id | sold_quantity |
| ---: | ---: |
| 101 | 5 |
| 102 | 6 |
| 103 | 2 |
| 104 | 1 |
| 105 | 7 |
| 106 | 8 |

Hàng 1005 của sản phẩm 103 bị loại vì `CANCELLED`. Bán ngày 30/09 và 01/11 không thuộc khoảng tháng 10. Sản phẩm 107 không có giao dịch nên **không xuất hiện trong kết quả có `GROUP BY product_id`**.

Điều kiện **nửa mở**:

~~~sql
sold_on >= DATE '2026-10-01'
AND sold_on < DATE '2026-11-01'
~~~

diễn đạt trọn tháng 10 với cách biểu thị rõ ràng, thuận lợi khi cột ngày/giờ có hoặc chuyển thành dữ liệu `TIMESTAMP`. Với `DATE` cụ thể trong bài, nó lấy tất cả ngày từ 01/10 đến 31/10.

### 8.2. UPDATE FROM một nguồn đã GROUP BY

~~~sql
BEGIN;

WITH sales_summary AS (
    SELECT
        s.product_id,
        SUM(s.quantity) AS sold_quantity
    FROM lab_up274_sales AS s
    WHERE s.sale_status = 'POSTED'
      AND s.sold_on >= DATE '2026-10-01'
      AND s.sold_on < DATE '2026-11-01'
    GROUP BY s.product_id
)
UPDATE lab_up274_products AS p
SET sold_qty_oct = summary.sold_quantity
FROM sales_summary AS summary
WHERE summary.product_id = p.product_id
RETURNING p.product_id, p.sold_qty_oct;

ROLLBACK;
~~~

Vì nguồn `sales_summary` chỉ có **một hàng trên mỗi `product_id`**, mỗi sản phẩm được ghép với tối đa một tổng. Giá trị mới của các sản phẩm 101–106 lần lượt là **5, 6, 2, 1, 7, 8**.

**Nhưng sản phẩm 107 không có nhóm nguồn**, nên `UPDATE FROM` ở trên **không chạm tới hàng 107**. Nếu `sold_qty_oct` của 107 đang là 0, kết quả trông có vẻ đúng. Nếu nó từng là **số khác 0 từ lần tính trước**, giá trị ấy sẽ bị giữ lại và có thể trở thành **số thống kê cũ**.

Đây là điểm quan trọng khi cập nhật từ bảng tổng hợp: **không có nhóm nguồn không đồng nghĩa câu UPDATE sẽ tự đặt giá trị đích bằng 0**.

### 8.3. Nếu cần cập nhật cả những sản phẩm không có bán hàng

Có thể dùng **truy vấn con tương quan** với `COALESCE` để tạo số 0 cho sản phẩm không có dòng bán:

~~~sql
BEGIN;

UPDATE lab_up274_products AS p
SET sold_qty_oct = (
    SELECT COALESCE(SUM(s.quantity), 0)
    FROM lab_up274_sales AS s
    WHERE s.product_id = p.product_id
      AND s.sale_status = 'POSTED'
      AND s.sold_on >= DATE '2026-10-01'
      AND s.sold_on < DATE '2026-11-01'
)
RETURNING
    p.product_id,
    p.sold_qty_oct;

ROLLBACK;
~~~

Kết quả **trên cả bảy sản phẩm**:

| product_id | sold_qty_oct |
| ---: | ---: |
| 101 | 5 |
| 102 | 6 |
| 103 | 2 |
| 104 | 1 |
| 105 | 7 |
| 106 | 8 |
| 107 | 0 |

`SUM(...)` trên tập **không có hàng** trả `NULL`, còn `COALESCE(..., 0)` chuyển giá trị đó về 0 theo quy tắc thống kê của bài: **không có giao dịch POSTED trong tháng được xem là số lượng bán bằng 0**.

Hệ quản trị vẫn có thể tối ưu cách thực thi; cách giải thích “truy vấn con theo từng sản phẩm” mô tả **ngữ nghĩa tương quan**, không phải khẳng định máy chủ phải quét bảng bán hàng bảy lần theo đúng trình tự đó.

### 8.4. Dùng CTE LEFT JOIN để bảo đảm một hàng nguồn cho mọi sản phẩm

Một phương án khác là tổng hợp trước, sau đó **LEFT JOIN từ tập sản phẩm đầy đủ**:

~~~sql
BEGIN;

WITH sales_summary AS (
    SELECT
        s.product_id,
        SUM(s.quantity) AS sold_quantity
    FROM lab_up274_sales AS s
    WHERE s.sale_status = 'POSTED'
      AND s.sold_on >= DATE '2026-10-01'
      AND s.sold_on < DATE '2026-11-01'
    GROUP BY s.product_id
),
complete_source AS (
    SELECT
        p0.product_id,
        COALESCE(summary.sold_quantity, 0) AS sold_quantity
    FROM lab_up274_products AS p0
    LEFT JOIN sales_summary AS summary
        ON summary.product_id = p0.product_id
)
UPDATE lab_up274_products AS p
SET sold_qty_oct = src.sold_quantity
FROM complete_source AS src
WHERE src.product_id = p.product_id
  AND p.sold_qty_oct IS DISTINCT FROM src.sold_quantity
RETURNING p.product_id, p.sold_qty_oct;

ROLLBACK;
~~~

`complete_source` có một hàng cho cả sản phẩm **107**, với số lượng 0. Vì trong bảng mẫu `sold_qty_oct` của 107 vốn đã là 0, điều kiện `IS DISTINCT FROM` bỏ qua hàng 107 để tránh cập nhật không cần thiết; giá trị lưu vẫn là 0. Nếu nó đang là số cũ khác 0, câu lệnh sẽ đưa về 0.

Điểm chung giữa các phương án đúng: **nguồn phải được đưa về độ hạt một hàng cho mỗi sản phẩm**, đồng thời cần có quy tắc rõ ràng cho **sản phẩm không có dòng bán**.

## 9. Truy vấn con trong WHERE: EXISTS và NOT EXISTS

Không phải lúc nào giá trị mới cũng được lấy trực tiếp từ bảng nguồn. Đôi khi dữ liệu bên ngoài chỉ được dùng để xác định **hàng đích có được thay đổi hay không**.

### 9.1. EXISTS: chỉ cập nhật khi có hàng liên quan

Ví dụ minh họa: đánh dấu yêu cầu kiểm tra giá nếu sản phẩm ACTIVE có **ít nhất một báo giá PENDING**.

~~~sql
BEGIN;

UPDATE lab_up274_products AS p
SET price_review_required = TRUE
WHERE p.status = 'ACTIVE'
  AND EXISTS (
      SELECT 1
      FROM lab_up274_supplier_quotes AS q
      WHERE q.product_id = p.product_id
        AND q.approval_status = 'PENDING'
  )
RETURNING p.product_id, p.price_review_required;

ROLLBACK;
~~~

Chỉ sản phẩm **104** có báo giá PENDING. `EXISTS` chỉ kiểm tra **có ít nhất một hàng nguồn thỏa điều kiện**, không cần truy vấn con trả một giá trị đơn lẻ.

### 9.2. NOT EXISTS: đánh dấu sản phẩm không có báo giá được duyệt

~~~sql
BEGIN;

UPDATE lab_up274_products AS p
SET price_review_required = TRUE
WHERE p.status = 'ACTIVE'
  AND NOT EXISTS (
      SELECT 1
      FROM lab_up274_supplier_quotes AS q
      WHERE q.product_id = p.product_id
        AND q.approval_status = 'APPROVED'
  )
RETURNING p.product_id, p.sku, p.price_review_required;

ROLLBACK;
~~~

Kết quả là **104 (MOUSE)** và **107 (PRINTER)**:

- 104 có báo giá nhưng **chưa được duyệt**.
- 107 **không có báo giá**.
- 106 là INACTIVE nên không bị cập nhật dù có báo giá.

Khi yêu cầu là “không có bản ghi liên quan nào”, `NOT EXISTS` thường rõ nghĩa hơn `NOT IN`, nhất là nếu cột được truy vấn có thể `NULL`. Trong bảng mẫu `supplier_quotes.product_id` được khai báo `NOT NULL`, nhưng tư duy an toàn là **so sánh sự tồn tại theo khóa có ý nghĩa**, không phụ thuộc vào may mắn của kiểu dữ liệu.

### 9.3. Dùng một scalar subquery trong WHERE để lọc theo giá trị

Yêu cầu: “Tăng giá **5%** cho các sản phẩm ACTIVE có giá hiện tại **thấp hơn trung bình giá của chính danh mục đó**”.

~~~sql
BEGIN;

UPDATE lab_up274_products AS p
SET unit_price = ROUND(p.unit_price * 1.05, 2)
WHERE p.status = 'ACTIVE'
  AND p.unit_price < (
      SELECT AVG(p2.unit_price)
      FROM lab_up274_products AS p2
      WHERE p2.category = p.category
        AND p2.status = 'ACTIVE'
  )
RETURNING p.product_id, p.unit_price AS new_price;

ROLLBACK;
~~~

Truy vấn con tính **trung bình của danh mục tương ứng với sản phẩm đang xét**. Theo dữ liệu ban đầu, điều kiện chọn các sản phẩm **101, 104 và 105**:

- Danh mục STATIONERY: giá 12000 và 35000, trung bình 23500 → sản phẩm 101 thấp hơn.
- Danh mục ELECTRONIC: các sản phẩm ACTIVE 104, 105, 107 có giá 180000, 300000, 2200000; trung bình khoảng 893333.33 → 104 và 105 thấp hơn.
- Danh mục ACCESSORY chỉ có sản phẩm 103 ACTIVE, nên giá của nó bằng trung bình danh mục, không đạt điều kiện `<`.

Ví dụ này minh họa việc truy vấn con trong `WHERE` cung cấp **ngưỡng tương quan**, còn `SET` lấy giá trị dựa trên **giá hiện tại của hàng đích**.

**Cảnh báo:** lệnh `SET unit_price = unit_price * 1.05` là phép tăng tương đối. Nếu chạy **nhiều lần và COMMIT**, giá sẽ tiếp tục tăng ở các lần thực thi sau nếu điều kiện vẫn thỏa; nó **không có tính lặp lại an toàn** (*idempotent*) như việc gán một giá mục tiêu cố định. Trong báo cáo giá, cần thiết kế điều kiện và lịch chạy để tránh áp dụng tăng giá hai lần ngoài ý muốn.

## 10. NULL khi UPDATE từ truy vấn con và bảng khác

Hãy so sánh ba trường hợp **không có hàng nguồn**:

| Cách viết | Hàng đích không có nguồn khớp |
| --- | --- |
| `UPDATE ... FROM nguồn WHERE nguồn.id = đích.id` | Thông thường **không được cập nhật** vì không có hàng ghép |
| `SET x = (SELECT value FROM nguồn WHERE ...)` | Scalar subquery không có hàng → biểu thức nhận **`NULL`** |
| `SET x = (SELECT COALESCE(SUM(...), 0) ...)` | Truy vấn tổng hợp không `GROUP BY` trả một hàng; tổng tập rỗng thành **0** theo `COALESCE` |

Những khác biệt này ảnh hưởng trực tiếp tới dữ liệu sau lệnh.

### 10.1. Không có hàng và có hàng nhưng giá trị NULL

Một scalar subquery có thể trả `NULL` vì:

1. **Không có hàng nguồn phù hợp**.
2. **Có một hàng nguồn** nhưng cột được chọn mang `NULL`.

Với cột đích `NOT NULL`, cả hai trường hợp có thể khiến `UPDATE` bị từ chối. Với cột đích nullable, `NULL` có thể được lưu, nhưng bạn cần chắc rằng đó đúng là ý nghĩa nghiệp vụ.

Đối với cột giá trong bộ dữ liệu này, `supplier_quotes.offered_price` là `NOT NULL` nên chỉ có trường hợp **không có báo giá hợp lệ** làm scalar subquery rỗng trong ví dụ giá. Các hệ thống thực tế có thể có cột nguồn nullable; khi ấy phải kiểm soát cả hai trường hợp.

### 10.2. COALESCE có thể che khuất dữ liệu thiếu

~~~sql
SET unit_price = COALESCE(
    (
        SELECT q.offered_price
        FROM lab_up274_supplier_quotes AS q
        WHERE q.product_id = p.product_id
          AND q.approval_status = 'APPROVED'
        ORDER BY q.valid_from DESC, q.quote_id DESC
        LIMIT 1
    ),
    p.unit_price
)
~~~

Biểu thức này **giữ giá cũ khi không có nguồn**. Nó có thể hữu ích, nhưng không tự chứng minh rằng dữ liệu nguồn đầy đủ: người dùng vẫn có thể muốn **báo lỗi hoặc đánh dấu thiếu báo giá**.

Với thống kê `sold_qty_oct`, quy tắc “không có giao dịch POSTED trong tháng → 0” hợp lý trong bài. Với **giá nhà cung cấp**, “không có báo giá → 0” thường **không hợp lý**, vì 0 là một giá trị kinh doanh khác với **chưa biết giá**.

### 10.3. IS DISTINCT FROM để tránh vấn đề logic ba giá trị

Trong PostgreSQL:

| Bên trái | Bên phải | `a <> b` | `a IS DISTINCT FROM b` |
| --- | --- | --- | --- |
| 10 | 12 | TRUE | TRUE |
| 10 | 10 | FALSE | FALSE |
| `NULL` | `NULL` | UNKNOWN | FALSE |
| `NULL` | 0 | UNKNOWN | TRUE |
| 0 | `NULL` | UNKNOWN | TRUE |

Nếu cột có thể `NULL`, điều kiện `WHERE old_value <> new_value` có thể bỏ sót thay đổi **từ NULL sang giá trị hoặc ngược lại**. `IS DISTINCT FROM` diễn đạt rõ “hai giá trị có khác nhau, kể cả trường hợp thiếu dữ liệu”.

## 11. UPDATE với nhiều cột được lấy từ cùng một nguồn

Một câu `UPDATE` có thể thay đổi **nhiều cột** cho một hàng đích:

~~~sql
UPDATE target AS t
SET
    col_a = s.new_a,
    col_b = s.new_b,
    modified_at = CURRENT_TIMESTAMP
FROM source AS s
WHERE s.key = t.key;
~~~

Tính chính xác **một hàng nguồn trên mỗi hàng đích** càng quan trọng khi cập nhật nhiều cột: các giá trị mới phải đến từ **cùng một bản ghi nguồn đúng nghĩa nghiệp vụ**, không phải những bản ghi được chọn tùy tiện.

### 11.1. Ví dụ mở rộng với kế hoạch kho

Giả sử khi phê duyệt kế hoạch, ngoài tồn kho ta còn muốn ghi chú vào một cột `restock_note` ở bảng sản phẩm. Bộ dữ liệu mẫu **không có cột đó**, nên đoạn dưới chỉ là **mẫu cấu trúc**, không được chạy nguyên văn:

~~~sql
-- Mau minh hoa, gia dinh target co cot restock_note.
UPDATE products AS p
SET
    stock_qty = r.target_stock,
    restock_note = r.plan_note
FROM restock_plan AS r
WHERE r.product_id = p.product_id
  AND r.approved = TRUE;
~~~

Ở đây `r.target_stock` và `r.plan_note` đến từ **cùng hàng kế hoạch r**. Nếu bảng kế hoạch không đảm bảo một hàng trên mỗi `product_id`, cần chuẩn hóa nguồn trước khi dùng.

### 11.2. Không giả định SET có thứ tự đánh giá giống một chương trình tuần tự

Khi viết:

~~~sql
SET a = b,
    b = a
~~~

ý nghĩa và quy tắc tham chiếu giá trị cũ/mới phụ thuộc cú pháp SQL dialect. Trong PostgreSQL, các biểu thức gán thông thường dùng **giá trị của hàng đích trước khi cập nhật**, nên kiểu gán này có thể đổi chỗ hai giá trị nếu hai cột tương thích. Không nên suy diễn rằng lệnh `SET a = b` được hoàn tất trước rồi câu `b = a` mới đọc `a` đã sửa.

Khi cần công thức cập nhật phức tạp, hãy tính rõ các giá trị dự kiến trong một truy vấn nguồn/CTE và kiểm soát tính tương thích thay vì phụ thuộc vào trực giác về thứ tự gán.

## 12. UPDATE không có điều kiện và những trường hợp nguy hiểm

Trong SQL, một câu:

~~~sql
UPDATE lab_up274_products
SET price_review_required = TRUE;
~~~

là cú pháp hợp lệ và **cập nhật toàn bộ bảy hàng**. Điều đó có thể đúng nếu yêu cầu thực sự là “đánh dấu tất cả sản phẩm”, nhưng thường là rủi ro khi người viết quên `WHERE`.

Đối với `UPDATE FROM`, hai lỗi còn dễ nhầm:

1. **Thiếu điều kiện nối nguồn tới đích**: nhiều sản phẩm có thể lấy giá trị của những kế hoạch không liên quan.
2. **Có điều kiện nối nhưng thiếu điều kiện nghiệp vụ**: cập nhật cả sản phẩm INACTIVE, kế hoạch chưa duyệt hoặc kế hoạch mục tiêu thấp hơn tồn kho hiện tại.

Hãy phân biệt:

~~~sql
-- Dieu kien LIEN KET:
r.product_id = p.product_id

-- Dieu kien NGHIEP VU:
r.approved = TRUE
AND p.status = 'ACTIVE'
AND r.target_stock > p.stock_qty
~~~

Một phép nối đúng khóa **chưa đủ** để xác định phạm vi cập nhật đúng.

### 12.1. Lệnh UPDATE có thể trả 0 hàng

Nếu không có hàng thỏa `WHERE` hoặc không có hàng ghép từ `FROM`, số hàng cập nhật có thể là **0**. Điều này có thể bình thường khi không có sản phẩm cần sửa, hoặc cảnh báo rằng dữ liệu nguồn/điều kiện ghép không đúng.

Nên phân biệt:

- **Không có đối tượng nào cần cập nhật**.
- **Có đối tượng nhưng không khớp khóa nguồn**.
- **Bị lọc bởi điều kiện trạng thái/phê duyệt**.
- **Giá mới bằng giá cũ nên bị loại bởi `IS DISTINCT FROM`**.

Đừng thay điều kiện `WHERE` bằng một điều kiện rộng hơn chỉ để nhìn thấy “có hàng được cập nhật” mà chưa hiểu lý do.

## 13. Quy trình an toàn: xem trước, cập nhật thử, kiểm tra, rồi COMMIT

Với cập nhật hàng loạt, đặc biệt khi lấy giá trị từ bảng khác, nên dùng **quy trình có thể quan sát được**.

### Bước 1 — Xác nhận yêu cầu và khóa

Ghi rõ:

~~~text
Bang dich:      lab_up274_products
Nguon:          lab_up274_restock_plan
Khoa lien ket:  product_id
Gia tri moi:    stock_qty := target_stock
Phan vi:        approved = true, ACTIVE, target_stock > stock_qty
Ky vong:        3 san pham (101, 103, 104)
~~~

Không cập nhật theo **tên sản phẩm** nếu khóa ổn định đã có, vì tên có thể trùng, bị sửa chính tả hoặc thay đổi theo thời gian.

### Bước 2 — Dùng SELECT xem chính xác các hàng sẽ đổi

~~~sql
SELECT
    p.product_id,
    p.stock_qty AS before_stock,
    r.target_stock AS after_stock
FROM lab_up274_products AS p
JOIN lab_up274_restock_plan AS r
    ON r.product_id = p.product_id
WHERE r.approved = TRUE
  AND p.status = 'ACTIVE'
  AND r.target_stock > p.stock_qty
ORDER BY p.product_id;
~~~

Đặc biệt chú ý số hàng **của `SELECT` sau phép nối**. Nếu một sản phẩm xuất hiện nhiều lần, cần xem lại tính duy nhất của nguồn trước khi `UPDATE`.

### Bước 3 — Thử UPDATE trong transaction

~~~sql
BEGIN;

UPDATE lab_up274_products AS p
SET stock_qty = r.target_stock
FROM lab_up274_restock_plan AS r
WHERE r.product_id = p.product_id
  AND r.approved = TRUE
  AND p.status = 'ACTIVE'
  AND r.target_stock > p.stock_qty
RETURNING p.product_id, p.stock_qty;

SELECT
    product_id, stock_qty
FROM lab_up274_products
WHERE product_id IN (101, 103, 104)
ORDER BY product_id;

ROLLBACK;
~~~

Trong cùng transaction, `SELECT` nhìn thấy các giá trị vừa cập nhật. `ROLLBACK` sau đó **hủy thay đổi trên bảng**, nên bộ dữ liệu vẫn sẵn sàng cho bài tiếp theo.

### Bước 4 — Chỉ lưu nếu đã được phép

Đối với một thao tác thực tế đã được phê duyệt, thay `ROLLBACK` bằng `COMMIT` **sau khi đã xác nhận** phạm vi và kết quả mong muốn. Không tự chuyển các ví dụ thử nghiệm trong bài thành cập nhật production.

### Bước 5 — Lưu dấu vết phù hợp

Trong hệ thống nghiệp vụ, có thể cần biết **ai cập nhật, thời điểm, lý do, giá trị trước/sau và nguồn quyết định**. Cột `updated_at` chỉ trả lời một phần câu hỏi; nếu cần lịch sử đầy đủ, nên dùng **audit log/bảng lịch sử/CDC** theo thiết kế, thay vì nghĩ rằng `UPDATE` tự lưu mọi bản cũ.

## 14. RETURNING, số hàng ảnh hưởng và giá trị trước/sau

PostgreSQL hỗ trợ `RETURNING` sau `UPDATE` để lấy các giá trị của hàng được cập nhật.

~~~sql
BEGIN;

UPDATE lab_up274_products AS p
SET stock_qty = r.target_stock
FROM lab_up274_restock_plan AS r
WHERE r.product_id = p.product_id
  AND r.approved = TRUE
  AND p.status = 'ACTIVE'
  AND r.target_stock > p.stock_qty
RETURNING p.product_id, p.sku, p.stock_qty;

ROLLBACK;
~~~

`RETURNING p.stock_qty` ở mẫu này là **giá trị mới**. Không nên suy luận một câu `RETURNING p.stock_qty` sẽ tự trả cả giá trị cũ.

Nếu cần ghi lại cả **tồn cũ và tồn mới**, có thể chạy `SELECT` xem trước trong một giao dịch phù hợp, hoặc dùng cơ chế log/audit hay các khả năng `RETURNING` theo **đúng phiên bản PostgreSQL**. Cú pháp tham chiếu `OLD`/`NEW` trong `RETURNING` có khác biệt theo phiên bản, nên bài này dùng mẫu chung là **`RETURNING` giá trị mới** thay vì dựa vào một tính năng chưa chắc có trên máy chủ thực hành.

### 14.1. Số hàng được UPDATE khác số hàng nguồn

Nếu một sản phẩm có nhiều báo giá, bảng nguồn có thể có nhiều hàng nhưng `UPDATE` không có nghĩa sẽ tạo thêm nhiều hàng sản phẩm. Nó **sửa hàng đã có**, không phải `INSERT`.

Đặc biệt, số hàng cập nhật được báo bởi client/`RETURNING` không phải bằng chứng rằng **bảng nguồn chỉ có một hàng cho mỗi sản phẩm**: vấn đề chọn nguồn thiếu tính xác định vẫn có thể tồn tại ngay khi kết quả cho “mỗi sản phẩm sửa một lần”.

## 15. Tính đúng khi chạy lại: idempotency và đồng bộ

Với công việc đồng bộ lặp lại, cần phân biệt hai kiểu cập nhật:

**Kiểu gán giá trị mục tiêu:**

~~~sql
SET stock_qty = r.target_stock
~~~

Nếu nguồn không đổi, cập nhật lại vẫn đặt cùng `stock_qty`. Có thể thêm `WHERE p.stock_qty IS DISTINCT FROM r.target_stock` để tránh ghi không cần thiết.

**Kiểu tăng tương đối:**

~~~sql
SET stock_qty = p.stock_qty + r.add_qty
~~~

Mỗi lần chạy sẽ cộng thêm một lần. Nếu tiến trình được khởi động lại và câu lệnh được chạy hai lần, số lượng có thể bị cộng đôi. Trong nghiệp vụ tồn kho, thường phải lưu **mã giao dịch/đợt nhập duy nhất** hoặc dùng mô hình sổ cái nhập xuất để bảo đảm một sự kiện không được áp dụng hai lần.

Tương tự:

~~~sql
SET unit_price = ROUND(unit_price * 1.05, 2)
~~~

có thể tăng giá nhiều lần nếu chạy lại. Còn:

~~~sql
SET unit_price = latest_quote.offered_price * 1.20
~~~

là phép gán theo giá nguồn đã chọn, thường có tính lặp lại ổn định hơn nếu nguồn không đổi.

**Một câu UPDATE đúng về cú pháp chưa có nghĩa là một tác vụ đồng bộ an toàn khi được chạy lại.**

## 16. Giao dịch, đồng thời và dữ liệu nguồn thay đổi

Trong một database có nhiều người dùng, dữ liệu có thể thay đổi trong khoảng thời gian giữa **`SELECT` xem trước** và **`UPDATE` thực tế**.

Một số tình huống:

- Nhân viên khác phê duyệt hoặc hủy kế hoạch nhập hàng.
- Báo giá mới được duyệt trong khi tiến trình cập nhật giá đang chạy.
- Một giao dịch bán mới được ghi nhận khiến báo cáo tổng tháng thay đổi.
- Hai phiên cùng sửa một sản phẩm, có khả năng chờ khóa hoặc cập nhật chồng lên nhau.

### 16.1. Transaction và mức cô lập

`BEGIN`/`COMMIT` giúp gom các câu lệnh thành một giao dịch, nhưng **không tự đảm bảo** rằng mọi `SELECT` trong giao dịch đều quan sát cùng một snapshot dưới mọi mức cô lập.

Trong PostgreSQL, dưới mức `READ COMMITTED` thông dụng, các câu lệnh khác nhau thường có snapshot riêng; điều kiện và hàng thực tế có thể đổi nếu phiên khác commit giữa các câu. Nếu quy trình cần một ảnh chụp nhất quán hoặc quy tắc khóa chặt hơn, cần cân nhắc **mức cô lập**, khóa hàng và thiết kế giao dịch phù hợp.

### 16.2. UPDATE thường khóa các hàng đích được sửa

PostgreSQL sẽ sử dụng cơ chế khóa hàng phù hợp cho các hàng đích bị cập nhật. Các transaction có thể **chờ nhau**, và khi cập nhật nhiều hàng theo những thứ tự khác nhau còn có nguy cơ **deadlock**.

Không nên kéo dài transaction khi không cần thiết. Nếu cần phối hợp giữa nhiều bảng và nhiều bước nghiệp vụ, hãy thiết kế thứ tự thao tác, thời gian khóa, retry khi lỗi đồng thời và xử lý rollback phù hợp.

### 16.3. SELECT FOR UPDATE không tự khóa “mọi thay đổi nguồn”

Khi thực sự cần ngăn một số thay đổi đồng thời, có thể dùng khóa rõ ràng trên những hàng được chọn. Nhưng `SELECT ... FOR UPDATE` chỉ khóa những hàng phù hợp theo cơ chế của hệ quản trị; nó **không tự khóa mọi bản ghi nguồn có thể được thêm trong tương lai**, cũng không giải quyết toàn bộ vấn đề snapshot.

Trong bài thực hành, dùng `BEGIN ... UPDATE ... RETURNING ... ROLLBACK` là đủ để quan sát ý nghĩa lệnh; các chiến lược đồng thời nâng cao cần được thiết kế theo yêu cầu hệ thống thật.

## 17. Hiệu năng khi cập nhật từ bảng khác hoặc truy vấn con

Một câu `UPDATE` có thể đọc nhiều hàng nguồn và sửa nhiều hàng đích. Hiệu năng phụ thuộc cách ghép, bộ lọc, chỉ mục, tổng hợp và số hàng bị ghi.

### 17.1. Chỉ mục trên khóa ghép

Trong dữ liệu mẫu:

- `products.product_id` có chỉ mục nhờ `PRIMARY KEY`.
- `restock_plan.product_id` cũng có chỉ mục nhờ `PRIMARY KEY`.
- `supplier_quotes.product_id` là khóa ngoại nhưng PostgreSQL **không tự tạo chỉ mục chỉ vì đó là khóa ngoại**.
- `sales.product_id` là khóa ngoại và cũng không tự bảo đảm có chỉ mục.

Trong tải thực tế, có thể xem xét các chỉ mục như:

~~~sql
-- DDL minh hoa; khong bat buoc cho bang mau nho.
CREATE INDEX lab_up274_quotes_lookup_idx
ON lab_up274_supplier_quotes (
    product_id, approval_status, valid_from DESC, quote_id DESC
);

CREATE INDEX lab_up274_sales_lookup_idx
ON lab_up274_sales (product_id, sold_on, sale_status);
~~~

Chỉ mục cần được đánh giá theo truy vấn thường chạy, phân bố dữ liệu và chi phí ghi. **Không nên tạo mọi chỉ mục chỉ vì một ví dụ SQL có dùng cột đó**.

### 17.2. Tổng hợp nguồn một lần so với correlated subquery

Đối với hàng triệu sản phẩm và giao dịch, `UPDATE FROM` nguồn đã `GROUP BY product_id` có thể là một cách biểu đạt tập hợp rõ ràng. Truy vấn con tương quan cũng có thể được bộ tối ưu chuyển hóa hoặc sử dụng chỉ mục phù hợp; không thể khẳng định một kiểu viết **luôn nhanh hơn** kiểu khác mà không xem kế hoạch và dữ liệu.

Ưu tiên **đúng ngữ nghĩa**, kiểm soát bội số nguồn và phạm vi cập nhật, rồi mới tối ưu.

### 17.3. EXPLAIN trên UPDATE

~~~sql
EXPLAIN
UPDATE lab_up274_products AS p
SET stock_qty = r.target_stock
FROM lab_up274_restock_plan AS r
WHERE r.product_id = p.product_id
  AND r.approved = TRUE
  AND p.status = 'ACTIVE'
  AND r.target_stock > p.stock_qty;
~~~

Trong PostgreSQL, `EXPLAIN` **không có `ANALYZE`** hiển thị kế hoạch dự kiến mà **không thực thi lệnh UPDATE**. Ngược lại, **`EXPLAIN ANALYZE UPDATE ...` sẽ thực thi cập nhật thực sự** trong ngữ cảnh giao dịch; không được dùng trên dữ liệu thật mà tưởng đó chỉ là một thao tác xem kế hoạch không ghi.

### 17.4. Tránh cập nhật những hàng không đổi

Điều kiện:

~~~sql
AND p.stock_qty IS DISTINCT FROM r.target_stock
~~~

có thể giảm số hàng đích bị cập nhật khi mục tiêu chỉ là đồng bộ. Một `UPDATE` gán lại cùng giá trị vẫn có thể phát sinh các chi phí và tác động như ghi phiên bản hàng, trigger hoặc thay đổi metadata tùy hệ. Khi dùng điều kiện loại hàng không đổi, cần xác định những tác động phụ đó có phải **được yêu cầu** hay không.

## 18. Khác biệt giữa các SQL dialect

Ý tưởng **cập nhật giá trị từ bảng khác** phổ biến, nhưng cú pháp nối nguồn khác nhau giữa hệ quản trị. Các ví dụ sau là **mẫu phương ngữ**, giả định đã có bảng và cột tương ứng; không phải tất cả đều chạy trực tiếp trên bộ bảng PostgreSQL `lab_up274_*`.

### 18.1. PostgreSQL: UPDATE ... FROM

~~~sql
UPDATE lab_up274_products AS p
SET stock_qty = r.target_stock
FROM lab_up274_restock_plan AS r
WHERE r.product_id = p.product_id
  AND r.approved = TRUE
  AND p.status = 'ACTIVE'
  AND r.target_stock > p.stock_qty;
~~~

Trong PostgreSQL, bảng đích đứng ngay sau `UPDATE`; các bảng nguồn sau `FROM` và điều kiện ghép đặt ở `WHERE`. Cú pháp `RETURNING` có thể lấy giá trị hàng được sửa.

### 18.2. SQL Server: UPDATE alias ... FROM ... JOIN ...

Ví dụ T-SQL:

~~~sql
-- T-SQL: gia su dbo.Products va dbo.RestockPlan da ton tai.
UPDATE p
SET p.stock_qty = r.target_stock
FROM dbo.Products AS p
JOIN dbo.RestockPlan AS r
    ON r.product_id = p.product_id
WHERE r.approved = 1
  AND p.status = 'ACTIVE'
  AND r.target_stock > p.stock_qty;
~~~

SQL Server có cú pháp `OUTPUT INSERTED...`/`DELETED...` trong các thao tác DML theo ngữ cảnh phù hợp, thay vì dùng nguyên `RETURNING` của PostgreSQL.

**Cảnh giác:** `UPDATE FROM` với nhiều hàng nguồn khớp cùng một hàng đích cũng không được xem là đã có quy tắc chọn “hàng đúng” nếu bạn không tự xác định. Dùng nguồn đã tổng hợp hoặc xếp hạng duy nhất.

### 18.3. MySQL: UPDATE ... JOIN ... SET

Ví dụ MySQL:

~~~sql
-- MySQL: gia su products va restock_plan da ton tai.
UPDATE products AS p
JOIN restock_plan AS r
    ON r.product_id = p.product_id
SET p.stock_qty = r.target_stock
WHERE r.approved = TRUE
  AND p.status = 'ACTIVE'
  AND r.target_stock > p.stock_qty;
~~~

Khác PostgreSQL, dạng `UPDATE JOIN` của MySQL đặt phép nối **trước `SET`**. Để lấy giá trị mới, cơ chế trả kết quả và API của driver có thể khác `RETURNING`.

### 18.4. SQLite: UPDATE FROM phụ thuộc phiên bản

SQLite hỗ trợ dạng `UPDATE ... FROM` kể từ **SQLite 3.33.0**. Ví dụ:

~~~sql
-- SQLite 3.33+; gia su products, restock_plan da ton tai.
UPDATE products AS p
SET stock_qty = r.target_stock
FROM restock_plan AS r
WHERE r.product_id = p.product_id
  AND r.approved = 1
  AND r.target_stock > p.stock_qty;
~~~

Với SQLite cũ hơn hoặc môi trường không cho `UPDATE FROM`, có thể dùng truy vấn con tương quan trong `SET` và `EXISTS` ở `WHERE`. Tính năng `RETURNING` của SQLite có từ **3.35.0**; những ứng dụng dùng thư viện SQLite nhúng cần biết phiên bản thực tế.

### 18.5. Oracle: correlated subquery hoặc MERGE

Ví dụ Oracle với cú pháp `MERGE` thường gặp:

~~~sql
-- Oracle SQL minh hoa, khong phai PostgreSQL.
MERGE INTO products p
USING restock_plan r
ON (r.product_id = p.product_id)
WHEN MATCHED THEN
    UPDATE SET p.stock_qty = r.target_stock
    WHERE r.approved = 1
      AND p.status = 'ACTIVE'
      AND r.target_stock > p.stock_qty;
~~~

`MERGE` có quy tắc riêng, đặc biệt với khóa khớp và khả năng một hàng đích bị cùng nguồn tác động nhiều lần. Oracle ở các phiên bản mới còn có những khả năng cú pháp cập nhật nâng cao, nhưng **không nên tự giả định mọi phiên bản Oracle dùng đúng `UPDATE FROM` PostgreSQL**.

### 18.6. Bảng tóm tắt

| Nhu cầu | PostgreSQL | MySQL | SQL Server | SQLite | Oracle |
| --- | --- | --- | --- | --- | --- |
| Cập nhật từ bảng khác | `UPDATE ... SET ... FROM ... WHERE ...` | `UPDATE ... JOIN ... SET ... WHERE ...` | `UPDATE alias SET ... FROM ... JOIN ...` | `UPDATE ... FROM` ở bản phù hợp | Truy vấn con, `MERGE` hoặc cú pháp của bản đang dùng |
| Scalar subquery trong `SET` | Có | Có | Có | Có | Có |
| Lọc bằng `EXISTS`/`NOT EXISTS` | Có | Có | Có | Có | Có |
| Xếp hạng nguồn với `ROW_NUMBER` | Có | MySQL 8.0+ | Có | SQLite bản hỗ trợ window | Có |
| `DISTINCT ON` | Có | Không cùng cú pháp | Không cùng cú pháp | Không cùng cú pháp | Không cùng cú pháp |
| Trả dữ liệu vừa sửa | `RETURNING` | API/cơ chế khác tùy bản | `OUTPUT` | `RETURNING` từ 3.35.0 | `RETURNING ... INTO` theo ngữ cảnh |
| So giá trị kể cả `NULL` | `IS DISTINCT FROM` | Có toán tử NULL-safe `<=>` | Có `IS DISTINCT FROM` ở bản phù hợp | Có `IS DISTINCT FROM` ở bản phù hợp | Tùy phiên bản/cách biểu đạt |

Khi chuyển hệ, cần kiểm tra **phiên bản thật, kiểu dữ liệu, logic `NULL`, xử lý hàng nguồn trùng và giao dịch**, chứ không chỉ sửa vài từ khóa.

## 19. Những lỗi thường gặp khi UPDATE từ nguồn ngoài

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Nhiều sản phẩm bị sửa bằng cùng một giá kế hoạch | `UPDATE FROM` thiếu điều kiện ghép khóa | Thêm `source.product_id = target.product_id` |
| Giá mới đôi khi lấy báo giá cũ, đôi khi báo giá khác | Một sản phẩm khớp nhiều báo giá | Dùng `ROW_NUMBER`/`DISTINCT ON`/tổng hợp để chọn **một hàng nguồn** |
| Scalar subquery báo lỗi nhiều hàng | `SET col = (SELECT ...)` trả hơn một hàng | Chọn quy tắc một hàng hoặc tổng hợp |
| `unit_price` bị gán `NULL` | Không có hàng nguồn nhưng `SET` dùng scalar subquery trực tiếp | Dùng `WHERE EXISTS` hoặc quy tắc thay thế rõ ràng |
| `UPDATE FROM` không sửa sản phẩm 107 khi tính bán tháng 10 | Không có nhóm dữ liệu bán tương ứng | Bổ sung tập sản phẩm đầy đủ và `COALESCE`, hoặc scalar aggregate |
| Tổng số lượng bán cao hơn dự kiến | Dòng CANCELLED hoặc ngoài kỳ lọt vào nguồn | Lọc đúng trạng thái và khoảng ngày trước tổng hợp |
| Cập nhật cả sản phẩm INACTIVE | Thiếu điều kiện bảng đích | Thêm `p.status = 'ACTIVE'` khi nghiệp vụ yêu cầu |
| Tồn kho bị giảm dù chỉ muốn bổ sung | Không kiểm tra `target_stock > stock_qty` | Thêm điều kiện mục tiêu lớn hơn tồn cũ |
| Đếm số hàng nguồn rồi cho rằng đó là số sản phẩm bị sửa | Một nguồn có thể có nhiều hàng trên cùng khóa | Kiểm tra bội số và số hàng đích riêng |
| Viết `SET p.stock_qty = ...` trong PostgreSQL | Không đúng cách viết cột đích của dialect | Dùng `SET stock_qty = ...` |
| Viết nguồn trong `FROM` nhưng quên điều kiện tương quan | Nguồn không được nối đúng hàng đích | Kiểm tra đường liên kết từng khóa |
| Viết `WHERE old_col <> new_col` và bỏ sót thay đổi NULL | So sánh với `NULL` có thể UNKNOWN | Dùng `IS DISTINCT FROM` hoặc phép so NULL-safe tương ứng |
| Chạy lệnh tăng giá phần trăm hai lần | Cập nhật tương đối không có cơ chế chống lặp | Có mã lần cập nhật/quy tắc idempotency phù hợp |
| `RETURNING` không trả giá cũ như kỳ vọng | Biểu thức thông thường trả trạng thái mới | Dùng bước xem trước, audit hoặc tính năng đúng phiên bản |
| Chạy `EXPLAIN ANALYZE UPDATE` như một truy vấn chỉ đọc | `ANALYZE` thực thi câu lệnh | Chỉ dùng `EXPLAIN` không ANALYZE khi không muốn cập nhật |
| Chạy ví dụ lỗi rồi tiếp tục trong transaction PostgreSQL | Transaction có thể chuyển sang trạng thái aborted | `ROLLBACK` hoặc rollback savepoint phù hợp |
| Thay `ROLLBACK` thành `COMMIT` khi chưa xác minh | Thay đổi được lưu thật | Xem trước, thử, đối chiếu rồi mới commit khi được phép |

## 20. Bài tập thực hành có đáp án

Các bài dựa trên bốn bảng `lab_up274_*` ở mục 2. Hãy xem mỗi bài là **một tình huống độc lập trên dữ liệu ban đầu**. Các đáp án có lệnh ghi dùng `BEGIN ... ROLLBACK` để bạn quan sát kết quả mà không ảnh hưởng bài sau.

### Bài 1 — Cập nhật tồn kho từ bảng kế hoạch

**Yêu cầu:** chỉ cập nhật sản phẩm ACTIVE có kế hoạch đã duyệt và `target_stock` lớn hơn tồn hiện tại.

**Đáp án:**

~~~sql
BEGIN;

UPDATE lab_up274_products AS p
SET stock_qty = r.target_stock
FROM lab_up274_restock_plan AS r
WHERE r.product_id = p.product_id
  AND r.approved = TRUE
  AND p.status = 'ACTIVE'
  AND r.target_stock > p.stock_qty
RETURNING p.product_id, p.stock_qty;

ROLLBACK;
~~~

Kết quả là **101: 18**, **103: 10**, **104: 6**. Sản phẩm 102 không giảm tồn; 105 chưa duyệt; 106 INACTIVE.

### Bài 2 — Xem trước hàng sẽ cập nhật

**Yêu cầu:** chưa chạy `UPDATE`, chỉ liệt kê tồn cũ và tồn mục tiêu cho những hàng đủ điều kiện của bài 1.

**Đáp án:**

~~~sql
SELECT
    p.product_id,
    p.stock_qty AS old_stock,
    r.target_stock AS proposed_stock
FROM lab_up274_products AS p
JOIN lab_up274_restock_plan AS r
    ON r.product_id = p.product_id
WHERE r.approved = TRUE
  AND p.status = 'ACTIVE'
  AND r.target_stock > p.stock_qty
ORDER BY p.product_id;
~~~

Có **ba hàng**: 101 (4 → 18), 103 (3 → 10), 104 (0 → 6).

### Bài 3 — Chọn báo giá mới nhất trong scalar subquery

**Yêu cầu:** cập nhật giá bán sản phẩm ACTIVE thành **120% báo giá APPROVED gần nhất**; nếu cùng ngày, chọn `quote_id` lớn hơn; sản phẩm không có báo giá duyệt không bị sửa.

**Đáp án:**

~~~sql
BEGIN;

UPDATE lab_up274_products AS p
SET unit_price = (
    SELECT ROUND(q.offered_price * 1.20, 2)
    FROM lab_up274_supplier_quotes AS q
    WHERE q.product_id = p.product_id
      AND q.approval_status = 'APPROVED'
    ORDER BY q.valid_from DESC, q.quote_id DESC
    LIMIT 1
)
WHERE p.status = 'ACTIVE'
  AND EXISTS (
      SELECT 1
      FROM lab_up274_supplier_quotes AS q
      WHERE q.product_id = p.product_id
        AND q.approval_status = 'APPROVED'
  )
RETURNING p.product_id, p.unit_price;

ROLLBACK;
~~~

Các sản phẩm được cập nhật: **101, 102, 103, 105**; giá mới lần lượt **12960, 36000, 228000, 324000**.

### Bài 4 — Vì sao UPDATE FROM trực tiếp báo giá là rủi ro?

Cho câu:

~~~sql
-- Khong thuc thi.
UPDATE lab_up274_products AS p
SET unit_price = q.offered_price
FROM lab_up274_supplier_quotes AS q
WHERE q.product_id = p.product_id
  AND q.approval_status = 'APPROVED';
~~~

**Câu hỏi:** tại sao có thể sai dù điều kiện khóa đã đúng?

**Đáp án:** một sản phẩm có thể có **nhiều báo giá được duyệt**. 101, 103 và 105 đều khớp hai hàng nguồn. PostgreSQL không bảo đảm lấy báo giá nào khi `UPDATE FROM` có nhiều hàng ghép cho cùng một đích. Phải chọn một hàng theo quy tắc như ngày mới nhất và `quote_id` lớn nhất, dùng `ROW_NUMBER() ... WHERE rn = 1` hoặc một kỹ thuật tương đương.

### Bài 5 — Tổng bán tháng 10 bằng truy vấn con tương quan

**Yêu cầu:** đặt `sold_qty_oct` cho **mọi sản phẩm**, kể cả sản phẩm không có dòng bán hàng, theo tổng số lượng `POSTED` trong tháng 10/2026.

**Đáp án:**

~~~sql
BEGIN;

UPDATE lab_up274_products AS p
SET sold_qty_oct = (
    SELECT COALESCE(SUM(s.quantity), 0)
    FROM lab_up274_sales AS s
    WHERE s.product_id = p.product_id
      AND s.sale_status = 'POSTED'
      AND s.sold_on >= DATE '2026-10-01'
      AND s.sold_on < DATE '2026-11-01'
)
RETURNING p.product_id, p.sold_qty_oct;

ROLLBACK;
~~~

Theo ID 101–107, số bán là **5, 6, 2, 1, 7, 8, 0**. `COALESCE` làm sản phẩm 107 (không có bán hàng) nhận 0.

### Bài 6 — Vì sao UPDATE FROM GROUP BY không sửa mọi hàng?

Giả sử ta đã có `sales_summary`:

~~~sql
WITH sales_summary AS (
    SELECT product_id, SUM(quantity) AS sold_qty
    FROM lab_up274_sales
    WHERE sale_status = 'POSTED'
      AND sold_on >= DATE '2026-10-01'
      AND sold_on < DATE '2026-11-01'
    GROUP BY product_id
)
SELECT *
FROM sales_summary
ORDER BY product_id;
~~~

**Câu hỏi:** vì sao dùng `UPDATE ... FROM sales_summary` theo `product_id` có thể bỏ sót sản phẩm 107?

**Đáp án:** `sales_summary` không chứa hàng cho 107 vì sản phẩm đó không có dòng bán hàng. `UPDATE FROM` theo khóa chỉ sửa các hàng đích có đối tác nguồn khớp. Cần dùng correlated aggregate với `COALESCE(SUM(...), 0)` hoặc tạo nguồn đầy đủ bằng `LEFT JOIN` từ danh sách mọi sản phẩm, nếu mục tiêu là đặt lại cả những hàng không có giao dịch.

### Bài 7 — Đánh dấu sản phẩm thiếu báo giá APPROVED

**Yêu cầu:** với sản phẩm ACTIVE không có báo giá được duyệt, đặt `price_review_required = TRUE`.

**Đáp án:**

~~~sql
BEGIN;

UPDATE lab_up274_products AS p
SET price_review_required = TRUE
WHERE p.status = 'ACTIVE'
  AND NOT EXISTS (
      SELECT 1
      FROM lab_up274_supplier_quotes AS q
      WHERE q.product_id = p.product_id
        AND q.approval_status = 'APPROVED'
  )
RETURNING p.product_id, p.price_review_required;

ROLLBACK;
~~~

Kết quả là **104** và **107**. `NOT EXISTS` hỏi đúng điều kiện “không có báo giá APPROVED”.

### Bài 8 — Sửa UPDATE để tránh cập nhật giá không đổi

**Yêu cầu:** dùng CTE đã có cột `proposed_price` theo mỗi `product_id`; chỉ cập nhật những sản phẩm có giá khác đề xuất.

**Đáp án (CTE nguồn đầy đủ):**

~~~sql
BEGIN;

WITH ranked AS (
    SELECT
        q.product_id,
        ROUND(q.offered_price * 1.20, 2) AS proposed_price,
        ROW_NUMBER() OVER (
            PARTITION BY q.product_id
            ORDER BY q.valid_from DESC, q.quote_id DESC
        ) AS rn
    FROM lab_up274_supplier_quotes AS q
    WHERE q.approval_status = 'APPROVED'
)
UPDATE lab_up274_products AS p
SET unit_price = r.proposed_price
FROM ranked AS r
WHERE r.product_id = p.product_id
  AND r.rn = 1
  AND p.status = 'ACTIVE'
  AND p.unit_price IS DISTINCT FROM r.proposed_price
RETURNING p.product_id, p.unit_price;

ROLLBACK;
~~~

Điều kiện `r.rn = 1` chọn một hàng nguồn cho mỗi khóa. `IS DISTINCT FROM` chỉ nhận hàng có giá khác, giúp tránh ghi không cần thiết.

### Bài 9 — Kiểm tra nguồn có nhiều hàng trên mỗi khóa

**Yêu cầu:** tìm những sản phẩm có **trên một báo giá APPROVED**.

**Đáp án:**

~~~sql
SELECT
    product_id,
    COUNT(*) AS approved_quotes
FROM lab_up274_supplier_quotes
WHERE approval_status = 'APPROVED'
GROUP BY product_id
HAVING COUNT(*) > 1
ORDER BY product_id;
~~~

Kết quả: **101, 103, 105**, mỗi sản phẩm có 2 báo giá được duyệt. Đây là thông tin cảnh báo trước khi thiết kế `UPDATE FROM`.

### Bài 10 — Dùng ngưỡng từ truy vấn con trong WHERE

**Yêu cầu:** tăng 5% cho các sản phẩm ACTIVE có giá dưới giá trung bình của danh mục tương ứng.

**Đáp án:**

~~~sql
BEGIN;

UPDATE lab_up274_products AS p
SET unit_price = ROUND(p.unit_price * 1.05, 2)
WHERE p.status = 'ACTIVE'
  AND p.unit_price < (
      SELECT AVG(p2.unit_price)
      FROM lab_up274_products AS p2
      WHERE p2.category = p.category
        AND p2.status = 'ACTIVE'
  )
RETURNING p.product_id, p.unit_price;

ROLLBACK;
~~~

Kết quả là các sản phẩm **101, 104, 105**. Đây là phép tăng tương đối nên có rủi ro tăng nhiều lần nếu chạy lại và commit ngoài ý muốn.

### Bài 11 — Phân biệt không có nguồn với nguồn NULL

**Câu hỏi:** khi dùng:

~~~sql
SET some_col = (
    SELECT s.some_value
    FROM source_table AS s
    WHERE s.key = t.key
)
~~~

thì điều gì xảy ra nếu không có hàng khớp? Khác thế nào với `UPDATE FROM`?

**Đáp án:** scalar subquery không có hàng trả giá trị **`NULL`**. Nếu `some_col NOT NULL`, lệnh có thể bị lỗi; nếu nullable, có thể lưu `NULL`. Với `UPDATE FROM source_table s WHERE s.key = t.key`, hàng đích **không có nguồn khớp** thì **không được cập nhật** trong phép nối đó. Cần chọn theo nghiệp vụ chứ không chỉ theo độ ngắn câu SQL.

### Bài 12 — Viết lại cập nhật tồn kho bằng EXISTS và truy vấn con

**Yêu cầu:** không dùng `UPDATE FROM`. Vẫn cập nhật hàng ACTIVE có kế hoạch được duyệt, chỉ tăng tồn lên mức mục tiêu.

**Đáp án:**

~~~sql
BEGIN;

UPDATE lab_up274_products AS p
SET stock_qty = (
    SELECT r.target_stock
    FROM lab_up274_restock_plan AS r
    WHERE r.product_id = p.product_id
      AND r.approved = TRUE
      AND r.target_stock > p.stock_qty
)
WHERE p.status = 'ACTIVE'
  AND EXISTS (
      SELECT 1
      FROM lab_up274_restock_plan AS r
      WHERE r.product_id = p.product_id
        AND r.approved = TRUE
        AND r.target_stock > p.stock_qty
  )
RETURNING p.product_id, p.stock_qty;

ROLLBACK;
~~~

Kết quả là **101, 103, 104** với tồn mới **18, 10, 6**. Do `restock_plan.product_id` là khóa chính, scalar subquery có tối đa một hàng nguồn khớp. `EXISTS` giúp loại những sản phẩm không đủ điều kiện trước khi phép gán được áp dụng.

## 21. Ghi nhớ

| Mục tiêu | Mẫu SQL PostgreSQL | Điều quan trọng |
| --- | --- | --- |
| Lấy giá trị trực tiếp từ bảng khác | `UPDATE t SET c = s.v FROM source s WHERE s.key = t.key` | **Ghép đúng khóa**; nguồn phải duy nhất theo mỗi hàng đích |
| Tính một giá trị bằng truy vấn con | `SET c = (SELECT v FROM source WHERE key = t.key)` | Trả **tối đa một hàng**; tập rỗng cho `NULL` |
| Chỉ cập nhật khi có nguồn | `WHERE EXISTS (SELECT 1 ... WHERE s.key = t.key)` | Tránh cập nhật các hàng không có nguồn hợp lệ |
| Cập nhật khi **không** có bản ghi liên quan | `WHERE NOT EXISTS (SELECT 1 ... )` | Phù hợp để đánh dấu thiếu dữ liệu |
| Chọn báo giá gần nhất | `ROW_NUMBER() OVER (PARTITION BY key ORDER BY date DESC, id DESC)` | Xác định quy tắc phá hòa và chỉ lấy `rn = 1` |
| Chuẩn bị nguồn tổng hợp | `WITH summary AS (SELECT key, SUM(...) GROUP BY key) UPDATE ... FROM summary` | Một hàng trên mỗi khóa; xử lý khóa không có nhóm nguồn |
| Đặt thống kê về 0 khi không có hàng | `COALESCE(SUM(...), 0)` trong scalar aggregate | Chỉ dùng khi **0** là quy tắc nghiệp vụ hợp lệ |
| Tránh cập nhật không đổi | `WHERE old IS DISTINCT FROM proposed` | So được cả giá trị nullable và tránh ghi dư |
| Xem kết quả cập nhật | `RETURNING ...` | Nhận giá trị hàng vừa sửa; kiểm tra cú pháp theo dialect |
| Thử nghiệm không lưu thay đổi | `BEGIN; UPDATE ...; ROLLBACK;` | Dùng database thực hành, không giả định rollback sequence |
| Tối ưu truy vấn cập nhật | Xem bội số nguồn, chỉ mục và `EXPLAIN` | `EXPLAIN ANALYZE UPDATE` **có thực thi UPDATE** |

Trước khi chạy một câu `UPDATE` có dữ liệu từ nơi khác, hãy tự hỏi:

1. **“Hàng đích nào sẽ bị sửa?”** — Xác định rõ điều kiện `WHERE` và trạng thái nghiệp vụ.
2. **“Mỗi hàng đích lấy dữ liệu từ đúng một nguồn nào?”** — Kiểm tra khóa liên kết và xử lý nguồn nhiều hàng bằng xếp hạng hoặc tổng hợp.
3. **“Nếu không có nguồn hoặc có giá trị NULL thì chuyện gì xảy ra?”** — `UPDATE FROM` và scalar subquery có hành vi khác nhau.
4. **“Tôi sẽ xác minh và hoàn tác thế nào?”** — Xem trước bằng `SELECT`, thử bằng transaction, sử dụng `RETURNING`, chỉ commit khi được phép.

Nắm chắc bốn câu hỏi này giúp bạn cập nhật dữ liệu từ truy vấn con hoặc bảng khác **đúng đối tượng, đúng giá trị, có thể kiểm chứng**, tránh những lỗi nguy hiểm mà cú pháp SQL hợp lệ không tự ngăn được.
