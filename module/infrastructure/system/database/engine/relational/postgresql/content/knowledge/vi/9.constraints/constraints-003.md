# PRIMARY KEY, UNIQUE và chỉ mục hỗ trợ trong PostgreSQL

## 1. Mục tiêu bài học

Trong một hệ thống bán hàng, cơ sở dữ liệu cần bảo đảm rằng:

- Không có hai khách hàng dùng cùng một **mã khách hàng**.
- Một tenant không có hai sản phẩm cùng **SKU**, nhưng hai tenant khác nhau có thể cùng SKU.
- Hai tài khoản không đăng ký cùng một **email** nếu email là định danh toàn hệ thống.
- Một khách hàng chỉ có **tối đa một địa chỉ mặc định**.
- Các bản ghi đơn hàng tham chiếu **khách hàng có thật**.
- Nhiều request đồng thời không tạo ra những dòng trùng nhau do ứng dụng kiểm tra quá muộn.

Những yêu cầu này liên quan đến **ràng buộc duy nhất (uniqueness constraints)** và **chỉ mục (indexes)**. Trong PostgreSQL, hai cấu trúc rất quan trọng là:

- **`PRIMARY KEY`**: xác định một khóa chính duy nhất của bảng, có các giá trị khóa **không NULL** và **không trùng nhau**.
- **`UNIQUE`**: ràng buộc tính duy nhất của một cột hoặc một tổ hợp cột; có quy tắc riêng cho **`NULL`**.

Khi tạo các ràng buộc này, PostgreSQL thông thường tự tạo **B-tree unique index** để thực thi việc kiểm tra. Tuy nhiên, **ràng buộc** là điều kiện đúng đắn của dữ liệu; **chỉ mục** là cấu trúc truy cập và thực thi. Chúng liên quan mật thiết nhưng không phải hai khái niệm thay thế hoàn toàn cho nhau.

Sau bài học, người học có thể:

1. Thiết kế `PRIMARY KEY`, `UNIQUE` đơn cột và khóa ghép phù hợp nghiệp vụ.
2. Giải thích `NULL` trong unique constraint và `NULLS NOT DISTINCT` từ PostgreSQL 15.
3. Phân biệt **unique constraint**, **unique index**, **partial unique index** và **expression unique index**.
4. Hiểu vai trò của index hỗ trợ, thứ tự cột và `INCLUDE` đối với hiệu năng truy vấn.
5. Xác định yêu cầu của khóa được `FOREIGN KEY` tham chiếu và chỉ mục phía bảng tham chiếu.
6. Xử lý xung đột dữ liệu bằng `INSERT ... ON CONFLICT` mà không gặp race condition kiểm tra-trước-ghi.
7. Phân biệt ràng buộc `DEFERRABLE`, thời điểm kiểm tra và tác động đến upsert.
8. Kiểm tra index/constraint trong catalog và chuẩn bị migration an toàn cho bảng lớn.
9. Thực hành bằng PostgreSQL với dữ liệu mẫu và bài tập có lời giải.

> **An toàn:** Các lệnh tạo bảng, chèn dữ liệu hoặc thay đổi index chỉ dành cho **database thực hành** được phép. Với production, phải lập kế hoạch migration, sao lưu, kiểm tra dữ liệu trùng, khóa và ảnh hưởng tải trước khi thay đổi.

---

## 2. Hai khái niệm: ràng buộc logic và cấu trúc vật lý

Hãy xét bảng `customers`:

```sql
CREATE TABLE customers (
    customer_id BIGINT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL
);
```

Có hai lời cam kết về dữ liệu:

1. `customer_id` xác định duy nhất một khách hàng và không có giá trị `NULL`.
2. `email` không trùng giữa các khách và cũng không có `NULL`.

PostgreSQL cần cách kiểm tra những cam kết này hiệu quả khi có rất nhiều hàng. Khi khai báo `PRIMARY KEY` hoặc `UNIQUE`, PostgreSQL tạo chỉ mục B-tree duy nhất tương ứng trong trường hợp bảng thông thường.

Mối quan hệ có thể hình dung:

~~~text
Quy tắc nghiệp vụ
  "Mã khách hàng không trùng"
            |
            v
PRIMARY KEY (customer_id)       -- Ràng buộc của bảng
            |
            v
Unique B-tree index             -- Cấu trúc hỗ trợ thực thi
            |
            v
Kiểm tra khi INSERT / UPDATE,
đồng thời giúp một số SELECT tìm nhanh
~~~

Chỉ mục không chỉ để làm `SELECT` nhanh hơn: **unique index còn có trách nhiệm ngăn dữ liệu không hợp lệ khi ghi**.

Tuy nhiên:

- Một **unique constraint** được quản lý như ràng buộc của bảng và xuất hiện trong metadata constraint.
- Một **unique index** được tạo trực tiếp bằng `CREATE UNIQUE INDEX` có thể cung cấp một dạng đảm bảo uniqueness, kể cả trên **biểu thức** hoặc **tập dòng thỏa predicate**.
- Một index thông thường không có `UNIQUE` chỉ phục vụ truy cập, **không bảo vệ tính duy nhất**.
- PostgreSQL chỉ cho phép **một `PRIMARY KEY` trên một bảng**, nhưng có thể có nhiều `UNIQUE` constraints.

Không nên dùng kiểm tra ở ứng dụng thay cho ràng buộc DB:

```text
Request A: SELECT COUNT(*) WHERE email = 'x@example.com' -> 0
Request B: SELECT COUNT(*) WHERE email = 'x@example.com' -> 0
Request A: INSERT email x
Request B: INSERT email x
```

Nếu chỉ dựa trên `SELECT` rồi `INSERT`, hai request đồng thời đều có thể tin rằng email còn trống. Một unique constraint/index đúng sẽ bảo vệ quy tắc **ngay tại thời điểm ghi**, thay vì chỉ tin kết quả đọc trước đó.

## 3. PRIMARY KEY: định danh chính thức của một hàng

### 3.1. PRIMARY KEY bảo đảm điều gì?

```sql
CREATE TABLE products (
    product_id BIGINT PRIMARY KEY,
    product_name TEXT NOT NULL
);
```

Ràng buộc trên có nghĩa:

- Không được có hai hàng cùng `product_id`.
- Không được có hàng mà `product_id IS NULL`.
- Mỗi giá trị khóa xác định tối đa một hàng trong bảng.
- PostgreSQL có một unique index hỗ trợ kiểm tra và truy cập theo PK.

Hai câu sau đều không hợp lệ nếu dữ liệu tương ứng đã tồn tại hoặc khóa NULL:

```sql
-- Ví dụ sẽ lỗi nếu product_id = 1 đã tồn tại.
INSERT INTO products(product_id, product_name)
VALUES (1, 'Tên khác');

-- Ví dụ sẽ lỗi vì PRIMARY KEY không chấp nhận NULL.
INSERT INTO products(product_id, product_name)
VALUES (NULL, 'Không mã');
```

SQLSTATE thường gặp:

| Vi phạm | SQLSTATE | Ý nghĩa |
|---|---|---|
| Trùng primary key/unique key | `23505` | `unique_violation` |
| NULL tại cột bắt buộc | `23502` | `not_null_violation` |
| Tham chiếu khóa ngoại không tồn tại | `23503` | `foreign_key_violation` |
| Vi phạm CHECK | `23514` | `check_violation` |

Trong ứng dụng, mã SQLSTATE hữu ích hơn việc so sánh chuỗi thông báo lỗi có thể thay đổi theo phiên bản/ngôn ngữ.

### 3.2. Mỗi bảng tối đa một PRIMARY KEY

```sql
CREATE TABLE demo (
    id BIGINT PRIMARY KEY,
    code TEXT UNIQUE
);
```

Đây là một PK và một alternate key. Không thể tạo thêm PK thứ hai trên cùng bảng:

```sql
-- Không hợp lệ nếu bảng đã có PRIMARY KEY:
ALTER TABLE demo ADD PRIMARY KEY (code);
```

Nhưng một PK có thể **gồm nhiều cột**:

```sql
CREATE TABLE enrollment (
    student_id BIGINT NOT NULL,
    course_id BIGINT NOT NULL,
    grade NUMERIC(4,2),
    PRIMARY KEY (student_id, course_id)
);
```

Ở đây một cặp `(student_id, course_id)` xác định một đăng ký; không yêu cầu `student_id` hoặc `course_id` riêng lẻ là duy nhất.

### 3.3. Primary key không bắt buộc tự tăng

PostgreSQL không yêu cầu PK phải là `SERIAL`, `BIGSERIAL`, `IDENTITY`, UUID hay số nguyên liên tiếp. Các lựa chọn thường gặp:

| Loại khóa | Ví dụ | Ưu và lưu ý |
|---|---|---|
| Mã nghiệp vụ | `sku`, `student_code` | Dễ hiểu; cần bảo đảm bền vững, không tái sử dụng sai |
| Số nguyên do ứng dụng cấp | `BIGINT` | Đơn giản; phải điều phối cấp ID không trùng |
| Identity | `BIGINT GENERATED ... AS IDENTITY` | PostgreSQL cấp giá trị qua sequence |
| UUID | `UUID PRIMARY KEY` | Phù hợp hệ phân tán; xem xét cách sinh và tác động index |
| Khóa ghép | `(tenant_id, sku)` | Thể hiện uniqueness theo phạm vi nhiều cột |

Ví dụ với identity:

```sql
CREATE TABLE customers_identity (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name TEXT NOT NULL
);

INSERT INTO customers_identity(full_name)
VALUES ('Nguyễn An')
RETURNING customer_id;
```

`RETURNING` là cách lấy ID do database sinh. **Identity/sequence tự sinh giá trị không thay thế PRIMARY KEY/UNIQUE**: một sequence có thể có khoảng trống do rollback/cache, có thể được điều chỉnh, và định nghĩa tính duy nhất cuối cùng vẫn nằm ở constraint.

### 3.4. Khóa tự nhiên và khóa thay thế

Một email có vẻ là khóa tự nhiên, nhưng khách hàng có thể đổi email, email có thể cần chuẩn hóa và đôi khi một địa chỉ được tái sử dụng. Vì thế nhiều hệ thống dùng:

```sql
customer_id BIGINT PRIMARY KEY,
email TEXT NOT NULL UNIQUE
```

`customer_id` là **khóa thay thế (surrogate key)** bền vững cho quan hệ; `email` là **alternate business key** theo chính sách.

Thêm surrogate key không có nghĩa bỏ mọi uniqueness nghiệp vụ: nếu email phải độc nhất thì vẫn cần unique constraint phù hợp.

## 4. UNIQUE: ràng buộc tính duy nhất ngoài PRIMARY KEY

### 4.1. UNIQUE đơn cột

```sql
CREATE TABLE employees (
    employee_id BIGINT PRIMARY KEY,
    employee_code TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL
);
```

Mỗi `employee_code` phải duy nhất. Một bảng có thể có nhiều unique constraints khác nhau:

```sql
CREATE TABLE organizations (
    organization_id BIGINT PRIMARY KEY,
    organization_code TEXT NOT NULL UNIQUE,
    tax_number TEXT UNIQUE,
    organization_name TEXT NOT NULL
);
```

Ở đây mã tổ chức không được NULL; mã số thuế được phép thiếu, với ngữ nghĩa unique mặc định về NULL như sẽ giải thích.

### 4.2. UNIQUE ghép

```sql
CREATE TABLE catalog_products (
    tenant_id BIGINT NOT NULL,
    sku TEXT NOT NULL,
    title TEXT NOT NULL,
    CONSTRAINT uq_catalog_tenant_sku UNIQUE (tenant_id, sku)
);
```

Ràng buộc:

```text
UNIQUE (tenant_id, sku)
```

đảm bảo **mỗi tenant có tối đa một sản phẩm cho một SKU**.

Những hàng sau hợp lệ:

| tenant_id | sku |
|---:|---|
| 10 | `P-100` |
| 10 | `P-101` |
| 20 | `P-100` |

Nhưng thêm tiếp `(10, 'P-100')` sẽ vi phạm uniqueness.

Đặc biệt:

```text
UNIQUE (tenant_id, sku)
```

**không tương đương**:

```text
UNIQUE (tenant_id)
UNIQUE (sku)
```

Hai ràng buộc đơn cột riêng biệt sẽ cấm một tenant có nhiều SKU và cấm hai tenant dùng chung SKU — sai nghiệp vụ.

### 4.3. Chọn PRIMARY KEY hay UNIQUE cho khóa ghép?

Nếu bảng là quan hệ đăng ký môn học và không có ID khác:

```sql
PRIMARY KEY (student_id, course_id)
```

là lựa chọn hợp lý.

Nếu bảng có `enrollment_id` được API dùng như định danh chính:

```sql
enrollment_id BIGINT PRIMARY KEY,
UNIQUE (student_id, course_id)
```

cũng có thể đúng **nếu nghiệp vụ vẫn giới hạn một lần đăng ký cho mỗi cặp**. Hai ràng buộc đóng vai trò khác nhau, không thừa về **ngữ nghĩa** mặc dù đều tạo index và có chi phí.

### 4.4. Tên constraint giúp xử lý lỗi

```sql
CREATE TABLE accounts (
    account_id BIGINT PRIMARY KEY,
    account_code TEXT NOT NULL,
    CONSTRAINT uq_accounts_account_code UNIQUE (account_code)
);
```

Tên `uq_accounts_account_code` giúp nhận diện chính xác quy tắc bị vi phạm trong log, migration và xử lý `ON CONFLICT ON CONSTRAINT`.

Đặt tên rõ nghĩa cũng hỗ trợ quy trình đổi schema và tìm constraint trong `pg_constraint`.

## 5. NULL trong UNIQUE: điểm khác biệt rất quan trọng

### 5.1. UNIQUE mặc định coi NULL là phân biệt

Theo hành vi mặc định của PostgreSQL:

```sql
CREATE TABLE contact_methods (
    contact_id BIGINT PRIMARY KEY,
    external_reference TEXT UNIQUE
);
```

Các dòng sau **hợp lệ**:

```sql
INSERT INTO contact_methods(contact_id, external_reference)
VALUES
    (1, NULL),
    (2, NULL),
    (3, 'EXT-100');
```

Vì unique constraint mặc định không xem các giá trị `NULL` là bằng nhau theo mục đích kiểm tra tính duy nhất.

Nhưng:

```sql
-- Sẽ vi phạm vì 'EXT-100' đã xuất hiện.
INSERT INTO contact_methods(contact_id, external_reference)
VALUES (4, 'EXT-100');
```

Đừng nhầm `NULL` với chuỗi rỗng `''`: hai chuỗi rỗng giống nhau trên cột unique sẽ bị xem là trùng, còn nhiều NULL có thể cùng tồn tại theo quy tắc mặc định.

### 5.2. NULL trong UNIQUE ghép

```sql
CREATE TABLE app_events (
    event_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    external_ref TEXT,
    UNIQUE (tenant_id, external_ref)
);
```

Những dòng:

```text
(tenant_id=10, external_ref=NULL)
(tenant_id=10, external_ref=NULL)
```

được cho phép theo unique mặc định. Vì thế **một thành phần nullable** của khóa ghép có thể khiến nhiều hàng có cùng các thành phần khác mà vẫn không bị xem là trùng.

Nếu business key **phải xác định mọi hàng**, cần xét `NOT NULL` trên các cột của khóa hoặc quy tắc `NULLS NOT DISTINCT`.

### 5.3. UNIQUE NULLS NOT DISTINCT (PostgreSQL 15+)

Từ PostgreSQL 15, có thể viết:

```sql
CREATE TABLE external_links (
    link_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    external_ref TEXT,
    CONSTRAINT uq_external_links
        UNIQUE NULLS NOT DISTINCT (tenant_id, external_ref)
);
```

Ràng buộc này coi `NULL` là **không phân biệt** cho mục đích uniqueness. Vì vậy:

- `(10, 'ABC')` chỉ được một dòng.
- `(10, NULL)` cũng chỉ được **một** dòng.
- `(20, NULL)` vẫn có thể tồn tại vì `tenant_id` khác.

Không nên áp dụng `NULLS NOT DISTINCT` máy móc: nếu nghiệp vụ muốn **nhiều bản ghi chưa có mã ngoài**, unique mặc định lại đúng hơn.

Có thể dùng trực tiếp với index:

```sql
CREATE UNIQUE INDEX uq_external_links_tenant_ref
ON external_links (tenant_id, external_ref)
NULLS NOT DISTINCT;
```

Đây là ví dụ thay thế khi chưa có một constraint/index tương đương; **không cần tạo cả hai** trên cùng cột nếu không có lý do cụ thể.

### 5.4. Quyết định theo yêu cầu nghiệp vụ

| Quy tắc | Cách biểu diễn gợi ý |
|---|---|
| Mã khách hàng luôn tồn tại và duy nhất | `PRIMARY KEY` hoặc `NOT NULL UNIQUE` |
| Email có thể chưa có; email đã nhập không được trùng | `UNIQUE(email)` mặc định, email nullable |
| Mỗi nhóm chỉ có tối đa một bản ghi thiếu mã ngoài | `UNIQUE NULLS NOT DISTINCT(group_id, external_code)` |
| Chỉ những dòng đang hoạt động mới cần độc nhất | **Partial unique index** |
| Email không phân biệt hoa/thường | **Expression unique index** hoặc thiết kế kiểu/collation phù hợp |

`NULL` là vấn đề **ngữ nghĩa của dữ liệu**, không chỉ một tùy chọn SQL.

## 6. PRIMARY KEY ghép trong hệ thống đa tenant

Nhiều hệ thống có dữ liệu được phân vùng logic theo tenant.

Ví dụ:

```sql
CREATE TABLE tenant_products (
    tenant_id BIGINT NOT NULL,
    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,
    unit_price NUMERIC(12,2) NOT NULL,
    PRIMARY KEY (tenant_id, sku)
);
```

Tại sao không dùng `PRIMARY KEY (sku)`? Vì tenant A và tenant B đều có thể bán sản phẩm với SKU `P-100`, nhưng đó là **hai đối tượng độc lập**.

Khi thiết kế khóa ghép cần hỏi:

1. `tenant_id` có phải phạm vi của uniqueness không?
2. Thứ tự `(tenant_id, sku)` có phù hợp truy vấn theo tenant không?
3. Bảng tham chiếu có cần truyền đủ cả hai cột để giữ đúng tenant không?
4. Có tính năng tái sử dụng SKU cũ sau khi ngừng bán không?
5. Các cột khóa có ổn định hay bị đổi tên/mã thường xuyên không?

### 6.1. Khóa ghép và khóa ngoại ghép

```sql
CREATE TABLE product_notes (
    note_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    sku TEXT NOT NULL,
    note_text TEXT NOT NULL,
    CONSTRAINT fk_product_notes_product
        FOREIGN KEY (tenant_id, sku)
        REFERENCES tenant_products(tenant_id, sku)
);
```

FK ghép yêu cầu hai giá trị cùng tham chiếu một hàng khóa của `tenant_products`. Không thể tùy ý kết hợp một `tenant_id` và SKU từ hai sản phẩm khác nhau.

Nếu các cột FK nullable, quy tắc `MATCH SIMPLE` mặc định có cách xử lý NULL riêng; để mô hình này rõ ràng, chúng được khai báo `NOT NULL`.

### 6.2. B-tree index hỗ trợ khóa ghép

PostgreSQL tạo unique index cho:

```sql
PRIMARY KEY (tenant_id, sku)
```

Một B-tree có thứ tự khóa này thường hữu ích cho:

```sql
WHERE tenant_id = 10
```

và đặc biệt:

```sql
WHERE tenant_id = 10 AND sku = 'P-100'
```

Nhưng truy vấn chỉ lọc:

```sql
WHERE sku = 'P-100'
```

không có cùng đường truy cập tiền tố thuận lợi. PostgreSQL có những tối ưu tùy phiên bản/kế hoạch, nhưng **không nên coi index `(tenant_id, sku)` tự động tối ưu mọi truy vấn chỉ theo SKU**. Kiểm tra `EXPLAIN` và workload thật trước khi tạo thêm index.

## 7. Index mà PostgreSQL tạo để hỗ trợ constraint

### 7.1. PRIMARY KEY và UNIQUE mặc định tạo index

Trên heap table thông thường, khi tạo:

```sql
PRIMARY KEY (product_id)
```

hoặc:

```sql
UNIQUE (tenant_id, sku)
```

PostgreSQL tự tạo **unique B-tree index** phục vụ việc kiểm tra các ràng buộc đó.

Vì vậy không cần vô điều kiện tạo thêm:

```sql
CREATE INDEX idx_duplicate ON products (product_id);
```

nếu đã có `PRIMARY KEY(product_id)`. Một index mới trùng khóa chỉ làm tăng dung lượng và chi phí ghi mà chưa chắc cải thiện `SELECT`.

### 7.2. Constraint và index không hoàn toàn tương đương

| Tiêu chí | `PRIMARY KEY` | `UNIQUE` constraint | `CREATE UNIQUE INDEX` |
|---|---|---|---|
| Ngăn khóa trùng | Có | Có | Có |
| Ngăn NULL ở tất cả key columns | Có | Không mặc định; thêm `NOT NULL` nếu cần | Không mặc định; phụ thuộc cột và `NULLS NOT DISTINCT` |
| Một bảng được có nhiều? | Tối đa một PK | Có | Có |
| Metadata ràng buộc trong `pg_constraint` | Có | Có | Không tự thành constraint khi tạo trực tiếp |
| Tạo B-tree unique index hỗ trợ | Có | Có | Bản thân là index |
| Biểu thức như `lower(email)` | Không trong cột constraint trực tiếp | Không như biểu thức constraint trực tiếp | Có |
| Predicate như `WHERE is_active` | Không | Không | Có |
| `DEFERRABLE` theo constraint | Có thể | Có thể | `CREATE UNIQUE INDEX` trực tiếp không có khai báo này |
| Dùng để giải thích mô hình logic | Rất rõ | Rất rõ | Thể hiện quy tắc riêng cần giải thích |

Index được tạo để hỗ trợ constraint có thể có tên trùng tên constraint; việc xóa constraint có thể kéo theo index thuộc constraint. Vì vậy không thao tác trực tiếp trên index **do constraint sở hữu** như thể nó là index độc lập.

### 7.3. Xem index bằng pg_indexes

```sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'constraint_lab'
ORDER BY tablename, indexname;
```

`pg_indexes.indexdef` cho biết câu lệnh định nghĩa index theo PostgreSQL, gồm phương thức, key columns, thuộc tính `UNIQUE` và predicate nếu có.

### 7.4. Xem constraint bằng pg_constraint

```sql
SELECT
    con.conname AS constraint_name,
    con.contype AS constraint_type,
    con.conrelid::regclass AS table_name,
    con.conindid::regclass AS supporting_index,
    con.condeferrable AS is_deferrable,
    con.condeferred AS initially_deferred,
    pg_get_constraintdef(con.oid, true) AS definition
FROM pg_constraint AS con
JOIN pg_namespace AS n
  ON n.oid = con.connamespace
WHERE n.nspname = 'constraint_lab'
  AND con.contype IN ('p', 'u')
ORDER BY table_name, constraint_name;
```

Trong `pg_constraint.contype`:

- `p` là primary key.
- `u` là unique constraint.
- `f` là foreign key.
- `c` là check constraint.

Một `CREATE UNIQUE INDEX` độc lập có thể xuất hiện ở `pg_indexes` **mà không có** ràng buộc tương ứng trong `pg_constraint`.

### 7.5. Kiểm tra trạng thái index qua pg_index

```sql
SELECT
    i.indexrelid::regclass AS index_name,
    i.indrelid::regclass AS table_name,
    i.indisunique AS unique_index,
    i.indisprimary AS primary_index,
    i.indisvalid AS valid_for_planner,
    i.indisready AS ready_for_writes,
    i.indnkeyatts AS key_columns,
    i.indnatts AS all_index_columns,
    pg_get_indexdef(i.indexrelid) AS definition
FROM pg_index AS i
WHERE i.indrelid = 'constraint_lab.products'::regclass
ORDER BY index_name;
```

Các trường `indisvalid`, `indisready` đặc biệt hữu ích khi một **CREATE INDEX CONCURRENTLY** bị lỗi hoặc chưa hoàn tất. Không coi index tồn tại trong catalog là bằng chứng nó đã sẵn sàng và hợp lệ.

## 8. UNIQUE INDEX độc lập: dùng khi constraint chuẩn chưa đủ

### 8.1. Tạo một unique index thông thường

```sql
CREATE UNIQUE INDEX ux_users_username
ON users (username);
```

Cú pháp này đòi bảng `users` đã tồn tại; đây là ví dụ minh họa, không phải lệnh chạy ngay trên schema thực hành.

Nó bảo vệ uniqueness tương tự một constraint không trì hoãn, nhưng tồn tại dưới dạng **index độc lập**. Nếu không cần biểu thức/predicate hay quy trình đặc biệt, dùng `UNIQUE` constraint trong DDL thường diễn đạt mô hình rõ ràng hơn.

### 8.2. Unique index trên biểu thức

Đôi khi nghiệp vụ coi hai email khác nhau về chữ hoa/thường là cùng một định danh:

```text
Lan@Example.com
lan@example.com
```

Nếu chỉ có:

```sql
UNIQUE (email)
```

thì với các kiểu/collation so sánh phân biệt phù hợp, hai chuỗi có thể không bị xem là trùng.

Có thể dùng expression index:

```sql
CREATE UNIQUE INDEX ux_users_email_normalized
ON users (lower(btrim(email)));
```

Index thực thi uniqueness trên **kết quả biểu thức** `lower(btrim(email))`, chứ không phải nguyên văn `email`.

Cần lưu ý:

- Biểu thức index phải đáp ứng các yêu cầu của PostgreSQL, gồm khả năng sử dụng các hàm phù hợp trong index expression.
- Quy tắc email không phân biệt hoa/thường cần được xác nhận, nhất là phần local-part, Unicode, collation và chính sách chuẩn hóa.
- **Dữ liệu cũ** chứa hai giá trị có cùng biểu thức chuẩn hóa sẽ khiến việc tạo unique index thất bại.
- Query muốn tận dụng expression index thường phải có biểu thức/điều kiện phù hợp để planner nhận diện.
- Không dùng unique expression index như một khóa FK thông thường nếu cần tham chiếu bằng cột gốc theo các quy tắc FK chuẩn.

Một lựa chọn khác khi môi trường hỗ trợ là extension `citext` hoặc thiết kế collation phù hợp, nhưng mỗi phương án có semantics/chi phí cần được đánh giá; không tự coi mọi phương án là tương đương.

### 8.3. Partial unique index: ràng buộc chỉ một phần dữ liệu

Yêu cầu:

> Mỗi khách hàng chỉ có **tối đa một địa chỉ giao hàng mặc định**.

Một bảng có nhiều địa chỉ:

```sql
CREATE TABLE customer_addresses (
    address_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    label TEXT NOT NULL,
    is_default BOOLEAN NOT NULL DEFAULT FALSE
);
```

Nếu dùng:

```sql
UNIQUE (customer_id, is_default)
```

sẽ sai vì nó cho phép **tối đa một** địa chỉ `is_default = FALSE` cho mỗi khách, trong khi khách phải được có nhiều địa chỉ phụ.

Giải pháp là **partial unique index**:

```sql
CREATE UNIQUE INDEX ux_addresses_one_default
ON customer_addresses (customer_id)
WHERE is_default;
```

Index chỉ chứa những hàng mà `is_default` là TRUE. Vì vậy:

- Một khách có **nhiều địa chỉ phụ**.
- Một khách có **tối đa một địa chỉ mặc định**.
- Khách có thể **không có** địa chỉ mặc định.

Điểm cuối quan trọng: partial unique index bảo vệ điều kiện **“tối đa một”**, **không bảo đảm “bắt buộc có đúng một”**. Nếu cần ít nhất một địa chỉ mặc định, phải bổ sung quy trình nghiệp vụ/ràng buộc khác phù hợp với tình huống tạo và xóa dữ liệu.

### 8.4. Soft delete và uniqueness có điều kiện

Một ứng dụng có thể giữ hàng đã xóa mềm:

```sql
CREATE TABLE project_members (
    membership_id BIGINT PRIMARY KEY,
    project_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    deleted_at TIMESTAMPTZ
);
```

Quy tắc:

> Một cặp `(project_id, user_id)` chỉ được có một membership **chưa bị xóa mềm**.

```sql
CREATE UNIQUE INDEX ux_project_members_active
ON project_members (project_id, user_id)
WHERE deleted_at IS NULL;
```

Khi một membership đã có `deleted_at` khác NULL, nó rời khỏi tập index và cặp này có thể được tạo lại cho một membership mới.

Vì vậy cần quyết định rõ khi “khôi phục” membership cũ: nếu đã tồn tại membership mới đang hoạt động cho cùng cặp, đặt `deleted_at = NULL` trên bản ghi cũ sẽ bị unique index chặn. Đây thường là hành vi mong muốn để tránh hai thành viên active.

### 8.5. Partial index không phải UNIQUE constraint chuẩn

`UNIQUE` constraint không có cú pháp `WHERE` để chỉ áp dụng cho một số hàng. `CREATE UNIQUE INDEX ... WHERE ...` là giải pháp đúng cho uniqueness có điều kiện.

Một partial unique index **không thể được gắn thành UNIQUE constraint thông thường** qua `ALTER TABLE ... ADD CONSTRAINT ... USING INDEX`, và không thể làm khóa đích tham chiếu FK phổ thông như một unique key không partial.

## 9. Thứ tự cột, index ghép và tối ưu truy vấn

### 9.1. Thứ tự khóa ảnh hưởng đường truy cập

Với:

```sql
UNIQUE (tenant_id, sku)
```

PostgreSQL tạo B-tree theo khóa `(tenant_id, sku)`.

Câu:

```sql
SELECT *
FROM constraint_lab.products
WHERE tenant_id = 10
  AND sku = 'P-100';
```

là trường hợp dùng hai key columns rất phù hợp.

Câu:

```sql
SELECT *
FROM constraint_lab.products
WHERE tenant_id = 10;
```

có thể tận dụng tiền tố `tenant_id` nếu bảng đủ lớn và planner thấy có lợi.

Câu:

```sql
SELECT *
FROM constraint_lab.products
WHERE sku = 'P-100';
```

không có cùng ưu thế tiền tố. Nếu truy vấn tìm SKU trên **mọi tenant** thường xuyên và trả ít dòng, cần thử một index khác, chẳng hạn:

```sql
CREATE INDEX ix_products_sku
ON constraint_lab.products (sku);
```

Tuy nhiên, chỉ tạo sau khi kiểm tra workload và `EXPLAIN`; không mặc định một index thêm là tốt cho mọi trường hợp.

### 9.2. Một index để kiểm tra uniqueness có thể phục vụ SELECT

Với primary key:

```sql
PRIMARY KEY (order_id)
```

query:

```sql
SELECT *
FROM constraint_lab.orders
WHERE order_id = 1001;
```

có cơ hội truy cập hàng bằng PK index. Nhưng với bảng vài dòng, PostgreSQL có thể chọn `Seq Scan`; điều đó **không có nghĩa PK/UNIQUE không hoạt động**. Ràng buộc vẫn được thực thi khi ghi, độc lập với quyết định đọc của planner.

### 9.3. Không tạo index trùng để “chắc ăn”

Nếu bảng đã có:

```sql
PRIMARY KEY (tenant_id, sku)
```

thì:

```sql
CREATE UNIQUE INDEX ux_products_same_columns
ON constraint_lab.products (tenant_id, sku);
```

thường không mang lại thêm một quy tắc nghiệp vụ mới và tăng chi phí ghi. Khi định tối ưu, kiểm tra `pg_indexes` trước và xem lý do cụ thể cần một index khác hướng sort, thứ tự key, predicate hoặc covering.

### 9.4. INCLUDE và covering index

PostgreSQL hỗ trợ đưa các cột **không tham gia khóa tra cứu/uniqueness** vào index như cột **INCLUDE**, ví dụ:

```sql
CREATE INDEX ix_products_tenant_sku_cover
ON constraint_lab.products (tenant_id, sku)
INCLUDE (product_name, price);
```

Index có hai **key columns** và thêm hai **included columns**. Các included columns:

- Có thể giúp một số query lấy dữ liệu từ index mà không cần đọc toàn bộ hàng heap khi đáp ứng điều kiện.
- **Không tham gia** kiểm tra uniqueness của key columns trong unique index có INCLUDE.
- Làm index lớn hơn; kiểu dữ liệu và kích thước giá trị có thể ảnh hưởng khả năng lưu trữ/index.
- Không phải lúc nào cũng tránh heap fetch vì PostgreSQL còn cần bảo đảm **MVCC visibility**.

Ví dụ nếu một unique constraint/index có khóa `(tenant_id, sku)` và `INCLUDE(product_name)`, uniqueness vẫn chỉ dựa trên `(tenant_id, sku)`.

**Chú ý:** ở schema lab đã có PK `(tenant_id, sku)`. Index covering vừa nêu là **ứng viên thử nghiệm** có thể chồng lấn PK index, không phải khuyến nghị luôn giữ cả hai. Cần đo trước khi thêm index rộng.

## 10. FOREIGN KEY: khóa đích và index phía tham chiếu

### 10.1. FK phải tham chiếu khóa có uniqueness được PostgreSQL chấp nhận

Ví dụ:

```sql
CREATE TABLE authors (
    author_id BIGINT PRIMARY KEY,
    pen_name TEXT NOT NULL UNIQUE
);

CREATE TABLE books (
    book_id BIGINT PRIMARY KEY,
    author_id BIGINT NOT NULL
        REFERENCES authors(author_id)
);
```

Bảng `authors` có PK trên `author_id`. Bảng `books` dùng FK để bảo đảm ID được tham chiếu là hợp lệ.

Theo các điều kiện PostgreSQL, cột đích của FK có thể là **primary key**, cột có **unique constraint không deferrable**, hoặc các cột thuộc một **unique index không partial** phù hợp. Không suy luận một partial/expression unique index là khóa đích FK thông thường.

### 10.2. PostgreSQL không tự tạo index trên cột FK ở phía con

Khi:

```sql
CREATE TABLE books (
    book_id BIGINT PRIMARY KEY,
    author_id BIGINT NOT NULL REFERENCES authors(author_id)
);
```

PostgreSQL bảo vệ quan hệ nhờ PK/unique ở **bảng cha**. Nó **không tự động** tạo thêm index trên `books(author_id)` chỉ vì đã có FK.

Nếu thường xuyên tìm sách theo tác giả hoặc xóa/sửa khóa ở bảng `authors`, có thể thêm:

```sql
CREATE INDEX ix_books_author_id
ON books(author_id);
```

Chỉ mục trên bảng con có thể quan trọng khi PostgreSQL kiểm tra các dòng tham chiếu trong lúc `DELETE`/`UPDATE` ở bảng cha. Không có index phù hợp, một số thao tác có thể cần quét nhiều hàng ở bảng con.

### 10.3. Khóa ngoại ghép

Giả sử:

```sql
PRIMARY KEY (tenant_id, sku)
```

trên sản phẩm. Bảng ghi chú phải tham chiếu đúng **cả hai cột**:

```sql
FOREIGN KEY (tenant_id, sku)
REFERENCES products(tenant_id, sku)
```

Không thể dựa vào FK chỉ trên `sku` nếu SKU không unique toàn hệ thống.

### 10.4. Unique partial index và FK

Nếu chỉ có:

```sql
CREATE UNIQUE INDEX ux_active_email
ON customers (email)
WHERE deleted_at IS NULL;
```

thì uniqueness chỉ áp dụng ở tập **khách chưa bị xóa mềm**. Không thể dùng nó như một khóa tham chiếu FK chuẩn cho mọi hàng trong `customers`, bởi các hàng không thỏa predicate có thể trùng email.

Đây là lý do các quan hệ thường tham chiếu **PK bất biến** như `customer_id`, còn email là thuộc tính nghiệp vụ với unique rule riêng.

## 11. DEFERRABLE UNIQUE và PRIMARY KEY

### 11.1. Immediate hay deferred?

Mặc định constraint thường được kiểm tra theo quy tắc **không trì hoãn**. Một số tình huống cần một transaction **tạm thời** tạo trạng thái vi phạm uniqueness nhưng đưa dữ liệu về hợp lệ **trước khi commit**.

Ví dụ đổi số ghế 1 và 2 cho hai người trong cùng một phiên:

```text
Khách A: seat 1
Khách B: seat 2
```

Nếu cập nhật A thành 2 rồi mới cập nhật B thành 1, bước trung gian có thể bị unique constraint chặn.

PostgreSQL hỗ trợ constraint `DEFERRABLE`:

```sql
CREATE TABLE seat_assignments (
    assignment_id BIGINT PRIMARY KEY,
    session_id BIGINT NOT NULL,
    seat_no INTEGER NOT NULL,
    CONSTRAINT uq_session_seat
        UNIQUE (session_id, seat_no)
        DEFERRABLE INITIALLY DEFERRED
);
```

Dữ liệu mẫu:

```sql
INSERT INTO seat_assignments
    (assignment_id, session_id, seat_no)
VALUES
    (1, 10, 1),
    (2, 10, 2);
```

Transaction đổi ghế:

```sql
BEGIN;

UPDATE seat_assignments
SET seat_no = CASE seat_no
    WHEN 1 THEN 2
    WHEN 2 THEN 1
END
WHERE session_id = 10
  AND seat_no IN (1, 2);

COMMIT;
```

Constraint được kiểm tra theo chế độ deferred, cho phép trạng thái trung gian nhưng yêu cầu **dữ liệu hợp lệ tại điểm kiểm tra cuối**. Nếu còn hai hàng cùng `(session_id, seat_no)` khi commit, transaction sẽ thất bại.

### 11.2. Đặt thời điểm kiểm tra

Có thể khai báo:

```sql
UNIQUE (session_id, seat_no)
DEFERRABLE INITIALLY IMMEDIATE
```

và trong transaction có quyền/phạm vi phù hợp:

```sql
BEGIN;

SET CONSTRAINTS uq_session_seat DEFERRED;

-- Thực hiện một loạt thay đổi.
-- Trạng thái cuối phải thỏa uniqueness.

COMMIT;
```

`SET CONSTRAINTS` chỉ điều khiển các constraint có thể deferrable, không biến mọi index thành deferrable.

### 11.3. Đánh đổi khi sử dụng DEFERRABLE

- Vi phạm có thể chỉ xuất hiện lúc `COMMIT`, nên ứng dụng phải xử lý lỗi commit.
- Constraint có thể gây chi phí và tranh chấp khác so với uniqueness kiểm tra tức thì.
- PostgreSQL **không cho dùng deferrable unique constraints làm arbiter cho `ON CONFLICT DO UPDATE`**.
- Khi làm khóa đích FK, cần lưu ý PostgreSQL yêu cầu khóa tham chiếu có uniqueness phù hợp **không deferrable**.

Vì vậy chỉ dùng `DEFERRABLE` khi thật sự có nghiệp vụ cần tạm thời đổi thứ tự/mã trong cùng transaction.

### 11.4. ON CONFLICT và DEFERRABLE

`INSERT ... ON CONFLICT` cần một arbiter phù hợp để quyết định hàng nào xung đột. Deferrable unique constraint **không phải lựa chọn phù hợp** cho cú pháp đó. Nếu quy trình chủ yếu là upsert theo business key, một `UNIQUE` **không deferrable** thường tự nhiên hơn.

## 12. INSERT ... ON CONFLICT: ghi an toàn trước cạnh tranh đồng thời

### 12.1. Khi nào cần upsert?

Giả sử API nhận một bản ghi khách hàng với business key:

```text
(tenant_id = 10, email = 'an@example.com')
```

Nếu chưa có thì thêm; nếu đã có thì cập nhật tên. Hai request đồng thời không nên dùng quy trình `SELECT` rồi quyết định `INSERT` riêng rẽ.

PostgreSQL hỗ trợ `ON CONFLICT` để phối hợp với uniqueness enforcement.

### 12.2. DO NOTHING

```sql
INSERT INTO constraint_lab.customers
    (customer_id, tenant_id, email, display_name)
VALUES
    (99, 10, 'an@example.com', 'An mới')
ON CONFLICT ON CONSTRAINT uq_customers_tenant_email
DO NOTHING;
```

Nếu tenant 10 đã có email tương ứng, câu không chèn dòng mới. Nhưng việc **bỏ qua** xung đột cần phù hợp nghiệp vụ: nếu đây là thao tác đăng ký mà người dùng phải nhận lỗi “email đã dùng”, `DO NOTHING` có thể che mất sự kiện quan trọng.

### 12.3. DO UPDATE

```sql
INSERT INTO constraint_lab.customers
    (customer_id, tenant_id, email, display_name)
VALUES
    (99, 10, 'an@example.com', 'Nguyễn An mới')
ON CONFLICT ON CONSTRAINT uq_customers_tenant_email
DO UPDATE SET
    display_name = EXCLUDED.display_name
RETURNING customer_id, tenant_id, email, display_name;
```

`EXCLUDED.display_name` là giá trị của dòng định chèn, còn bản ghi hiện có được cập nhật theo hành động `DO UPDATE`.

**Chú ý:** nếu đã tồn tại `(tenant_id=10,email='an@example.com')`, `customer_id=99` của dòng đề xuất không tự thay thế PK cũ trừ khi bạn chủ động cập nhật PK (thường không nên). `RETURNING` trả thông tin hàng cuối cùng theo hành động.

### 12.4. Chọn conflict target đúng

Có thể chỉ rõ columns:

```sql
ON CONFLICT (tenant_id, email)
DO UPDATE SET display_name = EXCLUDED.display_name
```

hoặc constraint name:

```sql
ON CONFLICT ON CONSTRAINT uq_customers_tenant_email
DO UPDATE SET display_name = EXCLUDED.display_name
```

Việc **chọn đúng business key** rất quan trọng. Nếu chọn chỉ `customer_id`, hệ thống có thể xử lý một trường hợp trùng PK nhưng bỏ qua rule tenant/email, hoặc ngược lại.

Cũng cần xử lý những lỗi uniqueness khác: ví dụ không thể mặc định mọi `23505` đều là một loại xung đột mà application được phép bỏ qua.

### 12.5. ON CONFLICT với partial unique index

Khi dùng unique index có predicate:

```sql
CREATE UNIQUE INDEX ux_active_membership
ON project_members(project_id, user_id)
WHERE deleted_at IS NULL;
```

có thể viết conflict target có predicate tương ứng để PostgreSQL tìm arbiter phù hợp:

```sql
INSERT INTO project_members
    (membership_id, project_id, user_id, deleted_at)
VALUES
    (101, 10, 20, NULL)
ON CONFLICT (project_id, user_id)
    WHERE deleted_at IS NULL
DO NOTHING;
```

Đây là ví dụ **trên bảng đã tạo partial index tương ứng**. Không dùng `ON CONFLICT ON CONSTRAINT ux_active_membership` để chỉ một unique index không thuộc constraint: tên index trực tiếp **không phải tên constraint**.

Cần kiểm tra quy tắc inference của arbiter trên PostgreSQL version đang dùng và những index khác có thể cùng phù hợp. Nếu business logic cần phân biệt giữa một membership active và một membership đã xóa mềm, hãy thử dữ liệu cả hai trường hợp.

## 13. Phòng thực hành: tạo schema và dữ liệu

Phần này dùng một schema riêng: `constraint_lab`.

### 13.1. Khởi tạo

```sql
CREATE SCHEMA IF NOT EXISTS constraint_lab;
```

Nếu schema tồn tại từ lần thử khác, không xóa nó tùy tiện; tạo database lab sạch hoặc chọn schema khác có cùng cấu trúc.

### 13.2. Bảng tenants

```sql
CREATE TABLE constraint_lab.tenants (
    tenant_id BIGINT PRIMARY KEY,
    tenant_name TEXT NOT NULL UNIQUE
);
```

Trong ví dụ này `tenant_name` được đặt unique để minh họa một alternate key. Trong doanh nghiệp thật, tên hiển thị có thể trùng, nên đôi khi cần `tenant_code` unique và cho phép `tenant_name` trùng.

### 13.3. Bảng customers

```sql
CREATE TABLE constraint_lab.customers (
    customer_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL
        REFERENCES constraint_lab.tenants(tenant_id),
    email TEXT NOT NULL,
    display_name TEXT NOT NULL,
    CONSTRAINT uq_customers_tenant_email
        UNIQUE (tenant_id, email)
);
```

Quy tắc:

- `customer_id` là ID toàn cục của khách trong dữ liệu lab.
- `tenant_id` tham chiếu tenant có thật.
- Một tenant không có hai khách cùng `email`.
- Hai tenant khác nhau **có thể** dùng cùng email.

Đây là uniqueness **trong phạm vi tenant**, không phải toàn hệ thống.

### 13.4. Bảng products với PRIMARY KEY ghép

```sql
CREATE TABLE constraint_lab.products (
    tenant_id BIGINT NOT NULL
        REFERENCES constraint_lab.tenants(tenant_id),
    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,
    price NUMERIC(12,2) NOT NULL CHECK (price >= 0),
    CONSTRAINT pk_products
        PRIMARY KEY (tenant_id, sku)
);
```

Không có cột `product_id` toàn cục trong ví dụ này. Khóa `(tenant_id, sku)` đủ xác định một sản phẩm theo phạm vi nghiệp vụ đã giả định.

### 13.5. Bảng orders có alternate key nullable

```sql
CREATE TABLE constraint_lab.orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES constraint_lab.customers(customer_id),
    external_ref TEXT,
    status TEXT NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    amount NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    ordered_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_orders_customer_external
        UNIQUE (customer_id, external_ref)
);
```

`external_ref` có thể NULL khi nguồn ngoài chưa cấp mã. Unique mặc định cho phép nhiều đơn cùng customer có `external_ref NULL`; các mã **không NULL** phải duy nhất trong phạm vi customer.

### 13.6. Bảng addresses và partial unique index

```sql
CREATE TABLE constraint_lab.customer_addresses (
    address_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES constraint_lab.customers(customer_id),
    address_label TEXT NOT NULL,
    is_default BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE UNIQUE INDEX ux_customer_one_default_address
ON constraint_lab.customer_addresses (customer_id)
WHERE is_default;
```

Mỗi khách có thể có nhiều địa chỉ phụ và tối đa một địa chỉ mặc định.

### 13.7. Nạp dữ liệu

```sql
INSERT INTO constraint_lab.tenants
    (tenant_id, tenant_name)
VALUES
    (10, 'Shop A'),
    (20, 'Shop B');

INSERT INTO constraint_lab.customers
    (customer_id, tenant_id, email, display_name)
VALUES
    (1, 10, 'an@example.com', 'Nguyễn An'),
    (2, 10, 'binh@example.com', 'Trần Bình'),
    (3, 20, 'an@example.com', 'Nguyễn An ở Shop B');

INSERT INTO constraint_lab.products
    (tenant_id, sku, product_name, price)
VALUES
    (10, 'P-100', 'Bàn phím', 350000),
    (10, 'P-101', 'Chuột', 150000),
    (20, 'P-100', 'Bàn phím Shop B', 380000);

INSERT INTO constraint_lab.orders
    (order_id, customer_id, external_ref, status, amount)
VALUES
    (1001, 1, 'REQ-001', 'PAID', 350000),
    (1002, 1, NULL, 'NEW', 150000),
    (1003, 1, NULL, 'NEW', 250000),
    (1004, 2, 'REQ-001', 'PAID', 500000);

INSERT INTO constraint_lab.customer_addresses
    (address_id, customer_id, address_label, is_default)
VALUES
    (11, 1, 'Nhà', TRUE),
    (12, 1, 'Công ty', FALSE),
    (21, 2, 'Nhà', TRUE),
    (31, 3, 'Cơ quan', FALSE);
```

Dữ liệu mẫu cho thấy:

- Hai tenant có thể cùng SKU `P-100`.
- Hai tenant có thể cùng email `an@example.com`.
- Hai khách khác nhau có thể cùng `external_ref='REQ-001'`.
- Một khách có thể có **nhiều đơn external_ref NULL**.
- Một khách có nhiều địa chỉ phụ nhưng chỉ một địa chỉ mặc định.

Các số ID được cung cấp tường minh cho bài tập. Trong hệ thống thật, có thể cân nhắc identity/UUID nếu cần cơ chế cấp ID thay vì tự chọn số.

## 14. Thử các trường hợp hợp lệ và vi phạm

### 14.1. PRIMARY KEY trùng

Dòng sau **sẽ lỗi `23505`** vì sản phẩm của tenant 10 với SKU `P-100` đã có:

```sql
-- CHỈ CHẠY RIÊNG KHI MUỐN QUAN SÁT LỖI:
INSERT INTO constraint_lab.products
    (tenant_id, sku, product_name, price)
VALUES
    (10, 'P-100', 'Tên mới', 400000);
```

Nhưng SKU `P-100` của tenant 20 đã tồn tại độc lập, không xung đột với tenant 10.

### 14.2. UNIQUE trong phạm vi tenant

Dòng sau **sẽ lỗi** vì tenant 10 đã có email:

```sql
-- CHỈ CHẠY RIÊNG KHI MUỐN QUAN SÁT LỖI:
INSERT INTO constraint_lab.customers
    (customer_id, tenant_id, email, display_name)
VALUES
    (99, 10, 'an@example.com', 'Một khách khác');
```

Một email ở tenant 20 không vi phạm key `(10, 'an@example.com')`.

### 14.3. UNIQUE với nhiều NULL

```sql
SELECT order_id, customer_id, external_ref
FROM constraint_lab.orders
WHERE customer_id = 1
ORDER BY order_id;
```

Trong dữ liệu mẫu, khách 1 có hai đơn với `external_ref IS NULL`; cả hai hợp lệ.

### 14.4. Vi phạm partial unique index

```sql
-- CHỈ CHẠY RIÊNG KHI MUỐN QUAN SÁT LỖI:
INSERT INTO constraint_lab.customer_addresses
    (address_id, customer_id, address_label, is_default)
VALUES
    (13, 1, 'Địa chỉ mặc định thứ hai', TRUE);
```

Unique index trên `customer_id WHERE is_default` sẽ chặn vì khách 1 đã có địa chỉ 11 là mặc định.

Thêm địa chỉ phụ:

```sql
BEGIN;

INSERT INTO constraint_lab.customer_addresses
    (address_id, customer_id, address_label, is_default)
VALUES
    (13, 1, 'Địa chỉ phụ khác', FALSE);

ROLLBACK;
```

hợp lệ vì `FALSE` không thuộc predicate của unique index. `ROLLBACK` giữ bộ dữ liệu mẫu cho các phần sau.

### 14.5. Quan sát lỗi trong transaction

Nếu muốn thử một lệnh dự kiến lỗi mà vẫn tiếp tục transaction, dùng `SAVEPOINT`:

```sql
BEGIN;

SAVEPOINT before_duplicate;

-- Chạy một lệnh INSERT dự kiến vi phạm UNIQUE ở đây.
-- Sau khi nhận lỗi 23505, thực hiện:

ROLLBACK TO SAVEPOINT before_duplicate;

ROLLBACK;
```

Nếu không `ROLLBACK TO SAVEPOINT` sau khi statement báo lỗi trong transaction, PostgreSQL thường coi transaction hiện tại là **aborted** và các statement tiếp theo bị từ chối cho đến khi rollback. Không dán toàn bộ các lệnh kiểm thử lỗi vào một script rồi giả định client sẽ tự tiếp tục mọi bước.

## 15. Truy vấn metadata để chứng minh constraint nào đang tồn tại

### 15.1. Liệt kê PK/UNIQUE của schema

```sql
SELECT
    con.conrelid::regclass AS table_name,
    con.conname AS constraint_name,
    CASE con.contype
        WHEN 'p' THEN 'PRIMARY KEY'
        WHEN 'u' THEN 'UNIQUE'
        ELSE con.contype::text
    END AS constraint_type,
    con.conindid::regclass AS supporting_index,
    pg_get_constraintdef(con.oid, true) AS definition
FROM pg_constraint AS con
JOIN pg_namespace AS n
  ON n.oid = con.connamespace
WHERE n.nspname = 'constraint_lab'
  AND con.contype IN ('p', 'u')
ORDER BY table_name, constraint_name;
```

Thông tin `supporting_index` cho thấy index ràng buộc dùng. Các index tạo độc lập — như partial index của địa chỉ mặc định — cần được xem riêng qua `pg_indexes`.

### 15.2. Liệt kê mọi index

```sql
SELECT
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'constraint_lab'
ORDER BY tablename, indexname;
```

Một bài kiểm tra hữu ích:

1. Tìm index của `pk_products`.
2. Tìm index của `uq_customers_tenant_email`.
3. Tìm `ux_customer_one_default_address` và predicate `WHERE is_default`.
4. Đối chiếu index nào **do constraint tạo**, index nào **tạo trực tiếp**.

### 15.3. information_schema

```sql
SELECT
    table_schema,
    table_name,
    constraint_name,
    constraint_type
FROM information_schema.table_constraints
WHERE table_schema = 'constraint_lab'
  AND constraint_type IN ('PRIMARY KEY', 'UNIQUE')
ORDER BY table_name, constraint_name;
```

`information_schema` là giao diện metadata theo chuẩn SQL; `pg_catalog` và `pg_indexes` cung cấp nhiều chi tiết riêng của PostgreSQL hơn, nhất là expression/partial indexes.

### 15.4. psql và pgAdmin

Trong `psql`:

```text
\d+ constraint_lab.products
\d+ constraint_lab.customers
\di constraint_lab.*
```

Đây là **psql meta-commands**, không phải câu SQL gửi qua JDBC hoặc pgAdmin Query Tool. Trong pgAdmin, xem các nhóm **Constraints**, **Indexes** và SQL/DDL của bảng.

## 16. EXPLAIN: index hỗ trợ ràng buộc có được dùng khi đọc không?

### 16.1. Quan sát truy vấn tra PK

```sql
EXPLAIN
SELECT tenant_id, sku, product_name, price
FROM constraint_lab.products
WHERE tenant_id = 10
  AND sku = 'P-100';
```

Planner **có thể** chọn index trên `(tenant_id,sku)` hoặc `Seq Scan` tùy quy mô, dữ liệu và ước lượng chi phí. Trên bảng có vài hàng, quét bảng thường rất rẻ.

Không vì thấy `Seq Scan` mà kết luận PK không hoạt động: **uniqueness khi ghi** và **kế hoạch đọc** là hai chức năng khác nhau.

### 16.2. EXPLAIN ANALYZE và BUFFERS

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT tenant_id, sku, product_name, price
FROM constraint_lab.products
WHERE tenant_id = 10
  AND sku = 'P-100';
```

`EXPLAIN ANALYZE` **thực thi câu SELECT thật** để đo. Đọc:

- `actual time` và `actual rows`.
- `loops` của từng node.
- Số buffer được hit/read.
- Sự chênh lệch giữa `rows` ước lượng và thực tế.
- Có hay không `Index Scan`/`Index Only Scan`.

Đối với bảng mẫu nhỏ, số mili giây **không dự báo** tình trạng khi có hàng triệu hàng. Muốn đánh giá hiệu năng index, phải đo trên dữ liệu đại diện và điều kiện lọc thực tế.

### 16.3. Unique index không bảo đảm Index Only Scan

Ngay cả khi query chỉ đọc các cột có trong index, PostgreSQL vẫn cần tuân theo **MVCC visibility**. `Index Only Scan` đôi khi phải về heap nếu Visibility Map chưa đánh dấu page all-visible; xem chỉ số `Heap Fetches` trong kế hoạch.

Vì vậy không thể suy luận một index bao phủ cột là luôn tránh mọi lần đọc bảng.

### 16.4. Quan sát thống kê sử dụng index

```sql
SELECT
    schemaname,
    relname,
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'constraint_lab'
ORDER BY relname, indexrelname;
```

Các bộ đếm là **thống kê từ thời gian hoạt động/chu kỳ reset**, không phải số liệu trong một câu truy vấn duy nhất, và có các giới hạn về cách diễn giải. Một unique index có `idx_scan` thấp vẫn có thể quan trọng để **bảo vệ uniqueness khi ghi**.

**Không xóa unique index chỉ vì thấy ít lượt Index Scan.**

## 17. Thêm PRIMARY KEY hoặc UNIQUE cho bảng đang có dữ liệu

Một bảng lớn có thể ban đầu chưa có constraint. Việc thêm ràng buộc trên production đòi nhiều bước hơn một câu `ALTER TABLE`.

### 17.1. Kiểm tra dữ liệu trùng trước

Giả sử bảng `legacy_customers(tenant_id,email,...)` đang tồn tại:

```sql
SELECT
    tenant_id,
    email,
    COUNT(*) AS duplicate_count
FROM legacy_customers
GROUP BY tenant_id, email
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC, tenant_id, email;
```

Câu này là truy vấn minh họa, chỉ chạy khi bảng thật tồn tại. Với dữ liệu lớn, chính phép `GROUP BY` có thể tốn tài nguyên.

Nếu muốn key bắt buộc không NULL:

```sql
SELECT COUNT(*) AS null_keys
FROM legacy_customers
WHERE tenant_id IS NULL
   OR email IS NULL;
```

Với `UNIQUE NULLS NOT DISTINCT`, duplicate check có thể cần xử lý nhóm NULL theo semantics mục tiêu. Với `PRIMARY KEY`, mọi thành phần khóa phải **không NULL**.

Không thể “sửa” duplicate bằng `MAX(id)`, `DISTINCT` hoặc xóa bừa những dòng mà không biết dữ liệu nào là nguồn sự thật. Cần chính sách merge/dedup do nghiệp vụ xác nhận.

### 17.2. Thêm constraint trực tiếp

Ví dụ:

```sql
ALTER TABLE legacy_customers
ADD CONSTRAINT uq_legacy_tenant_email
UNIQUE (tenant_id, email);
```

PostgreSQL phải xác nhận uniqueness và tạo index hỗ trợ. Trên bảng lớn, có thể phát sinh thời gian quét, khóa và tải I/O đáng kể. Không mặc định thao tác DDL này là “online, không chặn ghi”.

### 17.3. Tạo index concurrently rồi gắn constraint

Với bảng lớn, một chiến lược thường được cân nhắc là:

```sql
CREATE UNIQUE INDEX CONCURRENTLY
    ux_legacy_tenant_email
ON legacy_customers (tenant_id, email);
```

Sau khi tạo **thành công, hợp lệ**, có thể gắn index phù hợp thành constraint:

```sql
ALTER TABLE legacy_customers
ADD CONSTRAINT uq_legacy_tenant_email
UNIQUE USING INDEX ux_legacy_tenant_email;
```

Một số điều kiện khi dùng `USING INDEX`:

- Index cần là B-tree **unique**, hợp lệ và đáp ứng yêu cầu cấu trúc.
- **Không** là partial index hoặc expression index.
- Các thuộc tính sắp xếp/phương thức phải tương thích với yêu cầu của PostgreSQL cho constraint.
- `ALTER TABLE` vẫn có thể cần khóa và có tác động ngắn nhưng đáng kể trong giờ tải cao.
- Khi gắn index, constraint trở thành chủ sở hữu của index tương ứng theo cơ chế PostgreSQL.

`CREATE INDEX CONCURRENTLY` không được chạy bên trong một transaction block thông thường. Việc thêm **PRIMARY KEY** qua `USING INDEX` còn phải đảm bảo các cột khóa là `NOT NULL`; nếu chưa có, PostgreSQL có thể phải thực hiện thêm bước xác minh/thay đổi, có tác động khóa và scan.

### 17.4. Nếu CREATE UNIQUE INDEX CONCURRENTLY thất bại

Các nguyên nhân thường gặp:

- Dữ liệu hiện đã có duplicate.
- Một transaction đồng thời chèn duplicate trong quá trình tạo.
- Lỗi tài nguyên, deadlock hoặc công việc bị hủy.
- Thay đổi schema khác diễn ra trong thời gian build.

Một đợt tạo index concurrently bị lỗi **có thể để lại index `INVALID`**. Đặc biệt, tùy giai đoạn lỗi, unique index invalid có thể vẫn liên quan đến thực thi kiểm tra uniqueness trong một số tình huống — không được coi nó là vô hại.

Kiểm tra:

```sql
SELECT
    indexrelid::regclass AS index_name,
    indisvalid,
    indisready,
    indisunique
FROM pg_index
WHERE indrelid = 'legacy_customers'::regclass;
```

Nếu có index invalid, xử lý theo runbook: xác định nguyên nhân, xem index có còn tham gia bảo vệ ghi hay không, quyết định **drop/rebuild concurrently** phù hợp và kiểm tra lại. Không tự xóa index production khi chưa xác minh nó thuộc constraint hay được workload khác sử dụng.

### 17.5. NOT VALID không áp dụng tùy ý cho UNIQUE

PostgreSQL hỗ trợ các quy trình `NOT VALID`/`VALIDATE CONSTRAINT` cho **một số loại constraint** như foreign key và check. Không nên giả định có thể thêm một `UNIQUE NOT VALID` tùy ý rồi validate sau theo cách giống FK: PostgreSQL không hỗ trợ quy trình đó như một lựa chọn chung cho unique constraint.

Với uniqueness trên bảng lớn, cần chọn đúng chiến lược `CREATE UNIQUE INDEX CONCURRENTLY` nếu phù hợp.

## 18. Concurrency, khóa và tính đúng đắn khi ghi

### 18.1. Tại sao UNIQUE ngăn race condition?

Ví dụ hai transaction cùng chèn email:

```text
T1: INSERT (tenant=10,email='new@example.com')
T2: INSERT (tenant=10,email='new@example.com')
```

PostgreSQL phải bảo đảm không thể có hai dòng **cùng thỏa uniqueness** được commit theo semantics constraint. Một transaction có thể phải chờ transaction kia rồi báo lỗi uniqueness, hoặc upsert theo nhánh `ON CONFLICT` tùy câu lệnh.

Điều quan trọng là tính đúng đắn được bảo đảm ở **database boundary**, không phụ thuộc việc hai request có đọc trạng thái trước đó hay không.

### 18.2. Không sử dụng unique constraint như công cụ khóa mọi nghiệp vụ

UNIQUE bảo vệ **giá trị khóa không trùng**. Nó không tự bảo vệ:

- Tổng tồn kho không âm nếu nhiều hàng liên quan.
- Tổng số ghế còn lại theo một thuật toán chọn chỗ.
- Một khách chỉ được tạo tối đa N đơn/ngày.
- Một cặp thời gian đặt lịch không được chồng lấn khi phạm vi là **interval**.

Những quy tắc này có thể đòi cập nhật có điều kiện, transaction, isolation, exclusion constraint hoặc cơ chế đồng thời khác.

Ví dụ “không có hai khoảng đặt phòng chồng nhau” có thể phù hợp với **exclusion constraint** trên range type thay vì UNIQUE một cặp timestamp đơn giản.

### 18.3. Lock và migration

Thay constraint/index ở bảng lớn có thể tương tác với những transaction ghi dài. Cần theo dõi:

- Thời gian chạy DDL.
- Lock waits/blocked sessions.
- CPU, I/O, WAL và replication lag.
- Connection pool và error rate của ứng dụng.
- Những job khác đang tạo/sửa index.

`CREATE INDEX CONCURRENTLY` giảm một số loại chặn ghi so với tạo index thường, nhưng không có nghĩa **không tốn tài nguyên và không phải chờ**. Nó còn phải xử lý các transaction đang hoạt động và các giai đoạn quét dữ liệu.

## 19. UNIQUE và bảng partitioned

PostgreSQL hỗ trợ declarative partitioning, nhưng uniqueness xuyên các partition có những giới hạn quan trọng.

### 19.1. Ví dụ bảng chia theo tenant

```sql
CREATE TABLE partitioned_products (
    tenant_id BIGINT NOT NULL,
    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,
    PRIMARY KEY (tenant_id, sku)
) PARTITION BY LIST (tenant_id);
```

PK gồm `tenant_id`, là **partition key**, phù hợp với yêu cầu chung khi khai báo PK/UNIQUE trên partitioned table.

### 19.2. Tại sao khóa phải chứa partition key?

PostgreSQL sử dụng các index trên từng partition trong nhiều trường hợp, không có một unique index toàn cục độc lập theo mọi partition theo cách ứng dụng có thể mặc định sử dụng.

Để có thể chứng minh uniqueness qua phạm vi partition, các constraint `PRIMARY KEY`/`UNIQUE` khai báo trên partitioned parent phải chứa **toàn bộ các cột của partition key** theo những điều kiện PostgreSQL áp dụng; partition key của thiết kế constraint còn bị giới hạn khi dùng biểu thức/function.

Nếu bảng partition theo `tenant_id`, một `UNIQUE (sku)` trên **parent** không thể tự bảo đảm SKU không lặp trên mọi tenant/partition bằng cơ chế key đó. Nếu nghiệp vụ thực sự yêu cầu SKU unique toàn hệ thống, cần xem lại **chiến lược partition, khóa hoặc cách kiểm soát uniqueness**.

### 19.3. Partition theo ngày và khóa đơn hàng

Một hệ thống chia `orders` theo `created_at` có thể muốn `order_id` unique toàn hệ thống. Nhưng khai báo PK chỉ `(order_id)` trên partitioned parent theo `created_at` không đơn giản tương đương một PK toàn cục trên heap table thường.

Có thể cần khóa gồm partition key, một cơ chế cấp ID toàn cục kết hợp kiểm soát ở nơi khác, hoặc thiết kế partition theo trục khác. **Sequence tạo ID mới không tự là bằng chứng duy nhất tuyệt đối của mọi hàng trong tất cả partition.**

Phải phân biệt **quy tắc nghiệp vụ** và **khả năng ràng buộc của storage/partition layout** trước khi chọn partition key.

## 20. Phân biệt UNIQUE và các khái niệm dễ nhầm

| Khái niệm | Bảo vệ điều gì? | Không tự bảo vệ điều gì? |
|---|---|---|
| `PRIMARY KEY` | Khóa chính không NULL và không trùng | Những business keys khác nếu chưa khai báo |
| `UNIQUE` | Tính duy nhất của key columns theo semantics NULL | Một tham chiếu có tồn tại ở bảng khác |
| `UNIQUE NULLS NOT DISTINCT` | Tính duy nhất khi coi NULL không phân biệt | Mọi cột bắt buộc không NULL |
| `UNIQUE INDEX ... WHERE` | Tính duy nhất chỉ trên tập hàng thỏa predicate | Những hàng nằm ngoài predicate; “phải có ít nhất một” |
| `UNIQUE INDEX(lower(email))` | Tính duy nhất của biểu thức chuẩn hóa | Tính hợp lệ của mọi dạng email theo nghiệp vụ |
| `FOREIGN KEY` | Giá trị tham chiếu đến key đích có thật | Uniqueness ở bảng con nếu nghiệp vụ cần một-một |
| `CHECK` | Biểu thức kiểm tra hàng theo SQL semantics | Các quy tắc tổng quát nhiều hàng |
| `INDEX` không UNIQUE | Đường truy cập dữ liệu | Tính duy nhất |
| `ON CONFLICT` | Xử lý khi INSERT đụng arbiter phù hợp | Mọi loại lỗi nghiệp vụ hoặc xung đột ở constraint khác |

### 20.1. Ràng buộc “tối đa một” khác “đúng một”

`UNIQUE (customer_id)` trên bảng hồ sơ phụ bảo đảm tối đa **một hồ sơ** cho một khách. Nó không bắt buộc **mọi khách** đều phải có hồ sơ.

Tương tự, partial unique index `WHERE is_default` chỉ bảo đảm tối đa một địa chỉ mặc định, không bắt buộc có địa chỉ mặc định.

Nếu cần “mỗi khách **phải có** một địa chỉ mặc định”, phải thiết kế thêm một cơ chế duy trì tính tồn tại và tính nhất quán của tham chiếu, thường có ràng buộc/cập nhật transaction thích hợp.

### 20.2. Tính duy nhất không đồng nghĩa tính hợp lệ của định dạng

```sql
UNIQUE (email)
```

không kiểm tra email có chứa ký tự `@`, không kiểm tra domain tồn tại và không xác nhận email đã được người dùng sở hữu. Những việc đó là các quy tắc khác.

### 20.3. Case-sensitive và collation

Tùy kiểu dữ liệu và collation, so sánh các chuỗi có thể khác nhau. Không mặc định `UNIQUE(TEXT)` luôn coi `An@X` và `an@x` là một giá trị, cũng không khẳng định mọi môi trường đều cùng semantics.

Nếu yêu cầu nghiệp vụ không phân biệt hoa/thường, chọn **chính sách chuẩn hóa/so sánh** cụ thể và kiểm thử trên database version/collation đang dùng.

### 20.4. PK không bảo đảm thứ tự SELECT

Một index B-tree có thứ tự key, nhưng:

```sql
SELECT * FROM constraint_lab.products;
```

không có `ORDER BY` thì **không có thứ tự trả kết quả được SQL đảm bảo**.

Nếu UI cần thứ tự:

```sql
SELECT *
FROM constraint_lab.products
ORDER BY tenant_id, sku;
```

Phải viết `ORDER BY` tường minh; không dựa vào việc bảng có PK.

## 21. Một quy trình thiết kế constraint có thể áp dụng

~~~mermaid
flowchart TD
    A["Xác định thực thể và business keys"] --> B["Chọn PK ổn định, không NULL"]
    B --> C["Liệt kê các alternate unique rules"]
    C --> D["Xác định phạm vi tenant và NULL semantics"]
    D --> E{"Uniqueness áp dụng mọi hàng?"}
    E -- "Có" --> F["UNIQUE constraint / PK"]
    E -- "Không" --> G["Partial unique index"]
    F --> H{"Có chuẩn hóa biểu thức?"}
    G --> H
    H -- "Có" --> I["Expression unique index, kiểm tra dữ liệu"]
    H -- "Không" --> J["Đặt ràng buộc và index phù hợp"]
    I --> J
    J --> K["Thiết kế FK và index phía tham chiếu"]
    K --> L["Kiểm tra duplicate/null và concurrency"]
    L --> M["Migration staging + EXPLAIN + rollback"]
~~~

Trước khi thêm một unique rule, hãy hỏi:

1. **Mã định danh chính** của mỗi hàng là gì?
2. Quy tắc áp dụng **toàn hệ thống, một tenant hay một giai đoạn thời gian**?
3. Có trường hợp khóa **NULL hoặc chưa được cấp** không?
4. Nếu nullable, nhiều dòng cùng NULL có hợp lệ không?
5. Uniqueness có chỉ áp dụng cho dòng `active`, `deleted_at IS NULL` hoặc trạng thái khác không?
6. Có cần so sánh **biểu thức chuẩn hóa** như `lower(email)` không?
7. Có cần khóa này làm **đích tham chiếu của FK** không?
8. Có cần tạm thời vi phạm trong transaction rồi sửa trước commit không?
9. Bộ dữ liệu hiện tại có duplicate hoặc các trường hợp biên không?
10. Index tạo ra có hỗ trợ các truy vấn thường dùng hay đang chồng lấn index khác?

## 22. Những lỗi thiết kế thường gặp

### 22.1. Dùng UNIQUE khi business key chưa ổn định

Ví dụ áp `UNIQUE(full_name)` cho khách hàng có thể chặn những người trùng tên. Hãy dùng key phù hợp và ràng buộc theo quy tắc thật.

### 22.2. Bỏ quên tenant_id trong unique key

Nếu email chỉ cần độc nhất **trong tenant**, `UNIQUE(email)` toàn bảng sẽ chặn cùng email ở tenant khác. Dùng `UNIQUE(tenant_id,email)`.

### 22.3. Nhầm UNIQUE ghép với hai UNIQUE riêng

`UNIQUE(a,b)` không có nghĩa `a` hoặc `b` riêng lẻ duy nhất. Đặt hai unique constraints đơn cột riêng nếu nghiệp vụ thực sự cần từng cột duy nhất.

### 22.4. Quên NULL trong UNIQUE

`UNIQUE(external_ref)` mặc định cho phép nhiều NULL. Dùng `NOT NULL` hoặc `NULLS NOT DISTINCT` tùy chính sách, không chọn ngẫu nhiên.

### 22.5. Tạo index thường rồi nghĩ đã chặn trùng

`CREATE INDEX` **không phải** `CREATE UNIQUE INDEX`. Một index phục vụ lọc không tự tạo invariant uniqueness.

### 22.6. Dùng partial unique index để làm FK

Partial index không bảo đảm uniqueness trên toàn bộ bảng, nên không thể coi nó là đích FK thông thường. Dùng PK/unique key phù hợp làm định danh.

### 22.7. Không tạo index phù hợp ở phía FK

PostgreSQL không tự thêm index con khi khai báo FK. Các thao tác xóa/sửa khóa cha có thể tốn nhiều scan trên bảng con; đánh giá index ở phía tham chiếu theo workload.

### 22.8. Dùng ON CONFLICT DO NOTHING để che lỗi nghiệp vụ

Nếu khách hàng cần biết email bị chiếm, bỏ qua xung đột mà không thông báo có thể tạo trải nghiệm sai và mất dữ liệu đề xuất.

### 22.9. Giữ cả hai index trùng khóa

Constraint đã có index hỗ trợ. Chỉ thêm index khác khi có bằng chứng về predicate, covering, thứ tự key, workload hoặc yêu cầu khác.

### 22.10. Tạo unique constraint trên bảng bẩn mà không tìm duplicate

Lệnh sẽ thất bại; migration có thể gây tải và khóa trước khi báo lỗi. Kiểm tra, làm sạch và thử trước trên môi trường đại diện.

### 22.11. Coi CONCURRENTLY là hoàn toàn không tác động

`CREATE UNIQUE INDEX CONCURRENTLY` vẫn đọc bảng, ghi WAL, tiêu thụ CPU/I/O và có thể phải chờ các transaction. Nếu thất bại có thể để lại invalid index cần xử lý.

### 22.12. Gắn nhầm DEFERRABLE với upsert

Deferrable unique constraint hữu ích cho đổi thứ tự, nhưng không phù hợp làm arbiter `ON CONFLICT DO UPDATE`. Chọn semantics ràng buộc theo trường hợp ghi thực tế.

### 22.13. Quên partition key khi khai báo UNIQUE trên bảng partitioned

Một PK/unique key toàn bộ partitioned table phải đáp ứng yêu cầu có các cột partition key. Không giả định có một global unique index độc lập như một bảng heap đơn.

### 22.14. Xóa unique index vì thống kê idx_scan thấp

Index có thể được sử dụng chủ yếu để kiểm tra **uniqueness khi ghi**. Số lượt Index Scan thấp không đủ để xem nó vô dụng.

## 23. Bài tập thực hành

Sử dụng schema `constraint_lab` của phần 13. Các bài dự kiến lỗi nên được thực hiện riêng trên lab và dùng transaction/savepoint nếu cần giữ dữ liệu mẫu.

### Bài 1 — PRIMARY KEY hay UNIQUE?

Bảng `employees(employee_id, employee_code, full_name)` yêu cầu ID và mã nhân viên đều duy nhất, không NULL; `employee_id` là định danh cho API. Viết DDL và giải thích cách chọn PK/alternate key.

### Bài 2 — Khóa theo tenant

Một SKU được phép dùng lại ở tenant khác nhưng không được trùng trong cùng tenant. Viết constraint và xác định các cặp hợp lệ:

```text
(tenant=1,sku=A)
(tenant=2,sku=A)
(tenant=1,sku=B)
(tenant=1,sku=A)
```

### Bài 3 — NULL trong UNIQUE

`orders(customer_id, external_ref)` có `UNIQUE(customer_id, external_ref)`, còn `external_ref` nullable. Cặp `(1,NULL)` có thể xuất hiện hai lần không? Khi dùng `NULLS NOT DISTINCT`, hành vi thay đổi thế nào?

### Bài 4 — Partial unique index

Thiết kế bảng địa chỉ cho phép một khách có nhiều địa chỉ nhưng tối đa một địa chỉ `is_default = TRUE`. Vì sao `UNIQUE(customer_id,is_default)` không đúng? Viết index thay thế.

### Bài 5 — Email không phân biệt hoa/thường

Bảng `users(user_id,email)` có email không NULL. Viết unique expression index trên `lower(btrim(email))`. Làm sao kiểm tra duplicate trước khi tạo?

### Bài 6 — Khóa ngoại và index phía con

`authors(author_id PRIMARY KEY)` và `books(book_id PRIMARY KEY,author_id REFERENCES authors)`. PostgreSQL tự tạo những index nào? Với truy vấn thường xuyên `WHERE author_id=?`, nên cân nhắc index nào?

### Bài 7 — Đọc catalog

Viết SQL liệt kê tên constraint PK/UNIQUE và tên index hỗ trợ trong schema `constraint_lab`. Vì sao `ux_customer_one_default_address` không nằm trong danh sách `pg_constraint` PK/UNIQUE?

### Bài 8 — ON CONFLICT

Viết câu upsert `customers` theo `(tenant_id,email)`, khi đã có thì cập nhật `display_name`; trả về `customer_id`. Điều gì xảy ra với ID được đề xuất nếu conflict xảy ra với một customer hiện tại?

### Bài 9 — DEFERRABLE

Hai người ngồi ghế 1 và 2 trong cùng phiên. Cần đổi ghế bằng UPDATE mà không bị lỗi uniqueness ở trạng thái tạm thời. Thiết kế constraint nào có thể phù hợp? Vì sao nó có thể không phù hợp với `ON CONFLICT`?

### Bài 10 — Dữ liệu trùng trước migration

Bảng `legacy_customers` có 10 triệu dòng và chưa có unique key. Viết SQL tìm duplicate `(tenant_id,email)` và mô tả kế hoạch tạo unique constraint với tác động ghi được kiểm soát.

### Bài 11 — INCLUDE và uniqueness

Một unique index có khóa `(tenant_id,sku)` và `INCLUDE(product_name)`. Hai hàng cùng `(tenant_id,sku)` nhưng `product_name` khác có được tồn tại không? Vì sao?

### Bài 12 — PARTITION BY RANGE

Bảng `orders` partition theo `created_at`, ứng dụng muốn `PRIMARY KEY(order_id)` duy nhất xuyên mọi partition. Hãy giải thích hạn chế và một số phương án thiết kế cần cân nhắc.

### Bài 13 — Phân biệt kế hoạch đọc và bảo vệ ghi

Một bảng có 20 hàng, PostgreSQL chọn `Seq Scan` cho truy vấn theo PK. Có thể kết luận index PK không tồn tại hay constraint không hoạt động không? Nêu cách kiểm tra bằng catalog và bằng thao tác ghi dự kiến vi phạm.

### Bài 14 — Viết quyết định thiết kế

Một bảng có các cột `membership_id`, `project_id`, `user_id`, `deleted_at`. Yêu cầu: mỗi cặp `(project_id,user_id)` có tối đa một membership chưa xóa, nhưng được lưu nhiều membership lịch sử đã xóa. Hãy chọn PK và unique rule phù hợp; giải thích hệ quả khi khôi phục bản ghi cũ.

## 24. Gợi ý lời giải

### Bài 1

```sql
CREATE TABLE employees (
    employee_id BIGINT PRIMARY KEY,
    employee_code TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL
);
```

`employee_id` là PK theo định danh API; `employee_code` là alternate key theo quy tắc nghiệp vụ. Hai khóa đều không NULL và duy nhất.

### Bài 2

```sql
UNIQUE (tenant_id, sku)
```

Ba cặp đầu hợp lệ; cặp thứ tư trùng `(1,'A')` nên vi phạm. Có thể dùng `PRIMARY KEY (tenant_id,sku)` nếu đó là định danh chính và hai cột không NULL.

### Bài 3

Với unique mặc định, hai hàng `(1,NULL)` có thể tồn tại. Với:

```sql
UNIQUE NULLS NOT DISTINCT (customer_id, external_ref)
```

thì `(1,NULL)` chỉ được một hàng, còn `(2,NULL)` là một key khác.

### Bài 4

`UNIQUE(customer_id,is_default)` chặn cả hai địa chỉ phụ `FALSE` của cùng khách. Cần:

```sql
CREATE UNIQUE INDEX ux_one_default
ON customer_addresses(customer_id)
WHERE is_default;
```

Index này đảm bảo **tối đa một**, không phải **bắt buộc có một**.

### Bài 5

```sql
CREATE UNIQUE INDEX ux_users_email_normalized
ON users (lower(btrim(email)));
```

Kiểm tra trước:

```sql
SELECT
    lower(btrim(email)) AS normalized_email,
    COUNT(*) AS duplicates
FROM users
GROUP BY lower(btrim(email))
HAVING COUNT(*) > 1;
```

Cần xác nhận quy tắc chuẩn hóa, collation và các giá trị NULL nếu có.

### Bài 6

PostgreSQL tạo index cho `authors(author_id PRIMARY KEY)` và `books(book_id PRIMARY KEY)`, nhưng **không tự tạo** index cho `books.author_id` chỉ vì FK. Có thể thử:

```sql
CREATE INDEX ix_books_author
ON books(author_id);
```

nếu đọc sách theo tác giả hoặc thao tác trên bảng cha cho thấy cần.

### Bài 7

```sql
SELECT
    con.conrelid::regclass AS table_name,
    con.conname,
    con.conindid::regclass AS index_name,
    pg_get_constraintdef(con.oid) AS definition
FROM pg_constraint AS con
JOIN pg_namespace AS n
  ON n.oid = con.connamespace
WHERE n.nspname = 'constraint_lab'
  AND con.contype IN ('p','u');
```

Partial unique index được tạo trực tiếp, nên không tự có một `UNIQUE` constraint tương ứng trong `pg_constraint`.

### Bài 8

```sql
INSERT INTO constraint_lab.customers
    (customer_id,tenant_id,email,display_name)
VALUES
    (99,10,'an@example.com','Tên mới')
ON CONFLICT ON CONSTRAINT uq_customers_tenant_email
DO UPDATE SET display_name = EXCLUDED.display_name
RETURNING customer_id;
```

Nếu xung đột với khách hiện có, `RETURNING customer_id` trả ID của hàng thực tế được cập nhật. ID 99 của dòng định chèn không tự thay thế khóa hiện tại.

### Bài 9

```sql
UNIQUE (session_id, seat_no) DEFERRABLE INITIALLY DEFERRED
```

cho phép thao tác đổi ghế trong transaction nếu trạng thái cuối hợp lệ. Deferrable unique không phải arbiter hợp lệ cho `ON CONFLICT DO UPDATE`.

### Bài 10

```sql
SELECT tenant_id, email, COUNT(*) AS duplicate_count
FROM legacy_customers
GROUP BY tenant_id, email
HAVING COUNT(*) > 1;
```

Sau khi giải quyết duplicate và NULL theo nghiệp vụ, có thể thử `CREATE UNIQUE INDEX CONCURRENTLY` trên staging/production được kiểm soát, xác minh index valid rồi `ALTER TABLE ... ADD CONSTRAINT ... USING INDEX` nếu index phù hợp. Ghi nhận lock, WAL, I/O, lỗi và phương án rollback.

### Bài 11

Không. Uniqueness chỉ dựa trên **key columns** `(tenant_id,sku)`; included columns dùng cho dữ liệu phụ trong index, không tham gia kiểm tra trùng.

### Bài 12

PostgreSQL yêu cầu PK/UNIQUE trên partitioned parent đáp ứng yêu cầu chứa partition key. Với partition theo `created_at`, PK chỉ `order_id` không tự được hỗ trợ như một global unique key. Cần cân nhắc khóa gồm partition key, thay trục partition, hoặc cơ chế kiểm soát ID toàn cục cùng các giới hạn ràng buộc tương ứng.

### Bài 13

Không. `Seq Scan` là lựa chọn của planner cho tập dữ liệu nhỏ. Dùng `pg_constraint`, `pg_indexes`, `pg_index` để xác minh PK/index; một thử nghiệm INSERT trùng trong lab sẽ cho lỗi `23505` dù kế hoạch SELECT dùng Seq Scan.

### Bài 14

```sql
membership_id BIGINT PRIMARY KEY
```

và:

```sql
CREATE UNIQUE INDEX ux_membership_active
ON project_members(project_id,user_id)
WHERE deleted_at IS NULL;
```

Một hàng đã xóa mềm không thuộc index; khôi phục nó có thể gây xung đột nếu đã tồn tại một membership active mới cho cùng cặp.

## 25. Kết luận

`PRIMARY KEY` và `UNIQUE` xác định những bất biến cốt lõi của dữ liệu PostgreSQL. PK là khóa chính **không NULL, không trùng**; UNIQUE bảo vệ business key hoặc alternate key theo phạm vi cột và quy tắc NULL. PostgreSQL thường tạo **unique B-tree index** để thực thi các constraint này, đồng thời hỗ trợ một số truy vấn đọc, nhưng **ràng buộc đúng đắn** và **kế hoạch sử dụng index** phải được đánh giá riêng.

Khi nghiệp vụ phức tạp hơn, cần chọn đúng cơ chế:

- **`UNIQUE (tenant_id, sku)`** cho uniqueness theo phạm vi tenant.
- **`UNIQUE NULLS NOT DISTINCT`** khi NULL cũng cần được coi là trùng.
- **Expression unique index** cho khóa chuẩn hóa như `lower(email)`.
- **Partial unique index** cho những hàng active hoặc địa chỉ mặc định.
- **DEFERRABLE constraint** khi transaction cần tạm vi phạm nhưng phải đúng lúc kết thúc.
- **`ON CONFLICT`** để xử lý ghi đồng thời theo arbiter phù hợp.
- **FK và index phía bảng con** để bảo vệ tham chiếu và hỗ trợ truy cập/kiểm tra.

Phương pháp làm việc bền vững là: **xác định quy tắc nghiệp vụ → chọn khóa và semantics NULL → bảo vệ bằng constraint/index phù hợp → kiểm tra dữ liệu hiện có → triển khai an toàn → đo workload và quan sát sau thay đổi**. Một index chỉ thực sự có giá trị khi nó vừa phục vụ đúng nhu cầu, vừa giữ dữ liệu nhất quán với chi phí vận hành được chấp nhận.
