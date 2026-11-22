# Phân biệt xử lý xung đột với bỏ qua mọi lỗi

## 1. Xung đột dữ liệu không đồng nghĩa với mọi lỗi của INSERT

Trong hệ thống thực tế, ứng dụng có thể gửi cùng một yêu cầu tạo dữ liệu nhiều lần: người dùng nhấn nút hai lần, một tác vụ import chạy lại hoặc một dịch vụ retry sau khi mất kết nối. Khi thêm một sản phẩm có cùng mã `sku`, cơ sở dữ liệu có thể báo lỗi **trùng khóa duy nhất**.

Một yêu cầu nghiệp vụ hợp lý là:

> Nếu mã sản phẩm đã tồn tại, đừng tạo bản sao; hoặc cập nhật bản ghi đó theo quy tắc đã định nghĩa.

Đó là **xử lý xung đột** (*conflict handling*, một thành phần của `UPSERT`). Nhưng có một yêu cầu khác nguy hiểm hơn nhiều:

> Bất kỳ lỗi nào xảy ra trong lúc chèn thì cứ bỏ qua, coi như thành công.

Hai yêu cầu này **khác hẳn nhau**. Việc bỏ qua một bản ghi đã có sẵn có thể đúng nghiệp vụ; việc nuốt lỗi dữ liệu âm, khóa ngoại không tồn tại, cột bắt buộc bị `NULL` hoặc dữ liệu sai kiểu sẽ khiến ứng dụng **mất dữ liệu hoặc báo thành công sai**.

Một số cơ chế SQL cần phân biệt:

| Cơ chế | Ý định chính | Điều không được suy ra |
| --- | --- | --- |
| PostgreSQL `ON CONFLICT ... DO NOTHING` | Không chèn khi gặp xung đột uniqueness/exclusion phù hợp | Không phải `IGNORE ALL ERRORS` |
| PostgreSQL `ON CONFLICT ... DO UPDATE` | Chuyển xung đột uniqueness phù hợp thành cập nhật | Không làm mọi lỗi constraint hợp lệ |
| MySQL `ON DUPLICATE KEY UPDATE` | Cập nhật khi vi phạm khóa chính/khóa duy nhất | Không cho chọn arbiter rõ như `ON CONFLICT (sku)` |
| MySQL `INSERT IGNORE` | Bỏ qua/giảm cấp một số loại lỗi theo quy tắc MySQL | Không phải cơ chế “chỉ bỏ trùng SKU” hay “không lỗi nào còn xảy ra” |
| SQLite `INSERT OR IGNORE` | Bỏ qua hàng vi phạm một số constraint cụ thể | Không bỏ qua lỗi khóa ngoại như một quy tắc chung |
| SQLite UPSERT `ON CONFLICT ... DO NOTHING/UPDATE` | Xử lý xung đột uniqueness | Không tự xử lý `NOT NULL`, `CHECK`, FK |
| SQL `MERGE` trên DBMS hỗ trợ | Chọn INSERT/UPDATE/DELETE tùy hàng khớp nguồn | Không tự miễn kiểm tra dữ liệu hay bảo đảm không có race |
| Bắt mọi exception ở ứng dụng | Che mọi kiểu thất bại nếu dùng sai | Không đồng nghĩa với idempotency |

**Mục tiêu bài học:** biết lỗi nào có thể được xử lý có chủ đích, lỗi nào bắt buộc phải được báo ra, cách kiểm chứng số hàng đã ghi và cách thiết kế thao tác tạo/cập nhật an toàn khi có nhiều người dùng hoặc retry.

## 2. Phân biệt các nhóm lỗi thường gặp khi ghi dữ liệu

### 2.1. Lỗi uniqueness: giá trị đã có

Ví dụ cột `sku` có ràng buộc `UNIQUE`:

~~~sql
CREATE TABLE demo_skus (
    sku VARCHAR(30) PRIMARY KEY,
    label VARCHAR(100) NOT NULL
);

INSERT INTO demo_skus (sku, label)
VALUES ('BK-001', 'So tay');
~~~

Chèn lần nữa:

~~~sql
INSERT INTO demo_skus (sku, label)
VALUES ('BK-001', 'So tay ban khac');
~~~

Thông thường DBMS từ chối vì một khóa `BK-001` đã có. Đây là **xung đột định danh**: có thể quyết định bỏ qua, cập nhật hoặc trả lỗi 409/duplicate theo hợp đồng ứng dụng.

### 2.2. Lỗi NOT NULL: thiếu trường bắt buộc

~~~sql
-- label là NOT NULL.
INSERT INTO demo_skus (sku, label)
VALUES ('BK-002', NULL);
~~~

Đây không phải dữ liệu trùng khóa. Nếu bỏ qua lỗi này, ứng dụng có thể làm mất hàng `BK-002` mà không ai biết, dù việc thiếu tên có thể là lỗi nghiêm trọng của nguồn dữ liệu.

### 2.3. Lỗi CHECK: giá trị vi phạm quy tắc

~~~sql
CREATE TABLE demo_stock (
    sku VARCHAR(30) PRIMARY KEY,
    stock_qty INTEGER NOT NULL CHECK (stock_qty >= 0)
);

-- Sai miền giá trị tồn kho:
INSERT INTO demo_stock (sku, stock_qty)
VALUES ('PN-001', -5);
~~~

Chính sách “nếu trùng SKU thì không làm gì” **không có lý do** để nuốt lỗi tồn âm.

### 2.4. Lỗi FOREIGN KEY: liên kết không tồn tại

~~~sql
CREATE TABLE demo_vendors (
    vendor_id INTEGER PRIMARY KEY,
    vendor_name VARCHAR(100) NOT NULL
);

CREATE TABLE demo_vendor_items (
    sku VARCHAR(30) PRIMARY KEY,
    vendor_id INTEGER NOT NULL
        REFERENCES demo_vendors(vendor_id)
);

-- vendor_id=999 chưa có trong bảng vendor:
INSERT INTO demo_vendor_items (sku, vendor_id)
VALUES ('KB-001', 999);
~~~

Đây là lỗi **toàn vẹn tham chiếu**, không phải lỗi trùng khóa. Một tác vụ import đúng phải xác minh vendor, ghi vào vùng staging để xử lý, hoặc báo thất bại tùy nghiệp vụ.

### 2.5. Sai kiểu, tràn số và lỗi hệ thống

Những lỗi khác có thể gồm:

- Chuỗi không đổi được sang kiểu số/ngày;
- Giá trị quá độ rộng cột hoặc ngoài phạm vi kiểu;
- Deadlock, lock timeout, lỗi kết nối;
- Thiếu quyền ghi, sai tên bảng/cột, cú pháp sai;
- Trigger hoặc hàm do ứng dụng khai báo phát sinh lỗi.

Chúng **không trở thành “dữ liệu đã tồn tại”** chỉ vì cùng xuất hiện ở câu `INSERT`. Một cơ chế xử lý trùng khóa tốt cần có **phạm vi lỗi rõ ràng**.

## 3. Schema thực hành: sản phẩm và nhà cung cấp

Các ví dụ chính trong phần 3–9 sử dụng **PostgreSQL**. Những phần dành cho MySQL, SQLite, SQL Server và Oracle sẽ được ghi rõ.

### 3.1. Tạo bảng

~~~sql
CREATE TABLE vendors (
    vendor_id INTEGER PRIMARY KEY,
    vendor_name VARCHAR(100) NOT NULL
);

INSERT INTO vendors (vendor_id, vendor_name)
VALUES
    (10, 'Alpha Supply'),
    (20, 'Beta Supply');

CREATE TABLE catalog_products (
    product_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(30) NOT NULL UNIQUE,
    external_code VARCHAR(30) UNIQUE,
    product_name VARCHAR(100) NOT NULL,
    category_code VARCHAR(20) NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL,
    stock_qty INTEGER NOT NULL DEFAULT 0,
    vendor_id INTEGER NOT NULL REFERENCES vendors(vendor_id),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_catalog_category
        CHECK (category_code IN ('BOOK', 'TOOL', 'DEVICE')),
    CONSTRAINT chk_catalog_price
        CHECK (unit_price >= 0),
    CONSTRAINT chk_catalog_stock
        CHECK (stock_qty >= 0)
);
~~~

Tạo dữ liệu:

~~~sql
INSERT INTO catalog_products (
    sku, external_code, product_name, category_code,
    unit_price, stock_qty, vendor_id
)
VALUES
    ('BK-001', 'ERP-A1', 'So tay',  'BOOK',   100.00, 10, 10),
    ('PN-002', 'ERP-B2', 'But bi',  'TOOL',    20.00,  4, 20),
    ('HD-003', 'ERP-C3', 'Tai nghe','DEVICE', 300.00,  2, 10);
~~~

Bảng khởi tạo:

| SKU | external_code | Tên | Loại | Giá | Tồn | vendor_id |
| --- | --- | --- | --- | ---: | ---: | ---: |
| BK-001 | ERP-A1 | So tay | BOOK | 100.00 | 10 | 10 |
| PN-002 | ERP-B2 | But bi | TOOL | 20.00 | 4 | 20 |
| HD-003 | ERP-C3 | Tai nghe | DEVICE | 300.00 | 2 | 10 |

### 3.2. Ràng buộc là lớp bảo vệ bắt buộc

Trong bảng này:

- `product_id` là identity PK, dùng làm khóa nội bộ.
- `sku` là khóa nghiệp vụ `UNIQUE NOT NULL`.
- `external_code` là một khóa `UNIQUE` **khác**; có thể `NULL`.
- `product_name` và `category_code` bắt buộc.
- `unit_price` và `stock_qty` không được âm.
- `vendor_id` phải tồn tại trong `vendors`.

Việc có **hai khóa duy nhất khác nhau** sẽ giúp thấy khác biệt giữa “bỏ qua trùng SKU” và “bỏ qua mọi loại trùng”.

Các ví dụ thay đổi dữ liệu nên chạy riêng trong transaction rồi `ROLLBACK` để giữ nguyên dữ liệu cho phần tiếp theo:

~~~sql
BEGIN;

-- Một thử nghiệm INSERT / UPSERT ở đây.

ROLLBACK;
~~~

Nếu câu lệnh phát sinh lỗi PostgreSQL trong transaction, transaction đó có thể chuyển sang trạng thái lỗi. Khi ấy cần `ROLLBACK` hoặc `ROLLBACK TO SAVEPOINT` đúng cách trước khi tiếp tục, không chạy hàng loạt lệnh như thể không có lỗi.

## 4. PostgreSQL: ON CONFLICT DO NOTHING xử lý cái gì?

### 4.1. Chọn đúng khóa xung đột

Giả sử hệ thống nhận lại sản phẩm `BK-001` đã tồn tại. Ta muốn **bỏ qua riêng xung đột SKU**:

~~~sql
BEGIN;

INSERT INTO catalog_products (
    sku, external_code, product_name, category_code,
    unit_price, stock_qty, vendor_id
)
VALUES (
    'BK-001', 'ERP-A1', 'So tay tu import',
    'BOOK', 100.00, 10, 10
)
ON CONFLICT (sku) DO NOTHING
RETURNING product_id, sku;

ROLLBACK;
~~~

Vì `BK-001` đã tồn tại:

- Không tạo thêm bản ghi `BK-001`.
- Không cập nhật sản phẩm `BK-001` đang có.
- `RETURNING` **không trả hàng** cho dòng bị bỏ qua.

Phần `(sku)` được gọi là **conflict target**: xác định arbiter uniqueness mà câu lệnh chủ đích xử lý. Với PostgreSQL, `ON CONFLICT DO NOTHING` có thể bỏ conflict target, nhưng khi chỉ muốn xử lý đúng một khóa nghiệp vụ, nêu rõ target giúp thiết kế dễ hiểu và dễ phát hiện những xung đột khác.

### 4.2. Có nhiều UNIQUE khác nhau: target rất quan trọng

Tạo một SKU mới nhưng cố tình dùng lại `external_code` của sản phẩm đã có:

~~~sql
BEGIN;

INSERT INTO catalog_products (
    sku, external_code, product_name, category_code,
    unit_price, stock_qty, vendor_id
)
VALUES (
    'BK-NEW', 'ERP-A1', 'So moi',
    'BOOK', 120.00, 2, 10
)
ON CONFLICT (sku) DO NOTHING;

ROLLBACK;
~~~

Kết quả: **lỗi trùng `external_code`**, vì câu lệnh chỉ cho phép bỏ qua conflict với `sku`. Đây là hành vi cần thiết nếu hệ thống coi xung đột mã ERP là vấn đề phải điều tra, chứ không phải lý do bỏ qua một SKU mới.

Nếu viết:

~~~sql
BEGIN;

INSERT INTO catalog_products (
    sku, external_code, product_name, category_code,
    unit_price, stock_qty, vendor_id
)
VALUES (
    'BK-NEW', 'ERP-A1', 'So moi',
    'BOOK', 120.00, 2, 10
)
ON CONFLICT DO NOTHING
RETURNING sku;

ROLLBACK;
~~~

thì PostgreSQL có thể **bỏ qua cả xung đột uniqueness của `external_code`**, vì conflict target đã được bỏ. Không có hàng được trả về, nhưng nếu ứng dụng chỉ log “INSERT thành công”, người vận hành khó phân biệt **đã thêm** hay **đã bỏ qua**.

**Nguyên tắc:** khi yêu cầu là “trùng SKU thì bỏ qua”, hãy ưu tiên `ON CONFLICT (sku) DO NOTHING`. Không mở rộng sang `ON CONFLICT DO NOTHING` không target chỉ để tránh thêm lỗi nếu nghiệp vụ không cho phép bỏ qua những unique constraint khác.

### 4.3. DO NOTHING không bỏ qua NOT NULL

~~~sql
-- PostgreSQL: lỗi NOT NULL, không được DO NOTHING che đi.
INSERT INTO catalog_products (
    sku, external_code, product_name, category_code,
    unit_price, stock_qty, vendor_id
)
VALUES (
    'BK-NNULL', 'ERP-NNULL', NULL,
    'BOOK', 120.00, 1, 10
)
ON CONFLICT (sku) DO NOTHING;
~~~

`product_name` bắt buộc. Vì `sku='BK-NNULL'` chưa tồn tại, bản ghi vi phạm `NOT NULL`. `DO NOTHING` **không phải bộ lọc lỗi tổng quát**.

### 4.4. DO NOTHING không bỏ qua CHECK

~~~sql
-- PostgreSQL: lỗi CHECK (unit_price >= 0).
INSERT INTO catalog_products (
    sku, external_code, product_name, category_code,
    unit_price, stock_qty, vendor_id
)
VALUES (
    'BK-NEG', 'ERP-NEG', 'So gia am',
    'BOOK', -12.00, 1, 10
)
ON CONFLICT (sku) DO NOTHING;
~~~

Giá âm là dữ liệu không hợp lệ và vẫn phải bị từ chối.

Tương tự, nếu `stock_qty = -1` hoặc `category_code = 'UNKNOWN'` thì những constraint `CHECK` tương ứng vẫn có thể gây lỗi.

### 4.5. DO NOTHING không bỏ qua FOREIGN KEY

~~~sql
-- PostgreSQL: lỗi FK do vendor_id=999 không tồn tại.
INSERT INTO catalog_products (
    sku, external_code, product_name, category_code,
    unit_price, stock_qty, vendor_id
)
VALUES (
    'BK-FK', 'ERP-FK', 'So khong co vendor',
    'BOOK', 50.00, 1, 999
)
ON CONFLICT (sku) DO NOTHING;
~~~

Không được coi `vendor_id=999` là “SKU đã tồn tại”. Đây là dữ liệu thiếu liên kết và cần xử lý bằng cách chèn vendor đúng, mapping ID hợp lệ hoặc từ chối hàng.

### 4.6. DO NOTHING không bỏ qua lỗi kiểu dữ liệu

~~~sql
-- PostgreSQL: 'khong-phai-so' không ép được sang NUMERIC.
INSERT INTO catalog_products (
    sku, external_code, product_name, category_code,
    unit_price, stock_qty, vendor_id
)
VALUES (
    'BK-TYPE', 'ERP-TYPE', 'Sai gia',
    'BOOK', 'khong-phai-so', 1, 10
)
ON CONFLICT (sku) DO NOTHING;
~~~

Lỗi ép kiểu vẫn là lỗi. Trình tự chính xác các loại lỗi có thể xuất hiện khi **một hàng đồng thời vi phạm nhiều ràng buộc** phụ thuộc ngữ cảnh đánh giá; không xây ứng dụng dựa trên việc loại lỗi nào chắc chắn xuất hiện trước trong một hàng sai nhiều chỗ. Trong bài học, mỗi ví dụ lỗi được tạo bằng một SKU mới để nguyên nhân không nhập nhằng.

### 4.7. DO NOTHING không chặn mọi lỗi vận hành

Những lỗi do mất kết nối, quyền truy cập, sai cú pháp, deadlock, hết dung lượng, hàm/trigger lỗi... cũng không tự biến thành thành công chỉ vì có `ON CONFLICT`.

**Phạm vi của `ON CONFLICT` là xử lý xung đột liên quan đến những unique/exclusion arbiters hợp lệ theo PostgreSQL**, không phải tổng quát hóa thành “khi có bất kỳ exception thì tiếp tục”.

## 5. PostgreSQL: DO UPDATE và phạm vi của nó

### 5.1. UPSERT: thêm nếu chưa có, cập nhật khi trùng SKU

~~~sql
BEGIN;

INSERT INTO catalog_products (
    sku, external_code, product_name, category_code,
    unit_price, stock_qty, vendor_id
)
VALUES (
    'BK-001', 'ERP-A1', 'So tay',
    'BOOK', 120.00, 3, 10
)
ON CONFLICT (sku)
DO UPDATE SET
    unit_price = EXCLUDED.unit_price,
    stock_qty = catalog_products.stock_qty + EXCLUDED.stock_qty,
    updated_at = CURRENT_TIMESTAMP
RETURNING sku, unit_price, stock_qty;

ROLLBACK;
~~~

Dữ liệu gốc `BK-001` có `unit_price=100`, `stock_qty=10`. Hàng dự định chèn mang giá 120 và số lượng 3; vì SKU trùng, `DO UPDATE` áp dụng:

| SKU | Giá sau | Tồn sau |
| --- | ---: | ---: |
| BK-001 | 120.00 | 13 |

Ý nghĩa:

- `EXCLUDED` cung cấp các giá trị của **hàng được đề xuất chèn**.
- `catalog_products.stock_qty` là tồn kho của **hàng đã có** trong nhánh cập nhật.
- `DO UPDATE` không đương nhiên sửa mọi cột: chỉ những cột liệt kê trong `SET` được chủ động thay đổi (ngoài tác động schema/trigger).

Nếu SKU chưa tồn tại, nhánh `INSERT` thêm hàng bình thường và vẫn phải vượt qua mọi kiểm tra constraint.

### 5.2. DO UPDATE cũng có thể thất bại

Ví dụ một nhánh cập nhật cố đặt tồn âm:

~~~sql
-- PostgreSQL: nhánh UPDATE vi phạm CHECK.
INSERT INTO catalog_products (
    sku, external_code, product_name, category_code,
    unit_price, stock_qty, vendor_id
)
VALUES (
    'BK-001', 'ERP-A1', 'So tay',
    'BOOK', 120.00, 3, 10
)
ON CONFLICT (sku)
DO UPDATE SET stock_qty = -1;
~~~

Dù xung đột SKU được nhận diện, giá trị mới không hợp lệ vẫn bị constraint từ chối. **“Đã vào nhánh DO UPDATE” không có nghĩa mọi câu lệnh trong đó được miễn kiểm tra ràng buộc.**

Ngoài ra, `ON CONFLICT (sku) DO UPDATE` không có nghĩa lỗi uniqueness phát sinh từ việc sửa `external_code` cũng được bỏ qua. Nếu UPDATE tạo xung đột với một unique constraint khác, lệnh có thể thất bại.

### 5.3. WHERE trong DO UPDATE là một điều kiện nghiệp vụ

Có thể chỉ cập nhật nếu giá đưa vào khác giá đang lưu:

~~~sql
BEGIN;

INSERT INTO catalog_products (
    sku, external_code, product_name, category_code,
    unit_price, stock_qty, vendor_id
)
VALUES (
    'BK-001', 'ERP-A1', 'So tay',
    'BOOK', 100.00, 3, 10
)
ON CONFLICT (sku)
DO UPDATE SET
    unit_price = EXCLUDED.unit_price,
    updated_at = CURRENT_TIMESTAMP
WHERE catalog_products.unit_price
      IS DISTINCT FROM EXCLUDED.unit_price
RETURNING sku, unit_price;

ROLLBACK;
~~~

Giá mới và giá cũ đều 100, nên điều kiện trong `DO UPDATE WHERE` là sai: **không cập nhật** và `RETURNING` không trả hàng cho sản phẩm này.

Vì vậy, một `RETURNING` rỗng trong một UPSERT không tự chứng minh “đã bỏ qua vì trùng SKU theo DO NOTHING”. Nó cũng có thể xuất hiện khi nhánh `DO UPDATE` không thỏa điều kiện WHERE.

### 5.4. Một khóa xung đột được xử lý, không phải mọi uniqueness

PostgreSQL `ON CONFLICT DO UPDATE` cần **conflict target** thích hợp cho unique arbiter; không áp dụng như một cách tự động “bắt bất kỳ unique nào rồi sửa đại một hàng”. Với exclusion constraints và các đặc điểm như constraint deferrable, khả năng chọn arbiter có quy tắc riêng. Không giả định một unique/index/constraint bất kỳ đều dùng được theo cùng cách ở `DO UPDATE`.

Nếu bảng có nhiều unique keys như `sku` và `external_code`, phải **định nghĩa khóa nghiệp vụ nào nhận diện thực thể**. Khi một hàng đề xuất đồng thời trùng hai khóa nhưng các khóa chỉ tới **hai sản phẩm khác nhau**, “upsert bản ghi nào?” không có câu trả lời hợp lệ nếu thiếu quy tắc hợp nhất rõ ràng.

### 5.5. UPSERT không nhất thiết idempotent

Thao tác:

~~~sql
ON CONFLICT (sku)
DO UPDATE SET
    stock_qty = catalog_products.stock_qty + EXCLUDED.stock_qty
~~~

cộng thêm tồn kho mỗi lần retry. Nếu cùng một yêu cầu nhập 3 sản phẩm được gửi hai lần, tồn kho **có thể tăng 6** chứ không phải tăng 3.

Vậy:

- `DO NOTHING` khi trùng SKU có thể phù hợp cho “tạo một lần” nếu nội dung trùng thật sự là cùng yêu cầu.
- `DO UPDATE SET stock_qty = EXCLUDED.stock_qty` là hành vi **thay thế giá trị**.
- `DO UPDATE SET stock_qty = old + incoming` là hành vi **tích lũy**, không an toàn với retry nếu không có khóa idempotency hoặc log sự kiện riêng.

**UPSERT không tự bảo đảm tính idempotent của mọi cập nhật.** Phải xét ý nghĩa của phép gán và định danh của mỗi yêu cầu.

## 6. MySQL: ON DUPLICATE KEY UPDATE khác INSERT IGNORE

### 6.1. ON DUPLICATE KEY UPDATE chủ đích cập nhật khi trùng khóa

MySQL hỗ trợ:

~~~sql
-- MySQL: ví dụ bảng có sku UNIQUE/PRIMARY KEY.
INSERT INTO catalog_products (
    sku, external_code, product_name, category_code,
    unit_price, stock_qty, vendor_id
)
VALUES (
    'BK-001', 'ERP-A1', 'So tay',
    'BOOK', 120.00, 3, 10
)
ON DUPLICATE KEY UPDATE
    unit_price = 120.00,
    stock_qty = stock_qty + 3;
~~~

Câu này thay đổi hàng trùng key theo ngữ nghĩa MySQL. `ON DUPLICATE KEY UPDATE` **không cho chỉ đích arbiter như PostgreSQL `ON CONFLICT (sku)`**.

Nếu một bảng có **nhiều UNIQUE indexes**, một hàng đầu vào có thể va chạm những khóa khác nhau. Đây là nguồn rủi ro: ứng dụng muốn cập nhật theo SKU nhưng câu SQL có thể rơi vào một nhánh duplicate từ unique key khác. MySQL khuyến cáo thận trọng với `ON DUPLICATE KEY UPDATE` trên bảng có nhiều unique indexes.

Ở phiên bản MySQL mới, một số cú pháp tham chiếu giá trị đầu vào dùng row alias thay cho `VALUES(col)` đã bị đánh dấu không nên dùng trong ngữ cảnh nhất định. Khi cần một câu MySQL production có thể chạy qua nhiều phiên bản, hãy kiểm tra cú pháp của phiên bản MySQL đang dùng thay vì chép máy móc từ PostgreSQL `EXCLUDED`.

### 6.2. INSERT IGNORE không có nghĩa “chỉ bỏ qua bản ghi đã tồn tại”

MySQL có dạng:

~~~sql
-- MySQL:
INSERT IGNORE INTO catalog_products (
    sku, external_code, product_name, category_code,
    unit_price, stock_qty, vendor_id
)
VALUES (
    'BK-001', 'ERP-A1', 'So tay',
    'BOOK', 100.00, 10, 10
);
~~~

Khi gặp trùng key, MySQL có thể **bỏ qua hàng xung đột và sinh cảnh báo (warning)** thay vì báo lỗi nghiêm trọng như INSERT thường.

Nhưng `IGNORE` của MySQL rộng hơn một cơ chế xử lý duy nhất cho `sku`. Tùy loại lỗi, phiên bản, SQL mode và storage engine, một số tình huống có thể:

- Bỏ qua một hàng gây lỗi rồi tiếp tục xử lý những hàng còn lại;
- Chuyển một số lỗi dữ liệu thành warning;
- Điều chỉnh/ép giá trị không hợp lệ hoặc dùng giá trị mặc định ngầm định;
- Vẫn phát sinh lỗi nghiêm trọng đối với các tình huống không thể/không được xử lý bằng `IGNORE`.

**Không được tuyên bố `INSERT IGNORE` bỏ qua mọi lỗi.** Nó chỉ thay đổi cách MySQL xử lý **những trường hợp nhất định**, và việc đổi lỗi thành warning có thể khiến dữ liệu ghi vào khác với đầu vào, hoặc một phần hàng không được ghi.

### 6.3. Nguy cơ từ dữ liệu không hợp lệ

Giả sử một lô nhập có:

~~~text
Dòng 1: sku = BK-001, đã tồn tại
Dòng 2: sku = BK-NEW, unit_price không hợp lệ
Dòng 3: sku = PN-NEW, dữ liệu hợp lệ
~~~

Nếu dùng `INSERT IGNORE`, một số hàng có thể bị bỏ qua hoặc giá trị bị điều chỉnh theo cơ chế MySQL, trong khi công cụ import chỉ thấy câu lệnh kết thúc mà không nổi bật lỗi nguồn.

Hệ quả có thể là:

- Tên sản phẩm bị thiếu hoặc bị thay bằng giá trị không mong muốn;
- Một dòng được báo “đã xử lý” dù thực tế không có hàng trong bảng;
- Số bản ghi import không bằng số bản ghi nguồn;
- Dữ liệu từ hệ thống thượng nguồn bị sai nhưng cảnh báo bị bỏ sót.

Vì thế không nên xem `INSERT IGNORE` là cách “làm cho import chạy êm” khi không có cơ chế **thu thập cảnh báo, đối soát số hàng và lưu danh sách hàng bị từ chối**.

### 6.4. Xem warning và trạng thái sau INSERT IGNORE

Trong MySQL, kiểm tra cảnh báo ngay sau câu lệnh liên quan trong cùng phiên:

~~~sql
-- MySQL:
INSERT IGNORE INTO catalog_products (
    sku, external_code, product_name, category_code,
    unit_price, stock_qty, vendor_id
)
VALUES (
    'BK-001', 'ERP-A1', 'So tay',
    'BOOK', 100.00, 10, 10
);

SHOW WARNINGS;
~~~

Cùng với số hàng được ghi và việc kiểm tra bảng đích, warning giúp phát hiện các trường hợp bị bỏ qua/chuyển đổi. Nhưng warning có thể chịu giới hạn lưu trữ hoặc công cụ kết nối, nên quy trình import lớn nên có **logging và staging** riêng, không phụ thuộc hoàn toàn vào giao diện client hiển thị cảnh báo.

### 6.5. MySQL REPLACE không phải “sửa hàng cũ”

MySQL có cú pháp:

~~~sql
REPLACE INTO catalog_products (
    sku, external_code, product_name, category_code,
    unit_price, stock_qty, vendor_id
)
VALUES (
    'BK-001', 'ERP-A1', 'So tay moi',
    'BOOK', 120.00, 1, 10
);
~~~

`REPLACE` có thể thực hiện hành vi **xóa hàng xung đột rồi chèn hàng mới**, không đơn giản là `UPDATE` những cột được cung cấp. Tác động có thể gồm:

- Mất những giá trị ở cột không được nêu trong INSERT, vì hàng cũ bị thay thế;
- Thay đổi ID auto-increment;
- Kích hoạt logic DELETE/INSERT, bao gồm trigger hoặc hành vi quan hệ tham chiếu;
- Gây tác động ngoài ý muốn khi nhiều unique keys cùng xung đột.

Không dùng `REPLACE` để thay `ON DUPLICATE KEY UPDATE` nếu chưa hiểu đầy đủ cơ chế xóa/chèn và khóa ngoại.

## 7. SQLite: UPSERT có mục đích hẹp, OR IGNORE rộng hơn

### 7.1. SQLite UPSERT ON CONFLICT xử lý uniqueness

SQLite hỗ trợ cú pháp kiểu UPSERT trên các phiên bản thích hợp:

~~~sql
-- SQLite, giả định bảng có sku UNIQUE.
INSERT INTO catalog_products (
    sku, product_name, category_code,
    unit_price, stock_qty, vendor_id
)
VALUES (
    'BK-001', 'So tay', 'BOOK',
    100.00, 10, 10
)
ON CONFLICT(sku) DO NOTHING;
~~~

`ON CONFLICT(sku) DO NOTHING` xử lý xung đột uniqueness tại `sku`, không phải bộ lọc mọi lỗi. `DO UPDATE SET ...` cũng có thể dùng cho xung đột phù hợp.

Trong SQLite, cú pháp `ON CONFLICT` có thể xuất hiện trong nhiều ngữ cảnh lịch sử khác nhau. Phải phân biệt **UPSERT ON CONFLICT ở cuối INSERT** với **`ON CONFLICT` được khai báo như một conflict resolution clause trong DDL**.

### 7.2. INSERT OR IGNORE có phạm vi rộng hơn

SQLite hỗ trợ:

~~~sql
INSERT OR IGNORE INTO catalog_products (
    sku, product_name, category_code,
    unit_price, stock_qty, vendor_id
)
VALUES (
    'BK-001', 'So tay', 'BOOK',
    100.00, 10, 10
);
~~~

Trong SQLite, conflict resolution algorithm `IGNORE` áp dụng cho các vi phạm `UNIQUE`, `NOT NULL` và `CHECK` nhất định: hàng vi phạm có thể **bị bỏ qua** thay vì dừng toàn bộ lệnh. Vì vậy nó có phạm vi rộng hơn hẳn UPSERT chỉ dành cho uniqueness.

Đặc biệt: **SQLite `OR IGNORE` không bỏ qua lỗi `FOREIGN KEY`; với lỗi FK, IGNORE hoạt động như ABORT theo quy tắc SQLite.** Không được suy từ từ “IGNORE” rằng mọi constraint đều bị vô hiệu hóa.

Nếu schema có FK, cần bảo đảm SQLite đang bật kiểm tra khóa ngoại theo kết nối, ví dụ:

~~~sql
PRAGMA foreign_keys = ON;
~~~

Thực hành trên SQLite cần kiểm tra cấu hình kết nối thực tế; việc có `REFERENCES` trong schema nhưng không kích hoạt enforcement ở kết nối có thể làm kết quả thử nghiệm FK sai lệch.

### 7.3. So sánh hai dạng qua lỗi thiếu tên

Giả sử `product_name NOT NULL`.

~~~sql
-- SQLite: có thể bỏ qua hàng vi phạm NOT NULL.
INSERT OR IGNORE INTO catalog_products (
    sku, product_name, category_code,
    unit_price, stock_qty, vendor_id
)
VALUES (
    'BK-MISSING', NULL, 'BOOK',
    100.00, 1, 10
);
~~~

Trong khi:

~~~sql
-- SQLite: UPSERT chỉ xử lý uniqueness, không xử lý NOT NULL.
INSERT INTO catalog_products (
    sku, product_name, category_code,
    unit_price, stock_qty, vendor_id
)
VALUES (
    'BK-MISSING', NULL, 'BOOK',
    100.00, 1, 10
)
ON CONFLICT(sku) DO NOTHING;
~~~

vẫn phải báo lỗi `NOT NULL` khi không có uniqueness conflict cần xử lý.

**Điểm cần nhớ:** nhìn thấy chuỗi `IGNORE` không đủ để kết luận câu SQL “an toàn hơn”. Nó có thể khiến ứng dụng **không phát hiện dòng dữ liệu sai**.

### 7.4. SQLite OR REPLACE cũng không phải UPDATE

Tương tự MySQL REPLACE, SQLite `INSERT OR REPLACE` có thể xóa hàng xung đột về uniqueness rồi chèn hàng thay thế; với một số constraint khác có quy tắc khác. Nó **không** đồng nghĩa với “giữ nguyên mọi cột cũ, chỉ sửa cột tôi gửi”.

Tác động tới khóa chính, FK, trigger và các cột bị bỏ qua có thể rất quan trọng. Khi muốn cập nhật có chọn lọc, ưu tiên UPSERT với `DO UPDATE SET` định nghĩa rõ những cột cần thay đổi.

## 8. MERGE: chọn nhánh hành động, không nuốt lỗi

### 8.1. MERGE diễn đạt quan hệ giữa nguồn và đích

Ở các DBMS hỗ trợ, `MERGE` cho phép so khớp dữ liệu nguồn với bảng đích:

~~~text
Hàng nguồn
   |
   +-- MATCHED (đã có hàng đích tương ứng)
   |       → UPDATE hoặc hành động được hỗ trợ
   |
   +-- NOT MATCHED (chưa có hàng đích)
           → INSERT hoặc hành động được hỗ trợ
~~~

Điểm khác với `ON CONFLICT`: `MERGE` chọn nhánh dựa vào **điều kiện khớp nguồn/đích** được khai báo trong câu lệnh. Nó không có nghĩa cơ sở dữ liệu sẽ bỏ qua mọi lỗi phát sinh khi thực hiện nhánh INSERT/UPDATE/DELETE.

### 8.2. PostgreSQL MERGE minh họa (phiên bản hỗ trợ)

PostgreSQL hỗ trợ `MERGE` từ phiên bản 15. Ví dụ:

~~~sql
-- PostgreSQL 15+, trong một transaction thực hành.
MERGE INTO catalog_products AS t
USING (
    VALUES
        ('BK-001', 'ERP-A1', 'So tay',  'BOOK', 110.00, 10, 10),
        ('TL-004', 'ERP-D4', 'Thuoc',   'TOOL',  15.00,  5, 20)
) AS s (
    sku, external_code, product_name, category_code,
    unit_price, stock_qty, vendor_id
)
ON t.sku = s.sku
WHEN MATCHED THEN
    UPDATE SET
        unit_price = s.unit_price,
        stock_qty = s.stock_qty,
        updated_at = CURRENT_TIMESTAMP
WHEN NOT MATCHED THEN
    INSERT (
        sku, external_code, product_name, category_code,
        unit_price, stock_qty, vendor_id
    )
    VALUES (
        s.sku, s.external_code, s.product_name, s.category_code,
        s.unit_price, s.stock_qty, s.vendor_id
    );
~~~

Ý nghĩa: `BK-001` khớp SKU nên được cập nhật; `TL-004` chưa có nên được thêm. Mỗi nhánh vẫn phải tuân theo `NOT NULL`, `CHECK`, `UNIQUE`, `FK` và các ràng buộc khác.

Ví dụ cần chạy trên đúng phiên bản PostgreSQL hỗ trợ `MERGE` và trong môi trường có dữ liệu mẫu từ đầu bài; một số phiên bản không có tất cả các mệnh đề mở rộng như `RETURNING` cho MERGE.

### 8.3. MERGE có thể thất bại vì dữ liệu nguồn trùng

Giả sử dữ liệu nguồn có **hai hàng cùng SKU `BK-001`**, và cả hai cùng khớp một hàng đích. Một `MERGE` có thể không được phép cập nhật cùng hàng đích hai lần và báo lỗi cardinality/duplicate update theo DBMS.

Vì thế nguồn của `MERGE` cần được kiểm tra:

~~~sql
-- Trên bảng staging giả định:
SELECT sku, COUNT(*) AS row_count
FROM staging_products
GROUP BY sku
HAVING COUNT(*) > 1;
~~~

Trong đoạn trên `staging_products` là **bảng giả định** dùng để minh họa phát hiện khóa trùng. Muốn chạy phải tạo bảng staging theo hệ thống thực tế.

Nếu nghiệp vụ cần chọn một bản ghi nguồn cuối cùng theo `received_at` hoặc độ ưu tiên, phải **chọn nguồn đơn trị có quy tắc**, không chỉ đặt `DISTINCT` trên toàn bộ hàng rồi hy vọng hết trùng SKU.

### 8.4. MERGE không thay thế UNIQUE constraint

Giả sử hai transaction đồng thời kiểm tra “SKU chưa tồn tại” và cùng chọn nhánh INSERT của `MERGE`. Tùy DBMS, isolation, locking và kế hoạch, một transaction có thể gặp xung đột uniqueness hoặc lỗi đồng thời khác.

`MERGE` không phải bảo đảm chung rằng “sẽ không bao giờ xảy ra duplicate key error”. Cần:

- Ràng buộc `UNIQUE`/`PRIMARY KEY` ở database;
- Transaction và locking phù hợp;
- Retry có kiểm soát với lỗi đồng thời **có thể retry**;
- Định nghĩa một khóa tự nhiên hoặc idempotency key rõ ràng.

Ví dụ PostgreSQL `INSERT ... ON CONFLICT` và `MERGE` không hoàn toàn tương đương về bảo đảm đồng thời. Khi mục tiêu là UPSERT trên một khóa uniqueness và PostgreSQL hỗ trợ `ON CONFLICT`, thường nên ưu tiên nó để có hành vi giải quyết xung đột khóa đã khai báo rõ hơn, thay vì mặc định mọi câu `MERGE` là UPSERT chống race tương đương.

### 8.5. SQL Server MERGE cũng không phải ignore

SQL Server có cú pháp `MERGE` với `WHEN MATCHED` và `WHEN NOT MATCHED`. Nó cũng phải đáp ứng constraint. Cần xác định nguồn có một hàng ứng với một hàng đích, kiểm soát concurrency, trigger và hành vi của câu lệnh theo phiên bản.

Không lấy `MERGE` làm “thuốc chữa” mọi lỗi nhập dữ liệu. Với các thao tác đơn giản, đôi khi một `UPDATE` và một `INSERT` có transaction, locking/unique key rõ ràng sẽ dễ kiểm chứng và vận hành hơn; lựa chọn phụ thuộc DBMS và yêu cầu.

## 9. Lý do TRY/CATCH mọi lỗi không phải chiến lược UPSERT

Một mẫu pseudo-code nguy hiểm:

~~~java
try {
    insertProduct(product);
} catch (Exception ignored) {
    // Bỏ qua mọi lỗi; coi như sản phẩm đã tồn tại.
}
~~~

Đoạn này có thể che:

- Sản phẩm đã tồn tại thật;
- Giá âm hoặc sai định dạng;
- Thiếu nhà cung cấp;
- Database không kết nối được;
- Câu SQL sai sau khi nâng cấp schema;
- Không có quyền ghi;
- Deadlock hoặc timeout cần retry.

Sau đó tầng API trả **thành công** trong khi không có hàng nào được ghi hoặc hàng cũ hoàn toàn không được cập nhật. Đây là lỗi vận hành và toàn vẹn dữ liệu nghiêm trọng.

### 9.1. Bắt đúng loại lỗi vẫn cần đúng khóa nghiệp vụ

Nếu chọn xử lý exception ở ứng dụng, ví dụ PostgreSQL dùng SQLSTATE:

| SQLSTATE | Nhóm lỗi phổ biến | Ý nghĩa |
| --- | --- | --- |
| `23505` | `unique_violation` | Vi phạm ràng buộc UNIQUE/PRIMARY KEY |
| `23502` | `not_null_violation` | Vi phạm NOT NULL |
| `23503` | `foreign_key_violation` | Vi phạm FOREIGN KEY |
| `23514` | `check_violation` | Vi phạm CHECK |
| `40001` | `serialization_failure` | Có thể cần retry toàn transaction theo chính sách |
| `40P01` | `deadlock_detected` | Có thể cần retry toàn transaction theo chính sách |

Trong PostgreSQL, ngay cả khi SQLSTATE là `23505`, điều đó **chưa chứng minh** lỗi đến từ **`sku`**. Có thể nó đến từ `external_code` hoặc khóa unique khác. Nếu nghiệp vụ chỉ cho phép bỏ trùng SKU, xử lý exception cần xét **tên constraint/index phù hợp** và nội dung yêu cầu, thay vì coi mọi `23505` là “đã có sản phẩm”.

Trong nhiều tình huống, `INSERT ... ON CONFLICT (sku) DO NOTHING` diễn đạt chủ đích tốt hơn việc thử INSERT rồi bắt lỗi uniqueness tổng quát.

### 9.2. PostgreSQL transaction bị lỗi cần rollback đúng cách

Trong PostgreSQL, nếu một câu INSERT lỗi trong transaction, những câu tiếp theo trong transaction đó thường không thể chạy bình thường cho tới khi rollback hoặc dùng savepoint phù hợp.

Mẫu ý tưởng:

~~~sql
BEGIN;

SAVEPOINT before_insert;

-- Thử một INSERT có thể lỗi.

-- Nếu lỗi và client/driver xác nhận cần bỏ qua đúng lỗi được phép:
ROLLBACK TO SAVEPOINT before_insert;

-- Sau đó tiếp tục các thao tác khác khi transaction hợp lệ.
COMMIT;
~~~

`ROLLBACK TO SAVEPOINT` chỉ minh họa **nhánh xử lý sau khi đã bắt và phân loại lỗi**; không chạy nó một cách máy móc sau một INSERT thành công rồi gọi là UPSERT.

Nếu có thể mô tả tình huống bằng `ON CONFLICT`, thường tránh được việc cố tình kích hoạt lỗi và xử lý transaction thủ công. Savepoint vẫn có ích cho các luồng import yêu cầu ghi lỗi từng hàng với phạm vi khôi phục cụ thể.

### 9.3. Retry phải có giới hạn và tiêu chí

Một lỗi serialization hoặc deadlock có thể cần retry **toàn transaction** nếu thao tác đủ an toàn để thực hiện lại. Nhưng:

- Vi phạm `CHECK` do giá âm sẽ không được sửa bằng việc retry y nguyên.
- Vi phạm `FK` do vendor ID sai thường cần sửa dữ liệu hoặc trình tự ghi, không chỉ lặp INSERT.
- Xung đột `UNIQUE` có thể là kết quả hợp lệ của một lệnh “tạo nếu chưa có”, hoặc là dấu hiệu một khách hàng gửi dữ liệu mâu thuẫn.
- Lỗi timeout/mất kết nối có thể khiến trạng thái commit **chưa rõ** với client; phải dùng idempotency key và truy vấn trạng thái đáng tin cậy trước khi quyết định phát lệnh lại.

Không lập trình một vòng lặp “catch mọi exception rồi retry vô hạn”. Lựa chọn retry là chính sách dựa trên **loại lỗi và ngữ nghĩa giao dịch**.

## 10. “Bỏ qua xung đột” và “thành công” không phải một trạng thái duy nhất

### 10.1. Ba kết quả cần phân biệt

Một yêu cầu tạo dữ liệu có thể dẫn đến:

1. **INSERTED:** hàng mới được tạo.
2. **SKIPPED_EXISTING:** dữ liệu không thay đổi vì khóa đã tồn tại và chính sách cho phép bỏ qua.
3. **REJECTED/FAILED:** dữ liệu sai hoặc thao tác thất bại; cần báo nguyên nhân.

Khi có UPSERT `DO UPDATE`, cần thêm:

4. **UPDATED:** hàng có sẵn được cập nhật thành công.
5. **NO_CHANGE:** nhánh cập nhật được xem xét nhưng điều kiện WHERE không thỏa, hoặc không có thay đổi nghiệp vụ cần ghi.

Các trạng thái này hữu ích cho audit, API và quy trình import. **Tránh gom tất cả vào “thành công” mà không có số hàng và nguyên nhân.**

### 10.2. PostgreSQL RETURNING giúp quan sát nhưng cần diễn giải

~~~sql
INSERT INTO catalog_products (
    sku, external_code, product_name, category_code,
    unit_price, stock_qty, vendor_id
)
VALUES (
    'BK-001', 'ERP-A1', 'So tay',
    'BOOK', 100.00, 10, 10
)
ON CONFLICT (sku) DO NOTHING
RETURNING product_id, sku;
~~~

Nếu `BK-001` đã có, kết quả `RETURNING` rỗng: không có hàng **được chèn**. Đừng diễn giải là “không có lỗi nào xảy ra trong toàn bộ pipeline” nếu chưa kiểm tra kết quả các bước khác.

Cũng không nên dựa vào việc số ID tự sinh phải liên tục: PostgreSQL sequence/identity có thể tiêu thụ giá trị ngay cả khi thử chèn gặp conflict và đi nhánh `DO NOTHING`, dẫn tới khoảng trống hợp lệ trong dãy ID.

### 10.3. Với multi-row INSERT, một câu lệnh không nói hết mọi dòng

Ví dụ PostgreSQL:

~~~sql
BEGIN;

INSERT INTO catalog_products (
    sku, external_code, product_name, category_code,
    unit_price, stock_qty, vendor_id
)
VALUES
    ('BK-001', 'ERP-A1',  'So tay',      'BOOK', 100, 10, 10),
    ('TL-NEW', 'ERP-NEW', 'Thuoc 20cm',  'TOOL',  15,  5, 20)
ON CONFLICT (sku) DO NOTHING
RETURNING sku;

ROLLBACK;
~~~

Với dữ liệu ban đầu, `BK-001` bị bỏ qua còn `TL-NEW` được chèn và trả về. Lệnh trả **một hàng** trong `RETURNING` dù đầu vào có hai hàng.

Điều cần kiểm tra:

~~~text
Input rows:        2
Inserted rows:     1
Skipped by policy: 1
Rejected rows:     0  (với đúng dữ liệu ví dụ)
~~~

Nhưng nếu một dòng khác bị lỗi `CHECK`/`FK`, trong PostgreSQL câu multi-row INSERT thường thất bại như một statement, chứ không tự “chèn được những dòng hợp lệ, bỏ dòng sai” chỉ vì có `DO NOTHING`.

**Không lấy `ON CONFLICT DO NOTHING` làm cơ chế import “best effort” cho mọi lỗi.**

### 10.4. Có cần trả hàng đã tồn tại?

`ON CONFLICT DO NOTHING RETURNING` không trả hàng đã bị bỏ qua. Nếu API cần trả ID của bản ghi đã tồn tại, có thể:

- Truy vấn lại theo SKU sau INSERT, với transaction/isolation phù hợp;
- Dùng cấu trúc riêng và kiểm soát concurrent insert;
- Hoặc áp dụng `DO UPDATE` thật sự nếu nghiệp vụ cần cập nhật.

Đừng thực hiện một `DO UPDATE SET x = x` chỉ để lấy `RETURNING` mà không xét chi phí ghi, trigger, lock và side effects. Một “UPDATE không đổi giá trị” vẫn có thể có tác động vận hành hoặc được tính là một lần cập nhật.

## 11. Idempotency: trùng request khác trùng dữ liệu

### 11.1. Hai request cùng SKU chưa chắc giống nhau

Giả sử hai yêu cầu:

~~~json
{
  "sku": "BK-001",
  "productName": "So tay",
  "unitPrice": 100
}
~~~

và:

~~~json
{
  "sku": "BK-001",
  "productName": "So tay",
  "unitPrice": 9000
}
~~~

Chúng trùng khóa SKU nhưng **khác nội dung quan trọng**. Nếu API dùng `ON CONFLICT (sku) DO NOTHING`, yêu cầu thứ hai có thể bị bỏ qua mà client tưởng giá 9000 đã được ghi.

Vì vậy có ít nhất hai chính sách:

- **Create if absent:** nếu SKU đã tồn tại, trả kết quả “đã tồn tại” mà **không khẳng định payload đã được áp dụng**.
- **Idempotent create request:** nếu cùng idempotency key được gửi lại với **cùng payload**, trả kết quả cũ; nếu cùng key nhưng payload khác, báo xung đột yêu cầu thay vì âm thầm bỏ.

### 11.2. Thiết kế khóa idempotency theo từng nghiệp vụ

Một hệ thống thanh toán hoặc nhập tồn kho có thể lưu một bảng sự kiện:

~~~sql
CREATE TABLE inventory_events (
    event_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    request_key VARCHAR(100) NOT NULL UNIQUE,
    sku VARCHAR(30) NOT NULL,
    quantity_delta INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Ví dụ ghi sự kiện:

~~~sql
INSERT INTO inventory_events (request_key, sku, quantity_delta)
VALUES ('import-2026-11-14-line-42', 'BK-001', 3)
ON CONFLICT (request_key) DO NOTHING
RETURNING event_id, request_key;
~~~

Cơ chế này cho phép nhận diện **yêu cầu bị gửi lại**, thay vì coi mọi lần tăng tồn cho cùng SKU đều trùng. Tuy vậy để bảo đảm một yêu cầu chỉ tác động tồn kho một lần, việc **ghi sự kiện và cập nhật tồn** cần được tổ chức cùng transaction hoặc quy trình đảm bảo exactly-once-effect theo kiến trúc.

Ngoài ra, phải xác minh request key cũ có **cùng nội dung sự kiện**; nếu cùng key nhưng `quantity_delta` khác, không nên im lặng cho qua.

### 11.3. Trùng khóa không tự chứng minh dữ liệu giống nhau

Khi `sku` đã tồn tại, có thể cần kiểm tra thêm:

- Tên sản phẩm có tương thích không?
- Nhà cung cấp có đúng không?
- Mã `external_code` có trỏ đến cùng thực thể không?
- Yêu cầu này là retry của lần trước hay một bản cập nhật độc lập?
- Có chính sách version/updated_at để chống ghi đè không?

Nếu không có quy tắc rõ, “trùng khóa thì bỏ” chỉ là một **một quyết định kỹ thuật**, không tự là chính sách nghiệp vụ đúng.

## 12. Import dữ liệu: dùng staging thay vì IGNORE mọi lỗi

### 12.1. Yêu cầu của một pipeline đáng tin cậy

Giả sử một tệp có 10.000 sản phẩm. Kết quả mong muốn không chỉ là “câu SQL chạy xong”, mà cần biết:

- Bao nhiêu dòng **đầu vào**?
- Bao nhiêu dòng **hợp lệ**?
- Bao nhiêu dòng **đã thêm**?
- Bao nhiêu dòng **đã cập nhật**?
- Bao nhiêu dòng **trùng theo khóa nghiệp vụ**?
- Bao nhiêu dòng **bị từ chối**? Vì lỗi nào?
- Dòng nào không tìm được nhà cung cấp?
- Dòng nào có giá âm hoặc thiếu SKU?
- Nếu chạy lại lô, kết quả có bị thay đổi không?

Một pipeline chỉ dùng `INSERT IGNORE` rồi đọc số hàng chèn thường không đủ để giải thích toàn bộ.

### 12.2. Ví dụ schema staging

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE staging_product_import (
    batch_id VARCHAR(50) NOT NULL,
    source_line_no INTEGER NOT NULL,
    sku_raw TEXT,
    external_code_raw TEXT,
    product_name_raw TEXT,
    category_raw TEXT,
    price_raw TEXT,
    qty_raw TEXT,
    vendor_raw TEXT,
    PRIMARY KEY (batch_id, source_line_no)
);
~~~

Cố ý lưu trường chưa kiểm tra dưới dạng `TEXT` để có thể **giữ lại cả dòng sai** cho bước kiểm định, thay vì nạp thẳng vào bảng production có các ràng buộc.

Một quy trình thường có dạng:

~~~text
File nguồn
    |
    v
Staging: giữ batch_id, số dòng và dữ liệu thô
    |
    v
Kiểm tra định dạng, bắt buộc, miền giá trị, mapping vendor
    |
    +-- Sai → error_rows: batch_id, line_no, reason, raw values
    |
    +-- Đúng → normalized_rows với khóa nghiệp vụ rõ
                 |
                 v
           Phân loại: mới / đã tồn tại / xung đột payload
                 |
                 v
           INSERT / UPSERT có target rõ và transaction
                 |
                 v
           Đối soát counts + audit + kết quả batch
~~~

Mỗi bước có thể dùng CTE, bảng tạm hoặc công cụ ETL phù hợp. `staging_product_import` trong bài chỉ là cấu trúc gợi ý, không phải quy trình import hoàn chỉnh.

### 12.3. Kiểm tra trùng trong chính lô import

~~~sql
SELECT
    batch_id,
    sku_raw,
    COUNT(*) AS occurrences
FROM staging_product_import
WHERE sku_raw IS NOT NULL
GROUP BY batch_id, sku_raw
HAVING COUNT(*) > 1;
~~~

Một lô có hai dòng cùng SKU nhưng giá khác có thể cần **báo lỗi lô** hoặc chọn dòng thắng theo timestamp/số dòng được quy định. Không để `ON CONFLICT DO NOTHING` hoặc `MERGE` tự quyết định ngẫu nhiên.

### 12.4. Đừng nghĩ staging có thể bỏ ràng buộc bảng đích

Staging giúp lưu và báo lỗi dữ liệu thô, nhưng khi chuyển sang `catalog_products` vẫn phải tuân theo `NOT NULL`, `CHECK`, `UNIQUE`, FK và các quy tắc giao dịch. Đó là lợi thế của mô hình: **dữ liệu sai được tách ra và giải thích, không bí mật lọt qua constraint**.

### 12.5. Báo cáo nhập liệu cần chống đếm nhầm

Trong hệ có retry, số lần **thử xử lý** không bằng số **sản phẩm mới**. Một batch có thể:

- Xử lý 100 dòng nguồn;
- Thêm 80 sản phẩm;
- Bỏ qua 15 SKU đã tồn tại;
- Từ chối 5 dòng sai dữ liệu.

Những số này phải đối soát được với log của từng dòng. Nếu cả 15 dòng trùng bị log là “inserted” hoặc 5 dòng sai bị im lặng bỏ qua, báo cáo sẽ sai.

## 13. Transaction, tính nguyên tử và lỗi từng hàng

### 13.1. Một lệnh đa hàng không mặc định là best effort

Trong PostgreSQL, một câu:

~~~sql
INSERT INTO catalog_products (
    sku, external_code, product_name, category_code,
    unit_price, stock_qty, vendor_id
)
VALUES
    ('TL-GOOD', 'ERP-GOOD', 'Thuoc', 'TOOL', 15, 3, 20),
    ('TL-BAD',  'ERP-BAD',  'Thuoc loi', 'TOOL', -5, 3, 20)
ON CONFLICT (sku) DO NOTHING;
~~~

không được bảo đảm sẽ “chèn dòng hợp lệ, âm thầm bỏ dòng giá âm”. `CHECK (unit_price >= 0)` có thể khiến **toàn bộ câu INSERT thất bại** theo atomicity của statement PostgreSQL.

Nếu muốn xử lý lỗi từng dòng, cần một quy trình **phân loại lỗi** và chia phạm vi thực thi; không dùng `ON CONFLICT` như thay thế cho validation.

### 13.2. Savepoint cho các bước có thể thất bại riêng

Trong một số quy trình import từng dòng, có thể:

1. Mở transaction.
2. Tạo savepoint trước khi chèn một dòng.
3. Chèn dòng.
4. Nếu lỗi, phân loại SQLSTATE, rollback về savepoint và ghi lỗi ra bảng audit phù hợp.
5. Nếu thành công, tiếp tục.
6. Commit cả lô theo quy tắc xác định.

Đây là mô hình cần được code hóa cẩn thận trong ứng dụng/driver; không tự chạy mỗi lệnh sau khi transaction đã vào trạng thái lỗi. Với hàng nghìn/hàng triệu dòng, savepoint từng dòng có chi phí và cần cân nhắc batch validation/staging.

### 13.3. “IGNORE” có thể thay đổi khả năng phát hiện lỗi

Với một số cú pháp `IGNORE`, database có thể trả **warning** thay vì exception. Nếu ứng dụng chỉ catch exception, nó có thể **không nhận biết vấn đề** vì không có exception nào được ném ra.

Do đó:

- Kiểm tra warning/diagnostic nếu dùng cơ chế có thể downgrade lỗi.
- Ghi số hàng được chấp nhận và số hàng bị bỏ.
- Coi giá trị bị ép/chuyển đổi là một sự kiện cần theo dõi.
- Phân loại lỗi và không bỏ qua mất kết nối, quyền, constraint hoặc lỗi schema.

## 14. Bảo đảm đồng thời: uniqueness constraint là nền tảng

### 14.1. SELECT trước rồi INSERT không chống race một mình

Mẫu dễ gặp:

~~~text
1. SELECT xem sku='BK-NEW' đã tồn tại chưa.
2. Nếu chưa có, INSERT sku='BK-NEW'.
~~~

Hai transaction có thể đồng thời không thấy SKU rồi cùng cố INSERT. Nếu bảng không có `UNIQUE(sku)`, có thể tạo bản ghi trùng; nếu có `UNIQUE`, một transaction sẽ bị chặn hoặc nhận lỗi/đi vào nhánh conflict theo cơ chế engine.

**Không dùng kiểm tra tồn tại ở ứng dụng để thay thế UNIQUE constraint trong DBMS.**

### 14.2. PostgreSQL ON CONFLICT gắn xử lý với ràng buộc

~~~sql
INSERT INTO catalog_products (
    sku, product_name, category_code,
    unit_price, stock_qty, vendor_id
)
VALUES (
    'BK-RACE', 'So nhap cung luc', 'BOOK',
    100, 2, 10
)
ON CONFLICT (sku) DO NOTHING;
~~~

Khi hai session cùng chèn `BK-RACE`, ràng buộc unique và cơ chế `ON CONFLICT` xử lý xung đột ở mức database theo ngữ nghĩa PostgreSQL, không dựa chỉ vào một SELECT kiểm tra trước đó.

Nhưng khi phát sinh lỗi khác như `CHECK`/`FK`, xung đột đồng thời không cho phép bỏ qua lỗi đó. `ON CONFLICT` cũng không thay đổi bản chất transaction của toàn bộ quy trình nghiệp vụ liên quan.

### 14.3. MERGE và SELECT-then-INSERT cần đánh giá concurrency riêng

Không mặc định MERGE của mọi DBMS sẽ chống race như PostgreSQL `ON CONFLICT`. Cần kiểm tra isolation/locking và unique constraint. Với transaction có thể retry, thiết kế **idempotency key** để tránh một lần retry cộng tiền/tồn thêm lần thứ hai.

### 14.4. Không dựa vào identity liên tục để suy kết quả

Một lần thử INSERT bị bỏ qua do unique conflict vẫn có thể tiêu thụ giá trị sequence/identity, tùy DBMS. Vì vậy các số ID như 101, 103, 108 không chứng minh đã mất bản ghi hay mất request. Để kiểm toán, dùng **bảng sự kiện, request ID và trạng thái thực thi**, không dựa vào “khoảng trống” của ID tự sinh.

## 15. Cách chọn cơ chế theo yêu cầu

| Yêu cầu | Kỹ thuật thường phù hợp | Cần lưu ý |
| --- | --- | --- |
| Tạo sản phẩm nếu SKU chưa có; nếu có thì không sửa | PostgreSQL `ON CONFLICT (sku) DO NOTHING` hoặc tương đương SQLite UPSERT | Khi trùng, phải báo đã tồn tại chứ không nói đã chèn |
| Nếu SKU có rồi thì cập nhật giá | `ON CONFLICT (sku) DO UPDATE` hoặc MySQL `ON DUPLICATE KEY UPDATE` theo dialect | Check constraint vẫn áp dụng; MySQL nhiều UNIQUE có rủi ro |
| Chèn nhiều hàng và kiểm định dữ liệu sai | Staging + validation + báo cáo lỗi | Không dùng IGNORE làm validation |
| Retry tạo cùng một yêu cầu | Idempotency key + UNIQUE + kiểm tra payload | Trùng SKU không nhất thiết là cùng request |
| Chuyển nguồn thành INSERT/UPDATE theo match | `MERGE` ở hệ hỗ trợ | Source phải rõ và unique; không che lỗi |
| Nhập CSV muốn biết hàng nào không hợp lệ | Staging/raw data + error rows | Không nuốt NULL/FK/CHECK |
| Chỉ bỏ qua lỗi trùng đúng một unique constraint | Conflict target rõ khi dialect cho phép | Bắt lỗi unique tổng quát không đủ |
| Cần xử lý lỗi riêng từng dòng | Validation hoặc savepoint/điều phối theo transaction | Phải giữ trạng thái lỗi/audit chính xác |
| Không rõ lệnh trước đã commit hay chưa | Tra cứu theo request key và trả lại kết quả cũ | Retry vô điều kiện có thể nhân tác động |

### 15.1. Khi nào DO NOTHING là lựa chọn tốt?

`DO NOTHING` hợp lý khi:

- Dữ liệu được định danh bằng khóa unique rõ ràng;
- Tồn tại đã là trạng thái chấp nhận được theo nghiệp vụ;
- Bản ghi đề xuất không cần cập nhật hàng cũ;
- Ứng dụng phân biệt được “đã tạo” và “đã có”;
- Những lỗi khác phải **vẫn được báo ra**.

### 15.2. Khi nào DO UPDATE cần thận trọng?

`DO UPDATE` hợp lý khi muốn đồng bộ trường dữ liệu theo quy tắc rõ. Nhưng cần trả lời:

- Cột nào được phép ghi đè?
- Giá trị đầu vào đã được validate chưa?
- Có so version/timestamp để chống ghi đè dữ liệu mới bằng dữ liệu cũ không?
- Cập nhật là phép gán thay thế hay cộng dồn?
- Có trigger, audit, thay đổi `updated_at` không?
- Khi trùng nhiều khóa unique, có chọn được đúng thực thể không?

### 15.3. Khi nào nên từ chối thay vì bỏ qua?

Nếu hai hệ thống gửi cùng `sku` nhưng thông tin nhà cung cấp, đơn giá hoặc mã ERP mâu thuẫn, một câu `DO NOTHING` có thể giấu đi vấn đề đồng bộ. Khi không có quy tắc hợp nhất rõ, **trả conflict và yêu cầu xử lý** thường an toàn hơn việc bỏ qua hoặc ghi đè.

## 16. Những lỗi hiểu nhầm phổ biến

| Hiểu nhầm | Hậu quả | Cách hiểu đúng |
| --- | --- | --- |
| “`ON CONFLICT DO NOTHING` bỏ qua mọi lỗi.” | Che mất phân biệt unique với CHECK/FK/NOT NULL | PostgreSQL `ON CONFLICT` xử lý conflict arbiter phù hợp, không phải all errors |
| “Bỏ conflict target luôn an toàn hơn.” | Có thể bỏ qua unique khác như external_code | Chỉ rõ `ON CONFLICT (sku)` nếu nghiệp vụ chỉ bỏ SKU |
| “Đã trùng SKU thì payload chắc giống bản ghi cũ.” | Mất cập nhật hoặc che mâu thuẫn | So sánh nội dung/định nghĩa idempotency |
| “UPSERT luôn idempotent.” | `stock_qty = old + incoming` bị cộng lặp khi retry | Khóa sự kiện/request riêng |
| “`DO UPDATE` tránh mọi lỗi constraint.” | UPDATE vẫn vi phạm CHECK/UNIQUE/FK được | Giữ constraint và validate |
| “MySQL INSERT IGNORE chỉ bỏ qua duplicate key.” | Có thể downgrade/điều chỉnh lỗi khác tùy loại | Theo dõi warning, kiểm tra kết quả |
| “MySQL INSERT IGNORE bảo đảm không bao giờ lỗi.” | Vẫn có lỗi nghiêm trọng | Không coi IGNORE là catch-all |
| “SQLite OR IGNORE và UPSERT DO NOTHING giống nhau.” | OR IGNORE rộng hơn với NOT NULL/CHECK | Chọn conflict target cho uniqueness |
| “SQLite OR IGNORE cũng bỏ qua FK.” | FK vẫn có thể ABORT | Bật enforcement và xử lý FK đúng |
| “REPLACE chỉ sửa những cột mới.” | Có thể xóa hàng cũ rồi chèn, ảnh hưởng ID/FK | Dùng DO UPDATE nếu muốn cập nhật có chọn |
| “MERGE không bao giờ bị duplicate key.” | Race hoặc nguồn trùng vẫn lỗi | UNIQUE + transaction + quy tắc nguồn |
| “Bắt `23505` là chắc trùng SKU.” | Có thể trùng external_code | Kiểm tra constraint cụ thể |
| “RETURNING rỗng = thành công đã lưu.” | Có thể không hề có hàng được chèn/sửa | Phân biệt inserted/skipped/no_change |
| “Một multi-row DO NOTHING sẽ bỏ mọi hàng sai.” | Statement có thể lỗi vì CHECK/FK | Validate/staging |
| “SELECT chưa tồn tại rồi INSERT là an toàn đồng thời.” | Race giữa hai session | UNIQUE + conflict handling/locking |
| “ID không liên tục chứng minh mất dữ liệu.” | Kết luận sai với sequence/identity | Audit dựa trên request/event |
| “Retry mọi lỗi là cách sửa.” | Có thể lặp vô hạn hoặc nhân tác động | Phân loại lỗi, retry có giới hạn và idempotency |

## 17. Bài tập thực hành có đáp án

Các bài 1–9 dùng schema PostgreSQL `vendors` và `catalog_products` ở mục 3. Dữ liệu gốc có `BK-001`, `PN-002` và `HD-003`. Nếu thực hành nhiều lệnh INSERT, nên dùng transaction/ROLLBACK hoặc tạo dữ liệu mẫu mới. Những câu minh họa lỗi chỉ nên chạy riêng trên môi trường thử.

### Bài 1 — Chỉ bỏ trùng SKU

Viết SQL thêm một sản phẩm nhưng **chỉ bỏ qua nếu `sku` đã tồn tại**; những lỗi khác phải báo ra.

**Đáp án:**

~~~sql
INSERT INTO catalog_products (
    sku, external_code, product_name, category_code,
    unit_price, stock_qty, vendor_id
)
VALUES (
    'BK-001', 'ERP-A1', 'So tay',
    'BOOK', 100.00, 10, 10
)
ON CONFLICT (sku) DO NOTHING;
~~~

Không bỏ conflict target nếu nghiệp vụ chỉ xử lý SKU.

### Bài 2 — Trùng external_code khác trùng SKU

Với `sku='BK-NEW'` chưa có nhưng `external_code='ERP-A1'` đã được dùng, câu `ON CONFLICT (sku) DO NOTHING` sẽ làm gì?

**Đáp án:** phát sinh **lỗi trùng khóa external_code**. Conflict target `sku` không áp dụng cho unique constraint `external_code`.

Nếu bỏ target và dùng `ON CONFLICT DO NOTHING`, hàng đó có thể bị bỏ qua vì external_code. Đó là lý do phải định nghĩa khóa mà nghiệp vụ cho phép bỏ xung đột.

### Bài 3 — DO NOTHING và CHECK

Câu có `unit_price = -2`, SKU mới, `ON CONFLICT (sku) DO NOTHING`. Nó có chèn hàng không?

**Đáp án:** không. Trên PostgreSQL, `CHECK (unit_price >= 0)` bị vi phạm nên câu lệnh **báo lỗi**, không đơn giản “bỏ qua xung đột”. Một giá âm không phải duplicate key.

### Bài 4 — DO NOTHING và FK

Câu chèn có SKU mới, giá hợp lệ nhưng `vendor_id=999` không tồn tại. `DO NOTHING` có che lỗi được không?

**Đáp án:** không. `FOREIGN KEY` vẫn áp dụng; phải sửa vendor mapping hoặc tạo vendor theo quy trình hợp lệ.

### Bài 5 — UPSERT cộng tồn có idempotent không?

Ban đầu sản phẩm `BK-001` tồn 10. Chạy hai lần một UPSERT với:

~~~sql
ON CONFLICT (sku)
DO UPDATE SET
    stock_qty = catalog_products.stock_qty
                + EXCLUDED.stock_qty
~~~

mỗi lần gửi `stock_qty=3`. Tồn sau hai lần là bao nhiêu?

**Đáp án:** nếu cả hai lần thành công, tồn sẽ là **16** (10 + 3 + 3), không phải 13. Đây là một phép cộng dồn, không idempotent nếu request bị retry. Cần định danh sự kiện nhập hàng riêng hoặc thiết kế không nhân đôi tác động.

### Bài 6 — MySQL INSERT IGNORE có nên dùng để nhập mọi CSV?

Một người đề nghị dùng `INSERT IGNORE` để “không còn lỗi nào trong quá trình import”, không đọc warning. Đánh giá.

**Đáp án:** không nên. `INSERT IGNORE` có thể đổi một số lỗi thành warning, bỏ qua một số hàng hoặc điều chỉnh dữ liệu theo phiên bản/mode. Nó **không giải quyết mọi lỗi** và có thể che dữ liệu sai. Cần staging, validation, warning và đối soát số hàng.

### Bài 7 — SQLite OR IGNORE so với UPSERT

Nếu `product_name NOT NULL` mà giá trị `NULL`, hãy so sánh SQLite:

~~~sql
INSERT OR IGNORE INTO catalog_products (...)
VALUES (...);
~~~

và:

~~~sql
INSERT INTO catalog_products (...)
VALUES (...)
ON CONFLICT(sku) DO NOTHING;
~~~

**Đáp án:** `OR IGNORE` có thể bỏ qua hàng vi phạm NOT NULL theo SQLite; UPSERT `ON CONFLICT(sku) DO NOTHING` không dành cho NOT NULL và phải báo lỗi. Dấu `...` trong đề chỉ là placeholder, không phải SQL chạy trực tiếp.

### Bài 8 — RETURNING khi DO NOTHING

Trên PostgreSQL, chèn `BK-001` đã có với `ON CONFLICT (sku) DO NOTHING RETURNING sku`. Kết quả trả mấy hàng?

**Đáp án:** **0 hàng**, vì không có hàng nào mới được chèn. Điều này phải được phân biệt với “đã chèn thành công”; ứng dụng có thể trả trạng thái đã tồn tại.

### Bài 9 — UPSERT làm đổi giá nhưng không đổi tên

Viết câu PostgreSQL để khi trùng SKU thì cập nhật chỉ `unit_price` và thời gian; khi chưa có thì chèn dữ liệu mới.

**Đáp án:**

~~~sql
INSERT INTO catalog_products (
    sku, external_code, product_name, category_code,
    unit_price, stock_qty, vendor_id
)
VALUES (
    'BK-001', 'ERP-A1', 'So tay',
    'BOOK', 120.00, 10, 10
)
ON CONFLICT (sku)
DO UPDATE SET
    unit_price = EXCLUDED.unit_price,
    updated_at = CURRENT_TIMESTAMP
RETURNING sku, product_name, unit_price;
~~~

Nhánh UPDATE không gán `product_name`, nên tên đang lưu không bị ghi đè bởi tên từ hàng đề xuất (trừ các cơ chế ngoài câu lệnh).

### Bài 10 — MERGE với nguồn trùng

Một nguồn MERGE có hai dòng cùng SKU, cả hai khớp một hàng đích. Có nên kỳ vọng MERGE tự chọn dòng sau cùng không?

**Đáp án:** không. Nhiều DBMS có thể báo lỗi khi một hàng đích bị cập nhật nhiều lần hoặc có quy tắc khác. Phải chuẩn hóa nguồn về một hàng theo khóa và chọn một quy tắc ưu tiên rõ ràng trước MERGE.

### Bài 11 — SQLSTATE 23505 có đủ chưa?

PostgreSQL trả `23505` khi INSERT thất bại. Có thể kết luận ngay rằng SKU đã tồn tại không?

**Đáp án:** chưa. Bảng có `UNIQUE(sku)` và `UNIQUE(external_code)`; lỗi có thể đến từ bất kỳ ràng buộc nào. Cần xác định tên constraint hoặc dùng `ON CONFLICT (sku)` khi mục đích chỉ xử lý SKU.

### Bài 12 — Transaction sau lỗi

Trong PostgreSQL, một câu INSERT bị lỗi trong transaction. Ứng dụng vẫn tiếp tục chạy INSERT khác trong cùng transaction mà không rollback. Điều gì có thể xảy ra?

**Đáp án:** transaction có thể đang ở trạng thái thất bại; các câu tiếp theo bị từ chối cho đến khi `ROLLBACK` hoặc rollback về savepoint phù hợp. Không nuốt exception rồi giả định transaction vẫn nguyên vẹn.

### Bài 13 — Trùng request hay trùng SKU?

Hai request có cùng SKU nhưng giá khác. Nên tự động coi request thứ hai là một retry hợp lệ không?

**Đáp án:** không. Trùng SKU chỉ có nghĩa cùng khóa nghiệp vụ; payload có thể mâu thuẫn. Nên có request/idempotency key và kiểm tra payload hoặc trả conflict có giải thích rõ.

### Bài 14 — Đối soát một lô

Một lô có 100 dòng; 75 được chèn, 20 được bỏ vì SKU đã có, 5 bị từ chối vì lỗi dữ liệu. API nên báo “100 thành công” hay báo các loại kết quả?

**Đáp án:** báo **100 dòng đã xem xét**, gồm **75 inserted, 20 skipped_existing, 5 rejected**, kèm danh sách và lý do từng dòng bị từ chối. Không đánh đồng “đã đi qua xử lý” với “đã chèn”.

### Bài 15 — REPLACE hay DO UPDATE?

Một bảng có cột `created_at` và FK tham chiếu tới sản phẩm. Người viết muốn sửa giá nhưng không muốn xóa hàng. Có nên dùng MySQL `REPLACE`/SQLite `OR REPLACE` không?

**Đáp án:** không nên chọn mặc định. Cơ chế replace có thể xóa và chèn lại, làm thay đổi ID/giá trị mặc định và ảnh hưởng FK/trigger. Dùng UPSERT `DO UPDATE` hoặc UPDATE có chọn lọc theo dialect để giữ danh tính hàng.

### Bài 16 — Kiểm tra chính sách nhập tồn kho

Một sự kiện nhận 5 sản phẩm gửi lại ba lần do timeout. Thiết kế nào an toàn hơn: UPSERT cộng 5 mỗi lần, hay lưu `request_key` duy nhất và chỉ áp dụng tác động một lần?

**Đáp án:** cách có **request_key duy nhất**, kiểm soát cùng payload và transaction cho việc ghi event + cập nhật tồn là hướng an toàn hơn. UPSERT cộng dồn theo SKU mỗi lần có thể cộng 15 thay vì 5.

### Bài 17 — Chọn công cụ

Chọn giải pháp phù hợp:

1. Chỉ bỏ qua SKU đã tồn tại, vẫn báo các lỗi khác.
2. Chèn/cập nhật theo khóa trong PostgreSQL.
3. Nạp tệp chứa nhiều dòng sai định dạng và cần báo từng lỗi.
4. So khớp bảng nguồn/đích có nhiều nhánh hành động.
5. Chạy lại cùng sự kiện thanh toán mà không ghi tiền lần hai.

**Gợi ý đáp án:**

1. `ON CONFLICT (sku) DO NOTHING`.
2. `ON CONFLICT (sku) DO UPDATE` với quy tắc cập nhật rõ.
3. Staging + validation + error reporting, không dùng IGNORE để che lỗi.
4. `MERGE` ở DBMS hỗ trợ, nhưng phải kiểm tra uniqueness và concurrency.
5. Idempotency key + transaction + kiểm tra trạng thái đã xử lý.

## 18. Checklist trước khi triển khai

Trước khi đưa UPSERT/MERGE hoặc câu INSERT có xử lý xung đột vào hệ thống, hãy xác định:

1. **Khóa nào xác định bản ghi?** SKU, external ID, email, hay request key?
2. **Xung đột nào được phép bỏ qua?** Chỉ một unique key hay toàn bộ uniqueness conflicts?
3. **Khi trùng khóa, có cần cập nhật không?** Nếu có, chỉ cột nào?
4. **Giá trị sai phải xử lý ra sao?** NOT NULL, CHECK, FK, dữ liệu sai kiểu còn được báo không?
5. **Có nhiều UNIQUE khác nhau không?** Một hàng có thể xung đột với hai thực thể?
6. **Payload retry có giống payload ban đầu không?** Làm sao phát hiện cùng key nhưng nội dung khác?
7. **Nhánh DO UPDATE có idempotent không?** Cộng dồn có nguy cơ lặp?
8. **MERGE có nguồn đơn trị theo khóa không?** Có nguy cơ nhiều source rows khớp cùng target?
9. **Transaction và concurrency được bảo vệ thế nào?** Có UNIQUE constraint, isolation, locking, retry?
10. **Lỗi nào được retry, lỗi nào phải từ chối?** Có giới hạn retry không?
11. **Cảnh báo có bị giấu không?** Đặc biệt khi dùng `IGNORE` trên MySQL/SQLite.
12. **Làm sao biết hàng nào đã ghi?** `RETURNING`, row count, audit/event log.
13. **Khi một lô có lỗi, yêu cầu atomic hay best effort?** Có cần staging và báo từng dòng?
14. **Kết quả API có phân biệt inserted, updated, skipped, rejected không?**
15. **Phiên bản/dialect đang dùng có chính xác cú pháp và quy tắc mong muốn không?**

## 19. Tổng kết

**Xử lý xung đột** là một quyết định có phạm vi rõ: khi hai thao tác muốn ghi cùng một **khóa đã được ràng buộc duy nhất**, hệ thống có thể chọn **bỏ qua**, **cập nhật**, hoặc **báo xung đột**. Nó **không** có nghĩa dữ liệu sai kiểu, vi phạm `NOT NULL`, `CHECK`, `FOREIGN KEY`, lỗi kết nối hay lỗi transaction đều trở thành thành công.

Trong PostgreSQL, `ON CONFLICT (sku) DO NOTHING` diễn đạt rõ việc chỉ bỏ qua trùng SKU; `DO UPDATE` xử lý nhánh cập nhật nhưng vẫn chịu mọi constraint. MySQL `INSERT IGNORE` và SQLite `INSERT OR IGNORE` có phạm vi riêng, có thể bỏ hoặc hạ cấp **những lỗi khác** ngoài duplicate key, nên phải theo dõi warning và kết quả thật. `MERGE` mô tả hành động khi nguồn khớp/không khớp đích, chứ không thay thế ràng buộc dữ liệu, quy tắc nguồn đơn trị hay bảo vệ đồng thời.

Một hệ thống đáng tin cậy phải **báo đúng loại kết quả**: đã thêm, đã cập nhật, đã bỏ vì tồn tại, không thay đổi hay thất bại vì dữ liệu sai. Với thao tác có retry, cần thêm **idempotency key và kiểm soát payload** để không cộng tồn hoặc ghi tiền nhiều lần.

**Nguyên tắc cốt lõi:** chỉ bỏ qua **xung đột được nghiệp vụ cho phép**, không bỏ qua **mọi lỗi chỉ vì câu lệnh cần chạy tiếp**. Khả năng phát hiện và giải thích dữ liệu sai quan trọng không kém khả năng xử lý bản ghi trùng.
