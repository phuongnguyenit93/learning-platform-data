# Tra cứu cấu trúc bằng information_schema và pg_catalog trong PostgreSQL

Khi tiếp nhận một PostgreSQL database chưa quen thuộc, câu hỏi đầu tiên thường không phải “bảng này có bao nhiêu dòng?” mà là **“hệ thống đang có những đối tượng nào, chúng được định nghĩa ra sao và liên hệ với nhau thế nào?”**. Người phát triển cần biết một cột có cho phép `NULL` không, khóa ngoại trỏ tới bảng nào, index có hợp lệ không, view được viết từ truy vấn nào, hoặc vì sao cùng tên bảng lại được tìm thấy trong schema khác.

PostgreSQL cung cấp hai nhóm nguồn metadata đặc biệt hữu ích:

- **`information_schema`**: một tập hợp view theo chuẩn SQL, cung cấp cách tra cứu cấu trúc tương đối dễ chuyển đổi giữa những hệ quản trị quan hệ.
- **`pg_catalog`**: các system catalog và view đặc thù PostgreSQL, lưu thông tin chi tiết mà `information_schema` có thể không cung cấp, chẳng hạn OID đối tượng, index expression, ràng buộc nội bộ, trạng thái index, partition và kích thước lưu trữ.

Bài học hướng dẫn tra cứu từ schema, bảng, cột đến khóa chính, khóa ngoại, index, view, sequence và quyền; giải thích cách ghép các system catalog bằng **OID** và **số thứ tự cột (attnum)**, đồng thời nêu những giới hạn liên quan đến quyền xem metadata, phiên bản PostgreSQL và các đối tượng đặc biệt. Ví dụ áp dụng cho PostgreSQL hiện đại (phần lớn từ phiên bản 12 trở lên) và dùng schema thực hành riêng để không ảnh hưởng dữ liệu thật.

## 1. Metadata là gì? Khác dữ liệu nghiệp vụ ở đâu?

Giả sử hệ thống có bảng `sales.orders`:

~~~sql
SELECT order_id, order_code, status
FROM sales.orders;
~~~

Câu lệnh trên đọc **dữ liệu nghiệp vụ** của các đơn hàng. Còn nếu muốn biết bảng `orders` có những cột nào, `status` là kiểu gì, `order_code` có unique hay không, ta cần tra cứu **metadata**.

| Thông tin | Ví dụ | Loại |
| --- | --- | --- |
| Một đơn hàng cụ thể | `SO-001` có trạng thái `PAID` | Dữ liệu nghiệp vụ |
| Tên cột | `order_code` | Metadata |
| Kiểu cột | `TEXT`, `TIMESTAMPTZ`, `NUMERIC(12,2)` | Metadata |
| Khóa chính | `orders_pkey` | Metadata |
| Quan hệ | `orders.customer_id` tham chiếu `customers.customer_id` | Metadata |
| Index | Index theo khách hàng và ngày đặt | Metadata |
| Chủ sở hữu/đặc quyền | Role nào có `SELECT` hay `UPDATE` | Metadata/quản trị |
| Ước tính hàng | `pg_class.reltuples` | Thống kê ước tính, không phải số hàng chính xác |

Trong PostgreSQL, metadata của phần lớn đối tượng được lưu ở **system catalogs**. Các view trong `information_schema` hoặc những view thân thiện như `pg_catalog.pg_tables` thường lấy thông tin từ các catalog này rồi trình bày ở hình thức dễ đọc.

~~~mermaid
flowchart TD
    D["DDL: CREATE TABLE / INDEX / VIEW"] --> C["PostgreSQL system catalogs<br/>pg_class, pg_attribute, pg_constraint..."]
    C --> I["information_schema<br/>view theo chuẩn SQL"]
    C --> P["pg_catalog views và functions"]
    I --> A["Ứng dụng / công cụ tra cấu trúc cơ bản"]
    P --> B["Quản trị / PostgreSQL-specific introspection"]
~~~

Không nên tự sửa dữ liệu trong các bảng system catalog bằng `INSERT`, `UPDATE` hoặc `DELETE`. Thay đổi cấu trúc phải đi qua DDL được PostgreSQL hỗ trợ để server cập nhật metadata, phụ thuộc, khóa và bộ nhớ đệm nội bộ đúng cách.

## 2. Chuẩn bị một schema ví dụ để chạy truy vấn metadata

Ta tạo schema `meta_lab` cùng bốn bảng: khách hàng, sản phẩm, đơn hàng và chi tiết đơn. Ngoài ra có một index và một view. Bộ DDL giúp các câu tra cứu metadata ở những mục sau trả kết quả có ý nghĩa.

**Chỉ chạy trên database học tập/trống mà bạn có quyền quản lý.** Nếu đã có schema `meta_lab` thuộc một bài tập khác, hãy chọn tên mới và thay tương ứng trong các truy vấn; đừng xóa đối tượng chưa biết nguồn gốc.

### 2.1. Tạo schema, bảng và ràng buộc

~~~sql
CREATE SCHEMA meta_lab;

CREATE TABLE meta_lab.customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY,
    customer_code TEXT NOT NULL,
    email TEXT NOT NULL,
    full_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT customers_pk PRIMARY KEY (customer_id),
    CONSTRAINT customers_code_uq UNIQUE (customer_code),
    CONSTRAINT customers_email_uq UNIQUE (email),
    CONSTRAINT customers_name_check
        CHECK (length(btrim(full_name)) > 0)
);

CREATE TABLE meta_lab.products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY,
    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,
    list_price NUMERIC(12, 2) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT products_pk PRIMARY KEY (product_id),
    CONSTRAINT products_sku_uq UNIQUE (sku),
    CONSTRAINT products_price_check CHECK (list_price > 0)
);

CREATE TABLE meta_lab.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY,
    order_code TEXT NOT NULL,
    customer_id BIGINT NOT NULL,
    ordered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    status TEXT NOT NULL DEFAULT 'NEW',

    CONSTRAINT orders_pk PRIMARY KEY (order_id),
    CONSTRAINT orders_code_uq UNIQUE (order_code),
    CONSTRAINT orders_customer_fk
        FOREIGN KEY (customer_id)
        REFERENCES meta_lab.customers (customer_id)
        ON DELETE RESTRICT,
    CONSTRAINT orders_status_check
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED'))
);

CREATE TABLE meta_lab.order_items (
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL,

    CONSTRAINT order_items_pk
        PRIMARY KEY (order_id, product_id),
    CONSTRAINT items_order_fk
        FOREIGN KEY (order_id)
        REFERENCES meta_lab.orders (order_id),
    CONSTRAINT items_product_fk
        FOREIGN KEY (product_id)
        REFERENCES meta_lab.products (product_id),
    CONSTRAINT items_quantity_check CHECK (quantity > 0),
    CONSTRAINT items_price_check CHECK (unit_price > 0)
);

CREATE INDEX idx_orders_customer_time
    ON meta_lab.orders (customer_id, ordered_at DESC);
~~~

Thiết kế này cho thấy:

- `customers` và `products` là bảng cha của các quan hệ nghiệp vụ.
- `orders.customer_id` tham chiếu khóa chính của `customers`.
- `order_items` sử dụng **khóa chính tổng hợp** `(order_id, product_id)`.
- Các ràng buộc `UNIQUE`, `CHECK` và `FOREIGN KEY` được đặt tên rõ ràng.
- `orders.order_id` dùng `IDENTITY` nên PostgreSQL có sequence liên quan để cấp ID.
- Index `idx_orders_customer_time` giúp quan sát metadata của index **không được tạo chỉ để thực thi khóa chính/khóa duy nhất**.

### 2.2. Tạo view và comment cho đối tượng

~~~sql
CREATE VIEW meta_lab.v_order_summary AS
SELECT
    o.order_id,
    o.order_code,
    c.customer_code,
    o.status,
    COALESCE(
        SUM(oi.quantity * oi.unit_price),
        0::numeric
    ) AS order_total
FROM meta_lab.orders AS o
JOIN meta_lab.customers AS c
    ON c.customer_id = o.customer_id
LEFT JOIN meta_lab.order_items AS oi
    ON oi.order_id = o.order_id
GROUP BY
    o.order_id, o.order_code, c.customer_code, o.status;

COMMENT ON TABLE meta_lab.orders IS
    'Đơn hàng thực hành để minh họa metadata PostgreSQL.';

COMMENT ON COLUMN meta_lab.orders.order_code IS
    'Mã nghiệp vụ duy nhất của đơn hàng.';
~~~

View giúp minh họa việc metadata không chỉ mô tả bảng vật lý. `COMMENT` là thông tin mô tả có thể được tra qua catalog. View tổng hợp này không thể được xem như một bảng vật lý độc lập được tự động lưu dữ liệu; nó biểu diễn truy vấn.

### 2.3. Nạp vài dòng để đối chiếu dữ liệu và cấu trúc

~~~sql
INSERT INTO meta_lab.customers (customer_code, email, full_name)
VALUES
    ('C001', 'an@example.test', 'Nguyễn An'),
    ('C002', 'binh@example.test', 'Trần Bình');

INSERT INTO meta_lab.products
    (sku, product_name, list_price)
VALUES
    ('BOOK-001', 'Sách PostgreSQL', 150000.00),
    ('PEN-001', 'Bút xanh',        20000.00);

INSERT INTO meta_lab.orders
    (order_code, customer_id, status)
SELECT
    'SO-001', customer_id, 'PAID'
FROM meta_lab.customers
WHERE customer_code = 'C001';

INSERT INTO meta_lab.order_items
    (order_id, product_id, quantity, unit_price)
SELECT
    o.order_id, p.product_id, 2, 150000.00
FROM meta_lab.orders AS o
CROSS JOIN meta_lab.products AS p
WHERE o.order_code = 'SO-001'
  AND p.sku = 'BOOK-001';
~~~

Các truy vấn **metadata** ở những phần tiếp theo không yêu cầu nạp dữ liệu. Phần seed chỉ giúp phân biệt việc `COUNT(*)` đọc dòng thật với những thông số ước tính ở system catalog. Với seed trên, view `meta_lab.v_order_summary` có một dòng và tổng tiền là `300000.00`.

## 3. Bắt đầu bằng môi trường hiện tại và search_path

Trước khi truy vấn catalog, cần xác nhận **đang kết nối vào database nào, với role nào và đang sử dụng schema tìm kiếm nào**.

~~~sql
SELECT
    current_database() AS database_name,
    current_user AS current_role,
    current_schema() AS first_schema,
    current_setting('search_path') AS search_path_text,
    current_schemas(TRUE) AS resolved_schemas;
~~~

`search_path` quyết định việc PostgreSQL tìm tên đối tượng **không có tiền tố schema**. Ví dụ nếu trong nhiều schema đều có bảng `orders`, câu:

~~~sql
SELECT * FROM orders;
~~~

có thể trỏ đến đối tượng khác nhau tùy đường tìm kiếm; còn:

~~~sql
SELECT * FROM meta_lab.orders;
~~~

chỉ rõ bảng trong schema `meta_lab`. Với công cụ phân tích metadata, migration hoặc code generator, nên **lọc theo tên schema đầy đủ** thay vì dựa trên `search_path` bất định.

### 3.1. Kiểm tra đối tượng có tồn tại mà không phát lỗi

~~~sql
SELECT
    to_regclass('meta_lab.orders') AS orders_object,
    to_regclass('meta_lab.unknown_table') AS missing_object;
~~~

`to_regclass(text)` tìm tên đối tượng có thể biểu diễn như `regclass` và trả `NULL` khi tên không tìm thấy, thay vì luôn gây lỗi như ép kiểu trực tiếp `'...'::regclass` đối với tên không tồn tại.

Lưu ý: `regclass` không chỉ biểu diễn “bảng dữ liệu”, mà còn có thể trỏ đến đối tượng trong `pg_class` như view, sequence hoặc index. Muốn xác nhận **loại** đối tượng, cần kiểm tra thêm `pg_class.relkind`.

### 3.2. Những schema hệ thống thường gặp

| Schema | Mục đích |
| --- | --- |
| `pg_catalog` | System catalogs, functions, types và các đối tượng nội bộ |
| `information_schema` | Các view metadata theo chuẩn SQL |
| `public` | Schema thông dụng do database tạo sẵn, quyền cụ thể phụ thuộc cấu hình/phiên bản |
| `pg_toast` | Cơ chế lưu trữ nội bộ cho giá trị lớn |
| `pg_temp_N` | Schema tạm của session khi cần |
| `meta_lab` | Schema ứng dụng/thực hành do ta tạo |

Không nên đưa bảng ứng dụng vào `pg_catalog` hoặc sửa đối tượng hệ thống. Khi liệt kê mọi schema, có thể thấy nhiều schema kỹ thuật không phải schema nghiệp vụ.

## 4. information_schema là gì và khi nào nên dùng?

`information_schema` bao gồm các view như:

- `information_schema.schemata` — schema.
- `information_schema.tables` — bảng và view có thể nhìn thấy theo điều kiện quyền.
- `information_schema.columns` — cột và đặc tính.
- `information_schema.table_constraints` — ràng buộc.
- `information_schema.key_column_usage` — cột tham gia một số ràng buộc khóa.
- `information_schema.constraint_column_usage` — cột liên quan đến ràng buộc.
- `information_schema.referential_constraints` — các thuộc tính khóa ngoại.
- `information_schema.views` — định nghĩa view khi được phép xem.
- `information_schema.sequences` — metadata sequence ở mức chuẩn.

Ưu điểm là tên trường tương đối gần chuẩn SQL, không đòi hỏi hiểu nhiều OID và cấu trúc lưu trữ bên trong PostgreSQL. Tuy nhiên:

1. Chúng chỉ bao phủ **phần metadata phù hợp với mô hình chuẩn** và cách PostgreSQL triển khai.
2. Những view này thường **lọc theo quyền truy cập**; không thấy đối tượng không luôn có nghĩa đối tượng không tồn tại.
3. Các chi tiết riêng như **expression index**, trạng thái `indisvalid`, loại bảng partition, tệp lưu trữ hoặc materialized view có thể cần `pg_catalog`.
4. “Chuẩn SQL” không có nghĩa câu lệnh cụ thể có thể copy nguyên xi giữa PostgreSQL, MySQL, SQL Server và Oracle mà kết quả giống nhau.

## 5. Tra cứu schema và bảng bằng information_schema

### 5.1. Liệt kê các schema người dùng có thể quan sát

~~~sql
SELECT
    catalog_name,
    schema_name,
    schema_owner
FROM information_schema.schemata
WHERE schema_name = 'meta_lab';
~~~

`catalog_name` trong ngữ cảnh PostgreSQL thường phản ánh **database hiện tại**. Không nhầm cột này với tên một database khác mà connection có thể đọc bảng trực tiếp.

### 5.2. Liệt kê bảng và view trong schema

~~~sql
SELECT
    table_catalog,
    table_schema,
    table_name,
    table_type
FROM information_schema.tables
WHERE table_schema = 'meta_lab'
ORDER BY table_type, table_name;
~~~

Với bộ đối tượng đã tạo, ta kỳ vọng thấy bốn bảng và một view:

| `table_name` | `table_type` |
| --- | --- |
| `customers` | `BASE TABLE` |
| `products` | `BASE TABLE` |
| `orders` | `BASE TABLE` |
| `order_items` | `BASE TABLE` |
| `v_order_summary` | `VIEW` |

Thứ tự in ra thực tế do `ORDER BY` quyết định; bảng ở đây nhóm theo loại để dễ hiểu. `table_type` trong PostgreSQL cũng có thể phản ánh loại bảng khác như foreign table khi phù hợp.

Nếu một role không có quyền thích hợp trên các bảng/view, kết quả từ `information_schema.tables` có thể chỉ hiện một phần. Việc truy vấn metadata **không tự cấp quyền đọc nội dung bảng**.

### 5.3. Đếm bảng theo schema

~~~sql
SELECT
    table_schema,
    COUNT(*) AS accessible_base_tables
FROM information_schema.tables
WHERE table_type = 'BASE TABLE'
  AND table_schema = 'meta_lab'
GROUP BY table_schema;
~~~

Đây là số **bảng cơ sở có thể xuất hiện trong view metadata theo quyền hiện tại**, không nhất thiết là kiểm kê tuyệt đối tất cả object của instance. Và `COUNT(*)` ở đây đếm **các bản ghi metadata**, không phải số hàng nghiệp vụ trong bảng.

## 6. Xem cột, thứ tự, kiểu dữ liệu và giá trị mặc định

Một câu truy vấn thường dùng nhất khi tiếp nhận hệ thống là:

~~~sql
SELECT
    table_name,
    ordinal_position,
    column_name,
    data_type,
    udt_name,
    character_maximum_length,
    numeric_precision,
    numeric_scale,
    is_nullable,
    column_default,
    is_identity,
    identity_generation
FROM information_schema.columns
WHERE table_schema = 'meta_lab'
  AND table_name = 'orders'
ORDER BY ordinal_position;
~~~

Ý nghĩa các trường:

| Trường | Diễn giải |
| --- | --- |
| `ordinal_position` | Vị trí cột theo thứ tự định nghĩa có thể nhìn thấy |
| `column_name` | Tên cột |
| `data_type` | Tên kiểu theo biểu diễn của `information_schema` |
| `udt_name` | Tên kiểu nền trong PostgreSQL; hữu ích với một số kiểu đặc thù |
| `character_maximum_length` | Giới hạn độ dài nếu kiểu và khai báo có thông tin đó |
| `numeric_precision` / `numeric_scale` | Độ chính xác và số chữ số thập phân khi phù hợp |
| `is_nullable` | `YES` hoặc `NO` theo thông tin nullability của cột |
| `column_default` | Biểu thức default khi có thể xem, không nhất thiết giống source SQL ban đầu |
| `is_identity` | `YES` nếu cột identity |
| `identity_generation` | Ví dụ `ALWAYS` đối với identity được định nghĩa như bài |

Với `meta_lab.orders`, `order_id` là `BIGINT GENERATED ALWAYS AS IDENTITY`; hãy đọc `is_identity` thay vì suy ra identity chỉ bằng cách tìm chuỗi `nextval(...)` trong `column_default`. Identity và kiểu khai báo kiểu `serial` có khác biệt về ngữ nghĩa quản lý sequence.

### 6.1. data_type và udt_name không luôn giống nhau

Trong PostgreSQL, kiểu dữ liệu có thể là:

- Kiểu SQL phổ biến: `integer`, `numeric`, `character varying`.
- Kiểu PostgreSQL đặc thù: `uuid`, `jsonb`, `inet`, `timestamptz` (thường thể hiện trong catalog dưới tên nội bộ).
- Kiểu người dùng định nghĩa: enum, domain, composite.
- Array hoặc kiểu đặc biệt khác.

`information_schema.columns.data_type` có thể dùng tên theo chuẩn hoặc giá trị như `USER-DEFINED`, `ARRAY`. Trong một số trường hợp cần `udt_schema`, `udt_name`, `domain_schema` và `domain_name` để hiểu đúng kiểu cơ sở hoặc domain:

~~~sql
SELECT
    column_name,
    data_type,
    udt_schema,
    udt_name,
    domain_schema,
    domain_name
FROM information_schema.columns
WHERE table_schema = 'meta_lab'
  AND table_name = 'orders'
ORDER BY ordinal_position;
~~~

Nếu công cụ sinh mã cần tái tạo **kiểu PostgreSQL với typmod**, `pg_catalog.format_type` thường hữu ích hơn ghép tay `data_type` và độ dài.

### 6.2. NULL và CHECK là hai lớp kiểm tra khác nhau

`is_nullable = 'NO'` phản ánh thông tin không cho phép `NULL`. Một `CHECK (quantity > 0)` đơn thuần **không tự cấm NULL**: trong PostgreSQL, `CHECK` được xem là thỏa khi biểu thức trả `TRUE` hoặc `UNKNOWN` do `NULL`; cần khai báo `NOT NULL` riêng để cấm giá trị thiếu.

Vì vậy, khi đọc metadata, cần kiểm tra **cả nullability và ràng buộc CHECK**, không chỉ nhìn một cột `data_type`.

## 7. Tra cứu các ràng buộc chuẩn bằng information_schema

PostgreSQL dùng ràng buộc để bảo vệ dữ liệu, và `information_schema.table_constraints` cho biết loại của chúng.

~~~sql
SELECT
    table_name,
    constraint_name,
    constraint_type,
    is_deferrable,
    initially_deferred
FROM information_schema.table_constraints
WHERE table_schema = 'meta_lab'
ORDER BY table_name, constraint_type, constraint_name;
~~~

Những loại thường gặp:

| `constraint_type` | Ý nghĩa |
| --- | --- |
| `PRIMARY KEY` | Khóa chính, không trùng và không `NULL` |
| `UNIQUE` | Giá trị/cặp giá trị khóa duy nhất theo ngữ nghĩa ràng buộc |
| `FOREIGN KEY` | Bảo vệ tham chiếu từ bảng con tới bảng cha |
| `CHECK` | Giới hạn điều kiện trên dữ liệu |

`NOT NULL` được thể hiện rõ trong `information_schema.columns.is_nullable`; tùy phiên bản PostgreSQL, cách ghi nhận nội bộ ràng buộc `NOT NULL` có thể thay đổi. Đừng trông chờ mọi yêu cầu không-null đều phải xuất hiện như một dòng cùng kiểu trong `table_constraints`.

### 7.1. Xem các cột thuộc PRIMARY KEY và UNIQUE

~~~sql
SELECT
    tc.table_name,
    tc.constraint_name,
    tc.constraint_type,
    kcu.ordinal_position,
    kcu.column_name
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
    ON kcu.constraint_catalog = tc.constraint_catalog
   AND kcu.constraint_schema = tc.constraint_schema
   AND kcu.constraint_name = tc.constraint_name
   AND kcu.table_schema = tc.table_schema
   AND kcu.table_name = tc.table_name
WHERE tc.table_schema = 'meta_lab'
  AND tc.constraint_type IN ('PRIMARY KEY', 'UNIQUE')
ORDER BY
    tc.table_name,
    tc.constraint_name,
    kcu.ordinal_position;
~~~

Với bảng `order_items`, constraint `order_items_pk` phải có hai cột theo thứ tự:

~~~text
ordinal_position = 1 -> order_id
ordinal_position = 2 -> product_id
~~~

**Thứ tự cột có ý nghĩa.** Nó liên quan cách khóa tổng hợp được khai báo và index liên quan được tổ chức. Không nên gom cột vào một chuỗi bằng phép aggregate thiếu `ORDER BY ordinal_position` rồi cho rằng thứ tự tự nhiên luôn ổn định.

### 7.2. Tổng hợp cột của một ràng buộc thành một hàng

~~~sql
SELECT
    tc.table_name,
    tc.constraint_name,
    tc.constraint_type,
    string_agg(
        quote_ident(kcu.column_name),
        ', ' ORDER BY kcu.ordinal_position
    ) AS constraint_columns
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
    ON kcu.constraint_catalog = tc.constraint_catalog
   AND kcu.constraint_schema = tc.constraint_schema
   AND kcu.constraint_name = tc.constraint_name
   AND kcu.table_schema = tc.table_schema
   AND kcu.table_name = tc.table_name
WHERE tc.table_schema = 'meta_lab'
  AND tc.constraint_type IN ('PRIMARY KEY', 'UNIQUE')
GROUP BY
    tc.table_name,
    tc.constraint_name,
    tc.constraint_type
ORDER BY tc.table_name, tc.constraint_name;
~~~

`quote_ident` trích dẫn tên cột an toàn cho mục đích hiển thị theo cú pháp identifier PostgreSQL. Trong code generator, cần phân biệt rõ **identifier** với **giá trị dữ liệu**, không đưa tên do người dùng nhập vào SQL bằng phép nối chuỗi thiếu kiểm soát.

### 7.3. Xem các thuộc tính của FOREIGN KEY

~~~sql
SELECT
    tc.table_name AS child_table,
    tc.constraint_name,
    rc.match_option,
    rc.update_rule,
    rc.delete_rule
FROM information_schema.table_constraints AS tc
JOIN information_schema.referential_constraints AS rc
    ON rc.constraint_catalog = tc.constraint_catalog
   AND rc.constraint_schema = tc.constraint_schema
   AND rc.constraint_name = tc.constraint_name
WHERE tc.table_schema = 'meta_lab'
  AND tc.constraint_type = 'FOREIGN KEY'
ORDER BY child_table, tc.constraint_name;
~~~

`update_rule` và `delete_rule` có thể trả những hành động như `NO ACTION`, `RESTRICT`, `CASCADE`, `SET NULL` hoặc `SET DEFAULT` theo định nghĩa. Thông tin này trả lời câu hỏi “Điều gì xảy ra khi khóa ở bảng cha bị sửa hoặc bản ghi cha bị xóa?”.

Ở hệ thống có nhiều schema và tên constraint trùng, việc join bằng **catalog, schema, tên constraint** là cần thiết. Với các truy vấn mapping FK phức tạp, đặc biệt khóa ngoại nhiều cột, sử dụng OID trong `pg_catalog` thường rõ ràng và ít nhập nhằng hơn.

## 8. Khi nào phải chuyển sang pg_catalog?

`pg_catalog` là schema chứa các catalog và một số view, function hệ thống. Các catalog quan trọng cho việc tra cấu trúc:

| Catalog/view/function | Nội dung chính |
| --- | --- |
| `pg_namespace` | Schema / namespace |
| `pg_class` | Table, view, materialized view, index, sequence và nhiều đối tượng quan hệ |
| `pg_attribute` | Thuộc tính/cột của relation, theo `attnum` |
| `pg_type` | Định nghĩa kiểu dữ liệu và kiểu do người dùng tạo |
| `pg_attrdef` | Default hoặc biểu thức sinh cột |
| `pg_constraint` | Khóa chính, unique, foreign key, check, exclusion và metadata liên quan |
| `pg_index` | Cấu trúc và trạng thái index |
| `pg_inherits` / `pg_partitioned_table` | Quan hệ kế thừa và bảng phân vùng |
| `pg_description` | Comment trên đối tượng/cột |
| `pg_depend` | Phụ thuộc giữa các đối tượng |
| `pg_proc` | Function/procedure |
| `pg_trigger` | Trigger |
| `pg_sequence` / `pg_sequences` | Thuộc tính sequence và view thân thiện |
| `pg_tables`, `pg_views`, `pg_matviews`, `pg_indexes` | Những view tra cứu đơn giản hơn catalog gốc |
| `pg_get_constraintdef`, `pg_get_indexdef`, `pg_get_viewdef` | Hàm dựng lại định nghĩa dễ đọc |

Các catalog này là **chi tiết triển khai PostgreSQL**, không phải hợp đồng metadata chuẩn SQL cho mọi DBMS. Schema, tên cột hoặc semantics có thể thay đổi giữa major versions. Công cụ introspection nên được thử nghiệm theo các phiên bản PostgreSQL mà ứng dụng hỗ trợ.

## 9. Hiểu OID, attnum và relkind trước khi JOIN catalog

Ba khái niệm đặc thù:

- **OID** (*Object Identifier*): định danh nội bộ của nhiều đối tượng catalog, thường dùng để join giữa các catalog trong **database hiện tại**.
- **`attnum`**: số thứ tự của thuộc tính trong một relation; kết hợp với `attrelid` để xác định cột.
- **`relkind`**: ký hiệu phân loại relation trong `pg_class`.

~~~mermaid
flowchart LR
    N["pg_namespace<br/>oid, nspname"] -->|"oid = relnamespace"| C["pg_class<br/>oid, relname, relkind"]
    C -->|"oid = attrelid"| A["pg_attribute<br/>attnum, attname, atttypid"]
    A -->|"atttypid = oid"| T["pg_type<br/>typname"]
    C -->|"oid = conrelid"| K["pg_constraint<br/>contype, conkey, confrelid"]
    C -->|"oid = indrelid"| I["pg_index<br/>indexrelid, indisvalid"]
~~~

**OID là định danh nội bộ**, không phải mã nghiệp vụ ổn định cho ứng dụng. Sau dump/restore hoặc tạo lại object, OID có thể khác. Không đưa OID của bảng vào dữ liệu nghiệp vụ làm khóa lâu dài nếu không có lý do và cơ chế vòng đời rõ ràng.

### 9.1. Các giá trị relkind thường dùng

| `pg_class.relkind` | Loại |
| --- | --- |
| `r` | Bảng thông thường (*ordinary table*) |
| `p` | Bảng phân vùng (*partitioned table*) |
| `v` | View |
| `m` | Materialized view |
| `f` | Foreign table |
| `S` | Sequence |
| `i` | Index |
| `I` | Partitioned index |

`pg_class` còn chứa các relation nội bộ khác, ví dụ TOAST và composite type. Nếu muốn liệt kê “bảng người dùng”, cần lọc `relkind` và schema phù hợp, không chỉ `SELECT * FROM pg_class` rồi đếm mọi dòng.

### 9.2. Liệt kê các đối tượng trong một schema bằng pg_class

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    c.relkind,
    pg_get_userbyid(c.relowner) AS owner_name,
    c.relpersistence
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'meta_lab'
  AND c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S', 'i', 'I')
ORDER BY c.relkind, c.relname;
~~~

`relpersistence` mô tả việc relation được định nghĩa như persistent, unlogged hoặc temporary (các ký hiệu như `p`, `u`, `t`). Nó **khác `relkind`**: một cột nói về loại đối tượng, cột kia nói về tính lưu trữ.

Nếu người học thấy các index và sequence trong kết quả, đó không phải “bảng dữ liệu bị tạo thừa”. Chúng là những đối tượng có metadata trong `pg_class`.

## 10. Tra cứu định nghĩa cột bằng pg_attribute

Với catalog, ta ghép `pg_class`, `pg_namespace`, `pg_attribute` và `pg_attrdef`:

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    a.attnum AS column_position,
    a.attname AS column_name,
    pg_catalog.format_type(a.atttypid, a.atttypmod)
        AS formatted_type,
    a.attnotnull AS is_not_null,
    a.attidentity AS identity_kind,
    a.attgenerated AS generated_kind,
    pg_catalog.pg_get_expr(d.adbin, d.adrelid)
        AS default_or_generation_expr
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
JOIN pg_catalog.pg_attribute AS a
    ON a.attrelid = c.oid
LEFT JOIN pg_catalog.pg_attrdef AS d
    ON d.adrelid = a.attrelid
   AND d.adnum = a.attnum
WHERE n.nspname = 'meta_lab'
  AND c.relname = 'orders'
  AND c.relkind IN ('r', 'p')
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
~~~

Vì sao điều kiện `a.attnum > 0 AND NOT a.attisdropped` quan trọng?

- PostgreSQL có các **system columns** như `ctid` và `xmin` được mô tả bằng số thuộc tính đặc biệt; không phải cột SQL do ứng dụng định nghĩa.
- Khi `DROP COLUMN`, thông tin vị trí cũ có thể được giữ theo cơ chế nội bộ. Không lọc `attisdropped` có thể làm công cụ sinh schema nhìn thấy cột đã xóa.
- `attnum` là **vị trí nội bộ trong relation**, không phải thứ tự cột tự do thay đổi mà không ảnh hưởng metadata. Có thể tồn tại khoảng trống do cột đã drop.

`format_type(atttypid, atttypmod)` dựng kiểu hiển thị như `numeric(12,2)` và thường thuận tiện hơn tự nối `pg_type.typname` với các thuộc tính precision/length.

### 10.1. Thông tin identity và generated columns

Trong `pg_attribute`:

- `attidentity` có thể biểu diễn cột identity theo kiểu `ALWAYS` hoặc `BY DEFAULT`, và rỗng với cột thường.
- `attgenerated` cho biết cột generated theo các dạng mà phiên bản PostgreSQL hỗ trợ; thường là ký hiệu rỗng khi không phải generated.
- `pg_attrdef` và `pg_get_expr` có thể mô tả biểu thức default hoặc biểu thức của generated column.

Đừng coi mọi cột dùng sequence đều có `column_default LIKE 'nextval%'`: cột identity được quản lý khác với cách khai báo `serial` truyền thống. Khi cần phát hiện sequence đi kèm cột, dùng các hàm/catalog chuyên biệt thay vì chỉ tìm chuỗi default.

## 11. Lấy định nghĩa ràng buộc trực tiếp từ pg_constraint

`pg_constraint` chứa thông tin phong phú hơn view metadata chuẩn, đặc biệt hữu ích cho khóa ngoại nhiều cột, deferrable constraints và kiểm tra việc ràng buộc đã validate hay chưa.

~~~sql
SELECT
    c.relname AS table_name,
    con.conname AS constraint_name,
    con.contype AS constraint_kind,
    con.condeferrable AS is_deferrable,
    con.condeferred AS initially_deferred,
    con.convalidated AS is_validated,
    pg_catalog.pg_get_constraintdef(con.oid, TRUE)
        AS definition
FROM pg_catalog.pg_constraint AS con
JOIN pg_catalog.pg_class AS c
    ON c.oid = con.conrelid
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'meta_lab'
ORDER BY c.relname, con.conname;
~~~

Một số mã `contype` thường thấy:

| `contype` | Ý nghĩa |
| --- | --- |
| `p` | Primary key |
| `u` | Unique constraint |
| `f` | Foreign key |
| `c` | Check constraint |
| `x` | Exclusion constraint |

`pg_get_constraintdef(con.oid, TRUE)` giúp dựng lại biểu thức SQL tương ứng, ví dụ:

~~~text
PRIMARY KEY (order_id, product_id)
FOREIGN KEY (customer_id) REFERENCES meta_lab.customers(customer_id) ON DELETE RESTRICT
CHECK ((quantity > 0))
~~~

Đây là **dạng hiển thị minh họa**; PostgreSQL có thể thêm dấu ngoặc, quote identifier hoặc các tùy chọn khác. Nếu cần lưu DDL, nên dùng công cụ dump/schema migration phù hợp, không tự giả định văn bản deparse là nguyên văn file migration ban đầu.

### 11.1. Các trường về tính hợp lệ và trì hoãn

`convalidated` giúp xem ràng buộc đã được validate hay chưa khi loại constraint và cú pháp tương ứng cho phép trạng thái `NOT VALID`. `condeferrable`/`condeferred` mô tả khả năng trì hoãn kiểm tra và trạng thái ban đầu.

Không phải mọi loại constraint đều có thể dùng `NOT VALID` hay `DEFERRABLE`. Ví dụ kiểm tra nullability và unique index có những quy tắc riêng. Công cụ introspection cần hiểu **loại constraint** chứ không chỉ đọc một boolean rồi suy luận quá rộng.

### 11.2. Tra cột của FOREIGN KEY nhiều cột bằng OID và attnum

Khóa ngoại nhiều cột có dạng:

~~~sql
FOREIGN KEY (col_a, col_b)
REFERENCES parent_table (parent_a, parent_b)
~~~

Muốn biết `col_a` ứng với `parent_a`, không được chỉ join qua tên constraint rồi ghép tùy thứ tự. `pg_constraint` lưu:

- `conrelid`: OID của bảng con.
- `confrelid`: OID của bảng cha (với foreign key).
- `conkey`: mảng `attnum` của các cột ở bảng con.
- `confkey`: mảng `attnum` tương ứng ở bảng cha.

Truy vấn dưới đây đọc **từng cặp cột theo vị trí trong mảng**:

~~~sql
SELECT
    child_ns.nspname AS child_schema,
    child.relname AS child_table,
    con.conname AS foreign_key_name,
    k.pos AS column_pair_position,
    child_col.attname AS child_column,
    parent_ns.nspname AS parent_schema,
    parent.relname AS parent_table,
    parent_col.attname AS parent_column
FROM pg_catalog.pg_constraint AS con
JOIN pg_catalog.pg_class AS child
    ON child.oid = con.conrelid
JOIN pg_catalog.pg_namespace AS child_ns
    ON child_ns.oid = child.relnamespace
JOIN pg_catalog.pg_class AS parent
    ON parent.oid = con.confrelid
JOIN pg_catalog.pg_namespace AS parent_ns
    ON parent_ns.oid = parent.relnamespace
CROSS JOIN LATERAL
    generate_subscripts(con.conkey, 1) AS k(pos)
JOIN pg_catalog.pg_attribute AS child_col
    ON child_col.attrelid = con.conrelid
   AND child_col.attnum = con.conkey[k.pos]
JOIN pg_catalog.pg_attribute AS parent_col
    ON parent_col.attrelid = con.confrelid
   AND parent_col.attnum = con.confkey[k.pos]
WHERE con.contype = 'f'
  AND child_ns.nspname = 'meta_lab'
ORDER BY
    child.relname,
    con.conname,
    k.pos;
~~~

Với dữ liệu thực hành, ta sẽ thấy các quan hệ:

~~~text
orders.customer_id          -> customers.customer_id
order_items.order_id        -> orders.order_id
order_items.product_id      -> products.product_id
~~~

Truy vấn này vẫn có ích nếu sau này xuất hiện một foreign key hai hoặc ba cột. OID của constraint là định danh nội bộ đáng tin cậy cho phép nối trong cùng catalog, trong khi tên constraint riêng lẻ không nhất thiết duy nhất trong toàn instance.

## 12. Tra cứu index: dùng pg_indexes hay pg_index?

`information_schema` không cung cấp một view chuẩn tương đương đầy đủ với `pg_index` để phân tích mọi đặc tính index đặc thù PostgreSQL. Cách đơn giản nhất:

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_catalog.pg_indexes
WHERE schemaname = 'meta_lab'
ORDER BY tablename, indexname;
~~~

Kết quả bao gồm cả **index do ràng buộc PRIMARY KEY/UNIQUE tạo ra** và index được tạo bằng `CREATE INDEX`. Vì vậy, số index thường **lớn hơn số lệnh CREATE INDEX viết trực tiếp** trong DDL.

### 12.1. Xem index có unique/primary/valid hay không

~~~sql
SELECT
    t.relname AS table_name,
    i.relname AS index_name,
    x.indisunique AS is_unique,
    x.indisprimary AS supports_primary_key,
    x.indisvalid AS is_valid,
    x.indisready AS is_ready_for_insert,
    pg_catalog.pg_get_indexdef(i.oid) AS index_ddl
FROM pg_catalog.pg_index AS x
JOIN pg_catalog.pg_class AS t
    ON t.oid = x.indrelid
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = t.relnamespace
JOIN pg_catalog.pg_class AS i
    ON i.oid = x.indexrelid
WHERE n.nspname = 'meta_lab'
  AND t.relname = 'orders'
ORDER BY i.relname;
~~~

Các trường quan trọng:

- `indisunique`: index có cơ chế đảm bảo tính duy nhất theo định nghĩa của index.
- `indisprimary`: index đang phục vụ primary key.
- `indisvalid`: planner có thể xem index là hợp lệ để dùng theo điều kiện tương ứng.
- `indisready`: index đã sẵn sàng nhận cập nhật từ hoạt động ghi hay chưa.

Trong vận hành, `CREATE INDEX CONCURRENTLY` có thể thất bại và để lại **index chưa hợp lệ**. Chỉ nhìn tên index xuất hiện trong `pg_indexes` không đủ kết luận index đang được planner sử dụng bình thường. `pg_index.indisvalid` là tín hiệu quan trọng; khi gặp index invalid, cần xác định nguyên nhân và kế hoạch xử lý, không tự xóa trên production khi chưa đánh giá.

### 12.2. Expression index, partial index và INCLUDE

Giả sử có các index:

~~~sql
-- Ví dụ DDL, chỉ chạy trên bảng lab nếu muốn thực hành.
CREATE INDEX idx_customers_lower_email
    ON meta_lab.customers (lower(email));

CREATE INDEX idx_products_active
    ON meta_lab.products (list_price)
    WHERE is_active = TRUE;
~~~

Một index trên `lower(email)` là **expression index**; index theo `list_price` nhưng chỉ chứa dòng `is_active = TRUE` là **partial index**. Danh sách cột thuần túy không biểu diễn hết ngữ nghĩa. Dùng:

~~~sql
SELECT
    i.relname AS index_name,
    pg_catalog.pg_get_indexdef(i.oid) AS definition
FROM pg_catalog.pg_index AS x
JOIN pg_catalog.pg_class AS i
    ON i.oid = x.indexrelid
JOIN pg_catalog.pg_class AS t
    ON t.oid = x.indrelid
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = t.relnamespace
WHERE n.nspname = 'meta_lab'
  AND t.relname IN ('customers', 'products')
ORDER BY index_name;
~~~

Khi viết công cụ kiểm kê index, có thể cần xét cả `pg_index.indpred` (predicate của partial index), `indexprs` (biểu thức), `indkey` và danh sách cột `INCLUDE`. Để **hiển thị** định nghĩa dễ đọc, `pg_get_indexdef` thường thích hợp hơn việc tự ghép tất cả metadata.

Không nên thêm các index trên chỉ vì muốn thấy chúng trong catalog. Trong hệ thống thật, cần phân tích truy vấn, độ chọn lọc, chi phí ghi và kế hoạch thực thi.

## 13. Tra cứu view và materialized view

### 13.1. View qua information_schema

~~~sql
SELECT
    table_schema,
    table_name,
    view_definition,
    check_option,
    is_updatable
FROM information_schema.views
WHERE table_schema = 'meta_lab'
ORDER BY table_name;
~~~

`v_order_summary` được định nghĩa bằng `CREATE VIEW`. Cột `view_definition` có thể bị giới hạn theo quyền sở hữu/đặc quyền phù hợp; không nên suy ra view “rỗng” chỉ vì một role không nhìn thấy definition.

### 13.2. View qua pg_views và pg_get_viewdef

~~~sql
SELECT
    schemaname,
    viewname,
    viewowner,
    definition
FROM pg_catalog.pg_views
WHERE schemaname = 'meta_lab';

SELECT pg_catalog.pg_get_viewdef(
    'meta_lab.v_order_summary'::regclass,
    TRUE
) AS reconstructed_select;
~~~

`pg_get_viewdef` tái dựng câu `SELECT` phía sau view ở dạng chuẩn hóa theo PostgreSQL. Văn bản có thể khác format, alias hoặc dấu ngoặc so với lệnh `CREATE VIEW` ban đầu dù ngữ nghĩa tương đương. Đừng dùng so sánh chuỗi nguyên văn làm cách duy nhất để xác nhận migration chưa thay đổi.

### 13.3. Materialized view cần truy vấn riêng

**Materialized view** lưu kết quả vật lý tại thời điểm tạo/refresh theo cơ chế của PostgreSQL, khác với view thường. Để tìm:

~~~sql
SELECT
    schemaname,
    matviewname,
    matviewowner,
    ispopulated,
    definition
FROM pg_catalog.pg_matviews
WHERE schemaname = 'meta_lab'
ORDER BY matviewname;
~~~

Với bộ DDL hiện tại, kết quả là **0 dòng** vì chưa tạo materialized view.

Trong `pg_class`, materialized view có `relkind = 'm'`. Không kỳ vọng chúng xuất hiện giống ordinary view trong mọi truy vấn `information_schema.views`. Khi công cụ cần liệt kê đầy đủ mọi nguồn dữ liệu, phải xét thêm `pg_matviews` và các loại relation khác.

## 14. Tra cứu sequence và cột IDENTITY

`IDENTITY` dùng sequence để cấp giá trị theo cơ chế được PostgreSQL quản lý. Với bảng `meta_lab.customers`:

~~~sql
SELECT
    column_name,
    is_identity,
    identity_generation,
    identity_start,
    identity_increment
FROM information_schema.columns
WHERE table_schema = 'meta_lab'
  AND table_name = 'customers'
  AND column_name = 'customer_id';
~~~

Để tìm sequence được liên kết với cột identity hoặc serial:

~~~sql
SELECT pg_catalog.pg_get_serial_sequence(
    'meta_lab.customers',
    'customer_id'
) AS sequence_name;
~~~

Tên sequence thật có thể do PostgreSQL sinh ra theo quy tắc đặt tên và tránh trùng, nên không nên suy diễn chắc chắn tên sẽ là `customers_customer_id_seq` nếu DDL/restore đã thay đổi object.

Xem các sequence trong schema:

~~~sql
SELECT
    schemaname,
    sequencename,
    sequenceowner,
    data_type,
    start_value,
    min_value,
    max_value,
    increment_by,
    cycle
FROM pg_catalog.pg_sequences
WHERE schemaname = 'meta_lab'
ORDER BY sequencename;
~~~

### 14.1. Sequence không đồng nghĩa COUNT(*) của bảng

Giá trị sequence có thể tăng dù transaction chèn dữ liệu sau đó **ROLLBACK**. Khi xóa dòng hoặc gặp lỗi unique, ID cũng có thể xuất hiện khoảng trống. Vì vậy:

~~~text
Giá trị ID lớn nhất:  10
Số dòng hiện có:       7
~~~

không chứng minh đã “mất ba dòng dữ liệu” hoặc sequence bị lỗi. Đừng dùng `max(id) + 1` để tự cấp ID trong ứng dụng đa kết nối; sử dụng identity/sequence được PostgreSQL quản lý.

### 14.2. Không tự sửa sequence khi chỉ đang xem metadata

`setval(...)`, `ALTER SEQUENCE` và `RESTART` là thao tác **có thể ảnh hưởng ID cấp sau này**. Chúng không phải truy vấn metadata thuần đọc. Đặc biệt trên production, thay đổi sequence thiếu hiểu biết có thể gây trùng khóa chính khi câu `INSERT` tiếp theo chạy.

Để điều tra, ưu tiên `information_schema.columns`, `pg_get_serial_sequence` và `pg_sequences` trước. Cần nhớ một số trường về trạng thái hiện thời của sequence có thể bị giới hạn theo quyền và không thể diễn giải là ID kế tiếp tuyệt đối trong môi trường đồng thời.

## 15. Tra cứu comment mô tả đối tượng

Ở phần tạo schema, ta đã chạy `COMMENT ON TABLE` và `COMMENT ON COLUMN`. PostgreSQL cung cấp các hàm đọc description để đưa vào tài liệu schema:

~~~sql
SELECT
    obj_description(
        'meta_lab.orders'::regclass,
        'pg_class'
    ) AS table_comment;
~~~

Đọc comment của từng cột:

~~~sql
SELECT
    a.attnum,
    a.attname AS column_name,
    pg_catalog.col_description(c.oid, a.attnum)
        AS column_comment
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
JOIN pg_catalog.pg_attribute AS a
    ON a.attrelid = c.oid
WHERE n.nspname = 'meta_lab'
  AND c.relname = 'orders'
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
~~~

Nếu một đối tượng/cột chưa có comment, hàm có thể trả `NULL`. **Không có comment không có nghĩa cấu trúc sai**; nhưng với hệ thống lớn, comment giúp người dùng và công cụ hiểu ý nghĩa nghiệp vụ mà tên cột không thể diễn đạt đủ.

`COMMENT` không phải hợp đồng thay thế ràng buộc hoặc quyền. Một câu comment ghi “email unique” không ngăn trùng dữ liệu nếu DDL không có unique constraint thực sự.

## 16. Tra cứu kích thước và thống kê bảng bằng pg_catalog

Một bảng có thể có cùng số cột nhưng khác nhau rất lớn về kích thước và workload. PostgreSQL cung cấp những hàm kích thước có thể dùng với `regclass`:

~~~sql
SELECT
    pg_size_pretty(
        pg_relation_size('meta_lab.orders'::regclass)
    ) AS main_relation_size,
    pg_size_pretty(
        pg_table_size('meta_lab.orders'::regclass)
    ) AS table_storage_size,
    pg_size_pretty(
        pg_indexes_size('meta_lab.orders'::regclass)
    ) AS indexes_size,
    pg_size_pretty(
        pg_total_relation_size('meta_lab.orders'::regclass)
    ) AS total_relation_size;
~~~

Diễn giải ở mức thực hành:

| Hàm | Ý nghĩa chính |
| --- | --- |
| `pg_relation_size` | Kích thước của relation fork được chọn, mặc định main fork |
| `pg_table_size` | Kích thước lưu trữ liên quan đến bảng, bao gồm những thành phần bảng/TOAST thích hợp nhưng **không gồm index của bảng** |
| `pg_indexes_size` | Tổng kích thước index liên quan tới bảng |
| `pg_total_relation_size` | Tổng kích thước bảng cùng index và các thành phần phụ thuộc thích hợp |
| `pg_size_pretty` | Chuyển số byte sang chuỗi đơn vị dễ đọc |

Kết quả thay đổi theo lượng dữ liệu, index, trạng thái VACUUM và chi tiết storage. Đây là **đo kích thước lưu trữ**, không phải số hàng trong bảng.

### 16.1. Liệt kê kích thước các bảng thường trong schema

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    pg_size_pretty(
        pg_total_relation_size(c.oid)
    ) AS total_size,
    pg_total_relation_size(c.oid) AS total_bytes
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'meta_lab'
  AND c.relkind = 'r'
ORDER BY total_bytes DESC, table_name;
~~~

Đối với hệ thống phân vùng, cần suy nghĩ thêm về bảng cha `relkind='p'` và các partition con. Hàm kích thước trên partitioned parent không được hiểu tự động là tổng toàn bộ mọi partition; có thể cần duyệt cây partition và tổng hợp đúng các thành viên.

### 16.2. reltuples và relpages là thống kê ước tính

~~~sql
SELECT
    c.relname AS table_name,
    c.reltuples AS estimated_rows,
    c.relpages AS estimated_pages
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'meta_lab'
  AND c.relkind IN ('r', 'p')
ORDER BY c.relname;
~~~

`reltuples` là **ước tính số hàng** mà planner sử dụng hoặc tham khảo trong các phép tính liên quan, thường được cập nhật bởi VACUUM/ANALYZE và cơ chế thống kê. Nó có thể khác đáng kể với:

~~~sql
SELECT COUNT(*) FROM meta_lab.orders;
~~~

`COUNT(*)` chạy trên bảng để đếm theo snapshot của truy vấn, còn `reltuples` là metadata ước tính. Đừng dùng `reltuples` cho nghiệp vụ cần con số chính xác như số giao dịch đã thanh toán.

### 16.3. pg_stat_user_tables bổ sung thông tin vận hành

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_catalog.pg_stat_user_tables
WHERE schemaname = 'meta_lab'
ORDER BY relname;
~~~

`pg_stat_user_tables` là **view thống kê vận hành**, không phải catalog cấu trúc thuần túy. Các giá trị `n_live_tup` và `n_dead_tup` cũng mang tính ước tính. Việc một bảng mới tạo có `last_analyze` bằng `NULL` chưa chứng minh có sự cố; có thể nó chưa từng được analyze theo cơ chế tương ứng.

## 17. Bảng phân vùng và inheritance trong pg_catalog

Với những schema lớn, PostgreSQL có thể dùng **partitioning**. Một bảng partitioned parent thường có `pg_class.relkind = 'p'`, còn các partition con có thể là ordinary table với metadata kế thừa.

Tra quan hệ cha–con:

~~~sql
SELECT
    parent_ns.nspname AS parent_schema,
    parent.relname AS parent_table,
    child_ns.nspname AS child_schema,
    child.relname AS child_table,
    pg_get_expr(
        child.relpartbound,
        child.oid
    ) AS partition_bound
FROM pg_catalog.pg_inherits AS inh
JOIN pg_catalog.pg_class AS parent
    ON parent.oid = inh.inhparent
JOIN pg_catalog.pg_namespace AS parent_ns
    ON parent_ns.oid = parent.relnamespace
JOIN pg_catalog.pg_class AS child
    ON child.oid = inh.inhrelid
JOIN pg_catalog.pg_namespace AS child_ns
    ON child_ns.oid = child.relnamespace
WHERE parent_ns.nspname = 'meta_lab'
  AND parent.relkind = 'p'
ORDER BY parent.relname, child.relname;
~~~

Bộ DDL thực hành chưa tạo partition, nên truy vấn trên thường trả **0 dòng**. `pg_inherits` còn được dùng cho **table inheritance** truyền thống; vì vậy không được kết luận mọi dòng trong `pg_inherits` đều là declarative partitioning nếu chưa xem loại của bảng cha và metadata khác.

Để xem partition key:

~~~sql
SELECT
    c.relname AS partitioned_table,
    pg_catalog.pg_get_partkeydef(c.oid) AS partition_key
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'meta_lab'
  AND c.relkind = 'p'
ORDER BY c.relname;
~~~

Khi viết công cụ kiểm kê dung lượng, số hàng hoặc index cho partitioned tables, phải xác định có tính **các partition con** hay không. Đếm mỗi relation trong `pg_class` rồi cộng tùy ý rất dễ bị đếm trùng hoặc bỏ sót.

## 18. Tra cứu function, trigger và những đối tượng khác

Một schema PostgreSQL không chỉ có table/index/view. Nó còn có thể có function, procedure, trigger, enum, domain và extension.

### 18.1. Functions và procedures

Một truy vấn cơ bản dùng `pg_proc`:

~~~sql
SELECT
    n.nspname AS schema_name,
    p.proname AS routine_name,
    p.prokind AS routine_kind,
    pg_catalog.pg_get_function_identity_arguments(p.oid)
        AS identity_arguments,
    pg_catalog.pg_get_function_result(p.oid)
        AS return_type
FROM pg_catalog.pg_proc AS p
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE n.nspname = 'meta_lab'
ORDER BY p.proname, identity_arguments;
~~~

`pg_proc` mô tả cả function và những dạng routine khác; `prokind` giúp phân biệt. **Tên routine không phải lúc nào cũng duy nhất** vì PostgreSQL hỗ trợ overloaded functions, tức cùng tên nhưng khác kiểu/tham số. Khi cần chỉ định một function cụ thể, sử dụng signature hoặc OID thay vì dựa vào `proname` đơn lẻ.

Muốn xem định nghĩa (khi role có quyền phù hợp):

~~~sql
-- Chỉ hoạt động khi function với signature này có thật.
-- Ví dụ hình thức:
-- SELECT pg_get_functiondef('meta_lab.some_fn(integer)'::regprocedure);
~~~

### 18.2. Triggers

~~~sql
SELECT
    c.relname AS table_name,
    t.tgname AS trigger_name,
    t.tgenabled AS enabled_state,
    pg_catalog.pg_get_triggerdef(t.oid, TRUE)
        AS definition
FROM pg_catalog.pg_trigger AS t
JOIN pg_catalog.pg_class AS c
    ON c.oid = t.tgrelid
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'meta_lab'
  AND NOT t.tgisinternal
ORDER BY c.relname, t.tgname;
~~~

Trong ví dụ hiện tại, chưa có trigger do người dùng tạo, nên có thể trả **0 dòng**. Điều kiện `NOT t.tgisinternal` tránh đưa nhiều trigger nội bộ, bao gồm những trigger phục vụ thực thi khóa ngoại, vào danh sách trigger ứng dụng.

**Đừng kết luận “không có trigger” từ kết quả này nếu đang muốn kiểm kê mọi trigger nội bộ của hệ thống.** Nó chỉ liệt kê trigger không được đánh dấu internal trong schema lọc.

### 18.3. Kiểu do người dùng tạo

~~~sql
SELECT
    n.nspname AS schema_name,
    t.typname AS type_name,
    t.typtype AS type_kind,
    t.typcategory
FROM pg_catalog.pg_type AS t
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = t.typnamespace
WHERE n.nspname = 'meta_lab'
ORDER BY t.typname;
~~~

`pg_type` chứa nhiều loại type, trong đó có **composite types tự động liên quan đến bảng**. Vì vậy kết quả nhiều hơn số lệnh `CREATE TYPE` không nhất thiết là lỗi. Nếu muốn liệt kê riêng enum hoặc domain, cần lọc `typtype` thích hợp; đây là chi tiết PostgreSQL-specific.

## 19. Quyền truy cập và khả năng nhìn thấy metadata

Một nguyên tắc quan trọng: **metadata visibility khác data access**.

- `information_schema` thường chỉ hiển thị object/cột mà role có những quyền phù hợp.
- `pg_catalog` có thể cho phép đọc nhiều metadata hơn, nhưng điều đó không trao quyền `SELECT` trên bảng nghiệp vụ.
- Một số thông tin nhạy cảm (định nghĩa object, chi tiết quyền hoặc thông tin xác thực) được giới hạn qua quyền/schema/view riêng.
- Row-level security (RLS) ảnh hưởng việc đọc **dữ liệu hàng**, không nên được diễn giải là cơ chế tự động ẩn toàn bộ tên bảng/cột trong catalog.

### 19.1. Kiểm tra role hiện tại và quyền trên bảng

~~~sql
SELECT
    current_user AS role_name,
    has_schema_privilege(
        current_user,
        'meta_lab',
        'USAGE'
    ) AS can_use_schema,
    has_table_privilege(
        current_user,
        'meta_lab.orders',
        'SELECT'
    ) AS can_select_orders,
    has_table_privilege(
        current_user,
        'meta_lab.orders',
        'INSERT'
    ) AS can_insert_orders;
~~~

Các hàm `has_schema_privilege` và `has_table_privilege` xét quyền của role theo những quy tắc PostgreSQL hỗ trợ, bao gồm những quyền được thừa hưởng khi phù hợp. Với một object không tồn tại, một số dạng lời gọi có thể trả lỗi; hãy xác nhận đối tượng bằng `to_regclass` hoặc lấy OID trước nếu cần công cụ introspection chịu được object thiếu.

### 19.2. Xem grants bằng information_schema

~~~sql
SELECT
    table_schema,
    table_name,
    grantor,
    grantee,
    privilege_type,
    is_grantable
FROM information_schema.role_table_grants
WHERE table_schema = 'meta_lab'
ORDER BY table_name, grantee, privilege_type;
~~~

Kết quả phụ thuộc role đang truy vấn và cách các đặc quyền được cấp. `role_table_grants` không phải câu trả lời duy nhất cho mọi quyền hiệu lực, vì có vấn đề role membership, ownership, quyền được thừa hưởng và quyền cấp cho `PUBLIC`. Khi cần hỏi “role này có thực sự được SELECT không?”, `has_table_privilege` thường phù hợp hơn việc suy ra chỉ từ một dòng GRANT.

### 19.3. Không tra password bằng system catalog

`pg_roles` cung cấp metadata role phù hợp để quan sát, nhưng **không nhằm tiết lộ password hash**. Catalog nhạy cảm như `pg_authid` có giới hạn truy cập. Không cố lấy credential hoặc secret bằng việc “chỉ truy vấn metadata”; công tác quản trị phải tuân thủ chính sách quyền và bảo mật.

## 20. Dùng các meta-command của psql khi cần tra nhanh

`psql` cung cấp những lệnh bắt đầu bằng dấu `\`:

~~~text
\dn
\dt meta_lab.*
\dv meta_lab.*
\di meta_lab.*
\ds meta_lab.*
\d meta_lab.orders
\d+ meta_lab.orders
\d+ meta_lab.v_order_summary
~~~

Chúng giúp:

- `\dn`: liệt kê schema.
- `\dt`: bảng.
- `\dv`: view.
- `\di`: index.
- `\ds`: sequence.
- `\d`: mô tả cấu trúc object, cột và các ràng buộc.
- `\d+`: bổ sung một số thông tin như storage/comment/size tùy loại object và phiên bản.

Đây là **client-side meta-command của psql**, không phải cú pháp SQL gửi qua JDBC. Nếu chạy:

~~~sql
-- Không phải SQL hợp lệ khi gửi qua PreparedStatement:
-- \d meta_lab.orders
~~~

thì ứng dụng không nhận được kết quả như psql. Với một dịch vụ Java sinh metadata tự động, nên dùng truy vấn `information_schema` hoặc `pg_catalog`.

### 20.1. Tìm SQL mà psql dùng để tra metadata

`psql` có tùy chọn echo các truy vấn nội bộ, hữu ích để học cách catalog được kết hợp. Ví dụ trong môi trường lab:

~~~text
psql -E -d your_database
\d meta_lab.orders
~~~

Với cách này, bạn có thể quan sát những SQL do psql thực thi để tạo phần hiển thị. Tuy nhiên đây là chi tiết triển khai của **phiên bản psql**, không phải API ổn định mà ứng dụng nên copy nguyên văn và phụ thuộc lâu dài.

## 21. Viết một báo cáo kiểm kê schema có thể chạy lại

Đối với người mới tiếp quản một hệ thống, có thể lập báo cáo metadata bằng nhiều truy vấn chỉ đọc, tránh tự tạo SQL động ngay lúc đầu.

### 21.1. Danh sách relation và owner

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    CASE c.relkind
        WHEN 'r' THEN 'table'
        WHEN 'p' THEN 'partitioned table'
        WHEN 'v' THEN 'view'
        WHEN 'm' THEN 'materialized view'
        WHEN 'f' THEN 'foreign table'
        WHEN 'S' THEN 'sequence'
        WHEN 'i' THEN 'index'
        WHEN 'I' THEN 'partitioned index'
        ELSE 'other'
    END AS object_type,
    pg_get_userbyid(c.relowner) AS owner_name
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'meta_lab'
  AND c.relkind IN ('r','p','v','m','f','S','i','I')
ORDER BY object_type, object_name;
~~~

### 21.2. Số cột ứng dụng trên mỗi bảng

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    COUNT(a.attnum) AS user_column_count
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
LEFT JOIN pg_catalog.pg_attribute AS a
    ON a.attrelid = c.oid
   AND a.attnum > 0
   AND NOT a.attisdropped
WHERE n.nspname = 'meta_lab'
  AND c.relkind IN ('r', 'p')
GROUP BY n.nspname, c.relname
ORDER BY c.relname;
~~~

Điều kiện lọc cột nằm **trong JOIN** giúp vẫn giữ những bảng được chọn mà không có cột theo phạm vi truy vấn; trong thực tế ordinary tables sẽ có các cột ứng dụng khi đã được định nghĩa.

### 21.3. FK relationships để vẽ ERD

~~~sql
SELECT
    child.relname AS from_table,
    con.conname AS fk_name,
    parent.relname AS to_table,
    pg_get_constraintdef(con.oid, TRUE) AS fk_definition
FROM pg_catalog.pg_constraint AS con
JOIN pg_catalog.pg_class AS child
    ON child.oid = con.conrelid
JOIN pg_catalog.pg_class AS parent
    ON parent.oid = con.confrelid
JOIN pg_catalog.pg_namespace AS ns
    ON ns.oid = child.relnamespace
WHERE ns.nspname = 'meta_lab'
  AND con.contype = 'f'
ORDER BY from_table, fk_name;
~~~

Khi cần vẽ ERD có **tên cột chính xác ở cả hai đầu**, dùng phiên bản ghép `conkey` và `confkey` theo vị trí ở mục 11.2 thay vì chỉ lấy định nghĩa dạng chuỗi.

### 21.4. Index không hợp lệ trong schema

~~~sql
SELECT
    t.relname AS table_name,
    i.relname AS index_name,
    x.indisvalid,
    x.indisready
FROM pg_catalog.pg_index AS x
JOIN pg_catalog.pg_class AS i
    ON i.oid = x.indexrelid
JOIN pg_catalog.pg_class AS t
    ON t.oid = x.indrelid
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = t.relnamespace
WHERE n.nspname = 'meta_lab'
  AND NOT x.indisvalid
ORDER BY t.relname, i.relname;
~~~

Với schema lab được tạo bình thường, truy vấn thường trả **0 dòng**. Trên một hệ thống thực, một index invalid có thể do tạo index concurrently thất bại hoặc tác vụ khác chưa hoàn tất; kiểm tra trạng thái và tiến trình vận hành trước khi can thiệp.

## 22. Những giới hạn và lưu ý khi sử dụng metadata

### 22.1. Thông tin metadata không phải snapshot toàn hệ thống bất biến

PostgreSQL hỗ trợ DDL đồng thời. Nếu một công cụ chạy nhiều truy vấn metadata nối tiếp trong các transaction khác nhau, giữa hai truy vấn có thể có migration đổi tên bảng, thêm cột hoặc xóa index.

Đối với tác vụ xuất schema cần tính nhất quán cao, nên chọn **một quy trình snapshot/backup/migration có kiểm soát**. Không kỳ vọng một chuỗi truy vấn rời rạc trong môi trường đang thay đổi DDL sẽ luôn tái tạo được cùng một định nghĩa tại một thời điểm.

### 22.2. Không so sánh OID giữa hai môi trường

OID của một bảng ở database dev có thể khác OID của bảng tương ứng ở staging hoặc production. Muốn đối chiếu schema giữa môi trường, dùng **tên schema, tên object, loại, định nghĩa và migration version**; OID chỉ nên làm khóa JOIN metadata trong context của từng database.

### 22.3. Xác định chính xác tên có chữ hoa hoặc ký tự đặc biệt

PostgreSQL chuyển identifier không được quote về chữ thường:

~~~sql
CREATE TABLE meta_lab.sample_table (id INTEGER);
-- Tên thực tế: sample_table.
~~~

Nhưng:

~~~sql
CREATE TABLE meta_lab."SampleTable" (id INTEGER);
-- Tên thực tế phải được tham chiếu bằng "SampleTable".
~~~

Vì vậy các filter `WHERE table_name = 'sampletable'` sẽ không tìm được `"SampleTable"`. Với ứng dụng sinh DDL, nên chuẩn hóa cách đặt tên hoặc dùng `quote_ident` / `format('%I.%I', schema_name, table_name)` khi cần tạo identifier.

**Không chạy hai lệnh CREATE trên nếu chỉ muốn tra cứu metadata**; chúng minh họa cách PostgreSQL xử lý identifier.

### 22.4. Quyền xem metadata không đồng nghĩa quyền sửa schema

Một role có thể đọc tên bảng từ `pg_catalog.pg_class` nhưng không có `SELECT` trên nội dung bảng và không có quyền `ALTER TABLE`. Đừng coi một công cụ introspection có thể liệt kê object là công cụ đã được cấp quyền quản trị. Đối với role ứng dụng, vẫn cần tách quyền read/write/migration và bảo vệ thông tin nhạy cảm.

### 22.5. Catalog có thể thay đổi theo phiên bản

Các cột về generated columns, partitioning, index options và thông tin quyền có thể có điểm khác nhau giữa major PostgreSQL versions. Đặc biệt, không nên viết câu `SELECT *` rồi serialize toàn bộ row metadata thành một format hợp đồng bất biến.

Với công cụ dùng lâu dài:

1. Xác định những PostgreSQL major versions được hỗ trợ.
2. Chỉ chọn các trường metadata thật sự cần.
3. Kiểm thử trên các kiểu đối tượng đặc biệt như identity, domain, array, materialized view, partition và expression index.
4. Không tự sửa system catalog để “sửa lỗi metadata”.
5. Dùng migration/schema dump làm nguồn kiểm chứng cấu trúc khi phù hợp.

## 23. information_schema hay pg_catalog: chọn nhanh theo yêu cầu

| Câu hỏi | Nguồn ưu tiên | Vì sao? |
| --- | --- | --- |
| Schema nào đang tồn tại và có thể truy cập? | `information_schema.schemata` | View dễ dùng và gần chuẩn SQL |
| Bảng/view nào tôi được phép nhìn thấy? | `information_schema.tables` | Có cơ chế lọc theo quyền |
| Cột, kiểu SQL, default, nullable? | `information_schema.columns` | Đủ cho nhiều use case CRUD/schema browser |
| Khóa chính, unique, FK cơ bản? | `table_constraints`, `key_column_usage` | Đọc được qua view theo chuẩn |
| Cột FK nhiều thành phần nối tương ứng thế nào? | `pg_constraint`, `pg_attribute` | `conkey`/`confkey` và OID cho mapping chính xác |
| DDL của index, expression, partial, trạng thái valid? | `pg_indexes`, `pg_index` | Metadata PostgreSQL-specific |
| Phân biệt ordinary table, partition, matview, sequence? | `pg_class.relkind` | Đầy đủ loại relation hơn view chuẩn |
| Xem DDL của view? | `pg_views` / `pg_get_viewdef` | Tái dựng định nghĩa |
| Xem comment trên cột? | `col_description` | Liên kết comment theo OID + attnum |
| Tra sequence của identity? | `pg_get_serial_sequence` / `pg_sequences` | Hỗ trợ cơ chế identity/serial |
| Xem kích thước bảng/index? | `pg_total_relation_size`, `pg_indexes_size` | Hàm storage-specific |
| Xem số hàng chính xác? | `SELECT COUNT(*)` | Catalog chỉ cung cấp ước tính |
| Xem quyền hiệu lực của role? | `has_table_privilege` | Phù hợp hơn suy luận từ một bản ghi GRANT |
| Xem nhanh từ terminal? | `psql \d` / `\dt` / `\di` | Thực dụng khi khám phá bằng tay |

Một quy tắc thực hành tốt là **bắt đầu từ `information_schema` nếu yêu cầu là metadata SQL phổ biến**, rồi dùng `pg_catalog` khi cần đặc tính PostgreSQL chuyên sâu hoặc khi muốn dựng lại cấu trúc chính xác theo OID.

## 24. Bài tập thực hành

### Bài 1 — Liệt kê cột và xác định NOT NULL

Viết truy vấn từ `information_schema.columns` để trả tất cả cột của `meta_lab.products` cùng `ordinal_position`, `data_type`, `is_nullable` và `column_default`.

**Gợi ý:**

~~~sql
SELECT
    ordinal_position,
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'meta_lab'
  AND table_name = 'products'
ORDER BY ordinal_position;
~~~

Giải thích vì sao cột `is_active` có default `TRUE` nhưng vẫn cần khai báo `NOT NULL` nếu muốn cấm `NULL`.

### Bài 2 — Nhận diện composite primary key

Sử dụng `table_constraints` và `key_column_usage` tìm các cột của `order_items_pk`. Có thể dùng query mục 7.1 và thêm điều kiện `tc.constraint_name = 'order_items_pk'`.

**Kỳ vọng:** `order_id` là cột thứ nhất, `product_id` là cột thứ hai. Giải thích tại sao không đặt mỗi cột là unique riêng.

### Bài 3 — Vẽ sơ đồ quan hệ bằng catalog

Từ query ghép `pg_constraint` ở mục 11.2, vẽ các mũi tên:

~~~text
orders.customer_id       --> customers.customer_id
order_items.order_id     --> orders.order_id
order_items.product_id   --> products.product_id
~~~

Sau đó giải thích vì sao một tên constraint đơn lẻ không phải lúc nào cũng đủ làm khóa để join mọi metadata.

### Bài 4 — Tìm index khác với index của khóa chính

Chạy `pg_indexes` trên `meta_lab.orders`. Xác định index nào phục vụ khóa chính, unique và index nào do lệnh `CREATE INDEX idx_orders_customer_time` tạo. Sau đó xem `indisvalid` bằng `pg_index`.

**Gợi ý:** đừng đếm `CREATE INDEX` trong source SQL để suy ra tổng số index thật, vì `PRIMARY KEY` và `UNIQUE` thường có index hỗ trợ.

### Bài 5 — So view và materialized view

Tra `information_schema.views`, `pg_views` và `pg_matviews` trong schema. `v_order_summary` thuộc loại nào? Vì sao truy vấn `pg_matviews` trả 0 dòng với bộ DDL?

**Gợi ý:** view thường được khai báo bằng truy vấn; materialized view là đối tượng lưu kết quả vật lý có thể được refresh.

### Bài 6 — So metadata số hàng với COUNT(*)

Chạy:

~~~sql
SELECT relname, reltuples
FROM pg_catalog.pg_class
WHERE oid = 'meta_lab.orders'::regclass;

SELECT COUNT(*) AS exact_visible_rows
FROM meta_lab.orders;
~~~

**Câu hỏi:** tại sao `reltuples` có thể khác 1, dù seed tạo một đơn hàng? Giải thích sự khác nhau giữa thống kê dùng cho planner và phép đếm theo snapshot.

### Bài 7 — Tra comment và sequence

Dùng `obj_description`, `col_description` và `pg_get_serial_sequence` để trả lời:

- Comment của bảng `orders` là gì?
- Comment của `orders.order_code` là gì?
- `customers.customer_id` có liên kết sequence nào?

**Gợi ý:** không tự đoán tên sequence dựa trên tên bảng.

### Bài 8 — Xác định giới hạn theo quyền

Đặt tình huống role báo cáo chỉ có `USAGE` schema và `SELECT` trên `meta_lab.v_order_summary`, không có `SELECT` trực tiếp trên bảng `orders`. Hãy giải thích:

1. Vì sao `information_schema.tables` có thể hiển thị khác khi chạy bằng owner và role báo cáo?
2. Vì sao thấy object trong `pg_catalog` không tự cấp quyền `SELECT`?
3. Có nên để role báo cáo dùng superuser chỉ để kiểm kê metadata không?

**Gợi ý:** metadata visibility, quyền truy cập bảng và quyền sửa schema là những khái niệm riêng.

### Bài 9 — Xử lý tên object có chữ hoa

Giả sử một nhóm tạo bảng với identifier được quote là `"CustomerOrders"`. Vì sao điều kiện `table_name = 'customerorders'` không tìm thấy nó? Viết cách dùng `to_regclass` với tên được quote chính xác và cách lọc `pg_class.relname` phù hợp.

### Bài 10 — Thiết kế công cụ xuất tài liệu schema

Thiết kế một báo cáo gồm các phần:

- Schema, tên object và loại relation.
- Tên cột, kiểu hiển thị, nullable, identity/default.
- Khóa chính, unique, check và foreign key.
- Index expression/partial cùng trạng thái valid.
- View definitions và comments.
- Metadata kích thước nếu có quyền.

Hãy chỉ ra phần nào nên ưu tiên `information_schema` và phần nào bắt buộc hoặc thích hợp hơn với `pg_catalog`. Khi triển khai, sử dụng OID để join **trong cùng database**, không dùng OID làm khóa định danh đối tượng bền vững giữa hai môi trường.

## 25. Gợi ý sử dụng metadata trong dự án thật

Khi viết công cụ làm việc với PostgreSQL, các nguồn metadata có thể phục vụ:

**Tạo tài liệu dữ liệu tự động:** lấy tên cột, type, FK, comment và view definition để dựng sơ đồ quan hệ hoặc data dictionary.

**Kiểm tra migration:** so sánh object dự kiến trong migration với cấu trúc thật. Cần tránh chỉ so tên cột mà bỏ qua nullable, index, constraint hoặc default.

**Schema browser/IDE:** hỗ trợ người dùng khám phá bảng, view và các quan hệ dù không có quyền xem toàn bộ dữ liệu.

**Kiểm kê vận hành:** tìm index invalid, phân vùng, kiểu tự định nghĩa, sequence, table owner hoặc dung lượng storage để phục vụ thay đổi có kiểm soát.

**Công cụ sinh câu SQL:** metadata giúp xác định cột và kiểu, nhưng vẫn phải dùng cách quote identifier an toàn, bind tham số dữ liệu và kiểm soát quyền thực thi. Việc một tên cột được tìm thấy trong catalog không khiến mọi SQL dựng từ input trở nên an toàn.

Trong hệ thống có nhiều role và schema, nên ghi rõ **database, schema, role đang truy vấn và phiên bản PostgreSQL** cùng báo cáo. Một kết quả metadata không có các thông tin ngữ cảnh đó rất dễ bị hiểu nhầm là đầy đủ cho toàn server.

## 26. Tài liệu tham khảo chính thức

Khi phát triển công cụ introspection lâu dài, hãy kiểm tra tài liệu đúng phiên bản:

- [PostgreSQL — Information Schema](https://www.postgresql.org/docs/current/information-schema.html): hệ thống view metadata theo chuẩn SQL.
- [PostgreSQL — System Catalogs](https://www.postgresql.org/docs/current/catalogs.html): `pg_class`, `pg_attribute`, `pg_constraint`, `pg_index` và các catalog khác.
- [PostgreSQL — System Information Functions](https://www.postgresql.org/docs/current/functions-info.html): các hàm tra OID, quyền, định nghĩa và metadata.
- [PostgreSQL — Database Object Size Functions](https://www.postgresql.org/docs/current/functions-admin.html): các hàm kích thước đối tượng.
- [PostgreSQL — psql](https://www.postgresql.org/docs/current/app-psql.html): các meta-command `\d`, `\dt`, `\di` và chế độ hiển thị truy vấn nội bộ.

Đường dẫn `/docs/current/` nói về phiên bản ổn định hiện hành. Nếu database đang chạy PostgreSQL 14, 15, 16 hoặc phiên bản cụ thể khác, nên đổi phần `current` thành **số major tương ứng** khi xem hành vi chi tiết.

## 27. Tổng kết

**`information_schema` là điểm khởi đầu thuận tiện** khi cần kiểm kê schema, bảng, cột, khóa và view theo mô hình metadata tương đối chuẩn hóa. Nó phù hợp nhiều nhu cầu tạo giao diện quản trị, tài liệu schema và kiểm tra cấu trúc cơ bản, nhưng kết quả có thể chịu ảnh hưởng của quyền người dùng và không bao phủ mọi khả năng riêng của PostgreSQL.

**`pg_catalog` cung cấp góc nhìn chi tiết hơn vào kiến trúc đối tượng PostgreSQL.** Bằng cách nối `pg_namespace`, `pg_class`, `pg_attribute`, `pg_constraint` và `pg_index` qua OID và `attnum`, ta có thể xác định chính xác loại relation, cột, foreign key nhiều thành phần, trạng thái index, partition, view, sequence, comment và thông tin lưu trữ. Các hàm `pg_get_*def` giúp dựng lại định nghĩa ở dạng dễ đọc.

Khi tra cứu metadata, luôn nhớ ba giới hạn: **không nhầm tên object với schema/search_path**, **không coi ước tính catalog là số liệu nghiệp vụ chính xác**, và **không nhầm quyền nhìn thấy metadata với quyền thao tác dữ liệu**. Biết chọn đúng nguồn và đọc đúng ngữ nghĩa giúp người học tự khám phá cơ sở dữ liệu lạ, hỗ trợ migration và quản trị PostgreSQL trên cơ sở bằng chứng thay vì phỏng đoán.
