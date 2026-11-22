# Phụ thuộc đối tượng và tác động của thay đổi lược đồ

## 1. Một thay đổi nhỏ có thể ảnh hưởng đến nhiều thành phần

Trong cơ sở dữ liệu quan hệ, **lược đồ (schema)** mô tả cấu trúc dữ liệu: bảng, cột, kiểu dữ liệu, khóa, ràng buộc, chỉ mục, view và các đối tượng liên quan. Một đối tượng hiếm khi tồn tại độc lập hoàn toàn. Bảng này có thể được tham chiếu bởi khóa ngoại của bảng khác; cột có thể xuất hiện trong view, chỉ mục, điều kiện truy vấn, thủ tục hoặc báo cáo.

**Phụ thuộc đối tượng (object dependency)** là quan hệ trong đó một đối tượng hoặc thành phần cần sự tồn tại, cấu trúc hoặc hành vi nhất định của đối tượng khác để tiếp tục hoạt động đúng.

Ví dụ, một ứng dụng có bảng `customers` với cột `full_name`. Nhóm phát triển muốn đổi tên cột thành `display_name`. Chỉ một lệnh `ALTER TABLE` có thể tác động đến:

- View đọc tên khách hàng.
- Câu SQL ở API, batch job, báo cáo hoặc ứng dụng di động.
- Mã ánh xạ ORM/JPA đang khai báo tên cột `full_name`.
- Chỉ mục, trigger, constraint hoặc function tham chiếu tới cột.
- Quy trình đồng bộ dữ liệu, CDC (change data capture) và các bảng phân tích.
- Những phiên bản ứng dụng cũ vẫn hoạt động trong lúc triển khai.

Một hệ quản trị cơ sở dữ liệu (DBMS) có thể phát hiện và ngăn **một số** thay đổi phá vỡ phụ thuộc đã đăng ký trong metadata, nhưng không thể bảo đảm phát hiện mọi tham chiếu nằm bên ngoài cơ sở dữ liệu.

**Mục tiêu bài học:** hiểu cách các phụ thuộc hình thành, phân biệt phụ thuộc mà DBMS biết với phụ thuộc ở tầng ứng dụng, dự đoán tác động của DDL, và xây dựng quy trình thay đổi lược đồ an toàn, có thể kiểm chứng.

## 2. Lược đồ ví dụ: khách hàng và đơn hàng

Các ví dụ sau ưu tiên **PostgreSQL** vì hỗ trợ `CREATE SCHEMA`, các loại phụ thuộc và công cụ khám phá metadata rõ ràng. Khái niệm áp dụng cho SQL Server, MySQL/MariaDB, Oracle và SQLite; cú pháp DDL, quản lý transaction và hành vi phụ thuộc có thể khác.

Tạo một schema thực hành riêng:

~~~sql
CREATE SCHEMA shop;

CREATE TABLE shop.customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name TEXT NOT NULL,
    email TEXT UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE shop.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL
        CHECK (total_amount >= 0),
    placed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES shop.customers (customer_id)
        ON DELETE RESTRICT
);

CREATE INDEX idx_orders_customer_id
    ON shop.orders (customer_id);

CREATE VIEW shop.customer_order_totals AS
SELECT
    c.customer_id,
    c.full_name,
    COUNT(o.order_id) AS order_count,
    COALESCE(SUM(o.total_amount), 0) AS total_spent
FROM shop.customers AS c
LEFT JOIN shop.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.full_name;
~~~

Thêm dữ liệu:

~~~sql
INSERT INTO shop.customers (full_name, email)
VALUES
    ('An', 'an@example.test'),
    ('Binh', 'binh@example.test');

INSERT INTO shop.orders (customer_id, total_amount)
SELECT customer_id, 750000
FROM shop.customers
WHERE email = 'an@example.test';

SELECT customer_id, full_name, order_count, total_spent
FROM shop.customer_order_totals
ORDER BY customer_id;
~~~

Trong ví dụ này:

- `customers.customer_id` là khóa chính và là khóa được tham chiếu.
- `orders.customer_id` là khóa ngoại trỏ đến `customers.customer_id`.
- `fk_orders_customer` là ràng buộc bảo vệ tính toàn vẹn tham chiếu.
- `idx_orders_customer_id` là chỉ mục hỗ trợ một số truy vấn và thao tác liên quan đến khách hàng trên bảng đơn hàng.
- `customer_order_totals` là view phụ thuộc vào bảng và các cột được dùng trong câu `SELECT` của nó.
- Mã ứng dụng truy vấn `customer_order_totals` cũng phụ thuộc vào **giao diện cột kết quả** của view.

**Lưu ý:** PostgreSQL tự tạo chỉ mục cho khóa chính và ràng buộc `UNIQUE`, nhưng không mặc định tự tạo chỉ mục ở **cột tham chiếu của khóa ngoại** (`orders.customer_id`). Vì vậy ví dụ tạo chỉ mục đó tường minh.

## 3. Đọc sơ đồ phụ thuộc

Có thể biểu diễn các quan hệ chính thành đồ thị có hướng: **đối tượng ở đầu mũi tên cần đến đối tượng ở cuối mũi tên**.

~~~text
shop.customer_order_totals (VIEW)
        |                       |
        v                       v
shop.customers             shop.orders
  | customer_id                 | customer_id
  | full_name                   | total_amount
  |                             |
  +<---- FK fk_orders_customer -+
                                |
                  idx_orders_customer_id
                  (INDEX trên orders.customer_id)

Ứng dụng / ORM / API / báo cáo / ETL
       |           |          |
       +-----------+----------+
                   v
        Bảng, cột, view hoặc
        định dạng kết quả đang dùng
~~~

Đồ thị ở trên nhằm diễn giải khái niệm, không phải một bản trích xuất đầy đủ của metadata PostgreSQL. Khi phân tích một thay đổi, hãy hỏi hai hướng:

1. **Upstream:** đối tượng hiện tại đang dựa vào những đối tượng/cột nào?
2. **Downstream:** những đối tượng, truy vấn hoặc hệ thống nào đang dựa vào đối tượng/cột định sửa?

Một view phụ thuộc vào bảng gốc, còn một báo cáo phụ thuộc vào view. Nếu xóa cột trong bảng gốc, tác động có thể lan qua nhiều tầng.

## 4. Các loại phụ thuộc cần nhận biết

| Loại | Ví dụ | DBMS có tự nhận biết không? | Nguy cơ khi thay đổi |
| --- | --- | --- | --- |
| Khóa ngoại | `orders.customer_id` tham chiếu `customers.customer_id` | Thường có, thông qua catalog ràng buộc | Xóa/sửa khóa phá tính toàn vẹn tham chiếu |
| View | `customer_order_totals` đọc `customers.full_name` | Thường có, tùy DBMS và loại view | View không tạo được/không chạy hoặc thay đổi cột xuất ra |
| Chỉ mục | `idx_orders_customer_id` trên `orders.customer_id` | Có | Chỉ mục bị bỏ, không còn phù hợp hoặc hiệu năng thay đổi |
| Constraint | `CHECK (total_amount >= 0)`, `UNIQUE(email)` | Có | Dữ liệu không hợp lệ hoặc ghi dữ liệu thất bại |
| Cột phát sinh / default / sequence | Identity, generated column, biểu thức mặc định | Có hoặc một phần, tùy DBMS | Sinh khóa hoặc tính cột không còn đúng |
| Trigger / function / stored procedure | Logic ghi nhật ký, tính tổng, validation | Có thể có phụ thuộc tĩnh; SQL động thường khó dò | Lỗi chỉ xuất hiện khi code thực thi |
| Ứng dụng / ORM | `@Column(name = "full_name")`, câu SQL trong backend | Thường **không** | Lỗi truy vấn, deserialize, ghi dữ liệu |
| ETL, CDC, báo cáo, BI | Pipeline đọc cột `full_name` | Thường **không** | Đứt pipeline, sai số liệu, schema drift |
| Quyền truy cập | `GRANT SELECT` trên bảng/cột/view | Có metadata, nhưng hành vi phụ thuộc hệ | Ứng dụng hoặc vai trò không còn đọc được |
| Backup, replica, tích hợp ngoài | Consumer phụ thuộc định dạng schema | Chỉ được biết một phần, thường ngoài catalog | Đồng bộ hoặc khôi phục không đúng kỳ vọng |

Cần phân biệt **phụ thuộc cấu trúc** và **phụ thuộc hành vi**:

- Phụ thuộc cấu trúc: một khóa ngoại yêu cầu khóa được tham chiếu; view được khai báo dùng một cột cụ thể. DBMS có thể ghi nhận trực tiếp.
- Phụ thuộc hành vi: đoạn code kỳ vọng kết quả có tên trường `full_name`; báo cáo giả định `email` không `NULL`; ứng dụng kỳ vọng truy vấn luôn nhanh. DBMS thường không có thông tin để bảo vệ các kỳ vọng đó.

Ví dụ một thay đổi chỉ số lượng/kiểu dữ liệu trong `SELECT *` có thể vẫn là SQL hợp lệ, nhưng mã ứng dụng lấy cột theo vị trí hoặc serializer tạo JSON khác trước. DBMS không thể suy ra đó là lỗi nghiệp vụ.

## 5. Tác động của từng loại thay đổi lược đồ

Không phải mọi thay đổi đều giống nhau. Xét các thao tác DDL thường gặp:

| Thay đổi | Tác động cần đánh giá |
| --- | --- |
| Thêm cột cho phép `NULL` | Thường ít phá vỡ truy vấn liệt kê cột; có thể ảnh hưởng `SELECT *`, `INSERT ... VALUES` không liệt kê cột, đồng bộ schema và model |
| Thêm cột `NOT NULL` | Hàng hiện có chưa có giá trị; cần default/backfill hoặc cách triển khai tương ứng |
| Đổi tên cột | View/triggers có thể được DBMS cập nhật hoặc chặn; SQL, DTO, ORM và report cũ có thể hỏng |
| Đổi kiểu cột | Dữ liệu có thể không chuyển được; khả năng tương thích giá trị, chỉ mục, ràng buộc, khóa và hiệu năng thay đổi |
| Xóa cột | Mất dữ liệu cột và phá những tham chiếu; khó khôi phục nếu không có bản sao |
| Xóa bảng | Phá khóa ngoại, view, báo cáo, ứng dụng; dữ liệu mất |
| Thêm/sửa khóa ngoại | Dữ liệu đang có phải hợp lệ; các thao tác ghi/xóa có thể thất bại hoặc tốn chi phí hơn |
| Thêm `UNIQUE` | Thất bại nếu dữ liệu trùng; những insert/update trước đây thành hợp lệ giờ có thể bị từ chối |
| Thêm/chỉnh `CHECK` | Dữ liệu quá khứ và thao tác ghi tương lai có thể vi phạm |
| Tạo/xóa chỉ mục | Tác động đến thời gian đọc, ghi, dung lượng, khóa; không nhất thiết đổi kết quả logic |
| Đổi view | Có thể đổi tên, kiểu hoặc thứ tự cột kết quả; đối tượng sử dụng view bị ảnh hưởng |
| Đổi tên/xóa schema | Mọi định danh đủ schema và quyền truy cập liên quan cần được xét |

Từ góc nhìn tương thích, có ba nhóm:

- **Tương thích với phiên bản cũ:** thay đổi mà phiên bản ứng dụng đang chạy vẫn đọc/ghi được và giữ đúng ý nghĩa. Thêm cột nullable thường là ứng viên, nhưng không mặc định an toàn với `SELECT *` hoặc insert theo vị trí.
- **Cần phối hợp chuyển đổi:** ví dụ đổi tên cột, tách bảng, thay khóa, thay đổi kiểu. Cần giai đoạn hai cấu trúc cùng tồn tại hoặc chuyển dữ liệu.
- **Phá vỡ rõ ràng:** xóa cột/bảng, làm chặt constraint ngay khi dữ liệu chưa hợp lệ, đổi kiểu không chuyển đổi được.

Đánh giá phải dựa trên **schema, dữ liệu hiện có và phiên bản ứng dụng đang hoạt động**, không chỉ trên cú pháp DDL.

## 6. RESTRICT, CASCADE và phụ thuộc được DBMS quản lý

Trong PostgreSQL, thao tác xóa đối tượng có thể gặp phụ thuộc đã được catalog ghi nhận. Mặc định nhiều lệnh `DROP` hành xử theo hướng **`RESTRICT`**: từ chối xóa khi còn đối tượng phụ thuộc cần được bảo vệ.

Ví dụ sau chỉ dùng để hiểu hành vi trong **cơ sở dữ liệu thử nghiệm**, không áp dụng trực tiếp cho production:

~~~sql
-- Trên PostgreSQL: view customer_order_totals phụ thuộc vào full_name.
-- Hệ quản trị sẽ từ chối xóa cột nếu còn phụ thuộc view đó.
ALTER TABLE shop.customers
DROP COLUMN full_name RESTRICT;
~~~

Nếu thêm `CASCADE`, PostgreSQL có thể loại bỏ **các đối tượng phụ thuộc tương ứng**, chẳng hạn view:

~~~sql
-- Minh họa tác động nguy hiểm; không chạy khi muốn giữ view!
ALTER TABLE shop.customers
DROP COLUMN full_name CASCADE;
~~~

Điều quan trọng:

- `CASCADE` không có nghĩa “sửa tất cả các nơi dùng cột cho tương thích”; nó thường **xóa những đối tượng phụ thuộc** được DBMS quản lý.
- `CASCADE` không đi sửa mã Java, ORM mapping, dashboard hay job ETL ở ngoài DBMS.
- Một số phụ thuộc nội bộ, như chỉ mục gắn chặt với cột, có thể được DBMS tự xử lý khi xóa cột, kể cả không ghi rõ `CASCADE`; loại và phạm vi xử lý phụ thuộc DBMS.
- `ON DELETE CASCADE` trong **khóa ngoại** là một cơ chế khác: nó quy định hành vi **xóa hàng dữ liệu** khi hàng cha bị xóa, không phải cách drop đối tượng schema. Không được nhầm hai khái niệm cùng tên `CASCADE`.

Một thao tác đáng chú ý là đổi tên cột:

~~~sql
-- Minh họa trong PostgreSQL:
ALTER TABLE shop.customers
RENAME COLUMN full_name TO display_name;
~~~

PostgreSQL có thể tự cập nhật tham chiếu của view được quản lý trong catalog để view tiếp tục hoạt động; tuy nhiên **tên cột kết quả mà view công bố có thể vẫn giữ tên cũ**. Code ứng dụng truy vấn trực tiếp `shop.customers.full_name` sẽ gặp lỗi sau khi đổi tên. Các DBMS khác có thể yêu cầu sửa/rebuild view hoặc xử lý dependency khác nhau.

Vì thế, **một lệnh DDL thực thi thành công không chứng minh mọi consumer đã tương thích**.

## 7. Phát hiện phụ thuộc trước khi sửa

Cần kết hợp **metadata DBMS** với việc tìm tham chiếu trong code và các hệ thống ngoài database.

### 7.1. Xem cấu trúc cột và ràng buộc

`information_schema` cung cấp giao diện metadata chuẩn hóa ở nhiều hệ SQL, nhưng mức hỗ trợ và cách giới hạn theo quyền không hoàn toàn giống nhau.

~~~sql
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'shop'
  AND table_name = 'customers'
ORDER BY ordinal_position;
~~~

Tìm bảng đang tham chiếu `shop.customers` trong PostgreSQL bằng catalog hệ thống:

~~~sql
SELECT
    con.conname AS foreign_key_name,
    con.conrelid::regclass AS referencing_table,
    con.confrelid::regclass AS referenced_table
FROM pg_constraint AS con
WHERE con.contype = 'f'
  AND con.confrelid = 'shop.customers'::regclass
ORDER BY referencing_table::text, foreign_key_name;
~~~

Với dữ liệu schema mẫu, truy vấn chỉ ra `fk_orders_customer` từ `shop.orders` đến `shop.customers`.

### 7.2. Tìm view phụ thuộc

Trên PostgreSQL, có thể xem view nào tham chiếu đến bảng bằng metadata:

~~~sql
SELECT
    view_schema,
    view_name,
    table_schema,
    table_name
FROM information_schema.view_table_usage
WHERE table_schema = 'shop'
  AND table_name = 'customers'
ORDER BY view_schema, view_name;
~~~

Kết quả phụ thuộc quyền/ownership và phạm vi metadata lộ ra cho tài khoản hiện tại; không nên xem danh sách thiếu từ một user ít quyền là bằng chứng không còn phụ thuộc.

Muốn đọc định nghĩa một view cụ thể trong PostgreSQL:

~~~sql
SELECT pg_get_viewdef('shop.customer_order_totals'::regclass, TRUE);
~~~

PostgreSQL có các catalog như `pg_depend`, `pg_rewrite`, `pg_constraint`, `pg_class`, `pg_attribute` và `pg_trigger` để phân tích sâu. Tuy nhiên `pg_depend` lưu nhiều loại quan hệ phụ thuộc nội bộ và cần hiểu phân loại `deptype`, OID, rewrite rule; không nên coi một câu lọc text tên cột hoặc kết quả join đơn giản trên catalog là bản đồ đầy đủ.

Các công cụ quản trị DBMS thường cung cấp giao diện “Dependencies / Dependents”, “View Definition”, “Referenced by” hoặc truy vấn hệ thống chuyên biệt. Chúng giúp bổ sung danh sách metadata, nhưng vẫn cần tìm phần ứng dụng.

### 7.3. Tìm những tham chiếu mà DBMS không biết

Ví dụ khi muốn đổi `full_name` thành `display_name`, hãy tìm các cách dùng sau trong nguồn ứng dụng, test, script và cấu hình:

~~~text
full_name
customers.full_name
SELECT *
INSERT INTO customers VALUES (...)
@Column(name = "full_name")
"full_name" trong DTO / serializer / hợp đồng API
tên trường ở biểu mẫu, báo cáo, dashboard, ETL, BI
định nghĩa mapping CDC hoặc bảng analytics
~~~

Một truy vấn SQL được lắp ghép động, thực thi trong stored procedure hoặc được cấu hình ở một dịch vụ khác có thể không xuất hiện khi tìm chuỗi trong một repository.

Đối với hệ thống có nhiều ứng dụng, nên tạo danh sách **consumer** và phiên bản còn hoạt động: backend, worker, ứng dụng mobile, báo cáo, API public, batch job, CDC, replica, đối tác tích hợp. Truy xuất log truy vấn và quan sát thực tế giúp nhận diện những đường đi ít được tài liệu hóa.

### 7.4. Lập bản đồ tác động

Trước khi sửa một cột quan trọng, ghi lại bảng tác động:

| Thành phần | Phụ thuộc vào | Thay đổi cần làm | Cách xác minh |
| --- | --- | --- | --- |
| `shop.customer_order_totals` | `customers.full_name` | Chuyển sang cột mới hoặc tạo view v2 | Đọc định nghĩa, truy vấn view |
| API đọc hồ sơ | SQL và JSON tên khách hàng | Cập nhật query/mapping, giữ hợp đồng API nếu cần | Integration/API test |
| Batch ghi khách hàng | `INSERT`/`UPDATE` vào `full_name` | Ghi cả cột mới trong giai đoạn chuyển đổi | Chạy job trên dữ liệu thử |
| Dashboard doanh thu | View hoặc schema BI | Chuyển nguồn dữ liệu/alias | Đối soát số liệu |
| CDC/warehouse | Danh sách cột, schema event | Cập nhật mapping và kiểm tra replay | Kiểm tra event & dữ liệu đích |
| Các phiên bản ứng dụng cũ | Cột cũ | Giữ cột cũ đến khi rút hết phiên bản cũ | Kiểm tra traffic/deployment |

## 8. Thay đổi an toàn theo mô hình Expand → Migrate → Contract

Giả sử cần đổi tên cột `customers.full_name` thành `display_name` trong một hệ thống đang hoạt động liên tục. Đổi tên trực tiếp có thể làm ứng dụng cũ bị lỗi. Cách triển khai theo nhiều giai đoạn giúp hai phiên bản ứng dụng cùng hoạt động trong thời gian chuyển đổi.

### Giai đoạn A — Expand: thêm cấu trúc mới tương thích

Thêm cột mới **cho phép NULL**:

~~~sql
ALTER TABLE shop.customers
ADD COLUMN display_name TEXT;
~~~

Lúc này `full_name` và view cũ vẫn tồn tại. Mã ứng dụng cũ chưa cần đổi ngay.

Không vội dùng:

~~~sql
-- Không phù hợp khi chưa có dữ liệu hoặc DEFAULT hợp lý:
ALTER TABLE shop.customers
ADD COLUMN display_name TEXT NOT NULL;
~~~

Với bảng đã có dữ liệu, các hàng cũ chưa có `display_name`, nên thao tác có thể bị từ chối. Dùng `DEFAULT` có thể giúp một số thay đổi, nhưng không nên tự ý đặt giá trị giả chỉ để thỏa constraint.

### Giai đoạn B — Migrate: chuyển dữ liệu và nâng cấp ứng dụng

Backfill dữ liệu sẵn có:

~~~sql
UPDATE shop.customers
SET display_name = full_name
WHERE display_name IS NULL;
~~~

Trong bảng lớn, một `UPDATE` trên toàn bộ dữ liệu có thể tạo lượng ghi, WAL/redo log và khóa lớn. Nên cân nhắc chia lô theo khóa chính, có kiểm soát tiến độ và độ trễ. Ví dụ trên phù hợp để học với bảng nhỏ.

Trong giai đoạn chuyển đổi, **ứng dụng ghi mới/cập nhật phải duy trì cả hai cột** cho đến khi không còn consumer cũ. Một lệnh minh họa:

~~~sql
UPDATE shop.customers
SET
    full_name = 'An Nguyen',
    display_name = 'An Nguyen'
WHERE customer_id = 1;
~~~

Một số nhóm dùng trigger tạm hoặc lớp truy cập dữ liệu chung để đồng bộ hai cột. Dù dùng phương pháp nào, cần xác định nguồn dữ liệu nào đúng khi hai cột khác nhau và tránh ghi đè dữ liệu mới bằng dữ liệu cũ trong lúc backfill.

Trong giai đoạn này có thể thêm **view phiên bản mới** để consumer chuyển dần, giữ nguyên view cũ:

~~~sql
CREATE VIEW shop.customer_order_totals_v2 AS
SELECT
    c.customer_id,
    c.display_name,
    COUNT(o.order_id) AS order_count,
    COALESCE(SUM(o.total_amount), 0) AS total_spent
FROM shop.customers AS c
LEFT JOIN shop.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.display_name;
~~~

Các consumer cũ tiếp tục đọc `shop.customer_order_totals`, còn consumer mới có thể đọc `shop.customer_order_totals_v2` với cột `display_name`. Đây là một ví dụ **version hóa giao diện dữ liệu**.

Lưu ý PostgreSQL không cho `CREATE OR REPLACE VIEW` tùy tiện đổi tên các cột đầu ra hiện có trong vị trí cũ; việc tạo một view v2 mới giúp tránh phá hợp đồng view cũ.

### Giai đoạn C — Xác minh dữ liệu và tăng ràng buộc

Sau khi tất cả writer đều ghi `display_name` và backfill đã hoàn tất, kiểm tra giá trị thiếu hoặc sai lệch:

~~~sql
SELECT COUNT(*) AS missing_display_name
FROM shop.customers
WHERE display_name IS NULL;

SELECT COUNT(*) AS inconsistent_names
FROM shop.customers
WHERE display_name IS DISTINCT FROM full_name;
~~~

Kết quả kỳ vọng theo quy tắc đồng bộ ví dụ là `0` ở cả hai truy vấn. Nếu có sai lệch, cần xử lý nguyên nhân thay vì tự động lấy bất kỳ phía nào làm nguồn chân lý.

Khi dữ liệu đã bảo đảm không `NULL` và tất cả writer duy trì điều kiện đó, có thể tăng ràng buộc:

~~~sql
ALTER TABLE shop.customers
ALTER COLUMN display_name SET NOT NULL;
~~~

Trên một bảng lớn, thao tác nâng ràng buộc có thể cần quét bảng hoặc khóa đáng kể. PostgreSQL có những kỹ thuật triển khai theo giai đoạn (như `CHECK ... NOT VALID` rồi `VALIDATE CONSTRAINT` trong các tình huống phù hợp), nhưng khả năng tận dụng ràng buộc đã xác minh, loại khóa và thời gian thực hiện phụ thuộc phiên bản và DDL cụ thể. Đánh giá trên dữ liệu đại diện và công cụ triển khai trước khi áp dụng.

### Giai đoạn D — Contract: loại bỏ cấu trúc cũ khi không còn phụ thuộc

Chỉ sau khi mọi ứng dụng, báo cáo, job và view đã chuyển sang cột mới, mới cân nhắc loại bỏ cấu trúc cũ. Với schema ví dụ, view cũ vẫn dùng `full_name` nên cần xử lý nó trước:

~~~sql
-- Minh họa bước dọn dẹp SAU khi đã chuyển toàn bộ consumer:
DROP VIEW shop.customer_order_totals;

ALTER TABLE shop.customers
DROP COLUMN full_name;
~~~

Những lệnh trên xóa giao diện cũ và dữ liệu của cột cũ; chỉ chạy sau khi hoàn tất kiểm kê phụ thuộc và phương án phục hồi dữ liệu. Nếu còn đối tượng phụ thuộc khác, DBMS có thể từ chối lệnh `DROP COLUMN`.

Quá trình chuyển đổi đầy đủ:

~~~text
Phiên bản cũ:
customers(full_name)
    |
    +--> view cũ, API cũ

EXPAND:
customers(full_name, display_name NULL)
    |
    +--> API cũ vẫn hoạt động

MIGRATE:
backfill + writer ghi cả hai cột
    |
    +--> view cũ, view v2
    +--> consumer lần lượt chuyển sang display_name

VALIDATE:
kiểm tra dữ liệu, khóa lỗi ghi, thêm NOT NULL khi phù hợp

CONTRACT:
xác nhận consumer cũ đã dừng
    |
    +--> xóa view cũ, xóa full_name
    +--> chỉ còn hợp đồng mới
~~~

Trong môi trường có rolling deployment, đừng bắt đầu `CONTRACT` ngay khi phiên bản mới đầu tiên được triển khai; có thể vẫn còn instance, queue worker, ứng dụng mobile hoặc đối tác đang dùng schema cũ.

## 9. Tương thích ngược, tương thích xuôi và hợp đồng dữ liệu

**Tương thích ngược (backward compatibility)** trong triển khai schema thường nghĩa là phiên bản ứng dụng cũ vẫn hoạt động với schema mới trong một khoảng thời gian. **Tương thích xuôi (forward compatibility)** nghĩa là thành phần mới có thể hoạt động với schema trước đó, nếu kế hoạch rollout yêu cầu.

Các câu hỏi thiết thực:

- Một instance ứng dụng cũ có thể tiếp tục `INSERT` khi đã thêm cột mới không?
- Ứng dụng mới có đọc được dữ liệu được tạo trước khi backfill không?
- Một job được chạy lại với binary cũ có còn dùng cột đã xóa không?
- API công bố tên thuộc tính JSON có phải giữ nguyên dù tên cột vật lý đổi không?
- Một view có phải đóng vai trò **giao diện ổn định** để che việc đổi cấu trúc bên dưới không?

**Tên cột trong DB không bắt buộc trùng tên trường API.** Ví dụ có thể đổi từ `full_name` sang `display_name` ở DB nhưng vẫn phục vụ JSON `"fullName"` theo hợp đồng API, miễn adapter/mapping được cập nhật nhất quán. Đó là một lớp cách ly hữu ích giữa schema lưu trữ và consumer.

Ngược lại, việc sử dụng `SELECT *` trong một API có thể làm thay đổi cột trả về khi bảng được thêm cột. Ưu tiên liệt kê rõ các cột public:

~~~sql
SELECT customer_id, full_name, email
FROM shop.customers
WHERE customer_id = 1;
~~~

Sau khi đổi schema, cập nhật mapping một cách có chủ đích; tránh để các biến động nội bộ tự thay đổi giao diện public.

## 10. Tác động đến dữ liệu và tính toàn vẹn

### 10.1. Đổi kiểu dữ liệu có thể làm mất thông tin

Một lệnh như:

~~~sql
-- Chỉ minh họa: PostgreSQL có thể yêu cầu cast và kiểm tra dữ liệu.
ALTER TABLE shop.customers
ALTER COLUMN full_name TYPE VARCHAR(20);
~~~

có nguy cơ không phù hợp với dữ liệu tên dài hơn 20 ký tự và có thể làm lỗi thao tác hoặc không đạt yêu cầu kinh doanh. Những thay đổi kiểu có thể buộc DBMS ghi lại bảng, xây lại chỉ mục hoặc giữ khóa trong một thời gian.

Trước khi thu hẹp kích thước, kiểm tra dữ liệu thực tế:

~~~sql
SELECT
    MAX(CHAR_LENGTH(full_name)) AS max_length,
    COUNT(*) FILTER (WHERE CHAR_LENGTH(full_name) > 20) AS too_long_count
FROM shop.customers;
~~~

`FILTER` trong ví dụ trên là cú pháp PostgreSQL/SQL hiện đại nhưng không được mọi DBMS hỗ trợ. Một cách thay thế phổ biến là `SUM(CASE WHEN ... THEN 1 ELSE 0 END)`.

### 10.2. Constraint mới có thể thất bại trên dữ liệu cũ

Giả sử cần email không được trùng. Dữ liệu hiện tại có thể có email trùng, nên thêm `UNIQUE` ngay sẽ thất bại:

~~~sql
SELECT
    email,
    COUNT(*) AS duplicate_count
FROM shop.customers
WHERE email IS NOT NULL
GROUP BY email
HAVING COUNT(*) > 1;
~~~

Sau khi làm sạch dữ liệu, mới cân nhắc constraint. Tương tự, thêm `FOREIGN KEY` cần xét các hàng mồ côi; thêm `NOT NULL` cần giải quyết hàng thiếu; thêm `CHECK` cần xem dữ liệu đã tồn tại và các đường ghi sau này.

### 10.3. Thay khóa chính có tác động lan rộng

Nếu đổi `customers.customer_id`, khóa ngoại trong `orders` và các bảng con khác cần được tính đến. Thay khóa chính thường kéo theo thay đổi dữ liệu tham chiếu, chỉ mục, API, cache key, URL, ID trong event và bảng dữ liệu phân tích.

Đặc biệt, **khóa thay thế (surrogate key)** đã được phát tán ra nhiều hệ thống không dễ “đổi tên hoặc đánh số lại” chỉ bằng một câu DDL. Cần có bảng ánh xạ ID cũ–mới hoặc chiến lược migration bảo đảm toàn vẹn giữa các thành phần.

## 11. Tác động đến giao dịch, khóa và hiệu năng

Một DDL đúng logic vẫn có thể gây sự cố vận hành khi chạy trên bảng lớn hoặc có nhiều giao dịch đồng thời.

| Rủi ro | Ví dụ | Cần quan sát |
| --- | --- | --- |
| Khóa DDL | `ALTER TABLE` chờ các giao dịch đang mở | Lock wait, thời gian giữ khóa, timeout |
| Quét hoặc ghi lại bảng | Đổi kiểu cột, gắn ràng buộc hoặc backfill | Thời gian, I/O, WAL/redo, dung lượng |
| Thay đổi kế hoạch truy vấn | Xóa chỉ mục, thay kiểu, thêm điều kiện | `EXPLAIN`, độ trễ, CPU |
| Tăng chi phí ghi | Bổ sung chỉ mục, constraint, trigger | Throughput và độ trễ insert/update |
| Đồng bộ chậm | DDL lớn hoặc backfill đổ dồn sang replica/CDC | Replication lag, backlog |
| Tranh chấp giữa ứng dụng cũ và mới | Một phiên bản chỉ ghi cột cũ, bản khác chỉ đọc cột mới | Dữ liệu lệch, lỗi đọc/ghi |
| Khôi phục khó | Drop cột làm mất dữ liệu | Backup/PITR, kế hoạch phục hồi |

**DDL có transaction hay không là khác biệt quan trọng giữa hệ quản trị.** PostgreSQL hỗ trợ nhiều thao tác DDL bên trong transaction, nhưng có ngoại lệ và các mức khóa khác nhau. MySQL thường implicit commit với nhiều lệnh DDL; SQL Server, Oracle và SQLite có quy tắc riêng. Không được viết `BEGIN; ALTER TABLE ...; ROLLBACK;` rồi giả định rollback luôn phục hồi schema ở mọi DBMS.

Với hệ thống có dữ liệu lớn, cần xác định trước: thao tác có cần khóa độc quyền không, có được thực hiện online không, có thể chia lô không, và có đủ dung lượng/log cho migration không. Khả năng “online DDL” thay đổi theo DBMS, phiên bản, engine và kiểu thay đổi; không tồn tại một quy tắc áp dụng chung.

## 12. Khả chuyển giữa các hệ quản trị

Cùng khái niệm schema dependency nhưng DBMS có thể thực hiện DDL khác nhau:

| Chủ đề | Khác biệt cần chú ý |
| --- | --- |
| `ALTER TABLE` | Hỗ trợ rename, drop, change type, default và nhiều thay đổi trong một lệnh khác nhau |
| `DROP ... CASCADE` / `RESTRICT` | Không phải mọi DBMS có cùng cú pháp hoặc hành vi xóa phụ thuộc |
| View | Cách lưu định nghĩa, cập nhật tham chiếu khi đổi tên, `CREATE OR REPLACE` và materialized view khác nhau |
| Khóa ngoại | Hành vi DDL, kiểm tra constraint, index tham chiếu và cách xử lý cascade khác nhau |
| Index | Tạo online/concurrently, loại index, index biểu thức và lock khác nhau |
| DDL transaction | Mức hỗ trợ rollback/implicit commit khác nhau |
| Metadata | `information_schema` chỉ bao phủ một phần; catalog hệ thống chuyên biệt theo DBMS |
| Thứ tự cột, kiểu dữ liệu | Một số engine hạn chế thay đổi type hoặc phải dựng lại bảng |
| Phân quyền | Owner, role, schema, default privilege và thay đổi grant khác nhau |

Ví dụ trong PostgreSQL, `ALTER TABLE ... RENAME COLUMN` có thể tự cập nhật tham chiếu trong view. Trong hệ khác, việc đổi tên hoặc cấu trúc nguồn có thể làm view invalid, yêu cầu refresh metadata hoặc sửa định nghĩa tường minh. Vì vậy phải thử với **đúng DBMS và phiên bản triển khai**, không suy ra từ kết quả của một hệ khác.

SQLite ở nhiều trường hợp `ALTER TABLE` bị giới hạn hơn so với PostgreSQL, và một số thay đổi cần mô hình “tạo bảng mới → sao chép dữ liệu → đổi tên bảng”, với việc bảo toàn index, trigger, foreign key và dữ liệu đặc biệt cẩn thận. Các phiên bản SQLite gần đây đã hỗ trợ nhiều thao tác hơn; cần tra tài liệu theo phiên bản đích.

## 13. Quy trình triển khai một schema migration

Đối với thay đổi có phụ thuộc, một migration không kết thúc ở việc câu DDL chạy thành công. Quy trình nên gắn với hợp đồng dữ liệu và chu kỳ triển khai ứng dụng.

### Bước 1 — Xác định thay đổi và phạm vi

Mô tả “trước → sau”, ví dụ:

~~~text
Trước: customers.full_name TEXT NOT NULL
Sau:   customers.display_name TEXT NOT NULL

Dữ liệu: tên khách hàng được giữ nguyên
Ứng dụng: tương thích hai phiên bản trong giai đoạn chuyển đổi
API: giữ nguyên trường JSON public nếu chưa được thông báo đổi hợp đồng
~~~

### Bước 2 — Kiểm kê metadata và consumer

Đọc bảng, index, constraint, view, trigger, function, grant và truy vấn từ catalog; tìm tham chiếu trong source code, migration cũ, báo cáo, CDC, jobs, ứng dụng khác và quyền truy cập. Ghi rõ owner từng consumer và chiến lược nâng cấp.

### Bước 3 — Kiểm tra dữ liệu nền

Đếm hàng, đo giá trị `NULL`, dữ liệu trùng, giá trị vượt giới hạn kiểu, ràng buộc có nguy cơ thất bại. Dùng dữ liệu đại diện về kích thước và phân phối; bảng nhỏ trên máy phát triển không phản ánh hết chi phí của bảng sản xuất.

### Bước 4 — Viết migration có thứ tự

Dùng một công cụ quản lý migration như Flyway/Liquibase hoặc hệ thống migration đang có để lưu phiên bản DDL trong source control. Giữ migration có thứ tự, có thể tái lập và được đánh giá như thay đổi code. Không sửa lại một migration đã áp dụng ở nhiều môi trường nếu quy trình yêu cầu lịch sử bất biến; tạo migration mới để chỉnh sửa.

### Bước 5 — Phối hợp thứ tự triển khai

Với thay đổi phá vỡ giao diện, triển khai theo `Expand → Migrate → Contract`. Chỉ chuyển sang bước loại bỏ cấu trúc cũ sau khi chắc chắn không còn consumer dựa vào nó. Đặt ngưỡng quan sát lỗi, thời gian dừng hoặc khả năng chuyển hướng traffic khi cần.

### Bước 6 — Xác minh và có phương án phục hồi

Kiểm tra kết quả schema, dữ liệu, hành vi đọc/ghi của các phiên bản app, view, quyền truy cập, kế hoạch truy vấn, log lỗi và các consumer bên ngoài. Với thay đổi làm mất dữ liệu, rollback DDL không luôn đủ; cần backup, snapshot, PITR hoặc chiến lược forward fix. Thử quy trình phục hồi theo hạ tầng thực tế trước khi thực hiện thay đổi phá hủy.

## 14. Hai tình huống dễ nhầm

### Tình huống A — “Thêm cột mới thì chắc chắn an toàn”

Giả sử:

~~~sql
ALTER TABLE shop.orders
ADD COLUMN coupon_code TEXT;
~~~

Với truy vấn có danh sách cột tường minh, đây thường là thay đổi tương thích. Nhưng ứng dụng cũ có thể sử dụng:

~~~sql
INSERT INTO shop.orders VALUES (...);
~~~

hoặc đọc:

~~~sql
SELECT * FROM shop.orders;
~~~

Nếu thiếu danh sách cột ở `INSERT`, số lượng/ý nghĩa giá trị theo vị trí có thể không còn khớp với cấu trúc bảng. `SELECT *` có thể làm kết quả mang thêm cột, ảnh hưởng mapper theo vị trí, CSV export, hợp đồng dữ liệu hoặc bảng đích ETL. Vì vậy thêm cột nullable **thường ít rủi ro hơn**, nhưng vẫn cần xem cách ứng dụng tiêu thụ schema.

### Tình huống B — “DBMS không báo lỗi thì consumer vẫn chạy”

Đổi tên `full_name` thành `display_name` có thể khiến catalog được cập nhật đúng, và view cũ vẫn truy vấn được. Nhưng một câu SQL Java cũ:

~~~sql
SELECT full_name
FROM shop.customers
WHERE customer_id = ?;
~~~

sẽ thất bại khi cột `full_name` không còn. Tương tự, một báo cáo có thể vẫn truy vấn view được nhưng mong đợi alias khác. Hệ quản trị chỉ bảo đảm tính hợp lệ của những phụ thuộc **nó quản lý**, không biết đầy đủ hợp đồng ở API hoặc ứng dụng.

## 15. Bài tập thực hành

Thực hành với schema `shop` trong môi trường thử nghiệm. Các bài có thể chạy riêng trên database đã reset theo mục 2 để tránh ảnh hưởng lẫn nhau.

### Bài 1 — Vẽ đồ thị phụ thuộc

Một ứng dụng có `products(product_id, price)`, `order_items(product_id, quantity)`, view `sales_summary` tính `SUM(price * quantity)` và dashboard đọc `sales_summary`. Hãy liệt kê các cạnh phụ thuộc, sau đó dự đoán điều gì xảy ra nếu xóa `products.price`.

**Gợi ý:** view phụ thuộc vào cột `products.price` và dữ liệu bên `order_items`; dashboard phụ thuộc vào đầu ra của view. Nếu view là phụ thuộc được DBMS ghi nhận, thao tác drop cột có thể bị từ chối hoặc làm mất view khi dùng cơ chế cascade. Dashboard có thể hỏng ngay cả khi DDL đã hoàn thành.

### Bài 2 — Chọn phương án triển khai

Cần đổi `customers.full_name` thành `display_name` trong hệ thống có nhiều phiên bản backend cùng chạy. Chọn giữa:

A. Đổi tên cột ngay trong một lệnh `ALTER TABLE` và triển khai app mới sau.

B. Thêm cột mới, đồng bộ ghi dữ liệu, backfill, nâng cấp consumer, thêm constraint rồi mới loại bỏ cột cũ.

**Đáp án:** B phù hợp với yêu cầu có nhiều phiên bản đồng thời. A chỉ có thể cân nhắc khi đã xác nhận toàn bộ consumer được nâng cấp đồng bộ hoặc có thời gian dừng và tác động đã được kiểm soát.

### Bài 3 — Tìm khóa ngoại tham chiếu

Viết truy vấn PostgreSQL tìm các foreign key đang tham chiếu bảng `shop.customers` và trả tên bảng con.

~~~sql
SELECT
    con.conname AS foreign_key_name,
    con.conrelid::regclass AS child_table
FROM pg_constraint AS con
WHERE con.contype = 'f'
  AND con.confrelid = 'shop.customers'::regclass;
~~~

Kết quả mong đợi gồm `fk_orders_customer` và bảng `shop.orders`.

### Bài 4 — Phân biệt hai loại CASCADE

Phân biệt:

~~~sql
-- Điều khiển hành vi xóa HÀNG có liên quan:
FOREIGN KEY (customer_id)
REFERENCES shop.customers(customer_id)
ON DELETE CASCADE
~~~

và:

~~~sql
-- Điều khiển việc xóa ĐỐI TƯỢNG phụ thuộc trong DDL:
DROP TABLE shop.customers CASCADE;
~~~

**Đáp án:** đoạn đầu xóa các hàng con theo quy tắc foreign key khi hàng cha bị xóa. Đoạn sau là thao tác cấu trúc, có thể làm mất các đối tượng phụ thuộc do DBMS quản lý, tùy loại phụ thuộc. Hai cơ chế khác phạm vi và rủi ro.

### Bài 5 — Dự đoán hai lỗi có thể xảy ra

Giả sử bổ sung cột `phone TEXT NOT NULL` vào bảng `customers` đang có hàng, đồng thời API cũ dùng `INSERT INTO customers VALUES (...)`. Hãy nêu hai nguyên nhân có thể làm triển khai thất bại.

**Đáp án:** (1) hàng cũ chưa có `phone` nên thêm `NOT NULL` không có default/backfill phù hợp có thể thất bại; (2) `INSERT` theo vị trí ở ứng dụng cũ có thể không còn đúng số cột hoặc thứ tự. Khắc phục bằng migration nhiều giai đoạn, thêm cột nullable hoặc default có ý nghĩa, backfill, cập nhật ứng dụng dùng danh sách cột tường minh và chỉ tăng ràng buộc sau khi đã chuẩn bị dữ liệu.

## Kết luận

**Phụ thuộc đối tượng** liên kết bảng, cột, khóa ngoại, index, view, function và các consumer ở ngoài cơ sở dữ liệu. DBMS có thể bảo vệ những phụ thuộc được ghi nhận trong catalog nhưng không thể tự cập nhật mọi API, ORM mapping, báo cáo hoặc pipeline. Để thay đổi lược đồ an toàn, cần lập bản đồ tác động, hiểu hành vi `RESTRICT`/`CASCADE` và khác biệt giữa các DBMS, kiểm tra dữ liệu và khóa, rồi phối hợp thứ tự triển khai theo `Expand → Migrate → Contract` khi cần tương thích nhiều phiên bản. Tính đúng đắn của migration được quyết định bởi **dữ liệu và hành vi của toàn hệ thống sau thay đổi**, không chỉ bởi việc lệnh `ALTER TABLE` chạy thành công.
