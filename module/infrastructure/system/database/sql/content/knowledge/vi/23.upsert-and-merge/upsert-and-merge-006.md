# Phân biệt thêm mới, cập nhật và bỏ qua dữ liệu

Khi nhập danh mục sản phẩm từ hệ thống bên ngoài, không phải hàng nào cũng cần được chèn vào cơ sở dữ liệu. Một mã sản phẩm **chưa tồn tại** cần được **thêm mới**; một mã **đã tồn tại nhưng có dữ liệu mới hơn** cần được **cập nhật**; một mã **đã có dữ liệu giống hệt hoặc nguồn gửi lại bản cũ** có thể được **bỏ qua**. Đôi khi còn xuất hiện tình huống khó hơn: hai bản ghi có **cùng phiên bản** nhưng nội dung khác nhau, không nên tùy tiện ghi đè mà cần **rà soát xung đột**.

Đó là bài toán **Upsert** (*insert or update*) và **MERGE**. Hãy phân biệt hai tầng:

1. **Quy tắc nghiệp vụ:** khi nào quyết định `INSERT`, `UPDATE`, `SKIP` hoặc chuyển sang kiểm tra dữ liệu?
2. **Cơ chế SQL:** dùng `INSERT ... ON CONFLICT`, `MERGE`, `UPDATE`/`INSERT` có điều kiện hoặc kỹ thuật tương đương để hiện thực quyết định đó một cách đáng tin cậy.

Một câu lệnh “chạy thành công” không đồng nghĩa mọi hàng nguồn đã được cập nhật: một số hàng có thể bị **bỏ qua đúng chủ đích**. Ngược lại, dùng cơ chế upsert mà **không có điều kiện cập nhật** có thể ghi đè dữ liệu mới bằng dữ liệu cũ.

Bài thuộc **Database SQL → Upsert và MERGE**. Ví dụ chính dùng **PostgreSQL**; phần cuối giải thích khác biệt giữa PostgreSQL, SQLite, MySQL, SQL Server và Oracle Database.

## 1. Ba hành động căn bản và một trạng thái cần rà soát

Giả sử mỗi sản phẩm được nhận diện bởi một mã `sku` ổn định. Hệ thống nội bộ có bảng `catalog`, còn lô nhập có bảng `incoming`.

~~~text
                     Mot hang INCOMING
                            |
                            v
              SKU da co trong CATALOG chua?
                      /             \
                    Chua             Da co
                     |                 |
                     v                 v
                   INSERT      So phien ban nguon
                                     |
                 +-------------------+------------------+
                 |                   |                  |
              Moi hon             Cu hon           Bang nhau
                 |                   |                  |
                 v                   v                  v
               UPDATE             SKIP_STALE     So noi dung
                                                   /      \
                                               Giong      Khac
                                                 |          |
                                                 v          v
                                            SKIP_DUPLICATE  REVIEW
~~~

Đây là **một chính sách minh họa**, không phải quy tắc mặc định của SQL. Cụ thể, bài này định nghĩa:

| Tình huống | Hành động | Ý nghĩa |
| --- | --- | --- |
| `sku` chưa có trong bảng đích | **INSERT** | Tạo một bản ghi sản phẩm mới |
| `sku` đã có, `source_version` nguồn **lớn hơn** phiên bản đích | **UPDATE** | Thay thông tin bằng bản mới hơn |
| `sku` đã có, phiên bản nguồn **nhỏ hơn** | **SKIP_STALE** | Không ghi đè bằng dữ liệu lỗi thời |
| `sku` đã có, phiên bản **bằng nhau**, các thuộc tính giống nhau | **SKIP_DUPLICATE** | Bỏ qua lần gửi lại cùng dữ liệu |
| `sku` đã có, phiên bản **bằng nhau** nhưng thuộc tính khác nhau | **REVIEW_CONFLICT** | Bất thường: cùng phiên bản mà nội dung không khớp |

Nếu phiên bản nguồn lớn hơn nhưng giá, tồn và tên vẫn giống nhau, chính sách này vẫn coi là **UPDATE** để ghi nhận `source_version` mới. Đó là cập nhật **metadata phiên bản**, không nhất thiết là thay đổi nghiệp vụ về giá hoặc tồn kho.

**Phân biệt “SKIP” và “lỗi”:** bỏ qua bản cũ hoặc dữ liệu trùng có thể là hành động **thành công theo chính sách**. Còn `REVIEW_CONFLICT` là tình huống cần quyết định nghiệp vụ, không nên tự coi là dữ liệu trùng hợp lệ.

## 2. Cần khóa duy nhất trước khi nói tới upsert

Upsert cần trả lời câu hỏi **“hàng nguồn này tương ứng hàng đích nào?”**. Trong bài, câu trả lời là cột `sku`.

Nếu bảng cho phép nhiều hàng có cùng `sku`, yêu cầu “cập nhật sản phẩm này” trở nên mơ hồ. Vì vậy, schema cần một ràng buộc bảo đảm định danh, ví dụ:

~~~sql
sku VARCHAR(20) PRIMARY KEY
~~~

hoặc, nếu bảng có khóa kỹ thuật khác:

~~~sql
sku VARCHAR(20) NOT NULL UNIQUE
~~~

Hai kiểu khai báo khác nhau ở mô hình khóa, nhưng đều có thể giúp bảo đảm `sku` duy nhất và không `NULL` nếu được khai báo như trên.

### 2.1. Khóa dùng để so phải phản ánh đúng nghiệp vụ

Nếu hai doanh nghiệp (*tenant*) cùng có sản phẩm `PEN`, `sku` đơn lẻ không thể nhận diện duy nhất trong hệ thống chung. Khóa có thể phải là **`(tenant_id, sku)`**:

~~~sql
-- Vi du minh hoa, khong chay voi bang mau cua bai:
CREATE TABLE tenant_catalog (
    tenant_id INTEGER NOT NULL,
    sku VARCHAR(20) NOT NULL,
    product_name TEXT NOT NULL,
    PRIMARY KEY (tenant_id, sku)
);
~~~

Khi đó upsert phải xử lý xung đột theo **đúng cả hai cột**, không chỉ `sku`. Định nghĩa **hàng nào là “đã tồn tại”** bắt đầu từ thiết kế khóa, không phải từ từ khóa `MERGE` hay `ON CONFLICT`.

### 2.2. Không lấy tên sản phẩm làm khóa nếu tên không ổn định

Tên có thể đổi từ “Bút bi” thành “Bút bi xanh” mà sản phẩm vẫn là cùng một đối tượng. Nếu upsert dựa trên `product_name`, hệ thống có thể **chèn nhầm sản phẩm mới** thay vì cập nhật tên. Hãy dùng khóa nghiệp vụ bền vững hoặc định danh bất biến do hệ thống quản lý.

## 3. Dữ liệu thực hành: danh mục hiện tại và lô nhập mới

Ta tạo hai bảng PostgreSQL:

- `lab_up290_catalog`: **bảng đích**, chứa danh mục đã được lưu.
- `lab_up290_incoming`: **bảng staging/nguồn**, chứa một lô dữ liệu sắp đồng bộ.

Hãy chạy đoạn khởi tạo **một lần trong database thực hành riêng** chưa có những bảng cùng tên. Các ví dụ `UPDATE`, `INSERT` và `MERGE` bên dưới sẽ được bao trong `BEGIN ... ROLLBACK` để không làm thay đổi dữ liệu ban đầu sau mỗi lần thử.

### 3.1. Bảng đích

~~~sql
CREATE TABLE lab_up290_catalog (
    sku VARCHAR(20) PRIMARY KEY,
    product_name VARCHAR(100) NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL
        CHECK (unit_price >= 0),
    stock_qty INTEGER NOT NULL
        CHECK (stock_qty >= 0),
    source_version INTEGER NOT NULL
        CHECK (source_version > 0),
    updated_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO lab_up290_catalog
    (sku, product_name, unit_price, stock_qty, source_version)
VALUES
    ('PEN',   'Bút bi xanh',   12000.00, 10, 3),
    ('NOTE',  'Sổ ghi chú',    35000.00,  8, 2),
    ('MOUSE', 'Chuột có dây', 170000.00,  4, 5),
    ('BAG',   'Ba lô',        300000.00,  3, 2),
    ('USB',   'USB 32 GB',     80000.00,  6, 2),
    ('BOOK',  'Sách SQL',      95000.00, 12, 4);
~~~

`source_version` là **số phiên bản của dữ liệu sản phẩm từ nguồn**, được giả định tăng theo từng `sku`. Nó không phải số lần câu SQL đã chạy hay ID toàn cục của lô nhập.

### 3.2. Bảng nguồn của lô đồng bộ

~~~sql
CREATE TABLE lab_up290_incoming (
    sku VARCHAR(20) PRIMARY KEY,
    product_name VARCHAR(100) NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL
        CHECK (unit_price >= 0),
    stock_qty INTEGER NOT NULL
        CHECK (stock_qty >= 0),
    source_version INTEGER NOT NULL
        CHECK (source_version > 0)
);

INSERT INTO lab_up290_incoming
    (sku, product_name, unit_price, stock_qty, source_version)
VALUES
    ('PEN',   'Bút bi xanh',   12500.00, 15, 4),
    ('NOTE',  'Sổ ghi chú',    35000.00,  8, 2),
    ('MOUSE', 'Chuột có dây', 160000.00,  6, 4),
    ('BAG',   'Ba lô',        300000.00,  3, 2),
    ('USB',   'USB 32 GB',     85000.00,  7, 3),
    ('KEY',   'Bàn phím',     240000.00,  5, 1),
    ('PAD',   'Lót chuột',     45000.00,  9, 1);
~~~

**Tập đích có 6 sản phẩm**, **lô nguồn có 7 hàng**. Bảng nguồn có `PRIMARY KEY(sku)` nên trong **lô này** mỗi SKU xuất hiện **tối đa một lần**. Đây là điều kiện rất quan trọng để dùng upsert theo tập mà không có nhiều hàng nguồn tranh nhau một khóa đích.

Xem dữ liệu:

~~~sql
SELECT sku, product_name, unit_price, stock_qty, source_version
FROM lab_up290_catalog
ORDER BY sku;

SELECT sku, product_name, unit_price, stock_qty, source_version
FROM lab_up290_incoming
ORDER BY sku;
~~~

| SKU | Đích: giá | Đích: tồn | Đích: phiên bản | Nguồn: giá | Nguồn: tồn | Nguồn: phiên bản |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BAG | 300000 | 3 | 2 | 300000 | 3 | 2 |
| BOOK | 95000 | 12 | 4 | — | — | — |
| KEY | — | — | — | 240000 | 5 | 1 |
| MOUSE | 170000 | 4 | 5 | 160000 | 6 | 4 |
| NOTE | 35000 | 8 | 2 | 35000 | 8 | 2 |
| PAD | — | — | — | 45000 | 9 | 1 |
| PEN | 12000 | 10 | 3 | 12500 | 15 | 4 |
| USB | 80000 | 6 | 2 | 85000 | 7 | 3 |

Dấu **—** nghĩa là **không có hàng** ở bảng tương ứng, không phải một hàng mang giá trị `NULL`.

### 3.3. Kết quả mong muốn theo chính sách của bài

| SKU nguồn | Kết quả | Lý do |
| --- | --- | --- |
| KEY | **INSERT** | Chưa có trong đích |
| PAD | **INSERT** | Chưa có trong đích |
| PEN | **UPDATE** | Phiên bản 4 mới hơn 3 |
| USB | **UPDATE** | Phiên bản 3 mới hơn 2 |
| NOTE | **SKIP_DUPLICATE** | Cùng phiên bản 2, cùng nội dung |
| BAG | **SKIP_DUPLICATE** | Cùng phiên bản 2, cùng nội dung |
| MOUSE | **SKIP_STALE** | Phiên bản 4 cũ hơn phiên bản 5 |

Sản phẩm **BOOK** không có trong lô nguồn. Vì chính sách đang xét **đồng bộ những hàng nguồn gửi đến**, nó **không bị xóa hay cập nhật** chỉ vì vắng mặt ở lô này.

Tổng cộng: **2 INSERT + 2 UPDATE + 3 SKIP = 7 hàng nguồn**. Sau khi đồng bộ thành công, bảng đích có **8 sản phẩm** vì được thêm hai SKU. Trong bài, không có hàng thuộc `REVIEW_CONFLICT`; ta sẽ tìm hiểu cách phát hiện loại bất thường này.

## 4. Phân loại trước khi ghi: SELECT + LEFT JOIN + CASE

Trước khi thực thi lệnh ghi, ta có thể **xem trước hành động** bằng truy vấn chỉ đọc. Đây cũng là cách làm rõ chính sách nghiệp vụ, độc lập với cú pháp `ON CONFLICT` hay `MERGE`.

~~~sql
SELECT
    i.sku,
    c.source_version AS stored_version,
    i.source_version AS incoming_version,
    c.unit_price AS stored_price,
    i.unit_price AS incoming_price,
    CASE
        WHEN c.sku IS NULL THEN 'INSERT'
        WHEN i.source_version > c.source_version THEN 'UPDATE'
        WHEN i.source_version < c.source_version THEN 'SKIP_STALE'
        WHEN ROW(
            i.product_name, i.unit_price, i.stock_qty
        ) IS NOT DISTINCT FROM ROW(
            c.product_name, c.unit_price, c.stock_qty
        ) THEN 'SKIP_DUPLICATE'
        ELSE 'REVIEW_CONFLICT'
    END AS proposed_action
FROM lab_up290_incoming AS i
LEFT JOIN lab_up290_catalog AS c
    ON c.sku = i.sku
ORDER BY i.sku;
~~~

Kết quả theo thứ tự SKU:

| sku | stored_version | incoming_version | proposed_action |
| --- | ---: | ---: | --- |
| BAG | 2 | 2 | SKIP_DUPLICATE |
| KEY | `NULL` | 1 | INSERT |
| MOUSE | 5 | 4 | SKIP_STALE |
| NOTE | 2 | 2 | SKIP_DUPLICATE |
| PAD | `NULL` | 1 | INSERT |
| PEN | 3 | 4 | UPDATE |
| USB | 2 | 3 | UPDATE |

### 4.1. Vì sao LEFT JOIN từ nguồn?

Lô nhập là tập cần được **phân loại từng hàng**. Vì vậy bắt đầu từ `incoming AS i`, rồi `LEFT JOIN` đến đích. Nếu không có hàng đích, các cột từ `c` nhận `NULL`; vì `c.sku` là khóa chính **không thể `NULL` trên hàng thật**, `c.sku IS NULL` xác định trường hợp cần INSERT.

Nếu dùng `INNER JOIN` ngay từ đầu, những SKU mới `KEY` và `PAD` sẽ **biến mất khỏi kết quả**, khiến ta không thể nhìn thấy các hàng cần thêm.

### 4.2. Vì sao so nội dung bằng IS NOT DISTINCT FROM?

Trong PostgreSQL, `IS NOT DISTINCT FROM` kiểm tra sự tương đương **kể cả `NULL`**:

- Hai giá trị bằng nhau → TRUE.
- Hai giá trị đều `NULL` → TRUE.
- Một giá trị `NULL`, bên kia khác `NULL` → FALSE.
- Hai giá trị khác nhau → FALSE.

Ở bảng mẫu, những thuộc tính đem so đều `NOT NULL`, nhưng cách viết này vẫn hữu ích khi hệ thống mở rộng thêm cột nullable như mô tả, ghi chú hoặc ngày giao hàng.

Biểu thức:

~~~sql
ROW(i.product_name, i.unit_price, i.stock_qty)
IS NOT DISTINCT FROM
ROW(c.product_name, c.unit_price, c.stock_qty)
~~~

so ba thuộc tính **theo vị trí tương ứng**, không dựa vào tên cột. Nó phù hợp trong PostgreSQL khi muốn nhận diện “cùng nội dung”. Nếu chỉ cần kiểm tra một cột, có thể viết `i.unit_price IS NOT DISTINCT FROM c.unit_price`.

### 4.3. Khi phiên bản bằng nhau nhưng nội dung khác nhau

Giả sử một bản ghi nguồn của `NOTE` mang **phiên bản 2** như trong đích, nhưng giá lại là **37000** thay vì 35000. Theo chính sách, trường hợp này **không được tự gọi là phiên bản mới hơn**; cũng không phải bản gửi trùng. Nó là `REVIEW_CONFLICT`.

Truy vấn tìm bất thường:

~~~sql
SELECT
    i.sku,
    c.source_version,
    c.product_name AS stored_name,
    i.product_name AS incoming_name,
    c.unit_price AS stored_price,
    i.unit_price AS incoming_price,
    c.stock_qty AS stored_stock,
    i.stock_qty AS incoming_stock
FROM lab_up290_incoming AS i
JOIN lab_up290_catalog AS c
    ON c.sku = i.sku
WHERE i.source_version = c.source_version
  AND ROW(
      i.product_name, i.unit_price, i.stock_qty
  ) IS DISTINCT FROM ROW(
      c.product_name, c.unit_price, c.stock_qty
  )
ORDER BY i.sku;
~~~

**Với dữ liệu mẫu, kết quả rỗng.** Nếu có hàng, quy trình đồng bộ cần gửi chúng sang bước xác minh hoặc **chặn lô** theo yêu cầu nghiệp vụ. Cơ chế `ON CONFLICT ... WHERE incoming_version > current_version` đơn thuần sẽ bỏ qua những hàng cùng phiên bản, **không tự báo rằng nội dung khác nhau**.

### 4.4. Thống kê số hàng theo hành động

~~~sql
WITH decisions AS (
    SELECT
        i.sku,
        CASE
            WHEN c.sku IS NULL THEN 'INSERT'
            WHEN i.source_version > c.source_version THEN 'UPDATE'
            WHEN i.source_version < c.source_version THEN 'SKIP_STALE'
            WHEN ROW(
                i.product_name, i.unit_price, i.stock_qty
            ) IS NOT DISTINCT FROM ROW(
                c.product_name, c.unit_price, c.stock_qty
            ) THEN 'SKIP_DUPLICATE'
            ELSE 'REVIEW_CONFLICT'
        END AS action_name
    FROM lab_up290_incoming AS i
    LEFT JOIN lab_up290_catalog AS c
        ON c.sku = i.sku
)
SELECT action_name, COUNT(*) AS row_count
FROM decisions
GROUP BY action_name
ORDER BY action_name;
~~~

| action_name | row_count |
| --- | ---: |
| INSERT | 2 |
| SKIP_DUPLICATE | 2 |
| SKIP_STALE | 1 |
| UPDATE | 2 |

Đây là **thống kê dự kiến dựa trên ảnh chụp dữ liệu khi chạy SELECT**, không tự chứng minh các lệnh ghi sau đó đã thực thi đúng bốn hành động trong môi trường có dữ liệu thay đổi đồng thời. Khi cần audit chính xác, hãy có cơ chế ghi nhận **kết quả thực tế** trong quy trình giao dịch.

## 5. INSERT thông thường và lý do trùng khóa gây lỗi

Khi chưa có `sku` trong bảng đích, một lệnh `INSERT` bình thường là phù hợp:

~~~sql
BEGIN;

INSERT INTO lab_up290_catalog (
    sku, product_name, unit_price, stock_qty, source_version
)
VALUES (
    'KEY', 'Bàn phím', 240000.00, 5, 1
)
RETURNING sku, source_version;

ROLLBACK;
~~~

Trong transaction, câu lệnh thêm một hàng `KEY`. Sau `ROLLBACK`, bản ghi mới **không được giữ lại**, nên các ví dụ upsert tiếp theo vẫn có thể xem `KEY` là hàng mới.

Ngược lại:

~~~sql
-- KHONG CHAY nhu mot lenh them moi hop le tren du lieu ban dau:
INSERT INTO lab_up290_catalog (
    sku, product_name, unit_price, stock_qty, source_version
)
VALUES (
    'PEN', 'Bút bi xanh', 12500.00, 15, 4
);
~~~

`PEN` đã tồn tại và `sku` là `PRIMARY KEY`. Lệnh `INSERT` bình thường vi phạm ràng buộc duy nhất (*unique violation*); PostgreSQL **không tự chuyển thành UPDATE** chỉ vì các thuộc tính khác có giá trị mới.

Upsert đưa ra **một quy tắc khi gặp xung đột khóa**, chứ không thay đổi ý nghĩa của `PRIMARY KEY`.

## 6. INSERT ... ON CONFLICT DO NOTHING: bỏ qua nếu đã tồn tại

PostgreSQL hỗ trợ:

~~~sql
INSERT INTO ten_bang (khoa, cot_1, cot_2)
VALUES (gia_tri_khoa, gia_tri_1, gia_tri_2)
ON CONFLICT (khoa) DO NOTHING;
~~~

Khi phát sinh xung đột theo khóa `khoa`, câu lệnh **không cập nhật hàng cũ**. Nó **bỏ qua việc chèn hàng mới đó**.

### 6.1. Thử một SKU đã tồn tại

~~~sql
BEGIN;

INSERT INTO lab_up290_catalog (
    sku, product_name, unit_price, stock_qty, source_version
)
VALUES (
    'PEN', 'Bút bi xanh', 12500.00, 15, 4
)
ON CONFLICT (sku) DO NOTHING
RETURNING sku, unit_price, source_version;

ROLLBACK;
~~~

Với dữ liệu ban đầu, câu `RETURNING` **không trả hàng nào**. `PEN` đã tồn tại nên thao tác chèn bị bỏ qua; giá vẫn **12000** và phiên bản vẫn **3**.

Đây là **SKIP do trùng khóa**, không phải **UPDATE dữ liệu mới**. Nếu mục tiêu của nghiệp vụ là nhận giá mới từ nguồn, `DO NOTHING` không đáp ứng yêu cầu.

### 6.2. Cùng câu DO NOTHING với một SKU mới

~~~sql
BEGIN;

INSERT INTO lab_up290_catalog (
    sku, product_name, unit_price, stock_qty, source_version
)
VALUES (
    'KEY', 'Bàn phím', 240000.00, 5, 1
)
ON CONFLICT (sku) DO NOTHING
RETURNING sku, unit_price, source_version;

ROLLBACK;
~~~

Lúc này `KEY` chưa tồn tại, nên câu lệnh **INSERT** và `RETURNING` trả một hàng. Chính sách của `DO NOTHING` là:

~~~text
Khong co xung dot khoa  -> INSERT
Co xung dot khoa       -> SKIP (khong xem phien ban, khong UPDATE)
~~~

Nó phù hợp với các công việc “chỉ thêm nếu chưa tồn tại” như ghi một mã sự kiện duy nhất, **nhưng không phù hợp** khi cần cập nhật bản mới hơn.

### 6.3. DO NOTHING không có nghĩa bỏ qua mọi loại lỗi

`ON CONFLICT (sku) DO NOTHING` xử lý xung đột theo **ràng buộc/khóa được chỉ định**. Nó không biến giá âm, kiểu dữ liệu sai, vi phạm `NOT NULL` hay mọi lỗi khóa ngoại thành dữ liệu hợp lệ.

PostgreSQL còn cho phép `ON CONFLICT DO NOTHING` không nêu mục tiêu xung đột trong một số ngữ cảnh; không nên dùng sự tiện lợi ấy để **che giấu rằng lô nhập đang vi phạm một ràng buộc duy nhất khác** mà nghiệp vụ cần biết.

**SKIP có chủ đích** phải dựa trên chính sách xác định, không phải “im lặng trước mọi lỗi”.

## 7. ON CONFLICT DO UPDATE: thêm mới hoặc cập nhật hàng đã có

Cú pháp PostgreSQL thường gặp:

~~~sql
INSERT INTO target_table AS t (
    business_key, value_col, source_version
)
VALUES (
    key_value, value_value, version_value
)
ON CONFLICT (business_key) DO UPDATE
SET
    value_col = EXCLUDED.value_col,
    source_version = EXCLUDED.source_version;
~~~

`EXCLUDED` là tên đặc biệt trong `ON CONFLICT DO UPDATE`, biểu diễn **hàng được đề xuất chèn**, nhưng đã gặp xung đột. Nó **không** phải bảng dữ liệu lưu riêng.

So sánh hai phía:

| Biểu thức | Ý nghĩa |
| --- | --- |
| `t.unit_price` | Giá **đang lưu** trên hàng đích có khóa trùng |
| `EXCLUDED.unit_price` | Giá **được đề xuất** từ `VALUES` hoặc `SELECT` |
| `t.source_version` | Phiên bản đang lưu |
| `EXCLUDED.source_version` | Phiên bản nguồn đang gửi đến |

### 7.1. Cập nhật SKU PEN bằng phiên bản mới

~~~sql
BEGIN;

INSERT INTO lab_up290_catalog AS c (
    sku, product_name, unit_price, stock_qty, source_version
)
VALUES (
    'PEN', 'Bút bi xanh', 12500.00, 15, 4
)
ON CONFLICT (sku) DO UPDATE
SET
    product_name = EXCLUDED.product_name,
    unit_price = EXCLUDED.unit_price,
    stock_qty = EXCLUDED.stock_qty,
    source_version = EXCLUDED.source_version,
    updated_at = CURRENT_TIMESTAMP
WHERE EXCLUDED.source_version > c.source_version
RETURNING sku, unit_price, stock_qty, source_version;

ROLLBACK;
~~~

Với dữ liệu ban đầu, `PEN` có phiên bản **3**, còn dữ liệu đề xuất có phiên bản **4**. Vì điều kiện `4 > 3` là TRUE, PostgreSQL thực hiện nhánh **UPDATE**:

| sku | unit_price | stock_qty | source_version |
| --- | ---: | ---: | ---: |
| PEN | 12500.00 | 15 | 4 |

### 7.2. Bỏ qua nguồn cũ với cùng câu upsert

~~~sql
BEGIN;

INSERT INTO lab_up290_catalog AS c (
    sku, product_name, unit_price, stock_qty, source_version
)
VALUES (
    'MOUSE', 'Chuột có dây', 160000.00, 6, 4
)
ON CONFLICT (sku) DO UPDATE
SET
    unit_price = EXCLUDED.unit_price,
    stock_qty = EXCLUDED.stock_qty,
    source_version = EXCLUDED.source_version
WHERE EXCLUDED.source_version > c.source_version
RETURNING sku, unit_price, source_version;

ROLLBACK;
~~~

`MOUSE` đang có phiên bản **5**, nguồn là **4**. `4 > 5` là FALSE nên **không có UPDATE**. Lệnh `RETURNING` không trả hàng nào; giá đang lưu vẫn **170000** và phiên bản vẫn **5**.

Như vậy, câu SQL có điều kiện đã hiện thực:

~~~text
Chua co SKU       -> INSERT
Co SKU va moi hon -> UPDATE
Co SKU va khong moi hon -> SKIP
~~~

Điều kiện `WHERE` trong **nhánh `DO UPDATE`** chỉ quyết định **có cập nhật hàng đã khớp hay không**. Nếu điều kiện sai, hàng không được chèn như một bản thứ hai và cũng không bị đổi. Đó là **SKIP**, không phải “quay lại thử INSERT”.

### 7.3. Bỏ qua dữ liệu trùng phiên bản và nội dung

~~~sql
BEGIN;

INSERT INTO lab_up290_catalog AS c (
    sku, product_name, unit_price, stock_qty, source_version
)
VALUES (
    'NOTE', 'Sổ ghi chú', 35000.00, 8, 2
)
ON CONFLICT (sku) DO UPDATE
SET
    product_name = EXCLUDED.product_name,
    unit_price = EXCLUDED.unit_price,
    stock_qty = EXCLUDED.stock_qty,
    source_version = EXCLUDED.source_version
WHERE EXCLUDED.source_version > c.source_version
RETURNING sku;

ROLLBACK;
~~~

`NOTE` có cùng phiên bản **2** ở cả hai phía; `WHERE` sai, nên thao tác **SKIP_DUPLICATE** theo dữ liệu mẫu. Tuy nhiên, SQL này cũng sẽ **skip một hàng cùng phiên bản nhưng nội dung khác**. Để bảo vệ chính sách `REVIEW_CONFLICT`, cần thực hiện bước **kiểm tra dữ liệu xung đột** như mục 4.3 trước khi chấp nhận lô.

### 7.4. Những thành phần quan trọng trong DO UPDATE

- `ON CONFLICT (sku)`: chỉ ra **khóa/ràng buộc duy nhất** dùng để tìm xung đột.
- `DO UPDATE SET ...`: thay các giá trị trên **hàng đích đã tồn tại**, không thêm hàng mới.
- `EXCLUDED.column`: giá trị **được đề xuất chèn**.
- `WHERE EXCLUDED.source_version > c.source_version`: cập nhật **chỉ khi phiên bản nguồn mới hơn**.
- `RETURNING ...`: trả các hàng **thực sự được chèn hoặc cập nhật**; hàng bỏ qua không xuất hiện.

Trong PostgreSQL, phía **trái** `SET` thường viết **tên cột đích không có bí danh** (ví dụ `unit_price = ...`), còn phía phải có thể tham chiếu `EXCLUDED` và bí danh đích `c`.

## 8. Upsert cả lô nguồn bằng INSERT ... SELECT ... ON CONFLICT

Đến đây, mỗi ví dụ xử lý một SKU. Trong ứng dụng nhập dữ liệu, một lô thường có nhiều hàng. PostgreSQL cho phép nguồn của `INSERT` là một câu `SELECT`:

~~~sql
BEGIN;

INSERT INTO lab_up290_catalog AS c (
    sku, product_name, unit_price, stock_qty, source_version
)
SELECT
    i.sku,
    i.product_name,
    i.unit_price,
    i.stock_qty,
    i.source_version
FROM lab_up290_incoming AS i
WHERE TRUE
ON CONFLICT (sku) DO UPDATE
SET
    product_name = EXCLUDED.product_name,
    unit_price = EXCLUDED.unit_price,
    stock_qty = EXCLUDED.stock_qty,
    source_version = EXCLUDED.source_version,
    updated_at = CURRENT_TIMESTAMP
WHERE EXCLUDED.source_version > c.source_version
RETURNING
    sku,
    product_name,
    unit_price,
    stock_qty,
    source_version;

SELECT
    sku,
    product_name,
    unit_price,
    stock_qty,
    source_version
FROM lab_up290_catalog
ORDER BY sku;

ROLLBACK;
~~~

**Vì sao có `WHERE TRUE` trong `SELECT`?** Với PostgreSQL, khi `INSERT ... SELECT` kết hợp `ON CONFLICT`, một `WHERE` tường minh ở phần `SELECT` giúp tránh tình huống bộ phân tích cú pháp hiểu nhầm `ON` là mệnh đề nối bảng. `WHERE TRUE` không lọc bớt hàng nào; nó chỉ làm ranh giới cú pháp rõ ràng. Đây là mẹo tương thích được PostgreSQL khuyến nghị.

### 8.1. Những hàng được thực sự chèn hoặc cập nhật

`RETURNING` trả **4 hàng**:

| sku | Kết quả thực tế | unit_price | stock_qty | source_version |
| --- | --- | ---: | ---: | ---: |
| KEY | INSERT | 240000.00 | 5 | 1 |
| PAD | INSERT | 45000.00 | 9 | 1 |
| PEN | UPDATE | 12500.00 | 15 | 4 |
| USB | UPDATE | 85000.00 | 7 | 3 |

Thứ tự `RETURNING` thực tế **không được đảm bảo**; bảng này được sắp theo SKU để dễ đọc. Dòng “Kết quả thực tế” là **phân loại dựa trên dữ liệu ban đầu**, không phải một cột `RETURNING` tự sinh trong câu SQL trên.

Các hàng `NOTE`, `BAG`, `MOUSE` **không có trong `RETURNING`** vì nhánh `DO UPDATE` bị chặn bởi điều kiện phiên bản. Chúng không được cập nhật nhưng vẫn tồn tại trong bảng đích.

### 8.2. Bảng đích trong transaction sau lệnh upsert

Truy vấn `SELECT` sau lệnh upsert (trước `ROLLBACK`) thấy tám SKU:

| sku | unit_price | stock_qty | source_version |
| --- | ---: | ---: | ---: |
| BAG | 300000.00 | 3 | 2 |
| BOOK | 95000.00 | 12 | 4 |
| KEY | 240000.00 | 5 | 1 |
| MOUSE | 170000.00 | 4 | 5 |
| NOTE | 35000.00 | 8 | 2 |
| PAD | 45000.00 | 9 | 1 |
| PEN | 12500.00 | 15 | 4 |
| USB | 85000.00 | 7 | 3 |

Sản phẩm BOOK không xuất hiện trong lô nhập nên giữ nguyên. MOUSE giữ bản **phiên bản 5** thay vì bị ghi đè bởi bản **4**.

Sau `ROLLBACK`, toàn bộ cập nhật/chèn trong ví dụ được hoàn tác: bảng đích trở về **sáu SKU ban đầu**, còn bảng `incoming` không thay đổi.

### 8.3. Phân biệt số hàng nguồn và số hàng bị ảnh hưởng

| Đại lượng | Số lượng |
| --- | ---: |
| Hàng trong lô nguồn | 7 |
| Hàng mới được chèn | 2 |
| Hàng đích được cập nhật | 2 |
| Hàng nguồn được bỏ qua | 3 |
| Hàng thực sự chèn/cập nhật, xuất hiện trong `RETURNING` | 4 |
| Hàng đích sau upsert | 8 |

**Không được suy ra “3 hàng bỏ qua” chỉ từ `RETURNING`** nếu không biết chính xác số hàng nguồn đủ điều kiện và không có lỗi. `RETURNING` không nói rõ lý do SKIP; muốn phân biệt stale và duplicate, hãy dùng bước phân loại hoặc audit riêng.

### 8.4. INSERT SELECT có thể không thành công nếu nguồn trùng khóa

Trong PostgreSQL, một lệnh `INSERT ... ON CONFLICT DO UPDATE` không được **tác động cùng một hàng đích nhiều lần** trong cùng câu lệnh. Nếu nguồn `SELECT` trả hai hàng cùng `sku`, PostgreSQL có thể báo lỗi liên quan tới **cardinality violation**.

Bài đã tạo `incoming.sku PRIMARY KEY`, nên lô này không có trùng khóa. Khi nhập từ file hoặc bảng staging **chưa có ràng buộc duy nhất**, phải phát hiện và chuẩn hóa trước, không được nghĩ upsert tự chọn một trong hai hàng trùng.

## 9. MERGE: diễn đạt rõ MATCHED, NOT MATCHED và hành động

`MERGE` là câu lệnh SQL giúp so khớp bảng đích với tập nguồn rồi chỉ định những hành động theo trường hợp **đã khớp** hoặc **chưa khớp**.

PostgreSQL hỗ trợ `MERGE` từ **phiên bản 15**.

Mẫu khái quát:

~~~sql
MERGE INTO target_table AS t
USING source_table AS s
ON t.business_key = s.business_key
WHEN MATCHED AND dieu_kien_can_cap_nhat THEN
    UPDATE SET some_value = s.some_value
WHEN NOT MATCHED THEN
    INSERT (business_key, some_value)
    VALUES (s.business_key, s.some_value);
~~~

Đọc từng nhánh:

| Nhánh | Khi nào? | Hành động |
| --- | --- | --- |
| `WHEN MATCHED AND ... THEN UPDATE` | Có hàng đích khớp khóa **và** điều kiện cập nhật đúng | Sửa hàng đã có |
| `WHEN NOT MATCHED THEN INSERT` | Hàng nguồn **không khớp** hàng đích | Thêm hàng mới |
| Hàng MATCHED nhưng không thỏa nhánh hành động nào | Không có hành động áp dụng | **SKIP** |

`MERGE` có thêm những khả năng khác tùy hệ quản trị và phiên bản, kể cả xóa trong những trường hợp được hỗ trợ. Nhưng bài này chỉ dùng ba tình huống **thêm, cập nhật, bỏ qua**, không mặc định xóa hàng đích không xuất hiện trong nguồn.

### 9.1. MERGE chạy trên lô nhập mẫu

~~~sql
BEGIN;

MERGE INTO lab_up290_catalog AS c
USING lab_up290_incoming AS i
ON c.sku = i.sku
WHEN MATCHED
     AND i.source_version > c.source_version THEN
    UPDATE SET
        product_name = i.product_name,
        unit_price = i.unit_price,
        stock_qty = i.stock_qty,
        source_version = i.source_version,
        updated_at = CURRENT_TIMESTAMP
WHEN NOT MATCHED THEN
    INSERT (
        sku, product_name, unit_price, stock_qty, source_version
    )
    VALUES (
        i.sku, i.product_name, i.unit_price,
        i.stock_qty, i.source_version
    );

SELECT sku, unit_price, stock_qty, source_version
FROM lab_up290_catalog
ORDER BY sku;

ROLLBACK;
~~~

Trong transaction, kết quả là **hai INSERT (KEY, PAD), hai UPDATE (PEN, USB), ba SKIP (BAG, NOTE, MOUSE)**. Sau `ROLLBACK`, bảng đích trở về dữ liệu ban đầu.

Không cần viết nhánh “nếu phiên bản không mới hơn thì làm gì” khi chính sách muốn **không có hành động**. Các hàng MATCHED không thỏa điều kiện UPDATE sẽ bị bỏ qua. PostgreSQL cũng có khả năng `DO NOTHING` tường minh ở các nhánh phù hợp, nhưng việc **không viết nhánh hành động tương ứng** là đủ để thể hiện SKIP trong ví dụ này.

### 9.2. ON là điều kiện nhận diện, không phải điều kiện quyết định cập nhật

Ở câu đúng:

~~~sql
ON c.sku = i.sku
WHEN MATCHED AND i.source_version > c.source_version THEN
    UPDATE ...
~~~

`ON` chỉ cho biết **SKU đã tồn tại hay chưa**. Điều kiện **phiên bản mới hơn** được đặt ở `WHEN MATCHED AND ...`.

Không nên chuyển điều kiện phiên bản vào `ON`:

~~~sql
-- SAI VE NGHIEP VU: KHONG CHAY.
MERGE INTO lab_up290_catalog AS c
USING lab_up290_incoming AS i
ON c.sku = i.sku
   AND i.source_version > c.source_version
WHEN MATCHED THEN
    UPDATE SET unit_price = i.unit_price
WHEN NOT MATCHED THEN
    INSERT (sku, product_name, unit_price, stock_qty, source_version)
    VALUES (
        i.sku, i.product_name, i.unit_price,
        i.stock_qty, i.source_version
    );
~~~

Ví dụ `MOUSE` **đã tồn tại** nhưng phiên bản nguồn không mới hơn. Với `ON` sai ở trên, hàng này bị coi là **NOT MATCHED** dù SKU thực sự có mặt. Nhánh `INSERT` có thể cố thêm một `MOUSE` thứ hai và **vi phạm khóa chính**.

**Quy tắc:** `ON` biểu diễn định danh của thực thể; `WHEN MATCHED AND ...` biểu diễn **chính sách được phép cập nhật**.

### 9.3. Thứ tự các nhánh WHEN có ý nghĩa

Trong những câu `MERGE` phức tạp, các nhánh `WHEN` có thể chứa điều kiện khác nhau. Nếu nhiều nhánh được viết cho cùng một loại MATCHED/NOT MATCHED, thứ tự và khả năng đến được từng nhánh phải theo cú pháp và quy tắc của dialect.

Với chính sách ví dụ, chỉ có một nhánh MATCHED–UPDATE và một nhánh NOT MATCHED–INSERT, vì vậy logic đơn giản. Không viết một nhánh MATCHED không điều kiện đứng trước rồi kỳ vọng một nhánh MATCHED có điều kiện phía sau vẫn được chạy.

## 10. MERGE và ON CONFLICT: điểm giống và khác

Cả hai đều có thể giải quyết bài toán upsert, nhưng **không phải hai câu lệnh hoàn toàn thay thế được nhau**.

| Khía cạnh | PostgreSQL `INSERT ... ON CONFLICT` | PostgreSQL `MERGE` |
| --- | --- | --- |
| Điểm khởi đầu | Thử `INSERT`; xử lý khi gặp xung đột khóa duy nhất | Ghép tập nguồn và bảng đích theo `ON` |
| Xác định hàng trùng | Xung đột với `UNIQUE`/`PRIMARY KEY` hoặc arbiter phù hợp | Điều kiện `ON` |
| Khi chưa có hàng | INSERT | `WHEN NOT MATCHED THEN INSERT` |
| Khi đã có hàng | `DO NOTHING` hoặc `DO UPDATE` | `WHEN MATCHED THEN UPDATE`, bỏ qua hoặc các nhánh được hỗ trợ |
| Điều kiện không cập nhật | `DO UPDATE ... WHERE ...` | `WHEN MATCHED AND ...` hoặc không có nhánh hành động |
| Nguồn được đề xuất chèn | `EXCLUDED.column` | Bí danh nguồn trong `USING` |
| Xử lý xung đột đồng thời | Cơ chế `ON CONFLICT DO UPDATE` kết hợp chỉ mục duy nhất cung cấp bảo đảm upsert nguyên tử trong điều kiện hỗ trợ | Không mặc định có cùng bảo đảm tự chuyển nhánh khi một phiên khác chèn khóa mới; có thể gặp lỗi unique và cần retry |
| Trùng khóa trong tập nguồn | Có thể lỗi khi cùng hàng đích bị tác động hai lần | Có thể lỗi cardinality hoặc vi phạm unique tùy nhánh |
| Cập nhật/có thể xóa tùy điều kiện | Chỉ xử lý INSERT/UPDATE/DO NOTHING | Có khả năng diễn đạt nhiều nhánh hành động hơn tùy phiên bản |
| Trả hàng đã đổi | `RETURNING` | Khả năng `RETURNING` của `MERGE` phụ thuộc phiên bản PostgreSQL; ví dụ dùng `SELECT` trong transaction để tương thích |

### 10.1. Chọn công cụ nào?

Chọn **`ON CONFLICT`** thường hợp lý khi:

- Mục tiêu chính là thêm một hàng, **nếu đã có cùng khóa duy nhất thì cập nhật/bỏ qua**.
- Có ràng buộc unique/primary key rõ ràng.
- Quan tâm nhiều đến trường hợp các phiên **đồng thời thử chèn cùng khóa**.

Chọn **`MERGE`** thường hợp lý khi:

- Muốn diễn đạt rõ các trường hợp MATCHED và NOT MATCHED bằng các nhánh trong một câu SQL.
- Nguồn đã được chuẩn hóa duy nhất theo khóa và chính sách hành động có nhiều điều kiện.
- Dùng một SQL dialect hỗ trợ `MERGE` với cú pháp, hành vi đồng thời và các giới hạn phù hợp.

Không chọn chỉ theo tiêu chí “lệnh nào trông hiện đại hơn”. Với dữ liệu thật, **tính đúng, khả năng retry, bội số nguồn và chi phí thực thi** quan trọng hơn độ ngắn của cú pháp.

## 11. Bỏ qua không đồng nghĩa cập nhật lại giá trị cũ

Đôi khi người viết cố “bỏ qua” bằng cách vẫn chạy UPDATE nhưng gán lại các giá trị cũ:

~~~sql
-- KHONG TUONG DUONG voi bo qua thuc su trong moi he thong.
SET unit_price = c.unit_price
~~~

Về **giá trị cột tiền**, kết quả có thể giống trạng thái trước. Nhưng đó vẫn có thể là **một lệnh UPDATE thực sự**, với các hệ quả:

- Trigger cập nhật có thể chạy.
- Cột `updated_at` có thể được ghi lại.
- Database có thể tạo phiên bản hàng mới, sinh log hoặc khóa hàng.
- Hệ thống đồng bộ, CDC hoặc kiểm toán có thể ghi nhận một thay đổi.

Ở PostgreSQL, `ON CONFLICT DO UPDATE ... WHERE điều_kiện` giúp **không thực hiện nhánh cập nhật** khi điều kiện sai, thay vì gán lại cột cũ.

Chính sách **SKIP_DUPLICATE** được dùng để giảm ghi không cần thiết, không chỉ để giữ các giá trị số học giống nhau.

### 11.1. UPDATE phiên bản mới nhưng nội dung không đổi

Giả sử một hàng nguồn có `source_version = 7`, còn đích `source_version = 6`, nhưng `product_name`, `unit_price` và `stock_qty` vẫn giống nhau.

Với quy tắc “phiên bản mới hơn luôn được chấp nhận”, ta **UPDATE `source_version` từ 6 lên 7**. Đây là cách ghi nhận “đã xử lý phiên bản mới”, dù các thuộc tính hiển thị không đổi.

Nếu nghiệp vụ muốn **SKIP hoàn toàn khi nội dung không đổi**, cần định nghĩa xem có cập nhật metadata phiên bản hay không. Bỏ cập nhật phiên bản có thể khiến hệ thống gặp lại cùng phiên bản “mới hơn” ở những lô sau. Không có câu trả lời chung cho mọi hệ thống; **quy tắc chính sách phải rõ trước khi viết SQL**.

## 12. Giữ dữ liệu đã mới hơn: tránh ghi đè nguồn cũ

Một trường hợp nguy hiểm là đồng bộ đến không theo thứ tự:

~~~text
Lan 1: den phien ban 5 -> cap nhat thanh 5
Lan 2: den tre phien ban 4 -> KHONG DUOC ghi de 5 bang 4
Lan 3: gui lai phien ban 5 -> SKIP vi trung
Lan 4: den phien ban 6 -> cap nhat thanh 6
~~~

Điều kiện cốt lõi:

~~~sql
WHERE EXCLUDED.source_version > c.source_version
~~~

hoặc, trong `MERGE`:

~~~sql
WHEN MATCHED AND i.source_version > c.source_version THEN
    UPDATE ...
~~~

giúp chặn **bản cũ** ở phía nguồn khi khóa đã tồn tại.

### 12.1. Phiên bản phải có ý nghĩa trong phạm vi của từng khóa

Nếu `source_version` là phiên bản chung của **toàn bộ file nhập** nhưng không tăng ổn định cho từng sản phẩm, so `incoming.version > current.version` có thể không phản ánh bản nào mới hơn. Cần hiểu ý nghĩa **thứ tự dữ liệu** từ hệ thống nguồn.

Ví dụ, số phiên bản 6 của SKU A và 6 của SKU B không nhất thiết là cùng một sự kiện. Thứ tự chỉ có ý nghĩa khi so **các bản của cùng SKU**.

### 12.2. Ngày giờ không tự thay thế được phiên bản đáng tin cậy

Nếu hệ thống chỉ có `updated_at` từ nguồn, có thể cần so thời gian; nhưng phải xem xét:

- Đồng hồ giữa các hệ thống có đồng bộ không?
- Độ chính xác timestamp có đủ phân biệt hai thay đổi gần nhau không?
- Một sự kiện đến trễ có timestamp từ lúc tạo hay lúc nhận?
- Hai sự kiện cùng thời điểm thì cần khóa phá hòa nào?

Với bài này, dùng số phiên bản nguyên đơn điệu giúp tách rõ vấn đề. Trong hệ thống thật, cần giao thức thứ tự được bảo đảm hoặc cơ chế phiên bản/hàng đợi đủ tin cậy.

## 13. Nguồn có nhiều hàng cho cùng khóa: phải chuẩn hóa trước

Trong bài, `incoming.sku` là `PRIMARY KEY`, nhưng dữ liệu thô từ CSV, message queue hay API có thể có:

~~~text
sku   version   price
PEN      4       12500
PEN      5       13000
PEN      5       13200   <-- cung phien ban, khac noi dung
~~~

Không thể cho cả ba hàng vào một câu upsert rồi kỳ vọng SQL tự biết **bản đúng**. Trước hết phải phân biệt:

- Nhiều phiên bản **khác nhau**: có thể chọn phiên bản cao nhất theo chính sách.
- Hai bản **cùng phiên bản và nội dung giống nhau**: có thể coi là bản gửi trùng.
- Hai bản **cùng phiên bản nhưng nội dung khác**: cần rà soát nguồn, không tự ý chọn ngẫu nhiên.

### 13.1. Tìm khóa trùng trong bảng raw

Giả sử có bảng `raw_import` với `sku`, `source_version` và các thuộc tính (bảng này **không được tạo trong script mẫu**):

~~~sql
-- MAU MINH HOA: chi chay neu da co bang raw_import.
SELECT sku, COUNT(*) AS row_count
FROM raw_import
GROUP BY sku
HAVING COUNT(*) > 1
ORDER BY sku;
~~~

Đây là kiểm tra bội số **trên khóa nghiệp vụ**, khác với việc viết `SELECT DISTINCT *`. Hai hàng cùng SKU nhưng khác phiên bản **không phải hai sản phẩm khác nhau**.

### 13.2. Xem thứ tự khi nguồn có nhiều phiên bản

Ví dụ độc lập, chỉ đọc dữ liệu CTE:

~~~sql
WITH raw_import(sku, source_version, unit_price, event_id) AS (
    VALUES
        ('PEN', 4, 12500::numeric, 1001),
        ('PEN', 5, 13000::numeric, 1002),
        ('USB', 3,  85000::numeric, 1003)
),
ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY sku
            ORDER BY source_version DESC, event_id DESC
        ) AS rn
    FROM raw_import
)
SELECT sku, source_version, unit_price, event_id
FROM ranked
WHERE rn = 1
ORDER BY sku;
~~~

Kết quả lấy **PEN phiên bản 5** và **USB phiên bản 3**. `event_id` chỉ là khóa phá hòa, không tự chứng minh phiên bản có nội dung đáng tin cậy. Nếu phiên bản cao nhất có hai bản **khác nội dung**, hệ thống cần chính sách phát hiện bất thường trước khi chọn.

### 13.3. Không dùng LIMIT 1 mà thiếu ORDER BY

Một truy vấn `SELECT ... LIMIT 1` không có `ORDER BY` **không xác định “bản mới nhất”**. Thứ tự hàng lưu trên đĩa hoặc thứ tự gửi trong file không phải tiêu chí nghiệp vụ được SQL bảo đảm.

Nếu muốn chọn một bản theo phiên bản, phải viết rõ `ORDER BY source_version DESC` và **tiêu chí phân định khi hòa**; đồng thời kiểm tra trường hợp hòa mang dữ liệu mâu thuẫn.

## 14. Trường hợp một SKU có nhiều ràng buộc UNIQUE

Giả sử bảng sản phẩm ngoài `sku` còn có `barcode UNIQUE` hoặc `external_id UNIQUE`. Lô nguồn có SKU mới nhưng barcode lại trùng sản phẩm khác.

Khi đó:

- `ON CONFLICT (sku)` **không mặc định xử lý mọi lỗi unique khác**.
- `DO NOTHING` không chỉ định mục tiêu xung đột có thể bỏ qua những xung đột mà nghiệp vụ thực sự cần xem là **lỗi**.
- `MERGE ON t.sku = s.sku` có thể quyết định NOT MATCHED theo SKU, nhưng khi INSERT vẫn có thể **vi phạm UNIQUE barcode**.

Đó là lý do cần xác định **khóa thực thể**, kiểm tra mối quan hệ giữa các định danh và không coi “trùng bất kỳ cột unique nào” là “cùng sản phẩm”.

### 14.1. Giá trị NULL trong khóa UNIQUE

Ở PostgreSQL, `PRIMARY KEY` không nhận `NULL`. Cột có `UNIQUE` mà **cho phép `NULL`** thường có quy tắc riêng về các giá trị `NULL` trong tính duy nhất; PostgreSQL hiện đại còn có tùy chọn `NULLS NOT DISTINCT` để điều chỉnh một số ràng buộc.

Vì thế, không nên xây chính sách upsert dựa trên một khóa nghiệp vụ nullable rồi mặc định mọi dòng `NULL` đều sẽ va vào cùng một xung đột. Nếu một định danh thực sự bắt buộc, hãy thiết kế **`NOT NULL` và tính duy nhất** tương ứng.

## 15. MERGE không tự xóa hàng đích vắng mặt ở nguồn

Một hiểu nhầm hay gặp: “Sau MERGE, bảng đích sẽ giống hệt tập nguồn.”

Điều đó **không đúng với câu MERGE của bài**. Nó chỉ:

- INSERT những khóa nguồn chưa có ở đích.
- UPDATE những khóa đã có khi nguồn mới hơn.
- SKIP những khóa đã có khi nguồn không mới hơn.

Nó **không xóa** SKU BOOK chỉ vì BOOK không xuất hiện trong `incoming`.

Nếu hệ thống nguồn gửi **bản snapshot đầy đủ** và nghiệp vụ muốn loại những hàng không còn xuất hiện, đó là **một quy tắc đồng bộ bổ sung** cần được định nghĩa rất cẩn thận. Một lô **delta chỉ chứa những SKU thay đổi** thì sự vắng mặt của BOOK hoàn toàn bình thường.

Trước khi thiết kế nhánh xóa, hãy xác nhận:

1. Nguồn gửi **toàn bộ danh mục** hay chỉ **thay đổi kể từ lần trước**?
2. File có bị thiếu do lỗi nhập/giới hạn trang/đường truyền không?
3. “Không xuất hiện” có nghĩa là xóa vật lý, vô hiệu hóa hay chưa có dữ liệu trong lô?
4. Có khóa ngoại, lịch sử giao dịch hoặc yêu cầu audit cần bảo vệ không?

Bài này chủ động tập trung **INSERT, UPDATE và SKIP**, không tự xóa bản ghi.

## 16. Điều gì xảy ra khi thực thi lại cùng một lô?

Upsert thường được dùng trong tiến trình **có thể retry** khi lỗi mạng hoặc job chạy lại. Với chính sách phiên bản của bài:

~~~text
Truoc lan 1: PEN version 3; KEY chua ton tai
Lan 1:
    PEN version 4 -> UPDATE
    KEY version 1 -> INSERT
Lan 2 (gui lai y het):
    PEN version 4 -> SKIP (bang phien ban)
    KEY version 1 -> SKIP (bang phien ban)
~~~

Như vậy **giá trị kinh doanh không bị cộng dồn hoặc nhân lên sau lần chạy lại**, vì phép gán lấy **giá trị mục tiêu**:

~~~sql
SET
    unit_price = EXCLUDED.unit_price,
    stock_qty = EXCLUDED.stock_qty
~~~

Chính sách này khác với thao tác:

~~~sql
-- Can than: moi lan chay se cong tiep neu khong co co che chong lap.
SET stock_qty = c.stock_qty + EXCLUDED.stock_qty
~~~

Nếu dữ liệu nguồn biểu diễn **số lượng tăng thêm của một sự kiện** chứ không phải **mức tồn cuối cùng**, cần nhận diện từng sự kiện bằng **ID duy nhất** và áp dụng đúng một lần. Không được biến một sự kiện cộng tồn thành “upsert giá trị tồn tuyệt đối” hoặc ngược lại mà chưa có mô hình nghiệp vụ rõ ràng.

### 16.1. Idempotency không tự giải quyết mọi cạnh tranh

Ngay cả khi một lô chạy lại không đổi trạng thái cuối, vẫn cần giải quyết các phiên **đồng thời** cùng ghi một khóa. Đồng thời, nếu nguồn gửi **hai phiên bản khác nhau** thì điều kiện phiên bản phải bảo vệ bản mới hơn.

Idempotency (chạy lại cùng đầu vào không làm đổi kết quả sau lần đầu) và concurrency control (điều phối ghi đồng thời) là **hai yêu cầu liên quan nhưng không đồng nhất**.

## 17. Đồng thời: tại sao ON CONFLICT thường phù hợp cho upsert theo khóa?

Hãy tưởng tượng hai phiên:

~~~text
Phien A: SELECT PEN -> khong thay
Phien B: SELECT PEN -> khong thay
Phien A: INSERT PEN -> thanh cong
Phien B: INSERT PEN -> loi duplicate key
~~~

Đó là **race condition** (*check-then-insert*). Nếu ứng dụng tự viết:

~~~sql
SELECT ... WHERE sku = 'PEN';
-- Neu khong co thi INSERT, neu co thi UPDATE.
~~~

thì kết quả kiểm tra `SELECT` có thể **lỗi thời ngay khi chuẩn bị viết**.

Trong PostgreSQL, `INSERT ... ON CONFLICT DO UPDATE` sử dụng **cơ chế xung đột với ràng buộc duy nhất** để thực hiện nhánh insert/update một cách nguyên tử trong những điều kiện hỗ trợ. Đây là ưu điểm nổi bật so với tự `SELECT` rồi chọn hai lệnh riêng mà không có kiểm soát đồng thời.

### 17.1. MERGE và ON CONFLICT không có cùng bảo đảm đồng thời

Trong PostgreSQL, `MERGE` quyết định các trường hợp MATCHED/NOT MATCHED theo cơ chế ghép và cách thực thi của nó. Nếu một phiên khác chèn khóa phù hợp **trong lúc MERGE đang thực thi**, `MERGE` **không được mặc định bảo đảm** tự chuyển thành UPDATE đúng như `ON CONFLICT DO UPDATE`; một lệnh INSERT trong MERGE có thể gặp **unique violation**. Quy trình cần có **transaction, retry hoặc khóa/mức cô lập** phù hợp.

Không nên coi `MERGE` là giải pháp tự động cho mọi vấn đề race condition.

### 17.2. Có thể có deadlock, retry và lỗi ràng buộc

Với lô upsert lớn, các phiên có thể tranh chấp nhiều khóa khác nhau. Các trường hợp cần được ứng dụng xử lý gồm:

- Lỗi trùng khóa do nhánh hoặc constraint ngoài dự kiến.
- Lỗi serialization trong mức cô lập mạnh.
- Deadlock hoặc timeout do khóa.
- Giao dịch bị rollback và cần thử lại an toàn.

Thiết kế retry phải bảo đảm **không nhân đôi các sự kiện tăng số lượng**, đồng thời chỉ báo thành công khi transaction thực sự commit.

### 17.3. SELECT phân loại trước không thay thế ràng buộc tại thời điểm ghi

Một báo cáo preflight thấy 2 INSERT, 2 UPDATE, 3 SKIP là ảnh chụp đúng **khi SELECT được chạy**. Nếu bảng đích thay đổi trước khi câu ghi chạy, một SKU dự kiến INSERT có thể đã tồn tại; một SKU dự kiến UPDATE có thể đã lên phiên bản cao hơn.

Với nhu cầu audit/chính sách nghiêm ngặt, hãy phối hợp **transaction, mức cô lập, khóa, kiểm tra phiên bản và cơ chế ghi log**. Không nên dựa độc nhất vào kết quả của một `SELECT` chạy trước đó.

## 18. RETURNING, đếm số hàng và audit kết quả

Trong PostgreSQL, `INSERT ... ON CONFLICT DO UPDATE ... RETURNING` trả các hàng được **INSERT hoặc UPDATE thực sự**. Khi nhánh `DO NOTHING` hoặc điều kiện `DO UPDATE WHERE` bỏ qua hàng, hàng đó không có trong kết quả trả về.

### 18.1. RETURNING không luôn có nhãn INSERT/UPDATE

Ví dụ:

~~~sql
INSERT INTO lab_up290_catalog AS c (
    sku, product_name, unit_price, stock_qty, source_version
)
VALUES (
    'PEN', 'Bút bi xanh', 12500.00, 15, 4
)
ON CONFLICT (sku) DO UPDATE
SET
    unit_price = EXCLUDED.unit_price,
    stock_qty = EXCLUDED.stock_qty,
    source_version = EXCLUDED.source_version
WHERE EXCLUDED.source_version > c.source_version
RETURNING sku, source_version;
~~~

`RETURNING sku, source_version` chỉ hiện giá trị hàng sau thao tác; **không tự có cột “đây là INSERT hay UPDATE”**. Với PostgreSQL hiện đại, khả năng truy cập hình ảnh OLD/NEW trong `RETURNING` thay đổi theo phiên bản, nhưng không nên dùng mẹo đọc cột hệ thống như `xmax` rồi coi nó là **hợp đồng audit bền vững trên mọi phiên bản và tình huống**.

Muốn thống kê chính xác từng hành động trong hệ thống thật, có thể:

- Ghi trước quyết định theo một snapshot/giao dịch có kiểm soát, rồi đối chiếu kết quả sau.
- Tách những nhánh xử lý và ghi audit trong cùng transaction khi phù hợp.
- Dùng tính năng trả về loại hành động mà SQL dialect/phiên bản cung cấp, ví dụ `OUTPUT $action` của SQL Server `MERGE`.
- Ghi event log theo ID sự kiện/phiên bản để phân biệt hàng đã xử lý, bỏ qua và cần rà soát.

### 18.2. Không thể kết luận “bỏ qua an toàn” chỉ từ 0 rows affected

Một lệnh trả 0 hàng có thể do:

- Khóa đã tồn tại và `DO NOTHING`.
- Nguồn cũ/bằng phiên bản nên điều kiện `WHERE` của `DO UPDATE` không đạt.
- Truy vấn nguồn ban đầu không trả hàng.
- Hàng bị loại trước khi vào lệnh vì điều kiện `WHERE` ở `SELECT`.
- Quy trình đang xử lý nhánh khác hoặc gặp lỗi, rollback.

Vì vậy số hàng ảnh hưởng cần được diễn giải **cùng với chính sách và trạng thái giao dịch**.

## 19. Dữ liệu đầu vào không hợp lệ: SKIP không được che lỗi

Chính sách bỏ qua hợp lệ dựa trên **khóa và phiên bản**. Nhưng một hàng nguồn có thể vi phạm **ràng buộc dữ liệu**:

- `unit_price < 0`.
- `stock_qty < 0`.
- `sku IS NULL`.
- Tên vượt độ dài cột.
- Trùng khóa nhưng nội dung khác với cùng phiên bản.
- Mã sản phẩm khác nhau nhưng trùng một định danh phụ duy nhất.

Ví dụ bảng mẫu có:

~~~sql
unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0)
~~~

Một hàng có giá âm **không được chấp nhận chỉ vì SKU của nó trùng một bản cũ**. PostgreSQL kiểm tra các ràng buộc liên quan trong xử lý INSERT/ON CONFLICT; không nên dựa vào `DO NOTHING` hoặc `DO UPDATE WHERE FALSE` để lọc bỏ mọi dữ liệu không hợp lệ.

Đối với nguồn cần được nhập từ hệ thống không tin cậy, có thể thiết kế **bảng staging với bước xác minh**, phân loại hàng hợp lệ, hàng trùng hợp lệ và hàng lỗi. Sau đó mới đưa các hàng được phép vào câu upsert.

### 19.1. REVIEW_CONFLICT nên có lối xử lý rõ ràng

Theo quy tắc bài:

~~~text
SKU ton tai
AND incoming_version = stored_version
AND payload khac nhau
=> REVIEW_CONFLICT
~~~

Một hệ thống có thể chọn:

- Dừng cả lô để xác minh nguồn.
- Đưa riêng hàng lỗi vào bảng kiểm tra.
- Ghi sự kiện cảnh báo và bỏ qua hàng lỗi, nếu chính sách cho phép.

Không có một lựa chọn tự động đúng cho mọi ngành. Nhưng **không nên âm thầm gọi REVIEW_CONFLICT là bản trùng bình thường**, vì điều đó che một bất thường về tính nhất quán phiên bản.

## 20. Khác biệt giữa các SQL dialect

Không phải hệ quản trị SQL nào cũng có cả `ON CONFLICT` và `MERGE` với cùng cú pháp. Đặc biệt chú ý rằng **các đoạn ví dụ dưới đây là ví dụ phương ngữ**, giả định bảng tương ứng đã tồn tại; không chạy chúng nguyên xi trong PostgreSQL của bài nếu cú pháp thuộc hệ khác.

### 20.1. PostgreSQL: ON CONFLICT và MERGE

PostgreSQL dùng:

~~~sql
INSERT INTO lab_up290_catalog AS c (
    sku, product_name, unit_price, stock_qty, source_version
)
VALUES (
    'PEN', 'Bút bi xanh', 12500.00, 15, 4
)
ON CONFLICT (sku) DO UPDATE
SET
    unit_price = EXCLUDED.unit_price,
    stock_qty = EXCLUDED.stock_qty,
    source_version = EXCLUDED.source_version
WHERE EXCLUDED.source_version > c.source_version;
~~~

và hỗ trợ `MERGE` từ PostgreSQL 15. `EXCLUDED` là tên đặc biệt của lệnh upsert, không phải bảng nguồn được khai báo trong `MERGE`.

### 20.2. SQLite: UPSERT với ON CONFLICT

SQLite hỗ trợ cú pháp UPSERT kiểu `ON CONFLICT ... DO UPDATE` từ phiên bản **3.24.0**. Ví dụ:

~~~sql
-- SQLite minh hoa: gia dinh catalog co khoa UNIQUE(sku).
INSERT INTO catalog (
    sku, product_name, unit_price, stock_qty, source_version
)
VALUES (
    'PEN', 'But bi xanh', 12500, 15, 4
)
ON CONFLICT(sku) DO UPDATE SET
    product_name = excluded.product_name,
    unit_price = excluded.unit_price,
    stock_qty = excluded.stock_qty,
    source_version = excluded.source_version
WHERE excluded.source_version > catalog.source_version;
~~~

SQLite có `RETURNING` từ **3.35.0**. Cần kiểm tra phiên bản SQLite **được nhúng trong ứng dụng**, vì thiết bị hoặc thư viện không phải lúc nào cũng dùng bản giống môi trường phát triển.

### 20.3. MySQL: ON DUPLICATE KEY UPDATE

MySQL có cơ chế:

~~~sql
-- MySQL minh hoa, bang catalog da ton tai.
INSERT INTO catalog (sku, unit_price)
VALUES ('PEN', 12500) AS incoming
ON DUPLICATE KEY UPDATE
    unit_price = incoming.unit_price;
~~~

Đây là ví dụ cú pháp **ghi đè khi gặp khóa duy nhất trùng**, **chưa** có quy tắc “chỉ nhận phiên bản mới hơn”. Với MySQL, muốn giữ phiên bản phải xây điều kiện rõ ràng trong các phép gán hoặc thiết kế lệnh/transaction phù hợp.

Đặc biệt:

- Xung đột có thể xảy ra trên **nhiều chỉ mục duy nhất**, không nhất thiết chỉ một `sku` như cách `ON CONFLICT (sku)` chỉ định trong PostgreSQL.
- Trong MySQL 8.0 hiện đại, dạng `VALUES(col)` dùng ở `ON DUPLICATE KEY UPDATE` đã bị khuyến cáo không dùng trong những phiên bản phù hợp; cú pháp bí danh hàng mới có thể là lựa chọn thay thế, cần xem chính xác phiên bản.
- Cách đánh giá nhiều phép gán trong `SET` và hàm có điều kiện cần được kiểm tra để tránh phép gán phiên bản làm thay đổi ý nghĩa điều kiện của các phép gán sau.
- `INSERT IGNORE` hoặc `REPLACE` **không tương đương** với chính sách upsert có kiểm soát; `REPLACE` có thể gây tác động xóa/chèn, khóa ngoại hoặc trigger ngoài mong đợi.

Không sao chép thẳng `EXCLUDED` hoặc `MERGE` PostgreSQL sang MySQL rồi kỳ vọng chạy.

### 20.4. SQL Server: MERGE và OUTPUT $action

SQL Server có `MERGE` theo cú pháp T-SQL. Ví dụ:

~~~sql
-- T-SQL minh hoa: dbo.Catalog va dbo.Incoming da ton tai.
MERGE INTO dbo.Catalog AS c
USING dbo.Incoming AS i
ON c.sku = i.sku
WHEN MATCHED AND i.source_version > c.source_version THEN
    UPDATE SET
        c.product_name = i.product_name,
        c.unit_price = i.unit_price,
        c.stock_qty = i.stock_qty,
        c.source_version = i.source_version
WHEN NOT MATCHED BY TARGET THEN
    INSERT (sku, product_name, unit_price, stock_qty, source_version)
    VALUES (
        i.sku, i.product_name, i.unit_price,
        i.stock_qty, i.source_version
    )
OUTPUT
    $action AS merge_action,
    INSERTED.sku;
~~~

`OUTPUT $action` cho biết nhánh thao tác **INSERT/UPDATE/DELETE thực hiện** trong SQL Server. Các hàng không có hành động có thể không xuất hiện trong `OUTPUT`.

**Chú ý đồng thời:** `MERGE` trên SQL Server có các vấn đề và khuyến nghị thận trọng phụ thuộc phiên bản, chỉ mục và mức cô lập. Nhiều hệ thống chọn tổ hợp `UPDATE`/`INSERT` có transaction/khóa phù hợp thay vì dùng một `MERGE` phức tạp. Cần xem tài liệu và chính sách của hệ quản trị đang chạy; đừng giả định cú pháp ngắn hơn là an toàn hơn trước race condition.

### 20.5. Oracle Database: MERGE

Oracle thường dùng `MERGE INTO ... USING ... ON ... WHEN MATCHED THEN UPDATE ... WHEN NOT MATCHED THEN INSERT`:

~~~sql
-- Oracle SQL minh hoa; catalog va incoming da ton tai.
MERGE INTO catalog c
USING incoming i
ON (c.sku = i.sku)
WHEN MATCHED THEN
    UPDATE SET
        c.product_name = i.product_name,
        c.unit_price = i.unit_price,
        c.stock_qty = i.stock_qty,
        c.source_version = i.source_version
    WHERE i.source_version > c.source_version
WHEN NOT MATCHED THEN
    INSERT (
        sku, product_name, unit_price, stock_qty, source_version
    )
    VALUES (
        i.sku, i.product_name, i.unit_price,
        i.stock_qty, i.source_version
    );
~~~

Khác PostgreSQL, Oracle đặt điều kiện lọc của **nhánh UPDATE** trong `WHEN MATCHED ... UPDATE ... WHERE ...` theo cú pháp Oracle. Không nên mang nguyên vị trí điều kiện hoặc cách tham chiếu cột của Oracle sang PostgreSQL.

### 20.6. Bảng lựa chọn nhanh

| Hệ quản trị | Cú pháp thường dùng cho thêm/cập nhật | Cách biểu đạt bỏ qua |
| --- | --- | --- |
| **PostgreSQL** | `INSERT ... ON CONFLICT DO UPDATE`, `MERGE` (15+) | `DO NOTHING`, `DO UPDATE WHERE` không đạt, hoặc MERGE không có nhánh hành động |
| **SQLite** | `INSERT ... ON CONFLICT DO UPDATE` | `DO NOTHING` hoặc `WHERE` của DO UPDATE không đạt |
| **MySQL** | `INSERT ... ON DUPLICATE KEY UPDATE` | Điều kiện/quy tắc trên phép gán hoặc logic transaction riêng; `INSERT IGNORE` có ngữ nghĩa khác |
| **SQL Server** | `MERGE`; hoặc UPDATE/INSERT trong transaction | Không có nhánh hành động áp dụng |
| **Oracle** | `MERGE` hoặc các câu có điều kiện thích hợp | Điều kiện `WHERE` trong nhánh UPDATE hoặc không có nhánh áp dụng |

**Cảnh báo chuyển hệ:** cú pháp chỉ là một phần. Còn phải kiểm tra **trùng khóa, giá trị `NULL`, bội số nguồn, ràng buộc, xử lý đồng thời, số hàng ảnh hưởng và khả năng trả nhãn hành động**.

## 21. Quy trình triển khai một lô nhập an toàn

Một quy trình thực tế thường gồm những bước sau:

### Bước 1 — Xác định nguồn là snapshot hay delta

- **Snapshot đầy đủ:** nguồn tuyên bố chứa trạng thái của tất cả đối tượng tại một mốc.
- **Delta:** nguồn chỉ chứa các đối tượng/sự kiện thay đổi.

Với **delta**, việc một SKU vắng mặt không có nghĩa phải xóa nó. Với **snapshot đầy đủ**, việc vắng mặt cũng chưa tự chứng minh cần xóa, trừ khi đã có chính sách rõ.

### Bước 2 — Xác định khóa và quy tắc phiên bản

- Khóa là `sku` hay tổ hợp `tenant_id, sku`?
- Một khóa nguồn có xuất hiện nhiều lần trong lô không?
- Phiên bản nào được xem là mới hơn?
- Cùng phiên bản nhưng khác nội dung thì xử lý thế nào?

### Bước 3 — Kiểm tra tính hợp lệ trước khi ghi

Kiểm tra giá âm, tồn âm, khóa thiếu, độ dài dữ liệu, trùng khóa trong staging và bất thường cùng phiên bản khác nội dung. Những lỗi này không nên bị biến thành “SKIP bình thường”.

### Bước 4 — Xem trước hành động

Chạy `SELECT LEFT JOIN CASE` của mục 4 và đối chiếu số hàng kỳ vọng. Với dữ liệu thực hành: 2 INSERT, 2 UPDATE, 2 SKIP_DUPLICATE, 1 SKIP_STALE.

### Bước 5 — Thực thi trong transaction

Ví dụ `BEGIN; ... INSERT ON CONFLICT ...; SELECT ...; ROLLBACK;` khi thử nghiệm. Trong tác vụ thật, chỉ `COMMIT` khi các điều kiện kiểm soát và quy trình cho phép.

### Bước 6 — Ghi nhận kết quả và theo dõi lỗi

Cần biết lô nào đã được nhận, phiên bản nào được áp dụng, hàng nào bị bỏ qua vì cũ/trùng, hàng nào có xung đột, và transaction có commit không. Chỉ nhìn số hàng `RETURNING` không đủ cho mọi câu hỏi.

### Bước 7 — Thiết kế retry có kiểm soát

Lô gửi lại phải không làm nhân đôi số lượng hoặc giảm phiên bản. Nếu thao tác là cập nhật tuyệt đối theo phiên bản, điều kiện upsert có thể giúp đạt mục tiêu; nếu là sự kiện tăng/giảm tồn, cần cơ chế ID sự kiện duy nhất hoặc sổ cái.

## 22. Những lỗi thường gặp

| Hiện tượng/cách viết | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| `INSERT` thường vào SKU đã có | Lỗi khóa duy nhất | Dùng upsert khi đúng nhu cầu |
| Dùng `DO NOTHING` cho mọi SKU đã có | Bỏ qua cả dữ liệu thực sự mới | Dùng `DO UPDATE` có điều kiện phiên bản |
| Dùng `DO UPDATE` không có `WHERE` | Dữ liệu cũ có thể ghi đè bản mới | Kiểm tra phiên bản/độ mới |
| Xem mọi hàng bị bỏ qua là dữ liệu trùng | Có thể là bản cũ hoặc cùng phiên bản nhưng khác nội dung | Phân loại SKIP_STALE, SKIP_DUPLICATE, REVIEW_CONFLICT |
| Không có unique key trên định danh | Không xác định một sản phẩm là hàng nào | Tạo khóa chính/unique phù hợp |
| `MERGE ON sku = sku AND version_new > version_old` | Hàng đã tồn tại nhưng bản cũ bị coi NOT MATCHED, có thể cố INSERT trùng | Để `ON` chỉ định danh, điều kiện phiên bản ở `WHEN MATCHED AND` |
| Nguồn có hai hàng cùng SKU trong một lệnh | Có thể lỗi cardinality/unique; không xác định bản nào đúng | Kiểm tra, chuẩn hóa/khử trùng theo chính sách |
| Chọn một bản nguồn bằng `LIMIT 1` không ORDER BY | Không xác định bản mới nhất | Xếp theo phiên bản/thời gian và khóa phân định |
| Dùng `SELECT DISTINCT *` để xóa mọi vấn đề trùng | Không giải quyết hai hàng cùng khóa nhưng khác nội dung | Kiểm tra trùng theo khóa nghiệp vụ |
| Nhầm `EXCLUDED` là hàng cũ | `EXCLUDED` là hàng đề xuất chèn | Dùng bí danh đích cho giá trị đang lưu |
| Dùng `SET x = x` để “bỏ qua” | Vẫn có thể là UPDATE thực sự, sinh log/trigger | Dùng `DO NOTHING` hoặc điều kiện ngăn UPDATE |
| Cho rằng `RETURNING` liệt kê cả SKIP | Hàng không chèn/cập nhật thường không được trả | Có nguồn phân loại/audit riêng |
| Dùng `MAX(id)` để đoán hàng vừa thêm | Không an toàn với concurrency | Dùng `RETURNING` hoặc API generated key của dialect |
| Chạy lại sự kiện cộng tồn như upsert gán giá trị tuyệt đối | Có thể sai bản chất nghiệp vụ hoặc cộng đôi | Phân biệt state update và event processing |
| Cho rằng `MERGE` luôn giống `ON CONFLICT` khi đồng thời | Các bảo đảm và cách xử lý unique violation khác nhau | Dùng transaction, retry và công cụ phù hợp |
| Bản nguồn có giá âm nhưng nghĩ `DO NOTHING` sẽ bỏ qua | Ràng buộc dữ liệu vẫn phải được kiểm tra | Kiểm tra staging và giữ ràng buộc |
| Tự xóa hàng đích vì không có trong lô nguồn | Lô có thể chỉ là delta hoặc không đầy đủ | Chỉ xóa theo chính sách snapshot được xác thực |
| Dùng cú pháp một dialect cho mọi hệ | MySQL, SQLite, SQL Server, Oracle và PostgreSQL khác nhau | Kiểm tra phiên bản/cú pháp/hành vi cụ thể |

## 23. Bài tập thực hành có đáp án

Các bài từ 1 đến 11 dựa trên hai bảng `lab_up290_catalog` và `lab_up290_incoming` ở mục 3. **Mỗi bài là tình huống độc lập trên dữ liệu ban đầu.** Nếu bài có thao tác ghi, đáp án bao trong `BEGIN ... ROLLBACK` để tránh làm thay đổi kết quả những bài sau. Các đoạn đánh dấu “không chạy” là tình huống cần phân tích, không phải câu lệnh cần thực thi.

### Bài 1 — Nhận diện hàng cần thêm

**Yêu cầu:** lấy các SKU chỉ có ở lô nguồn, chưa có trong danh mục.

**Đáp án:**

~~~sql
SELECT i.sku, i.product_name
FROM lab_up290_incoming AS i
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_up290_catalog AS c
    WHERE c.sku = i.sku
)
ORDER BY i.sku;
~~~

Kết quả là **KEY** và **PAD**. Đây là cách kiểm tra **sự tồn tại theo khóa**, không cần so giá hay tồn kho.

### Bài 2 — Nhận diện hàng có phiên bản mới hơn

**Yêu cầu:** liệt kê các hàng đã có ở đích mà phiên bản của nguồn lớn hơn.

**Đáp án:**

~~~sql
SELECT
    i.sku,
    c.source_version AS old_version,
    i.source_version AS new_version
FROM lab_up290_incoming AS i
JOIN lab_up290_catalog AS c
    ON c.sku = i.sku
WHERE i.source_version > c.source_version
ORDER BY i.sku;
~~~

Kết quả **PEN (3 → 4)** và **USB (2 → 3)**.

### Bài 3 — Phân biệt trùng dữ liệu và phiên bản cũ

**Yêu cầu:** liệt kê các SKU đã có với phiên bản nguồn không lớn hơn phiên bản đích, kèm lý do.

**Đáp án:**

~~~sql
SELECT
    i.sku,
    CASE
        WHEN i.source_version < c.source_version
            THEN 'SKIP_STALE'
        WHEN ROW(
            i.product_name, i.unit_price, i.stock_qty
        ) IS NOT DISTINCT FROM ROW(
            c.product_name, c.unit_price, c.stock_qty
        ) THEN 'SKIP_DUPLICATE'
        ELSE 'REVIEW_CONFLICT'
    END AS reason
FROM lab_up290_incoming AS i
JOIN lab_up290_catalog AS c
    ON c.sku = i.sku
WHERE i.source_version <= c.source_version
ORDER BY i.sku;
~~~

Kết quả **BAG SKIP_DUPLICATE, MOUSE SKIP_STALE, NOTE SKIP_DUPLICATE**.

### Bài 4 — INSERT mới hoặc SKIP bằng DO NOTHING

**Yêu cầu:** thử chèn `PEN` và kiểm tra nó có được cập nhật không khi dùng `DO NOTHING`.

**Đáp án:**

~~~sql
BEGIN;

INSERT INTO lab_up290_catalog (
    sku, product_name, unit_price, stock_qty, source_version
)
VALUES (
    'PEN', 'Bút bi xanh', 12500.00, 15, 4
)
ON CONFLICT (sku) DO NOTHING
RETURNING sku, unit_price;

SELECT sku, unit_price, source_version
FROM lab_up290_catalog
WHERE sku = 'PEN';

ROLLBACK;
~~~

`RETURNING` không có hàng; `SELECT` cho giá **12000**, phiên bản **3** như cũ. `DO NOTHING` bỏ qua, **không phải UPDATE**.

### Bài 5 — UPDATE đúng khi phiên bản mới hơn

**Yêu cầu:** cập nhật sản phẩm `PEN` từ bản nguồn phiên bản 4 nhưng không ghi đè nếu nó đã lên phiên bản 4 hoặc cao hơn.

**Đáp án:**

~~~sql
BEGIN;

INSERT INTO lab_up290_catalog AS c (
    sku, product_name, unit_price, stock_qty, source_version
)
VALUES (
    'PEN', 'Bút bi xanh', 12500.00, 15, 4
)
ON CONFLICT (sku) DO UPDATE SET
    product_name = EXCLUDED.product_name,
    unit_price = EXCLUDED.unit_price,
    stock_qty = EXCLUDED.stock_qty,
    source_version = EXCLUDED.source_version
WHERE EXCLUDED.source_version > c.source_version
RETURNING sku, unit_price, stock_qty, source_version;

ROLLBACK;
~~~

Kết quả **PEN, 12500, 15, phiên bản 4**.

### Bài 6 — SKIP bản cũ

**Yêu cầu:** áp dụng cùng chính sách cho `MOUSE` phiên bản 4, trong khi đích đã lưu phiên bản 5.

**Đáp án:** thay dữ liệu `VALUES` của bài 5 thành:

~~~sql
VALUES ('MOUSE', 'Chuột có dây', 160000.00, 6, 4)
~~~

và giữ toàn bộ `ON CONFLICT ... DO UPDATE ... WHERE EXCLUDED.source_version > c.source_version`. Vì `4 > 5` sai, câu lệnh **không sửa MOUSE**; giá đích vẫn **170000** và phiên bản vẫn **5**. Đoạn `VALUES` ở trên chỉ là **phần thay thế trong câu INSERT đầy đủ**, không chạy độc lập.

### Bài 7 — Upsert cả lô từ bảng staging

**Yêu cầu:** dùng một lệnh SQL để chèn những SKU mới và cập nhật những SKU có phiên bản nguồn mới hơn. Không ghi đè các hàng stale/duplicate.

**Đáp án:**

~~~sql
BEGIN;

INSERT INTO lab_up290_catalog AS c (
    sku, product_name, unit_price, stock_qty, source_version
)
SELECT
    i.sku, i.product_name, i.unit_price, i.stock_qty, i.source_version
FROM lab_up290_incoming AS i
WHERE TRUE
ON CONFLICT (sku) DO UPDATE SET
    product_name = EXCLUDED.product_name,
    unit_price = EXCLUDED.unit_price,
    stock_qty = EXCLUDED.stock_qty,
    source_version = EXCLUDED.source_version,
    updated_at = CURRENT_TIMESTAMP
WHERE EXCLUDED.source_version > c.source_version
RETURNING sku, unit_price, source_version;

ROLLBACK;
~~~

Có **4 hàng trả về** tương ứng KEY, PAD, PEN, USB. MOUSE, NOTE, BAG được bỏ qua; BOOK không thuộc lô nhập nên giữ nguyên.

### Bài 8 — MERGE cùng chính sách

**Yêu cầu:** viết lại bài 7 bằng `MERGE` trên PostgreSQL 15+.

**Đáp án:**

~~~sql
BEGIN;

MERGE INTO lab_up290_catalog AS c
USING lab_up290_incoming AS i
ON c.sku = i.sku
WHEN MATCHED
     AND i.source_version > c.source_version THEN
    UPDATE SET
        product_name = i.product_name,
        unit_price = i.unit_price,
        stock_qty = i.stock_qty,
        source_version = i.source_version
WHEN NOT MATCHED THEN
    INSERT (sku, product_name, unit_price, stock_qty, source_version)
    VALUES (
        i.sku, i.product_name, i.unit_price,
        i.stock_qty, i.source_version
    );

SELECT sku, unit_price, stock_qty, source_version
FROM lab_up290_catalog
ORDER BY sku;

ROLLBACK;
~~~

Trong transaction, bảng đích có tám SKU; KEY/PAD được thêm, PEN/USB được cập nhật. Bảng đích trở về sáu SKU ban đầu sau `ROLLBACK`.

### Bài 9 — Tìm lỗi khi điều kiện phiên bản bị đặt vào MERGE ON

Cho câu sai:

~~~sql
-- KHONG CHAY:
MERGE INTO lab_up290_catalog AS c
USING lab_up290_incoming AS i
ON c.sku = i.sku
   AND i.source_version > c.source_version
WHEN MATCHED THEN
    UPDATE SET unit_price = i.unit_price
WHEN NOT MATCHED THEN
    INSERT (sku, product_name, unit_price, stock_qty, source_version)
    VALUES (
        i.sku, i.product_name, i.unit_price,
        i.stock_qty, i.source_version
    );
~~~

**Câu hỏi:** điều gì có thể xảy ra với MOUSE?

**Đáp án:** vì nguồn phiên bản 4 không lớn hơn phiên bản đích 5, điều kiện `ON` sai. MOUSE bị xếp vào **NOT MATCHED** dù SKU thực sự tồn tại, rồi câu `INSERT` có thể vi phạm `PRIMARY KEY(sku)`. Chỉ dùng `c.sku = i.sku` để nhận diện MATCHED, chuyển điều kiện phiên bản sang `WHEN MATCHED AND ...`.

### Bài 10 — Cùng phiên bản nhưng khác giá

**Tình huống:** nguồn gửi `NOTE` phiên bản 2 với giá 37000; đích có `NOTE` phiên bản 2 nhưng giá 35000.

**Câu hỏi:** đây là INSERT, UPDATE, SKIP_DUPLICATE hay trường hợp khác?

**Đáp án:** theo chính sách bài, đó là **REVIEW_CONFLICT**, vì cùng phiên bản nhưng dữ liệu không giống nhau. Một câu `DO UPDATE WHERE incoming_version > stored_version` sẽ bỏ qua hàng này theo điều kiện, nhưng **bỏ qua không có nghĩa dữ liệu nguồn hợp lệ**. Cần phát hiện bằng `source_version = target.source_version` kết hợp `ROW(...) IS DISTINCT FROM ROW(...)`, rồi gửi tới quy trình rà soát.

### Bài 11 — Nguồn chứa trùng khóa

**Tình huống:** bảng staging thô chứa hai hàng `PEN` phiên bản 4 và 5.

**Yêu cầu:** giải thích tại sao không nên đưa trực tiếp cả hai vào một lệnh `INSERT ... ON CONFLICT DO UPDATE` trên PostgreSQL.

**Đáp án:** một câu upsert có thể cố **tác động cùng một hàng đích nhiều lần**, dẫn tới lỗi cardinality. Cần kiểm tra bội số theo SKU và chuẩn hóa nguồn. Nếu quy tắc là chọn phiên bản lớn nhất, có thể dùng `ROW_NUMBER() OVER (PARTITION BY sku ORDER BY source_version DESC, event_id DESC)`, sau khi bảo đảm không có cùng phiên bản khác nội dung cần được rà soát.

### Bài 12 — Phân biệt lô delta và snapshot

**Tình huống:** SKU BOOK có trong catalog nhưng không xuất hiện trong bảng incoming. Người viết đề nghị xóa BOOK ngay sau MERGE.

**Đáp án:** **không được suy ra cần xóa chỉ vì vắng mặt**. Lô incoming có thể là **delta**, chỉ gửi những sản phẩm thay đổi. Ngay cả nếu là snapshot đầy đủ, việc xóa còn phụ thuộc quy tắc nghiệp vụ, độ tin cậy của mốc dữ liệu và ràng buộc liên quan. Với chính sách bài, BOOK giữ nguyên.

### Bài 13 — Chạy lại lô có an toàn không?

**Yêu cầu:** nếu lần đồng bộ đầu đã commit thành công, lần thứ hai gửi y hệt bảy hàng nguồn sẽ tạo bao nhiêu INSERT, UPDATE và SKIP theo điều kiện phiên bản?

**Đáp án:** **0 INSERT, 0 UPDATE, 7 SKIP**. KEY/PAD hiện đã có phiên bản 1, PEN đã có phiên bản 4, USB đã có phiên bản 3, còn NOTE/BAG/MOUSE vẫn không mới hơn. Việc bỏ qua không làm nhân đôi giá hoặc số lượng tồn.

Đây là kết quả với **dữ liệu nguồn và bảng đích không thay đổi theo cách khác giữa hai lần**, và chính sách upsert gán trạng thái tuyệt đối. Nếu dùng thao tác cộng thêm tồn kho theo sự kiện mà không có cơ chế chống lặp, kết luận này không còn đúng.

## 24. Ghi nhớ và cách lựa chọn

| Câu hỏi | Quy tắc/cú pháp cần nhớ |
| --- | --- |
| “Đây là sản phẩm mới hay đã có?” | So **khóa định danh duy nhất** (`sku` hoặc khóa ghép) |
| “Có thể thêm mới?” | Chưa có khóa → **INSERT** |
| “Có nên cập nhật?” | Đã có khóa **và** nguồn mới hơn → **UPDATE** |
| “Có nên bỏ qua?” | Đã có khóa, dữ liệu trùng hoặc nguồn cũ → **SKIP** theo chính sách |
| “Cùng phiên bản mà khác nội dung?” | **REVIEW_CONFLICT**, không tự coi là trùng |
| “Chỉ thêm nếu chưa có?” | PostgreSQL: `INSERT ... ON CONFLICT (key) DO NOTHING` |
| “Thêm hoặc cập nhật khi mới hơn?” | `ON CONFLICT (key) DO UPDATE SET ... WHERE EXCLUDED.version > target.version` |
| “Muốn diễn đạt từng trường hợp MATCHED?” | `MERGE ... USING ... ON key ... WHEN MATCHED ... WHEN NOT MATCHED ...` |
| “Nguồn trùng khóa trong cùng lô?” | Xác minh/deduplicate **trước** khi upsert hoặc MERGE |
| “Hàng đích không có trong nguồn?” | Không tự xóa nếu chưa có quy tắc **snapshot đầy đủ** và xử lý thiếu hàng |
| “Cần biết chính xác hàng đã sửa?” | Dùng `RETURNING` hoặc cơ chế audit của đúng dialect; SKIP thường không nằm trong kết quả |
| “Cần retry?” | Thiết kế phiên bản, khóa duy nhất, transaction và xử lý concurrency |

Khi gặp một lô nhập mới, hãy tách **quyết định nghiệp vụ** khỏi **cú pháp SQL**. Khóa duy nhất trả lời **“có phải cùng một thực thể không?”**; phiên bản và nội dung trả lời **“nên cập nhật hay bỏ qua?”**; còn `ON CONFLICT` hoặc `MERGE` là công cụ hiện thực các nhánh đó. Một quy trình upsert đáng tin cậy không chỉ chèn và cập nhật đúng, mà còn **bỏ qua đúng lý do, phát hiện dữ liệu bất thường, và bảo vệ trạng thái mới hơn khỏi bị ghi đè bởi nguồn cũ**.
