# search_path, phân giải tên và tên đối tượng đầy đủ

Trong PostgreSQL, một database có thể chứa nhiều **schema**, và trong mỗi schema có thể tồn tại bảng, view, sequence, kiểu dữ liệu, hàm hay những đối tượng khác. Vì vậy, câu lệnh `SELECT * FROM orders` chưa hoàn toàn xác định bảng nào sẽ được đọc nếu database có cả `sales.orders` và `archive.orders`.

PostgreSQL sử dụng tham số **`search_path`** để quyết định thứ tự tra cứu các schema khi một tên đối tượng **không được ghi kèm tên schema**. Cơ chế này giúp SQL ngắn và thuận tiện hơn, nhưng cũng gây ra những lỗi khó phát hiện: truy vấn nhầm bảng, tạo đối tượng ở schema không mong muốn, không tìm thấy bảng dù bảng có tồn tại, hoặc ứng dụng sử dụng nhầm hàm khi có schema không đáng tin cậy trong đường tìm kiếm.

Bài học sẽ giải thích **schema**, **phân giải tên** (*name resolution*), `search_path`, các schema đặc biệt `pg_catalog` và `pg_temp`, cách viết **tên đối tượng đầy đủ** (*schema-qualified names*), quyền `USAGE`/`CREATE`, cấu hình search path ở mức phiên/role/database, cùng các tình huống thực tế trong Java/JDBC và quản trị PostgreSQL.

> Các lệnh tạo schema/bảng, đổi `search_path` và sửa quyền trong bài chỉ dùng cho **database thử nghiệm** mà bạn được phép quản lý. Không áp dụng trực tiếp vào production khi chưa hiểu phạm vi thay đổi và các phụ thuộc của ứng dụng.

## 1. Schema là gì trong PostgreSQL?

**Schema** là một không gian tên (*namespace*) bên trong một database PostgreSQL. Các đối tượng cùng tên có thể cùng tồn tại nếu thuộc những schema khác nhau.

Ví dụ:

```text
PostgreSQL instance
└── database shopdb
    ├── schema sales
    │   ├── table orders
    │   ├── table customers
    │   └── function calculate_total(...)
    │
    ├── schema archive
    │   └── table orders
    │
    ├── schema public
    │   └── table products
    │
    └── schema pg_catalog
        ├── system views/tables
        ├── built-in functions
        └── built-in types
```

Như vậy, `sales.orders` và `archive.orders` là **hai quan hệ độc lập**, dù đều có tên cuối là `orders`. Người dùng có thể phân biệt bằng tên đầy đủ:

```sql
SELECT * FROM sales.orders;
SELECT * FROM archive.orders;
```

Một schema **không phải database khác**. Các schema trong cùng database chia sẻ một instance và có thể được truy vấn/join trực tiếp khi có quyền:

```sql
SELECT s.id, a.id
FROM sales.orders AS s
JOIN archive.orders AS a ON a.id = s.id;
```

Ví dụ câu JOIN chỉ minh họa cú pháp, giả định hai bảng và cột `id` đã tồn tại. Ngược lại, PostgreSQL **không tự hỗ trợ JOIN trực tiếp một bảng nằm ở database khác** bằng cách gõ `other_database.schema.table` như thể mọi database trong instance đều cùng không gian tên. Nhu cầu đó cần một cơ chế được thiết kế riêng, ví dụ foreign data wrapper như `postgres_fdw` hoặc kết nối ứng dụng.

### Schema thường dùng để làm gì?

- Phân nhóm các bảng theo lĩnh vực nghiệp vụ: `billing`, `sales`, `inventory`.
- Tách object của các module hoặc extension.
- Quản lý quyền truy cập cho từng nhóm object.
- Cho phép các bảng cùng tên trong các namespace khác nhau.
- Hỗ trợ một số mô hình multi-tenant hoặc quản lý phiên bản schema, nếu ứng dụng có chiến lược rõ ràng.

**Schema không phải một cơ chế cô lập bảo mật hoàn chỉnh theo mặc định.** Muốn giới hạn truy cập phải thiết lập đúng quyền trên schema và từng object, không chỉ đặt tên khác nhau hay thay `search_path`.

## 2. Hai cách viết tên đối tượng: không đầy đủ và đầy đủ

Một đối tượng được sử dụng trong SQL có thể được nhắc tới bằng:

| Cách gọi | Ví dụ | Ý nghĩa |
|---|---|---|
| **Unqualified name** | `orders` | PostgreSQL phải tìm schema theo `search_path` và ngữ cảnh câu SQL. |
| **Schema-qualified name** | `sales.orders` | Chỉ rõ schema `sales` và object `orders`. |
| **Tên hàm có schema** | `sales.calculate_total(123)` | Gọi hàm trong schema đã xác định, có thêm cơ chế lựa chọn chữ ký tham số. |
| **Tên sequence có schema** | `sales.order_id_seq` | Chỉ rõ sequence thuộc schema nào. |
| **Tên kiểu dữ liệu có schema** | `sales.order_status` | Chỉ rõ kiểu người dùng định nghĩa trong schema đó. |

Ví dụ:

```sql
-- Phụ thuộc search_path:
SELECT * FROM orders;

-- Không phụ thuộc search_path để xác định schema:
SELECT * FROM sales.orders;
```

Khi dùng tên đầy đủ, PostgreSQL vẫn kiểm tra **schema và object có tồn tại, role có đủ quyền** hay không. Tên đầy đủ không bỏ qua xác thực hay phân quyền.

### Tên đầy đủ không bắt buộc cho mọi cột

Trong truy vấn:

```sql
SELECT o.id, o.created_at
FROM sales.orders AS o
WHERE o.status = 'PAID';
```

`sales.orders` là tên quan hệ có schema. `o.id` và `o.status` là cột được phân giải qua **alias `o` của bảng trong câu truy vấn**, không phải qua `search_path`.

Vì vậy, cần phân biệt:

- **Tìm bảng/hàm/kiểu theo schema**: chịu ảnh hưởng của `search_path` khi không định danh schema.
- **Tìm cột theo alias, FROM scope và biểu thức**: chịu ảnh hưởng của phạm vi tên trong truy vấn; `search_path` không phải danh sách bảng để tìm cột.

Lỗi cột mơ hồ (`column reference ... is ambiguous`) trong một JOIN thường cần sửa bằng alias `a.id` hoặc `b.id`, không phải đổi `search_path`.

## 3. search_path là gì?

`search_path` là một tham số cấu hình PostgreSQL, có giá trị là **danh sách schema được tra cứu theo thứ tự** khi tên đối tượng chưa có schema.

Đọc giá trị hiện tại:

```sql
SHOW search_path;

SELECT current_setting('search_path') AS configured_path;
```

Một giá trị mặc định thường thấy ở PostgreSQL mới khởi tạo là:

```text
"$user", public
```

Ý nghĩa:

1. `"$user"` là ký hiệu đặc biệt tham chiếu tới **schema có tên trùng với tên role hiện tại**, nếu schema đó tồn tại và có thể được sử dụng. Nó **không** tự tạo schema.
2. `public` là schema thông thường mà nhiều database PostgreSQL có sẵn.
3. PostgreSQL còn có cơ chế tìm kiếm ngầm đối với **`pg_catalog`** và schema tạm **`pg_temp`**, nên `SHOW search_path` chưa chắc in ra toàn bộ thứ tự thực tế.

Ví dụ, role `report_user` có thể có schema `report_user`. Nếu schema tồn tại và role có quyền thích hợp, `"$user"` có thể trỏ tới schema ấy. Nếu không, PostgreSQL bỏ qua entry không dùng được và tiếp tục xét những schema hợp lệ tiếp theo.

### search_path không phải danh sách mọi schema trong database

Bạn có thể tạo `sales`, `billing` và `analytics` nhưng `SHOW search_path` vẫn là `"$user", public`. Trong trường hợp ấy:

```sql
SELECT * FROM sales.orders;
```

vẫn có thể hoạt động với quyền phù hợp, còn:

```sql
SELECT * FROM orders;
```

có thể báo không tìm thấy bảng, vì `sales` không được dùng trong quá trình tìm tên không đầy đủ.

**Đổi `search_path` không tạo hoặc xóa schema, không chuyển bảng sang schema khác và không cấp quyền truy cập.** Nó chủ yếu thay đổi cách PostgreSQL **hiểu các tên chưa được chỉ rõ schema**.

## 4. Quy tắc phân giải tên theo thứ tự search_path

Giả sử một phiên có:

```sql
SET search_path TO sales, archive, public;
```

Với tên bảng chưa chỉ schema:

```sql
SELECT * FROM orders;
```

PostgreSQL tìm theo thứ tự logic:

```text
Tên cần phân giải: orders
             │
             ▼
pg_catalog? (nếu áp dụng tìm kiếm ngầm cho loại object)
             │
             ▼
sales.orders có tồn tại và dùng được?
             ├── Có ──► chọn sales.orders
             │
             └── Không
                    │
                    ▼
archive.orders có tồn tại và dùng được?
             ├── Có ──► chọn archive.orders
             │
             └── Không
                    │
                    ▼
public.orders có tồn tại và dùng được?
             ├── Có ──► chọn public.orders
             └── Không ──► lỗi không tìm thấy relation
```

Sơ đồ lược bớt một số quy tắc đặc biệt: schema tạm `pg_temp` có thể được tìm trước các schema thông thường đối với **quan hệ và kiểu dữ liệu**, còn `pg_catalog` có vị trí ngầm hoặc tường minh riêng. Hai ngoại lệ này sẽ được giải thích ở các mục sau.

### “Schema đầu tiên thắng” chỉ là cách nói đơn giản hóa

Với các bảng cùng tên, việc chọn bảng theo **schema tìm được trước** thường rất trực quan. Nhưng với **hàm** hoặc **toán tử**, PostgreSQL còn dùng **số lượng, kiểu tham số, overload và quy tắc ép kiểu** để chọn đúng candidate.

Ví dụ, nếu có những hàm cùng tên nhưng chữ ký khác nhau trong nhiều schema, lời giải không đơn giản là “chọn bất kỳ hàm nào ở schema đầu tiên”. Phải xét cả khả năng khớp tham số và những quy tắc phân giải function của PostgreSQL.

Điều này quan trọng về **bảo mật**: đưa schema có người không tin cậy được tạo object vào `search_path` có thể ảnh hưởng cách phân giải hàm/toán tử và thay đổi ý nghĩa SQL.

## 5. Ví dụ thực hành: hai schema có bảng trùng tên

Tạo hai schema trong **database lab**:

```sql
CREATE SCHEMA IF NOT EXISTS training_sales;
CREATE SCHEMA IF NOT EXISTS training_archive;
```

Tạo mỗi schema một bảng `invoices`:

```sql
CREATE TABLE training_sales.invoices (
    id INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL
);

CREATE TABLE training_archive.invoices (
    id INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL
);

INSERT INTO training_sales.invoices(id, customer_name, amount)
VALUES
    (101, 'An', 125000),
    (102, 'Binh', 80000);

INSERT INTO training_archive.invoices(id, customer_name, amount)
VALUES
    (1, 'Cu', 50000);
```

**Đây là một ví dụ dùng trong database lab còn trống.** Nếu các bảng đã tồn tại, các lệnh `CREATE TABLE` sẽ báo lỗi; không được tùy tiện `DROP ... CASCADE` để chạy lại trên database có dữ liệu cần giữ.

### Bước 1 — Đặt schema sales trước

```sql
SET search_path TO training_sales, training_archive, public;

SHOW search_path;

SELECT id, customer_name, amount
FROM invoices
ORDER BY id;
```

Câu `SELECT` dùng tên `invoices` không đầy đủ. Nó tìm tới **`training_sales.invoices`** trước; kết quả dự kiến gồm hàng `101` và `102`.

### Bước 2 — Đảo thứ tự

```sql
SET search_path TO training_archive, training_sales, public;

SELECT id, customer_name, amount
FROM invoices
ORDER BY id;
```

Không thay đổi nội dung câu `SELECT`, nhưng giờ nó có thể trả hàng `id = 1` trong **`training_archive.invoices`**.

**Bài học:** Hai SQL text giống hệt nhau có thể đọc **hai tập dữ liệu khác nhau** khi `search_path` của connection khác nhau. Với ứng dụng tài chính, báo cáo hoặc multi-tenant, sự khác biệt âm thầm này có thể nghiêm trọng hơn lỗi “relation does not exist”.

### Bước 3 — Dùng tên đầy đủ để loại phụ thuộc

```sql
SELECT * FROM training_sales.invoices ORDER BY id;
SELECT * FROM training_archive.invoices ORDER BY id;
```

Bất kể `search_path` đang ưu tiên schema nào, hai câu trên chỉ rõ quan hệ cần đọc.

### Bước 4 — Dọn cấu hình phiên sau thí nghiệm

```sql
RESET search_path;
```

`RESET` đưa cấu hình của session về mặc định **có hiệu lực trong ngữ cảnh connection**, có thể bao gồm cài đặt từ role/database/server, chứ không nhất thiết luôn về chuỗi `"$user", public`. Lệnh này không xóa bảng hay schema.

## 6. current_schema() và current_schemas() khác SHOW search_path thế nào?

`SHOW search_path` in **giá trị cấu hình**, nhưng có thể chứa schema không tồn tại, không đủ quyền `USAGE` hoặc ký hiệu `"$user"` chưa được giải quyết.

PostgreSQL có các hàm giúp quan sát đường tìm kiếm thực tế:

```sql
SELECT
    current_schema() AS default_schema,
    current_schemas(false) AS explicit_usable_path,
    current_schemas(true) AS path_including_implicit;
```

| Biểu thức | Ý nghĩa |
|---|---|
| `SHOW search_path` | Chuỗi cài đặt của session, gồm cả entry đặc biệt/chưa tồn tại. |
| `current_setting('search_path')` | Lấy giá trị của GUC `search_path` ở dạng text để dùng trong SQL. |
| `current_schema()` | Schema hiện hành được chọn làm vị trí mặc định cho các object mới khi không chỉ schema. |
| `current_schemas(false)` | Danh sách các schema hợp lệ và có thể sử dụng trong đường tìm kiếm, không bao gồm các schema ngầm. |
| `current_schemas(true)` | Bao gồm các schema được tìm ngầm như `pg_catalog` và schema tạm đang tồn tại khi áp dụng. |

Ví dụ:

```sql
SET search_path TO schema_chua_ton_tai, training_sales, public;

SHOW search_path;

SELECT current_schema(), current_schemas(true);
```

`SHOW` vẫn có thể in `schema_chua_ton_tai`, nhưng PostgreSQL bỏ qua schema không tồn tại khi thực sự tìm object. Vì vậy `current_schema()` có thể là `training_sales` nếu schema đó hiện hữu và sử dụng được.

**Đừng nhầm hai loại kết quả.** Nếu ứng dụng log duy nhất chuỗi từ `SHOW search_path`, log đó có thể chưa phản ánh chính xác schema nào thực sự được tìm.

## 7. Tạo đối tượng mới: CREATE dùng schema nào?

`search_path` không chỉ ảnh hưởng `SELECT`. Khi tạo một số đối tượng **không ghi schema**, PostgreSQL sử dụng **schema hiện hành** được xác định từ đường tìm kiếm.

Giả sử:

```sql
SET search_path TO training_sales, training_archive, public;

SELECT current_schema();
-- Dự kiến: training_sales.

CREATE TABLE import_jobs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Vì câu `CREATE TABLE` không chỉ định schema, bảng mới thường được tạo trong **`training_sales`**, nếu role có quyền `CREATE` ở đó:

```sql
SELECT to_regclass('training_sales.import_jobs') AS created_table;
```

Nếu muốn chắc chắn schema của bảng mới, ghi đầy đủ:

```sql
CREATE TABLE training_archive.import_jobs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Đây là một bảng khác với `training_sales.import_jobs`.

### Đường tìm kiếm không tự cấp quyền CREATE

Nếu một role có `USAGE` trên `training_sales` nhưng **không có `CREATE`**, câu `CREATE TABLE import_jobs` có thể lỗi quyền dù `current_schema()` trỏ vào `training_sales`. PostgreSQL không mặc định “bỏ qua schema thiếu CREATE rồi tìm schema kế tiếp có thể ghi” cho thao tác tạo object.

Ngược lại, khi không có schema hợp lệ để tạo:

```sql
SET search_path TO schema_chua_ton_tai;

-- Có thể gây lỗi: no schema has been selected to create in.
CREATE TABLE should_not_be_created(id INTEGER);
```

Vì vậy, khi gặp lỗi tạo bảng, cần kiểm tra **`current_schema()` và quyền CREATE**, không chỉ xem bảng đã có hay chưa.

### DDL migration nên chỉ rõ schema

Một script migration dùng:

```sql
CREATE TABLE orders (...);
```

có thể tạo nhầm bảng dưới schema của role kết nối thay vì schema ứng dụng. Với quy trình migration cần độ tin cậy cao, ưu tiên:

```sql
CREATE TABLE app.orders (...);
```

Chọn một chuẩn đặt tên rõ ràng và kiểm tra schema đích trước khi triển khai; dấu `...` ở ví dụ trên là chỗ giữ nội dung cột, không phải câu SQL hoàn chỉnh.

## 8. pg_catalog: schema hệ thống luôn đáng chú ý

`pg_catalog` chứa nhiều bảng/view hệ thống, hàm và kiểu dữ liệu built-in của PostgreSQL. PostgreSQL tự đưa `pg_catalog` vào đường tra cứu khi cần.

Quy tắc quan trọng:

- Nếu **không liệt kê `pg_catalog`** trong `search_path`, nó thường được **tìm trước** các schema được liệt kê tường minh đối với các đối tượng thuộc loại thích hợp.
- Nếu **liệt kê `pg_catalog` tường minh**, nó được tìm **theo đúng vị trí** bạn đặt trong đường tìm kiếm.

Ví dụ:

```sql
SET search_path TO training_sales, public;

SELECT current_schemas(true);
```

Bạn có thể thấy `pg_catalog` xuất hiện dù `SHOW search_path` không in nó.

Nếu cần thứ tự tường minh và dễ kiểm soát:

```sql
SET search_path TO pg_catalog, training_sales, public;
```

**Không nên đặt schema có người không tin cậy được tạo hàm trước `pg_catalog` trong cấu hình thực thi mã có đặc quyền.** Một số trường hợp hàm hoặc toán tử cùng tên có thể dẫn đến hành vi không như dự kiến, nhất là khi có overload và ép kiểu tham số.

### Một ví dụ về đối tượng hệ thống

```sql
SELECT oid, relname
FROM pg_catalog.pg_class
WHERE relname = 'invoices';
```

Đây là cách dùng **tên đầy đủ `pg_catalog.pg_class`** để chỉ định rõ catalog relation, không phụ thuộc search path cho tên bảng hệ thống. Các cột `oid` và `relname` nằm trong phạm vi bảng đã chọn.

## 9. pg_temp: tại sao bảng tạm có thể “che” bảng thường?

Khi một session tạo **temporary table**, PostgreSQL dùng một schema tạm gắn với phiên, có thể được tham chiếu bằng alias đặc biệt **`pg_temp`**.

Điều quan trọng:

- Nếu schema tạm đang tồn tại và **`pg_temp` không được đặt tường minh** trong search path, PostgreSQL có thể tìm schema tạm **trước** những schema thông thường khi phân giải **quan hệ và tên kiểu dữ liệu**.
- Schema tạm **không được tra cứu ngầm cho tên hàm và toán tử**.
- Bảng tạm thường thuộc riêng session; session khác không mặc nhiên nhìn thấy bảng tạm của bạn qua tên `pg_temp` trong connection của họ.

Ví dụ trên một session lab:

```sql
SET search_path TO training_sales, public;

CREATE TEMP TABLE invoices (
    source_note TEXT NOT NULL
);

INSERT INTO invoices(source_note)
VALUES ('Du lieu tam cua session');

-- Do temp schema co uu tien doi voi relation,
-- ten invoices khong ghi schema co the tro den bang tam.
SELECT * FROM invoices;

-- Vẫn chỉ rõ bảng thường khi cần:
SELECT * FROM training_sales.invoices;

-- Chỉ rõ bảng tạm:
SELECT * FROM pg_temp.invoices;
```

Sau `CREATE TEMP TABLE`, câu `SELECT * FROM invoices` có thể trả cột `source_note` thay vì các cột `id`, `customer_name`, `amount` từ bảng thường. Nếu ứng dụng tưởng `invoices` luôn là bảng thường, kết quả sẽ gây bất ngờ.

### Khi nào nên đặt pg_temp ở cuối?

Trong những ngữ cảnh nhạy cảm về bảo mật, đặc biệt **`SECURITY DEFINER` function**, có thể đặt `pg_temp` ở **cuối search path** để tránh đối tượng tạm được ưu tiên quá mức:

```sql
SET search_path TO pg_catalog, training_sales, pg_temp;
```

Đây là một thành phần trong thiết kế search path an toàn, không phải giải pháp duy nhất. **Định danh đầy đủ tên bảng/hàm và hạn chế quyền CREATE ở schema được tin cậy** vẫn rất cần thiết.

Sau khi dùng xong ví dụ bảng tạm:

```sql
DROP TABLE IF EXISTS pg_temp.invoices;
RESET search_path;
```

Chỉ chạy lệnh `DROP` trên session lab đã tạo bảng tạm đó; không sao chép dọn dẹp vào kết nối ứng dụng có công việc khác đang chạy.

## 10. Quyền USAGE và CREATE trên schema

`search_path` quyết định **nơi PostgreSQL tìm tên**, còn quyền quyết định **role có được truy cập và thao tác đối tượng hay không**.

Hai quyền schema quan trọng:

| Quyền trên schema | Ý nghĩa |
|---|---|
| **USAGE** | Cho phép tra cứu/truy cập các đối tượng bên trong schema theo những quy tắc quyền áp dụng. |
| **CREATE** | Cho phép tạo một số đối tượng trong schema, theo ngữ nghĩa và ràng buộc của PostgreSQL. |

**USAGE trên schema không tự động cấp SELECT mọi bảng.** Muốn đọc `training_sales.invoices` còn cần quyền `SELECT` trên bảng hoặc cơ chế cấp quyền phù hợp.

Ví dụ minh họa trên database lab, thực hiện bằng role được phép quản trị:

```sql
-- Cấp khả năng sử dụng tên bên trong schema.
GRANT USAGE ON SCHEMA training_sales TO reporting_role;

-- Cấp quyền đọc một bảng cụ thể.
GRANT SELECT ON TABLE training_sales.invoices TO reporting_role;
```

Những lệnh trên giả định `reporting_role` đã tồn tại. Không nên cấp `CREATE` trên schema nghiệp vụ cho mọi tài khoản chỉ đọc chỉ để họ tránh lỗi `relation does not exist`.

### Kiểm tra quyền hiện có

```sql
SELECT
    current_user AS current_role,
    has_schema_privilege(current_user, 'training_sales', 'USAGE')
        AS can_use_schema,
    has_schema_privilege(current_user, 'training_sales', 'CREATE')
        AS can_create_in_schema;
```

Khi schema đã tồn tại nhưng role không có `USAGE`, PostgreSQL có thể **bỏ qua schema đó** khi phân giải tên thông qua `search_path`. Một tên đầy đủ như `training_sales.invoices` lại có thể báo **permission denied for schema training_sales**. Đây là lý do hai câu `SELECT` cùng nhắm bảng nghiệp vụ có thể cho thông báo lỗi khác nhau.

### Không coi public là schema luôn có quyền CREATE cho mọi người

Quyền mặc định trên schema `public` đã thay đổi ở các phiên bản PostgreSQL: từ PostgreSQL 15, trong database mới, quyền `CREATE` trên `public` không mặc định được cấp rộng rãi cho mọi role như ở nhiều phiên bản cũ. Database được nâng cấp hoặc có quyền tùy chỉnh vẫn có thể giữ thiết lập khác.

Khi đánh giá bảo mật, **kiểm tra ACL thực tế**, không suy luận từ tên `public` hoặc số phiên bản:

```sql
SELECT
    has_schema_privilege('public', 'USAGE')  AS public_usage,
    has_schema_privilege('public', 'CREATE') AS public_create;
```

Ví dụ này kiểm tra quyền của **role hiện tại**. Các quyết định `GRANT`/`REVOKE` cần xem object owner, các role khác, extension và chính sách triển khai của dự án.

## 11. search_path theo SESSION, ROLE và DATABASE

Một session PostgreSQL có thể nhận giá trị `search_path` từ nhiều tầng cấu hình. Hiểu phạm vi thay đổi giúp tránh ngạc nhiên khi một client có path khác client khác.

### 11.1. SET search_path trong một connection

```sql
SET search_path TO training_sales, public;

SELECT current_schema(), current_schemas(true);
```

Lệnh này thay đổi **session hiện tại**, không tự thay đổi session của ứng dụng khác. Kết nối đóng rồi mở lại có thể nhận cấu hình từ role, database hoặc server thay vì giá trị vừa SET.

Kết thúc phép thử:

```sql
RESET search_path;
```

### 11.2. ALTER ROLE ... SET

Người quản trị có quyền thích hợp có thể đặt giá trị mặc định cho các **session mới của một role**:

```sql
ALTER ROLE app_user
SET search_path TO training_sales, public;
```

Lệnh tác động đến cấu hình mặc định cho những lần đăng nhập phù hợp **sau đó**; không tự áp dụng ngay cho các connection đã mở trong pool.

### 11.3. ALTER DATABASE ... SET

Đặt cấu hình mặc định cho session mới kết nối vào một database:

```sql
ALTER DATABASE appdb
SET search_path TO training_sales, public;
```

Role khác nhau khi kết nối vào `appdb` có thể bị ảnh hưởng, trừ khi có cấu hình ưu tiên cao hơn. Cần cân nhắc tác động tới nhiều ứng dụng dùng chung database.

### 11.4. ALTER ROLE ... IN DATABASE ... SET

Khi chỉ muốn tác động tới **một role trong một database**:

```sql
ALTER ROLE app_user IN DATABASE appdb
SET search_path TO training_sales, public;
```

Đây thường là phạm vi thích hợp hơn khi cùng role đăng nhập nhiều database, hoặc database có nhiều ứng dụng dùng role khác nhau.

### Bảng so sánh phạm vi

| Cách cấu hình | Phạm vi | Connection đang mở có tự đổi không? |
|---|---|---|
| `SET search_path` | Session hiện tại. | Chính session ra lệnh thay đổi. |
| `ALTER ROLE ... SET` | Mặc định cho session mới của role. | Không. |
| `ALTER DATABASE ... SET` | Mặc định cho session mới vào database. | Không. |
| `ALTER ROLE ... IN DATABASE ... SET` | Mặc định cho tổ hợp role và database. | Không. |
| Cấu hình server/startup | Mặc định chung nếu không bị các tầng khác ghi đè. | Không tự thay đổi session đã khởi tạo. |

Trong các nguồn mặc định role/database, thiết lập **role trong database** có ưu tiên cao hơn các thiết lập chung của role hoặc database. Một `SET` explicit ở session có thể ghi đè mặc định của session đó.

**Lưu ý:** `ALTER ROLE ... SET` chỉ được nạp vào session khi role đăng nhập theo cơ chế hỗ trợ, không phải cứ dùng `SET ROLE` giữa một session thì mọi thiết lập startup của role mới đều tự được chạy lại.

## 12. SET LOCAL search_path cho một transaction

Đôi khi một tác vụ cần dùng schema riêng nhưng không muốn thay đổi lâu dài connection được tái sử dụng. PostgreSQL hỗ trợ **`SET LOCAL`** trong transaction:

```sql
BEGIN;

SET LOCAL search_path TO training_sales, public;

SELECT * FROM invoices ORDER BY id;

COMMIT;
```

Giá trị được đặt bằng `SET LOCAL` thường chỉ có hiệu lực tới cuối transaction đó; sau `COMMIT` hoặc `ROLLBACK`, session trở lại giá trị phù hợp trước khi `SET LOCAL` tác động.

| Lệnh | Vòng đời |
|---|---|
| `SET search_path TO ...` | Thay đổi session, có thể tồn tại qua nhiều transaction. |
| `SET LOCAL search_path TO ...` | Thay đổi trong phạm vi transaction đang thực thi. |
| `RESET search_path` | Trả tham số về cấu hình mặc định có hiệu lực của session. |

Không coi `SET LOCAL` ngoài một transaction block là cách tạo cấu hình tạm cho request. Lệnh này được thiết kế để áp dụng trong transaction; ngoài phạm vi thích hợp, PostgreSQL có thể đưa ra cảnh báo/không tạo tác động như bạn kỳ vọng.

### Vì sao SET LOCAL hữu ích cho ứng dụng?

Trong connection pool, một physical connection có thể phục vụ nhiều request:

```text
Connection #7
  ├── Request A: SET search_path = tenant_a
  ├── Trả connection về pool
  └── Request B: SELECT * FROM orders
                    ▲
                    └── có nguy cơ đọc nhầm tenant_a
```

Nếu cần đổi path theo transaction, `SET LOCAL` giúp giới hạn thời gian tác động. Tuy nhiên, nó **không thay thế kiểm soát quyền giữa các tenant**, bảo vệ identifier, ranh giới transaction, hoặc cơ chế reset connection của pool.

## 13. JDBC, Spring và connection pool

### 13.1. Mỗi connection có session state riêng

Ứng dụng Java thường dùng HikariCP hoặc pool tương tự. Một pool giữ nhiều **physical connections**, mỗi connection có `search_path` của riêng nó.

Giả sử:

```text
Connection A: search_path = training_sales, public
Connection B: search_path = training_archive, public

SQL giống hệt:
    SELECT * FROM invoices;

Connection A → training_sales.invoices
Connection B → training_archive.invoices
```

Đây là lý do nhiều lỗi “truy vấn lúc đúng lúc sai” có thể xảy ra khi path bị thay đổi rải rác qua request.

### 13.2. Thiết lập schema mặc định khi kết nối

pgJDBC hỗ trợ tham số kết nối **`currentSchema`** để xác định search path cho connection. Ví dụ **chuỗi kết nối lab**:

```properties
spring.datasource.url=jdbc:postgresql://127.0.0.1:5432/appdb?currentSchema=training_sales,public
```

Ý nghĩa: driver có thể thiết lập search path phù hợp khi tạo kết nối. Không đưa thông tin đăng nhập nhạy cảm vào URL hoặc commit secrets vào repository.

Một cách khác là cấu hình SQL khởi tạo connection của pool, theo phiên bản HikariCP/Spring hỗ trợ:

```yaml
spring:
  datasource:
    hikari:
      connection-init-sql: "SET search_path TO training_sales, public"
```

Cấu hình khởi tạo chỉ áp dụng khi **physical connection mới được tạo**, không có nghĩa mọi kết nối cũ tự được điều chỉnh sau khi thay đổi file cấu hình. Hãy xác định **một nguồn cấu hình chính** để tránh driver, pool và SQL nghiệp vụ ghi đè lẫn nhau.

### 13.3. JDBC setSchema

JDBC có API:

```java
connection.setSchema("training_sales");
```

Trong pgJDBC, hành vi liên quan đến schema/search path cần được hiểu theo đúng driver và phiên bản. API này hữu ích khi ứng dụng **quản lý một connection riêng**, nhưng không nên giả định mọi pool đều có thể tự khôi phục tất cả thay đổi schema nếu code gọi lệnh SQL `SET search_path` trực tiếp.

### 13.4. Rò rỉ trạng thái search_path trong pool

Ví dụ nguy hiểm:

```java
try (Connection connection = dataSource.getConnection();
     Statement statement = connection.createStatement()) {

    statement.execute("SET search_path TO training_archive, public");

    // Làm một vài truy vấn...
}
```

Đóng logical connection trong code trên thường có nghĩa **trả physical connection về pool**, không nhất thiết phá connection PostgreSQL. Nếu pool không biết hoặc không reset session GUC đã bị sửa bằng SQL, request sau có thể thừa hưởng path này.

Chiến lược giảm rủi ro:

1. Nếu có thể, **viết tên schema đầy đủ** trong SQL nghiệp vụ quan trọng.
2. Với một schema cố định cho cả ứng dụng, cấu hình nhất quán khi connection được tạo.
3. Khi cần thay đổi theo transaction, dùng `SET LOCAL` và quản lý transaction tường minh.
4. Dùng cơ chế multi-tenant được thiết kế rõ, không tự nối tên tenant trực tiếp từ request vào SQL.
5. Kiểm tra path **trên chính connection ứng dụng** khi điều tra lỗi, không chỉ từ cửa sổ `psql` của DBA.

## 14. Tên có dấu nháy kép và quy tắc chữ hoa/chữ thường

PostgreSQL chuyển **identifier không đặt trong dấu nháy kép** thành chữ thường khi phân tích SQL:

```sql
-- Hai cách này cùng chỉ tên đơn giản ở dạng lowercase.
SELECT * FROM Training_Sales.Invoices;
SELECT * FROM training_sales.invoices;
```

Nhưng identifier trong dấu nháy kép giữ nguyên kiểu chữ:

```sql
CREATE SCHEMA "SalesArea";

CREATE TABLE "SalesArea"."Orders" (
    "OrderID" BIGINT PRIMARY KEY,
    amount NUMERIC(12, 2)
);

SELECT "OrderID", amount
FROM "SalesArea"."Orders";
```

Với schema và bảng trên, câu:

```sql
SELECT * FROM salesarea.orders;
```

**không** tự trỏ tới `"SalesArea"."Orders"` vì tên đã được đặt trong dấu nháy kép và có phân biệt chữ hoa/chữ thường.

### Dấu nháy kép khác dấu nháy đơn

| Cú pháp | Ý nghĩa |
|---|---|
| `"SalesArea"` | Identifier tên schema có chữ hoa được giữ nguyên. |
| `'SalesArea'` | String literal, không phải cú pháp định danh schema trong `FROM`. |
| `training_sales.invoices` | Hai identifier không quote, được chuẩn hóa lowercase. |
| `"odd.schema"."table.name"` | Dấu chấm **nằm trong identifier** nếu được quote; không phải dấu phân cách phần tên. |

Đặt tên schema/table bằng chữ thường với dấu gạch dưới thường giúp SQL, migration và driver dễ quản lý hơn. Nếu đã dùng mixed-case identifiers, hãy nhất quán về dấu nháy kép.

### search_path với tên schema cần quote

```sql
SET search_path TO "SalesArea", public;

SHOW search_path;
```

Lệnh đặt đường tìm kiếm cho schema tên đúng `SalesArea`. Nếu vô tình viết `salesarea` không quote, PostgreSQL sẽ tìm schema chữ thường khác.

## 15. Metadata: xác định tên bảng thực sự được phân giải tới đâu

Đôi khi `SELECT * FROM invoices` chạy thành công nhưng bạn nghi ngờ đọc sai schema. PostgreSQL có những cách kiểm tra **OID và visibility** của quan hệ.

### 15.1. to_regclass()

`to_regclass(text)` phân giải tên quan hệ thành OID dạng `regclass` khi tìm thấy; nếu không tìm thấy, thường trả `NULL` thay vì báo lỗi không tồn tại.

```sql
SET search_path TO training_archive, training_sales, public;

SELECT
    to_regclass('invoices') AS resolved_unqualified,
    to_regclass('training_sales.invoices') AS sales_relation,
    to_regclass('training_archive.invoices') AS archive_relation;
```

Giá trị kiểu `regclass` có thể **hiển thị tên ngắn hoặc tên đầy đủ** tùy khả năng nhìn thấy của quan hệ qua search path. Nếu cần giá trị định danh ổn định hơn, lấy OID và join catalog.

### 15.2. Join pg_class với pg_namespace

```sql
SELECT
    c.oid,
    n.nspname AS schema_name,
    c.relname AS relation_name,
    c.relkind
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.oid = to_regclass('invoices');
```

Kết quả cho biết **schema thật của relation được phân giải trong phiên hiện tại**. Trong catalog, cùng `relname='invoices'` có thể có nhiều OID khác nhau ở các `relnamespace` khác nhau.

### 15.3. pg_table_is_visible()

```sql
SELECT
    pg_catalog.pg_table_is_visible(
        'training_sales.invoices'::regclass
    ) AS sales_is_visible,
    pg_catalog.pg_table_is_visible(
        'training_archive.invoices'::regclass
    ) AS archive_is_visible;
```

Một relation được xem là visible nếu nó có thể được tham chiếu chỉ bằng tên không đầy đủ trong ngữ cảnh hiện tại theo cơ chế phân giải. Nếu cả hai bảng cùng tên, schema đứng trước có thể che schema đứng sau.

### 15.4. Tìm mọi relation cùng tên

```sql
SELECT
    n.nspname AS schema_name,
    c.relname,
    c.relkind
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.relname = 'invoices'
ORDER BY n.nspname;
```

Truy vấn này có thể hiển thị relation trong nhiều schema, kể cả những schema không thuộc `search_path` hiện tại, tùy quyền đọc metadata. Để phân biệt table, view, materialized view và loại relation khác, xem `relkind` và tài liệu catalog của PostgreSQL.

## 16. Công cụ psql để xem schema và quan hệ

`psql` hỗ trợ những **meta-command** hữu ích:

```text
\dn
\dt
\dt *.*
\d training_sales.invoices
\d training_archive.invoices
```

Ý nghĩa thông thường:

- `\dn`: liệt kê schema.
- `\dt`: liệt kê các bảng theo quy tắc pattern/visibility của `psql`.
- `\dt *.*`: mở rộng phạm vi xem bảng thuộc nhiều schema.
- `\d training_sales.invoices`: xem cấu trúc bảng chỉ định bằng tên đầy đủ.

Đây là **lệnh riêng của `psql`**, không phải SQL gửi qua JDBC. Không đưa `\dn` hoặc `\dt` nguyên văn vào `PreparedStatement`.

### Đọc schema hiện tại bằng SQL

```sql
SELECT current_database() AS database_name,
       current_user AS role_name,
       current_schema() AS current_schema_name;

SHOW search_path;
```

Ba thông tin **database, role, search path** rất quan trọng khi điều tra hai ứng dụng cùng truy vấn PostgreSQL mà kết quả khác nhau.

## 17. Tên hàm, kiểu và toán tử cũng liên quan search_path

Tập trung vào bảng là chưa đủ. PostgreSQL sử dụng namespace cho nhiều loại object khác, nhưng quy tắc phân giải **không giống nhau hoàn toàn**.

### Hàm trong schema

Ví dụ:

```sql
CREATE FUNCTION training_sales.apply_tax(p_amount NUMERIC)
RETURNS NUMERIC
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT p_amount * 1.1
$$;

-- Tên đầy đủ:
SELECT training_sales.apply_tax(100);
```

Nếu gọi:

```sql
SELECT apply_tax(100);
```

PostgreSQL cần chọn schema và chữ ký hàm phù hợp với kiểu tham số, thông qua `search_path` và quy tắc function resolution.

### Overloading có thể khiến kết quả không hiển nhiên

PostgreSQL hỗ trợ **nhiều hàm cùng tên nhưng khác danh sách kiểu tham số**. Khi truyền literal chưa xác định kiểu hoặc có ép kiểu ngầm, bộ phân giải cân nhắc các ứng viên; thứ tự schema là một phần của quá trình, không phải toàn bộ.

Vì thế, nếu cần hành vi ổn định:

- Gọi hàm bằng **`schema.function_name(...)`** khi có rủi ro đụng tên.
- Dùng kiểu tham số rõ ràng khi overload quan trọng.
- Không thêm schema không đáng tin cậy vào search path của chương trình chạy có quyền cao.

### Kiểu dữ liệu người dùng định nghĩa

```sql
CREATE TYPE training_sales.invoice_state AS ENUM (
    'DRAFT',
    'ISSUED',
    'PAID'
);

CREATE TABLE training_sales.invoice_state_log (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    state training_sales.invoice_state NOT NULL
);
```

Tên kiểu đầy đủ tránh phụ thuộc search path khi có kiểu trùng tên ở schema khác.

### Toán tử có schema

PostgreSQL cũng cho phép schema-qualify toán tử qua cú pháp đặc biệt `OPERATOR(schema.operator)` khi cần. Ví dụ về cú pháp:

```sql
SELECT 1 OPERATOR(pg_catalog.+) 2;
```

Không thể giả định viết `schema.+` hoạt động như tên bảng: **toán tử có cú pháp phân giải riêng**.

## 18. search_path và bảo mật: vì sao cần tin cậy schema trong đường tìm kiếm?

Khi PostgreSQL tìm các tên không đầy đủ, nó phải xét object nằm trong các schema của `search_path`. Nếu một schema cho phép role **không đáng tin cậy** tạo object, role đó có thể tạo đối tượng cùng tên hoặc chữ ký gây ảnh hưởng tới câu SQL của người dùng khác.

Rủi ro tăng mạnh khi một hàm **`SECURITY DEFINER`** chạy với quyền của owner nhưng sử dụng tên object chưa đủ schema. Khi đó đường tìm kiếm do người gọi hoặc môi trường cung cấp có thể làm function định danh nhầm object.

### Minh họa tình huống nguy hiểm

Giả sử một function có quyền cao chạy:

```sql
-- Ví dụ mô tả thiết kế không an toàn, không phải code
-- nên triển khai thực tế.
SELECT COUNT(*) FROM accounts;
```

Nếu `accounts` không có schema rõ ràng và search path ưu tiên một schema do bên khác được tạo object, tên có thể được phân giải tới object không mong muốn. Với function, type hoặc operator, việc chèn đối tượng cùng tên còn có thể làm thay đổi logic theo các quy tắc chọn candidate.

### Cách viết SECURITY DEFINER thận trọng hơn

Trong schema có owner được tin cậy:

```sql
-- Giả định schema security_admin và bảng accounts được
-- quản lý bởi chủ sở hữu đáng tin cậy, quyền đã được rà soát.
CREATE FUNCTION security_admin.account_count()
RETURNS BIGINT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, security_admin, pg_temp
AS $$
DECLARE
    v_count BIGINT;
BEGIN
    SELECT COUNT(*) INTO v_count
    FROM security_admin.accounts;

    RETURN v_count;
END;
$$;
```

Đây là **mẫu thiết kế có điều kiện**: schema `security_admin` và bảng `accounts` phải tồn tại, owner và quyền `EXECUTE` phải được kiểm soát. Cách làm thể hiện một số nguyên tắc:

1. Search path của function được **đặt tường minh**.
2. `pg_catalog` được ưu tiên cho built-in object.
3. Chỉ dùng các schema **đáng tin cậy** trong đường tìm kiếm.
4. `pg_temp` được đưa về cuối thay vì để tìm trước các bảng của schema tin cậy.
5. Bảng quan trọng dùng tên **`security_admin.accounts`** rõ ràng.
6. Quyền tạo object trong schema và quyền thực thi function cần được kiểm soát.

**Không nghĩ chỉ cần thêm `SET search_path` là function tự an toàn.** Nếu schema được liệt kê cho phép một attacker tạo hàm/kiểu/toán tử, hoặc function thực thi dynamic SQL không được quote đúng, rủi ro vẫn còn.

### Cần xem quyền public thực tế

Trong những database cũ hoặc có ACL thay đổi, `public` có thể cho phép nhiều role tạo object. Khi security-sensitive function dùng `public` trong search path, cần xem xét rủi ro tên bị che.

Trên PostgreSQL 15+ với database mới, mặc định đã hạn chế quyền CREATE trên `public` hơn nhiều bản cũ; **đừng suy đoán từ version mà bỏ qua kiểm tra ACL**. Việc `REVOKE CREATE` trên production có thể ảnh hưởng các ứng dụng và extension hiện hữu, nên cần có kế hoạch migration và quyền thay thế phù hợp.

## 19. Multi-tenant theo schema: lợi ích và rủi ro

Một mô hình multi-tenant có thể dùng:

```text
database appdb
├── tenant_alpha
│   ├── orders
│   └── customers
├── tenant_beta
│   ├── orders
│   └── customers
└── shared
    └── product_catalog
```

Ứng dụng có thể đổi `search_path` theo tenant để dùng cùng SQL:

```sql
SET search_path TO tenant_alpha, shared, pg_catalog;

SELECT * FROM orders;
```

Nhưng mô hình này đòi hỏi **thiết kế chặt**:

- Tenant phải được **xác thực và ánh xạ** tới schema được phép, không lấy trực tiếp từ chuỗi request.
- Đường tìm kiếm phải được đặt theo đúng **transaction hoặc connection** và không rò rỉ sang request khác.
- Role truy cập cần quyền phù hợp; nếu mọi tenant đều được cấp quyền vào mọi schema, `search_path` **không phải hàng rào bảo mật**.
- Migration phải được áp dụng cho schema tương ứng và quản lý version.
- Query quan trọng cần tránh tham chiếu object ngoài tenant một cách không mong muốn.
- Hàm `SECURITY DEFINER` và dynamic SQL phải được rà soát riêng.

### Không nối tên schema từ input không đáng tin cậy

Mẫu nguy hiểm:

```java
// Không an toàn: không ghép tên schema từ request tùy ý.
String sql = "SET search_path TO " + tenantFromRequest;
statement.execute(sql);
```

Tên schema là **SQL identifier**, không thể dùng placeholder giá trị theo kiểu `SELECT ... WHERE id = ?` để thay thế trực tiếp mọi vị trí identifier trong SQL. Cần tra tenant trong **danh sách/schema mapping được cho phép** rồi dùng cách quote identifier hợp lệ.

Trong PL/pgSQL, nếu thật sự phải dựng SQL động dựa trên tên schema **đã được xác thực**, có thể dùng `format('%I', identifier)` để quote tên định danh, thay vì nối chuỗi tùy tiện:

```sql
-- Minh họa cách quote identifier của PostgreSQL.
SELECT format('%I.%I', 'tenant_alpha', 'orders')
       AS qualified_relation_name;
```

`format('%I', ...)` bảo vệ cú pháp identifier, **không tự kiểm tra role có quyền truy cập hay tenant hợp lệ**. Validation quyền và mapping tenant là trách nhiệm riêng của ứng dụng.

### Một thiết kế khác: tên đầy đủ hoặc tách role

Trong nhiều ứng dụng, truyền `schema.table` tường minh (với schema đã được whitelist) hoặc dùng role/connection riêng phù hợp có thể giảm rủi ro session leakage. Đổi lại, cần quản lý SQL và quyền kỹ lưỡng. Không có một cách duy nhất phù hợp mọi mô hình tenancy.

## 20. search_path và object đã được phân giải ở thời điểm trước

Khi PostgreSQL xử lý SQL, việc phân giải tên xảy ra trong những giai đoạn như parse analysis, planning hoặc thực thi tùy loại object/cơ chế.

### View và object dependency

Một view được tạo bằng:

```sql
SET search_path TO training_sales, public;

CREATE VIEW training_sales.invoice_ids AS
SELECT id FROM invoices;
```

Khi định nghĩa view, PostgreSQL xác định **object nguồn thực tế** và ghi nhận dependency tương ứng. Sau đó, đổi `search_path` của người truy vấn view **không mặc nhiên chuyển** nguồn của view từ `training_sales.invoices` sang `training_archive.invoices`.

Vì thế, khi thay đổi search path sau migration, cần phân biệt:

- SQL được gửi mới có tên không đầy đủ: có thể phân giải theo path mới.
- View/constraint/đối tượng đã lưu phụ thuộc vào OID của object: không tự chuyển thành phụ thuộc tới object cùng tên ở schema khác.
- Function chứa SQL (đặc biệt PL/pgSQL hoặc dynamic SQL): ngữ cảnh phân giải và thời điểm chuẩn bị câu lệnh cần được xem riêng, không áp dụng quy tắc duy nhất cho mọi function.

### Prepared statements và cache

Ứng dụng có thể dùng prepared statements hoặc server-side plan cache. Tên relation có thể được phân giải khi parse/prepare; PostgreSQL cũng có cơ chế re-parse/re-plan trong những tình huống như thay đổi `search_path` giữa các lần dùng. **Không nên dựa vào plan cache để giữ hoặc tự chuyển schema theo ý muốn**.

Nếu một ứng dụng thay `search_path` theo request, test cần bao phủ cả **prepared statements, connection pool, transaction và các schema trùng tên**. Giải pháp đơn giản hơn thường là tránh dùng path động tùy tiện cho các câu SQL cần tính xác định cao.

### Sequence và regclass

PostgreSQL có kiểu đặc biệt `regclass` biểu diễn OID của relation/sequence. Ví dụ:

```sql
SELECT to_regclass('training_sales.invoices');
```

Trong các biểu thức như `nextval('schema.sequence_name'::regclass)`, tên có thể được chuyển thành OID ở giai đoạn sớm theo cơ chế `regclass`, nên không thể giả định đổi `search_path` sẽ khiến mọi tham chiếu sequence đã lưu đổi sang sequence trùng tên ở schema khác.

Khi thiết kế migration, cần hiểu **định danh tên ở runtime** khác với **dependency đã lưu theo OID**.

## 21. Những lỗi thường gặp và cách chẩn đoán

### 21.1. relation does not exist — SQLSTATE 42P01

Ví dụ:

```sql
SELECT * FROM invoices;
```

Nếu bảng thật nằm ở `training_sales.invoices` nhưng schema đó không nằm trong path, PostgreSQL báo relation không tồn tại đối với **tên chưa đủ schema**.

Cách kiểm tra:

```sql
SHOW search_path;
SELECT current_schema(), current_schemas(true);
SELECT to_regclass('training_sales.invoices');
SELECT to_regclass('invoices');
```

Nếu tên đầy đủ tìm thấy nhưng tên ngắn không thấy, đây là dấu hiệu cần xem search path/privileges hơn là kết luận dữ liệu đã mất.

### 21.2. permission denied for schema hoặc table

Một tên đầy đủ có thể báo thiếu quyền schema `USAGE`; hoặc đã tìm được bảng nhưng thiếu quyền `SELECT`, `INSERT` hay `UPDATE` trên bảng.

Đọc thêm:

```sql
SELECT
    has_schema_privilege('training_sales', 'USAGE')
        AS schema_usage,
    has_schema_privilege('training_sales', 'CREATE')
        AS schema_create;
```

Nếu cần kiểm tra quyền bảng:

```sql
SELECT has_table_privilege(
    'training_sales.invoices',
    'SELECT'
) AS may_select_invoices;
```

Chỉ cấp **quyền tối thiểu cần thiết**, không giải quyết mọi lỗi bằng cách biến tài khoản ứng dụng thành superuser.

### 21.3. Không thấy bảng sau CREATE TABLE

Có thể DDL đã tạo bảng ở schema khác vì `search_path` của connection migration không giống dự kiến.

Kiểm tra:

```sql
SELECT current_schema(), current_schemas(true);

SELECT n.nspname, c.relname
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.relname = 'import_jobs';
```

Không tự tạo lại một bảng trùng nội dung trước khi xác định object cũ đang ở schema nào và có dữ liệu gì.

### 21.4. Cùng SQL nhưng trả số hàng khác giữa hai kết nối

Hãy kiểm tra:

```sql
SELECT
    current_database(),
    session_user,
    current_user,
    current_schema(),
    current_schemas(true);
```

Khác role, search path hoặc database có thể khiến SQL không đầy đủ trỏ tới dữ liệu khác. Nếu ứng dụng có pool, lấy thông tin **từ đúng connection thực hiện truy vấn**, kèm connection/request ID phù hợp.

### 21.5. Hàm bị gọi sai hoặc ambiguous function

Cùng tên hàm trong nhiều schema, có overload và tham số kiểu không rõ ràng có thể khiến PostgreSQL chọn candidate khác hoặc báo ambiguous function.

Giải pháp thường là **ghi schema cho hàm** và **ép kiểu tham số tường minh** khi phù hợp, đồng thời rà soát schema không đáng tin cậy xuất hiện trong search path.

### 21.6. Bảng tạm che bảng thường

Nếu session đã tạo `CREATE TEMP TABLE invoices`, tên `invoices` có thể phân giải tới temp schema. Kiểm tra `current_schemas(true)` và `to_regclass('invoices')`, rồi dùng `training_sales.invoices` nếu muốn bảng thường.

### 21.7. Thay ALTER ROLE nhưng ứng dụng chưa đổi

`ALTER ROLE ... SET search_path` ảnh hưởng session **mở mới**. Pool còn giữ physical connections cũ có thể tiếp tục dùng giá trị ban đầu hoặc giá trị do ứng dụng đã đặt.

Để đồng nhất, cần kế hoạch tái tạo kết nối hoặc thiết lập session baseline, không chỉ thay metadata của role.

### 21.8. Migration chạy được ở developer nhưng lỗi trên CI

Khác database role, schema, quyền, cấu hình `search_path` hoặc startup SQL có thể dẫn đến lỗi “table not found”/“permission denied”.

Cần log tối thiểu `current_database()`, `current_user`, `current_schemas(true)` và revision migration; ưu tiên DDL có schema đầy đủ và cấp quyền rõ ràng.

## 22. Quy trình thiết kế và vận hành search_path an toàn

Đối với dự án sử dụng nhiều schema, có thể thực hiện theo thứ tự:

1. **Xác định ownership của từng schema**: ai có `CREATE`, ai có `USAGE`, object nào là công khai cho ứng dụng.
2. **Chọn chuẩn tên**: schema/table lowercase, tên nhất quán, tránh trùng object không cần thiết.
3. **Quy định khi nào dùng tên đầy đủ**: migration, quyền, các bảng nghiệp vụ quan trọng, hàm có đặc quyền và SQL có rủi ro đụng tên.
4. **Quy định nguồn search_path**: cấu hình server, database, role, driver hay connection pool; tránh nhiều tầng cùng sửa không phối hợp.
5. **Thiết kế transaction boundaries**: nếu thay path theo từng tác vụ, dùng `SET LOCAL` và rollback/commit rõ.
6. **Rà soát bảo mật**: schema nào trong path cho phép người khác tạo object? `SECURITY DEFINER` có path đáng tin cậy không?
7. **Theo dõi thay đổi**: cùng một câu SQL có thể phân giải khác nếu schema hoặc thứ tự search path thay đổi.
8. **Kiểm tra bằng connection ứng dụng**: không dùng một session DBA làm bằng chứng duy nhất.
9. **Thử với schema trùng tên** trong staging nếu mô hình thật có nhiều schema hoặc multi-tenant.
10. **Lưu cấu hình cùng migration/IaC** khi phù hợp để tránh những môi trường chạy lệch nhau.

Một lựa chọn thực tế:

| Bối cảnh | Cách ưu tiên |
|---|---|
| Một ứng dụng có schema cố định | Đặt search path ổn định khi tạo connection, hoặc ghi tên đầy đủ cho những quan hệ quan trọng. |
| Migration schema | Ghi `schema.object` rõ ràng, kiểm tra database/role trước DDL. |
| Nhiều module chung database | Dùng schema riêng cho namespace, tên đầy đủ ở ranh giới module. |
| SECURITY DEFINER function | Đường tìm kiếm cố định, schema đáng tin cậy, pg_temp cuối, tên object quan trọng đầy đủ. |
| Multi-tenant theo schema | Ánh xạ tenant được xác thực, quản lý connection/transaction và quyền truy cập riêng; không coi search_path là kiểm soát bảo mật. |
| Phân tích lỗi object không tìm thấy | So sánh tên đầy đủ, `current_schemas(true)`, quyền schema/table và metadata catalog. |

## 23. Bài tập thực hành

### Bài 1 — Phân giải hai bảng cùng tên

Với hai bảng `training_sales.invoices` và `training_archive.invoices` của ví dụ:

```sql
SET search_path TO training_archive, training_sales, public;
SELECT * FROM invoices;
```

Hãy cho biết bảng được đọc và vì sao. Đổi lại `SET search_path TO training_sales, training_archive, public` rồi dự đoán kết quả mà không thay câu `SELECT`.

### Bài 2 — Đọc đường tìm kiếm thực tế

Giả sử:

```sql
SET search_path TO schema_missing, training_sales, public;
```

Hãy giải thích sự khác nhau giữa `SHOW search_path`, `current_schema()` và `current_schemas(true)`. Vì sao schema không tồn tại có thể xuất hiện trong chuỗi cấu hình nhưng không tham gia tìm tên?

### Bài 3 — CREATE TABLE tạo ở đâu?

Với `search_path = training_archive, training_sales, public`, role có `USAGE` và `CREATE` trên cả hai schema. Hãy cho biết `CREATE TABLE new_events(id INT)` tạo bảng ở đâu. Viết câu SQL tạo cùng bảng nhưng **bắt buộc** nằm ở `training_sales`.

Sau đó phân tích tình huống role có `USAGE` nhưng không có `CREATE` trên schema đứng đầu.

### Bài 4 — Bảng tạm và pg_temp

Trong session lab có `training_sales.invoices`. Chạy:

```sql
SET search_path TO training_sales, public;
CREATE TEMP TABLE invoices(note TEXT);
SELECT * FROM invoices;
```

Hỏi câu `SELECT` nhắm vào bảng nào? Viết truy vấn đọc bảng thường bất chấp bảng tạm, và nêu vì sao không nên mặc định temp schema được tìm cho tên hàm/toán tử.

### Bài 5 — Quyền và tên đầy đủ

Role `reporting_role` có quyền `SELECT` trên bảng `training_sales.invoices` nhưng không có `USAGE` trên schema `training_sales`.

Hãy giải thích những vấn đề có thể xảy ra khi dùng:

```sql
SELECT * FROM invoices;
SELECT * FROM training_sales.invoices;
```

Viết lệnh cấp quyền phù hợp theo nguyên tắc đặc quyền tối thiểu.

### Bài 6 — SET LOCAL và pool

Một ứng dụng web dùng 20 physical connections. Request A chạy `SET search_path TO tenant_alpha`, truy vấn rồi trả connection về pool. Request B sau đó mượn đúng connection ấy.

Hãy chỉ ra rủi ro, vai trò của `SET LOCAL` trong transaction và những điều **SET LOCAL không tự giải quyết**, đặc biệt vấn đề xác thực tenant và quyền schema.

### Bài 7 — Phân biệt giá trị role/database

Một database có cấu hình chung, một role có cấu hình `search_path` riêng và một thiết lập `ALTER ROLE ... IN DATABASE ... SET` cho role đó.

Hãy trình bày phạm vi mỗi cấu hình và giải thích tại sao connection cũ không tự cập nhật sau `ALTER ROLE`.

### Bài 8 — Chẩn đoán không tìm thấy bảng

Một ứng dụng báo `SQLSTATE 42P01: relation "orders" does not exist`. DBA biết rằng `sales.orders` tồn tại. Hãy xây checklist từ kiểm tra database, role, `search_path`, `current_schemas(true)`, quyền `USAGE`/`SELECT`, đến truy vấn `to_regclass('sales.orders')`.

### Bài 9 — SECURITY DEFINER

Vì sao một function `SECURITY DEFINER` dùng tên bảng và tên hàm không đầy đủ trong search path có schema do user khác được `CREATE` lại nguy hiểm? Hãy đề xuất mẫu `SET search_path` an toàn và giải thích lý do đặt `pg_temp` cuối.

### Bài 10 — Tên có dấu nháy kép

Một schema được tạo tên `"SalesArea"`, bên trong có bảng `"Orders"`. Viết câu SQL đọc bảng với tên đầy đủ đúng. Giải thích vì sao `salesarea.orders` không tương đương.

## Kết luận

**`search_path` quyết định thứ tự PostgreSQL tìm những tên object chưa được chỉ rõ schema.** Khi database có nhiều schema, hai câu SQL giống nhau có thể đọc hoặc thay đổi các object khác nhau nếu session có `search_path` khác nhau. Khi tạo object mà không ghi schema, **`current_schema()`** giúp xác định nơi PostgreSQL dự định tạo đối tượng; các quyền `USAGE` và `CREATE` vẫn được kiểm tra độc lập.

Muốn điều tra chính xác, hãy kết hợp **`SHOW search_path`, `current_schemas(true)`, `to_regclass()`, `pg_catalog` và quyền truy cập**. Ghi tên **`schema.object`** khi cần tính xác định, đặc biệt trong migration, SQL nghiệp vụ quan trọng và các function chạy với đặc quyền cao. Hãy nhớ **`pg_catalog`** có cơ chế tìm ngầm riêng và **`pg_temp`** có thể che bảng thường.

Trong ứng dụng Java và hệ thống nhiều tenant, cần đặc biệt kiểm soát **session state của connection pool**, giới hạn thời gian thay đổi bằng transaction khi phù hợp và tránh đưa tên schema lấy từ request trực tiếp vào SQL. **`search_path` là một cơ chế phân giải tên, không phải hàng rào phân quyền.** Hiểu rõ sự khác biệt đó là nền tảng để tổ chức dữ liệu PostgreSQL đúng schema, triển khai an toàn và chẩn đoán các lỗi tên đối tượng một cách đáng tin cậy.
