# INSERT nhiều hàng và giới hạn cú pháp theo hệ quản trị

Khi thêm dữ liệu vào bảng SQL, ví dụ đầu tiên thường chỉ có **một dòng**:

```sql
INSERT INTO products (sku, product_name, price)
VALUES ('SKU-001', 'Mouse', 350.00);
```

Trong ứng dụng thực tế, người dùng lại có thể nhập hàng chục sản phẩm từ một biểu mẫu, hệ thống nhận hàng nghìn sự kiện qua hàng đợi hoặc chương trình cần chuyển toàn bộ dữ liệu từ bảng staging sang bảng đích. Gửi một câu `INSERT` riêng cho từng dòng không phải lúc nào cũng là lựa chọn tốt. SQL cho phép **thêm nhiều hàng trong một thao tác** bằng `INSERT ... VALUES (...), (...)`, `INSERT ... SELECT` hoặc các cơ chế bulk load của từng hệ quản trị.

Tuy nhiên, cú pháp và giới hạn **không giống nhau giữa các DBMS**. PostgreSQL, MySQL, SQL Server, SQLite đều hỗ trợ nhiều nhóm giá trị trong `VALUES`; Oracle ở các phiên bản cũ thường cần `INSERT ALL` hoặc `INSERT ... SELECT`, còn Oracle Database 23ai bổ sung cú pháp multi-row `VALUES`. SQL Server có giới hạn **1.000 nhóm giá trị** đối với `INSERT ... VALUES` trực tiếp, nhưng không áp dụng đúng giới hạn đó khi `VALUES` được dùng như một bảng dẫn xuất trong `FROM`. Ngoài giới hạn cú pháp, số tham số bind, kích thước câu lệnh, dung lượng gói mạng, transaction log và ràng buộc dữ liệu cũng quyết định kích thước lô thực tế.

Bài học giải thích cách viết đúng một lệnh chèn nhiều hàng, điều kiện áp dụng, khác biệt phương ngữ, xử lý lỗi, giao dịch và lựa chọn giữa multi-row insert, JDBC batching, `INSERT ... SELECT` và bulk loading.

> Các ví dụ hoàn chỉnh ban đầu sử dụng **PostgreSQL**. Những đoạn dành cho SQL Server, MySQL/MariaDB, Oracle và SQLite được đánh dấu phương ngữ riêng; chúng không nhất thiết chạy nguyên văn trên PostgreSQL. Tên cột, kiểu ID và cú pháp trả khóa sinh tự động cũng khác giữa các DBMS.

## 1. Ba mô hình thêm nhiều hàng cần phân biệt

| Mô hình | Ý tưởng | Dùng khi nào |
|---|---|---|
| `INSERT ... VALUES (r1), (r2), ...` | Ghi nhiều nhóm giá trị trong **một câu SQL** | Số dòng vừa phải, dữ liệu đã có trong ứng dụng |
| `INSERT ... SELECT ...` | Chèn kết quả của một truy vấn vào bảng đích | Chuyển đổi dữ liệu từ bảng nguồn/staging, lọc và chuẩn hóa bằng SQL |
| **Batch / bulk API** | Driver hoặc công cụ nạp nhiều hàng theo lô | Nhiều bản ghi từ ứng dụng/file, yêu cầu giảm round-trip hoặc nhập lớn |

Một JDBC batch gồm nhiều lời gọi `PreparedStatement.addBatch()` **không bảo đảm** được driver gửi thành đúng **một** câu SQL `INSERT ... VALUES`. Driver có thể gửi nhiều câu đã chuẩn bị, hoặc tối ưu bằng cách gộp một số hàng thành multi-row statement. Vì thế cần phân biệt:

- **Số hàng trong một câu SQL**.
- **Số câu SQL được gửi trong một lượt/batch của driver**.
- **Số câu lệnh nằm trong một giao dịch**.

Ba con số này có thể khác nhau. Khả năng rollback toàn bộ phụ thuộc **ranh giới giao dịch**, không chỉ phụ thuộc ứng dụng gọi `executeBatch()` một lần.

## 2. Dữ liệu mẫu cho phần thực hành PostgreSQL

Ta dùng bảng sản phẩm có khóa sinh tự động, khóa nghiệp vụ `sku` duy nhất, các ràng buộc số lượng/giá và hai cột có giá trị mặc định.

```sql
-- PostgreSQL: các bảng TEMP tồn tại trong phiên đang kết nối.
CREATE TEMP TABLE demo_products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    price NUMERIC(12,2) NOT NULL CHECK (price >= 0),
    stock_qty INTEGER NOT NULL DEFAULT 0 CHECK (stock_qty >= 0),
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Ý nghĩa từng cột:

| Cột | Kiểu/ràng buộc | Quy tắc khi INSERT |
|---|---|---|
| `product_id` | `BIGINT IDENTITY`, PK | Để DBMS sinh; thông thường **không liệt kê** trong danh sách cột chèn |
| `sku` | `TEXT NOT NULL UNIQUE` | Bắt buộc có giá trị và không trùng |
| `product_name` | `TEXT NOT NULL` | Bắt buộc |
| `price` | `NUMERIC(12,2) CHECK(price >= 0)` | Bắt buộc, không âm |
| `stock_qty` | `INTEGER NOT NULL DEFAULT 0` | Có thể bỏ qua để dùng mặc định 0 |
| `note` | `TEXT` cho phép `NULL` | Không cung cấp thì nhận `NULL` nếu không có default khác |
| `created_at` | `TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP` | Có thể bỏ qua để DBMS tự ghi mốc thời gian |

Khi thực hành, có thể chèn ba sản phẩm ban đầu:

```sql
INSERT INTO demo_products (sku, product_name, price, stock_qty)
VALUES
    ('SKU-101', 'Mouse',      350.00, 10),
    ('SKU-102', 'Keyboard',   900.00,  5),
    ('SKU-103', 'USB Cable',  120.00,  0);

SELECT
    product_id, sku, product_name, price, stock_qty, note
FROM demo_products
ORDER BY sku;
```

Kết quả logic:

| sku | product_name | price | stock_qty | note |
|---|---|---:|---:|---|
| SKU-101 | Mouse | 350.00 | 10 | `NULL` |
| SKU-102 | Keyboard | 900.00 | 5 | `NULL` |
| SKU-103 | USB Cable | 120.00 | 0 | `NULL` |

Giá trị `product_id` do DBMS cấp, nên **không cố định các con số ID** trong đáp án. Kết quả thường cho thấy ba ID được sinh, nhưng thứ tự ID và khoảng cách giữa chúng không nên được dùng làm khóa liên kết với dữ liệu nguồn nếu ứng dụng cần chứng cứ chắc chắn.

## 3. Cú pháp cơ bản: INSERT một lần, nhiều bộ giá trị

Dạng tổng quát phổ biến:

```sql
INSERT INTO table_name (column_1, column_2, column_3)
VALUES
    (value_1a, value_2a, value_3a),
    (value_1b, value_2b, value_3b),
    (value_1c, value_2c, value_3c);
```

Các phần cần hiểu:

1. Danh sách `(column_1, column_2, column_3)` xác định **các cột đích**.
2. Mỗi cặp ngoặc `(value_1a, value_2a, value_3a)` là **một hàng sẽ chèn**.
3. Dấu phẩy giữa các cặp ngoặc phân tách **các hàng**, không phải chỉ các cột.
4. Dấu chấm phẩy ở cuối kết thúc **một câu INSERT**.
5. Mỗi nhóm giá trị phải có **đúng số biểu thức** tương ứng với danh sách cột.
6. Giá trị được gán **theo vị trí** trong danh sách cột, không theo tên hay kiểu suy đoán.

### 3.1. Ba hàng trong một câu khác ba câu INSERT

**Một câu, ba hàng:**

```sql
INSERT INTO demo_products (sku, product_name, price)
VALUES
    ('SKU-201', 'Notebook',  70.00),
    ('SKU-202', 'Pen',       15.00),
    ('SKU-203', 'Folder',    25.00);
```

**Ba câu, mỗi câu một hàng:**

```sql
INSERT INTO demo_products (sku, product_name, price)
VALUES ('SKU-301', 'Paper', 40.00);

INSERT INTO demo_products (sku, product_name, price)
VALUES ('SKU-302', 'Clip', 10.00);

INSERT INTO demo_products (sku, product_name, price)
VALUES ('SKU-303', 'Marker', 55.00);
```

Cả hai cách đều có thể đưa ba bản ghi vào bảng, nhưng khác **số câu SQL**, chi phí round-trip, nơi phát sinh lỗi và có thể cả phạm vi giao dịch khi đang bật autocommit.

Trong nhiều trường hợp, một multi-row `VALUES` giảm số lần gửi câu lệnh và chi phí xử lý so với từng `INSERT` đơn lẻ. Điều đó **không** có nghĩa ghép một triệu hàng vào một chuỗi SQL là luôn tối ưu.

### 3.2. Đúng và sai về số giá trị

```sql
-- ĐÚNG: mỗi hàng có ba giá trị cho ba cột.
INSERT INTO demo_products (sku, product_name, price)
VALUES
    ('SKU-A', 'Item A', 100),
    ('SKU-B', 'Item B', 200);
```

```sql
-- SAI: hàng thứ hai thiếu price.
INSERT INTO demo_products (sku, product_name, price)
VALUES
    ('SKU-A', 'Item A', 100),
    ('SKU-B', 'Item B');
```

```sql
-- SAI: đây là một hàng có sáu biểu thức, không phải hai hàng.
INSERT INTO demo_products (sku, product_name, price)
VALUES ('SKU-A', 'Item A', 100, 'SKU-B', 'Item B', 200);
```

Hệ quản trị không suy ra ranh giới hàng mới chỉ vì xuất hiện thêm ba giá trị. Muốn thêm một hàng, phải có **một nhóm ngoặc riêng**.

### 3.3. Thứ tự cột có thể thay đổi, nhưng vị trí phải khớp

```sql
INSERT INTO demo_products (price, product_name, sku)
VALUES
    (180.00, 'Cable 2m', 'SKU-X1'),
    (220.00, 'Adapter',  'SKU-X2');
```

Câu này hợp lệ vì các giá trị ở từng nhóm **theo thứ tự `price, product_name, sku`**, không theo thứ tự cột vật lý trong bảng.

Dạng sai về nghĩa có thể không báo lỗi:

```sql
-- Nếu cả hai cột là TEXT, sai vị trí có thể vẫn chạy.
INSERT INTO demo_products (sku, product_name, price)
VALUES ('Mouse', 'SKU-X3', 350);
```

Dữ liệu sẽ nhận `sku = 'Mouse'` và `product_name = 'SKU-X3'`, trái ý định. Vì vậy nên **liệt kê cột rõ ràng**, giữ danh sách cột ở một vị trí cố định và dùng tham số có tên/đối tượng ứng dụng để tạo giá trị đúng cột.

## 4. DEFAULT, NULL và cột được bỏ qua

Thêm nhiều hàng không thay đổi quy tắc cơ bản của `DEFAULT` và `NULL`.

### 4.1. Bỏ cột khỏi danh sách INSERT

```sql
INSERT INTO demo_products (sku, product_name, price)
VALUES
    ('SKU-D1', 'Sample D1',  99.00),
    ('SKU-D2', 'Sample D2', 149.00);
```

Ở cả hai hàng:

- `stock_qty` nhận mặc định **0**.
- `created_at` nhận biểu thức mặc định của DBMS.
- `note` nhận SQL `NULL` vì cho phép thiếu và không có default được định nghĩa.
- `product_id` được sinh theo identity.

Cột **`NOT NULL` không có default thích hợp** như `sku`, `product_name`, `price` không thể bị bỏ qua tùy tiện.

### 4.2. Dùng DEFAULT cho một ô cụ thể

Trong PostgreSQL, có thể chèn nhiều hàng mà một số ô yêu cầu giá trị mặc định:

```sql
INSERT INTO demo_products
    (sku, product_name, price, stock_qty, note)
VALUES
    ('SKU-D3', 'Sample D3', 199.00, DEFAULT, 'Initial import'),
    ('SKU-D4', 'Sample D4', 249.00,       8, NULL),
    ('SKU-D5', 'Sample D5', 299.00,       0, 'Stock verified');
```

Ba giá trị của `stock_qty` có ý nghĩa:

- `DEFAULT`: DBMS dùng giá trị mặc định (trong bảng mẫu là 0).
- `8`: ghi đúng số 8.
- `0`: ghi số 0 tường minh; trong ví dụ bằng mặc định về giá trị, nhưng không phải cú pháp áp dụng default.

Ở `note`, `NULL` là giá trị thiếu **tường minh**. Nếu một cột có default khác `NULL`, truyền `NULL` không đồng nghĩa yêu cầu default; nó có thể vi phạm `NOT NULL`.

### 4.3. DEFAULT VALUES thường tạo một hàng

PostgreSQL có cú pháp:

```sql
CREATE TEMP TABLE demo_import_marks (
    mark_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO demo_import_marks DEFAULT VALUES;
```

Câu trên tạo **một hàng dùng toàn bộ giá trị mặc định**. Không được suy từ `DEFAULT VALUES` rằng nó là cú pháp portable để sinh **nhiều** hàng mặc định ở mọi DBMS.

Đối với PostgreSQL, có thể viết nhiều nhóm `VALUES` mà cột đã chỉ định lấy `DEFAULT`:

```sql
-- Hai hàng; mark_id vẫn được tạo tự động.
INSERT INTO demo_import_marks (created_at)
VALUES (DEFAULT), (DEFAULT);
```

Nhưng nếu muốn nhiều hàng trong Oracle/SQL Server/MySQL/SQLite, hãy kiểm tra cú pháp tương ứng thay vì sao chép máy móc trường hợp này. Trong SQL Server, `DEFAULT` có những hạn chế khi dùng trực tiếp với cột `IDENTITY`.

### 4.4. Không dựa vào cùng timestamp để xác định thứ tự chèn

Nếu hai hàng nhận `created_at DEFAULT CURRENT_TIMESTAMP`, chúng **có thể có cùng giá trị timestamp**. Trên PostgreSQL, `CURRENT_TIMESTAMP` dùng mốc đầu giao dịch, nên ngay cả nhiều câu `INSERT` trong cùng giao dịch cũng có thể mang cùng timestamp.

Không dùng cột đó làm thứ tự duy nhất của các hàng trong một batch. Nếu cần thứ tự dữ liệu nhập, lưu `source_line_no` hoặc một khóa thứ tự có ngữ nghĩa rõ ràng.

## 5. Cột IDENTITY/AUTO_INCREMENT và nhiều hàng

Nhiều bảng sử dụng ID do DBMS tự sinh. Cách khai báo khác giữa các hệ:

| DBMS | Cơ chế ID phổ biến | Nguyên tắc khi chèn nhiều hàng |
|---|---|---|
| PostgreSQL | `GENERATED ... AS IDENTITY`, legacy `SERIAL` | Thường bỏ cột ID khỏi danh sách |
| MySQL/MariaDB | `AUTO_INCREMENT` | Thường bỏ cột ID hoặc để cơ chế tự sinh phù hợp |
| SQL Server | `IDENTITY(seed, increment)` | Thường bỏ cột identity; chèn ID tường minh cần cơ chế riêng |
| Oracle Database | Identity columns hoặc sequence | Bỏ cột identity nếu có default sinh; sequence theo quy tắc hệ |
| SQLite | `INTEGER PRIMARY KEY`, có thể thêm `AUTOINCREMENT` theo trường hợp | Bỏ cột khóa để engine cấp rowid/ID phù hợp |

Khi thêm nhiều hàng, **không đoán trước** rằng các ID sẽ là `100,101,102` liên tiếp, không bị ngắt và luôn khớp một-một theo thứ tự viết trong `VALUES`. Sequence/identity có thể có khoảng trống do rollback, xung đột, cache, trigger, nhiều giao dịch đồng thời hoặc chính sách cấp số của DBMS.

Nếu cần gắn ID đã sinh với hàng dữ liệu nguồn, hãy lưu khóa nghiệp vụ `sku` hoặc một correlation key tạm trong bản ghi và **nhận kết quả từ DBMS đúng cách**. Đừng tính ID thứ hai bằng công thức “ID đầu + 1” chỉ vì batch có hai dòng.

## 6. INSERT ... SELECT: chèn tất cả hàng từ một truy vấn

Không phải dữ liệu mới nào cũng được tạo từ các literal trong ứng dụng. Khi dữ liệu đã có trong bảng staging hoặc cần lọc/biến đổi bằng SQL, `INSERT ... SELECT` thường tự nhiên hơn.

Cú pháp chung:

```sql
INSERT INTO target_table (target_col_1, target_col_2, ...)
SELECT source_expression_1, source_expression_2, ...
FROM source_table
WHERE condition;
```

**Số cột và kiểu dữ liệu** ở kết quả `SELECT` phải phù hợp với danh sách cột đích, theo cùng quy tắc vị trí như `VALUES`. `SELECT` có thể trả 0, 1 hoặc hàng nghìn dòng.

### 6.1. Dựng bảng staging

```sql
CREATE TEMP TABLE demo_product_stage (
    source_line_no INTEGER PRIMARY KEY,
    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,
    price NUMERIC(12,2) NOT NULL,
    stock_qty INTEGER NOT NULL,
    eligible BOOLEAN NOT NULL
);

INSERT INTO demo_product_stage
    (source_line_no, sku, product_name, price, stock_qty, eligible)
VALUES
    (201, 'SKU-104', 'USB Hub',       500.00, 8, TRUE),
    (202, 'SKU-105', 'Monitor',      4200.00, 2, TRUE),
    (203, 'SKU-106', 'Debug Product',  10.00, 1, FALSE),
    (204, 'SKU-101', 'Old Mouse',     350.00, 7, TRUE);
```

Ở đây:

- Dòng 201 và 202 là sản phẩm mới hợp lệ.
- Dòng 203 được đánh dấu `eligible = FALSE` nên chưa nên nhập.
- Dòng 204 trùng `sku` với sản phẩm đã có trong bảng đích.

### 6.2. Chèn hàng hợp lệ chưa tồn tại

```sql
INSERT INTO demo_products (sku, product_name, price, stock_qty)
SELECT
    s.sku,
    s.product_name,
    s.price,
    s.stock_qty
FROM demo_product_stage AS s
WHERE s.eligible = TRUE
  AND NOT EXISTS (
      SELECT 1
      FROM demo_products AS p
      WHERE p.sku = s.sku
  );
```

Trên bộ dữ liệu mẫu và khi không có ghi đồng thời, dòng 201 và 202 được chèn; 203 bị loại vì không đủ điều kiện; 204 bị loại vì `sku` đã tồn tại.

**Nhưng `NOT EXISTS` không tự thay thế `UNIQUE` khi có cạnh tranh ghi.** Hai giao dịch có thể đồng thời cùng kết luận mã SKU chưa tồn tại rồi thử chèn. Ràng buộc `UNIQUE(sku)` tại bảng đích vẫn cần thiết và có thể kết hợp chiến lược xử lý xung đột của DBMS.

### 6.3. INSERT ... SELECT có thể trả 0 dòng

Nếu `SELECT` nguồn không trả hàng, `INSERT ... SELECT` thông thường không chèn gì. Điều này khác một câu `INSERT INTO ... DEFAULT VALUES`, vốn có thể sinh một hàng theo default.

```sql
-- PostgreSQL: không thêm hàng nào.
INSERT INTO demo_products (sku, product_name, price)
SELECT sku, product_name, price
FROM demo_product_stage
WHERE source_line_no = -1;
```

Điều này hữu ích khi dữ liệu nguồn chưa sẵn sàng; ứng dụng vẫn cần kiểm tra **số hàng thực sự được chèn** thay vì coi mọi câu INSERT chạy thành công đều thêm ít nhất một bản ghi.

### 6.4. ORDER BY trong INSERT ... SELECT không phải cam kết ID sinh

```sql
INSERT INTO demo_products (sku, product_name, price, stock_qty)
SELECT sku, product_name, price, stock_qty
FROM demo_product_stage
WHERE eligible
ORDER BY source_line_no;
```

`ORDER BY` có thể xác định thứ tự dòng kết quả đầu vào của `SELECT` theo quy tắc DBMS, nhưng **không nên xây hợp đồng rằng identity/sequence đã sinh sẽ ánh xạ vĩnh viễn theo số thứ tự ấy** trong mọi phương ngữ, phiên bản, trigger hoặc tình huống đồng thời.

Muốn đối soát, giữ `source_line_no` trong staging và dùng `sku`/correlation key, hoặc cơ chế trả về có mối liên kết xác định theo thiết kế.

## 7. Chèn kết quả CTE: dữ liệu được biến đổi ngay trong SQL

`WITH` có thể tổ chức dữ liệu staging và quy tắc chuẩn hóa trước khi chèn:

```sql
-- PostgreSQL
WITH normalized AS (
    SELECT
        TRIM(sku) AS sku,
        TRIM(product_name) AS product_name,
        price,
        stock_qty
    FROM demo_product_stage
    WHERE eligible = TRUE
)
INSERT INTO demo_products (sku, product_name, price, stock_qty)
SELECT
    sku, product_name, price, stock_qty
FROM normalized
ON CONFLICT (sku) DO NOTHING;
```

Đây vẫn là **một câu INSERT**, dù phần dữ liệu nguồn được định nghĩa bằng CTE. `ON CONFLICT (sku) DO NOTHING` là cú pháp PostgreSQL xử lý xung đột duy nhất, sẽ được giải thích kỹ hơn phía sau.

Đừng suy từ `WITH` rằng dữ liệu chắc chắn được tạo ra thành một bảng vật lý riêng rồi mới chèn. Bộ tối ưu có thể nội tuyến hoặc dùng tập trung gian theo cơ chế engine; cú pháp `WITH` chủ yếu giúp truy vấn dễ đọc.

## 8. Thêm nhiều hàng có nguyên tử không?

**Atomicity** (tính nguyên tử) có nghĩa thao tác có thể được coi là một đơn vị nhất quán về việc thành công/thất bại theo hợp đồng giao dịch của DBMS và storage engine.

Trong PostgreSQL, một câu `INSERT` thông thường là thao tác nguyên tử ở cấp câu lệnh: nếu một hàng trong `VALUES` vi phạm ràng buộc khiến câu lệnh thất bại, **những hàng khác từ cùng câu INSERT đó không được commit một phần**.

Ví dụ giả sử mã `SKU-101` đã tồn tại:

```sql
-- PostgreSQL: cả câu thất bại vì một hàng trùng UNIQUE.
INSERT INTO demo_products (sku, product_name, price)
VALUES
    ('SKU-NEW-1', 'New item', 50.00),
    ('SKU-101',   'Duplicate mouse', 350.00);
```

Câu này không có cơ chế xử lý trùng, nên `UNIQUE(sku)` báo lỗi. `SKU-NEW-1` **không được giữ lại như một hàng thành công riêng** của câu lệnh thất bại.

Tuy nhiên, không nên suy từ đây rằng:

- Một **JDBC batch** chứa nhiều câu INSERT tự động nguyên tử toàn bộ.
- Nhiều câu INSERT chạy với **autocommit bật** sẽ rollback cùng nhau.
- MySQL với mọi storage engine, mọi SQL mode và `INSERT IGNORE` đều có đúng hành vi PostgreSQL.
- IDENTITY/sequence sẽ không tăng hoặc không có khoảng trống khi câu lệnh rollback.

### 8.1. Nhiều câu INSERT trong một transaction

```sql
-- PostgreSQL
BEGIN;

INSERT INTO demo_products (sku, product_name, price)
VALUES ('SKU-T1', 'First batch item', 100.00);

INSERT INTO demo_products (sku, product_name, price)
VALUES ('SKU-T2', 'Second batch item', 200.00);

-- Nếu muốn giữ cả hai:
COMMIT;

-- Nếu cần hủy toàn bộ trước khi commit, dùng ROLLBACK
-- THAY CHO COMMIT, không chạy cả hai lệnh nối tiếp.
```

Nếu xảy ra lỗi trong giao dịch PostgreSQL, giao dịch thường đi vào trạng thái bị hủy cho tới khi `ROLLBACK` hoặc rollback tới savepoint phù hợp. Không tiếp tục giả định các lệnh sau sẽ hoạt động bình thường nếu chưa xử lý lỗi giao dịch.

### 8.2. Chèn theo lô và rollback

Nếu cần nhập 10.000 hàng theo 20 batch, mỗi batch 500 hàng:

- **Một transaction bao toàn bộ 20 batch:** lỗi chưa xử lý có thể khiến toàn bộ thao tác bị rollback.
- **Mỗi batch một transaction:** batch đã commit trước đó sẽ còn dữ liệu nếu batch sau thất bại.
- **Autocommit từng câu:** các câu thành công trước lỗi có thể đã được lưu.

Chọn ranh giới theo yêu cầu: nhập một file cần **all-or-nothing**, hay pipeline cho phép **tiến dần, có checkpoint và retry**. Cần hiểu chi phí transaction dài, khóa, log và ảnh hưởng tới các hệ khác.

### 8.3. Trigger, FK và CHECK vẫn hoạt động

Multi-row insert không bỏ qua:

- `PRIMARY KEY` và `UNIQUE`.
- `NOT NULL`.
- `CHECK`.
- `FOREIGN KEY`.
- Trigger và quy tắc nghiệp vụ tại DB.
- Các hạn chế về kiểu/độ dài trường.

Ví dụ, nếu một hàng có `stock_qty = -1`, ràng buộc `CHECK(stock_qty >= 0)` từ bảng mẫu sẽ làm câu chèn thất bại trong PostgreSQL (trừ khi hệ có logic điều chỉnh khác được định nghĩa rõ).

Dùng bulk API hoặc batching không nên được hiểu là bỏ qua tính toàn vẹn. Một số công cụ bulk có tùy chọn riêng cho kiểm tra ràng buộc/trigger; phải cấu hình theo yêu cầu thay vì hy sinh tính đúng để tăng tốc.

## 9. Xung đột khóa khi chèn nhiều hàng

Một batch nhập lại có thể chứa SKU đã tồn tại. Xử lý trùng là một **chính sách nghiệp vụ**, không phải đặc tính mặc định của cú pháp `VALUES`.

Những cách xử lý có thể là:

1. **Fail toàn bộ:** từ chối file/batch nếu có khóa trùng.
2. **Bỏ qua hàng trùng:** nhập các hàng mới, giữ nguyên hàng cũ.
3. **Cập nhật hàng đã có:** thực hiện *upsert* theo khóa.
4. **Đưa hàng lỗi vào bảng đối soát:** không tự chuyển giá trị.

### 9.1. PostgreSQL: ON CONFLICT DO NOTHING

```sql
INSERT INTO demo_products (sku, product_name, price, stock_qty)
VALUES
    ('SKU-101', 'Mouse imported again', 350.00, 10),
    ('SKU-901', 'New Charger',         480.00,  4)
ON CONFLICT (sku) DO NOTHING;
```

Nếu `SKU-101` đã có và `SKU-901` chưa có, PostgreSQL bỏ qua hàng xung đột và chèn hàng mới. **Số hàng được chèn thực tế có thể nhỏ hơn số hàng trong `VALUES`**.

`DO NOTHING` không phải công cụ che mọi lỗi: một hàng có kiểu dữ liệu sai hoặc vi phạm `CHECK`/`NOT NULL` không tự được bỏ qua chỉ vì bạn chọn xử lý xung đột khóa `sku`.

### 9.2. PostgreSQL: ON CONFLICT DO UPDATE

```sql
INSERT INTO demo_products (sku, product_name, price, stock_qty)
VALUES
    ('SKU-101', 'Mouse updated', 370.00, 12),
    ('SKU-902', 'Webcam',        890.00,  3)
ON CONFLICT (sku) DO UPDATE
SET product_name = EXCLUDED.product_name,
    price = EXCLUDED.price,
    stock_qty = EXCLUDED.stock_qty;
```

`EXCLUDED` trong PostgreSQL chỉ giá trị hàng **đang được đề xuất chèn**. Nếu khóa đã có, DBMS cập nhật những cột được chỉ định. Nếu chưa có, hàng được chèn bình thường.

**Bẫy quan trọng khi batch nguồn có khóa trùng nội bộ:** nếu cùng một câu `INSERT ... ON CONFLICT DO UPDATE` đề xuất hai hàng cùng khóa `sku` nhằm cập nhật **cùng một hàng đích hai lần**, PostgreSQL có thể báo lỗi cardinality thay vì tự chọn giá trị “cuối cùng”. Cần **khử trùng nguồn theo quy tắc rõ ràng trước khi upsert**, ví dụ giữ dòng có `source_line_no` lớn nhất.

Ví dụ dedup nguồn:

```sql
WITH ranked AS (
    SELECT
        s.*,
        ROW_NUMBER() OVER (
            PARTITION BY sku
            ORDER BY source_line_no DESC
        ) AS rn
    FROM demo_product_stage AS s
    WHERE eligible = TRUE
)
INSERT INTO demo_products (sku, product_name, price, stock_qty)
SELECT sku, product_name, price, stock_qty
FROM ranked
WHERE rn = 1
ON CONFLICT (sku) DO UPDATE
SET product_name = EXCLUDED.product_name,
    price = EXCLUDED.price,
    stock_qty = EXCLUDED.stock_qty;
```

**Quy tắc “dòng có source_line_no lớn nhất thắng” chỉ là một ví dụ.** Trong sản xuất có thể cần phiên bản nguồn, timestamp có kiểm soát hoặc ưu tiên hệ thống. Không tự cho rằng thứ tự file là đúng với mọi bản ghi trùng.

### 9.3. Xử lý xung đột khác theo DBMS

| DBMS | Cơ chế thường gặp | Cảnh báo |
|---|---|---|
| PostgreSQL | `ON CONFLICT (...) DO NOTHING/DO UPDATE` | Khóa xung đột cần có ràng buộc/index phù hợp |
| SQLite | `ON CONFLICT DO ...` ở phiên bản hỗ trợ, hoặc `INSERT OR IGNORE` | Chính sách conflict có thể áp nhiều loại ràng buộc; không bỏ qua mọi lỗi |
| MySQL/MariaDB | `INSERT IGNORE`, `ON DUPLICATE KEY UPDATE` | `IGNORE` có thể chuyển lỗi thành cảnh báo/điều chỉnh dữ liệu; không chỉ bỏ duplicate |
| SQL Server | Xử lý `UNIQUE`; mẫu kiểm tra/chèn có khóa, hoặc cơ chế merge/upsert thiết kế cẩn thận | Không suy `MERGE` luôn là giải pháp concurrency an toàn mặc định |
| Oracle | `MERGE` hoặc logic bắt ngoại lệ khóa trùng/đồng bộ dữ liệu | Cú pháp, khóa và ngữ nghĩa theo phiên bản |

Không đồng nhất `INSERT IGNORE` với `ON CONFLICT DO NOTHING` hay `REPLACE` với `DO UPDATE`. Ví dụ MySQL `REPLACE` có thể **xóa hàng cũ rồi chèn hàng mới**, ảnh hưởng khóa ngoại, trigger và ID; không phải một bản cập nhật bình thường.

## 10. RETURNING, OUTPUT và ID sinh ra khi chèn nhiều hàng

Ứng dụng thường muốn nhận những hàng vừa được chèn mà không chạy một truy vấn riêng.

### 10.1. PostgreSQL: RETURNING

```sql
INSERT INTO demo_products (sku, product_name, price)
VALUES
    ('SKU-R1', 'Router', 1500.00),
    ('SKU-R2', 'Switch', 2100.00)
RETURNING product_id, sku, created_at;
```

`RETURNING` trả dữ liệu của những hàng được tác động theo ngữ nghĩa PostgreSQL. Với ví dụ này, nó cho biết ID do DBMS sinh và SKU tương ứng.

**Không dựa vào thứ tự các dòng `RETURNING` để suy ID tương ứng vị trí thứ nhất/thứ hai trong `VALUES`.** Nếu cần ghép về dữ liệu ứng dụng, hãy ghép theo `sku`/correlation key hoặc theo hợp đồng API thích hợp. Khi có `ON CONFLICT DO NOTHING`, số hàng `RETURNING` có thể ít hơn số hàng đề xuất chèn.

### 10.2. SQL Server: OUTPUT INSERTED

T-SQL dùng `OUTPUT INSERTED.column`:

```sql
-- SQL Server: giả sử dbo.products có IDENTITY.
INSERT INTO dbo.products (sku, product_name, price)
OUTPUT INSERTED.product_id, INSERTED.sku
VALUES
    ('SKU-R1', N'Router', 1500.00),
    ('SKU-R2', N'Switch', 2100.00);
```

`OUTPUT` có quy tắc/giới hạn riêng khi bảng có trigger và các kiểu dữ liệu đặc biệt. Không hiểu nó như cú pháp PostgreSQL `RETURNING`. Quan trọng hơn, **không giả định thứ tự hàng OUTPUT khớp thứ tự hàng đầu vào** khi cần đối soát.

### 10.3. MySQL/MariaDB và SQLite

MySQL có `LAST_INSERT_ID()` và API driver liên quan đến ID tự tăng. Nhưng nó **không phải danh sách bảo đảm đầy đủ ID theo từng hàng của mọi multi-row insert**. Cách driver trả khóa sinh trong batching phụ thuộc phiên bản/driver/kiểu INSERT.

SQLite hiện đại (từ 3.35.0) hỗ trợ `RETURNING`:

```sql
-- SQLite 3.35.0+, giả sử products có cột tương ứng.
INSERT INTO products (sku, product_name, price)
VALUES ('SKU-R1', 'Router', 1500),
       ('SKU-R2', 'Switch', 2100)
RETURNING product_id, sku;
```

MariaDB cũng có tính năng `INSERT ... RETURNING` ở các phiên bản phù hợp. Không mặc định **MySQL** hỗ trợ cùng cú pháp `RETURNING` như PostgreSQL/MariaDB. Hãy chọn API/statement của đúng DBMS và **kiểm tra số hàng trả về**.

## 11. PostgreSQL: cú pháp nhiều hàng và giới hạn thực tế

Trên PostgreSQL, dạng phổ biến là:

```sql
INSERT INTO products (sku, product_name, price)
VALUES
    ('SKU-1', 'Mouse', 350),
    ('SKU-2', 'Keyboard', 900),
    ('SKU-3', 'Cable', 120);
```

PostgreSQL hỗ trợ nhiều nhóm `VALUES`, `INSERT ... SELECT`, `DEFAULT` trong một nhóm, `RETURNING` và `ON CONFLICT`. Tuy nhiên, **không nên suy rằng có thể viết vô hạn hàng trong một statement**.

Những giới hạn cần cân nhắc:

- **Số tham số bind** mà giao thức và driver hỗ trợ cho một prepared statement.
- **Chiều dài câu SQL và dữ liệu** gửi đến server.
- Chi phí phân tích cú pháp, lập kế hoạch và cấp phát bộ nhớ khi tạo câu `VALUES` rất lớn.
- Dung lượng dữ liệu/transaction log, khóa, index updates và trigger.
- Độ dài transaction và rủi ro rollback khối dữ liệu lớn.
- Mức độ hiệu quả khi dùng `COPY` thay vì hàng nghìn nhóm `VALUES`.

Với nhiều hàng từ file, `COPY FROM STDIN` hoặc cơ chế streaming/bulk của thư viện PostgreSQL thường phù hợp hơn việc nối hàng triệu literal thành một chuỗi SQL.

### 11.1. PostgreSQL COPY không phải INSERT ... VALUES

`COPY` là một cơ chế nạp theo dòng/luồng dữ liệu, có cú pháp và quyền truy cập riêng. Ví dụ về ý tưởng:

```sql
-- PostgreSQL; đây là mẫu minh họa đường dẫn file phía server
-- và cần quyền/quy trình phù hợp, không phải thao tác cần chạy.
COPY products (sku, product_name, price)
FROM '/path/on/database/server/products.csv'
WITH (FORMAT csv, HEADER true);
```

`COPY FROM 'file'` đọc file ở phía server và có yêu cầu quyền/đường dẫn riêng. Ứng dụng thường ưu tiên **`COPY FROM STDIN`** qua driver để stream dữ liệu từ client, tránh giả định server có thể đọc đường dẫn máy người dùng. Kiểm soát định dạng, escape, encoding và ràng buộc dữ liệu trước khi nhập.

## 12. MySQL và MariaDB: multi-row VALUES

MySQL/MariaDB hỗ trợ cú pháp cơ bản:

```sql
-- MySQL / MariaDB
INSERT INTO products (sku, product_name, price)
VALUES
    ('SKU-1', 'Mouse', 350.00),
    ('SKU-2', 'Keyboard', 900.00),
    ('SKU-3', 'Cable', 120.00);
```

MySQL còn có dạng `INSERT ... SET`, thường phục vụ **một hàng**:

```sql
-- MySQL: ví dụ dạng SET cho một hàng.
INSERT INTO products
SET sku = 'SKU-4',
    product_name = 'Adapter',
    price = 250.00;
```

Không nên đổi `VALUES` nhiều nhóm thành một danh sách `SET` rồi mong mỗi bộ assignment tự thành một hàng. MySQL có các dạng `VALUE`/`VALUES` và row constructor theo phiên bản; dùng `VALUES (...), (...)` thông thường để dễ đọc và chuyển DBMS hơn.

### 12.1. Giới hạn kích thước câu lệnh và max_allowed_packet

MySQL chịu ảnh hưởng của cấu hình **`max_allowed_packet`**, giới hạn kích thước gói/thông điệp được nhận và một số chuỗi trung gian. Một câu `INSERT` có quá nhiều giá trị hoặc giá trị văn bản/BLOB lớn có thể vượt giới hạn, bị từ chối hoặc làm kết nối gặp sự cố tùy tình huống.

Đừng hiểu “không thấy giới hạn 1.000 hàng như SQL Server” là có thể viết một câu hàng trăm MB tùy ý. Kích thước lô còn chịu ảnh hưởng mạng, SQL parser, driver, server memory và transaction log.

### 12.2. INSERT IGNORE có thể làm kết quả khác kỳ vọng

```sql
-- MySQL / MariaDB: ví dụ tùy chính sách nghiệp vụ.
INSERT IGNORE INTO products (sku, product_name, price)
VALUES
    ('SKU-1', 'Existing item', 350),
    ('SKU-5', 'New item', 750);
```

Ở những trường hợp trùng khóa, `IGNORE` có thể bỏ qua hàng. Nhưng MySQL còn có khả năng **biến một số lỗi dữ liệu thành cảnh báo và điều chỉnh giá trị** theo SQL mode/engine. Nếu dữ liệu có giá, ngày hoặc số lượng không hợp lệ, không nên dùng `IGNORE` như “bỏ qua duplicate an toàn tuyệt đối”.

Kiểm tra số hàng thực sự được chèn, cảnh báo và các trường hợp dữ liệu bị điều chỉnh. Với hệ thống quan trọng, cần báo cáo hàng từ chối và nguyên nhân thay vì cho rằng mỗi hàng trong `VALUES` đã được ghi đúng.

### 12.3. ON DUPLICATE KEY UPDATE

```sql
-- MySQL / MariaDB: minh họa một chính sách cập nhật cố định.
INSERT INTO products (sku, product_name, price)
VALUES
    ('SKU-1', 'Mouse updated', 370),
    ('SKU-5', 'Webcam', 850)
ON DUPLICATE KEY UPDATE
    product_name = 'Updated by import';
```

Đây là **mẫu minh họa cú pháp**, không phải một chiến lược upsert đầy đủ vì mọi hàng xung đột nhận cùng chuỗi. Ứng dụng thực tế cần sử dụng biểu thức cập nhật theo giá trị hàng đề xuất chèn và phiên bản MySQL/MariaDB cụ thể.

Khác PostgreSQL `ON CONFLICT (sku)`, cơ chế `ON DUPLICATE KEY UPDATE` có thể phản ứng với các xung đột trên những unique index khác của cùng bảng. Khi bảng có nhiều ràng buộc duy nhất, phải kiểm tra hàng nào được cập nhật và ý nghĩa nghiệp vụ. Không ghép dữ liệu khách/tổ chức sai chỉ vì một unique key phụ cũng trùng.

### 12.4. Bulk load MySQL/MariaDB

Đối với file lớn, dùng `LOAD DATA`/`LOAD DATA LOCAL INFILE` trong môi trường được phép và cấu hình an toàn thay vì tạo một câu SQL khổng lồ. Quyền file, chính sách `LOCAL`, escape CSV, encoding, chế độ strict và cách xử lý dòng sai cần được quản lý theo triển khai thực tế.

## 13. SQL Server: giới hạn 1.000 hàng của INSERT ... VALUES

SQL Server (T-SQL) hỗ trợ table value constructor:

```sql
-- SQL Server
INSERT INTO dbo.products (sku, product_name, price)
VALUES
    ('SKU-1', N'Mouse', 350.00),
    ('SKU-2', N'Keyboard', 900.00),
    ('SKU-3', N'Cable', 120.00);
```

**Giới hạn quan trọng:** khi dùng `VALUES` **trực tiếp** làm phần của `INSERT ... VALUES`, SQL Server cho phép **tối đa 1.000 hàng** trong một constructor. Nếu vượt ngưỡng, SQL Server báo lỗi (thường là lỗi 10738). Giới hạn này **không** phải “mỗi bảng chỉ chèn được 1.000 hàng” và cũng **không** phải “mỗi transaction chỉ được có 1.000 hàng”.

### 13.1. Hơn 1.000 hàng: tách thành nhiều INSERT

Ví dụ ý tưởng:

```sql
-- SQL Server: mỗi statement trực tiếp phải <= 1000 nhóm VALUES.
BEGIN TRANSACTION;

INSERT INTO dbo.products (sku, product_name, price)
VALUES ('SKU-A', N'Item A', 100),
       ('SKU-B', N'Item B', 200);
-- ... các batch khác, mỗi batch không quá 1000 hàng ...

INSERT INTO dbo.products (sku, product_name, price)
VALUES ('SKU-C', N'Item C', 300),
       ('SKU-D', N'Item D', 400);

COMMIT TRANSACTION;
```

Trong thực tế nên có khối `TRY/CATCH` và `ROLLBACK` khi lỗi, thay vì trông chờ script đơn giản ở trên tự xử lý mọi tình huống. Đặt nhiều statement trong một transaction giúp thiết kế phạm vi commit, nhưng cũng kéo theo chi phí khóa và log tương ứng.

### 13.2. Table value constructor trong derived table không có giới hạn 1.000 hàng cùng loại

SQL Server có điểm dễ nhầm: `VALUES` dùng **trong `FROM` như một bảng dẫn xuất** không chịu **giới hạn 1.000 hàng áp dụng cho direct INSERT ... VALUES**.

```sql
-- SQL Server: đây là INSERT ... SELECT FROM (VALUES ...).
INSERT INTO dbo.products (sku, product_name, price)
SELECT src.sku, src.product_name, src.price
FROM (
    VALUES
        ('SKU-1', N'Mouse',    CAST(350.00 AS DECIMAL(12,2))),
        ('SKU-2', N'Keyboard', CAST(900.00 AS DECIMAL(12,2))),
        ('SKU-3', N'Cable',    CAST(120.00 AS DECIMAL(12,2)))
) AS src(sku, product_name, price);
```

Dạng này có thể chứa hơn 1.000 hàng trong bảng dẫn xuất theo giới hạn cú pháp được Microsoft mô tả. **Nhưng** nó không xóa các giới hạn khác như tham số, kích thước batch, tài nguyên lập kế hoạch, bộ nhớ, log hay thời gian thực thi. Đừng dùng nó để đưa hàng trăm nghìn literal vào một truy vấn nếu cơ chế nạp dữ liệu chuyên dụng phù hợp hơn.

### 13.3. Cảnh báo về suy luận kiểu trong VALUES

Khi `VALUES` là bảng dẫn xuất, SQL Server cần chọn kiểu chung cho từng cột trong các hàng:

```sql
-- SQL Server: loại dữ liệu lẫn lộn có thể bị ép theo
-- type precedence, gây lỗi nếu chuỗi không phải số.
SELECT src.value
FROM (VALUES (1), ('ABC')) AS src(value);
```

Có thể xảy ra lỗi chuyển đổi vì một kiểu số được ưu tiên trong phép phân giải. Nên ép kiểu rõ nếu muốn một cột mã hỗn hợp:

```sql
SELECT src.code
FROM (
    VALUES
        (CAST(1 AS VARCHAR(30))),
        (CAST('ABC' AS VARCHAR(30)))
) AS src(code);
```

Điều này áp dụng cả cho `INSERT ... SELECT FROM (VALUES...)`: phải thống nhất ý nghĩa và kiểu của từng vị trí trước khi chèn vào bảng đích.

### 13.4. Số tham số của SQL Server

SQL Server còn có các giới hạn tham số tại lớp T-SQL/driver; một giới hạn thường gặp được tài liệu SQL Server nêu là **2.100 tham số** cho stored procedure/function, và nhiều đường gửi truy vấn tham số hóa cũng phải xét ngưỡng tương ứng.

Ví dụ ứng dụng tạo một câu với **4 tham số cho mỗi hàng**:

```text
INSERT INTO products (sku, product_name, price, stock_qty)
VALUES (?, ?, ?, ?), (?, ?, ?, ?), ...
```

Nếu tạo 700 hàng thì cần `700 × 4 = 2800` placeholder, vượt ngưỡng 2.100 thường gặp, **dù 700 < 1000**. Vì vậy, giới hạn thực tế có thể đến từ **tham số trước khi chạm giới hạn 1.000 hàng direct VALUES**. Một batch còn có thể chứa các tham số cố định khác, nên phải trừ chúng khỏi ngân sách.

Các phương án chuẩn cho khối lượng lớn trên SQL Server gồm **table-valued parameters (TVP)**, `SqlBulkCopy`, `BULK INSERT`, `bcp` hoặc nguồn staging với `INSERT ... SELECT`. Chọn theo đặc điểm ứng dụng và quyền vận hành.

## 14. Oracle Database: khác nhau theo phiên bản

Oracle là trường hợp rất quan trọng khi chuyển SQL giữa các hệ.

### 14.1. Oracle 19c/21c: không dùng trực tiếp multi-row comma VALUES kiểu PostgreSQL

Dạng sau quen thuộc với PostgreSQL/MySQL/SQL Server:

```sql
-- Không phải cú pháp multi-row INSERT trực tiếp dùng được
-- trên Oracle 19c/21c:
INSERT INTO products (sku, product_name, price)
VALUES
    ('SKU-1', 'Mouse', 350),
    ('SKU-2', 'Keyboard', 900);
```

Trong các phiên bản Oracle cũ như 19c/21c, thường dùng **`INSERT ALL`**, `INSERT ... SELECT` hoặc nhiều lệnh insert riêng cho bài toán này.

### 14.2. Oracle INSERT ALL

```sql
-- Oracle Database, ví dụ cú pháp multitable INSERT ALL.
INSERT ALL
    INTO products (sku, product_name, price)
    VALUES ('SKU-1', 'Mouse', 350)
    INTO products (sku, product_name, price)
    VALUES ('SKU-2', 'Keyboard', 900)
    INTO products (sku, product_name, price)
    VALUES ('SKU-3', 'Cable', 120)
SELECT 1 FROM dual;
```

`INSERT ALL` là cơ chế **multi-table insert** của Oracle. Trong ví dụ, mọi nhánh `INTO` đều nhắm **cùng bảng đích**, nên một câu tạo ba hàng. `SELECT 1 FROM dual` cung cấp một hàng nguồn để các nhánh `INTO` được áp dụng.

Đây không chỉ là cú pháp khác của `VALUES (r1), (r2)` trên mọi góc độ: `INSERT ALL` còn có các khả năng và quy tắc riêng đối với nhiều bảng, các điều kiện `WHEN`, sequence và xử lý biểu thức. Đặc biệt không dựa vào việc gọi sequence trong từng `INTO` như thể luôn tăng độc lập cho mỗi nhánh khi dùng chung một hàng nguồn. Nếu bảng có identity hoặc cơ chế sinh khóa, cần kiểm tra đúng hợp đồng phiên bản.

### 14.3. Oracle Database 23ai hỗ trợ multi-row VALUES

Oracle Database **23ai** bổ sung cú pháp multi-value `INSERT` thân thuộc:

```sql
-- Oracle Database 23ai:
INSERT INTO products (sku, product_name, price)
VALUES
    ('SKU-1', 'Mouse', 350),
    ('SKU-2', 'Keyboard', 900),
    ('SKU-3', 'Cable', 120);
```

Như vậy, câu “Oracle không hỗ trợ INSERT nhiều hàng với VALUES” **chỉ đúng khi gắn với những phiên bản cũ phù hợp**, không phải kết luận cho mọi bản Oracle hiện đại. Khi xây thư viện đa DBMS, hãy kiểm tra **phiên bản server** trước khi chọn cú pháp.

### 14.4. Oracle INSERT ... SELECT

Oracle cũng hỗ trợ chèn từ truy vấn nguồn:

```sql
-- Oracle: giả sử PRODUCT_STAGE chứa dữ liệu đúng kiểu.
INSERT INTO products (sku, product_name, price)
SELECT sku, product_name, price
FROM product_stage
WHERE eligible = 1;
```

Ví dụ trên giả định `eligible` là cột mã số với giá trị 1 biểu diễn đủ điều kiện. Trên hệ khác, cột boolean và cú pháp giá trị boolean có thể khác. Không dùng `TRUE` hay `1` một cách máy móc giữa các hệ.

Với dữ liệu rất lớn, Oracle có các công cụ như SQL*Loader, external tables hoặc direct-path insert theo lựa chọn/kế hoạch tương ứng. Cần xem logging, undo/redo, trigger, constraint và yêu cầu vận hành trước khi áp dụng.

## 15. SQLite: multi-row VALUES và giới hạn số biến bind

SQLite hiện đại hỗ trợ:

```sql
-- SQLite: giả sử products có các cột tương ứng.
INSERT INTO products (sku, product_name, price)
VALUES
    ('SKU-1', 'Mouse', 350),
    ('SKU-2', 'Keyboard', 900),
    ('SKU-3', 'Cable', 120);
```

Một giới hạn đặc biệt quan trọng với ứng dụng SQLite là **số host parameters** (`?`, `?NNN` hoặc tham số có tên).

Theo giới hạn mặc định được SQLite công bố:

- **Trước SQLite 3.32.0:** mặc định tối đa **999** host parameter trong một câu SQL.
- **Từ SQLite 3.32.0:** mặc định tối đa **32.766** host parameter.
- Giá trị có thể được cấu hình ở lúc biên dịch hoặc hạ qua `sqlite3_limit(..., SQLITE_LIMIT_VARIABLE_NUMBER, ...)`.

### 15.1. Ví dụ tính giới hạn theo cột

Nếu mỗi hàng có 4 placeholder:

```text
INSERT INTO products (sku, product_name, price, stock_qty)
VALUES (?, ?, ?, ?), (?, ?, ?, ?), ...
```

Với giới hạn mặc định cũ 999:

```text
floor(999 / 4) = 249 hàng
```

Với giới hạn mặc định hiện đại 32.766:

```text
floor(32766 / 4) = 8191 hàng
```

Hai con số chỉ tính **ngân sách placeholder**, không phải khuyến nghị nên chèn đúng số hàng cực đại. Thực tế còn chịu kích thước SQL, bộ nhớ, giới hạn câu lệnh/cột, dữ liệu lớn và hiệu năng. Nếu câu SQL có thêm các placeholder khác, số hàng tối đa phải giảm.

### 15.2. Cảnh báo với ?NNN

SQLite cho phép placeholder có số như `?1`, `?2`, nhưng cũng có quy tắc cấp vị trí tham số. Không tạo một tham số kiểu `?1000000000` với giả định chỉ dùng **một** biến: engine xét **số chỉ mục lớn nhất** khi bố trí vị trí bind và sẽ giới hạn để tránh cấp phát quá lớn.

Để dễ kiểm soát, khi tự tạo multi-row statement hãy dùng placeholder liên tiếp hoặc API bind phù hợp, không chọn số tham số tùy tiện.

### 15.3. Giao dịch và bulk SQLite

SQLite thường hưởng lợi đáng kể khi gom nhiều lần `INSERT` đã chuẩn bị trong **một transaction hợp lý**, thay vì commit từng hàng. Với file lớn, prepared statement tái sử dụng cùng transaction có thể ít tốn chi phí hơn việc sinh câu literal multi-VALUES cực dài.

Ngoài ra, **kiểm tra cấu hình foreign key** của từng kết nối SQLite; không mặc định mọi ứng dụng đã bật enforcement nếu dựa vào FK để bảo vệ dữ liệu nhập.

## 16. Bảng so sánh nhanh các hệ quản trị

| Hệ quản trị | `VALUES (r1),(r2)` trực tiếp? | Hạn chế/cơ chế nổi bật | Thay thế cho dữ liệu lớn |
|---|---|---|---|
| **PostgreSQL** | Có | Số bind, kích thước câu/plan, log và tài nguyên | `COPY FROM STDIN`, `INSERT ... SELECT`, JDBC batch |
| **MySQL** | Có | `max_allowed_packet`, engine/SQL mode, số bind/tài nguyên | `LOAD DATA`, batching, `INSERT ... SELECT` |
| **MariaDB** | Có | Tương tự nhiều ý tưởng MySQL nhưng tính năng/phiên bản khác | `LOAD DATA`, batching, `INSERT ... SELECT` |
| **SQL Server** | Có | **Tối đa 1.000 hàng** khi dùng trực tiếp `INSERT ... VALUES`; còn ngưỡng tham số | Derived `VALUES` trong `FROM`, TVP, `SqlBulkCopy`, `BULK INSERT` |
| **Oracle 19c/21c** | Không theo cú pháp dấu phẩy trực tiếp quen thuộc | `INSERT ALL`, `INSERT ... SELECT` | SQL*Loader, external tables, cơ chế direct path |
| **Oracle 23ai** | Có | Cần đúng phiên bản 23ai+ hỗ trợ multivalue insert | `INSERT ... SELECT`, cơ chế bulk Oracle |
| **SQLite** | Có trên phiên bản hiện đại | Mặc định **999** bind trước 3.32.0; **32.766** từ 3.32.0, có thể cấu hình | Prepared statement tái sử dụng + transaction |

Đây không phải danh sách “giới hạn hàng tối đa tuyệt đối” cho từng hệ. Một số hệ không áp số hàng trực tiếp cố định giống SQL Server; khi đó **các giới hạn tài nguyên và tham số** mới là yếu tố thực tế.

Cũng cần phân biệt sản phẩm phái sinh: Azure Synapse Analytics không hỗ trợ mọi dạng table value constructor giống SQL Server Database Engine. Không giả định tất cả dịch vụ mang tên SQL/Azure hỗ trợ y hệt.

## 17. Số hàng × số cột = số tham số bind

Khi ứng dụng tạo một câu INSERT tham số hóa, hãy tính **ngân sách placeholder** trước khi tạo SQL.

Giả sử số cột được bind trên mỗi hàng là `C` và số hàng trong một statement là `R`:

\[
P = R \times C + P_{\text{khác}}
\]

Trong đó:

- `P`: tổng số placeholder.
- `P_khác`: placeholder khác nằm trong cùng câu SQL, ví dụ điều kiện hoặc biểu thức phụ.
- Nếu một DBMS/driver có giới hạn `P_max`, cần `P <= P_max`.

Suy ra giới hạn hàng theo tham số:

\[
R_{\max} = \left\lfloor
\frac{P_{\max} - P_{\text{khác}}}{C}
\right\rfloor
\]

Đây là **công thức kiểm tra kỹ thuật** chứ chưa phải kích thước batch tối ưu.

### 17.1. Ví dụ SQL Server: 4 cột, 700 hàng

```text
4 placeholder/hàng × 700 hàng = 2.800 placeholder
```

Nếu đường gửi truy vấn có ngân sách 2.100 tham số, statement này không phù hợp dù **700 dưới ngưỡng 1.000 dòng của direct VALUES**.

Với 4 cột và không có tham số khác, ngưỡng toán học theo 2.100 là:

```text
floor(2100 / 4) = 525 hàng
```

Trong triển khai thực tế nên có phần dự phòng thay vì sử dụng đúng ngưỡng cực đại, và còn cần đảm bảo không vượt **giới hạn 1.000 nhóm VALUES trực tiếp**.

### 17.2. Ví dụ SQLite cũ: 5 cột

```text
floor(999 / 5) = 199 hàng
```

Một ứng dụng cần chạy cả trên SQLite trước 3.32.0 có thể chọn batch không quá 199 hàng nếu mỗi hàng cần năm placeholder và không có tham số khác. Nếu sử dụng driver duy trì kết nối đến phiên bản hiện đại, vẫn nên **kiểm tra hạn mức thực tế** thay vì luôn áp 32.766 theo số phiên bản chung.

### 17.3. Ví dụ thuật toán chọn kích thước lô

Giả sử ứng dụng có các giá trị cấu hình:

```text
columns_per_row      = 5
max_bind_parameters  = 2100
fixed_parameters     = 10
max_direct_values    = 1000
preferred_batch_rows = 300

max_rows_by_params = floor((2100 - 10) / 5)
                   = 418

chosen_rows = min(300, 418, 1000)
            = 300
```

Batch 300 hàng thỏa các ngân sách ví dụ và không cần đẩy statement lên giới hạn. **Đây chỉ là minh họa lựa chọn batch dựa trên cấu hình**, không phải khuyến nghị 300 hàng áp dụng mọi hệ thống.

Nếu dùng driver `addBatch()` với từng statement một hàng thay vì tự gộp `VALUES`, “số hàng trong JDBC batch” không nhất thiết tuân cùng phép nhân placeholder của **một SQL statement duy nhất**. Phải xét cách driver thực thi và khả năng rewrite của nó.

## 18. JDBC: prepared statement và batch nhiều hàng

Trong ứng dụng Java, khi dữ liệu đến từ một danh sách đối tượng, lựa chọn thường tốt là **dùng `PreparedStatement` và bind tham số**, tránh nối literal người dùng trực tiếp vào SQL.

Ví dụ mẫu, giả sử có một danh sách đối tượng `products` với các phương thức `sku()`, `name()`, `price()`, `stockQty()` và một `DataSource dataSource` đã được cấu hình:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

// products và dataSource là biến đã có trong ứng dụng.
String sql = """
    INSERT INTO products (sku, product_name, price, stock_qty)
    VALUES (?, ?, ?, ?)
    """;

try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        int pending = 0;

        for (Product p : products) {
            ps.setString(1, p.sku());
            ps.setString(2, p.name());
            ps.setBigDecimal(3, p.price());
            ps.setInt(4, p.stockQty());
            ps.addBatch();

            if (++pending >= 500) {
                ps.executeBatch();
                ps.clearBatch();
                pending = 0;
            }
        }

        if (pending > 0) {
            ps.executeBatch();
            ps.clearBatch();
        }

        connection.commit();
    } catch (SQLException ex) {
        connection.rollback();
        throw ex;
    }
}
```

*Giải thích*: Ví dụ dùng Java text block và kiểu `Product` tượng trưng cho lớp DTO của ứng dụng; cần thay theo mã nguồn thực tế. Nếu `products` là luồng lớn, nên đọc/đẩy theo batch mà không giữ toàn bộ trong RAM.

Điểm quan trọng:

- `PreparedStatement` tránh nối giá trị người dùng trực tiếp vào SQL và giúp áp kiểu đúng.
- `addBatch()` gom các lần bind của cùng câu đã chuẩn bị.
- `executeBatch()` gửi batch theo cơ chế JDBC driver; không hứa chúng biến thành một câu multi-row `VALUES`.
- `setAutoCommit(false)` và `commit()`/`rollback()` xác định phạm vi giao dịch trong ví dụ.
- `clearBatch()` bỏ các lời gọi đã chuẩn bị trong client khi cần.
- `500` là kích thước **minh họa**, cần đo theo DBMS/driver và khối lượng dữ liệu thực tế.

Nếu rollback thất bại hoặc kết nối gặp sự cố, ứng dụng còn phải xử lý ngoại lệ và trạng thái kết nối đúng chính sách. Đoạn mã trình bày luồng căn bản, không thay cho bộ khung xử lý transaction/retry đầy đủ của ứng dụng sản xuất.

### 18.1. Không chèn dữ liệu bằng SQL nối chuỗi

Không nên làm:

```java
// Không an toàn: giá trị từ người dùng được ghép thẳng vào SQL.
String sql = "INSERT INTO products (sku, product_name) VALUES ('"
        + userSku + "', '" + userName + "')";
```

Dấu nháy trong tên sản phẩm có thể phá cú pháp; dữ liệu không tin cậy có thể tạo SQL injection. Thêm nhiều hàng bằng cách nối hàng nghìn chuỗi càng làm vấn đề khó kiểm soát.

Dùng placeholder/driver hoặc công cụ nạp dữ liệu có giao thức escape/serialization đúng quy cách.

### 18.2. Lấy generated keys sau JDBC batch

JDBC có các cơ chế như `Statement.RETURN_GENERATED_KEYS` và `getGeneratedKeys()`, nhưng mức hỗ trợ cho **batch insert**, thứ tự khóa trả về và việc driver rewrite thành multi-row query có thể khác nhau.

Nếu ứng dụng cần ánh xạ chính xác ID với dữ liệu nguồn, hãy dựa vào khóa nghiệp vụ, output mapping đáng tin hoặc quy trình nhập staging rồi lấy khóa theo join; **không tự cộng dãy ID** từ giá trị cuối cùng được trả về.

### 18.3. Không retry mù một batch đã commit một phần

Nếu giao dịch đã commit nhưng client mất kết nối trước khi nhận phản hồi, ứng dụng có thể **không biết chắc** thao tác đã thành công. Retry toàn bộ có thể tạo bản ghi trùng nếu thiếu khóa nghiệp vụ hoặc idempotency key.

Hãy đặt ràng buộc `UNIQUE` thích hợp, dùng upsert/ignore theo chính sách và ghi dấu batch đã xử lý khi cần. Đây là cách biến thao tác nhập thành **an toàn khi thử lại**, chứ không phải thuộc tính tự có của multi-row `INSERT`.

## 19. Chia lô: không có một kích thước tối ưu cho mọi hệ

Ví dụ 100.000 sản phẩm có thể được xử lý thành 100 lô × 1.000 hàng, 200 lô × 500 hàng hoặc một luồng bulk. Lựa chọn cần xem:

| Yếu tố | Khi lô quá nhỏ | Khi lô quá lớn |
|---|---|---|
| Round-trip mạng | Nhiều lần gửi | Ít lần gửi hơn |
| SQL parse/plan | Chi phí lặp theo câu lệnh | SQL có thể rất dài/khó lập kế hoạch |
| Bộ nhớ client/server | Thường ít hơn | Có thể tăng mạnh |
| Transaction log | Nhiều đơn vị nhỏ | Một lô có thể tạo log lớn |
| Khóa và đồng thời | Thường giữ khóa ít hơn mỗi lô | Có thể giữ nhiều khóa lâu hơn |
| Khi một hàng lỗi | Dễ cô lập lô/hàng lỗi | Khó tìm hàng gây lỗi trong lô khổng lồ |
| Retry | Có thể retry từng lô | Retry lô lớn tốn kém hơn |
| Giới hạn DBMS/driver | Dễ tránh ngưỡng | Dễ vượt số biến, packet, 1.000 VALUES |

Khi quyết định, cần phân biệt **kích thước lô thực thi** với **kích thước giao dịch**. Có thể chạy 20 batch trong một transaction hoặc mỗi batch một transaction tùy yêu cầu.

Quy trình thực tế:

1. Xác định **đúng DBMS/phiên bản và driver**.
2. Xác định có hạn mức theo hàng/placeholder/kích thước gói nào cần tránh.
3. Chọn một kích thước batch **thận trọng** ban đầu.
4. Đo thời gian nhập, số lượt gửi, CPU, log, mức khóa, bộ nhớ và tỷ lệ lỗi.
5. Tăng/giảm batch theo bằng chứng thay vì dùng con số “tối ưu” truyền miệng.
6. Với file rất lớn, xem các API bulk chuyên dụng.

## 20. Dữ liệu có lỗi: kiểm tra trước khi chèn

Một file nhập thường chứa:

- SKU trống/trùng.
- Giá không phải số hoặc âm.
- Số lượng âm.
- Chuỗi vượt độ dài cột.
- Ngày không hợp lệ hoặc timezone không đúng.
- Mã tham chiếu không tồn tại.
- Một dòng có số cột sai.

Nếu gửi toàn bộ vào một multi-row `INSERT`, lỗi của một hàng có thể làm câu lệnh thất bại toàn bộ ở DBMS có atomicity cấp statement. Điều này tốt cho tính nhất quán, nhưng có thể khó trả lời người dùng **hàng nào cần sửa**.

### 20.1. Staging giúp đối soát từng dòng

Có thể nhập dữ liệu thô vào bảng staging kèm `source_line_no`, tên file/batch và trạng thái kiểm tra, sau đó phân loại:

```sql
-- PostgreSQL: kiểm tra các giá trị đã có kiểu NUMERIC/INTEGER.
SELECT
    source_line_no,
    sku,
    CASE
        WHEN BTRIM(sku) = '' THEN 'EMPTY_SKU'
        WHEN price < 0 THEN 'NEGATIVE_PRICE'
        WHEN stock_qty < 0 THEN 'NEGATIVE_STOCK'
        ELSE 'VALID'
    END AS validation_status
FROM demo_product_stage
ORDER BY source_line_no;
```

Bảng `demo_product_stage` của ví dụ đã khai báo `price NUMERIC` nên chuỗi giá không hợp lệ **không vào được bảng staging này**. Nếu muốn thu thập cả giá thô để báo lỗi, hãy dùng bảng staging với cột `raw_price TEXT` rồi chuyển có kiểm soát sau. Không `CAST` vô điều kiện dữ liệu CSV bất kỳ rồi mong mọi dòng lỗi đều được báo cáo riêng.

### 20.2. Kiểm tra duplicate trong batch trước

```sql
SELECT
    sku,
    COUNT(*) AS occurrences
FROM demo_product_stage
GROUP BY sku
HAVING COUNT(*) > 1
ORDER BY sku;
```

Đối với mẫu hiện tại không có SKU trùng trong stage, nhưng có `SKU-101` **đã tồn tại ở bảng đích**. Hai loại xung đột khác nhau:

- **Trùng nội bộ batch:** nhiều dòng nguồn chung khóa.
- **Trùng với dữ liệu đích:** khóa mới đã được sử dụng trước đó.

Một quy trình nhập đúng cần chính sách cho cả hai. `UNIQUE` ở bảng đích là lớp bảo vệ cuối cùng chứ không thay thế thông báo lỗi hữu ích cho người nhập.

### 20.3. Kích thước batch không phải cách sửa dữ liệu xấu

Nếu file có một hàng `price = -100`, chia từ batch 1.000 xuống 100 chỉ làm lỗi xuất hiện ở lô nhỏ hơn. Cần phân loại lỗi và quyết định bỏ qua/hoàn nguyên/sửa từng dòng theo hợp đồng, không chỉ “retry với batch nhỏ hơn” rồi mong lỗi biến mất.

## 21. Những điều dễ nhầm khi so sánh INSERT nhiều hàng

### 21.1. Một câu SQL không đồng nghĩa một hàng

`VALUES (1), (2), (3)` là ba hàng trong một statement. `INSERT ... SELECT` có thể chèn rất nhiều hàng dù văn bản câu lệnh chỉ vài dòng.

### 21.2. Một statement không đồng nghĩa một transaction toàn bộ quy trình

Ba statement liên tiếp có thể tự commit riêng hoặc nằm chung một transaction. Atomicity toàn quy trình chỉ có khi ranh giới giao dịch và engine hỗ trợ theo thiết kế.

### 21.3. Cùng số cột chưa chắc cùng ý nghĩa

Hai biểu thức kiểu `TEXT` có thể bị đảo `sku` và `product_name` mà không báo lỗi. Hãy kiểm tra thứ tự cột của danh sách `INSERT` và từng nhóm `VALUES`.

### 21.4. DEFAULT không giống NULL

`DEFAULT` lấy giá trị mặc định của cột nếu cú pháp hỗ trợ; `NULL` chủ động chèn giá trị thiếu. Với `NOT NULL`, truyền `NULL` có thể gây lỗi ngay cả khi cột có default.

### 21.5. Không coi generated IDs là dãy liên tiếp chắc chắn

Identity/sequence có thể có khoảng trống, rollback, cache hoặc cấp đồng thời. Đối soát bằng khóa nghiệp vụ/correlation key.

### 21.6. Số hàng được yêu cầu không bằng số hàng được chèn

`ON CONFLICT DO NOTHING` và các cơ chế ignore có thể bỏ qua hàng. Cần kiểm tra affected rows/RETURNING/OUTPUT/cảnh báo theo DBMS.

### 21.7. Không phải toàn bộ Oracle đều thiếu multi-row VALUES

Các phiên bản Oracle cũ như 19c/21c dùng `INSERT ALL`/`INSERT ... SELECT`; Oracle 23ai đã bổ sung cú pháp multi-value `INSERT`.

### 21.8. SQL Server 1.000 hàng không áp cho mọi kiểu INSERT

Ngưỡng 1.000 là **direct `INSERT ... VALUES`**; `INSERT ... SELECT FROM (VALUES ...)` có cách áp dụng khác, và bulk import có cơ chế riêng.

### 21.9. JDBC batch không mặc định dùng một statement

Cấu hình driver, rewrite và kiểu prepared statement quyết định số câu SQL được gửi. Phải đo và kiểm tra driver nếu muốn tối ưu.

### 21.10. Bulk nhanh hơn không có nghĩa bỏ kiểm soát dữ liệu

FK, UNIQUE, CHECK, trigger, logging và các lựa chọn về isolation là bộ phận của thiết kế. Không tắt cơ chế quan trọng chỉ vì muốn nhập nhanh.

## 22. Chọn giải pháp theo yêu cầu

| Tình huống | Gợi ý | Lý do |
|---|---|---|
| Người dùng tạo 3–20 dòng trong một form | Multi-row `INSERT ... VALUES` tham số hóa | Cú pháp ngắn, một statement |
| Ứng dụng tạo vài nghìn dòng trong Java | JDBC batch hoặc multi-row VALUES chia lô | Giảm round-trip và kiểm soát tham số |
| Di chuyển dữ liệu giữa hai bảng trong cùng DB | `INSERT ... SELECT` | Lọc/chuyển đổi trực tiếp trong DB |
| Cần loại/cập nhật SKU trùng khi import | Staging + kiểm tra + upsert/ignore đúng DBMS | Idempotency và tính toàn vẹn |
| File CSV rất lớn vào PostgreSQL | `COPY FROM STDIN` hoặc công cụ bulk phù hợp | Nạp theo luồng |
| File lớn vào MySQL/MariaDB | `LOAD DATA` nếu được phép | Cơ chế nhập file chuyên dụng |
| Nạp lớn vào SQL Server | TVP, `SqlBulkCopy` hoặc `BULK INSERT` | Vượt nhu cầu direct VALUES 1.000 hàng |
| Nạp lớn vào Oracle | SQL*Loader, external table, direct path hoặc API bulk | Tránh hàng nghìn statement thủ công |
| SQLite embedded với nhiều hàng | Reuse prepared statement và transaction | Giảm chi phí prepare/commit lặp |
| Cần báo lỗi theo dòng và cho người dùng sửa | Bảng staging có khóa dòng nguồn | Dễ đối soát/khôi phục |
| Cần all-or-nothing cho cả file | Transaction bao toàn bộ lô và xử lý lỗi | Không để kết quả nhập dở dang |

**Không có quy tắc “luôn dùng lô 1.000 hàng” cho mọi DBMS.** Hãy lựa chọn theo giới hạn cụ thể và bài toán dữ liệu, không chỉ theo cú pháp.

## 23. Bài tập thực hành

### Bài 1. Viết INSERT nhiều hàng

**Yêu cầu:** dùng PostgreSQL thêm ba sản phẩm `('SKU-Q1','Notebook',70)`, `('SKU-Q2','Pen',15)`, `('SKU-Q3','Folder',25)` vào `demo_products`; không truyền `product_id` và `stock_qty`.

**Đáp án:**

```sql
INSERT INTO demo_products (sku, product_name, price)
VALUES
    ('SKU-Q1', 'Notebook', 70),
    ('SKU-Q2', 'Pen', 15),
    ('SKU-Q3', 'Folder', 25);
```

Mỗi nhóm có ba giá trị; `product_id` được sinh, `stock_qty` mặc định 0.

### Bài 2. Dự đoán lỗi số lượng giá trị

```sql
INSERT INTO demo_products (sku, product_name, price)
VALUES ('SKU-Q4', 'Mouse', 350),
       ('SKU-Q5', 'Cable');
```

**Câu hỏi:** vì sao không hợp lệ?

**Đáp án:** nhánh `VALUES` thứ hai chỉ có **hai giá trị**, nhưng danh sách cột đích có **ba cột**. Cần cung cấp `price` hoặc thay đổi danh sách cột áp dụng chung cho tất cả hàng, đồng thời tôn trọng ràng buộc `NOT NULL`.

### Bài 3. Phân biệt NULL và DEFAULT

**Yêu cầu:** hàng thứ nhất dùng stock mặc định, hàng thứ hai dùng stock 7 và note `NULL`.

**Đáp án PostgreSQL:**

```sql
INSERT INTO demo_products
    (sku, product_name, price, stock_qty, note)
VALUES
    ('SKU-Q6', 'Tape',     30, DEFAULT, 'New import'),
    ('SKU-Q7', 'Stapler', 110,       7, NULL);
```

`DEFAULT` lấy 0 từ định nghĩa `stock_qty`; `NULL` của `note` là giá trị thiếu tường minh.

### Bài 4. Tính giới hạn SQL Server

**Câu hỏi:** SQL Server có thể dùng một `INSERT ... VALUES` trực tiếp gồm 1.200 nhóm giá trị không? Có thể dùng giải pháp nào?

**Đáp án:** không, vì direct table value constructor trong `INSERT ... VALUES` giới hạn **1.000 hàng**. Có thể chia thành hai câu INSERT, dùng `INSERT ... SELECT FROM (VALUES ...)` như derived table hoặc bulk/TVP. Tất cả phương án vẫn phải xét ngưỡng tham số và tài nguyên.

### Bài 5. Tính số placeholder

**Câu hỏi:** một statement tham số hóa có 5 cột cho mỗi hàng, một môi trường SQLite cũ có giới hạn 999 host parameters mặc định. Tối đa bao nhiêu hàng theo riêng giới hạn tham số, nếu không có placeholder khác?

**Đáp án:**

```text
floor(999 / 5) = 199 hàng
```

Con số 199 không chứng minh nên luôn dùng batch lớn như vậy. Còn các giới hạn kỹ thuật/hiệu năng khác.

### Bài 6. Oracle 19c

**Yêu cầu:** viết một câu thêm hai sản phẩm vào Oracle 19c mà không dùng cú pháp dấu phẩy multi-row `VALUES`.

**Đáp án:**

```sql
INSERT ALL
    INTO products (sku, product_name, price)
    VALUES ('SKU-Q8', 'Mouse', 350)
    INTO products (sku, product_name, price)
    VALUES ('SKU-Q9', 'Keyboard', 900)
SELECT 1 FROM dual;
```

Cần điều chỉnh tên bảng/kiểu/khóa sinh theo schema thực tế. Oracle 23ai đã có multi-row `VALUES` trực tiếp.

### Bài 7. INSERT ... SELECT

**Yêu cầu:** từ `demo_product_stage`, nhập mọi hàng `eligible = TRUE` vào `demo_products`; nếu trùng `sku`, bỏ qua bằng cú pháp PostgreSQL.

**Đáp án:**

```sql
INSERT INTO demo_products (sku, product_name, price, stock_qty)
SELECT sku, product_name, price, stock_qty
FROM demo_product_stage
WHERE eligible = TRUE
ON CONFLICT (sku) DO NOTHING;
```

`UNIQUE(sku)` vẫn là lớp bảo vệ chống trùng. `DO NOTHING` không có nghĩa mọi hàng đầu vào đều được ghi; cần kiểm tra số dòng thực tế.

### Bài 8. Tính nguyên tử

**Tình huống:** một câu `INSERT` PostgreSQL có hai hàng; hàng đầu hợp lệ, hàng thứ hai trùng khóa `sku`. Không dùng `ON CONFLICT`.

**Đáp án:** cả câu `INSERT` thất bại theo atomicity cấp statement, không commit riêng hàng đầu. Nếu lỗi phát sinh trong một transaction PostgreSQL, cần rollback hoặc rollback về savepoint phù hợp trước khi tiếp tục.

### Bài 9. IDENTITY và RETURNING

**Yêu cầu:** chèn hai sản phẩm trên PostgreSQL và nhận `product_id`/`sku` vừa tạo.

**Đáp án:**

```sql
INSERT INTO demo_products (sku, product_name, price)
VALUES
    ('SKU-Q10', 'Monitor', 4200),
    ('SKU-Q11', 'Webcam',  890)
RETURNING product_id, sku;
```

Ghép kết quả về nguồn bằng `sku` hoặc khóa tương ứng; không mặc định kết quả được trả theo thứ tự đầu vào hoặc ID liên tiếp.

### Bài 10. Chọn công cụ cho 500.000 dòng

**Tình huống:** Java đọc CSV 500.000 sản phẩm và cần nhập vào PostgreSQL, có ràng buộc SKU duy nhất, một số dòng sai định dạng.

**Gợi ý đáp án:** không ghép 500.000 hàng literal trong một câu `VALUES`. Có thể stream qua `COPY FROM STDIN` vào **staging**, kiểm tra định dạng/trùng theo `source_line_no`, sau đó `INSERT ... SELECT` kết hợp ràng buộc và chính sách xử lý xung đột. Hoặc dùng JDBC batch chia lô nếu khối lượng/tính năng của ứng dụng phù hợp. Ranh giới transaction và cơ chế retry/idempotency cần được xác định.

### Bài 11. JDBC batch có phải một câu SQL không?

**Câu hỏi:** chương trình gọi `ps.addBatch()` 500 lần rồi `ps.executeBatch()` một lần. Có thể khẳng định DBMS nhận đúng một `INSERT ... VALUES` 500 hàng và transaction tự động all-or-nothing không?

**Đáp án:** không. Cách driver gửi các câu và khả năng rewrite phụ thuộc driver/cấu hình. Atomicity toàn batch phụ thuộc chế độ giao dịch, lỗi và storage engine. Nếu cần tất cả cùng commit/rollback, điều khiển transaction rõ ràng.

### Bài 12. Retry nhập CSV

**Tình huống:** ứng dụng gửi batch 300 dòng, mất kết nối trước khi nhận kết quả; không biết server đã commit hay chưa. Có nên gửi lại nguyên batch không?

**Đáp án:** chỉ khi cơ chế nhập được thiết kế **idempotent** hoặc có đối soát xác nhận an toàn. Cần khóa duy nhất theo nghiệp vụ, batch identifier hoặc cơ chế upsert/ignore có kiểm soát để tránh dữ liệu trùng và mất thông tin. Không dựa vào identity ID để suy batch trước chưa chạy.

## 24. Tổng kết và nguyên tắc mang sang hệ thống thật

`INSERT ... VALUES (r1), (r2), ...` là cách đơn giản để thêm nhiều hàng trong một câu SQL. Mỗi nhóm ngoặc là một hàng, mọi nhóm phải khớp **cùng danh sách cột**, cùng quy tắc kiểu và ràng buộc. Khi dữ liệu nằm trong bảng nguồn, `INSERT ... SELECT` cho phép lọc/chuẩn hóa trên DB; khi dữ liệu nằm ở ứng dụng hoặc file lớn, JDBC batch hoặc cơ chế bulk thường phù hợp hơn.

**Giới hạn theo hệ quản trị phải được hiểu đúng phạm vi:**

- **PostgreSQL:** hỗ trợ multi-row `VALUES`, `RETURNING`, `ON CONFLICT`; xem giới hạn bind, plan, log và cân nhắc `COPY` khi nhập lớn.
- **MySQL/MariaDB:** hỗ trợ nhiều nhóm `VALUES`; chú ý packet size, SQL mode, engine và sự khác nhau giữa `INSERT IGNORE`/`ON DUPLICATE KEY UPDATE`.
- **SQL Server:** direct `INSERT ... VALUES` tối đa **1.000 hàng**, nhưng derived table `VALUES` trong `FROM` và bulk/TVP là lựa chọn khác; còn phải xét ngưỡng tham số.
- **Oracle:** 19c/21c thường dùng `INSERT ALL`/`INSERT ... SELECT`; 23ai hỗ trợ multi-row `VALUES` trực tiếp.
- **SQLite:** hỗ trợ nhiều nhóm `VALUES` nhưng có giới hạn host parameters theo phiên bản/cấu hình; prepared statement cộng transaction thường hữu ích.

Cuối cùng, hiệu năng không phải mục tiêu duy nhất. Cần xác định **atomicity theo transaction, ràng buộc dữ liệu, báo lỗi theo dòng, xử lý trùng, thứ tự/correlation key và khả năng retry**. Một chiến lược nhập nhiều hàng tốt là chiến lược không chỉ nhanh mà còn cho kết quả đúng, có thể đối soát và vận hành an toàn.

