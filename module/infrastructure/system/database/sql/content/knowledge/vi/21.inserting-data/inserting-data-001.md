# INSERT với danh sách cột và một hàng dữ liệu

Một cửa hàng có bảng sản phẩm trong cơ sở dữ liệu. Khi có một sản phẩm mới, hệ thống cần lưu **đúng một bản ghi** gồm mã sản phẩm, tên, giá bán, số lượng tồn và những thông tin liên quan. Trong SQL, thao tác thêm một hàng như vậy thường sử dụng lệnh **`INSERT INTO ... (danh_sách_cột) VALUES (danh_sách_giá_trị)`**.

Ví dụ ngắn:

~~~sql
INSERT INTO products (sku, product_name, unit_price)
VALUES ('BK-001', 'Sach SQL can ban', 120000.00);
~~~

Câu lệnh nói rõ **thêm vào bảng nào**, **điền những cột nào**, **mỗi cột nhận giá trị gì**. Những cột không được liệt kê sẽ được cơ sở dữ liệu xử lý theo **giá trị mặc định**, khả năng cho phép `NULL` và các ràng buộc đã khai báo.

Bài học thuộc **Database SQL → Thêm dữ liệu**. Ta sẽ học thật chắc một câu lệnh `INSERT` có **danh sách cột và một hàng dữ liệu**, sau đó tìm hiểu cách tránh các lỗi phổ biến: lệch thứ tự giá trị, thiếu cột bắt buộc, nhầm `NULL` với `DEFAULT`, trùng khóa, sai kiểu và chèn dữ liệu không an toàn từ ứng dụng.

Ví dụ thực hành dùng **PostgreSQL**. Khi chuyển sang MySQL, SQL Server, SQLite hoặc Oracle Database, phần lớn tư duy vẫn giữ nguyên; một số cú pháp như sinh khóa tự động và trả về hàng vừa chèn khác nhau theo hệ quản trị.

## 1. Cú pháp INSERT một hàng với danh sách cột

Dạng tổng quát:

~~~sql
INSERT INTO ten_bang (
    cot_1,
    cot_2,
    cot_3
)
VALUES (
    gia_tri_1,
    gia_tri_2,
    gia_tri_3
);
~~~

| Thành phần | Vai trò |
| --- | --- |
| `INSERT INTO` | Bắt đầu lệnh thêm hàng vào bảng |
| `ten_bang` | Bảng đích sẽ nhận bản ghi |
| `(cot_1, cot_2, cot_3)` | Danh sách **các cột được chủ động cung cấp giá trị** |
| `VALUES` | Đưa vào một hàng giá trị |
| `(gia_tri_1, gia_tri_2, gia_tri_3)` | Các biểu thức/giá trị tương ứng với danh sách cột |
| `;` | Ký hiệu kết thúc câu lệnh, thường cần khi chạy nhiều câu SQL liên tiếp |

**Nguyên tắc số một: các giá trị khớp với các cột theo vị trí, từ trái sang phải.**

~~~text
INSERT INTO products (sku,       product_name,         unit_price)
VALUES               ('BK-001',  'Sach SQL can ban',    120000.00);
                      |          |                     |
                      v          v                     v
                     sku       product_name           unit_price
~~~

Đây là **một hàng** vì sau `VALUES` chỉ có **một cặp ngoặc chứa các giá trị của hàng đó**. Nếu viết nhiều bộ giá trị ngăn bằng dấu phẩy, đó là dạng thêm **nhiều hàng**, nằm ngoài trọng tâm bài này.

### 1.1. Ba đặc điểm cần nhớ

1. **Danh sách cột nằm ngay sau tên bảng**, không nằm trong `VALUES`.
2. **Số biểu thức trong `VALUES` phải bằng số cột được liệt kê.** Nhiều hay ít hơn đều không hợp lệ.
3. **Giá trị phải phù hợp với cột tương ứng**, gồm kiểu dữ liệu, khả năng nhận `NULL` và các ràng buộc nghiệp vụ.

Trong SQL, dấu nháy đơn `'...'` biểu thị **giá trị chuỗi**. Tên cột như `sku`, `unit_price` thường viết **không có nháy đơn**. Dùng `'sku'` trong danh sách cột không phải cách tham chiếu tên cột thông thường.

## 2. Chuẩn bị bảng mẫu để thực hành

Ta xây dựng bảng `lab_ins261_products` với các kiểu cột điển hình. Chạy đoạn sau **một lần trong database PostgreSQL thực hành riêng**, khi bảng chưa tồn tại:

~~~sql
CREATE TABLE lab_ins261_products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku VARCHAR(30) NOT NULL UNIQUE,
    product_name VARCHAR(100) NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL
        CHECK (unit_price >= 0),
    stock_qty INTEGER NOT NULL DEFAULT 0
        CHECK (stock_qty >= 0),
    category VARCHAR(20) NOT NULL DEFAULT 'OTHER'
        CHECK (category IN ('BOOK', 'STATIONERY', 'OTHER')),
    available BOOLEAN NOT NULL DEFAULT TRUE,
    introduced_on DATE NOT NULL DEFAULT CURRENT_DATE,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Các cột có ý nghĩa:

| Cột | Kiểu | Quy tắc chính |
| --- | --- | --- |
| `product_id` | `BIGINT`, identity | Khóa chính do PostgreSQL tự sinh; không cần cung cấp khi `INSERT` thông thường |
| `sku` | `VARCHAR(30)` | Mã sản phẩm **bắt buộc**, **không trùng** |
| `product_name` | `VARCHAR(100)` | Tên sản phẩm **bắt buộc** |
| `unit_price` | `NUMERIC(12,2)` | Giá **bắt buộc**, không âm |
| `stock_qty` | `INTEGER` | Số lượng tồn mặc định **0**, không âm |
| `category` | `VARCHAR(20)` | Mặc định `'OTHER'`, chỉ nhận `BOOK`, `STATIONERY`, `OTHER` |
| `available` | `BOOLEAN` | Mặc định `TRUE`, không nhận `NULL` |
| `introduced_on` | `DATE` | Mặc định ngày hiện tại theo ngữ cảnh phiên/giao dịch của database |
| `note` | `TEXT` | Có thể để `NULL` vì không khai báo `NOT NULL` |
| `created_at` | `TIMESTAMPTZ` | Mặc định thời điểm hiện tại; dùng để ghi nhận thời điểm thêm |

Đây là **mô hình thực hành**, không phải thiết kế duy nhất dành cho mọi cửa hàng. Mục tiêu của bảng là quan sát cách `INSERT` xử lý cột bắt buộc, cột tùy chọn, giá trị mặc định, identity và ràng buộc.

**Lưu ý về môi trường:** các lệnh `CREATE TABLE` và `INSERT` thay đổi dữ liệu thật trong database đang kết nối. Hãy dùng database thực hành và không chạy những đoạn này trực tiếp trên hệ thống sản xuất.

## 3. INSERT đầu tiên: ghi một hàng với năm cột

Ta thêm một cuốn sách vào bảng:

~~~sql
INSERT INTO lab_ins261_products (
    sku,
    product_name,
    unit_price,
    stock_qty,
    category
)
VALUES (
    'BK-SQL-001',
    'Sách nhập môn SQL',
    120000.00,
    15,
    'BOOK'
);
~~~

Đây là **một lệnh thêm một hàng**. Từng cột nhận đúng giá trị theo vị trí:

| Cột được liệt kê | Giá trị từ `VALUES` | Ý nghĩa |
| --- | --- | --- |
| `sku` | `'BK-SQL-001'` | Mã sản phẩm |
| `product_name` | `'Sách nhập môn SQL'` | Tên sách |
| `unit_price` | `120000.00` | Giá 120.000 đơn vị tiền, lưu dạng số |
| `stock_qty` | `15` | Đang có 15 sản phẩm |
| `category` | `'BOOK'` | Thuộc danh mục sách |

Lệnh **không** cung cấp `product_id`, `available`, `introduced_on`, `note` và `created_at`. PostgreSQL xử lý như sau:

- `product_id`: tự sinh số định danh.
- `available`: nhận `TRUE` theo mặc định.
- `introduced_on`: nhận `CURRENT_DATE`.
- `note`: nhận `NULL` do cột cho phép thiếu giá trị và không có `DEFAULT` riêng.
- `created_at`: nhận `CURRENT_TIMESTAMP`.

Sau khi chạy lệnh, kiểm tra **bản ghi vừa thêm theo mã SKU**:

~~~sql
SELECT
    product_id,
    sku,
    product_name,
    unit_price,
    stock_qty,
    category,
    available,
    introduced_on,
    note,
    created_at
FROM lab_ins261_products
WHERE sku = 'BK-SQL-001';
~~~

Nếu lệnh `INSERT` thành công trên bảng mới tạo, truy vấn `SELECT` trả **một hàng**. Những giá trị tự sinh như `product_id`, `introduced_on` và `created_at` phụ thuộc trạng thái chuỗi identity, phiên database và thời điểm chạy; **không nên viết cứng một ID hoặc ngày vào kết quả kỳ vọng**.

### 3.1. Vì sao không viết tất cả mười cột?

Lợi ích lớn nhất của **danh sách cột** là chỉ cung cấp những dữ liệu ứng dụng thực sự có trách nhiệm nhập. Database có thể quản lý các cột như thời gian tạo, ID tự sinh và giá trị mặc định.

Viết:

~~~sql
INSERT INTO lab_ins261_products (
    sku, product_name, unit_price, stock_qty, category
)
VALUES (
    'BK-SQL-001', 'Sách nhập môn SQL', 120000.00, 15, 'BOOK'
);
~~~

rõ nghĩa hơn một chuỗi giá trị không kèm tên cột, đặc biệt khi sau này bảng được thêm cột có mặc định. **Danh sách cột giúp giảm phụ thuộc vào thứ tự cột vật lý của bảng**, nhưng không loại bỏ nghĩa vụ tuân thủ ràng buộc khi schema thay đổi.

## 4. Thứ tự cột trong INSERT có thể khác thứ tự trong bảng

PostgreSQL **không bắt buộc** cột trong danh sách `INSERT` phải viết theo thứ tự cột đã khai báo trong `CREATE TABLE`. Điều bắt buộc là **giá trị nằm đúng vị trí của cột trong danh sách INSERT**.

Ví dụ hợp lệ:

~~~sql
INSERT INTO lab_ins261_products (
    product_name,
    unit_price,
    sku,
    category,
    stock_qty
)
VALUES (
    'Bút ghi chú',
    12000.00,
    'ST-PEN-002',
    'STATIONERY',
    30
);
~~~

Kết quả vẫn đúng: `product_name` là “Bút ghi chú”, `unit_price` là 12000, `sku` là `ST-PEN-002`. Vì SQL **ghép theo vị trí trong câu `INSERT`**, không ghép theo tên suy đoán từ giá trị.

### 4.1. Sai do lệch thứ tự giá trị

~~~sql
-- SAI ve kieu du lieu/ngu nghia:
INSERT INTO lab_ins261_products (
    sku,
    product_name,
    unit_price
)
VALUES (
    'ST-PEN-003',
    12000.00,
    'Bút màu'
);
~~~

Ở câu này:

- `12000.00` được đặt vào `product_name` (cột chuỗi).
- `'Bút màu'` được đặt vào `unit_price` (cột số).

PostgreSQL sẽ không thể chuyển `'Bút màu'` thành kiểu số `NUMERIC` hợp lệ, nên câu lệnh thất bại. Trong trường hợp giá trị **đều có thể chuyển kiểu**, câu lệnh thậm chí có thể chạy nhưng đưa dữ liệu vào **sai cột**, khó phát hiện hơn.

### 4.2. Sai do số lượng cột và giá trị không bằng nhau

~~~sql
-- SAI: ba cot nhung chi hai gia tri.
INSERT INTO lab_ins261_products (sku, product_name, unit_price)
VALUES ('BK-ERR-001', 'Sách thiếu giá');
~~~

~~~sql
-- SAI: hai cot nhung ba gia tri.
INSERT INTO lab_ins261_products (sku, product_name)
VALUES ('BK-ERR-002', 'Sách thừa giá trị', 100000.00);
~~~

Lỗi được phát hiện ngay từ cấu trúc câu lệnh: mỗi cột liệt kê cần đúng **một biểu thức** tương ứng. Số lượng cột của **toàn bộ bảng** có thể lớn hơn số cột được liệt kê trong `INSERT`, vì các cột bỏ qua còn được xử lý theo quy tắc mặc định/`NULL`.

### 4.3. Đừng nhầm dấu phẩy trong cấu trúc

~~~sql
INSERT INTO lab_ins261_products (sku, product_name, unit_price)
VALUES ('BK-004', 'SQL nâng cao', 165000.00);
~~~

Các dấu phẩy **phân cách các phần tử** trong danh sách cột và danh sách giá trị; không viết dấu phẩy cuối nếu không có phần tử tiếp theo. Dấu ngoặc của `VALUES` bao lấy **một hàng**. Dấu chấm trong `165000.00` là ký hiệu thập phân trong biểu thức số SQL, không dùng dấu phẩy hàng nghìn theo cách trình bày tiếng Việt.

## 5. Cột không được liệt kê: DEFAULT, NULL và lỗi NOT NULL

Không phải cột nào cũng cần có mặt trong lệnh `INSERT`. Nhưng điều gì xảy ra khi **bỏ cột** phụ thuộc vào định nghĩa của cột đó.

| Loại cột | Bỏ khỏi danh sách `INSERT` sẽ thế nào? |
| --- | --- |
| Có `DEFAULT` | Nhận **giá trị mặc định** tương ứng |
| Không có `DEFAULT` và cho phép `NULL` | Thông thường nhận **`NULL`** |
| `NOT NULL`, không có mặc định hoặc cơ chế tự sinh | **Lỗi ràng buộc**, không thêm hàng |
| Identity/generated column theo thiết kế | Hệ quản trị tính hoặc sinh giá trị theo quy tắc đã khai báo |

Xem câu sau chỉ cung cấp **ba cột bắt buộc**:

~~~sql
INSERT INTO lab_ins261_products (
    sku,
    product_name,
    unit_price
)
VALUES (
    'BK-005',
    'Tài liệu SQL thực hành',
    99000.00
);
~~~

Nếu lệnh thành công:

- `stock_qty = 0`.
- `category = 'OTHER'`.
- `available = TRUE`.
- `introduced_on` là ngày mặc định được database áp dụng.
- `note IS NULL`.
- `created_at` được tự điền.
- `product_id` được tự sinh.

Đây là lý do câu lệnh với danh sách cột thường phù hợp khi bảng có nhiều cột kỹ thuật hoặc giá trị mặc định.

### 5.1. Bỏ cột khác với ghi tường minh NULL

Hai câu dưới **không đồng nghĩa**:

~~~sql
-- Bo stock_qty: nhan DEFAULT 0.
INSERT INTO lab_ins261_products (
    sku, product_name, unit_price
)
VALUES ('BK-006', 'Cẩm nang truy vấn', 80000.00);
~~~

~~~sql
-- Ghi NULL cho stock_qty: vi pham NOT NULL, khong nhan DEFAULT.
INSERT INTO lab_ins261_products (
    sku, product_name, unit_price, stock_qty
)
VALUES ('BK-ERR-007', 'Sản phẩm lỗi', 80000.00, NULL);
~~~

Khi đã **chủ động cung cấp `NULL`**, database kiểm tra giá trị đó với ràng buộc `NOT NULL`. Nó **không tự hiểu `NULL` là “xin áp dụng mặc định”**.

Điểm này quan trọng khi dữ liệu đến từ form hoặc API: nếu một trường không được gửi, ứng dụng có thể cần **bỏ cột** khỏi `INSERT`; nếu trường được gửi với ý nghĩa “không có giá trị”, ứng dụng cần xác định nên lưu `NULL` hay áp dụng mặc định theo hợp đồng dữ liệu.

### 5.2. Dùng từ khóa DEFAULT cho một vị trí giá trị

SQL cho phép chỉ rõ một cột dùng giá trị mặc định:

~~~sql
INSERT INTO lab_ins261_products (
    sku,
    product_name,
    unit_price,
    stock_qty,
    category
)
VALUES (
    'BK-008',
    'Luyện tập SQL',
    105000.00,
    DEFAULT,
    DEFAULT
);
~~~

Trong câu này:

- `stock_qty` dùng mặc định **0**.
- `category` dùng mặc định **`'OTHER'`**.

Từ khóa `DEFAULT` ở vị trí một biểu thức trong `VALUES` là **chỉ thị áp dụng mặc định cho cột tương ứng**, không phải một chuỗi `'DEFAULT'` hay một giá trị số.

### 5.3. Cột tùy chọn có thể nhận NULL

`note` được khai báo `TEXT` mà không có `NOT NULL`:

~~~sql
INSERT INTO lab_ins261_products (
    sku, product_name, unit_price, note
)
VALUES (
    'BK-009',
    'SQL qua ví dụ',
    115000.00,
    NULL
);
~~~

Câu trên hợp lệ và lưu `note IS NULL`. Nếu `note` bị bỏ khỏi danh sách, nó cũng nhận `NULL` trong thiết kế bảng này. Cả hai có thể cho cùng dữ liệu lưu, nhưng **ý định của ứng dụng** vẫn có thể khác nhau: “không gửi ghi chú” so với “gửi ghi chú rỗng hoặc xóa ghi chú”.

## 6. NULL, chuỗi rỗng, số 0 và FALSE khác nhau

Với một cột văn bản cho phép `NULL`, hãy phân biệt:

~~~sql
-- Khong biet/chua co gia tri ghi chu:
note = NULL

-- Co chuoi van ban, nhung chuoi co do dai bang 0:
note = ''

-- Co chuoi gom cac khoang trang:
note = '   '
~~~

Trong PostgreSQL, `NULL`, `''` và `'   '` là những trạng thái khác nhau. Không thể dùng `note = NULL` để tìm hàng có ghi chú thiếu; phải dùng `note IS NULL`.

Tương tự:

- `stock_qty = 0` nghĩa là biết tồn kho **bằng 0**, khác “chưa biết tồn kho” (`NULL`) nếu schema cho phép.
- `available = FALSE` nghĩa là biết sản phẩm **không khả dụng**, khác `NULL`.
- `unit_price = 0` là giá 0 hợp lệ theo `CHECK (unit_price >= 0)`, không phải dữ liệu bị bỏ trống.

Ví dụ thêm một sản phẩm miễn phí và không khả dụng:

~~~sql
INSERT INTO lab_ins261_products (
    sku,
    product_name,
    unit_price,
    stock_qty,
    available,
    note
)
VALUES (
    'BK-FREE-010',
    'Tài liệu dùng thử',
    0.00,
    0,
    FALSE,
    ''
);
~~~

Giá trị `FALSE` là Boolean SQL, không phải chuỗi `'FALSE'` trong ví dụ này. `note = ''` là chuỗi rỗng có chủ đích; nó khác với việc bỏ cột `note` để nhận `NULL`.

## 7. ID tự sinh: vì sao thường bỏ product_id khỏi INSERT?

Bảng mẫu khai báo:

~~~sql
product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY
~~~

Điều đó cho phép cơ sở dữ liệu sinh giá trị định danh cho hàng mới. Với cách khai báo `GENERATED ALWAYS` của PostgreSQL, một lệnh `INSERT` thông thường **không được tự ý gán giá trị định danh tường minh**:

~~~sql
-- Khong nen/khong hop le theo mac dinh GENERATED ALWAYS.
INSERT INTO lab_ins261_products (
    product_id, sku, product_name, unit_price
)
VALUES (
    999, 'BK-ERR-011', 'Sách ép ID', 100000.00
);
~~~

Thay vào đó, chỉ nhập các cột nghiệp vụ:

~~~sql
INSERT INTO lab_ins261_products (
    sku, product_name, unit_price
)
VALUES (
    'BK-011',
    'Tự học PostgreSQL',
    175000.00
);
~~~

PostgreSQL tự sinh `product_id` cho hàng mới. Cơ chế khác như `GENERATED BY DEFAULT AS IDENTITY` có quy tắc chấp nhận giá trị tường minh khác. Bài này dùng `GENERATED ALWAYS` để hướng người học **không tự gán khóa kỹ thuật** khi không có lý do quản trị đặc biệt.

### 7.1. Có phải ID tăng đều không có khoảng trống?

**Không.** Identity thường dùng sequence. Trong PostgreSQL, giá trị sequence có thể được tiêu thụ ngay cả khi một lệnh `INSERT` thất bại hoặc một transaction bị `ROLLBACK`. Vì vậy `product_id` có thể có **khoảng trống**.

Không nên coi ID là “số thứ tự hàng liên tục” hoặc suy ra chắc chắn hàng kế tiếp có `product_id = MAX(product_id) + 1`. Mục tiêu của ID là **định danh**, không phải bảo đảm dãy số hiển thị không đứt đoạn.

## 8. RETURNING: lấy thông tin hàng vừa được INSERT

Một ứng dụng sau khi thêm sản phẩm thường cần biết **ID do database tạo**, và có thể cần cả trạng thái hoặc ngày được áp dụng mặc định. Trong PostgreSQL, dùng `RETURNING`:

~~~sql
INSERT INTO lab_ins261_products (
    sku, product_name, unit_price, stock_qty
)
VALUES (
    'BK-012',
    'Thiết kế cơ sở dữ liệu',
    190000.00,
    8
)
RETURNING
    product_id,
    sku,
    product_name,
    stock_qty,
    category,
    available,
    created_at;
~~~

`RETURNING` trả về các giá trị **của hàng đã được thêm**, bao gồm `product_id` được tự sinh và những cột nhận mặc định. Truy vấn này vẫn là **một lệnh `INSERT` thêm một hàng**, không phải hai thao tác độc lập.

Điểm lợi:

- Không cần đoán `product_id`.
- Không cần chạy `SELECT MAX(product_id)`, vốn **không an toàn** để tìm ID hàng của phiên đang thao tác nếu nhiều phiên chèn đồng thời.
- Có thể nhận những giá trị thực tế database đã áp dụng, thay vì tự mô phỏng `DEFAULT` ở phía ứng dụng.

**Tác dụng phụ cần nhớ:** lệnh `INSERT ... RETURNING` vẫn **thêm dữ liệu thật**. `RETURNING` chỉ trả thông tin, không biến lệnh thành truy vấn chỉ đọc.

### 8.1. RETURNING * có nên dùng không?

~~~sql
INSERT INTO lab_ins261_products (sku, product_name, unit_price)
VALUES ('BK-013', 'Tối ưu câu SQL', 210000.00)
RETURNING *;
~~~

`RETURNING *` tiện khi học và muốn nhìn tất cả cột. Trong ứng dụng, thường nên liệt kê đúng các cột cần trả để hợp đồng dữ liệu rõ hơn và không phụ thuộc vào việc schema bổ sung cột mới.

## 9. Kiểu dữ liệu trong VALUES: chuỗi, số, ngày, Boolean và NULL

Giá trị trong `VALUES` phải có kiểu phù hợp với cột tương ứng.

| Kiểu cột | Ví dụ giá trị SQL | Ghi chú |
| --- | --- | --- |
| `VARCHAR`, `TEXT` | `'Sách SQL'` | Chuỗi dùng nháy đơn |
| `INTEGER` | `15` | Số nguyên, không thêm dấu phẩy tách hàng nghìn |
| `NUMERIC(12,2)` | `125000.50` | Số thập phân; dùng dấu chấm trong SQL |
| `BOOLEAN` | `TRUE`, `FALSE` | Hằng Boolean, không phải chuỗi văn bản |
| `DATE` | `DATE '2026-04-15'` | Literal ngày kiểu SQL rõ ràng |
| `TIMESTAMPTZ` | `CURRENT_TIMESTAMP` | Một biểu thức thời điểm do DB đánh giá |
| Cột có thể thiếu | `NULL` | Giá trị thiếu; phải thỏa ràng buộc của cột |
| Cột có mặc định | `DEFAULT` | Yêu cầu DB áp dụng giá trị mặc định ở vị trí đó |

Ví dụ thêm một sản phẩm với ngày được chỉ định:

~~~sql
INSERT INTO lab_ins261_products (
    sku,
    product_name,
    unit_price,
    stock_qty,
    available,
    introduced_on,
    note
)
VALUES (
    'ST-NOTE-014',
    'Sổ tay kẻ dòng',
    35000.50,
    20,
    TRUE,
    DATE '2026-04-15',
    'Đợt hàng tháng 4'
);
~~~

`DATE '2026-04-15'` minh họa cách chỉ rõ kiểu ngày; nó không phụ thuộc định dạng ngày tháng hiển thị trên giao diện như `15/04/2026`. Với kiểu `TIMESTAMPTZ`, giá trị hiển thị còn phụ thuộc múi giờ của phiên; không nên so trực tiếp chuỗi hiển thị giữa các phiên có cấu hình múi giờ khác nhau mà không hiểu chuyển đổi thời điểm.

### 9.1. Nháy đơn trong dữ liệu chuỗi

Nếu tên sản phẩm chứa dấu nháy đơn, không được đóng chuỗi một cách vô tình:

~~~sql
-- SAI do chuoi duoc dong som:
-- VALUES ('BK-ERR-015', 'O'Reilly SQL', 130000.00);
~~~

Trong SQL literal, có thể **nhân đôi dấu nháy đơn** bên trong chuỗi:

~~~sql
INSERT INTO lab_ins261_products (
    sku, product_name, unit_price
)
VALUES (
    'BK-015',
    'O''Reilly SQL',
    130000.00
);
~~~

Giá trị được lưu trong `product_name` là **`O'Reilly SQL`** với một dấu nháy đơn. Nhưng khi dữ liệu đến từ người dùng, **giải pháp chính nên là truy vấn có tham số**, không phải tự nối và tự thay dấu nháy theo từng trường hợp. Mục 14 trình bày nguyên tắc đó.

### 9.2. VALUES có thể chứa biểu thức

Các phần tử của `VALUES` không chỉ là hằng số:

~~~sql
INSERT INTO lab_ins261_products (
    sku, product_name, unit_price, stock_qty, introduced_on
)
VALUES (
    'BK-016',
    'SQL và thực tế',
    100000.00 + 25000.00,
    5 * 2,
    CURRENT_DATE
);
~~~

Ở đây `unit_price = 125000.00` và `stock_qty = 10`. `CURRENT_DATE` là biểu thức do database đánh giá. Dù có biểu thức tính toán, `VALUES (...)` vẫn mô tả **một hàng**.

Không nên mặc định các biểu thức trong `VALUES` có thể tự tham chiếu thoải mái tới một cột khác của **chính hàng đang chèn**; cú pháp tham chiếu, giá trị mặc định và cột tính toán có quy tắc riêng theo hệ quản trị. Nếu cần một công thức phụ thuộc dữ liệu đầu vào, hãy tính rõ biểu thức hoặc dùng cơ chế cột sinh theo thiết kế schema.

## 10. Ràng buộc quyết định INSERT có được chấp nhận hay không

Một câu `INSERT` đúng cú pháp vẫn có thể **thất bại** khi dữ liệu vi phạm ràng buộc. Những kiểm tra đó tồn tại để bảo vệ tính nhất quán của bảng.

### 10.1. NOT NULL: thiếu cột bắt buộc

Trong bảng mẫu, `sku`, `product_name` và `unit_price` đều bắt buộc và không có mặc định riêng.

~~~sql
-- SAI: thieu unit_price va cot nay NOT NULL, khong co DEFAULT.
INSERT INTO lab_ins261_products (
    sku, product_name
)
VALUES (
    'BK-ERR-017',
    'Sách không có giá'
);
~~~

Khi `unit_price` bị bỏ, giá trị thường được xem như `NULL` vì không có mặc định. Ràng buộc `NOT NULL` chặn hàng đó. Câu đúng cần cung cấp giá hợp lệ:

~~~sql
INSERT INTO lab_ins261_products (
    sku, product_name, unit_price
)
VALUES (
    'BK-017',
    'Sách có giá',
    85000.00
);
~~~

### 10.2. UNIQUE: SKU không được trùng

`sku VARCHAR(30) NOT NULL UNIQUE` khiến hai sản phẩm không được có cùng mã trong bảng. Giả sử `BK-SQL-001` đã được thêm ở mục 3:

~~~sql
-- SAI neu BK-SQL-001 da ton tai.
INSERT INTO lab_ins261_products (
    sku, product_name, unit_price
)
VALUES (
    'BK-SQL-001',
    'Sản phẩm trùng SKU',
    99000.00
);
~~~

PostgreSQL thường báo vi phạm ràng buộc duy nhất (unique violation). Việc ứng dụng đã kiểm tra “SKU chưa tồn tại” **không thay thế** `UNIQUE` ở database, vì một phiên khác có thể thêm mã đó sau khi ứng dụng kiểm tra nhưng trước khi lệnh `INSERT` được thực hiện.

Lệnh `INSERT` thông thường không tự “cập nhật bản ghi trùng” nếu không có cú pháp và quy tắc upsert riêng. Việc xử lý xung đột như `ON CONFLICT` của PostgreSQL là chủ đề mở rộng, không thay đổi ý nghĩa cơ bản của `INSERT ... VALUES (...)` trong bài.

### 10.3. CHECK: giá và tồn kho không được âm

~~~sql
-- SAI: vi pham CHECK (unit_price >= 0).
INSERT INTO lab_ins261_products (
    sku, product_name, unit_price
)
VALUES (
    'BK-ERR-018',
    'Giá âm',
    -1000.00
);
~~~

~~~sql
-- SAI: vi pham CHECK (stock_qty >= 0).
INSERT INTO lab_ins261_products (
    sku, product_name, unit_price, stock_qty
)
VALUES (
    'BK-ERR-019',
    'Tồn âm',
    100000.00,
    -5
);
~~~

Không phải mọi giá trị `0` đều sai. Bảng mẫu cho phép `unit_price = 0` và `stock_qty = 0` vì điều kiện là `>= 0`. Nếu nghiệp vụ cần **giá lớn hơn 0**, ràng buộc phải là `CHECK (unit_price > 0)` hoặc một quy tắc phù hợp khác.

### 10.4. CHECK danh mục: chỉ cho phép giá trị đã khai báo

~~~sql
-- SAI: category khong thuoc danh sach cho phep.
INSERT INTO lab_ins261_products (
    sku, product_name, unit_price, category
)
VALUES (
    'BK-ERR-020',
    'Sách ngoại lệ',
    110000.00,
    'ELECTRONICS'
);
~~~

Cột `category` chỉ chấp nhận `'BOOK'`, `'STATIONERY'`, `'OTHER'`; thêm một nhãn bất kỳ không được chấp nhận chỉ vì đó là chuỗi hợp lệ.

### 10.5. PRIMARY KEY và FOREIGN KEY

`product_id` là `PRIMARY KEY`: khi được tạo, giá trị của nó phải không `NULL` và duy nhất. Nếu một bảng có **khóa ngoại** (*foreign key*), `INSERT` còn phải bảo đảm giá trị tham chiếu đúng hàng cha khi ràng buộc được kiểm tra.

Ví dụ **minh họa độc lập**, không chạy nếu chưa tạo hai bảng tương ứng:

~~~sql
-- Gia su orders.customer_id REFERENCES customers.customer_id.
INSERT INTO orders (
    customer_id,
    order_date,
    total_amount
)
VALUES (
    42,
    DATE '2026-04-15',
    250000.00
);
~~~

Lệnh chỉ hợp lệ về khóa ngoại nếu khách hàng `customer_id = 42` tồn tại trong bảng cha tại thời điểm kiểm tra theo quy tắc ràng buộc; ngoài ra các cột và giá trị khác phải đáp ứng schema thật. Không nên bỏ ràng buộc khóa ngoại chỉ để một dòng `INSERT` chạy thành công.

## 11. Một lệnh INSERT có một hàng và tính nguyên tử

Với bảng thông thường, một câu `INSERT` được xử lý như một câu lệnh thay đổi dữ liệu trong giao dịch. Khi lệnh vi phạm ràng buộc, database **không lưu một nửa các cột của hàng rồi để phần còn lại thiếu**.

Với PostgreSQL và chế độ **autocommit** thường dùng ở SQL Editor, một câu `INSERT` thành công được commit theo chế độ của client/connection. Nếu bạn đang ở trong transaction tường minh, thay đổi có thể chưa được commit và vẫn có thể rollback.

### 11.1. Dùng BEGIN/ROLLBACK để thử chèn mà không giữ bản ghi

~~~sql
BEGIN;

INSERT INTO lab_ins261_products (
    sku, product_name, unit_price
)
VALUES (
    'BK-DEMO-021',
    'Sản phẩm thử giao dịch',
    70000.00
);

SELECT sku, product_name, unit_price
FROM lab_ins261_products
WHERE sku = 'BK-DEMO-021';

ROLLBACK;
~~~

Trong **chính transaction**, `SELECT` nhìn thấy hàng vừa thêm. Sau `ROLLBACK`, thay đổi trong transaction bị hủy; lệnh kiểm tra tiếp theo sẽ không tìm thấy hàng đó:

~~~sql
SELECT sku
FROM lab_ins261_products
WHERE sku = 'BK-DEMO-021';
~~~

Nếu cần giữ thay đổi, dùng `COMMIT` thay cho `ROLLBACK`, sau khi đã xác nhận dữ liệu và phạm vi giao dịch đúng ý định.

### 11.2. Nếu có lỗi bên trong transaction PostgreSQL

Trong một transaction PostgreSQL, sau khi một câu lệnh báo lỗi, transaction có thể chuyển sang trạng thái lỗi và **các câu SQL tiếp theo không được chạy như bình thường** cho đến khi `ROLLBACK` hoặc rollback về một `SAVEPOINT` hợp lệ.

Vì thế, các ví dụ **SAI** trong bài nhằm giải thích nguyên nhân lỗi, **không** nên dán và thực thi hàng loạt trong cùng một transaction rồi mong mọi câu tiếp tục. Hãy chạy riêng từng ví dụ lỗi trong môi trường thực hành, xem thông báo và khôi phục transaction trước khi làm bài tiếp.

### 11.3. ROLLBACK không nhất thiết hoàn tác bộ đếm identity

Trong PostgreSQL, sequence dùng để sinh identity không hoàn toàn tuân theo rollback như giá trị hàng của bảng. Sau khi `ROLLBACK` một lần chèn, một ID đã được cấp phát có thể không được sử dụng lại; đây là lý do không nên yêu cầu `product_id` luôn liên tục hoặc dùng nó làm số thứ tự báo cáo.

## 12. Cách kiểm tra kết quả sau khi chèn một hàng

Hãy phân biệt hai nhiệm vụ:

- **`INSERT`:** thêm hàng.
- **`SELECT`:** kiểm tra hoặc truy vấn hàng đã có.

Ví dụ đầy đủ:

~~~sql
INSERT INTO lab_ins261_products (
    sku,
    product_name,
    unit_price,
    stock_qty
)
VALUES (
    'ST-022',
    'Bộ giấy đánh dấu',
    25000.00,
    40
);

SELECT
    sku,
    product_name,
    unit_price,
    stock_qty,
    category
FROM lab_ins261_products
WHERE sku = 'ST-022';
~~~

Sau khi chèn thành công trên bảng chưa có mã `ST-022`, `SELECT` trả một hàng với `category = 'OTHER'`, vì cột này đã nhận giá trị mặc định.

Trong một số trình SQL, thông báo dạng **“1 row affected”** hoặc thẻ lệnh PostgreSQL dạng `INSERT 0 1` cho biết lệnh đã ảnh hưởng một hàng. Đây là thông tin từ client/driver; muốn xem giá trị thật, dùng `RETURNING` hoặc `SELECT`.

### 12.1. Tránh kiểm tra bằng MAX(product_id)

Không nên viết:

~~~sql
-- Khong dung cach nay de suy ra ID cua hang minh vua them:
SELECT MAX(product_id)
FROM lab_ins261_products;
~~~

Trong hệ thống có nhiều phiên thêm hàng đồng thời, `MAX(product_id)` có thể là ID của **hàng do phiên khác thêm**. `RETURNING product_id` của chính lệnh `INSERT` là cách PostgreSQL cung cấp ID hàng được tạo một cách trực tiếp và rõ nghĩa.

### 12.2. Một SKU phải chỉ trả một hàng

Trong bảng mẫu, `sku` có `UNIQUE NOT NULL`. Vì vậy truy vấn:

~~~sql
SELECT COUNT(*) AS matching_rows
FROM lab_ins261_products
WHERE sku = 'BK-SQL-001';
~~~

phải trả **0 hoặc 1** tùy SKU tồn tại hay không. Nếu người học chèn thành công mã đó ở mục 3 thì kết quả là **1**. Đó là hệ quả của ràng buộc `UNIQUE`, không phải do `SELECT` tự loại trùng.

## 13. INSERT một hàng so với các cách thêm dữ liệu khác

SQL còn có nhiều cách thêm dữ liệu, nhưng mỗi cách phục vụ mục tiêu khác nhau:

| Cách viết | Mục đích |
| --- | --- |
| `INSERT INTO t (a, b) VALUES (x, y)` | **Thêm một hàng**, chỉ rõ các cột được cung cấp |
| `INSERT INTO t (a, b) VALUES (x1, y1), (x2, y2)` | Thêm **nhiều hàng** trong một lệnh, nếu dialect hỗ trợ |
| `INSERT INTO t (a, b) SELECT ...` | Thêm dữ liệu lấy từ **kết quả truy vấn** |
| `INSERT INTO t DEFAULT VALUES` | Thử thêm một hàng chỉ bằng mặc định; chỉ hợp lệ nếu các ràng buộc được đáp ứng |
| `UPDATE t SET ... WHERE ...` | **Sửa** những hàng đã tồn tại |
| `INSERT ... ON CONFLICT ...` | Xử lý xung đột theo cú pháp của PostgreSQL, có thể bỏ qua hoặc cập nhật tùy quy tắc |

Với bảng `lab_ins261_products`, câu:

~~~sql
-- Khong hop le cho bang mau vi sku, product_name va unit_price
-- la NOT NULL va khong co DEFAULT.
INSERT INTO lab_ins261_products DEFAULT VALUES;
~~~

không thể tạo một sản phẩm hợp lệ vì thiếu các giá trị bắt buộc. `DEFAULT VALUES` không phải “bỏ qua mọi kiểm tra”.

### 13.1. Vì sao nên viết danh sách cột thay vì bỏ danh sách?

Trong SQL có dạng không liệt kê cột:

~~~sql
-- Chi minh hoa hinh dang, KHONG chay tren bang mau:
INSERT INTO some_table
VALUES (gia_tri_1, gia_tri_2, ...);
~~~

Khi không viết danh sách cột, câu lệnh phụ thuộc **danh sách và thứ tự cột đích** theo quy tắc dialect/schema. Với bảng mẫu có identity và nhiều cột mặc định, cách đó không phù hợp cho bài thực hành.

Viết danh sách cột giúp người đọc nhìn thấy chính xác **những giá trị nào do câu lệnh cung cấp** và giảm nguy cơ nhầm khi bảng được mở rộng.

### 13.2. Một hàng mới hay cập nhật hàng cũ?

Nếu mã SKU đã tồn tại và người dùng muốn đổi giá, đó thường là một bài toán **`UPDATE` theo khóa** hoặc **upsert có quy tắc rõ ràng**, không phải chèn một bản ghi cùng SKU bằng `INSERT` thông thường.

Ví dụ:

~~~sql
-- Minh hoa cu phap UPDATE, khong phai bai tap INSERT:
UPDATE lab_ins261_products
SET unit_price = 125000.00
WHERE sku = 'BK-SQL-001';
~~~

Không tự bỏ `UNIQUE` hoặc đổi SKU ngẫu nhiên để vượt qua lỗi trùng nếu nghiệp vụ thực sự muốn cập nhật hàng cũ.

## 14. Thêm dữ liệu từ ứng dụng: dùng câu lệnh có tham số

Trong ứng dụng, nhiều giá trị của `INSERT` đến từ form, API hoặc file nhập liệu. **Không ghép trực tiếp nội dung người dùng vào chuỗi SQL**, kể cả khi thao tác chỉ thêm một hàng.

Ví dụ **không an toàn** về nguyên tắc:

~~~text
sql = "INSERT INTO products (sku, product_name, unit_price) VALUES ('"
      + userSku + "', '" + userName + "', " + userPrice + ")"
~~~

Tên sản phẩm có dấu nháy đơn như `O'Reilly SQL` có thể làm hỏng cú pháp. Nghiêm trọng hơn, việc nối chuỗi với đầu vào không tin cậy có thể tạo lỗ hổng **SQL injection**.

Nên dùng **prepared statement / parameterized query**. Ví dụ minh họa JDBC trên Java khi đã có kết nối `Connection conn` hợp lệ:

~~~java
String sql = """
    INSERT INTO lab_ins261_products (
        sku, product_name, unit_price, stock_qty
    )
    VALUES (?, ?, ?, ?)
    """;

try (PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setString(1, "BK-JDBC-023");
    ps.setString(2, "Sách học SQL");
    ps.setBigDecimal(3, new BigDecimal("142000.00"));
    ps.setInt(4, 12);

    int affectedRows = ps.executeUpdate();
    System.out.println("Rows inserted: " + affectedRows);
}
~~~

Đây là **đoạn code minh họa** trong một ứng dụng đã thiết lập `Connection` và import những lớp JDBC/Java cần thiết; không phải một chương trình Java độc lập có thể chạy mà không cấu hình kết nối.

Điểm quan trọng:

- Dấu `?` là **vị trí tham số** được driver truyền dưới dạng dữ liệu, không phải chỗ ghép đoạn SQL do người dùng nhập.
- `ps.setString(1, ...)` đặt giá trị cho cột thứ nhất trong danh sách (ở đây là `sku`).
- `ps.setBigDecimal(3, ...)` giúp truyền giá tiền bằng kiểu thập phân chính xác thay vì suy diễn từ chuỗi.
- `executeUpdate()` thực hiện câu lệnh thay đổi dữ liệu; nếu thành công với một hàng thì thường trả số hàng ảnh hưởng là 1.

Ứng dụng vẫn cần kiểm tra đầu vào (ví dụ tên không rỗng, giá hợp lệ), nhưng **ràng buộc ở database** là lớp bảo vệ cuối cùng trước dữ liệu không hợp lệ hoặc truy cập đồng thời.

## 15. Khác biệt giữa các SQL dialect

Cấu trúc **`INSERT INTO bảng (danh sách cột) VALUES (một hàng giá trị)`** được hỗ trợ rộng rãi. Sự khác biệt thường nằm ở **khóa tự sinh**, cách lấy khóa sau khi chèn, kiểu dữ liệu và một số cú pháp mở rộng.

| Vấn đề | PostgreSQL | Ghi chú ở các hệ khác |
| --- | --- | --- |
| `INSERT INTO t (a, b) VALUES (x, y)` | Hỗ trợ | Cú pháp cơ bản phổ biến ở MySQL, SQL Server, SQLite và Oracle |
| Tên cột trong danh sách | Ghép giá trị theo vị trí | Nguyên tắc chung |
| Cột tự sinh ID | `GENERATED ... AS IDENTITY`, cơ chế sequence | MySQL thường dùng `AUTO_INCREMENT`; SQL Server dùng `IDENTITY`; SQLite có quy tắc `INTEGER PRIMARY KEY`/rowid; Oracle có identity/sequence |
| Lấy hàng vừa thêm | `RETURNING ...` | SQL Server có `OUTPUT INSERTED...`; SQLite bản hỗ trợ có `RETURNING`; MySQL thường dùng chức năng lấy ID của phiên; Oracle có cơ chế `RETURNING ... INTO` tùy ngữ cảnh |
| `DEFAULT` tại vị trí một giá trị | Có | Mức hỗ trợ và các ràng buộc khác nhau theo dialect |
| Kiểu Boolean | `BOOLEAN` với `TRUE`/`FALSE` | SQL Server thường dùng `BIT`; một số hệ ánh xạ Boolean vào kiểu số |
| Literal ngày | `DATE 'YYYY-MM-DD'` | Không phải dialect nào cũng dùng cùng cú pháp ép kiểu literal |
| Xử lý trùng khóa | Lỗi theo mặc định, có `ON CONFLICT` | MySQL có `ON DUPLICATE KEY UPDATE`; SQL Server có các mô hình xử lý xung đột riêng |

### 15.1. MySQL: AUTO_INCREMENT

Ví dụ **minh họa MySQL**, giả sử đã có bảng:

~~~sql
CREATE TABLE demo_mysql_products (
    product_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    sku VARCHAR(30) NOT NULL UNIQUE,
    product_name VARCHAR(100) NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL
);

INSERT INTO demo_mysql_products (sku, product_name, unit_price)
VALUES ('MY-001', 'MySQL căn bản', 99000.00);
~~~

Phần `INSERT ... (cột) VALUES (...)` vẫn tương tự. Khác biệt chủ yếu ở khai báo tự tăng `AUTO_INCREMENT` và cơ chế truy xuất ID sau chèn.

### 15.2. SQL Server: IDENTITY và OUTPUT

Giả sử bảng `dbo.Products` đã được tạo với các cột tương ứng, SQL Server có thể trả ID vừa chèn:

~~~sql
-- T-SQL minh hoa:
INSERT INTO dbo.Products (sku, product_name, unit_price)
OUTPUT INSERTED.product_id, INSERTED.sku
VALUES ('MS-001', N'Sách SQL Server', 99000.00);
~~~

Từ khóa `OUTPUT INSERTED...` đặt ở vị trí khác với `RETURNING` của PostgreSQL. Tiền tố `N'...'` trong T-SQL là cú pháp literal Unicode truyền thống, phù hợp khi làm việc với nội dung tiếng Việt.

### 15.3. SQLite: khóa và kiểu dữ liệu có quy tắc riêng

SQLite có những khác biệt về hệ kiểu và rowid. Ví dụ dùng `INTEGER PRIMARY KEY`:

~~~sql
CREATE TABLE demo_sqlite_products (
    product_id INTEGER PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    unit_price NUMERIC NOT NULL
);

INSERT INTO demo_sqlite_products (sku, product_name, unit_price)
VALUES ('SL-001', 'SQLite cơ bản', 99000.00);
~~~

Không suy luận rằng mọi bảng SQLite đều có cách tự sinh khóa giống `GENERATED ALWAYS AS IDENTITY` của PostgreSQL. Khi chuyển hệ, cần kiểm tra cả **khai báo schema** và **cơ chế nhận ID**, dù cú pháp `INSERT` cơ bản gần như không thay đổi.

### 15.4. Oracle: cấu trúc INSERT cơ bản

Oracle cũng dùng cấu trúc:

~~~sql
-- Vi du minh hoa, gia dinh bang PRODUCTS va cac cot da ton tai:
INSERT INTO products (sku, product_name, unit_price)
VALUES ('OR-001', 'Oracle SQL', 99000.00);
~~~

Việc sinh khóa, kiểu ngày/giờ, xử lý chuỗi rỗng và các cú pháp `RETURNING` trong Oracle có thể khác PostgreSQL. Đáng chú ý, Oracle Database truyền thống xem chuỗi ký tự rỗng `''` như `NULL` đối với nhiều cột ký tự, nên các ví dụ phân biệt `''` với `NULL` của PostgreSQL **không thể áp dụng nguyên xi** mà không kiểm tra dialect.

## 16. Quy trình thêm một hàng trong thực tế

Với yêu cầu “thêm một sản phẩm mới”, một quy trình hợp lý là:

1. **Xác định bảng đích và ý nghĩa mỗi cột.** Không suy luận kiểu hay quy tắc chỉ từ tên gọi.
2. **Chọn danh sách cột ứng dụng thực sự cung cấp.** Không nhập giá trị cho identity hoặc timestamp tự sinh nếu không có lý do rõ ràng.
3. **Kiểm tra giá trị bắt buộc.** Những cột `NOT NULL` không có mặc định cần có giá trị hợp lệ.
4. **Ghép cột–giá trị theo đúng vị trí.** Đặc biệt chú ý những cột đều là chuỗi, dễ đảo mà database không phát hiện.
5. **Dùng tham số cho dữ liệu từ người dùng.** Không tự nối giá trị vào chuỗi SQL.
6. **Thực thi trong phạm vi giao dịch thích hợp.** Với thao tác cần nhiều bảng, thiết kế transaction có kiểm soát.
7. **Nhận kết quả đáng tin cậy.** Dùng `RETURNING` khi cần ID sinh ra; kiểm tra hoặc xử lý lỗi ràng buộc.
8. **Hiển thị trạng thái chính xác.** Chỉ báo đã thêm thành công sau khi database xác nhận; nếu có giao dịch tường minh, còn phải tính tới việc commit.

Một ví dụ đầy đủ cho **một hàng** trong PostgreSQL:

~~~sql
INSERT INTO lab_ins261_products (
    sku,
    product_name,
    unit_price,
    stock_qty,
    category,
    available
)
VALUES (
    'BK-FINAL-024',
    'SQL cho người mới',
    135000.00,
    7,
    'BOOK',
    TRUE
)
RETURNING
    product_id,
    sku,
    product_name,
    unit_price,
    stock_qty,
    category,
    created_at;
~~~

Đoạn lệnh cho thấy các nguyên tắc cốt lõi: **liệt kê cột rõ ràng**, **một bộ giá trị đúng vị trí**, **bỏ qua các cột tự sinh/mặc định**, và **lấy ngay thông tin của hàng vừa thêm**.

## 17. Những lỗi thường gặp khi INSERT một hàng

| Lỗi hoặc suy luận | Vì sao sai / điều gì xảy ra | Hướng sửa |
| --- | --- | --- |
| Không viết danh sách cột và đoán thứ tự giá trị | Dễ lệch với cấu trúc bảng, nhất là khi thêm cột | Viết `INSERT INTO t (c1, c2, ...) VALUES (...)` |
| Số cột khác số giá trị | SQL không thể ghép từng cột với từng biểu thức | Đếm và khớp từng vị trí |
| Đảo hai giá trị cùng kiểu chuỗi | Database có thể nhận nhưng dữ liệu sai ngữ nghĩa | Đặt tên cột rõ, kiểm tra mapping trước khi thực thi |
| Bỏ cột `NOT NULL` không có `DEFAULT` | Database không có giá trị hợp lệ để lưu | Cung cấp dữ liệu bắt buộc hoặc thay đổi schema theo nghiệp vụ |
| Truyền `NULL` vào cột có `DEFAULT 0` và `NOT NULL` | `NULL` không có nghĩa là áp dụng mặc định | Bỏ cột hoặc dùng `DEFAULT` |
| Cho rằng cột cho phép `NULL` thì luôn phải liệt kê với `NULL` | Có thể đơn giản bỏ cột nếu phù hợp ngữ nghĩa | Dùng danh sách cột tối thiểu theo yêu cầu |
| Tự nhập `product_id` vào `GENERATED ALWAYS AS IDENTITY` | Mâu thuẫn với quy tắc sinh khóa | Bỏ ID khỏi danh sách cột, dùng `RETURNING` để nhận ID |
| Chèn SKU trùng | Vi phạm `UNIQUE` | Xác định đúng là thêm mới hay cập nhật; xử lý xung đột theo quy tắc |
| Chèn giá âm hoặc tồn âm | Vi phạm `CHECK` | Kiểm tra giá trị nghiệp vụ, không tắt ràng buộc |
| Viết `'120,000'` rồi kỳ vọng lưu số 120000 | Chuỗi có dấu phẩy có thể không chuyển được thành `NUMERIC` | Dùng literal số `120000.00` hoặc tham số số |
| Tên có dấu `'` nhưng ghép chuỗi SQL trực tiếp | Có thể lỗi cú pháp và gây rủi ro SQL injection | Dùng prepared statement; nếu tự viết literal thì escape đúng |
| Dùng `= NULL` để kiểm tra cột thiếu | So sánh thông thường với `NULL` cho UNKNOWN | Dùng `IS NULL` / `IS NOT NULL` |
| Dùng `SELECT MAX(id)` để lấy ID vừa chèn | Có thể lấy ID của phiên khác | Dùng `RETURNING` hoặc API nhận generated keys phù hợp dialect |
| Cho rằng `INSERT` thành công là luôn đã commit | Có thể vẫn đang trong transaction chưa commit | Xem chế độ transaction, xử lý `COMMIT`/`ROLLBACK` đúng |
| Chạy hàng loạt ví dụ lỗi trong transaction PostgreSQL | Một lỗi có thể làm transaction ở trạng thái aborted | Chạy riêng ví dụ, rollback hoặc dùng savepoint phù hợp |
| Cho rằng `ROLLBACK` phục hồi luôn giá trị sequence | Sequence có thể có khoảng trống | Không phụ thuộc vào ID liên tục |
| Sao chép cú pháp `RETURNING` sang mọi hệ | Dialect có cơ chế trả ID khác | Dùng cú pháp hoặc API tương ứng với hệ quản trị |

## 18. Bài tập thực hành có đáp án

Các bài dưới đây dùng bảng `lab_ins261_products` ở mục 2. Mỗi mã SKU được thiết kế **khác nhau** để có thể thử tuần tự **một lần trên bảng mới**. Nếu chạy lại cùng một bài, `UNIQUE(sku)` sẽ chặn lần chèn thứ hai; đó là hành vi đúng.

### Bài 1 — Thêm một sách chỉ bằng ba cột bắt buộc

**Yêu cầu:** thêm sản phẩm mã `EX-BK-001`, tên “Giải bài tập SQL”, giá `89000.00`. Không cung cấp số lượng tồn, danh mục và trạng thái.

**Đáp án:**

~~~sql
INSERT INTO lab_ins261_products (
    sku,
    product_name,
    unit_price
)
VALUES (
    'EX-BK-001',
    'Giải bài tập SQL',
    89000.00
);
~~~

Vì bỏ các cột có mặc định, hàng mới nhận `stock_qty = 0`, `category = 'OTHER'` và `available = TRUE`. `note` nhận `NULL`, `product_id` tự sinh.

### Bài 2 — Danh sách cột không theo thứ tự CREATE TABLE

**Yêu cầu:** thêm mã `EX-ST-002`, tên “Bút chì”, giá `7000.00` và tồn `50`, nhưng viết `product_name` trước `sku` trong danh sách.

**Đáp án:**

~~~sql
INSERT INTO lab_ins261_products (
    product_name,
    stock_qty,
    sku,
    unit_price
)
VALUES (
    'Bút chì',
    50,
    'EX-ST-002',
    7000.00
);
~~~

Giá trị vẫn được lưu đúng vì các biểu thức trong `VALUES` khớp với **thứ tự cột trong `INSERT`**, không phụ thuộc thứ tự ở `CREATE TABLE`.

### Bài 3 — Dùng DEFAULT tường minh

**Yêu cầu:** thêm mã `EX-BK-003`, tên “Bộ câu hỏi SQL”, giá 125000; để số lượng tồn và danh mục theo mặc định bằng từ khóa `DEFAULT`.

**Đáp án:**

~~~sql
INSERT INTO lab_ins261_products (
    sku,
    product_name,
    unit_price,
    stock_qty,
    category
)
VALUES (
    'EX-BK-003',
    'Bộ câu hỏi SQL',
    125000.00,
    DEFAULT,
    DEFAULT
);
~~~

Kết quả `stock_qty = 0` và `category = 'OTHER'`.

### Bài 4 — Giá 0 và trạng thái FALSE

**Yêu cầu:** thêm sản phẩm mẫu mã `EX-FREE-004`, tên “Tài liệu miễn phí”, giá 0, tồn 0, trạng thái không khả dụng.

**Đáp án:**

~~~sql
INSERT INTO lab_ins261_products (
    sku,
    product_name,
    unit_price,
    stock_qty,
    available
)
VALUES (
    'EX-FREE-004',
    'Tài liệu miễn phí',
    0.00,
    0,
    FALSE
);
~~~

`0` và `FALSE` đều là các giá trị **được cung cấp tường minh** và hợp lệ với bảng mẫu; chúng không đồng nghĩa `NULL`.

### Bài 5 — Thêm ngày cụ thể

**Yêu cầu:** thêm sách `EX-BK-005` với giá 150000 và ngày giới thiệu là **01/05/2026**. Dùng literal ngày rõ kiểu.

**Đáp án:**

~~~sql
INSERT INTO lab_ins261_products (
    sku,
    product_name,
    unit_price,
    introduced_on
)
VALUES (
    'EX-BK-005',
    'Nền tảng SQL',
    150000.00,
    DATE '2026-05-01'
);
~~~

Ngày được cung cấp rõ ràng nên **không dùng `CURRENT_DATE` mặc định** cho cột `introduced_on` của hàng này.

### Bài 6 — Ghi chú chứa dấu nháy đơn

**Yêu cầu:** thêm sản phẩm `EX-BK-006`, tên “O'Reilly SQL”, giá 165000. Hãy viết literal chuỗi hợp lệ.

**Đáp án:**

~~~sql
INSERT INTO lab_ins261_products (
    sku,
    product_name,
    unit_price
)
VALUES (
    'EX-BK-006',
    'O''Reilly SQL',
    165000.00
);
~~~

Hai dấu nháy đơn liên tiếp bên trong literal được lưu thành **một dấu nháy đơn**. Với đầu vào thật từ người dùng, **prepared statement** vẫn là lựa chọn cần ưu tiên.

### Bài 7 — RETURNING ID vừa tạo

**Yêu cầu:** thêm sản phẩm `EX-BK-007`, tên “PostgreSQL qua tình huống”, giá 180000 và ngay lập tức nhận ID cùng trạng thái.

**Đáp án:**

~~~sql
INSERT INTO lab_ins261_products (
    sku,
    product_name,
    unit_price
)
VALUES (
    'EX-BK-007',
    'PostgreSQL qua tình huống',
    180000.00
)
RETURNING
    product_id,
    sku,
    available,
    created_at;
~~~

`product_id` được database sinh; `available` mặc định TRUE; `created_at` được database điền theo mặc định. Không cần truy vấn `MAX(product_id)`.

### Bài 8 — Giải thích lỗi thiếu cột bắt buộc

Một bạn viết:

~~~sql
-- Khong chay nhu mot bai INSERT hop le.
INSERT INTO lab_ins261_products (
    sku,
    product_name
)
VALUES (
    'EX-ERR-008',
    'Sách thiếu giá'
);
~~~

**Câu hỏi:** có thêm được hàng không? Vì sao?

**Đáp án:** **không**. `unit_price` được khai báo `NOT NULL` mà không có `DEFAULT`, nên việc không cung cấp giá làm hàng vi phạm ràng buộc. Cần thêm `unit_price` và một giá hợp lệ trong danh sách cột và `VALUES`.

### Bài 9 — Giải thích lỗi do NULL và DEFAULT

Một bạn viết:

~~~sql
-- Khong chay nhu mot bai INSERT hop le.
INSERT INTO lab_ins261_products (
    sku, product_name, unit_price, stock_qty
)
VALUES (
    'EX-ERR-009', 'Sản phẩm thiếu tồn', 55000.00, NULL
);
~~~

**Câu hỏi:** tại sao bảng có `stock_qty DEFAULT 0` mà vẫn lỗi?

**Đáp án:** `NULL` là một giá trị được **cung cấp tường minh**; nó không ra lệnh áp dụng mặc định. Cột `stock_qty` đồng thời có `NOT NULL` nên giá trị `NULL` bị từ chối. Có thể bỏ `stock_qty` khỏi danh sách hoặc ghi `DEFAULT` tại vị trí tương ứng.

### Bài 10 — Sửa lỗi lệch cột và giá trị

Một câu sai:

~~~sql
-- Sai do thieu mot gia tri.
INSERT INTO lab_ins261_products (
    sku, product_name, unit_price
)
VALUES (
    'EX-ERR-010', 'Bài thực hành'
);
~~~

**Yêu cầu:** sửa thành câu thêm một hàng với giá 64000.

**Đáp án:**

~~~sql
INSERT INTO lab_ins261_products (
    sku, product_name, unit_price
)
VALUES (
    'EX-BK-010', 'Bài thực hành', 64000.00
);
~~~

Ba cột tương ứng đúng ba biểu thức. Một câu `INSERT` với danh sách cột không thể bỏ trống vị trí giá trị bắt buộc mà không sử dụng cú pháp hợp lệ như `DEFAULT` khi cột có mặc định thích hợp.

### Bài 11 — Thử chèn trong transaction rồi hủy

**Yêu cầu:** thêm thử sản phẩm `EX-ROLLBACK-011`, kiểm tra nó tồn tại trong transaction, rồi hủy thay đổi.

**Đáp án:**

~~~sql
BEGIN;

INSERT INTO lab_ins261_products (
    sku, product_name, unit_price
)
VALUES (
    'EX-ROLLBACK-011', 'Sản phẩm thử', 55000.00
);

SELECT sku, product_name
FROM lab_ins261_products
WHERE sku = 'EX-ROLLBACK-011';

ROLLBACK;

SELECT sku
FROM lab_ins261_products
WHERE sku = 'EX-ROLLBACK-011';
~~~

Trong transaction, lần `SELECT` đầu có thể thấy một hàng mới. Sau `ROLLBACK`, lần `SELECT` thứ hai không tìm thấy SKU đó, nếu không có phiên khác thêm cùng SKU. Identity có thể đã tiêu thụ một giá trị số dù hàng bị rollback.

### Bài 12 — Viết lệnh INSERT tối thiểu đúng yêu cầu

**Yêu cầu:** thêm sản phẩm có mã `EX-BK-012`, tên “Tổng hợp SQL”, giá 175000, tồn 3, danh mục BOOK; còn `available` và thời gian để mặc định. Câu lệnh phải **chèn đúng một hàng**, có danh sách cột rõ ràng.

**Đáp án:**

~~~sql
INSERT INTO lab_ins261_products (
    sku,
    product_name,
    unit_price,
    stock_qty,
    category
)
VALUES (
    'EX-BK-012',
    'Tổng hợp SQL',
    175000.00,
    3,
    'BOOK'
);
~~~

Các giá trị **đúng vị trí**, cột `available` nhận mặc định `TRUE`, `created_at` do database điền, `product_id` được tự sinh. Đây là mẫu áp dụng trực tiếp cho thao tác nhập một sản phẩm từ form quản trị.

## 19. Ghi nhớ

| Khi viết một lệnh INSERT | Cách làm đúng |
| --- | --- |
| Cần thêm **một hàng** | `INSERT INTO bảng (c1, c2, ...) VALUES (v1, v2, ...);` |
| Muốn câu SQL rõ nghĩa | **Luôn ưu tiên liệt kê danh sách cột** |
| Cần ánh xạ giá trị | `v1` cho `c1`, `v2` cho `c2`..., khớp **thứ tự và số lượng** |
| Cột có `DEFAULT` | Có thể **bỏ cột** hoặc ghi `DEFAULT` trong `VALUES` |
| Cột `NOT NULL` không có default | Phải cung cấp **giá trị hợp lệ** |
| Cột cho phép thiếu | Có thể lưu `NULL` khi phù hợp nghiệp vụ |
| Khóa identity tự sinh | Thường **không đưa ID vào danh sách cột** |
| Cần ID hoặc giá trị thật vừa lưu | PostgreSQL: `INSERT ... RETURNING ...` |
| Giá trị là chuỗi | Viết literal `'...'`; từ ứng dụng hãy dùng tham số |
| Giá trị số/ngày/Boolean | Dùng kiểu dữ liệu và biểu thức SQL thích hợp |
| Lỗi vi phạm ràng buộc | Không tắt ràng buộc; sửa dữ liệu hoặc thiết kế theo nghiệp vụ |
| Thử lệnh mà không giữ kết quả | Dùng transaction và `ROLLBACK` phù hợp |
| Dữ liệu từ người dùng | Dùng **prepared statement**, không nối chuỗi SQL |

Mẫu cần nhớ:

~~~sql
INSERT INTO lab_ins261_products (
    sku,
    product_name,
    unit_price
)
VALUES (
    'BK-DEMO',
    'Tên sản phẩm',
    100000.00
)
RETURNING product_id, sku;
~~~

**Cốt lõi của bài:** danh sách cột quyết định **bạn đang chủ động ghi giá trị cho những trường nào**, còn danh sách `VALUES` cung cấp **một hàng giá trị khớp đúng vị trí**. Các cột còn lại do schema quyết định theo `DEFAULT`, `NULL` hoặc cơ chế sinh giá trị; đồng thời mọi giá trị phải qua các ràng buộc. Nắm chắc điều này sẽ giúp bạn thêm một hàng dữ liệu đúng, dễ kiểm tra và an toàn trước khi chuyển sang các dạng `INSERT` phức tạp hơn.
