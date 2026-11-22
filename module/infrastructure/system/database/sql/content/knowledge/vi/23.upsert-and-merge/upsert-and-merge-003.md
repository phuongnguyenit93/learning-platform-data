# INSERT ON CONFLICT của PostgreSQL: thêm mới hoặc xử lý bản ghi trùng khóa

Khi ứng dụng gửi một lệnh `INSERT`, có thể bản ghi tương ứng đã tồn tại: mã sản phẩm trùng, email đã đăng ký, một sự kiện từ hàng đợi được gửi lại hoặc chương trình nhập dữ liệu được chạy hai lần. Nếu bảng có ràng buộc `PRIMARY KEY` hay `UNIQUE`, một lệnh chèn thông thường sẽ bị từ chối khi khóa trùng.

PostgreSQL cung cấp mệnh đề **`ON CONFLICT`** trong `INSERT` để định nghĩa trước cách xử lý những xung đột mà một **ràng buộc hoặc chỉ mục duy nhất phù hợp** phát hiện:

- **`ON CONFLICT ... DO NOTHING`:** bỏ qua hàng được đề xuất chèn nếu gặp xung đột thuộc phạm vi áp dụng.
- **`ON CONFLICT ... DO UPDATE SET ...`:** cập nhật hàng đang có thay vì tạo một hàng trùng; đây là mẫu **upsert** (*update hoặc insert*).

Ví dụ ngắn:

```sql
INSERT INTO products (sku, product_name, price)
VALUES ('MOUSE-01', 'Wireless Mouse', 350.00)
ON CONFLICT (sku) DO UPDATE
SET product_name = EXCLUDED.product_name,
    price = EXCLUDED.price;
```

Nếu `sku = 'MOUSE-01'` chưa tồn tại, PostgreSQL **chèn** hàng mới. Nếu đã tồn tại và có ràng buộc duy nhất trên `sku`, PostgreSQL **cập nhật** hàng tương ứng bằng giá trị được đề xuất chèn.

Điểm quan trọng là hiểu đúng **xung đột nào được xử lý, cách chọn khóa, dữ liệu `EXCLUDED` đại diện cho điều gì, xử lý `WHERE` và `RETURNING` ra sao, khi nào thao tác vẫn lỗi, và tính đúng đắn khi nhiều giao dịch cùng ghi**. Bài thuộc chương **Upsert và MERGE** của module Database SQL, tập trung vào **cú pháp PostgreSQL `INSERT ... ON CONFLICT`**; những so sánh với các DBMS khác chỉ để tránh nhầm phương ngữ.

> Các ví dụ thực hành dùng **PostgreSQL**. Từng đoạn thay đổi dữ liệu trên cùng bảng có thể ảnh hưởng kết quả của đoạn tiếp theo; nếu muốn chạy độc lập, dùng `BEGIN ... ROLLBACK` hoặc tạo lại dữ liệu mẫu. Đừng dùng các câu upsert có dữ liệu minh họa trên bảng sản xuất nếu chưa hiểu tác động.

## 1. Vì sao cần upsert thay vì SELECT trước rồi INSERT?

Một luồng ứng dụng dễ nghĩ tới là:

1. Tìm bằng `SELECT` xem khóa `sku` đã có chưa.
2. Nếu chưa có thì `INSERT`.
3. Nếu đã có thì `UPDATE`.

Ví dụ giả mã:

```text
IF NOT EXISTS (SELECT 1 FROM products WHERE sku = 'MOUSE-01')
    INSERT ...
ELSE
    UPDATE ...
```

Vấn đề là **cạnh tranh ghi** (*race condition*). Hai giao dịch có thể cùng kiểm tra:

```text
Thời điểm       Giao dịch A                 Giao dịch B
-----------     -----------------------     -----------------------
t1              SELECT: chưa có MOUSE-01
t2                                          SELECT: chưa có MOUSE-01
t3              INSERT MOUSE-01
t4                                          INSERT MOUSE-01
t5              COMMIT
t6                                          xung đột UNIQUE
```

Bước “đọc rồi quyết định” không tự bảo đảm chỉ một giao dịch được chèn. **Ràng buộc `UNIQUE` ở DB** là lớp ngăn trùng thực sự. `ON CONFLICT` kết hợp việc chèn và giải quyết xung đột trong một câu SQL, tránh phải tự viết một quy trình `SELECT` trước rồi `INSERT`/`UPDATE` không có cơ chế đồng bộ.

Trong PostgreSQL, `INSERT ... ON CONFLICT DO UPDATE` có bảo đảm mạnh rằng **mỗi hàng được đề xuất sẽ chèn hoặc cập nhật theo chính sách**, trừ khi một lỗi độc lập khác xảy ra. Sự bảo đảm này vẫn có ý nghĩa khi nhiều phiên giao dịch đồng thời tác động cùng khóa. Nhưng nó **không xóa bỏ nhu cầu thiết kế khóa duy nhất, ràng buộc, xử lý lỗi giao dịch và tính idempotent của nghiệp vụ**.

## 2. Tạo bảng mẫu và quy tắc duy nhất

Dữ liệu thực hành gồm sản phẩm có `sku` duy nhất, giá, tồn kho và phiên bản:

```sql
CREATE TEMP TABLE demo_products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,
    price NUMERIC(12, 2) NOT NULL CHECK (price >= 0),
    stock_qty INTEGER NOT NULL DEFAULT 0 CHECK (stock_qty >= 0),
    version_no INTEGER NOT NULL DEFAULT 1 CHECK (version_no >= 1),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_demo_products_sku UNIQUE (sku)
);

INSERT INTO demo_products
    (sku, product_name, price, stock_qty, version_no)
VALUES
    ('P-101', 'Mouse',      350.00, 10, 1),
    ('P-102', 'Keyboard',   900.00,  5, 2),
    ('P-103', 'USB Cable',  120.00,  0, 1),
    ('P-104', 'Monitor',   4200.00,  2, 1);

SELECT sku, product_name, price, stock_qty, version_no
FROM demo_products
ORDER BY sku;
```

Kết quả logic:

| sku | product_name | price | stock_qty | version_no |
|---|---|---:|---:|---:|
| P-101 | Mouse | 350.00 | 10 | 1 |
| P-102 | Keyboard | 900.00 | 5 | 2 |
| P-103 | USB Cable | 120.00 | 0 | 1 |
| P-104 | Monitor | 4200.00 | 2 | 1 |

Hai khóa quan trọng:

- `product_id` là **khóa chính** do PostgreSQL sinh; mỗi hàng có ID nội bộ.
- `sku` được bảo vệ bởi **`UNIQUE(sku)`**: không được có hai sản phẩm khác nhau có cùng mã `sku`.

Mọi ví dụ `ON CONFLICT (sku)` phía sau dựa vào ràng buộc `uq_demo_products_sku`. Nếu bỏ ràng buộc duy nhất trên `sku`, PostgreSQL **không tự xem hai hàng có cùng SKU là xung đột**; với `DO UPDATE` chỉ rõ `(sku)`, nó sẽ báo lỗi vì không tìm được unique/exclusion arbiter phù hợp.

### 2.1. Xung đột là khái niệm của ràng buộc/index, không phải “giá trị trông giống nhau”

Hai sản phẩm cùng `product_name = 'Mouse'` vẫn có thể được chèn nếu tên không bị `UNIQUE` ràng buộc. Ngược lại, hai sản phẩm có `sku` giống hệt nhau vi phạm `uq_demo_products_sku` dù tên, giá và các cột khác khác nhau.

Vì thế:

```sql
-- Xung đột theo SKU, nếu P-101 đã có:
INSERT INTO demo_products (sku, product_name, price)
VALUES ('P-101', 'Mouse 2', 400);
```

sẽ lỗi unique violation (thường SQLSTATE `23505`) nếu không khai báo cách xử lý.

`ON CONFLICT` không tự tìm ra “cùng một thực thể” theo ý nghĩa con người. **Phải chọn đúng khóa duy nhất theo nghiệp vụ**.

## 3. Khung cú pháp INSERT ... ON CONFLICT

Cấu trúc rút gọn:

```sql
INSERT INTO target_table [(column_list)]
VALUES (...)
ON CONFLICT [conflict_target]
DO NOTHING
[RETURNING ...];
```

hoặc:

```sql
INSERT INTO target_table AS t [(column_list)]
VALUES (...)
ON CONFLICT conflict_target
DO UPDATE SET
    column_1 = expression_1,
    column_2 = expression_2
[WHERE update_condition]
[RETURNING ...];
```

Trong PostgreSQL, `conflict_target` thông dụng là:

```sql
ON CONFLICT (column_name)

ON CONFLICT (column_1, column_2)

ON CONFLICT ON CONSTRAINT constraint_name

ON CONFLICT (column_1, column_2)
    WHERE index_predicate
```

Khi một unique index nằm trên biểu thức, conflict target còn có thể dùng biểu thức tương ứng, chẳng hạn `ON CONFLICT (lower(email))`.

**Quy tắc cần nhớ:**

- `DO NOTHING`: có thể **bỏ qua conflict target**, hoặc nêu rõ target.
- `DO UPDATE`: **phải có conflict target** để PostgreSQL biết hàng xung đột nào sẽ được cập nhật.
- `DO UPDATE SET`: chỉ định các cột muốn cập nhật; không tự cập nhật mọi cột từ `INSERT`.
- `EXCLUDED.column`: giá trị **được đề xuất chèn** tương ứng với cột đó.
- `WHERE` đặt sau `DO UPDATE SET`: **điều kiện có cập nhật hàng xung đột hay không**, không phải điều kiện chọn unique index.
- `RETURNING`: trả dữ liệu các hàng thực sự được chèn hoặc cập nhật theo ngữ nghĩa câu lệnh.

Đừng nhầm `ON CONFLICT` với `ON DELETE CASCADE`, `ON UPDATE CASCADE` của khóa ngoại; đây là các cơ chế khác nhau.

## 4. DO NOTHING: bỏ qua hàng trùng khóa

Ví dụ chèn hai hàng: một SKU đã có, một SKU mới.

```sql
INSERT INTO demo_products (sku, product_name, price, stock_qty)
VALUES
    ('P-101', 'Mouse imported again', 360.00, 7),
    ('P-105', 'Laptop Stand',         550.00, 4)
ON CONFLICT (sku) DO NOTHING
RETURNING product_id, sku, product_name;
```

Trên bảng mẫu ban đầu:

- `P-101` đã tồn tại → **bỏ qua** hàng đề xuất.
- `P-105` chưa tồn tại → **chèn** hàng mới.
- `RETURNING` chỉ trả `P-105`, không trả `P-101`.
- Bản ghi `P-101` vẫn giữ tên `Mouse`, giá `350.00`, stock `10`.

`DO NOTHING` thường phù hợp khi nhập dữ liệu theo khóa duy nhất với chính sách **“đã có thì giữ nguyên”**. Ví dụ một batch có thể được gửi lại mà người vận hành muốn giữ hàng đầu tiên đã được lưu.

### 4.1. Không chỉ định target với DO NOTHING

PostgreSQL cũng cho phép:

```sql
INSERT INTO demo_products (sku, product_name, price)
VALUES ('P-101', 'Duplicate ignored', 399.00)
ON CONFLICT DO NOTHING;
```

Khi bỏ conflict target, `DO NOTHING` áp dụng cho các xung đột với những unique constraints/indexes sử dụng làm arbiter hợp lệ; với trường hợp phù hợp, PostgreSQL bỏ qua hàng thay vì lỗi do khóa trùng.

**Lưu ý khác biệt:** Khi nêu `ON CONFLICT (sku)`, ta nói rõ **chỉ xử lý xung đột trên khóa `sku`**. Khi bỏ target, ta chấp nhận bỏ qua xung đột ở các khóa duy nhất phù hợp khác. Điều này có thể che đi một dữ liệu sai ngoài dự kiến nếu bảng có nhiều quy tắc duy nhất.

Trong dữ liệu quan trọng, việc nêu đúng khóa nghiệp vụ thường giúp người đọc hiểu chính xác chính sách chống trùng.

### 4.2. DO NOTHING không bỏ qua mọi loại lỗi

`ON CONFLICT DO NOTHING` **không biến `INSERT` thành “bỏ qua mọi lỗi”**:

- `price < 0` vẫn vi phạm `CHECK(price >= 0)`.
- Thiếu `sku` hoặc `product_name` vi phạm `NOT NULL`.
- Giá trị tham chiếu khóa ngoại không tồn tại vẫn có thể vi phạm `FOREIGN KEY`.
- Giá trị không chuyển được sang kiểu số vẫn có thể lỗi kiểu.
- Lỗi trigger hoặc phân quyền vẫn có thể làm câu lệnh thất bại.

Ví dụ:

```sql
-- Vẫn lỗi CHECK dù có ON CONFLICT DO NOTHING.
INSERT INTO demo_products (sku, product_name, price)
VALUES ('P-ERR', 'Invalid product', -100)
ON CONFLICT DO NOTHING;
```

Câu `ON CONFLICT` được thiết kế cho một **lớp xung đột duy nhất cụ thể**, không thay cho kiểm tra và làm sạch dữ liệu.

### 4.3. DO NOTHING và hai hàng trùng nhau ngay trong VALUES

```sql
INSERT INTO demo_products (sku, product_name, price)
VALUES
    ('P-109', 'Item A', 100),
    ('P-109', 'Item B', 150)
ON CONFLICT (sku) DO NOTHING;
```

Nếu `P-109` chưa có, chỉ một trong những hàng có thể được chèn; hàng còn lại gặp xung đột unique và bị bỏ qua theo cơ chế `DO NOTHING`. **Không dựa vào thứ tự ngẫu nhiên/không được bảo đảm của pipeline để biến cách này thành quy tắc “bản ghi cuối thắng”**.

Nếu nghiệp vụ cần giữ hàng có phiên bản cao hơn hay timestamp mới hơn, phải **khử trùng đầu vào theo tiêu chí xác định** trước khi chèn, không để thứ tự xử lý tình cờ quyết định giá trị.

## 5. DO UPDATE: cập nhật hàng đã có

Bài toán tiếp theo: hàng mới thì chèn; SKU đã có thì cập nhật tên, giá và tồn kho từ dữ liệu mới.

```sql
INSERT INTO demo_products AS p
    (sku, product_name, price, stock_qty, version_no)
VALUES
    ('P-102', 'Mechanical Keyboard', 950.00, 7, 3),
    ('P-106', 'USB Adapter',         180.00, 6, 1)
ON CONFLICT (sku) DO UPDATE
SET product_name = EXCLUDED.product_name,
    price        = EXCLUDED.price,
    stock_qty    = EXCLUDED.stock_qty,
    version_no   = EXCLUDED.version_no,
    updated_at   = CURRENT_TIMESTAMP
RETURNING product_id, sku, product_name, price, stock_qty, version_no;
```

Trên dữ liệu mẫu:

- `P-102` đã tồn tại → cập nhật thành tên `Mechanical Keyboard`, giá `950.00`, tồn kho `7`, phiên bản `3`.
- `P-106` chưa tồn tại → chèn hàng mới với giá `180.00`, tồn kho `6`, phiên bản `1`.
- Cả hàng **được chèn** và hàng **được cập nhật** đều có thể xuất hiện trong `RETURNING`.

### 5.1. EXCLUDED đại diện cho điều gì?

Trong phần `ON CONFLICT DO UPDATE`, PostgreSQL có tên đặc biệt **`EXCLUDED`** đại diện cho **hàng đầu vào đã được đề xuất chèn nhưng gặp xung đột**.

Ở ví dụ:

```sql
EXCLUDED.product_name
EXCLUDED.price
EXCLUDED.stock_qty
EXCLUDED.version_no
```

lần lượt là các giá trị của hàng `VALUES` tương ứng với SKU hiện tại.

Còn:

```sql
p.product_name
p.price
p.stock_qty
p.version_no
```

đại diện cho **giá trị của hàng hiện có ở bảng đích** trước khi cập nhật tại thời điểm thao tác xung đột được xử lý.

Đừng xem `EXCLUDED` là một bảng thật có thể `SELECT * FROM EXCLUDED` trong câu SQL bất kỳ. Đây là tên đặc biệt được sử dụng **trong ngữ cảnh `ON CONFLICT DO UPDATE`**.

### 5.2. SET chỉ tác động những cột được gán

```sql
INSERT INTO demo_products (sku, product_name, price)
VALUES ('P-101', 'Mouse Premium', 499.00)
ON CONFLICT (sku) DO UPDATE
SET price = EXCLUDED.price;
```

Với `P-101` đã tồn tại, chỉ có `price` thay đổi sang `499.00`. Cột `product_name` **vẫn là tên hiện có**, bởi dù `INSERT` đề xuất tên `Mouse Premium`, `SET` không yêu cầu cập nhật nó.

Các cột còn lại cũng giữ nguyên, trừ những thay đổi do trigger hoặc cơ chế DBMS khác được cấu hình. Không giả định `DO UPDATE` tự copy toàn bộ hàng đề xuất sang hàng cũ.

### 5.3. Viết biểu thức kết hợp hàng hiện có và hàng mới

Một trường hợp phổ biến là cộng thêm tồn kho từ một phiếu nhập. Khi đó, `stock_qty` trong dữ liệu đầu vào mang nghĩa **lượng nhập thêm**, không phải tồn kho tuyệt đối.

```sql
INSERT INTO demo_products AS p
    (sku, product_name, price, stock_qty)
VALUES
    ('P-103', 'USB Cable', 120.00, 4),
    ('P-107', 'HDMI Cable', 290.00, 6)
ON CONFLICT (sku) DO UPDATE
SET stock_qty = p.stock_qty + EXCLUDED.stock_qty,
    updated_at = CURRENT_TIMESTAMP
RETURNING sku, stock_qty;
```

Nếu `P-103` đang có stock 0, kết quả sau xung đột là **4**. Nếu `P-107` chưa tồn tại, nó được chèn với stock **6**.

Sự khác biệt:

| Biểu thức SET | Ý nghĩa |
|---|---|
| `stock_qty = EXCLUDED.stock_qty` | **Thay thế** tồn kho hiện có bằng giá trị mới |
| `stock_qty = p.stock_qty + EXCLUDED.stock_qty` | **Cộng dồn** lượng nhập vào tồn kho hiện có |
| `price = EXCLUDED.price` | Dùng giá được gửi trong bản ghi mới |
| `updated_at = CURRENT_TIMESTAMP` | Ghi dấu thời gian ở nhánh **UPDATE** |

**Cảnh báo idempotency:** mẫu cộng dồn **không an toàn nếu cùng phiếu nhập được gửi lại** mà không có khóa sự kiện riêng. Upsert theo SKU với `SET stock_qty = stock_qty + delta` sẽ cộng thêm lần nữa ở lần retry. Với dữ liệu tài chính/tồn kho, cần khóa định danh sự kiện, bảng ledger hoặc cơ chế chống xử lý lại, thay vì nghĩ `ON CONFLICT` tự làm mọi cập nhật trở thành idempotent.

### 5.4. Alias bảng đích giúp tránh nhầm lẫn

Có thể viết:

```sql
INSERT INTO demo_products AS p (sku, product_name, price)
VALUES ('P-102', 'Keyboard', 990)
ON CONFLICT (sku) DO UPDATE
SET price = EXCLUDED.price,
    updated_at = CURRENT_TIMESTAMP
WHERE p.price IS DISTINCT FROM EXCLUDED.price;
```

Alias `p` giúp phân biệt hàng đang có (`p.price`) với hàng được đề xuất (`EXCLUDED.price`). Trong PostgreSQL, khi dùng alias cho bảng đích, hãy dùng alias đó trong các tham chiếu cần thiết.

Tên `EXCLUDED` có ý nghĩa đặc biệt trong phần upsert. Nếu một bảng thật trùng tên `excluded`, việc đặt alias khác để tránh xung đột tên là cần thiết.

## 6. DO UPDATE ... WHERE: cập nhật có điều kiện

Đôi khi không muốn mọi lần import đều ghi đè hàng cũ. Ví dụ: chỉ chấp nhận dữ liệu đến từ **phiên bản mới hơn**.

Bảng mẫu có cột `version_no`. Truy vấn:

```sql
INSERT INTO demo_products AS p
    (sku, product_name, price, stock_qty, version_no)
VALUES
    ('P-102', 'Older Keyboard',  850.00, 5, 2),
    ('P-104', 'Monitor 4K',     4900.00, 3, 4),
    ('P-108', 'Docking Station', 1700.00, 2, 2)
ON CONFLICT (sku) DO UPDATE
SET product_name = EXCLUDED.product_name,
    price        = EXCLUDED.price,
    stock_qty    = EXCLUDED.stock_qty,
    version_no   = EXCLUDED.version_no,
    updated_at   = CURRENT_TIMESTAMP
WHERE p.version_no < EXCLUDED.version_no
RETURNING sku, version_no, price;
```

Giả sử đã chạy ví dụ phần 5 để `P-102` có `version_no = 3`:

| SKU | Phiên bản đang có | Phiên bản đến | Tác động |
|---|---:|---:|---|
| P-102 | 3 | 2 | **Không cập nhật** vì 3 không nhỏ hơn 2 |
| P-104 | 1 | 4 | **Cập nhật** lên phiên bản 4 |
| P-108 | Chưa có | 2 | **Chèn** hàng mới |

`WHERE` trong nhánh `DO UPDATE` được xét **khi đã xác định hàng xung đột**. Nếu điều kiện sai, PostgreSQL **không cập nhật hàng xung đột đó**, và hàng đó không xuất hiện trong `RETURNING`. Đáng chú ý, hàng xung đột có thể **vẫn bị khóa** trong quá trình kiểm tra, dù điều kiện `WHERE` cuối cùng không cập nhật.

### 6.1. Hai WHERE hoàn toàn khác nhau

So sánh:

```sql
-- WHERE của conflict target: chọn loại unique index thích hợp.
ON CONFLICT (tenant_id, user_id)
    WHERE deleted_at IS NULL
DO UPDATE SET ...

-- WHERE của hành động UPDATE: quyết định có cập nhật hàng khớp không.
ON CONFLICT (sku)
DO UPDATE SET version_no = EXCLUDED.version_no
WHERE p.version_no < EXCLUDED.version_no
```

Chúng khác về **vị trí, mục đích và thời điểm áp dụng**:

- `WHERE` ngay sau `ON CONFLICT (columns)` là **index predicate** để suy luận một **partial unique index** phù hợp.
- `WHERE` sau `DO UPDATE SET ...` là **điều kiện lọc hành động cập nhật** đối với hàng đang có.

Đừng dùng `WHERE p.version_no < EXCLUDED.version_no` trong conflict target: `EXCLUDED` không có cùng ý nghĩa/khả năng tham chiếu ở vị trí khai báo unique index predicate.

### 6.2. Không cần UPDATE nếu các giá trị không đổi

Nếu chỉ muốn tránh ghi lại khi dữ liệu giống hệt:

```sql
INSERT INTO demo_products AS p (sku, product_name, price)
VALUES ('P-101', 'Mouse', 350.00)
ON CONFLICT (sku) DO UPDATE
SET product_name = EXCLUDED.product_name,
    price = EXCLUDED.price,
    updated_at = CURRENT_TIMESTAMP
WHERE
    (p.product_name, p.price)
    IS DISTINCT FROM
    (EXCLUDED.product_name, EXCLUDED.price);
```

`IS DISTINCT FROM` là phép so sánh có kết quả boolean rõ ràng ngay cả khi hai vế có `NULL`, khác với `<>` có thể trả `UNKNOWN`. Bảng mẫu đã khai báo tên/giá `NOT NULL`, nhưng mẫu này hữu ích hơn khi làm việc với những cột được phép thiếu.

Nếu giá trị không khác nhau, không cập nhật và không làm mới `updated_at`. Đây có thể là chủ đích khi muốn giảm update dư thừa, phát sinh trigger/audit không cần thiết và lưu lượng replication.

**Tuy nhiên**, nếu nghiệp vụ yêu cầu đánh dấu lần nhận bản tin mới ngay cả khi nội dung giữ nguyên, không nên bỏ UPDATE; hãy lựa chọn theo hợp đồng dữ liệu.

## 7. Conflict target: PostgreSQL biết khóa nào gây xung đột bằng cách nào?

### 7.1. Suy luận unique index theo cột

Dạng thường dùng:

```sql
ON CONFLICT (sku) DO UPDATE SET ...
```

PostgreSQL tìm **unique index phù hợp** với danh sách cột/biểu thức đã nêu để làm **arbiter** (cơ chế phân xử xung đột). Với bảng mẫu, ràng buộc `uq_demo_products_sku` tạo ra unique index cần thiết cho `sku`.

Ưu điểm của kiểu viết bằng cột:

- Diễn đạt khóa nghiệp vụ rõ.
- Không phụ thuộc cứng vào một tên constraint cụ thể.
- Trong nhiều tình huống phù hợp, vẫn hoạt động nếu một unique index được thay thế bởi index khác **tương đương**, ví dụ khi xây lại index.

`ON CONFLICT (sku)` không có nghĩa “tìm mọi index có chứa `sku` ở vị trí đầu”. Nếu unique index duy nhất là trên **cặp `(tenant_id, sku)`**, chỉ ghi `(sku)` thường không đủ để PostgreSQL tìm một arbiter thích hợp.

### 7.2. Dùng tên constraint bằng ON CONSTRAINT

Bảng mẫu đã đặt tên ràng buộc:

```sql
CONSTRAINT uq_demo_products_sku UNIQUE (sku)
```

Vì vậy có thể viết:

```sql
INSERT INTO demo_products (sku, product_name, price)
VALUES ('P-101', 'Mouse', 350.00)
ON CONFLICT ON CONSTRAINT uq_demo_products_sku
DO UPDATE SET price = EXCLUDED.price;
```

Dạng này chỉ rõ **tên constraint**, hữu ích khi code muốn bám chính xác ràng buộc nghiệp vụ đã đặt tên. Đổi tên hoặc thay thế constraint có thể buộc code chỉnh theo.

**Phân biệt:** `ON CONFLICT ON CONSTRAINT ...` yêu cầu **tên constraint** phù hợp. Một **unique index độc lập**, nhất là **partial unique index**, không nhất thiết có một constraint cùng tên để chỉ định bằng cú pháp này.

### 7.3. Khóa ghép nhiều cột

Với hệ thống đa tổ chức, SKU có thể chỉ duy nhất **trong từng tenant**.

```sql
CREATE TEMP TABLE demo_tenant_products (
    tenant_id INTEGER NOT NULL,
    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,
    price NUMERIC(12,2) NOT NULL CHECK (price >= 0),
    PRIMARY KEY (tenant_id, sku)
);
```

Upsert đúng khóa ghép:

```sql
INSERT INTO demo_tenant_products AS p
    (tenant_id, sku, product_name, price)
VALUES
    (10, 'P-001', 'Mouse Tenant 10', 350),
    (20, 'P-001', 'Mouse Tenant 20', 390)
ON CONFLICT (tenant_id, sku) DO UPDATE
SET product_name = EXCLUDED.product_name,
    price = EXCLUDED.price;
```

Hai hàng cùng SKU nhưng khác tenant **không xung đột** vì khóa chính là cặp `(tenant_id, sku)`. Những lần nhập sau trong tenant 10 chỉ nên cập nhật sản phẩm thuộc tenant 10.

Không viết `ON CONFLICT (sku)` trên schema chỉ có `PRIMARY KEY (tenant_id, sku)` rồi mong PostgreSQL tự suy ra tenant hiện tại. Cần đủ **các thành phần của khóa** để ngăn lẫn dữ liệu.

### 7.4. Unique expression index: ví dụ email không phân biệt hoa/thường

Giả sử nghiệp vụ coi `'User@Example.Test'` và `'user@example.test'` là cùng email theo quy tắc chuẩn hóa của ứng dụng.

```sql
CREATE TEMP TABLE demo_contacts (
    contact_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL,
    display_name TEXT NOT NULL
);

CREATE UNIQUE INDEX ux_demo_contacts_email_ci
ON demo_contacts ((lower(email)));

INSERT INTO demo_contacts (email, display_name)
VALUES ('User@Example.Test', 'Initial user');

INSERT INTO demo_contacts AS c (email, display_name)
VALUES ('user@example.test', 'Updated user')
ON CONFLICT (lower(email)) DO UPDATE
SET display_name = EXCLUDED.display_name
RETURNING contact_id, email, display_name;
```

Ở đây arbiter là **biểu thức `lower(email)`**, không phải trực tiếp `email`. Hàng có email khác kiểu chữ vẫn xung đột theo unique expression index; thao tác cập nhật `display_name` nhưng **không nhất thiết thay đổi cách viết email đã lưu**.

Cần cân nhắc collation, chuẩn hóa Unicode, quy tắc miền email và địa phương hóa trước khi tuyên bố `lower(email)` là chính sách nhận dạng email hoàn chỉnh. Mục đích ví dụ là minh họa **unique index trên biểu thức** và conflict target tương ứng.

## 8. Partial unique index: upsert trong tập con có điều kiện

Một quy tắc phổ biến: mỗi người dùng trong một tenant được có **tối đa một subscription chưa xóa mềm**, nhưng lịch sử các subscription đã xóa được phép có nhiều hàng.

Ta có bảng:

```sql
CREATE TEMP TABLE demo_subscriptions (
    subscription_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    plan_name TEXT NOT NULL,
    deleted_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX ux_demo_live_subscription
ON demo_subscriptions (tenant_id, user_id)
WHERE deleted_at IS NULL;
```

Chỉ những hàng `deleted_at IS NULL` mới thuộc unique index này. Hàng đã soft-delete không ngăn một hàng active khác cùng `(tenant_id, user_id)` được tạo.

### 8.1. ON CONFLICT với predicate của partial index

```sql
INSERT INTO demo_subscriptions AS s
    (tenant_id, user_id, plan_name, deleted_at)
VALUES (10, 100, 'PRO', NULL)
ON CONFLICT (tenant_id, user_id)
    WHERE deleted_at IS NULL
DO UPDATE
SET plan_name = EXCLUDED.plan_name
RETURNING subscription_id, tenant_id, user_id, plan_name;
```

Nếu đã tồn tại một subscription **chưa xóa** cho cặp (10,100), PostgreSQL cập nhật `plan_name`. Nếu chỉ còn lịch sử có `deleted_at IS NOT NULL`, một hàng active mới được chèn.

**Quan trọng:** `WHERE deleted_at IS NULL` sau conflict target là **predicate dùng để suy luận partial unique index**. Nó không phải điều kiện riêng để quyết định cập nhật dữ liệu của hàng đã xung đột.

### 8.2. Tại sao không dùng ON CONSTRAINT tên index này?

`ux_demo_live_subscription` là một **unique index độc lập với điều kiện `WHERE`**, không phải ràng buộc `UNIQUE` thông thường có thể gọi bằng `ON CONSTRAINT`. Hình thức thường dùng ở đây là **chỉ ra cột và predicate** trong conflict target, như ví dụ.

### 8.3. Cẩn trọng khi bảng có thêm unique index khác

Nếu cùng bảng còn có một unique index **không partial** trên đúng cặp `(tenant_id, user_id)`, cấu trúc index/constraint đó sẽ cấm cả các bản ghi lịch sử trùng cặp, trái mục đích soft delete. Khi suy luận arbiter, PostgreSQL có quy tắc về những unique index phù hợp, trong đó một unique index không partial cũng có thể được suy luận trong những trường hợp có conflict target predicate.

Do đó thiết kế schema phải **thể hiện đúng quy tắc duy nhất** trước khi viết upsert; thêm một predicate vào `ON CONFLICT` không thể sửa một ràng buộc unique tổng quát đặt sai.

## 9. NULL và UNIQUE: không phải mọi giá trị thiếu đều xung đột

Trên PostgreSQL, ràng buộc `UNIQUE` thông thường mặc định cho phép **nhiều giá trị `NULL`** ở cột được phép thiếu, vì `NULL` được xử lý khác giá trị cụ thể trong quy tắc duy nhất.

```sql
CREATE TEMP TABLE demo_external_refs (
    ref_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_code TEXT UNIQUE,
    description TEXT NOT NULL
);

INSERT INTO demo_external_refs (external_code, description)
VALUES
    (NULL, 'Imported without code A'),
    (NULL, 'Imported without code B')
ON CONFLICT (external_code) DO UPDATE
SET description = EXCLUDED.description;
```

Cả hai hàng có thể được chèn vì `external_code = NULL` không bị unique constraint mặc định coi là một khóa trùng nhau.

### 9.1. PostgreSQL 15+: UNIQUE NULLS NOT DISTINCT

Nếu nghiệp vụ muốn **chỉ một hàng có khóa `NULL`**, PostgreSQL 15 trở lên hỗ trợ:

```sql
-- PostgreSQL 15+
CREATE TEMP TABLE demo_nullable_codes (
    item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_code TEXT,
    note TEXT,
    CONSTRAINT uq_demo_nullable_code
        UNIQUE NULLS NOT DISTINCT (external_code)
);
```

Với ràng buộc này, hai hàng có cùng `external_code NULL` được xem là **xung đột unique** theo chính sách `NULLS NOT DISTINCT`:

```sql
INSERT INTO demo_nullable_codes (external_code, note)
VALUES (NULL, 'First note')
ON CONFLICT (external_code) DO UPDATE
SET note = EXCLUDED.note;

INSERT INTO demo_nullable_codes (external_code, note)
VALUES (NULL, 'Updated note')
ON CONFLICT (external_code) DO UPDATE
SET note = EXCLUDED.note;
```

Sau hai câu, chỉ có **một** hàng chứa `external_code NULL` với note mới theo ràng buộc này.

**Lưu ý phiên bản:** không dùng `UNIQUE NULLS NOT DISTINCT` nếu PostgreSQL thấp hơn 15. Trước khi chọn mô hình khóa nullable, cân nhắc liệu mã nghiệp vụ thiếu có nên được phép hay không; đôi khi `NOT NULL` và một cơ chế nhận dạng rõ ràng tốt hơn một khóa có `NULL`.

### 9.2. Khóa ghép có NULL

Với `UNIQUE (tenant_id, external_code)`, nếu `external_code` có thể `NULL`, PostgreSQL mặc định có thể cho phép nhiều hàng cùng `tenant_id` với `external_code NULL`. Không giả định khóa ghép mặc nhiên coi `NULL` là bằng nhau. Nếu nghiệp vụ cần uniqueness mạnh với giá trị thiếu, thiết kế `NOT NULL` hoặc `NULLS NOT DISTINCT` khi phù hợp phiên bản và mục đích.

## 10. Xung đột nào ON CONFLICT xử lý được?

`ON CONFLICT` của PostgreSQL dựa vào các **unique indexes/constraints phù hợp** làm arbiter:

- `PRIMARY KEY` thông thường được bảo vệ bằng unique index.
- `UNIQUE` thông thường được bảo vệ bằng unique index.
- Unique expression index hoặc partial unique index có thể được suy luận nếu conflict target phù hợp.
- `DO NOTHING` có khả năng xử lý một số xung đột ràng buộc loại **exclusion** trong phạm vi PostgreSQL hỗ trợ.
- `DO UPDATE` **không dùng exclusion constraints làm arbiter**.
- Các ràng buộc **deferrable** không được hỗ trợ làm arbiter của `ON CONFLICT` theo cơ chế thông thường của PostgreSQL.

Ngoài ra, `ON CONFLICT` **không phải** cách xử lý tự động cho mọi `FOREIGN KEY`, `CHECK`, `NOT NULL`, lỗi kiểu, lỗi trigger hoặc RLS. Những lỗi độc lập đó vẫn có thể xảy ra.

### 10.1. Nếu chỉ có index thường, không có unique index

```sql
CREATE TEMP TABLE demo_labels (
    label_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    label_name TEXT NOT NULL
);

CREATE INDEX idx_demo_labels_name ON demo_labels(label_name);
```

`idx_demo_labels_name` là index **không unique**. Câu sau không có arbiter phù hợp cho `label_name`:

```sql
-- Không có UNIQUE(label_name), nên DO UPDATE theo tên không hợp lệ.
INSERT INTO demo_labels (label_name)
VALUES ('important')
ON CONFLICT (label_name) DO UPDATE
SET label_name = EXCLUDED.label_name;
```

PostgreSQL không suy ra “trùng khóa nghiệp vụ” chỉ từ một index tìm kiếm bình thường. Nếu tên nhãn phải duy nhất, trước hết cần định nghĩa **unique constraint/index** phù hợp.

### 10.2. Nếu xung đột khóa khác với target được nêu

Một bảng có hai unique constraints riêng, ví dụ `username` và `email`:

```sql
CREATE TEMP TABLE demo_users (
    user_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE
);

INSERT INTO demo_users (username, email)
VALUES ('an', 'an@example.test');
```

Giả sử dùng:

```sql
INSERT INTO demo_users (username, email)
VALUES ('other', 'an@example.test')
ON CONFLICT (username) DO UPDATE
SET email = EXCLUDED.email;
```

`username = 'other'` chưa trùng, nhưng `email = 'an@example.test'` đã trùng. Vì câu SQL chỉ xử lý xung đột theo **`username`**, xung đột `email` vẫn có thể làm lệnh **báo lỗi `UNIQUE`**.

Tương tự, ngay cả khi một hàng xung đột ở đúng arbiter và được cập nhật, phần `SET` có thể tạo vi phạm một unique constraint khác, CHECK hay FK và làm câu lệnh thất bại. Upsert không phải giấy phép bỏ qua toàn bộ ràng buộc.

### 10.3. DO NOTHING không có target trong bảng nhiều UNIQUE

```sql
INSERT INTO demo_users (username, email)
VALUES ('other', 'an@example.test')
ON CONFLICT DO NOTHING
RETURNING user_id;
```

Không chỉ định target nghĩa là PostgreSQL có thể bỏ qua hàng vì xung đột unique trên `email`. Truy vấn trả **không có hàng `RETURNING`** trong trường hợp này.

Nhưng “bỏ qua nếu xung đột ở **bất kỳ** unique key nào” có thể không phù hợp nghiệp vụ: email trùng nhưng username khác có thể là dữ liệu cần điều tra, thay vì âm thầm bỏ qua. Hãy xác định rõ chính sách của từng khóa.

## 11. RETURNING: biết hàng nào thực sự được tác động

PostgreSQL hỗ trợ `RETURNING` sau `INSERT ... ON CONFLICT`:

```sql
INSERT INTO demo_products (sku, product_name, price)
VALUES
    ('P-101', 'Mouse', 350),
    ('P-110', 'USB Hub', 480)
ON CONFLICT (sku) DO NOTHING
RETURNING product_id, sku, product_name;
```

Nếu `P-101` đã có, chỉ hàng chèn mới `P-110` được trả. Đây là cách ứng dụng biết **hàng nào đã chèn** trong chính câu lệnh.

Với `DO UPDATE`:

```sql
INSERT INTO demo_products AS p (sku, product_name, price)
VALUES
    ('P-101', 'Mouse v2', 380),
    ('P-111', 'Desk Lamp',  620)
ON CONFLICT (sku) DO UPDATE
SET product_name = EXCLUDED.product_name,
    price = EXCLUDED.price
RETURNING product_id, sku, product_name, price;
```

Kết quả gồm các hàng **được chèn hoặc được cập nhật**. Nhưng trong mẫu `RETURNING product_id, sku,...` này **không có cột nào tự động chỉ rõ nhánh INSERT hay UPDATE**.

### 11.1. Không phụ thuộc vào thứ tự RETURNING

Không được suy rằng các dòng `RETURNING` chắc chắn xuất theo đúng thứ tự các nhóm `VALUES`, hoặc ID auto-generated chắc chắn tăng liên tiếp để ánh xạ từng dòng nguồn. Trong xử lý nhập dữ liệu, dùng **`sku`/khóa nghiệp vụ hoặc correlation key** để đối chiếu.

### 11.2. DO UPDATE WHERE không thỏa: không có RETURNING

```sql
INSERT INTO demo_products AS p
    (sku, product_name, price, version_no)
VALUES ('P-102', 'Older name', 100, 1)
ON CONFLICT (sku) DO UPDATE
SET product_name = EXCLUDED.product_name,
    price = EXCLUDED.price,
    version_no = EXCLUDED.version_no
WHERE p.version_no < EXCLUDED.version_no
RETURNING sku, version_no;
```

Nếu `P-102` đã có phiên bản 2 hoặc 3, điều kiện sai nên hàng đó **không được cập nhật và không có dòng trả về**. Một tập `RETURNING` rỗng có thể là do tất cả bị bỏ qua bằng `DO NOTHING` hoặc do điều kiện `DO UPDATE WHERE` đều sai; ứng dụng phải hiểu câu lệnh mình đã gửi để diễn giải.

### 11.3. Tránh dựa vào cột hệ thống để phân biệt insert/update

Đôi khi gặp mẹo `RETURNING (xmax = 0) AS inserted` để suy đoán nhánh xử lý dựa trên cột hệ thống của PostgreSQL. Đây là cách gắn nghiệp vụ vào **chi tiết MVCC nội bộ**, không phải hợp đồng portable/ổn định để mô tả loại thao tác. Khi cần audit đáng tin, nên thiết kế cờ nghiệp vụ, bảng event, trigger/audit hoặc dùng tính năng truy xuất dữ liệu trước/sau phù hợp với phiên bản PostgreSQL cụ thể.

## 12. Một câu INSERT nhiều hàng và bẫy duplicate nội bộ

Đây là tình huống rất quan trọng khi nhập dữ liệu hàng loạt.

```sql
INSERT INTO demo_products AS p
    (sku, product_name, price)
VALUES
    ('P-120', 'Item A', 100),
    ('P-120', 'Item B', 200)
ON CONFLICT (sku) DO UPDATE
SET product_name = EXCLUDED.product_name,
    price = EXCLUDED.price;
```

Hai hàng đầu vào cùng `sku = 'P-120'`. Với `DO UPDATE`, PostgreSQL không cho một câu lệnh upsert **tác động cùng một hàng đích nhiều lần**. Nó có thể báo lỗi dạng:

```text
ON CONFLICT DO UPDATE command cannot affect row a second time
```

Đây là lỗi **cardinality violation** (thường SQLSTATE `21000`). Nó có thể xảy ra ngay cả khi trước đó `P-120` chưa có trong bảng, vì hàng đầu tiên được chèn rồi hàng tiếp theo muốn dùng cùng câu lệnh để cập nhật chính hàng ấy.

**Đừng giả định “nhóm VALUES phía sau thắng”** với `DO UPDATE`. PostgreSQL yêu cầu bạn xử lý duplicate ngay trong tập đầu vào hoặc tách thành các câu phù hợp.

### 12.1. DO NOTHING khác DO UPDATE khi nguồn có duplicate

Với `DO NOTHING`, một hàng trùng có thể được bỏ qua mà không yêu cầu cập nhật cùng hàng lần hai. Nhưng nếu cần chọn **bản ghi nào** của nhóm duplicate là hợp lệ, phải đưa logic chọn đó vào **truy vấn nguồn**.

### 12.2. Dùng ROW_NUMBER để khử trùng trước upsert

Giả sử có bảng staging chứa nhiều dòng cho cùng SKU, mỗi dòng có số thứ tự nguồn:

```sql
CREATE TEMP TABLE demo_product_stage (
    source_line_no INTEGER PRIMARY KEY,
    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,
    price NUMERIC(12,2) NOT NULL,
    stock_qty INTEGER NOT NULL,
    version_no INTEGER NOT NULL
);

INSERT INTO demo_product_stage
    (source_line_no, sku, product_name, price, stock_qty, version_no)
VALUES
    (1, 'P-130', 'Lamp old',  500, 4, 1),
    (2, 'P-130', 'Lamp new',  650, 5, 2),
    (3, 'P-131', 'Speaker',  990, 3, 1),
    (4, 'P-102', 'Keyboard patch', 975, 8, 4);
```

Chọn **phiên bản cao nhất**, và nếu cùng phiên bản thì `source_line_no` lớn hơn:

```sql
WITH ranked AS (
    SELECT
        s.*,
        ROW_NUMBER() OVER (
            PARTITION BY s.sku
            ORDER BY s.version_no DESC, s.source_line_no DESC
        ) AS rn
    FROM demo_product_stage AS s
),
selected AS (
    SELECT sku, product_name, price, stock_qty, version_no
    FROM ranked
    WHERE rn = 1
)
INSERT INTO demo_products AS p
    (sku, product_name, price, stock_qty, version_no)
SELECT sku, product_name, price, stock_qty, version_no
FROM selected
WHERE TRUE
ON CONFLICT (sku) DO UPDATE
SET product_name = EXCLUDED.product_name,
    price = EXCLUDED.price,
    stock_qty = EXCLUDED.stock_qty,
    version_no = EXCLUDED.version_no,
    updated_at = CURRENT_TIMESTAMP
WHERE p.version_no < EXCLUDED.version_no
RETURNING sku, product_name, version_no;
```

Giải thích:

1. `ROW_NUMBER() PARTITION BY sku` chia các dòng theo mã sản phẩm.
2. `ORDER BY version_no DESC, source_line_no DESC` chọn một dòng đại diện **có quy tắc**.
3. `WHERE rn = 1` bảo đảm nhiều nhất một hàng nguồn cho mỗi SKU.
4. `INSERT ... SELECT` chèn dữ liệu đã làm sạch về số lượng.
5. `ON CONFLICT (sku) DO UPDATE` chỉ cập nhật khi phiên bản đến **mới hơn** phiên bản đang lưu.
6. `RETURNING` liệt kê những hàng thực sự được chèn hoặc cập nhật.

`WHERE TRUE` sau `FROM selected` ở đây là một cách viết tường minh để phần `ON CONFLICT` không bị diễn giải nhầm như cú pháp liên quan `JOIN ... ON` trong những dạng `INSERT ... SELECT` phức tạp. Khi đã có `WHERE rn = 1` trực tiếp ở `SELECT`, không cần thêm điều kiện này; nó chỉ làm rõ cấu trúc trong ví dụ có CTE `selected`.

### 12.3. Đừng dùng DISTINCT khi bản ghi có cột khác nhau

`SELECT DISTINCT sku, product_name, price, ...` không gộp hai dòng `P-130` thành một nếu tên hoặc giá khác nhau. Muốn **một dòng mỗi SKU**, phải xác định dòng thắng theo nghiệp vụ rồi dùng `ROW_NUMBER()`, `DISTINCT ON` của PostgreSQL hoặc một chiến lược nhóm rõ ràng.

Ví dụ PostgreSQL `DISTINCT ON`:

```sql
SELECT DISTINCT ON (sku)
    sku, product_name, price, stock_qty, version_no
FROM demo_product_stage
ORDER BY sku, version_no DESC, source_line_no DESC;
```

Kết quả chỉ một hàng trên mỗi `sku`, với dòng phiên bản mới hơn được chọn. Đây là lựa chọn khác cho giai đoạn **dedup nguồn**, không phải một cú pháp của `ON CONFLICT` tự xử lý tie-break.

## 13. INSERT ... SELECT và ON CONFLICT

Upsert không giới hạn dữ liệu nguồn ở `VALUES`. PostgreSQL cho phép:

```sql
INSERT INTO demo_products AS p
    (sku, product_name, price, stock_qty, version_no)
SELECT
    s.sku,
    s.product_name,
    s.price,
    s.stock_qty,
    s.version_no
FROM demo_product_stage AS s
WHERE s.source_line_no >= 3
ON CONFLICT (sku) DO UPDATE
SET product_name = EXCLUDED.product_name,
    price = EXCLUDED.price,
    stock_qty = EXCLUDED.stock_qty,
    version_no = EXCLUDED.version_no
WHERE p.version_no < EXCLUDED.version_no;
```

Điểm cần nhớ:

- `INSERT ... SELECT` có thể chèn **0, 1 hoặc nhiều** dòng.
- `ON CONFLICT` áp dụng cho những hàng được truy vấn `SELECT` đưa vào.
- Nếu nhiều hàng `SELECT` tạo cùng khóa đích, lỗi **một hàng bị DO UPDATE hai lần** vẫn có thể xảy ra.
- Điều kiện trong `SELECT WHERE` **lọc dòng nguồn**.
- Điều kiện trong `DO UPDATE WHERE` **lọc hành động cập nhật ở hàng xung đột**.

### 13.1. Cẩn trọng cú pháp ON sau INSERT ... SELECT

PostgreSQL có thể gặp sự mơ hồ cú pháp giữa `ON CONFLICT` và `JOIN ... ON` trong một số dạng `INSERT ... SELECT`. Tài liệu PostgreSQL khuyên thêm một `WHERE` vào `SELECT`, thậm chí `WHERE TRUE` nếu không cần lọc, để bộ phân tích cú pháp nhận ra ranh giới:

```sql
INSERT INTO demo_products (sku, product_name, price)
SELECT sku, product_name, price
FROM demo_product_stage
WHERE TRUE
ON CONFLICT (sku) DO NOTHING;
```

Đây là một chi tiết khá thực dụng khi sinh SQL tự động; `WHERE TRUE` không làm thay đổi tập hàng, chỉ giúp cấu trúc câu rõ ràng trong trường hợp này.

### 13.2. Nếu dữ liệu đầu vào có lỗi CHECK/FK

Dù `ON CONFLICT DO UPDATE` có thể cập nhật SKU đã có, các hàng nguồn vẫn cần kiểu hợp lệ, ràng buộc phù hợp và giá trị có thể đưa vào nhánh thao tác tương ứng. Một dòng có `price = -1` không được “sửa lỗi” chỉ vì SKU đã có. Cần kiểm tra dữ liệu ở staging và tách hàng lỗi theo quy tắc nhập liệu.

## 14. Upsert idempotent và bài toán xử lý lại sự kiện

Trong hệ thống có retry, **idempotent** nghĩa là gửi lại cùng một yêu cầu hợp lệ không làm thay đổi kết quả nghiệp vụ theo cách không mong muốn.

### 14.1. Gán giá trị tuyệt đối có thể idempotent

```sql
INSERT INTO demo_products AS p
    (sku, product_name, price, stock_qty, version_no)
VALUES ('P-140', 'Office Chair', 2000.00, 5, 10)
ON CONFLICT (sku) DO UPDATE
SET product_name = EXCLUDED.product_name,
    price = EXCLUDED.price,
    stock_qty = EXCLUDED.stock_qty,
    version_no = EXCLUDED.version_no
WHERE p.version_no < EXCLUDED.version_no;
```

Nếu chạy lần đầu, hàng được chèn. Chạy lại cùng giá trị với cùng phiên bản, `WHERE p.version_no < EXCLUDED.version_no` sai, nên không cập nhật lần hai. Cách này phù hợp với chính sách **phiên bản chỉ tăng**, miễn là phiên bản nguồn được quản lý đúng.

### 14.2. Cộng dồn không tự idempotent

```sql
INSERT INTO demo_products AS p
    (sku, product_name, price, stock_qty)
VALUES ('P-103', 'USB Cable', 120.00, 3)
ON CONFLICT (sku) DO UPDATE
SET stock_qty = p.stock_qty + EXCLUDED.stock_qty;
```

Chạy lại cùng câu sẽ cộng tiếp **3 đơn vị** vào tồn kho; hoàn toàn có thể sai nếu đó chỉ là một sự kiện nhập kho bị retry.

Cách thiết kế đáng tin hơn là có **bảng sự kiện nhập kho với `event_id` duy nhất** và quy trình đảm bảo một event chỉ được áp dụng một lần vào số dư. Nếu muốn dùng `ON CONFLICT DO NOTHING` cho event_id, phải đặt việc ghi sự kiện và cập nhật số dư trong một giao dịch được đồng bộ đúng; không đơn giản tách thành hai câu độc lập rồi cho rằng “event được bỏ qua” chắc chắn ngăn cập nhật cộng dồn.

### 14.3. Đồng bộ theo phiên bản thay vì đồng hồ nhận dữ liệu

Khi dữ liệu đến không theo thứ tự, ví dụ phiên bản 4 đến trước phiên bản 3, dùng:

```sql
WHERE p.version_no < EXCLUDED.version_no
```

để chỉ chấp nhận bản mới hơn. Nếu dùng `updated_at` như điều kiện, phải xác định timestamp được phát ở nguồn nào, độ tin cậy, múi giờ và cách xử lý đồng hạng. **Timestamp DB lúc nhận** không tự tương đương phiên bản nghiệp vụ ở nguồn.

## 15. Cạnh tranh ghi và tính nguyên tử của ON CONFLICT

PostgreSQL xử lý upsert dưới cơ chế kiểm tra unique index và đồng bộ các hàng liên quan. Hãy xét hai phiên cùng chạy:

```sql
INSERT INTO demo_products (sku, product_name, price)
VALUES ('P-200', 'Item', 100)
ON CONFLICT (sku) DO UPDATE
SET price = EXCLUDED.price;
```

Nếu trước đó `P-200` chưa tồn tại, một phiên có thể chèn trước, phiên còn lại phát hiện xung đột và cập nhật theo chính sách. Không cần `SELECT` kiểm tra tồn tại trước làm điều kiện tiên quyết.

### 15.1. Bảo đảm của DO UPDATE không có nghĩa không thể có lỗi

Mặc dù `ON CONFLICT DO UPDATE` cung cấp kết quả chèn hoặc cập nhật theo cơ chế atomic của PostgreSQL trong trường hợp thông thường, câu SQL **vẫn có thể lỗi** vì:

- `NOT NULL`, `CHECK`, `FOREIGN KEY` hoặc unique constraint khác.
- Trùng nhiều hàng nguồn gây lỗi cardinality `21000`.
- Deadlock hoặc serialization failure.
- Lỗi trigger hoặc hàm được gọi trong biểu thức.
- Quyền `INSERT/UPDATE/SELECT` không đủ, hoặc chính sách Row-Level Security.
- Cấu trúc partition/schema không hỗ trợ hành vi cần thực hiện.

Đừng viết code “upsert luôn thành công và không bao giờ phải bắt lỗi”.

### 15.2. READ COMMITTED và hàng chưa nhìn thấy trong snapshot

Một đặc điểm đáng chú ý của PostgreSQL là trong mức cô lập **READ COMMITTED**, `ON CONFLICT DO UPDATE` có thể cập nhật hàng xung đột do giao dịch đồng thời tạo ra **ngay cả khi hàng ấy chưa nhìn thấy trong snapshot thông thường của câu `SELECT`** tại lúc bắt đầu câu lệnh, sau khi cơ chế đồng bộ và chờ giao dịch liên quan xử lý.

Với `ON CONFLICT DO NOTHING`, một hàng có thể bị bỏ qua vì xung đột từ giao dịch đồng thời, dù hàng ấy chưa hiển thị trong một snapshot đọc thông thường ở thời điểm đó. Do vậy không nên suy “không có dòng trong RETURNING = chắc chắn đã thấy dòng tồn tại từ trước câu lệnh”.

### 15.3. DO UPDATE WHERE có thể khóa hàng dù không cập nhật

PostgreSQL xác định hàng xung đột trước, rồi xét điều kiện `WHERE` của nhánh update. Một hàng được xác định làm ứng viên xung đột có thể **bị khóa** ngay cả khi điều kiện `WHERE` sai và không có bản cập nhật.

Với throughput cao, những upsert lặp cùng khóa vẫn có thể tạo tranh chấp khóa dù đa số bị bộ lọc phiên bản bỏ qua. Cần đo trên workload thật, không nhìn số hàng UPDATE bằng 0 rồi kết luận không có tác động đồng thời.

### 15.4. Deadlock và retry

Hai phiên có thể xử lý nhiều khóa theo thứ tự khác nhau:

```text
Phiên A: cập nhật SKU A → chờ SKU B
Phiên B: cập nhật SKU B → chờ SKU A
```

Nếu DBMS phát hiện deadlock, một giao dịch có thể bị hủy (PostgreSQL thường dùng SQLSTATE `40P01`). Ở mức cô lập Serializable cũng có thể gặp `40001` (*serialization_failure*).

Các biện pháp hữu ích:

- Nhập/upsert các khóa theo **thứ tự xác định** khi có nhiều khóa trong một giao dịch.
- Giữ giao dịch ngắn và chỉ xử lý dữ liệu cần thiết.
- Có chiến lược **retry toàn bộ transaction** khi gặp lỗi có thể retry, với giới hạn số lần/thời gian.
- Bảo đảm thao tác được retry **idempotent** về nghiệp vụ.
- Không chỉ retry lại câu cuối của một transaction đã bị PostgreSQL đánh dấu thất bại.

### 15.5. Mức cô lập không biến upsert thành distributed transaction

Một `INSERT ... ON CONFLICT` bảo vệ các ràng buộc trong cơ sở dữ liệu PostgreSQL theo phạm vi transaction. Nó không tự điều phối nguyên tử với việc gửi email, đẩy Kafka hay ghi sang hệ thống ngoài. Nếu upsert và phát sự kiện phải cùng cam kết, cân nhắc **transactional outbox** hoặc cơ chế tương đương phù hợp hệ thống.

## 16. Trigger, DEFAULT, generated column và EXCLUDED

### 16.1. DEFAULT được tính ở hàng đề xuất chèn

Giả sử `updated_at` có default `CURRENT_TIMESTAMP`. Khi câu `INSERT` không truyền `updated_at`, giá trị mặc định được dùng cho **nhánh chèn mới**.

Nhưng nếu hàng `sku` đã tồn tại và rẽ sang **DO UPDATE**, không có quy tắc rằng default của `updated_at` tự động được áp lại vào hàng cũ. Muốn cập nhật dấu thời gian khi update:

```sql
ON CONFLICT (sku) DO UPDATE
SET price = EXCLUDED.price,
    updated_at = CURRENT_TIMESTAMP
```

Nếu muốn hàng bị bỏ qua bởi `DO NOTHING` không thay đổi timestamp, đó chính là kết quả của việc không thực hiện update.

### 16.2. BEFORE INSERT trigger ảnh hưởng đến EXCLUDED

Trong PostgreSQL, kết quả của **row-level `BEFORE INSERT` trigger** có thể được phản ánh vào hàng `EXCLUDED` khi quyết định nhánh `DO UPDATE`.

Ví dụ ứng dụng dùng một trigger chuẩn hóa SKU thành chữ hoa trước khi chèn; các giá trị được đề xuất dùng để phát hiện xung đột và `EXCLUDED.sku` có thể đã mang giá trị được chuẩn hóa theo trigger. Vì vậy đừng hiểu `EXCLUDED` chỉ là “chuỗi JSON raw client gửi ban đầu” bất kể trigger.

### 16.3. Trigger của INSERT và UPDATE có thể đều liên quan

Upsert có thể đi theo đường chèn hoặc xung đột cập nhật, nên cả các loại trigger phù hợp với **INSERT** và **UPDATE** có thể tham gia theo quy tắc của PostgreSQL. Với trigger cấp câu lệnh, thứ tự và thời điểm kích hoạt còn có quy tắc riêng, kể cả khi số hàng thực sự cập nhật là 0 trong một số tình huống.

Nếu hệ thống dùng trigger để tăng version, viết audit hoặc phát thông điệp, phải kiểm tra hành vi của **upsert**, không chỉ test `INSERT` đơn lẻ rồi giả định chính xác cùng số lượt trigger.

### 16.4. Identity/sequence không đồng nghĩa “không có khoảng trống”

Bảng `demo_products` dùng `GENERATED ALWAYS AS IDENTITY`. Trong một `INSERT ... ON CONFLICT`, PostgreSQL có thể tiêu thụ giá trị sequence cho hàng được đề xuất chèn **trước khi xác định nhánh xung đột**. Vì vậy ngay cả `DO NOTHING` hoặc `DO UPDATE` cũng có thể tạo **khoảng trống ID**, không phải lỗi dữ liệu.

Không suy ra số hàng chèn từ chênh lệch `MAX(product_id)` trước/sau. Dùng `RETURNING`, affected row count và khóa nghiệp vụ để đối soát.

## 17. Phân biệt ON CONFLICT với MERGE

PostgreSQL hỗ trợ `MERGE` từ phiên bản **15**. Cả `MERGE` và `INSERT ... ON CONFLICT` đều có thể giải quyết những trường hợp dữ liệu nguồn có thể đã tồn tại, nhưng **không phải cú pháp thay thế tương đương trong mọi tình huống**.

| Tiêu chí | `INSERT ... ON CONFLICT` | `MERGE` |
|---|---|---|
| Ý tưởng chính | Thử chèn, xử lý xung đột unique của hàng được đề xuất | Ghép nguồn và đích theo điều kiện rồi xử lý nhánh matched/not matched |
| Cách xác định khớp | Unique index/constraint làm arbiter | Điều kiện `ON` của `MERGE` |
| Hành động thường dùng | `DO NOTHING`, `DO UPDATE` | Có thể có các nhánh `INSERT`/`UPDATE`/`DELETE` tùy phiên bản |
| Bảo đảm khi cạnh tranh ghi | `DO UPDATE` có bảo đảm atomic insert-or-update cụ thể của PostgreSQL | Không nên coi có cùng bảo đảm concurrency như `ON CONFLICT` |
| Phạm vi cú pháp | Tập trung vào INSERT và unique conflict | Tổng quát hơn cho đồng bộ dữ liệu nguồn–đích |
| Khi phù hợp | Upsert theo khóa duy nhất đã định nghĩa rõ | Quy trình đồng bộ nhiều nhánh điều kiện, có quy tắc matched/not matched |

Ví dụ `ON CONFLICT` được dùng nhiều cho bảng khách, sản phẩm, bản ghi đồng bộ có khóa nghiệp vụ duy nhất. `MERGE` có thể thuận tiện cho luồng staging với logic đa nhánh, nhưng cần kiểm tra cardinality, hành vi concurrent và giới hạn phiên bản.

**Không thay một upsert đang dựa vào atomic unique conflict bằng MERGE chỉ vì “hai lệnh đều là upsert”** mà không xem lại yêu cầu cạnh tranh ghi và kết quả mong muốn.

## 18. Khác biệt với MySQL, SQLite và SQL Server

Cùng khái niệm upsert nhưng các DBMS có cú pháp và quy tắc riêng:

| DBMS | Cú pháp thường gặp | Điểm cần nhớ |
|---|---|---|
| **PostgreSQL** | `INSERT ... ON CONFLICT (key) DO UPDATE SET ...` | Arbiter dựa trên unique index/constraint; có `EXCLUDED` |
| **SQLite** | `INSERT ... ON CONFLICT (...) DO UPDATE ...` ở phiên bản hỗ trợ | Cú pháp tương tự PostgreSQL ở mức ý tưởng nhưng không hoàn toàn giống mọi chi tiết, đặc biệt nhiều nhánh/xử lý constraint |
| **MySQL/MariaDB** | `INSERT ... ON DUPLICATE KEY UPDATE ...` | Xử lý dựa vào xung đột unique/primary key; không chọn mục tiêu arbiter giống `ON CONFLICT (key)` PostgreSQL |
| **SQL Server** | DML với kiểm soát giao dịch, `MERGE` hoặc giải pháp update/insert có locking phù hợp | Không có cú pháp `INSERT ... ON CONFLICT` PostgreSQL |
| **Oracle** | `MERGE` hoặc quy trình SQL/PLSQL dùng constraint phù hợp | Không dùng `EXCLUDED` PostgreSQL |

### 18.1. Không sao chép EXCLUDED sang MySQL

Ví dụ PostgreSQL:

```sql
INSERT INTO demo_products (sku, product_name, price)
VALUES ('P-101', 'Mouse New', 400)
ON CONFLICT (sku) DO UPDATE
SET price = EXCLUDED.price;
```

MySQL sử dụng `ON DUPLICATE KEY UPDATE` với cú pháp truy cập dữ liệu đề xuất riêng theo phiên bản, không sử dụng nguyên văn `EXCLUDED.price` ở cùng vị trí. Các phiên bản MySQL gần đây có thay đổi khuyến nghị đối với `VALUES(column)` và dùng alias hàng đề xuất. Khi chuyển ứng dụng, chọn SQL theo đúng dialect/phiên bản.

### 18.2. SQLite có cú pháp giống nhưng không đồng nhất về ràng buộc

SQLite hỗ trợ upsert với `ON CONFLICT` ở các phiên bản hiện đại, nhưng cấu trúc unique index, hành vi trigger, transaction/locking và cơ chế xử lý lỗi khác PostgreSQL. Không dùng câu “SQLite cũng có ON CONFLICT” để kết luận mọi tính năng như unique expression/partial inference, `RETURNING`, MVCC và concurrency đều giống PostgreSQL.

### 18.3. Không xử lý lỗi bằng cách bắt 23505 rồi UPDATE một cách sơ sài

Một ứng dụng có thể định viết:

```text
try INSERT
catch duplicate key -> UPDATE
```

Cách này cần quản lý transaction, unique constraint, cạnh tranh ghi, retry và các lỗi khác rất cẩn thận. Khi bài toán chính là upsert dựa trên unique key của PostgreSQL, **`INSERT ... ON CONFLICT` thường rõ nghĩa và an toàn hơn** một luồng “bắt lỗi rồi cập nhật” thủ công không có chiến lược khóa.

## 19. Upsert trong Java/JDBC

Ứng dụng Java có thể dùng `PreparedStatement` để gửi một câu upsert tham số hóa:

```java
String sql = """
    INSERT INTO products AS p
        (sku, product_name, price, stock_qty, version_no)
    VALUES (?, ?, ?, ?, ?)
    ON CONFLICT (sku) DO UPDATE
    SET product_name = EXCLUDED.product_name,
        price = EXCLUDED.price,
        stock_qty = EXCLUDED.stock_qty,
        version_no = EXCLUDED.version_no,
        updated_at = CURRENT_TIMESTAMP
    WHERE p.version_no < EXCLUDED.version_no
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, product.sku());
    ps.setString(2, product.name());
    ps.setBigDecimal(3, product.price());
    ps.setInt(4, product.stockQty());
    ps.setInt(5, product.versionNo());

    int affected = ps.executeUpdate();
    // Thường 1 nếu có INSERT/UPDATE thực sự;
    // 0 khi xung đột nhưng WHERE của DO UPDATE không thỏa.
}
```

Đoạn mã minh họa: `connection` và `product` là biến được ứng dụng quản lý, và bảng `products` cần có các cột/ràng buộc phù hợp. `PreparedStatement` tránh nối trực tiếp dữ liệu người dùng vào SQL và chuyển đúng kiểu giá/phiên bản.

### 19.1. Affected rows không nói đầy đủ “nhánh nào” xảy ra

Với câu upsert chỉ chèn hoặc cập nhật một hàng:

- Nếu một hàng được chèn, affected rows thường là **1**.
- Nếu hàng cũ được cập nhật, affected rows thường cũng là **1**.
- Nếu xung đột nhưng điều kiện `DO UPDATE WHERE` sai, affected rows có thể là **0**.
- Với multi-row input, tổng affected rows có thể thấp hơn số hàng đề xuất.

Đừng xem affected rows = 1 là bằng chứng **chèn mới**, vì có thể là **cập nhật**.

### 19.2. SQL injection và khóa nghiệp vụ

Không xây câu upsert bằng cách nối SKU/giá vào SQL literal:

```java
// Không an toàn; chỉ minh họa điều cần tránh.
String sql = "INSERT INTO products(sku) VALUES ('" + userInput + "')";
```

Dùng tham số của `PreparedStatement` và kiểm tra các trường bắt buộc. Ngay cả khi SQL không thể bị injection, một khóa nghiệp vụ chưa được chuẩn hóa vẫn có thể tạo nhiều biến thể không mong muốn (khoảng trắng, chữ hoa/thường, Unicode); quy tắc chuẩn hóa phải tương thích với unique index đang bảo vệ dữ liệu.

### 19.3. Batch upsert cũng có giới hạn

Nếu gửi hàng nghìn sản phẩm qua JDBC batch hoặc `INSERT ... VALUES (...), (...)`, cần:

- Tính số bind parameters của mỗi statement.
- Chọn kích thước batch theo driver, PostgreSQL và khối lượng dữ liệu.
- Khử trùng **SKU trong cùng một statement DO UPDATE** trước khi gửi.
- Đặt ranh giới transaction, bắt lỗi và retry hợp lý.
- Kiểm tra `RETURNING`/affected rows để đối soát.
- Không giả định thứ tự ID sinh theo hàng đầu vào.

JDBC batch với nhiều lần execute cùng statement một hàng không nhất thiết gây lỗi `21000` chỉ vì SKU trùng giữa các lần gọi; lỗi đó đặc biệt quan trọng khi **một câu INSERT ... ON CONFLICT DO UPDATE** chứa nhiều hàng cùng khóa. Dù vậy, cập nhật nhiều lần theo cùng khóa qua nhiều statement có thể có tác dụng nghiệp vụ khác và cần kiểm soát thứ tự.

## 20. Quyền truy cập, RLS và bảo mật

Một câu upsert có thể cần những quyền khác nhau:

- `INSERT` trên các cột được chèn.
- `UPDATE` trên các cột được gán bởi `DO UPDATE`.
- `SELECT` trên các cột được đọc trong biểu thức `SET`, `WHERE` và `RETURNING` theo quy tắc PostgreSQL.

Ví dụ:

```sql
SET stock_qty = p.stock_qty + EXCLUDED.stock_qty
```

không chỉ ghi `stock_qty` mà còn **đọc giá trị hiện có** `p.stock_qty`. Trình điều khiển hoặc role DB cần có quyền phù hợp với biểu thức đang thực hiện.

Nếu bảng có **Row-Level Security (RLS)**, upsert phải tuân thủ các chính sách áp dụng cho thao tác chèn/cập nhật và đọc dữ liệu theo cơ chế PostgreSQL. `ON CONFLICT` không bỏ qua quyền tenant hay chính sách bảo vệ dữ liệu.

### 20.1. Khóa tenant phải nằm trong arbiter đúng phạm vi

Giả sử trong hệ đa tenant, mỗi tenant có thể dùng SKU `P-001`. Khi đó unique key hợp lý có thể là:

```sql
UNIQUE (tenant_id, sku)
```

và câu upsert:

```sql
ON CONFLICT (tenant_id, sku) DO UPDATE ...
```

Không đặt unique key chỉ trên `sku` nếu nghiệp vụ cho phép trùng giữa tenant. Đồng thời phải đảm bảo `tenant_id` được lấy từ bối cảnh server được ủy quyền, không tin một giá trị do client tự gửi. Upsert theo khóa ghép không tự hoàn thành việc kiểm soát quyền.

### 20.2. Một unique index có thể tiết lộ sự tồn tại của dữ liệu

Trong môi trường nhiều quyền/tenant, lỗi unique constraint hoặc hành vi `ON CONFLICT` có thể cho thấy một khóa đã tồn tại dù người dùng không có quyền xem trực tiếp hàng đó. Vì vậy cần thiết kế unique keys, thông báo lỗi, RLS và API trả về phù hợp, tránh biến upsert thành đường dò email/tài khoản không được phép.

## 21. Hiệu năng và cách kiểm tra kế hoạch

`ON CONFLICT` không miễn phí: nó phải kiểm tra unique index, có thể chờ khóa, thực hiện `UPDATE`, ghi WAL, cập nhật chỉ mục và kích hoạt trigger.

### 21.1. Những yếu tố tác động hiệu năng

- **Tỷ lệ insert mới so với update:** nhiều xung đột update có thể tạo nhiều phiên bản hàng và áp lực VACUUM.
- **Một khóa bị cập nhật quá thường xuyên:** tranh chấp khóa hàng.
- **Số unique indexes:** mỗi index bổ sung có chi phí kiểm tra/duy trì.
- **Số cột bị UPDATE:** cập nhật không cần thiết tăng WAL/trigger/replication.
- **Số hàng trong statement:** batch quá lớn tăng thời gian giao dịch và khó phân tích lỗi.
- **Lượng dữ liệu trong `RETURNING`:** trả nhiều cột lớn có thể tăng chi phí mạng.
- **Chỉ mục trên các biểu thức/partial index:** có thể phù hợp nghiệp vụ nhưng cần xem chi phí cập nhật và điều kiện suy luận index.
- **Tính idempotent:** retry một lô cộng dồn không chỉ tốn tài nguyên mà còn có thể làm sai số liệu.

### 21.2. Tránh update khi dữ liệu giống hệt

Ví dụ:

```sql
INSERT INTO demo_products AS p
    (sku, product_name, price, stock_qty)
VALUES ('P-101', 'Mouse', 350.00, 10)
ON CONFLICT (sku) DO UPDATE
SET product_name = EXCLUDED.product_name,
    price = EXCLUDED.price,
    stock_qty = EXCLUDED.stock_qty,
    updated_at = CURRENT_TIMESTAMP
WHERE
    (p.product_name, p.price, p.stock_qty)
    IS DISTINCT FROM
    (EXCLUDED.product_name, EXCLUDED.price, EXCLUDED.stock_qty);
```

Đoạn này giảm một số UPDATE không cần thiết; nhưng vẫn phải giải quyết xung đột/khóa và có thể có chi phí truy cập. Đồng thời phải bảo đảm không vô ý bỏ một cập nhật bắt buộc như ghi “last_seen_at”.

### 21.3. EXPLAIN của INSERT phải cẩn thận

```sql
EXPLAIN
INSERT INTO demo_products (sku, product_name, price)
VALUES ('P-TEST', 'Test', 100)
ON CONFLICT (sku) DO NOTHING;
```

`EXPLAIN` thông thường cho kế hoạch dự kiến mà không thực thi thay đổi.

```sql
EXPLAIN (ANALYZE, BUFFERS)
INSERT INTO demo_products (sku, product_name, price)
VALUES ('P-TEST', 'Test', 100)
ON CONFLICT (sku) DO NOTHING;
```

`EXPLAIN ANALYZE` **thực thi câu INSERT thật**. Nếu muốn đo trong môi trường thử có thể hoàn tác, dùng một transaction có `ROLLBACK`, nhưng cần hiểu rằng sequence/identity có thể tiêu thụ số và những tác dụng phụ ngoại vi không phải lúc nào rollback theo dữ liệu.

Ở các phiên bản PostgreSQL phù hợp, plan có thể cho thông tin như `Conflict Resolution`, `Conflict Arbiter Indexes`, số tuple inserted/conflicting, nhưng tên/chi tiết hiển thị phụ thuộc phiên bản. Không đo hiệu năng chỉ bằng thời gian của một câu trên bảng tạm có vài hàng.

## 22. Những lỗi thường gặp

| Sai lầm | Vì sao sai hoặc nguy hiểm? | Cách xử lý |
|---|---|---|
| Viết `ON CONFLICT (sku)` khi chưa có `UNIQUE(sku)` | Không tìm được arbiter phù hợp | Tạo đúng unique constraint/index |
| Dùng `DO UPDATE` nhưng bỏ conflict target | PostgreSQL yêu cầu chỉ rõ mục tiêu cho DO UPDATE | Dùng `ON CONFLICT (sku)` hoặc `ON CONSTRAINT ...` |
| Nghĩ `ON CONFLICT DO NOTHING` bỏ qua CHECK/FK/NOT NULL | Vẫn có thể lỗi các ràng buộc khác | Kiểm tra đầu vào và xử lý lỗi rõ |
| Nghĩ `EXCLUDED` là hàng cũ | Nhầm giá trị dùng cập nhật | `EXCLUDED` = hàng đề xuất, alias đích = hàng đang có |
| Chỉ ghi `ON CONFLICT DO UPDATE` rồi mong mọi cột đổi | Chỉ các cột `SET` mới được cập nhật | Gán tường minh cột cần đổi |
| Cộng tồn kho bằng `p.stock_qty + EXCLUDED.stock_qty` rồi retry | Cùng sự kiện bị cộng nhiều lần | Dùng event ID/idempotency/ledger |
| Một statement DO UPDATE có hai hàng cùng SKU | Có thể lỗi cardinality `21000` | Dedup nguồn theo quy tắc trước khi insert |
| `SELECT DISTINCT sku, price` để dedup theo SKU | Giá khác nhau vẫn tạo nhiều hàng | `ROW_NUMBER`/`DISTINCT ON` theo khóa và thứ tự |
| `DO UPDATE WHERE` sai thì tưởng hàng được bỏ khóa hoàn toàn | Có thể vẫn khóa hàng xung đột | Đo lock contention và thiết kế batch |
| Dùng `ON CONFLICT DO NOTHING` không target trên bảng nhiều unique | Có thể âm thầm bỏ hàng vì khóa ngoài ý định | Nêu conflict target đúng nghiệp vụ |
| Bảng nhiều tenant chỉ unique theo SKU | Trộn/xung đột dữ liệu giữa tenant | `UNIQUE(tenant_id, sku)`, điều kiện quyền đầy đủ |
| Nghĩ `UNIQUE` mặc định coi hai `NULL` trùng | PostgreSQL thường cho nhiều NULL | Dùng NOT NULL hoặc NULLS NOT DISTINCT theo phiên bản |
| Dùng `ON CONSTRAINT` để chỉ tên partial unique index | Partial index không phải constraint tương ứng | Dùng inference với columns + predicate |
| Nghĩ DO UPDATE tự làm mới `updated_at DEFAULT` | Default của INSERT không tự cập nhật nhánh UPDATE | `SET updated_at = CURRENT_TIMESTAMP` |
| Dựa vào IDENTITY liên tiếp hoặc thứ tự RETURNING | Sequence có gap và output order không nên là khóa mapping | Dùng SKU/correlation key |
| Cho rằng `RETURNING` rỗng luôn là lỗi | DO NOTHING/WHERE false có thể không trả hàng | Kiểm tra chính sách và affected count |
| Bắt `23505` rồi retry UPDATE trong transaction đã lỗi | PostgreSQL có thể đánh dấu transaction thất bại | Dùng ON CONFLICT hoặc rollback/savepoint phù hợp |
| Coi `MERGE` và ON CONFLICT có cùng bảo đảm cạnh tranh | Ngữ nghĩa/concurrency không đồng nhất | Chọn theo nghiệp vụ và docs phiên bản |
| Dùng JDBC string concat với SKU người dùng | SQL injection/quote lỗi | PreparedStatement bind tham số |
| Tối ưu bằng bỏ unique index | Mất lớp bảo vệ chống trùng | Đo thật, giữ ràng buộc nghiệp vụ |

## 23. Bài tập thực hành có đáp án

### Bài 1. Bỏ qua SKU đã có

**Yêu cầu:** chèn `P-101` nếu chưa có; nếu đã có thì không sửa giá. Viết PostgreSQL.

**Đáp án:**

```sql
INSERT INTO demo_products (sku, product_name, price)
VALUES ('P-101', 'Mouse', 350)
ON CONFLICT (sku) DO NOTHING;
```

Vì `P-101` đã tồn tại trong dữ liệu mẫu, câu lệnh không cập nhật nó.

### Bài 2. Upsert giá mới

**Yêu cầu:** chèn `P-102` với tên `Mechanical Keyboard`, giá 975; nếu trùng SKU thì cập nhật cả tên và giá, giữ nguyên tồn kho.

**Đáp án:**

```sql
INSERT INTO demo_products (sku, product_name, price)
VALUES ('P-102', 'Mechanical Keyboard', 975)
ON CONFLICT (sku) DO UPDATE
SET product_name = EXCLUDED.product_name,
    price = EXCLUDED.price;
```

`stock_qty` không nằm trong `SET` nên không bị thay đổi chỉ bởi upsert này.

### Bài 3. Cộng dồn tồn kho

**Yêu cầu:** nhận thêm 5 USB Cable (SKU `P-103`), cộng vào tồn kho đã lưu.

**Đáp án:**

```sql
INSERT INTO demo_products AS p (sku, product_name, price, stock_qty)
VALUES ('P-103', 'USB Cable', 120, 5)
ON CONFLICT (sku) DO UPDATE
SET stock_qty = p.stock_qty + EXCLUDED.stock_qty;
```

**Hỏi thêm:** gửi lại lệnh hai lần có an toàn không? **Không** nếu cùng sự kiện nhập được áp dụng hai lần; cần event ID/idempotency.

### Bài 4. Chỉ chấp nhận phiên bản mới

**Yêu cầu:** hàng `P-104` chỉ được cập nhật nếu phiên bản mới lớn hơn phiên bản đang lưu.

**Đáp án:**

```sql
INSERT INTO demo_products AS p
    (sku, product_name, price, version_no)
VALUES ('P-104', 'Monitor Updated', 4600, 5)
ON CONFLICT (sku) DO UPDATE
SET product_name = EXCLUDED.product_name,
    price = EXCLUDED.price,
    version_no = EXCLUDED.version_no
WHERE p.version_no < EXCLUDED.version_no;
```

Nếu version hiện tại là 5 hoặc 6, update bị bỏ qua. Nếu bản ghi chưa tồn tại, nó được chèn với version 5.

### Bài 5. Dự đoán lỗi cardinality

```sql
INSERT INTO demo_products (sku, product_name, price)
VALUES ('P-501', 'A', 100),
       ('P-501', 'B', 200)
ON CONFLICT (sku) DO UPDATE
SET price = EXCLUDED.price;
```

**Đáp án:** một statement có hai hàng nguồn cùng SKU và muốn tác động một hàng đích nhiều lần. PostgreSQL có thể báo lỗi `ON CONFLICT DO UPDATE command cannot affect row a second time` (cardinality violation). Cần dedup trước và chọn A/B theo quy tắc rõ.

### Bài 6. UNIQUE thiếu

**Yêu cầu:** bảng có `sku TEXT` nhưng không có UNIQUE/PK trên sku. Dùng `ON CONFLICT (sku) DO UPDATE` có hợp lệ không?

**Đáp án:** không; PostgreSQL không tìm được arbiter unique phù hợp. Nếu SKU phải là khóa nghiệp vụ, cần thêm `UNIQUE(sku)` sau khi xử lý dữ liệu trùng hiện có.

### Bài 7. Khóa ghép theo tenant

**Yêu cầu:** bảng có `UNIQUE(tenant_id, sku)`, viết conflict target đúng.

**Đáp án:**

```sql
ON CONFLICT (tenant_id, sku) DO UPDATE
SET price = EXCLUDED.price
```

Không dùng `ON CONFLICT (sku)` vì SKU chỉ duy nhất **trong từng tenant**.

### Bài 8. Partial unique index

**Yêu cầu:** chỉ có một subscription chưa xóa mềm trên mỗi `(tenant_id, user_id)`. Index nào thích hợp và conflict target ra sao?

**Đáp án:**

```sql
CREATE UNIQUE INDEX ux_demo_live_subscription
ON demo_subscriptions (tenant_id, user_id)
WHERE deleted_at IS NULL;
```

```sql
INSERT INTO demo_subscriptions AS s
    (tenant_id, user_id, plan_name, deleted_at)
VALUES (10, 100, 'TEAM', NULL)
ON CONFLICT (tenant_id, user_id)
    WHERE deleted_at IS NULL
DO UPDATE
SET plan_name = EXCLUDED.plan_name;
```

Predicate trong conflict target là điều kiện chọn partial unique index, không phải `WHERE` của nhánh `DO UPDATE`.

### Bài 9. RETURNING với DO NOTHING

**Tình huống:** `P-101` đã có, `P-999` chưa có. Một `INSERT` chứa hai SKU và `ON CONFLICT (sku) DO NOTHING RETURNING sku`.

**Đáp án:** `RETURNING` chỉ chứa **P-999** nếu không có lỗi độc lập, vì `P-101` bị bỏ qua và không tạo thao tác chèn/cập nhật.

### Bài 10. NULL và UNIQUE

**Câu hỏi:** một cột `external_code TEXT UNIQUE` cho phép `NULL`. Hai câu chèn `external_code = NULL` có bắt buộc kích hoạt conflict trong PostgreSQL không?

**Đáp án:** không. Với `UNIQUE` mặc định, nhiều `NULL` được cho phép. PostgreSQL 15+ có `UNIQUE NULLS NOT DISTINCT` nếu nghiệp vụ muốn coi `NULL` là giá trị xung đột.

### Bài 11. ON CONFLICT không xử lý mọi ràng buộc

**Tình huống:** sản phẩm mới có `price = -10`, SKU chưa có. Gửi `ON CONFLICT DO NOTHING` có tự bỏ qua không?

**Đáp án:** không. Bảng mẫu có `CHECK(price >= 0)`; đây không phải xung đột unique được `ON CONFLICT DO NOTHING` xử lý. Lệnh có thể báo lỗi CHECK.

### Bài 12. Batch staging có SKU trùng

**Yêu cầu:** dùng bảng `demo_product_stage`, chọn một dòng có `version_no` lớn nhất theo SKU; nếu version bằng nhau, chọn `source_line_no` lớn hơn.

**Đáp án:**

```sql
WITH ranked AS (
    SELECT s.*,
           ROW_NUMBER() OVER (
               PARTITION BY sku
               ORDER BY version_no DESC, source_line_no DESC
           ) AS rn
    FROM demo_product_stage s
)
SELECT sku, product_name, price, stock_qty, version_no
FROM ranked
WHERE rn = 1
ORDER BY sku;
```

Dùng kết quả truy vấn này làm nguồn `INSERT ... SELECT ... ON CONFLICT ...`, tránh cho cùng một statement DO UPDATE gặp hai hàng cùng khóa.

### Bài 13. Phân biệt INSERT và UPDATE từ số hàng tác động

**Câu hỏi:** JDBC `executeUpdate()` trả 1 sau một câu `INSERT ... ON CONFLICT DO UPDATE` chỉ có một hàng đầu vào. Có kết luận đó là bản ghi mới không?

**Đáp án:** không. Affected rows = 1 có thể tương ứng **một INSERT** hoặc **một UPDATE**. Nếu ứng dụng cần phân biệt, phải thiết kế cách ghi/đọc trạng thái thao tác có hợp đồng rõ ràng, không suy chỉ từ số hàng.

### Bài 14. Vì sao hai giao dịch cùng INSERT không cần SELECT trước?

**Đáp án:** unique index của PostgreSQL là cơ chế phân xử xung đột tại DB, và `ON CONFLICT` được tích hợp trong chính câu `INSERT`. `SELECT` trước rồi `INSERT` tạo khoảng thời gian để hai phiên cùng kết luận “chưa có” và gây race; upsert tránh yêu cầu quyết định kiểu đó ở ứng dụng, nhưng vẫn cần xử lý những lỗi khác và retry giao dịch khi thích hợp.

## 24. Tóm tắt nguyên tắc sử dụng an toàn

Trước khi chọn `INSERT ... ON CONFLICT`, hãy trả lời lần lượt:

1. **Khóa nghiệp vụ là gì?** Một `sku`, một `email` đã chuẩn hóa, hay cặp `(tenant_id, sku)`?
2. **Schema có unique arbiter đúng hay chưa?** `PRIMARY KEY`, `UNIQUE`, unique expression index hoặc partial unique index phù hợp?
3. **Nếu trùng thì phải làm gì?** Giữ nguyên (`DO NOTHING`), thay thế các giá trị (`DO UPDATE SET col = EXCLUDED.col`), hay tính từ dữ liệu cũ (`SET col = p.col + EXCLUDED.col`)?
4. **Có cần điều kiện phiên bản hay thay đổi thực sự?** Dùng `DO UPDATE ... WHERE` khi quy tắc rõ, nhớ rằng hàng có thể vẫn bị khóa.
5. **Batch có trùng khóa nội bộ không?** Nếu có, xử lý trước để một câu `DO UPDATE` không tác động cùng hàng hai lần.
6. **Kết quả ứng dụng cần gì?** `RETURNING`/affected rows, correlation key để ghép, báo lỗi/ràng buộc và xử lý bỏ qua.
7. **Có cạnh tranh ghi và retry không?** Giữ transaction hợp lý, thiết kế idempotency, xử lý deadlock/serialization failure.
8. **Có khóa tenant, quyền, RLS và audit không?** Upsert không vượt qua các yêu cầu bảo mật và nhất quán khác.

**Kết luận:** `INSERT ... ON CONFLICT` là cơ chế upsert mạnh của PostgreSQL vì gắn hành động chèn/cập nhật trực tiếp với **ràng buộc duy nhất**. `DO NOTHING` phù hợp khi gặp khóa trùng thì giữ dữ liệu hiện có; `DO UPDATE` phù hợp khi cần cập nhật có chủ đích bằng `EXCLUDED` và dữ liệu hàng đích. Muốn sử dụng đúng trong hệ thống thật, cần phân biệt **conflict target**, **điều kiện `DO UPDATE WHERE`**, **unique/partial index**, **dữ liệu NULL**, **batch duplicate**, **RETURNING** và **hành vi đồng thời**. Đừng xem upsert là giải pháp tự động cho mọi lỗi INSERT hoặc mọi lần retry: tính đúng bắt đầu từ **khóa nghiệp vụ và chính sách cập nhật được định nghĩa rõ**.

