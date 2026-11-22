# INSERT INTO SELECT và ánh xạ cột nguồn, đích trong SQL

Trong chương **Thêm dữ liệu**, câu lệnh `INSERT INTO` không chỉ dùng để nhập từng dòng bằng `VALUES`. Bạn còn có thể **lấy những dòng do một câu `SELECT` tạo ra rồi chèn vào bảng đích**. Mẫu này đặc biệt hữu ích khi chuyển dữ liệu từ bảng nhập thô (*staging*) sang bảng nghiệp vụ, sao chép dữ liệu có điều kiện, tạo bảng lưu trữ, hoặc tổng hợp dữ liệu vào bảng báo cáo.

Tuy nhiên, một câu `INSERT INTO ... SELECT ...` có thể chạy thành công mà **ghi nhầm dữ liệu vào cột**, nếu bạn hiểu sai cách ánh xạ. Điều quan trọng nhất cần ghi nhớ:

> **Các biểu thức ở `SELECT` được gán cho các cột trong danh sách `INSERT INTO (...)` theo vị trí, từ trái sang phải — không theo tên hay bí danh cột nguồn.**

Bài học này giải thích cú pháp, thứ tự cột nguồn–đích, biểu thức biến đổi, kiểu dữ liệu, `DEFAULT`, khóa tự sinh, ràng buộc, giao dịch, cách tránh nhập trùng và phương pháp kiểm tra trước khi ghi. Phần lớn ví dụ chạy trên **PostgreSQL**; các nguyên tắc cốt lõi áp dụng cho nhiều hệ quản trị SQL, còn những cú pháp riêng được chỉ rõ.

## 1. Từ INSERT VALUES đến INSERT SELECT

### 1.1. Thêm một dòng bằng VALUES

```sql
INSERT INTO customers (customer_id, customer_name)
VALUES (1, 'An');
```

Ở đây dữ liệu được viết trực tiếp dưới dạng **giá trị cụ thể**. Với nhiều dòng:

```sql
INSERT INTO customers (customer_id, customer_name)
VALUES
    (1, 'An'),
    (2, 'Bình');
```

`VALUES` phù hợp khi bạn đã có sẵn các giá trị cần thêm.

### 1.2. Thêm những dòng do truy vấn tạo ra

```sql
INSERT INTO destination_table (
    destination_col_1,
    destination_col_2,
    destination_col_3
)
SELECT
    source_expression_1,
    source_expression_2,
    source_expression_3
FROM source_table
WHERE some_condition;
```

Câu `SELECT` là **nguồn dữ liệu** của câu `INSERT`:

1. `SELECT` xác định tập dòng cần chèn.
2. Mỗi dòng kết quả `SELECT` tạo **một dòng được đề nghị chèn** vào bảng đích.
3. Giá trị thứ nhất của `SELECT` đi vào `destination_col_1`, giá trị thứ hai đi vào `destination_col_2`, v.v.
4. Hệ quản trị kiểm tra kiểu dữ liệu, `NOT NULL`, khóa chính, khóa ngoại, `UNIQUE`, `CHECK` và những quy tắc khác áp dụng cho bảng đích.
5. Dòng đáp ứng điều kiện ghi sẽ được chèn; nếu có lỗi, kết quả của câu lệnh phụ thuộc hệ quản trị, engine lưu trữ và giao dịch đang dùng.

Đặc biệt: **không viết `VALUES` trước `SELECT`** trong mẫu này.

```sql
-- Sai cú pháp cho mẫu INSERT ... SELECT:
INSERT INTO destination_table (col1, col2)
VALUES SELECT col1, col2 FROM source_table;
```

Dạng đúng là:

```sql
INSERT INTO destination_table (col1, col2)
SELECT col1, col2
FROM source_table;
```

### 1.3. Những bài toán thường dùng

| Nhu cầu | Nguồn của `SELECT` | Bảng đích |
|---|---|---|
| Chuyển đơn hàng đã kiểm tra | Bảng staging có bộ lọc | Bảng đơn hàng chuẩn |
| Lưu trữ các đơn đã hoàn thành | Bảng đơn đang hoạt động | Bảng archive |
| Sao chép khách hàng thuộc một vùng | Bảng khách hàng kèm `WHERE` | Bảng phục vụ một tác vụ |
| Tạo báo cáo tổng hợp theo tháng | Truy vấn `GROUP BY` | Bảng tổng hợp |
| Chuyển đổi cấu trúc dữ liệu cũ | Nhiều bảng `JOIN`/`CASE`/`CAST` | Schema mới |
| Khởi tạo bảng quan hệ | Truy vấn ghép khóa và dữ liệu | Bảng liên kết |

**`INSERT SELECT` chèn kết quả đã chọn**, chứ không tự sao chép toàn bộ ràng buộc, khóa, chỉ mục hay thiết kế của bảng nguồn sang bảng đích. Bảng đích phải tồn tại và có cấu trúc phù hợp.

## 2. Ánh xạ cột theo vị trí là quy tắc quan trọng nhất

Xét một bảng đích:

```sql
CREATE TABLE lesson264_mapping_demo (
    code VARCHAR(30) NOT NULL,
    label VARCHAR(30) NOT NULL,
    quantity INTEGER NOT NULL
);
```

Giả sử nguồn là tập dữ liệu tạo bằng CTE:

```sql
WITH source_data AS (
    SELECT
        'P-101'::VARCHAR AS source_code,
        'Sách SQL'::VARCHAR AS source_label,
        3::INTEGER AS source_qty
)
SELECT
    source_code,
    source_label,
    source_qty
FROM source_data;
```

Giờ chèn vào bảng đích:

```sql
WITH source_data AS (
    SELECT
        'P-101'::VARCHAR AS source_code,
        'Sách SQL'::VARCHAR AS source_label,
        3::INTEGER AS source_qty
)
INSERT INTO lesson264_mapping_demo (
    code,
    label,
    quantity
)
SELECT
    source_code,
    source_label,
    source_qty
FROM source_data;
```

Kết quả có một dòng `('P-101', 'Sách SQL', 3)`.

### 2.1. Tên cột nguồn có thể khác tên cột đích

Không bắt buộc nguồn có tên `code`, `label` và `quantity`. Bạn có thể viết:

```sql
INSERT INTO lesson264_mapping_demo (
    code,
    label,
    quantity
)
SELECT
    s.product_ref,       -- Vị trí 1 → code.
    s.product_title,     -- Vị trí 2 → label.
    s.qty               -- Vị trí 3 → quantity.
FROM some_source_table AS s;
```

Đây là **minh họa ánh xạ**, không chạy trực tiếp vì chưa tạo bảng `some_source_table`.

`source.product_ref` không cần có tên giống `destination.code`. Điều kiện là **giá trị có ý nghĩa nghiệp vụ phù hợp và kiểu có thể ghi vào cột đích**.

### 2.2. Đổi thứ tự cột đích thì phải đổi tương ứng ở SELECT

Câu dưới cũng hợp lệ và cho cùng ánh xạ nghiệp vụ:

```sql
WITH source_data AS (
    SELECT
        'P-102'::VARCHAR AS product_code,
        'Bút chì'::VARCHAR AS product_label,
        5::INTEGER AS qty
)
INSERT INTO lesson264_mapping_demo (
    quantity,
    code,
    label
)
SELECT
    qty,             -- quantity đứng thứ nhất ở danh sách đích.
    product_code,    -- code đứng thứ hai.
    product_label    -- label đứng thứ ba.
FROM source_data;
```

**Thứ tự cột đích do bạn khai báo**, không nhất thiết trùng thứ tự cột vật lý trong bảng. Nhưng các biểu thức `SELECT` phải theo đúng thứ tự đã khai báo.

### 2.3. Bí danh AS không quyết định cột đích

Xem ví dụ cố tình đảo hai cột `VARCHAR`:

```sql
-- Ví dụ SAI về nghiệp vụ, không chạy:
INSERT INTO lesson264_mapping_demo (code, label, quantity)
SELECT
    'Sách SQL' AS label,
    'P-103' AS code,
    3 AS quantity;
```

Hệ quản trị gán:

| Vị trí | Cột đích | Biểu thức SELECT | Giá trị nhận |
|---:|---|---|---|
| 1 | `code` | `'Sách SQL' AS label` | `Sách SQL` |
| 2 | `label` | `'P-103' AS code` | `P-103` |
| 3 | `quantity` | `3 AS quantity` | `3` |

Vì hai cột đầu đều chấp nhận chuỗi, lỗi này **có thể không bị hệ quản trị phát hiện**. Đây là lý do ánh xạ theo **vị trí** cần được đọc kỹ, ngay cả khi có bí danh gợi ý tên cột.

### 2.4. Quy tắc số lượng cột

Thông thường, số biểu thức đầu ra của `SELECT` phải bằng số cột đích được liệt kê:

```sql
-- Sai: khai báo ba cột đích nhưng SELECT chỉ có hai biểu thức.
INSERT INTO lesson264_mapping_demo (code, label, quantity)
SELECT 'P-104', 'Tẩy';
```

Và:

```sql
-- Sai: khai báo hai cột đích nhưng SELECT trả ba biểu thức.
INSERT INTO lesson264_mapping_demo (code, label)
SELECT 'P-104', 'Tẩy', 2;
```

Việc thiếu hoặc thừa biểu thức khác với **các cột đích không được liệt kê**. Cột đích được bỏ khỏi danh sách có thể lấy giá trị `DEFAULT` hoặc `NULL` tùy định nghĩa bảng; xem phần tiếp theo.

## 3. Vì sao nên luôn viết danh sách cột đích rõ ràng?

Với một bảng có nhiều cột:

```sql
INSERT INTO destination_table
SELECT ...
FROM source_table;
```

cách không ghi `(destination_col_1, ...)` khiến việc ánh xạ phụ thuộc danh sách cột đích mà DBMS suy ra từ schema. Nó dễ sai khi:

- Bảng nguồn và đích khác thứ tự cột.
- Bảng đích thêm cột mới.
- Một cột đích có giá trị mặc định hoặc tự sinh.
- Bạn chỉ cần chuyển một phần cột.
- Một số cột có kiểu tương thích với nhau nhưng ý nghĩa hoàn toàn khác nhau.

Nên viết:

```sql
INSERT INTO destination_table (
    external_code,
    customer_id,
    ordered_on,
    amount
)
SELECT
    s.source_code,
    s.customer_ref,
    s.source_date,
    s.source_amount
FROM source_table AS s;
```

Danh sách rõ ràng có thêm tác dụng như **tài liệu ánh xạ dữ liệu**: người đọc nhìn thấy mỗi giá trị nguồn sẽ được dùng làm gì.

**Đừng dùng `SELECT *` làm nguồn cho một phép chèn có yêu cầu ánh xạ nghiêm ngặt.** `*` trả cột theo cấu trúc nguồn, có thể thay đổi khi thêm cột hoặc đổi định nghĩa view.

### 3.1. Tạo một bảng ánh xạ trong tài liệu thiết kế

Trước khi viết một phép chuyển đổi lớn, có thể lập bảng:

| Cột đích | Nguồn hoặc biểu thức | Quy tắc |
|---|---|---|
| `external_order_code` | `stage.source_code` | Giữ mã nguồn |
| `customer_id` | `stage.customer_ref` | Phải tồn tại ở bảng khách hàng |
| `order_date` | `stage.ordered_on` | Dùng kiểu `DATE` |
| `amount` | `stage.gross_value` | Không âm |
| `order_status` | `UPPER(BTRIM(stage.source_state))` | Chuẩn hóa và kiểm tra danh mục |
| `sales_channel` | `COALESCE(NULLIF(...), 'UNKNOWN')` | Chuẩn hóa; giá trị trống → UNKNOWN |
| `source_stage_id` | `stage.stage_id` | Dấu vết nguồn đã chọn |

Đây là **tài liệu logic** chứ không phải cơ chế SQL tự động. Nhưng nó giúp phát hiện sớm cột bị đảo, cột thiếu hoặc phép biến đổi chưa rõ.

## 4. Dữ liệu thực hành: từ staging đến bảng đơn hàng chuẩn

Các phần tiếp theo dùng PostgreSQL. Hãy chạy những lệnh tạo bảng và nhập dữ liệu trên **database thực hành**. Không chạy lặp lại các lệnh `CREATE TABLE`/`INSERT VALUES` nếu đối tượng và khóa đã tồn tại.

Ta dùng:

1. `lesson264_customers`: danh mục khách hàng.
2. `lesson264_stage_orders`: đơn hàng từ nguồn nhập.
3. `lesson264_orders`: bảng đích đã chuẩn hóa, có ràng buộc và khóa tự sinh.

### 4.1. Danh mục khách hàng

```sql
CREATE TABLE lesson264_customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL
);

INSERT INTO lesson264_customers (customer_id, customer_name)
VALUES
    (1, 'An'),
    (2, 'Bình'),
    (3, 'Chi'),
    (4, 'Dũng');
```

### 4.2. Bảng staging: nguồn nhập có thể chưa sạch

```sql
CREATE TABLE lesson264_stage_orders (
    stage_id INTEGER PRIMARY KEY,
    source_code VARCHAR(30) NOT NULL,
    customer_ref INTEGER,
    gross_value NUMERIC(12, 2) NOT NULL,
    ordered_on DATE NOT NULL,
    source_state VARCHAR(30) NOT NULL,
    sales_channel VARCHAR(30),
    batch_id VARCHAR(20) NOT NULL,
    is_accepted BOOLEAN NOT NULL DEFAULT FALSE
);
```

Staging có thể có:

- Cột với **tên khác** bảng đích.
- Trạng thái viết hoa/thường không thống nhất.
- Bản ghi cùng mã đơn đến nhiều lần.
- Khách hàng chưa tồn tại.
- Giá trị tiền âm, trạng thái không được hỗ trợ.
- Dữ liệu thuộc lô nhập khác.
- Dòng chưa được phê duyệt để chèn.

Trong hệ thống thật, cột staging có thể là `TEXT` để chứa cả dữ liệu nhập sai định dạng. Bài này dùng kiểu `DATE` và `NUMERIC` ở staging để tập trung vào **ánh xạ và điều kiện chèn**, rồi trình bày xử lý chuỗi thô ở phần riêng.

### 4.3. Thêm dữ liệu nguồn

```sql
INSERT INTO lesson264_stage_orders (
    stage_id,
    source_code,
    customer_ref,
    gross_value,
    ordered_on,
    source_state,
    sales_channel,
    batch_id,
    is_accepted
)
VALUES
    (1001, 'ORD-A101', 1, 120000.00,
        DATE '2026-11-01', 'paid', 'online', 'NOV26', TRUE),
    (1002, 'ORD-A102', 1, 200000.00,
        DATE '2026-11-02', ' PAID ', 'store', 'NOV26', TRUE),
    (1003, 'ORD-B103', 2,  90000.00,
        DATE '2026-11-03', 'PENDING', 'online', 'NOV26', TRUE),
    (1004, 'ORD-C104', 3,  80000.00,
        DATE '2026-11-04', 'Paid', 'web', 'NOV26', TRUE),

    -- Chưa được chấp nhận và customer_ref không hợp lệ.
    (1005, 'ORD-X105', 999, 40000.00,
        DATE '2026-11-05', 'PAID', 'online', 'NOV26', FALSE),

    -- Lô khác, không thuộc NOV26.
    (1006, 'ORD-D106', 4, 50000.00,
        DATE '2026-10-31', 'PAID', 'store', 'OCT26', TRUE),

    -- Cùng mã đơn với stage 1001, đến ở stage_id mới hơn.
    (1007, 'ORD-A101', 1, 120000.00,
        DATE '2026-11-01', 'paid', 'online', 'NOV26', TRUE),

    (1008, 'ORD-C108', 3,  70000.00,
        DATE '2026-11-06', 'refunded', 'web', 'NOV26', TRUE),
    (1009, 'ORD-B109', 2, 110000.00,
        DATE '2026-11-06', 'paid', 'online', 'NOV26', TRUE),

    -- Ba tình huống không được chèn theo quy tắc nghiệp vụ.
    (1010, 'ORD-B110', 2,  60000.00,
        DATE '2026-11-07', 'PAID', 'online', 'NOV26', FALSE),
    (1011, 'ORD-X111', 999, 25000.00,
        DATE '2026-11-08', 'PAID', 'online', 'NOV26', TRUE),
    (1012, 'ORD-B112', 2,  80000.00,
        DATE '2026-11-09', 'UNKNOWN', 'web', 'NOV26', TRUE),
    (1013, 'ORD-B113', 2, -10000.00,
        DATE '2026-11-10', 'PAID', 'web', 'NOV26', TRUE);
```

### 4.4. Bảng đích có kiểm tra tính hợp lệ

```sql
CREATE TABLE lesson264_orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_order_code VARCHAR(30) NOT NULL UNIQUE,
    customer_id INTEGER NOT NULL
        REFERENCES lesson264_customers(customer_id),
    order_date DATE NOT NULL,
    amount NUMERIC(12, 2) NOT NULL
        CHECK (amount >= 0),
    order_status VARCHAR(20) NOT NULL
        CHECK (order_status IN ('PAID', 'PENDING', 'REFUNDED')),
    sales_channel VARCHAR(30) NOT NULL
        DEFAULT 'UNKNOWN',
    source_stage_id INTEGER NOT NULL UNIQUE
        REFERENCES lesson264_stage_orders(stage_id),
    imported_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP
);
```

Những quy tắc đích:

- `order_id`: hệ quản trị **tự tạo** vì có `GENERATED ALWAYS AS IDENTITY`.
- `external_order_code`: mã đơn từ nguồn, phải **duy nhất** trong bảng đích.
- `customer_id`: khách hàng phải tồn tại ở `lesson264_customers`.
- `amount`: không âm.
- `order_status`: chỉ một trong ba giá trị hợp lệ.
- `sales_channel`: có giá trị mặc định khi **bỏ cột này khỏi danh sách chèn**.
- `source_stage_id`: lưu bản ghi staging **được chọn** để truy vết.
- `imported_at`: thời điểm nhập do DBMS đặt mặc định.

Lưu ý `source_stage_id` cũng duy nhất để một bản ghi staging không bị dùng làm nguồn cho **hai dòng đích khác nhau**. Chính sách này phù hợp dữ liệu minh họa; với một bản ghi nguồn có thể tạo nhiều dòng chi tiết đích, không nên áp dụng ràng buộc này một cách máy móc.

## 5. Xác định tập dòng được phép INSERT trước khi ghi

Một câu `INSERT SELECT` tốt thường bắt đầu từ **truy vấn SELECT độc lập** để người viết hiểu rõ các dòng dự định chèn.

Yêu cầu của bài:

1. Chỉ lấy `batch_id = 'NOV26'`.
2. Chỉ lấy dòng `is_accepted = TRUE`.
3. Khách hàng phải tồn tại.
4. `gross_value >= 0`.
5. Trạng thái sau chuẩn hóa nằm trong `PAID`, `PENDING`, `REFUNDED`.
6. Nếu một `source_code` xuất hiện nhiều lần, chỉ lấy **một bản ghi hợp lệ có `stage_id` lớn nhất**.

### 5.1. Lọc điều kiện hợp lệ bằng SELECT

```sql
SELECT
    s.stage_id,
    s.source_code,
    s.customer_ref,
    s.ordered_on,
    s.gross_value,
    UPPER(BTRIM(s.source_state)) AS normalized_status,
    COALESCE(
        NULLIF(UPPER(BTRIM(s.sales_channel)), ''),
        'UNKNOWN'
    ) AS normalized_channel
FROM lesson264_stage_orders AS s
JOIN lesson264_customers AS c
    ON c.customer_id = s.customer_ref
WHERE s.batch_id = 'NOV26'
  AND s.is_accepted = TRUE
  AND s.gross_value >= 0
  AND UPPER(BTRIM(s.source_state))
      IN ('PAID', 'PENDING', 'REFUNDED')
ORDER BY s.stage_id;
```

Kết quả gồm các `stage_id`:

```text
1001, 1002, 1003, 1004, 1007, 1008, 1009
```

Có **7 dòng hợp lệ trước bước khử trùng lặp**. Hai dòng 1001 và 1007 cùng mã `ORD-A101`.

`JOIN lesson264_customers` chỉ giữ nguồn có khách hàng tồn tại. Vì `customer_id` là khóa chính bên khách hàng, JOIN này không tự nhân dòng.

### 5.2. Chuẩn hóa trạng thái và kênh bán

```sql
UPPER(BTRIM(s.source_state))
```

Trong PostgreSQL, `BTRIM` bỏ khoảng trắng ở hai đầu chuỗi theo mặc định, `UPPER` chuyển chữ sang hoa. Vì thế:

- `'paid'` → `'PAID'`.
- `' PAID '` → `'PAID'`.
- `'Paid'` → `'PAID'`.
- `'refunded'` → `'REFUNDED'`.

Kênh bán:

```sql
COALESCE(
    NULLIF(UPPER(BTRIM(s.sales_channel)), ''),
    'UNKNOWN'
)
```

- Nếu có giá trị như `'online'` thì trả `'ONLINE'`.
- Nếu chỉ có khoảng trắng thì `BTRIM` cho chuỗi rỗng, `NULLIF(..., '')` chuyển thành `NULL`, `COALESCE` trả `'UNKNOWN'`.
- Nếu nguồn vốn là `NULL`, `COALESCE` cũng trả `'UNKNOWN'`.

**Điểm cần phân biệt:** biểu thức `COALESCE` ở đây **cung cấp một giá trị cụ thể** trong `SELECT`. Nó khác với việc bỏ hẳn cột đích để sử dụng `DEFAULT` do bảng quy định.

## 6. Khử trùng lặp nguồn trước khi chèn vào khóa UNIQUE

Nếu chèn cả 7 dòng hợp lệ, hai dòng `ORD-A101` sẽ đụng ràng buộc `UNIQUE (external_order_code)` ở đích.

Không nên giải quyết bằng:

```sql
SELECT DISTINCT
    source_code,
    customer_ref,
    gross_value,
    ordered_on,
    ...
```

với hy vọng luôn có đúng một dòng cho mỗi `source_code`. Nếu những bản nhập cùng mã khác giá trị, `DISTINCT` trên toàn bộ cột vẫn giữ **nhiều dòng**.

Bài toán thật là: **một hàng theo mỗi `source_code` với quy tắc chọn hàng**. Ta dùng `ROW_NUMBER`:

```sql
WITH valid_rows AS (
    SELECT
        s.stage_id,
        s.source_code,
        s.customer_ref,
        s.gross_value,
        s.ordered_on,
        UPPER(BTRIM(s.source_state)) AS normalized_status,
        COALESCE(
            NULLIF(UPPER(BTRIM(s.sales_channel)), ''),
            'UNKNOWN'
        ) AS normalized_channel
    FROM lesson264_stage_orders AS s
    JOIN lesson264_customers AS c
        ON c.customer_id = s.customer_ref
    WHERE s.batch_id = 'NOV26'
      AND s.is_accepted = TRUE
      AND s.gross_value >= 0
      AND UPPER(BTRIM(s.source_state))
          IN ('PAID', 'PENDING', 'REFUNDED')
),
ranked_rows AS (
    SELECT
        v.*,
        ROW_NUMBER() OVER (
            PARTITION BY v.source_code
            ORDER BY v.stage_id DESC
        ) AS rn
    FROM valid_rows AS v
)
SELECT
    stage_id,
    source_code,
    customer_ref,
    gross_value,
    ordered_on,
    normalized_status,
    normalized_channel
FROM ranked_rows
WHERE rn = 1
ORDER BY source_code;
```

Kết quả dự kiến:

| source_code | stage_id | customer_ref | gross_value | normalized_status |
|---|---:|---:|---:|---|
| ORD-A101 | **1007** | 1 | 120.000 | PAID |
| ORD-A102 | 1002 | 1 | 200.000 | PAID |
| ORD-B103 | 1003 | 2 | 90.000 | PENDING |
| ORD-B109 | 1009 | 2 | 110.000 | PAID |
| ORD-C104 | 1004 | 3 | 80.000 | PAID |
| ORD-C108 | 1008 | 3 | 70.000 | REFUNDED |

Có **6 mã đơn khác nhau**; mỗi mã chỉ chọn một dòng.

**Chính sách chọn `stage_id` lớn nhất chỉ là quy tắc minh họa.** Trong hệ thống thật, bản ghi nhập sau không phải lúc nào cũng đúng hơn. Có thể cần ưu tiên `verified_at`, phiên bản nguồn, trạng thái đã phê duyệt hoặc ngày hiệu lực. Nếu không có quy tắc xác định, đừng tự coi `MAX(stage_id)` là “đúng nhất”.

### 6.1. Lọc rồi xếp hạng hay xếp hạng rồi lọc?

Trong ví dụ, chúng ta **lọc dòng hợp lệ trước**, rồi chọn bản ghi có `stage_id` lớn nhất trong tập hợp lệ.

Nếu nghiệp vụ là “chọn bản nhập **mới nhất**, và nếu bản đó không hợp lệ thì **báo lỗi toàn mã đơn**”, quy trình sẽ khác: xếp hạng bản nhập trước, rồi kiểm tra chất lượng bản đã chọn. Hai cách có thể trả kết quả khác nhau khi bản mới nhất bị lỗi.

Hãy định nghĩa chính sách chính xác trước khi chọn thứ tự xử lý.

## 7. Câu INSERT INTO SELECT hoàn chỉnh

Sau khi đã xem trước tập dữ liệu đích, chèn bằng cùng nguồn trung gian:

```sql
WITH valid_rows AS (
    SELECT
        s.stage_id,
        s.source_code,
        s.customer_ref,
        s.gross_value,
        s.ordered_on,
        UPPER(BTRIM(s.source_state)) AS normalized_status,
        COALESCE(
            NULLIF(UPPER(BTRIM(s.sales_channel)), ''),
            'UNKNOWN'
        ) AS normalized_channel
    FROM lesson264_stage_orders AS s
    JOIN lesson264_customers AS c
        ON c.customer_id = s.customer_ref
    WHERE s.batch_id = 'NOV26'
      AND s.is_accepted = TRUE
      AND s.gross_value >= 0
      AND UPPER(BTRIM(s.source_state))
          IN ('PAID', 'PENDING', 'REFUNDED')
),
ranked_rows AS (
    SELECT
        v.*,
        ROW_NUMBER() OVER (
            PARTITION BY v.source_code
            ORDER BY v.stage_id DESC
        ) AS rn
    FROM valid_rows AS v
)
INSERT INTO lesson264_orders (
    external_order_code,
    customer_id,
    order_date,
    amount,
    order_status,
    sales_channel,
    source_stage_id
)
SELECT
    r.source_code,          -- 1 → external_order_code.
    r.customer_ref,         -- 2 → customer_id.
    r.ordered_on,           -- 3 → order_date.
    r.gross_value,          -- 4 → amount.
    r.normalized_status,    -- 5 → order_status.
    r.normalized_channel,   -- 6 → sales_channel.
    r.stage_id              -- 7 → source_stage_id.
FROM ranked_rows AS r
WHERE r.rn = 1
ON CONFLICT (external_order_code) DO NOTHING
RETURNING
    order_id,
    external_order_code,
    customer_id,
    source_stage_id,
    amount;
```

Đây là **một câu `WITH ... INSERT ... SELECT ... RETURNING`**. Không đặt dấu chấm phẩy giữa phần `WITH` và `INSERT`.

### 7.1. Ánh xạ chính xác theo thứ tự

| Vị trí | Cột đích trong `INSERT INTO (...)` | Biểu thức trong `SELECT` | Kiểu mong đợi |
|---:|---|---|---|
| 1 | `external_order_code` | `r.source_code` | Chuỗi |
| 2 | `customer_id` | `r.customer_ref` | Số nguyên, khóa ngoại |
| 3 | `order_date` | `r.ordered_on` | `DATE` |
| 4 | `amount` | `r.gross_value` | `NUMERIC(12,2)` |
| 5 | `order_status` | `r.normalized_status` | Chuỗi thuộc danh mục |
| 6 | `sales_channel` | `r.normalized_channel` | Chuỗi không `NULL` |
| 7 | `source_stage_id` | `r.stage_id` | Số nguyên tham chiếu staging |

Hai cột đích **không có trong danh sách**:

- `order_id` nhận giá trị tự sinh từ `IDENTITY`.
- `imported_at` nhận `DEFAULT CURRENT_TIMESTAMP`.

Không cần viết hai cột này ở `SELECT`.

### 7.2. Kết quả khi bảng đích còn rỗng

Đề nghị chèn có **6 dòng**, gồm:

- `ORD-A101` → bản nguồn 1007.
- `ORD-A102` → nguồn 1002.
- `ORD-B103` → nguồn 1003.
- `ORD-B109` → nguồn 1009.
- `ORD-C104` → nguồn 1004.
- `ORD-C108` → nguồn 1008.

Tổng tiền các dòng hợp lệ đã chọn:

\[
120000+200000+90000+110000+80000+70000=670000.
\]

Kiểm tra:

```sql
SELECT
    COUNT(*) AS imported_orders,
    SUM(amount) AS imported_amount
FROM lesson264_orders;
```

Nếu bảng ban đầu trống và chưa có phép ghi nào khác, kết quả là **6 đơn** và **670.000**.

### 7.3. Không tự dự đoán order_id

`order_id` là `GENERATED ALWAYS AS IDENTITY`. Giá trị cụ thể phụ thuộc trạng thái bộ cấp số và các phép chèn đã thử. **Không được giả định** đơn `ORD-A101` nhất định nhận `order_id = 1` hoặc các ID luôn liền nhau.

Các hệ quản trị có thể tiêu thụ giá trị sequence trong những phép chèn thất bại, xung đột hoặc bị rollback. Hãy dùng `RETURNING` hoặc truy vấn theo **mã nguồn duy nhất** để biết ID thực được cấp.

### 7.4. Kết quả RETURNING không có thứ tự bảo đảm

Trong câu ví dụ, `RETURNING` trả các dòng thực sự được chèn. Nếu muốn hiển thị theo `external_order_code`, có thể **đọc lại bảng**:

```sql
SELECT
    order_id,
    external_order_code,
    customer_id,
    amount,
    order_status,
    source_stage_id
FROM lesson264_orders
ORDER BY external_order_code;
```

Đừng dựa vào thứ tự dòng của nguồn `SELECT` để suy ra thứ tự phát sinh ID hoặc thứ tự hiển thị của `RETURNING`.

## 8. Tại sao có thể chạy lặp mà không nhập trùng?

Câu chèn ở phần 7 dùng:

```sql
ON CONFLICT (external_order_code) DO NOTHING
```

Đây là cú pháp **PostgreSQL**. Khi bảng đích đã có một dòng với `external_order_code` tương ứng, PostgreSQL không chèn thêm dòng xung đột đó. Với bảng đã chứa đủ sáu đơn, chạy lại cùng câu:

- Không tạo thêm sáu đơn trùng.
- `RETURNING` không trả dòng mới cho những mã đã tồn tại.
- `COUNT(*)` trong bảng vẫn là 6 nếu không có ghi khác.

Đây là một cách hỗ trợ tính **idempotent** cho tác vụ nhập dữ liệu: chạy lại cùng input không làm tăng bản ghi trùng theo khóa nghiệp vụ.

### 8.1. DO NOTHING không đồng nghĩa tự làm mới dữ liệu

Nếu batch sau mang giá trị `amount` mới cho một `external_order_code` đã tồn tại, `DO NOTHING` sẽ **giữ nguyên bản ghi đích cũ**. Điều đó có thể đúng với dữ liệu bất biến (ví dụ một đơn đã chốt) nhưng sai nếu cần cập nhật snapshot.

Nếu cần cập nhật, xem phần `ON CONFLICT DO UPDATE` sau. Không tự đổi sang cập nhật mà chưa quy định **dữ liệu nguồn nào được phép ghi đè dữ liệu hiện có**.

### 8.2. Dùng đúng khóa UNIQUE

`ON CONFLICT (external_order_code)` dựa trên ràng buộc duy nhất phù hợp trong bảng đích. Nếu mã ngoài chỉ duy nhất **trong từng cửa hàng**, bảng cần khóa duy nhất ghép như `UNIQUE(store_id, external_order_code)`, và xung đột cần xét cả hai cột.

Đặt khóa duy nhất quá rộng có thể gộp nhầm hai đơn khác nhau; đặt khóa quá hẹp có thể không phát hiện mã nhập lặp.

### 8.3. ON CONFLICT không thay thế kiểm tra nguồn

Nếu nguồn có hai dòng cùng mã nhưng khác giá trị và bạn chèn không chọn đại diện trước, `DO NOTHING` có thể khiến **một trong các dòng nguồn được chèn**, còn dòng còn lại bị bỏ, nhưng **không thể dựa vào thứ tự không quy định để đảm bảo đó là bản đúng**.

Vì vậy, quy trình chuẩn là:

1. Xác định và lọc dòng hợp lệ.
2. Chọn đúng một bản nguồn theo quy tắc nghiệp vụ.
3. Chèn vào bảng đích có `UNIQUE`.
4. Dùng cơ chế xử lý xung đột theo chính sách cập nhật.

## 9. Phân biệt DEFAULT, NULL và cột bị bỏ khỏi INSERT

Đây là một điểm dễ nhầm trong ánh xạ cột.

Bảng đích có:

```sql
sales_channel VARCHAR(30) NOT NULL DEFAULT 'UNKNOWN',
imported_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
```

### 9.1. Bỏ cột đích khỏi danh sách

Nếu không cung cấp `sales_channel` ở `INSERT INTO (...)`, giá trị mặc định được áp dụng:

```sql
-- Mẫu minh họa; cần dùng mã đơn mới chưa tồn tại nếu chạy.
INSERT INTO lesson264_orders (
    external_order_code,
    customer_id,
    order_date,
    amount,
    order_status,
    source_stage_id
)
SELECT
    s.source_code,
    s.customer_ref,
    s.ordered_on,
    s.gross_value,
    UPPER(BTRIM(s.source_state)),
    s.stage_id
FROM lesson264_stage_orders AS s
WHERE s.stage_id = 1002;
```

**Lưu ý:** Trong dữ liệu bài, nếu đã chạy lần nhập ở phần 7, `ORD-A102` và `source_stage_id = 1002` đã có ở đích; câu minh họa trên **sẽ xung đột UNIQUE** nếu chạy lại. Mục tiêu của đoạn là cho thấy **bỏ cột `sales_channel` khiến hệ quản trị lấy giá trị mặc định**; không phải hướng dẫn nhập lặp đơn đã có.

### 9.2. Cung cấp NULL không tự sử dụng DEFAULT

Nếu viết:

```sql
INSERT INTO lesson264_orders (..., sales_channel, ...)
SELECT ..., NULL, ...;
```

đó là đề nghị chèn giá trị **`NULL`** cho `sales_channel`, không phải “bỏ qua cột”. Vì `sales_channel NOT NULL`, câu chèn sẽ bị từ chối nếu không có cơ chế khác thay đổi giá trị.

Muốn nguồn trống trở thành `'UNKNOWN'`, dùng biểu thức rõ ràng:

```sql
COALESCE(
    NULLIF(UPPER(BTRIM(s.sales_channel)), ''),
    'UNKNOWN'
)
```

### 9.3. Có thể dùng DEFAULT trong INSERT VALUES

```sql
-- Ví dụ cú pháp INSERT VALUES, không chạy lại cùng khóa.
INSERT INTO lesson264_mapping_demo (code, label, quantity)
VALUES ('P-200', 'Sổ tay', 1);
```

Nếu bảng có cột đích `DEFAULT` được bỏ khỏi danh sách, nó tự nhận mặc định. Trong `INSERT ... SELECT`, cách phổ biến và dễ chuyển hệ nhất là **bỏ những cột muốn dùng DEFAULT khỏi danh sách đích**, chứ không cố viết `DEFAULT` như một biểu thức thường trong danh sách `SELECT`. Quy tắc cho từ khóa `DEFAULT` trong biểu thức/chèn thay đổi theo DBMS.

### 9.4. Identity và generated column

Bảng đích dùng `order_id BIGINT GENERATED ALWAYS AS IDENTITY`. Thông thường, bạn **không chèn giá trị nguồn vào cột này**. PostgreSQL có cơ chế `OVERRIDING SYSTEM VALUE` cho những trường hợp đặc biệt, nhưng không nên sử dụng khi chỉ cần nhập đơn từ staging và cấp một khóa nội bộ mới.

Phân biệt hai định danh:

- `external_order_code`: mã nguồn/nghiệp vụ để nhận diện đơn và xử lý nhập lại.
- `order_id`: khóa nội bộ do bảng đích cấp, không nhất thiết bằng mã hay số thứ tự nguồn.

## 10. Biến đổi kiểu dữ liệu và biểu thức trong SELECT

Nguồn và đích không cần có cùng định dạng, nhưng phép chuyển phải **rõ nghĩa và hợp lệ**.

### 10.1. Đổi tên và tính giá trị

Giả sử nguồn có `qty` và `unit_price`, đích cần `total_amount`:

```sql
-- Mẫu thiết kế; giả định có source_lines và target_lines.
INSERT INTO target_lines (
    source_line_id,
    total_amount
)
SELECT
    s.line_id,
    s.qty * s.unit_price
FROM source_lines AS s;
```

Giá trị `total_amount` được **tính từ nguồn**, không phải sao chép một cột cùng tên.

### 10.2. CAST chuỗi thành số hoặc ngày

Trong nhiều file nhập, dữ liệu tiền và ngày ban đầu là văn bản:

```sql
WITH raw_data (raw_code, raw_amount, raw_date) AS (
    VALUES (
        'ORD-TEST-1',
        '125000.50',
        '2026-11-07'
    )
)
SELECT
    raw_code,
    CAST(raw_amount AS NUMERIC(12, 2)) AS amount,
    CAST(raw_date AS DATE) AS order_date
FROM raw_data;
```

Kết quả là giá trị `NUMERIC(12,2)` và `DATE` phù hợp.

Trong PostgreSQL còn có dạng:

```sql
raw_amount::NUMERIC(12, 2)
raw_date::DATE
```

Dạng `::` là cú pháp PostgreSQL, không dùng được nguyên dạng ở mọi DBMS.

**Quan trọng:** nếu chuỗi chứa `'not-a-number'` hoặc ngày không hợp lệ như `'2026-02-30'`, việc ép kiểu có thể làm cả câu `INSERT SELECT` lỗi. Không mặc định `CAST` là một công cụ “sửa mọi dữ liệu thô”.

### 10.3. Kiểm tra dữ liệu trước khi ép kiểu

Với dữ liệu thô, quy trình đáng tin cậy thường gồm:

1. Giữ nguyên giá trị raw để truy vết.
2. Chuẩn hóa khoảng trắng, dấu phân cách, mã hóa.
3. Kiểm tra định dạng và miền giá trị bằng quy tắc đáng tin.
4. Phân loại dòng hợp lệ/dòng bị từ chối.
5. Chỉ chuyển kiểu và chèn dữ liệu đã đủ điều kiện.
6. Ghi lý do từ chối để xử lý.

Một biểu thức `CASE WHEN raw_value ~ 'regex' THEN CAST(...)` có thể giúp với định dạng đơn giản trong PostgreSQL, nhưng **regex không chứng minh mọi ngày lịch đều hợp lệ**, và việc tối ưu hóa/thứ tự đánh giá biểu thức SQL không nên bị hiểu như một trình chạy tuần tự tùy ý. Với nhập liệu phức tạp, có thể cần hàm kiểm tra, cấu trúc staging nhiều bước hoặc xử lý trong ứng dụng.

### 10.4. Chuẩn hóa trạng thái bằng CASE

Nếu hệ thống nguồn dùng mã khác đích:

```sql
CASE UPPER(BTRIM(s.source_state))
    WHEN 'PAID' THEN 'PAID'
    WHEN 'PENDING' THEN 'PENDING'
    WHEN 'REFUND' THEN 'REFUNDED'
    WHEN 'REFUNDED' THEN 'REFUNDED'
    ELSE NULL
END
```

Phép ánh xạ này có thể dùng trong `SELECT` trước `INSERT`. Nếu trả `NULL` trong khi cột đích `NOT NULL`, câu chèn sẽ lỗi; có thể chủ động lọc nguồn chưa ánh xạ được hoặc đưa vào bảng từ chối.

Đừng âm thầm chuyển mọi trạng thái lạ thành `'PAID'` chỉ để câu SQL chạy, vì như vậy làm sai nghiệp vụ.

### 10.5. Quy tắc làm tròn và đơn vị tiền

Nếu nguồn lưu tiền theo đồng nhưng bảng đích lưu theo nghìn đồng, phép biến đổi như `s.amount / 1000` cần được ghi rõ. Với tiền, nên dùng kiểu số chính xác như `NUMERIC/DECIMAL` theo yêu cầu và quy tắc làm tròn phù hợp; tránh phụ thuộc vào số dấu phẩy động khi dữ liệu cần độ chính xác kế toán.

**Ánh xạ cột không chỉ là đổi tên: đó còn là hợp đồng chuyển đổi giá trị và đơn vị đo.**

## 11. Khóa ngoại, CHECK, UNIQUE và NOT NULL khi INSERT SELECT

`INSERT SELECT` **không bỏ qua ràng buộc** của bảng đích.

### 11.1. Khóa ngoại

Nếu `customer_id = 999` không tồn tại trong `lesson264_customers`, việc chèn vào `lesson264_orders.customer_id` sẽ vi phạm khóa ngoại (trừ khi có cơ chế/ngoại lệ cấu hình đặc biệt của DBMS, không áp dụng trong bảng mẫu).

Trong phần nhập chuẩn, chúng ta JOIN với `lesson264_customers` để **loại trước những dòng không tìm được khách hàng**. Nhưng chỉ JOIN chưa thay thế ràng buộc FK trong tình huống dữ liệu có thể bị thay đổi đồng thời; FK ở đích là lớp bảo vệ cuối.

### 11.2. CHECK amount >= 0

Dòng staging `1013` có `gross_value = -10000`. Nếu chèn vào cột `amount` với ràng buộc `CHECK (amount >= 0)`, nó bị từ chối. Câu SELECT đã lọc `s.gross_value >= 0` để tránh đưa dòng sai vào phép ghi.

### 11.3. CHECK trạng thái

Dòng staging `1012` có `source_state = 'UNKNOWN'`, không nằm trong ba giá trị đích cho phép. Bộ lọc trạng thái loại nó trước khi chèn.

### 11.4. UNIQUE mã đơn

Hai dòng staging `1001` và `1007` cùng `ORD-A101`. `UNIQUE` không cho phép chèn cả hai vào đích. Bước `ROW_NUMBER` chọn **1007** theo chính sách của bài trước khi gửi tập dòng vào `INSERT`.

### 11.5. NOT NULL

Cột đích `customer_id` bắt buộc có giá trị. Nếu staging có `customer_ref NULL`, phép nối bằng khóa tới bảng khách hàng không tạo khớp. Nếu bạn bỏ bước kiểm tra nhưng vẫn chèn `NULL`, ràng buộc `NOT NULL` sẽ ngăn phép ghi.

**Nguyên tắc:** dùng bước kiểm tra/chuẩn hóa để trả lời **dòng nào được phép nhập**; giữ ràng buộc ở bảng đích để bảo vệ tính nhất quán dữ liệu ngay cả khi có đường ghi khác.

## 12. Kiểm tra dòng bị loại và ghi nhận lý do

Không nên để hệ thống âm thầm bỏ mọi dòng xấu rồi coi lô nhập đã hoàn thành đầy đủ. Với staging, nên có báo cáo **những dòng không được nhận**.

Ví dụ câu truy vấn chẩn đoán cho lô `NOV26`:

```sql
SELECT
    s.stage_id,
    s.source_code,
    CASE
        WHEN s.is_accepted = FALSE
            THEN 'NOT_ACCEPTED'
        WHEN s.customer_ref IS NULL
          OR c.customer_id IS NULL
            THEN 'UNKNOWN_CUSTOMER'
        WHEN s.gross_value < 0
            THEN 'NEGATIVE_AMOUNT'
        WHEN UPPER(BTRIM(s.source_state))
             NOT IN ('PAID', 'PENDING', 'REFUNDED')
            THEN 'INVALID_STATUS'
        ELSE 'ELIGIBLE_BEFORE_DEDUP'
    END AS validation_result
FROM lesson264_stage_orders AS s
LEFT JOIN lesson264_customers AS c
    ON c.customer_id = s.customer_ref
WHERE s.batch_id = 'NOV26'
ORDER BY s.stage_id;
```

Kết quả đáng chú ý:

| stage_id | validation_result |
|---:|---|
| 1005 | NOT_ACCEPTED |
| 1010 | NOT_ACCEPTED |
| 1011 | UNKNOWN_CUSTOMER |
| 1012 | INVALID_STATUS |
| 1013 | NEGATIVE_AMOUNT |

Các dòng 1001 và 1007 đều là `ELIGIBLE_BEFORE_DEDUP` trước khi chọn một mã đơn duy nhất; báo cáo ở trên **chưa thể hiện trạng thái bị loại do trùng mã**.

Một hệ thống nhập dữ liệu thường cần phân biệt:

- **Bị từ chối vì không hợp lệ.**
- **Đã có dữ liệu ở bảng đích.**
- **Nguồn hợp lệ nhưng không được chọn làm bản đại diện.**
- **Đã chèn mới.**
- **Đã cập nhật bản đích.**

Những trạng thái này có ý nghĩa nghiệp vụ khác nhau. `DO NOTHING` chỉ giải quyết việc không chèn dòng xung đột, **không tự tạo báo cáo đầy đủ cho lô nhập**.

### 12.1. Cẩn thận với điều kiện lọc và ba giá trị logic

Ví dụ `s.gross_value >= 0` trả `UNKNOWN` nếu `gross_value NULL`. Bảng staging mẫu có `gross_value NOT NULL`, nhưng khi dùng nguồn khác có thể cần điều kiện `IS NOT NULL` rõ ràng.

Với cờ `BOOLEAN` nullable, `WHERE is_accepted = TRUE` không chọn `NULL`. Điều này thường phù hợp chính sách “chỉ nhập dòng đã được chấp nhận”. Không nên dùng điều kiện như `is_accepted <> FALSE` mà không xét cách `NULL` được xử lý.

## 13. INSERT SELECT từ nhiều bảng bằng JOIN

Nguồn của `INSERT SELECT` không bắt buộc chỉ là một bảng. Nó có thể là một truy vấn `JOIN`:

```sql
INSERT INTO some_target (
    customer_id,
    customer_name,
    order_count
)
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id)
FROM lesson264_customers AS c
LEFT JOIN lesson264_orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name;
```

Đây là **mẫu thiết kế**, không chạy trực tiếp vì chưa tạo bảng `some_target`.

Điều cần quan tâm:

- `JOIN` có thể tạo nhiều dòng trên mỗi thực thể.
- `GROUP BY` phải bảo đảm đúng **grain** của bảng đích.
- Nếu bạn muốn một dòng **mỗi khách hàng**, nguồn `SELECT` cần có một dòng **mỗi `customer_id`**.
- Với một bảng đích có `UNIQUE(customer_id)`, việc `JOIN` vô tình nhân dòng có thể gây xung đột.

### 13.1. Tránh nhân đôi số tiền khi JOIN nhiều quan hệ một–nhiều

Giả sử có:

- `orders`: một dòng trên đơn.
- `order_items`: nhiều dòng trên đơn.
- `payments`: nhiều lần thanh toán trên đơn.

Nếu nối đồng thời `orders → order_items` và `orders → payments` rồi `SUM(order_total)`, giá trị đơn có thể bị nhân theo số tổ hợp giữa hai bảng con.

CTE là cách giúp **tổng hợp từng bảng con về một dòng trên khóa nối trước**, rồi mới chèn vào bảng báo cáo:

```sql
-- Ví dụ thiết kế: giả định các bảng nguồn/đích nêu dưới đây.
WITH items_by_order AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS item_amount
    FROM order_items
    GROUP BY order_id
),
payments_by_order AS (
    SELECT
        order_id,
        SUM(paid_amount) AS paid_amount
    FROM payments
    GROUP BY order_id
)
INSERT INTO order_finance_summary (
    order_id,
    item_amount,
    paid_amount
)
SELECT
    o.order_id,
    COALESCE(i.item_amount, 0),
    COALESCE(p.paid_amount, 0)
FROM orders AS o
LEFT JOIN items_by_order AS i
    ON i.order_id = o.order_id
LEFT JOIN payments_by_order AS p
    ON p.order_id = o.order_id;
```

Ở đây các CTE đều có tối đa **một dòng trên `order_id`**, nên không nhân số liệu khi ghép vào `orders`.

**Trước mỗi phép INSERT SELECT, hãy xác định một dòng kết quả nguồn đại diện cho điều gì**; bảng đích nên có một grain tương ứng.

## 14. Tạo bảng archive bằng INSERT SELECT

Một ví dụ thực hành khác là chuyển **những đơn PAID đã nhập** sang bảng lưu trữ phục vụ báo cáo.

### 14.1. Tạo bảng archive

```sql
CREATE TABLE lesson264_paid_archive (
    archive_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    archived_code VARCHAR(30) NOT NULL UNIQUE,
    archived_customer_id INTEGER NOT NULL,
    archived_on DATE NOT NULL,
    archived_amount NUMERIC(12, 2) NOT NULL,
    archived_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Ở bảng này, tên cột **khác bảng `lesson264_orders`** và có `archive_id` tự sinh.

### 14.2. Chèn các đơn PAID bằng SELECT

Sau khi đã nhập bảng `lesson264_orders` ở phần 7:

```sql
INSERT INTO lesson264_paid_archive (
    archived_code,
    archived_customer_id,
    archived_on,
    archived_amount
)
SELECT
    o.external_order_code,
    o.customer_id,
    o.order_date,
    o.amount
FROM lesson264_orders AS o
WHERE o.order_status = 'PAID'
ON CONFLICT (archived_code) DO NOTHING
RETURNING
    archive_id,
    archived_code,
    archived_amount;
```

Kết quả chèn lần đầu có **4 đơn PAID**:

| archived_code | archived_amount |
|---|---:|
| ORD-A101 | 120.000 |
| ORD-A102 | 200.000 |
| ORD-B109 | 110.000 |
| ORD-C104 | 80.000 |

Tổng tiền archive:

\[
120000+200000+110000+80000=510000.
\]

Hai cột `archive_id` và `archived_at` không nằm trong danh sách đích, nên nhận giá trị tự sinh/mặc định.

### 14.3. Kiểm tra sau khi chèn

```sql
SELECT
    COUNT(*) AS archived_paid_orders,
    SUM(archived_amount) AS archived_paid_amount
FROM lesson264_paid_archive;
```

Với dữ liệu mẫu đã nhập đúng một lô, kết quả là **4** và **510.000**.

Nếu chạy lại câu `INSERT ... ON CONFLICT DO NOTHING`, các mã đã tồn tại sẽ không được chèn thêm. Nhưng **bảng archive này là một bản sao dữ liệu tại thời điểm chạy**, không phải một view tự cập nhật khi bảng `lesson264_orders` thay đổi.

### 14.4. Archive có nghĩa là xóa khỏi bảng gốc không?

**Không.** `INSERT INTO archive SELECT ... FROM orders` **sao chép** dòng được chọn, không tự `DELETE` dòng ở bảng gốc.

Nếu nghiệp vụ cần “di chuyển” dữ liệu (ghi archive rồi xóa nguồn), phải thiết kế transaction, khóa và kiểm tra toàn vẹn riêng. Không tự chạy `DELETE` chỉ vì đã thấy câu `INSERT SELECT` hoàn tất.

## 15. INSERT SELECT với GROUP BY: chèn số liệu tổng hợp

`SELECT` cung cấp cho `INSERT` có thể là một truy vấn tổng hợp.

Giả sử muốn lưu **số đơn và doanh thu theo trạng thái** sau khi nhập dữ liệu.

### 15.1. Tạo bảng tổng hợp

```sql
CREATE TABLE lesson264_status_summary (
    summary_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_status VARCHAR(20) NOT NULL UNIQUE,
    order_count INTEGER NOT NULL,
    total_amount NUMERIC(14, 2) NOT NULL,
    calculated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### 15.2. Chèn kết quả GROUP BY

```sql
INSERT INTO lesson264_status_summary (
    order_status,
    order_count,
    total_amount
)
SELECT
    o.order_status,
    COUNT(*)::INTEGER AS order_count,
    SUM(o.amount) AS total_amount
FROM lesson264_orders AS o
GROUP BY o.order_status
ON CONFLICT (order_status) DO NOTHING
RETURNING
    order_status,
    order_count,
    total_amount;
```

Khi bảng `lesson264_orders` chứa sáu đơn của phần 7, kết quả:

| order_status | order_count | total_amount |
|---|---:|---:|
| PAID | 4 | 510.000 |
| PENDING | 1 | 90.000 |
| REFUNDED | 1 | 70.000 |

`GROUP BY` tạo **một dòng nguồn trên một trạng thái**, phù hợp ràng buộc `UNIQUE(order_status)` của bảng đích.

### 15.3. Vì sao phải hiểu kiểu kết quả của COUNT?

Trong PostgreSQL, `COUNT(*)` trả `BIGINT`. Bảng mẫu khai báo `order_count INTEGER`, nên ví dụ ép:

```sql
COUNT(*)::INTEGER
```

Với dữ liệu nhỏ, điều này phù hợp. Trong hệ thống lớn, số đếm có thể vượt phạm vi `INTEGER`. **Nên thiết kế cột `order_count BIGINT`** nếu có khả năng số lượng lớn, thay vì ép kiểu một cách mù quáng.

### 15.4. Cẩn thận với bảng tổng hợp theo kỳ

Nếu muốn lưu tổng hợp theo **tháng và trạng thái**, khóa đích thường cần là `(month_start, order_status)`, không chỉ `order_status`. Nếu dùng một bảng chỉ có `UNIQUE(order_status)` cho mọi tháng, bạn sẽ không lưu được nhiều tháng riêng biệt.

Những cột xác định **grain báo cáo** phải được thể hiện ở bảng đích và trong `GROUP BY` của nguồn.

## 16. INSERT SELECT từ UNION ALL và nhiều nguồn

Có thể chèn những dòng được tạo từ hai nguồn thông qua `UNION ALL`. Điểm cần chú ý là **các nhánh SELECT của UNION cũng ánh xạ cột theo vị trí** và phải có kiểu tương thích.

Ví dụ tự chứa chỉ để xem nguồn tổng hợp:

```sql
WITH web_orders (source_code, customer_id, amount) AS (
    VALUES
        ('WEB-1', 1, 50000::NUMERIC),
        ('WEB-2', 2, 70000::NUMERIC)
),
store_orders (store_code, customer_ref, total_amount) AS (
    VALUES
        ('STORE-1', 3, 100000::NUMERIC)
),
unified AS (
    SELECT
        source_code AS external_code,
        customer_id,
        amount,
        'WEB' AS channel
    FROM web_orders

    UNION ALL

    SELECT
        store_code,
        customer_ref,
        total_amount,
        'STORE'
    FROM store_orders
)
SELECT
    external_code,
    customer_id,
    amount,
    channel
FROM unified
ORDER BY external_code;
```

Kết quả có **3 dòng** với cùng cấu trúc cột. Khi dùng làm nguồn cho `INSERT`, cần thêm danh sách cột đích tương ứng.

`UNION ALL` giữ mọi dòng từ hai nhánh, không tự loại mã trùng. `UNION` loại dòng trùng theo **toàn bộ các cột được chọn**, chứ không chọn bản ghi tốt nhất trên khóa nghiệp vụ. Nếu hai nguồn có thể cùng gửi một mã đơn, hãy áp dụng quy tắc chọn nguồn ưu tiên trước khi INSERT và giữ khóa duy nhất ở đích.

### 16.1. Ví dụ chèn từ hai SELECT vào bảng mapping_demo

```sql
INSERT INTO lesson264_mapping_demo (
    code,
    label,
    quantity
)
SELECT
    'W-1',
    'Hàng web',
    2

UNION ALL

SELECT
    'S-1',
    'Hàng tại quầy',
    3;
```

Đây là một câu `INSERT SELECT` dùng `UNION ALL` làm nguồn. Chạy lại sẽ thêm các bản ghi giống nhau vì `lesson264_mapping_demo` **không có ràng buộc UNIQUE trên `code`**. Nếu muốn ngăn trùng trong bảng thật, cần thiết kế khóa đúng.

## 17. WHERE, JOIN và LIMIT tác động đến số dòng INSERT

### 17.1. WHERE có thể khiến không chèn dòng nào

```sql
INSERT INTO lesson264_mapping_demo (
    code,
    label,
    quantity
)
SELECT
    'P-NONE',
    'Không được chèn',
    1
WHERE 1 = 0;
```

Câu trên hợp lệ trong PostgreSQL nhưng **không chèn dòng nào**, vì nguồn `SELECT` trả 0 dòng.

Đây không phải lỗi cú pháp. Nếu ứng dụng mong đợi ít nhất một dòng, phải **kiểm tra số dòng bị ảnh hưởng**, số dòng `RETURNING`, hoặc đối chiếu kết quả sau ghi.

### 17.2. JOIN một–nhiều có thể nhân nguồn

```sql
-- Mẫu thiết kế: nguồn có một cha và nhiều dòng con.
INSERT INTO target_table (parent_id, amount)
SELECT
    p.parent_id,
    p.amount
FROM parent_table AS p
JOIN child_table AS c
    ON c.parent_id = p.parent_id;
```

Nếu một `parent` có 3 `child`, cùng `p.amount` được đề nghị chèn **3 lần**. Nếu muốn **một dòng trên parent**, hãy xét:

- Có thật sự cần JOIN `child_table`?
- Nếu chỉ muốn kiểm tra tồn tại con, dùng `EXISTS`.
- Nếu cần số lượng con, `GROUP BY` theo khóa cha.
- Nếu cần một con đại diện, chọn con bằng `ROW_NUMBER`/`LATERAL` trước khi JOIN.

### 17.3. LIMIT chọn bao nhiêu dòng nguồn, không đảm bảo thứ tự ID đích

PostgreSQL cho phép lấy một số dòng từ nguồn:

```sql
SELECT
    stage_id,
    source_code,
    gross_value
FROM lesson264_stage_orders
WHERE batch_id = 'NOV26'
ORDER BY gross_value DESC, stage_id DESC
LIMIT 3;
```

Đây là truy vấn xem trước “ba dòng nguồn có số tiền cao nhất” **trước khử trùng lặp và kiểm tra đầy đủ**.

Trong một `INSERT SELECT` thật, dùng `ORDER BY ... LIMIT` sau khi đã lọc hợp lệ và chọn một mã nguồn theo chính sách. Nếu không có `ORDER BY`, “ba dòng đầu” không có ý nghĩa ổn định. Nếu hai dòng có cùng `gross_value`, thêm khóa phá hòa như `stage_id`.

**Không dùng `ORDER BY` ở nguồn để suy luận thứ tự cấp giá trị `IDENTITY` hoặc thứ tự trả về của toàn bộ pipeline**. Hãy kiểm tra qua mã nghiệp vụ và `RETURNING`.

## 18. Giao dịch: thử chèn, xem kết quả và ROLLBACK

Với phép nhập dữ liệu đáng kể, nên tập thử trong transaction trước khi lưu chính thức.

Ví dụ thử sao chép một số dòng vào `lesson264_mapping_demo`:

```sql
BEGIN;

INSERT INTO lesson264_mapping_demo (
    code,
    label,
    quantity
)
SELECT
    'TX-1',
    'Dòng thử nghiệm',
    10;

SELECT
    code,
    label,
    quantity
FROM lesson264_mapping_demo
WHERE code = 'TX-1';

ROLLBACK;
```

Trong cùng transaction, `SELECT` thấy dòng mới được chèn. Sau `ROLLBACK`, dòng thử không được lưu.

Đối với thao tác sản xuất:

- Xác định **có cần tất cả dòng cùng thành công** không.
- Dùng transaction phù hợp với engine lưu trữ và DBMS.
- Xem số dòng trước và sau chèn.
- Ghi nhận lô, thời điểm và mã nguồn phục vụ truy vết.
- Quy định cách xử lý khi ràng buộc bị vi phạm.
- Không giả định sequence/identity trở về số cũ sau rollback.

### 18.1. Tính nguyên tử của một câu INSERT

Với các bảng transactional thông thường của PostgreSQL, nếu một câu `INSERT SELECT` gặp lỗi ràng buộc không được xử lý, **toàn bộ tác động của câu lệnh** được hủy và transaction có thể chuyển sang trạng thái lỗi đến khi rollback. Điều đó khác việc “chèn được 5 dòng rồi bỏ qua dòng thứ 6”.

Tuy nhiên, **không kết luận mọi hệ quản trị và mọi engine đều có cùng bảo đảm**. Trong MySQL, các engine transactional như InnoDB có tính chất khác với engine không hỗ trợ transaction. Một số cơ chế nhập hàng loạt chuyên dụng còn có chế độ bỏ qua hoặc ghi nhận lỗi từng dòng. Đọc tài liệu DBMS/engine được dùng trước khi thiết kế phục hồi khi lỗi.

### 18.2. Chia batch rất lớn

Một lô có hàng triệu dòng có thể cần phân trang, ghi theo batch hoặc dùng cơ chế nhập dữ liệu chuyên dụng. Khi chia batch, phải bảo đảm:

- Khóa xác định từng dòng là **duy nhất và ổn định**.
- Không phân trang theo thứ tự không xác định.
- Có checkpoint theo nguồn và khả năng chạy lại.
- Không bỏ sót/chèn trùng khi nguồn thay đổi đồng thời.
- Mỗi batch có giao dịch và cơ chế báo lỗi rõ ràng.

`INSERT SELECT` vẫn là mẫu hữu ích, nhưng kích thước lớn có thể yêu cầu kiến trúc nạp dữ liệu khác.

## 19. Chống nhập lặp bằng NOT EXISTS có đủ không?

Một mẫu thường gặp:

```sql
INSERT INTO lesson264_paid_archive (
    archived_code,
    archived_customer_id,
    archived_on,
    archived_amount
)
SELECT
    o.external_order_code,
    o.customer_id,
    o.order_date,
    o.amount
FROM lesson264_orders AS o
WHERE o.order_status = 'PAID'
  AND NOT EXISTS (
      SELECT 1
      FROM lesson264_paid_archive AS a
      WHERE a.archived_code = o.external_order_code
  );
```

Ý tưởng: chỉ đề nghị chèn mã chưa có ở archive.

**Nhưng `NOT EXISTS` tự nó không đủ để đảm bảo chống trùng khi có hai giao dịch đồng thời.** Hai giao dịch có thể cùng kiểm tra một mã chưa tồn tại, rồi cùng cố chèn. Ràng buộc `UNIQUE(archived_code)` mới là tầng bảo vệ quyết định; cần thêm cơ chế xử lý xung đột, cách cô lập hoặc khóa phù hợp.

Ngoài ra, `NOT EXISTS` trên bảng đích không giải quyết việc **chính nguồn SELECT có hai dòng cùng mã**. Hãy khử trùng lặp nguồn **và** đặt khóa unique đích.

### 19.1. Mẫu PostgreSQL thường vững hơn

```sql
INSERT INTO lesson264_paid_archive (
    archived_code,
    archived_customer_id,
    archived_on,
    archived_amount
)
SELECT
    o.external_order_code,
    o.customer_id,
    o.order_date,
    o.amount
FROM lesson264_orders AS o
WHERE o.order_status = 'PAID'
ON CONFLICT (archived_code) DO NOTHING;
```

`UNIQUE` cùng `ON CONFLICT` cho phép xử lý xung đột theo khóa ở mức DBMS. Dù vậy, bạn vẫn cần định nghĩa **dòng nào đúng**, **có cập nhật dữ liệu cũ không** và **ghi nhận kết quả lô nhập thế nào**.

## 20. Nếu muốn cập nhật khi mã đã tồn tại: UPSERT

Trong PostgreSQL, có thể kết hợp `INSERT SELECT` với `ON CONFLICT ... DO UPDATE`.

Ví dụ **mẫu thiết kế**, giả định một lô có thể gửi lại giá trị mới nhất cho cùng mã đơn:

```sql
-- Chỉ dùng sau khi đã xác định bản nguồn hợp lệ, duy nhất
-- theo external_order_code và chính sách ghi đè.
INSERT INTO lesson264_orders AS target (
    external_order_code,
    customer_id,
    order_date,
    amount,
    order_status,
    sales_channel,
    source_stage_id
)
SELECT
    r.source_code,
    r.customer_ref,
    r.ordered_on,
    r.gross_value,
    r.normalized_status,
    r.normalized_channel,
    r.stage_id
FROM some_valid_deduplicated_rows AS r
ON CONFLICT (external_order_code)
DO UPDATE SET
    customer_id = EXCLUDED.customer_id,
    order_date = EXCLUDED.order_date,
    amount = EXCLUDED.amount,
    order_status = EXCLUDED.order_status,
    sales_channel = EXCLUDED.sales_channel,
    source_stage_id = EXCLUDED.source_stage_id
WHERE
    target.source_stage_id < EXCLUDED.source_stage_id;
```

Ở đây `some_valid_deduplicated_rows` là **nguồn giả định đã được kiểm tra và chọn duy nhất**, không phải bảng đã tạo trong phần thực hành. Đoạn code thể hiện cách tổ chức `ON CONFLICT DO UPDATE`, không dùng trực tiếp như câu chạy hoàn chỉnh.

- `EXCLUDED` trong PostgreSQL biểu diễn các giá trị **đã được đề nghị chèn** nhưng xung đột.
- `target` là bí danh của bảng đích.
- `WHERE target.source_stage_id < EXCLUDED.source_stage_id` cho phép cập nhật chỉ khi ID staging mới hơn theo **chính sách mẫu**.

**Hạn chế quan trọng:** nguồn có `stage_id` lớn hơn chưa chắc đáng tin hơn hoặc mang sự kiện mới hơn. Nếu chính sách của doanh nghiệp dựa trên `effective_at`, trạng thái xác minh hay phiên bản nguồn, phải thay điều kiện `WHERE` tương ứng.

### 20.1. Cần khử trùng lặp nguồn trước UPSERT

Trong PostgreSQL, một câu `INSERT ... ON CONFLICT DO UPDATE` không thể dùng cùng một lệnh cập nhật **một dòng đích nhiều lần** do các dòng nguồn trùng khóa mà không xử lý phù hợp; có thể gặp lỗi liên quan đến việc ảnh hưởng cùng dòng nhiều lần. Vì vậy, **xác định một dòng nguồn duy nhất trên khóa xung đột trước** vẫn là yêu cầu thiết yếu.

### 20.2. UPSERT không đồng nghĩa MERGE ở mọi hệ quản trị

Các DBMS có cơ chế khác:

- PostgreSQL: `ON CONFLICT`; các phiên bản hiện đại còn có `MERGE`.
- MySQL: `ON DUPLICATE KEY UPDATE` và các quy tắc riêng.
- SQL Server: có `MERGE` và các mẫu `UPDATE`/`INSERT` riêng, phải xét concurrency.
- SQLite: có UPSERT `ON CONFLICT` ở các phiên bản hỗ trợ.
- Oracle: có `MERGE`, cú pháp và khả năng khác PostgreSQL.

Không chép nguyên cú pháp `EXCLUDED` của PostgreSQL sang mọi DBMS.

## 21. INSERT ... RETURNING để biết chính xác dòng đã chèn

PostgreSQL hỗ trợ:

```sql
INSERT INTO some_table (...)
SELECT ...
RETURNING ...;
```

`RETURNING` rất hữu ích vì:

- Nhận khóa nội bộ được cấp sau chèn.
- Biết **các dòng thực sự được chèn hoặc cập nhật** trong câu lệnh phù hợp.
- Tạo log hoặc xử lý bước tiếp theo trong ứng dụng.
- Tránh đoán giá trị `IDENTITY` hoặc dùng truy vấn lấy “ID cuối” không an toàn theo kiểu tự suy diễn.

Với bảng mapping demo:

```sql
INSERT INTO lesson264_mapping_demo (
    code,
    label,
    quantity
)
SELECT
    'R-1',
    'Hàng thử RETURNING',
    1
RETURNING
    code,
    label,
    quantity;
```

Đoạn này chèn một dòng và trả dòng đó.

### 21.1. RETURNING và DO NOTHING

Nếu `ON CONFLICT DO NOTHING` bỏ qua một dòng, dòng đó **không xuất hiện trong `RETURNING`**. Vì vậy, số dòng `RETURNING` có thể ít hơn số dòng nguồn đã đề nghị chèn.

Nếu cần biết lý do từng dòng không được chèn, cần một cơ chế kiểm toán nguồn, trạng thái xung đột và kết quả lô nhập; không chỉ dựa vào `RETURNING`.

### 21.2. Không phải DBMS nào cũng có RETURNING cùng cú pháp

SQL Server thường dùng `OUTPUT inserted...`. Oracle có các dạng `RETURNING` với phạm vi/sử dụng khác tùy loại DML. Khả năng `RETURNING` của SQLite phụ thuộc phiên bản. Khi dùng `INSERT SELECT` đa hệ quản trị, hãy kiểm tra cú pháp lấy dữ liệu sau ghi của từng DBMS.

## 22. Kiểm tra trước và sau khi INSERT

Một quy trình thực tế nên phân biệt **kiểm tra tập ứng viên** và **xác nhận bảng đích sau ghi**.

### 22.1. Trước khi ghi: xem số lượng và các khóa duy nhất

Sau khi xây CTE `valid_rows` và `ranked_rows`, bạn có thể dùng `SELECT` để xem những mã được chọn:

```sql
-- Phần SELECT cuối áp dụng khi có CTE ranked_rows
-- như định nghĩa ở phần 6.
SELECT
    source_code,
    stage_id,
    customer_ref,
    gross_value,
    normalized_status
FROM ranked_rows
WHERE rn = 1
ORDER BY source_code;
```

**Đây là đoạn SELECT tiếp nối CTE trong phần 6**, không phải câu chạy riêng sau dấu chấm phẩy. Khi thử độc lập, cần khai báo lại CTE.

Các câu hỏi cần xác minh:

- Có đúng **một dòng trên mỗi khóa nghiệp vụ** không?
- Số dòng hợp lệ có phù hợp với số bản ghi nguồn đã được chấp nhận không?
- Có dòng sai trạng thái/khách hàng/đơn vị tiền không?
- Có sự kiện bị loại bởi điều kiện `WHERE` mà nghiệp vụ thực sự cần không?

### 22.2. Sau khi ghi: đối chiếu theo khóa nguồn

```sql
SELECT
    o.external_order_code,
    o.customer_id,
    o.order_date,
    o.amount,
    o.order_status,
    o.sales_channel,
    o.source_stage_id
FROM lesson264_orders AS o
ORDER BY o.external_order_code;
```

Với dữ liệu mẫu sau chèn đúng, sẽ thấy sáu mã nguồn từ phần 7, trong đó `ORD-A101` gắn `source_stage_id = 1007`.

### 22.3. Đối chiếu tổng theo trạng thái

```sql
SELECT
    order_status,
    COUNT(*) AS order_count,
    SUM(amount) AS total_amount
FROM lesson264_orders
GROUP BY order_status
ORDER BY order_status;
```

Kết quả:

| order_status | order_count | total_amount |
|---|---:|---:|
| PAID | 4 | 510.000 |
| PENDING | 1 | 90.000 |
| REFUNDED | 1 | 70.000 |

Nếu tổng không khớp, hãy xem **mapping cột, điều kiện lọc, khử trùng lặp và khả năng ghi trước đó**. Không sửa kết quả bằng cách áp dụng `DISTINCT` tùy tiện lên số tiền.

### 22.4. Chú ý những lệnh INSERT không chèn dòng

Một câu `INSERT SELECT` trả 0 dòng từ nguồn là **thành công về mặt cú pháp** nhưng có thể là thất bại về kỳ vọng nghiệp vụ. Khi tải dữ liệu theo batch, nên có chỉ số:

- Dòng staging đọc.
- Dòng qua kiểm tra.
- Dòng bị loại do không hợp lệ.
- Dòng không được chọn do trùng mã.
- Dòng được đề nghị chèn.
- Dòng chèn mới.
- Dòng xung đột và bỏ qua hoặc cập nhật.

Định nghĩa chính xác cách đếm từng nhóm trước khi xây dashboard nhập liệu.

## 23. Một câu lệnh INSERT SELECT có thể đọc chính bảng đích không?

Về mặt cú pháp, nhiều DBMS cho phép dùng bảng đích trong nguồn `SELECT` của câu `INSERT` để **sao chép hoặc tạo thêm dòng từ chính bảng đó**, với quy tắc nhất quán dữ liệu riêng.

Ví dụ khái quát:

```sql
-- Ví dụ thiết kế, không chạy trên bảng thật nếu chưa rõ khóa.
INSERT INTO some_table (new_code, amount)
SELECT
    old_code || '-COPY',
    amount
FROM some_table
WHERE some_condition;
```

Nếu chạy lại mà không kiểm soát mã mới và điều kiện nguồn, bạn có thể tạo **nhiều thế hệ bản sao**. Ngoài ra, ràng buộc `UNIQUE` có thể chặn những lần chèn sau.

Với các tác vụ chép dữ liệu có giá trị thực, hãy dùng **khóa mới xác định được**, điều kiện lọc rõ ràng và giao dịch. Không giả định mọi DBMS có cùng mức hỗ trợ, snapshot hay hạn chế khi đọc bảng đang ghi.

## 24. So sánh INSERT SELECT với CREATE TABLE AS SELECT và MERGE

Đây là ba thao tác dễ bị đặt gần nhau nhưng giải quyết vấn đề khác nhau.

| Câu lệnh | Mục tiêu chính | Bảng đích có cần tồn tại? | Điểm cần nhớ |
|---|---|---|---|
| `INSERT INTO target(cols) SELECT ...` | **Thêm dòng** vào bảng đã có | **Có** | Ánh xạ theo danh sách cột đích và thứ tự SELECT |
| `CREATE TABLE new_table AS SELECT ...` | **Tạo bảng mới** từ kết quả truy vấn | Thường **không** | Không tự sao chép đầy đủ khóa, ràng buộc, trigger, chỉ mục của bảng nguồn |
| `MERGE` | Kết hợp xử lý matched/not matched theo điều kiện | **Có** | Cú pháp và hành vi tùy DBMS; cần chú ý dữ liệu nguồn trùng khóa và concurrency |
| `INSERT ... ON CONFLICT ...` | Thêm hoặc xử lý xung đột khóa ở PostgreSQL | **Có** | Cần khóa/ràng buộc phù hợp và chính sách cập nhật rõ |

Nếu mục tiêu là **đưa kết quả SELECT vào bảng đã thiết kế ràng buộc sẵn**, `INSERT INTO ... SELECT` là lựa chọn trực tiếp.

Nếu mục tiêu là **tạo một đối tượng bảng mới** từ truy vấn để thử nghiệm, `CREATE TABLE AS SELECT` có thể tiện, nhưng cần thiết kế bổ sung nếu muốn sử dụng như bảng nghiệp vụ có khóa và quy tắc toàn vẹn.

## 25. Lưu ý theo hệ quản trị

### 25.1. PostgreSQL

Dạng phổ biến:

```sql
INSERT INTO target (col1, col2)
SELECT expression1, expression2
FROM source
ON CONFLICT (unique_col) DO NOTHING
RETURNING unique_col;
```

PostgreSQL hỗ trợ `WITH` trước `INSERT`, `RETURNING`, `ON CONFLICT`, kiểu `IDENTITY` và nhiều công cụ chuyển đổi `::TYPE`.

**Cần xác định chính xác SELECT và mục tiêu xung đột trước khi chuyển sang DBMS khác.**

### 25.2. MySQL/MariaDB

Cấu trúc `INSERT INTO ... SELECT ...` cơ bản cũng phổ biến. Xử lý xung đột có những cơ chế như `ON DUPLICATE KEY UPDATE`, không dùng nguyên cú pháp `ON CONFLICT` của PostgreSQL. Kiểu boolean, tự tăng và xử lý lỗi phụ thuộc phiên bản, cấu hình SQL mode và engine lưu trữ.

### 25.3. SQL Server

T-SQL hỗ trợ `INSERT INTO target (cols) SELECT ...`; cột tự tăng có thể dùng `IDENTITY`, và để trả các dòng đã chèn thường dùng `OUTPUT inserted.column`. Không dùng nguyên cú pháp `RETURNING` và `ON CONFLICT` của PostgreSQL.

### 25.4. SQLite

SQLite hỗ trợ `INSERT INTO ... SELECT ...`, với quy tắc kiểu dữ liệu và `ON CONFLICT` riêng. Nếu kết hợp `INSERT ... SELECT` với UPSERT, trong một số trường hợp parser SQLite có thể cần mệnh đề `WHERE` rõ ràng ở `SELECT` để phân biệt `ON` của JOIN với `ON CONFLICT`. Kiểm tra tài liệu và phiên bản SQLite khi dùng cú pháp nâng cao.

### 25.5. Oracle Database

Oracle hỗ trợ `INSERT INTO ... SELECT ...`, nhưng cách quản lý identity/sequence, xử lý trùng và trả về giá trị sau DML khác PostgreSQL. Có thể dùng `MERGE` trong những bài toán cập nhật hoặc thêm theo điều kiện. Không mặc định `ON CONFLICT`, `::TYPE` hoặc `RETURNING` hoạt động y hệt PostgreSQL.

**Điểm có tính di động cao nhất:** khai báo rõ danh sách cột đích, tạo đúng số biểu thức trong `SELECT` theo đúng vị trí, và để bảng đích kiểm tra các ràng buộc đã thiết kế.

## 26. Những lỗi phổ biến khi INSERT INTO SELECT

### Lỗi 1. Cho rằng hệ quản trị ánh xạ theo tên cột

```sql
-- Nguồn có alias label rồi code, nhưng cột đích code rồi label.
INSERT INTO lesson264_mapping_demo (code, label, quantity)
SELECT
    'Hàng mẫu' AS label,
    'X-101' AS code,
    1 AS quantity;
```

Cột `code` nhận `'Hàng mẫu'`. Phải sửa **thứ tự biểu thức**, không chỉ đổi alias.

### Lỗi 2. Không ghi danh sách cột đích

`INSERT INTO target SELECT * FROM source` dễ sai khi schema khác nhau hoặc thay đổi. Hãy khai báo những cột cần ghi theo thứ tự rõ ràng.

### Lỗi 3. Số cột đích khác số biểu thức nguồn

Nếu liệt kê 7 cột đích nhưng `SELECT` trả 6 hoặc 8 biểu thức, câu chèn thường bị từ chối. Xác định đúng danh sách và không đưa cột tự sinh vào nguồn nếu không cần.

### Lỗi 4. Đưa NULL vào cột có DEFAULT và kỳ vọng DEFAULT được áp dụng

`NULL` là giá trị bạn đề nghị chèn, không phải đồng nghĩa với bỏ cột. Với cột `NOT NULL`, câu chèn bị từ chối; dùng `COALESCE` hoặc bỏ cột khỏi danh sách để lấy default tùy yêu cầu.

### Lỗi 5. Đưa mã khách không tồn tại vào bảng có FK

Dòng `customer_ref = 999` không tồn tại trong bảng khách. Kiểm tra trước ở staging và giữ FK ở đích để bảo vệ dữ liệu.

### Lỗi 6. Chèn hai dòng nguồn cùng khóa UNIQUE

Hai bản nguồn `ORD-A101` cần quy tắc chọn đại diện trước khi chèn. `DISTINCT` toàn hàng không bảo đảm mỗi mã chỉ còn một dòng.

### Lỗi 7. Không phân biệt “có thể ép kiểu” với “đúng ý nghĩa”

Hai cột chuỗi có thể chèn đảo vị trí mà không có lỗi kiểu. Một số tiền ghi nhầm sang cột khác cùng kiểu `NUMERIC` cũng có thể vượt qua kiểm tra kỹ thuật. Phải dựa vào **bảng ánh xạ nghiệp vụ**.

### Lỗi 8. Dùng JOIN một–nhiều rồi chèn nhiều dòng ngoài ý muốn

Nếu bảng đích mong một dòng trên đơn nhưng `SELECT` nối đơn với nhiều chi tiết, một đơn có thể bị đề nghị chèn nhiều lần. Hãy tổng hợp hoặc chọn một bản đúng grain trước.

### Lỗi 9. Coi ON CONFLICT DO NOTHING là đã “đồng bộ”

`DO NOTHING` giữ bản cũ nếu mã đã tồn tại. Nếu dữ liệu nguồn mới hơn và cần cập nhật, phải có chính sách `DO UPDATE` hoặc luồng đồng bộ khác.

### Lỗi 10. Dùng NOT EXISTS rồi bỏ khóa UNIQUE

Hai giao dịch đồng thời có thể cùng thấy mã chưa tồn tại. Dùng khóa UNIQUE và xử lý xung đột ở DBMS, không trông chờ kiểm tra trước bảo đảm tuyệt đối.

### Lỗi 11. Giả định IDENTITY không có lỗ hổng

Giá trị sequence có thể bị tiêu thụ dù chèn không thành công hoặc transaction bị rollback. Mã ID nội bộ không phải bộ đếm dòng đã chèn chắc chắn liền nhau.

### Lỗi 12. Không kiểm tra số dòng nguồn bằng 0

`INSERT SELECT` có thể thành công nhưng không chèn gì. Kiểm tra số dòng nguồn và số dòng thực ghi để phân biệt “không có dữ liệu hợp lệ” với “hệ thống đã nhập đủ”.

### Lỗi 13. Dùng ORDER BY làm cam kết ID tự sinh

`ORDER BY` trong nguồn có thể quyết định những dòng được chọn trước `LIMIT`, nhưng không nên dùng thứ tự đó như một hợp đồng gán ID hoặc thứ tự `RETURNING`. Dùng khóa nguồn để đối chiếu.

### Lỗi 14. Không có kế hoạch khôi phục khi chuyển dữ liệu

Phép chèn nhiều dòng cần kiểm soát transaction, quyền truy cập và khả năng chạy lại. Không tự xóa nguồn sau khi `INSERT SELECT` nếu chưa xác minh dữ liệu đích đầy đủ và chưa có phương án rollback.

## 27. Bài tập thực hành kèm lời giải

Các bài dưới đây dùng các bảng `lesson264_*` đã tạo ở phần 4, 14 và 15, trừ khi ghi rõ là ví dụ riêng. Bài sử dụng `INSERT` có thể tạo dữ liệu mới: thực hành ở database thử nghiệm và cân nhắc transaction/rollback khi cần.

### Bài 1. Đọc ánh xạ theo vị trí

Câu lệnh:

```sql
INSERT INTO lesson264_mapping_demo (
    quantity,
    code,
    label
)
SELECT
    7,
    'P-301',
    'Bìa hồ sơ';
```

**Câu hỏi:** Giá trị nào đi vào mỗi cột?

**Đáp án:** `quantity = 7`, `code = 'P-301'`, `label = 'Bìa hồ sơ'`. Danh sách đích có thứ tự khác cột vật lý của bảng nhưng được ánh xạ **với ba biểu thức nguồn theo đúng vị trí**.

### Bài 2. Tìm lỗi logic khi hai cột đều là VARCHAR

```sql
INSERT INTO lesson264_mapping_demo (code, label, quantity)
SELECT
    'Giấy A4' AS product_label,
    'A4-100' AS product_code,
    5 AS qty;
```

**Đáp án:** hai giá trị chuỗi bị đảo: `code` nhận `'Giấy A4'`, `label` nhận `'A4-100'`. Sửa:

```sql
INSERT INTO lesson264_mapping_demo (code, label, quantity)
SELECT
    'A4-100',
    'Giấy A4',
    5;
```

`AS` chỉ đổi **tên hiển thị** của cột nguồn; không thực hiện ánh xạ theo tên.

### Bài 3. Đếm số dòng staging đủ điều kiện trước khử trùng

```sql
SELECT COUNT(*) AS valid_before_dedup
FROM lesson264_stage_orders AS s
JOIN lesson264_customers AS c
    ON c.customer_id = s.customer_ref
WHERE s.batch_id = 'NOV26'
  AND s.is_accepted = TRUE
  AND s.gross_value >= 0
  AND UPPER(BTRIM(s.source_state))
      IN ('PAID', 'PENDING', 'REFUNDED');
```

**Đáp án:** **7 dòng**. Có cả `1001` và `1007` cùng mã `ORD-A101`.

### Bài 4. Khử trùng lặp theo source_code

```sql
WITH eligible AS (
    SELECT
        s.stage_id,
        s.source_code
    FROM lesson264_stage_orders AS s
    JOIN lesson264_customers AS c
        ON c.customer_id = s.customer_ref
    WHERE s.batch_id = 'NOV26'
      AND s.is_accepted = TRUE
      AND s.gross_value >= 0
      AND UPPER(BTRIM(s.source_state))
          IN ('PAID', 'PENDING', 'REFUNDED')
),
ranked AS (
    SELECT
        e.*,
        ROW_NUMBER() OVER (
            PARTITION BY source_code
            ORDER BY stage_id DESC
        ) AS rn
    FROM eligible AS e
)
SELECT
    source_code,
    stage_id
FROM ranked
WHERE rn = 1
ORDER BY source_code;
```

**Đáp án:** **6 dòng**; `ORD-A101` chọn `stage_id = 1007` theo chính sách ưu tiên ID lớn.

### Bài 5. Điền bảy cột đích từ bảy biểu thức nguồn

**Yêu cầu:** hoàn thiện ánh xạ để chèn dữ liệu staging đã chọn vào bảng đơn đích. Có thể dùng CTE `ranked_rows` từ phần 7.

```sql
INSERT INTO lesson264_orders (
    external_order_code,
    customer_id,
    order_date,
    amount,
    order_status,
    sales_channel,
    source_stage_id
)
SELECT
    r.source_code,
    r.customer_ref,
    r.ordered_on,
    r.gross_value,
    r.normalized_status,
    r.normalized_channel,
    r.stage_id
FROM ranked_rows AS r
WHERE r.rn = 1
ON CONFLICT (external_order_code) DO NOTHING;
```

**Giải thích:** đoạn trên là **phần `INSERT` tiếp nối CTE `WITH valid_rows, ranked_rows`** của phần 7. Nếu chạy riêng, cần khai báo lại hai CTE. Đây là ánh xạ bảy vị trí, còn `order_id` và `imported_at` được đích tự sinh/đặt mặc định.

### Bài 6. Sau nhập, tổng số đơn và tổng tiền là bao nhiêu?

```sql
SELECT
    COUNT(*) AS order_count,
    COALESCE(SUM(amount), 0) AS total_amount
FROM lesson264_orders;
```

**Đáp án:** khi bảng đích ban đầu rỗng và đã chạy đúng lần chèn ở phần 7, kết quả là **6 đơn**, **670000**. Nếu bảng có dữ liệu trước hoặc được thêm sau, con số có thể khác; đối chiếu theo batch và khóa nguồn.

### Bài 7. Phân biệt bỏ cột với chèn NULL

Bảng `lesson264_orders` có `sales_channel NOT NULL DEFAULT 'UNKNOWN'`. Hai trường hợp:

- A: `INSERT INTO lesson264_orders (... không có sales_channel ...) SELECT ...`.
- B: `INSERT INTO lesson264_orders (..., sales_channel, ...) SELECT ..., NULL, ...`.

**Đáp án:** A nhận giá trị `'UNKNOWN'` từ `DEFAULT` nếu dòng đáp ứng các ràng buộc khác. B yêu cầu ghi `NULL` nên bị ràng buộc `NOT NULL` từ chối. Nếu muốn chuyển giá trị kênh nguồn thiếu thành `'UNKNOWN'` mà vẫn giữ cột trong danh sách, dùng `COALESCE` rõ ràng.

### Bài 8. Những dòng nào bị từ chối do không hợp lệ?

```sql
SELECT
    s.stage_id,
    s.source_code
FROM lesson264_stage_orders AS s
LEFT JOIN lesson264_customers AS c
    ON c.customer_id = s.customer_ref
WHERE s.batch_id = 'NOV26'
  AND (
      s.is_accepted = FALSE
      OR c.customer_id IS NULL
      OR s.gross_value < 0
      OR UPPER(BTRIM(s.source_state))
         NOT IN ('PAID', 'PENDING', 'REFUNDED')
  )
ORDER BY s.stage_id;
```

**Đáp án:** các stage **1005, 1010, 1011, 1012, 1013**. Dòng 1006 thuộc batch `OCT26` nên không nằm trong phạm vi câu hỏi. Dòng 1001 hợp lệ nhưng có thể **không được chọn làm đại diện** do 1007 cùng mã; không nên gộp lý do này với lỗi kiểm tra dữ liệu.

### Bài 9. Sao chép các đơn PAID vào archive

```sql
INSERT INTO lesson264_paid_archive (
    archived_code,
    archived_customer_id,
    archived_on,
    archived_amount
)
SELECT
    external_order_code,
    customer_id,
    order_date,
    amount
FROM lesson264_orders
WHERE order_status = 'PAID'
ON CONFLICT (archived_code) DO NOTHING;
```

**Đáp án:** khi archive ban đầu rỗng, có **4 dòng**, tổng tiền **510000**. `archive_id` và `archived_at` nhận giá trị do đích tự sinh/mặc định.

### Bài 10. Tổng hợp theo trạng thái bằng INSERT SELECT

```sql
INSERT INTO lesson264_status_summary (
    order_status,
    order_count,
    total_amount
)
SELECT
    order_status,
    COUNT(*)::INTEGER,
    SUM(amount)
FROM lesson264_orders
GROUP BY order_status
ON CONFLICT (order_status) DO NOTHING;
```

**Đáp án:** từ sáu đơn mẫu, có `PAID: 4, 510000`; `PENDING: 1, 90000`; `REFUNDED: 1, 70000`. Nguồn đã `GROUP BY order_status` thành một dòng mỗi trạng thái.

### Bài 11. Vì sao NOT EXISTS chưa đủ chống nhập trùng đồng thời?

```sql
INSERT INTO lesson264_paid_archive (
    archived_code,
    archived_customer_id,
    archived_on,
    archived_amount
)
SELECT
    o.external_order_code,
    o.customer_id,
    o.order_date,
    o.amount
FROM lesson264_orders AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM lesson264_paid_archive AS a
    WHERE a.archived_code = o.external_order_code
);
```

**Đáp án:** hai giao dịch đồng thời có thể đều thấy cùng mã chưa có rồi đều cố chèn. `UNIQUE(archived_code)` bảo vệ bảng đích; tùy DBMS nên dùng cơ chế xử lý xung đột/giao dịch phù hợp. Ngoài ra, ví dụ trên **không lọc `PAID`**, nên có thể đề nghị chèn cả PENDING/REFUNDED; phải thêm điều kiện nghiệp vụ cần thiết.

### Bài 12. INSERT SELECT không có dòng nguồn

```sql
INSERT INTO lesson264_mapping_demo (
    code,
    label,
    quantity
)
SELECT
    'NONE-1',
    'Không có dòng',
    1
WHERE 1 = 0;
```

**Đáp án:** **0 dòng được chèn**. Không có lỗi cú pháp, nhưng số dòng nguồn bằng 0. Hãy kiểm tra số dòng bị ảnh hưởng nếu tác vụ yêu cầu phải nhập được ít nhất một dòng.

### Bài 13. Thử một phép chèn và không lưu dữ liệu

```sql
BEGIN;

INSERT INTO lesson264_mapping_demo (
    code,
    label,
    quantity
)
SELECT
    'TX-EXERCISE',
    'Dòng rollback',
    2;

SELECT *
FROM lesson264_mapping_demo
WHERE code = 'TX-EXERCISE';

ROLLBACK;
```

**Đáp án:** dòng `TX-EXERCISE` hiện trong `SELECT` bên trong transaction, nhưng không còn sau `ROLLBACK`. Đây là cách tập thử có kiểm soát trong PostgreSQL, không phải cách thay thế backup hoặc kế hoạch giao dịch cho nhập hàng loạt.

### Bài 14. Chọn đúng thứ tự để cập nhật snapshot nhập

Nguồn `some_valid_deduplicated_rows` có thể chứa mã đơn đã có. Yêu cầu chỉ cho phép dữ liệu mới ghi đè nếu `source_stage_id` lớn hơn giá trị đang lưu. Trong PostgreSQL, chính sách có thể biểu diễn bằng:

```sql
ON CONFLICT (external_order_code)
DO UPDATE SET
    amount = EXCLUDED.amount,
    source_stage_id = EXCLUDED.source_stage_id
WHERE target.source_stage_id < EXCLUDED.source_stage_id
```

**Giải thích:** đây là **đoạn xử lý xung đột**, phải gắn vào một câu `INSERT INTO lesson264_orders AS target ... SELECT ...` có nguồn đã khử trùng hợp lệ. Nó **không đủ cho mọi chính sách đồng bộ**: khi có nguồn nhập trễ hoặc thứ tự staging không phản ánh giá trị tin cậy, cần tiêu chí nghiệp vụ khác.

### Bài 15. Chọn công cụ phù hợp

Chọn giữa `INSERT VALUES`, `INSERT SELECT`, `CREATE TABLE AS SELECT`, và `MERGE`/UPSERT cho từng yêu cầu:

1. Thêm một khách hàng mới từ giá trị nhập trực tiếp.
2. Chèn toàn bộ đơn hợp lệ từ staging sang bảng đơn đã có khóa và CHECK.
3. Tạo một bảng thử nghiệm mới từ kết quả một câu SELECT.
4. Đồng bộ dòng theo khóa: nếu mã mới thì thêm, nếu mã đã có thì cập nhật có điều kiện.
5. Tạo bảng lưu doanh thu theo trạng thái từ `GROUP BY`.

**Gợi ý đáp án:**

1. `INSERT INTO ... VALUES ...`.
2. `INSERT INTO ... SELECT ...`, ánh xạ rõ ràng, kiểm tra và xử lý xung đột.
3. `CREATE TABLE ... AS SELECT ...` khi muốn **tạo bảng mới** và biết phải bổ sung ràng buộc nếu cần.
4. UPSERT/`MERGE` theo hỗ trợ của DBMS, với khóa duy nhất và chính sách xung đột rõ.
5. `INSERT INTO summary (...) SELECT ..., COUNT(*), SUM(...) FROM ... GROUP BY ...`.

## 28. Bảng ghi nhớ nhanh

| Câu hỏi | Câu trả lời cần nhớ |
|---|---|
| `INSERT INTO SELECT` để làm gì? | Chèn các dòng do một truy vấn `SELECT` tạo ra vào bảng đã tồn tại |
| Ánh xạ cột theo tên hay vị trí? | **Theo vị trí** giữa danh sách đích và biểu thức trong `SELECT` |
| Alias `AS` có quyết định cột đích không? | **Không**; alias chỉ đặt tên cho biểu thức đầu ra |
| Có cần ghi danh sách cột đích không? | Nên ghi rõ để tránh sai khi nguồn/đích khác schema |
| Số biểu thức `SELECT` cần bao nhiêu? | Phải khớp với số cột đích được liệt kê |
| Có thể dùng `WHERE`, `JOIN`, `GROUP BY`, CTE? | **Có**; SELECT có thể là truy vấn phức tạp |
| Cột đích không liệt kê sẽ nhận gì? | `DEFAULT` hoặc giá trị khác theo quy tắc schema; nếu không có default thường là `NULL` và có thể vi phạm `NOT NULL` |
| Chèn `NULL` có tương đương dùng `DEFAULT` không? | **Không** |
| Cột IDENTITY có cần nguồn không? | Thường **bỏ khỏi danh sách** để DBMS tự cấp |
| Nguồn có thể sinh nhiều dòng cùng khóa không? | Có; cần chọn đại diện/khử trùng và có `UNIQUE` ở đích |
| Chọn một nguồn hợp lệ theo quy tắc | `ROW_NUMBER() OVER (PARTITION BY key ORDER BY priority)`, lọc `rn = 1` |
| `ON CONFLICT DO NOTHING` có cập nhật dữ liệu cũ không? | **Không**; bỏ qua xung đột theo cơ chế PostgreSQL |
| `NOT EXISTS` đủ ngăn trùng đồng thời không? | **Không**; cần khóa/ràng buộc và xử lý transaction |
| `RETURNING` dùng khi nào? | Lấy dữ liệu các dòng thực sự được chèn/cập nhật theo cú pháp DBMS |
| `INSERT SELECT` có tạo bảng mới không? | **Không**; nếu muốn tạo bảng mới, xét `CREATE TABLE AS SELECT` |
| `INSERT SELECT` có xóa nguồn không? | **Không**; đây là thao tác thêm dòng ở đích |
| Nguồn `SELECT` trả 0 dòng? | Có thể chèn **0 dòng** mà không báo lỗi |
| Có bảo đảm ID tự sinh liên tục không? | **Không**; không suy luận ID từ số dòng hoặc thứ tự `SELECT` |
| Thử nghiệm trước ghi chính thức | Dùng `SELECT` xem trước, transaction, `RETURNING` và đối chiếu theo khóa |
| Khi nào cần `GROUP BY` trước INSERT? | Khi grain đích là một dòng trên nhóm, như mỗi khách/tháng/trạng thái |

## 29. Kết luận

**`INSERT INTO ... SELECT ...` là công cụ chuyển kết quả truy vấn thành dữ liệu được lưu trong bảng đích.** Sức mạnh của nó nằm ở việc kết hợp **lọc, JOIN, biến đổi kiểu, biểu thức, CTE và tổng hợp** ngay trong nguồn `SELECT`. Nhưng sự thuận tiện này cũng khiến những sai lệch ánh xạ hoặc điều kiện lọc có thể trở thành **dữ liệu sai được lưu lâu dài**.

Mẫu căn bản:

```sql
INSERT INTO destination_table (
    target_col_1,
    target_col_2,
    target_col_3
)
SELECT
    source_expr_1,    -- → target_col_1.
    source_expr_2,    -- → target_col_2.
    source_expr_3     -- → target_col_3.
FROM source_table
WHERE business_condition;
```

Khi triển khai một tác vụ thật, hãy kiểm tra lần lượt:

1. **Ánh xạ:** mỗi biểu thức nguồn có nằm đúng **vị trí cột đích** và đúng đơn vị/ý nghĩa không?
2. **Chất lượng nguồn:** dòng nào được phép nhập, dòng nào cần từ chối, có trùng khóa không?
3. **Ràng buộc đích:** `NOT NULL`, `CHECK`, `UNIQUE`, khóa ngoại và cột tự sinh có được đáp ứng không?
4. **Số dòng:** một dòng nguồn đại diện cho đơn, khách, chi tiết hay nhóm tổng hợp? Có bị nhân bởi `JOIN` không?
5. **Tính lặp lại:** nếu chạy batch lần nữa, nên bỏ qua, cập nhật hay báo lỗi theo khóa?
6. **Xác nhận:** số dòng thực ghi, tổng giá trị và mã nguồn có khớp dự kiến không? Có transaction/rollback khi cần không?

Chỉ khi sáu câu hỏi trên có câu trả lời rõ ràng, bạn mới nên coi một phép `INSERT SELECT` là **một quy trình nhập dữ liệu được kiểm soát**, thay vì chỉ là một câu SQL chạy không báo lỗi.

## Tài liệu tham khảo

- [PostgreSQL — INSERT](https://www.postgresql.org/docs/current/sql-insert.html): cú pháp `INSERT INTO ... SELECT`, danh sách cột, `ON CONFLICT` và `RETURNING`.
- [PostgreSQL — Data Definition: Default Values](https://www.postgresql.org/docs/current/ddl-default.html): giá trị mặc định cho các cột không được cung cấp.
- [PostgreSQL — Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): `NOT NULL`, `CHECK`, `UNIQUE`, khóa chính và khóa ngoại.
- [PostgreSQL — Window Functions](https://www.postgresql.org/docs/current/functions-window.html): `ROW_NUMBER` để chọn dòng đại diện trong mỗi nhóm nguồn.
- [Microsoft Learn — INSERT (Transact-SQL)](https://learn.microsoft.com/en-us/sql/t-sql/statements/insert-transact-sql): `INSERT ... SELECT` và các khác biệt của T-SQL.
- [MySQL Reference Manual — INSERT ... SELECT Statement](https://dev.mysql.com/doc/refman/8.4/en/insert-select.html): chèn kết quả truy vấn vào bảng MySQL.
- [SQLite — INSERT](https://www.sqlite.org/lang_insert.html): các dạng `INSERT` và xử lý xung đột.

