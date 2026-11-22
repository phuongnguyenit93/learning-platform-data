# Đổi tên bảng, cột và ràng buộc

Trong **Database SQL**, cấu trúc cơ sở dữ liệu không phải bất biến. Khi nghiệp vụ đổi thuật ngữ, mô hình dữ liệu được chuẩn hóa hoặc quy ước đặt tên được thống nhất, ta có thể cần đổi tên một **bảng**, một **cột** hoặc một **ràng buộc** mà không làm thay đổi ý nghĩa của dữ liệu. Những thao tác này thuộc nhóm **DDL (Data Definition Language)**: chúng thay đổi *lược đồ (schema)*, vì vậy có tác động đến câu SQL, chương trình, báo cáo và các thành phần đang phụ thuộc vào tên cũ.

Bài học giải thích nguyên tắc đặt lại tên, minh họa trên PostgreSQL và giới thiệu cú pháp của MySQL/MariaDB, SQLite, SQL Server và Oracle Database. Điểm quan trọng là phân biệt **đổi tên một đối tượng sẵn có** với **xóa rồi tạo lại đối tượng**: chúng có hệ quả rất khác nhau đối với dữ liệu, ràng buộc, quyền truy cập, khóa và khả năng hoàn tác.

## 1. Ba đối tượng có thể cần đổi tên

Giả sử hệ thống bán hàng có bảng `customer_orders`, các cột `order_id`, `order_note`, `order_status` và ràng buộc khóa chính `pk_customer_orders`. Sau khi chuẩn hóa cách đặt tên, ta muốn:

| Đối tượng | Tên cũ | Tên mới | Ý nghĩa thay đổi |
| --- | --- | --- | --- |
| Bảng | `customer_orders` | `purchase_orders` | Tên bảng phản ánh thuật ngữ nghiệp vụ mới |
| Cột | `order_note` | `notes` | Tên thuộc tính dễ hiểu, ngắn gọn hơn |
| Cột | `order_status` | `status` | Thống nhất tên trạng thái trong ngữ cảnh bảng |
| Ràng buộc khóa chính | `pk_customer_orders` | `pk_purchase_orders` | Tên constraint khớp với tên bảng mới |
| Ràng buộc kiểm tra | `ck_customer_orders_status` | `ck_purchase_orders_status` | Tên constraint phản ánh cấu trúc hiện tại |

**Đổi tên không có nghĩa là đổi giá trị.** Ví dụ `order_note` được đổi thành `notes` thì dữ liệu ghi chú trong từng dòng vẫn có ý nghĩa như trước. Tương tự, đổi tên một ràng buộc khóa chính không khiến cột khóa chính thay đổi; tên constraint chủ yếu phục vụ quản trị, tra cứu lỗi và migration.

Tuy vậy, tên là một phần của **giao diện giữa database và ứng dụng**. SQL cũ như:

```sql
SELECT order_id, order_note
FROM customer_orders;
```

sẽ cần được điều chỉnh sau khi bảng/cột đổi tên:

```sql
SELECT order_id, notes
FROM purchase_orders;
```

Tên cũ có thể được dùng ở nhiều nơi khác ngoài câu SQL này: view, trigger, procedure, báo cáo, ORM/JPA mapping, API, ETL, quyền truy cập, script triển khai và hệ thống bên ngoài.

## 2. RENAME khác DROP, CREATE và UPDATE như thế nào?

Một thao tác đổi tên giữ nguyên **đối tượng logic** và thay đổi định danh của đối tượng đó theo khả năng của DBMS. Khi engine hỗ trợ lệnh `RENAME` trực tiếp, đây thường là cách ít xáo trộn dữ liệu hơn so với dựng lại bảng.

| Lệnh/nhóm thao tác | Tác động chính | Có nhằm thay đổi dữ liệu từng dòng không? |
| --- | --- | --- |
| `ALTER TABLE ... RENAME TO ...` | Đổi tên bảng | Không |
| `ALTER TABLE ... RENAME COLUMN ...` | Đổi tên cột | Không |
| `ALTER TABLE ... RENAME CONSTRAINT ...` | Đổi tên constraint nếu DBMS hỗ trợ | Không |
| `UPDATE ... SET ...` | Thay đổi giá trị của các dòng | **Có** |
| `DROP TABLE` | Loại bỏ bảng, có thể làm mất dữ liệu và quan hệ liên quan | **Có rủi ro mất dữ liệu** |
| `CREATE TABLE` | Tạo một bảng mới | Không tự mang dữ liệu từ bảng cũ |

Không nên dùng công thức “`DROP` bảng cũ rồi `CREATE` bảng mới” chỉ để đổi tên, vì như vậy phải tự sao chép dữ liệu, chỉ mục, khóa ngoại, quyền truy cập, trigger và các thành phần phụ thuộc. Một số DBMS **không hỗ trợ đổi tên constraint trực tiếp**, khiến bước tạo lại ràng buộc trở thành trường hợp ngoại lệ cần quy trình migration cụ thể.

### Phân biệt tên bảng và schema

Trong cú pháp như `public.customer_orders`:

- `public` là **schema** trên PostgreSQL.
- `customer_orders` là **tên bảng** bên trong schema.
- Đổi tên bảng thành `purchase_orders` **không đồng nghĩa** chuyển bảng sang schema khác.

Ví dụ PostgreSQL:

```sql
-- Đổi tên bảng nhưng vẫn nằm trong schema public:
ALTER TABLE public.customer_orders
RENAME TO purchase_orders;

-- Chuyển schema là một thao tác khác (chỉ minh họa cú pháp):
-- ALTER TABLE public.purchase_orders SET SCHEMA archive;
```

Để tránh thao tác nhầm khi có nhiều schema trùng tên bảng, nên ghi đầy đủ schema trong câu lệnh DDL mà DBMS hỗ trợ. Trước khi đổi tên, hãy kiểm tra **đúng database, schema và đối tượng**.

## 3. Thực hành trọn vẹn với PostgreSQL

Ví dụ này dùng **PostgreSQL** và chạy trong **database thực hành**. Không áp dụng nguyên văn câu lệnh tạo/đổi tên lên database đang có bảng thật trùng tên.

### Bước 1 — Tạo bảng và các ràng buộc có tên

```sql
CREATE TABLE public.customer_orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY,
    customer_id BIGINT NOT NULL,
    order_note VARCHAR(200),
    order_status VARCHAR(12) NOT NULL DEFAULT 'NEW',

    CONSTRAINT pk_customer_orders
        PRIMARY KEY (order_id),

    CONSTRAINT ck_customer_orders_status
        CHECK (order_status IN ('NEW', 'PAID', 'CANCELLED'))
);
```

Trong bảng này:

- `order_id` là cột sinh mã tự động và được bảo vệ bởi **PRIMARY KEY**.
- `customer_id` là mã khách hàng; bài này chưa tạo bảng khách hàng và chưa khai báo **FOREIGN KEY**.
- `order_note` chứa ghi chú, có thể `NULL`.
- `order_status` có giá trị mặc định `NEW`.
- `ck_customer_orders_status` chỉ cho phép một trong ba trạng thái đã liệt kê.

Chèn dữ liệu mẫu:

```sql
INSERT INTO public.customer_orders
    (customer_id, order_note, order_status)
VALUES
    (101, 'Giao giờ hành chính', 'NEW'),
    (102, 'Khách đã thanh toán', 'PAID');

SELECT order_id, customer_id, order_note, order_status
FROM public.customer_orders
ORDER BY order_id;
```

### Bước 2 — Đổi tên bảng

Cú pháp PostgreSQL:

```sql
ALTER TABLE schema_name.old_table_name
RENAME TO new_table_name;
```

Áp dụng:

```sql
ALTER TABLE public.customer_orders
RENAME TO purchase_orders;
```

Sau lệnh này, truy vấn phải dùng tên bảng mới:

```sql
SELECT order_id, customer_id, order_note, order_status
FROM public.purchase_orders
ORDER BY order_id;
```

Tên bảng ở vế phải `RENAME TO` là tên mới **trong cùng schema**; không viết `public.purchase_orders` ở vị trí tên mới trong câu lệnh PostgreSQL.

### Bước 3 — Đổi tên cột

Cú pháp:

```sql
ALTER TABLE schema_name.table_name
RENAME COLUMN old_column_name TO new_column_name;
```

Áp dụng lần lượt:

```sql
ALTER TABLE public.purchase_orders
RENAME COLUMN order_note TO notes;

ALTER TABLE public.purchase_orders
RENAME COLUMN order_status TO status;
```

Bây giờ có thể đọc cùng các bản ghi bằng tên cột mới:

```sql
SELECT order_id, customer_id, notes, status
FROM public.purchase_orders
ORDER BY order_id;
```

Tên cột thay đổi nhưng **không thay kiểu dữ liệu, vị trí giá trị, NULLability hay giá trị mặc định** chỉ vì thao tác rename. PostgreSQL cập nhật định nghĩa ràng buộc nội bộ tham chiếu cột `order_status` để ràng buộc CHECK vẫn kiểm tra cột mới `status`. **Tên** `ck_customer_orders_status` thì vẫn còn cũ cho đến khi được đổi riêng.

### Bước 4 — Đổi tên ràng buộc

PostgreSQL có cú pháp:

```sql
ALTER TABLE schema_name.table_name
RENAME CONSTRAINT old_constraint_name TO new_constraint_name;
```

Áp dụng:

```sql
ALTER TABLE public.purchase_orders
RENAME CONSTRAINT pk_customer_orders TO pk_purchase_orders;

ALTER TABLE public.purchase_orders
RENAME CONSTRAINT ck_customer_orders_status
TO ck_purchase_orders_status;
```

Đổi tên constraint **không bỏ kiểm tra ràng buộc**. Với PostgreSQL, khi đổi tên constraint `PRIMARY KEY` hoặc `UNIQUE` có chỉ mục hỗ trợ, chỉ mục liên quan cũng được đổi tên theo cơ chế của PostgreSQL. Các chỉ mục tự tạo hay đặt tên độc lập vẫn cần được kiểm tra, vì **đổi tên bảng/cột không bảo đảm mọi tên index, sequence, trigger hoặc constraint được đổi theo quy ước mới**.

### Bước 5 — Xác minh tên và dữ liệu sau thay đổi

Tra cứu tên bảng:

```sql
SELECT
    to_regclass('public.customer_orders') AS old_table,
    to_regclass('public.purchase_orders') AS new_table;
```

Ở PostgreSQL, `to_regclass(...)` trả `NULL` nếu đối tượng theo tên truyền vào không tồn tại; trường `new_table` phải nhận diện bảng mới.

Tra cứu tên cột:

```sql
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'purchase_orders'
ORDER BY ordinal_position;
```

Tra cứu tên và loại ràng buộc:

```sql
SELECT constraint_name, constraint_type
FROM information_schema.table_constraints
WHERE table_schema = 'public'
  AND table_name = 'purchase_orders'
ORDER BY constraint_name;
```

Cuối cùng, đọc dữ liệu và kiểm tra ràng buộc:

```sql
SELECT order_id, customer_id, notes, status
FROM public.purchase_orders
ORDER BY order_id;

-- Dùng một giá trị hợp lệ để quan sát CHECK vẫn có hiệu lực:
INSERT INTO public.purchase_orders
    (customer_id, notes, status)
VALUES (103, 'Đơn hàng mới', 'NEW');
```

Nếu muốn thử xem lỗi CHECK, chỉ thực hiện câu `INSERT` không hợp lệ trong môi trường thử nghiệm (và xử lý giao dịch theo mục đích kiểm tra):

```sql
-- Dự kiến bị PostgreSQL từ chối vì vi phạm CHECK.
INSERT INTO public.purchase_orders
    (customer_id, status)
VALUES (104, 'UNKNOWN');
```

Lệnh thất bại là bằng chứng ràng buộc vẫn còn hiệu lực, nhưng nếu chạy bên trong một transaction PostgreSQL chưa kết thúc, lỗi có thể khiến transaction chuyển sang trạng thái cần `ROLLBACK`. Không dùng kiểm thử lỗi chủ ý trong cùng transaction chứa các thay đổi chưa được commit mà bạn muốn giữ.

## 4. Gói đổi tên trong một transaction trên PostgreSQL

Trong thực tế, đổi tên bảng, hai cột và hai constraint thường là **một thay đổi lược đồ thống nhất**. PostgreSQL cho phép thực hiện các thao tác `ALTER TABLE ... RENAME` trên trong transaction để tránh để lại trạng thái đổi tên dở nếu một bước lỗi.

Giả sử bạn đã có bảng `public.customer_orders` ở trạng thái **trước khi đổi tên** (đừng chạy lại nếu đã hoàn thành mục 3):

```sql
BEGIN;

ALTER TABLE public.customer_orders
RENAME TO purchase_orders;

ALTER TABLE public.purchase_orders
RENAME COLUMN order_note TO notes;

ALTER TABLE public.purchase_orders
RENAME COLUMN order_status TO status;

ALTER TABLE public.purchase_orders
RENAME CONSTRAINT pk_customer_orders TO pk_purchase_orders;

ALTER TABLE public.purchase_orders
RENAME CONSTRAINT ck_customer_orders_status TO ck_purchase_orders_status;

-- Có thể đọc dữ liệu / metadata bằng tên mới ngay trong transaction:
SELECT order_id, notes, status
FROM public.purchase_orders
ORDER BY order_id;

COMMIT;
```

Nếu phát hiện sự cố **trước `COMMIT`**, dùng `ROLLBACK` để hủy toàn bộ thay đổi trong transaction. Nếu đã `COMMIT`, muốn đổi lại phải thiết kế migration đảo ngược và kiểm tra những ứng dụng/phụ thuộc đã cập nhật theo tên mới.

### Khóa và tác động khi có truy cập đồng thời

Trên PostgreSQL, `ALTER TABLE ... RENAME` thường cần **khóa mạnh trên bảng**, có thể chặn truy vấn đồng thời trong thời gian lệnh/transaction giữ khóa. Một transaction kéo dài vì thao tác kiểm tra hoặc chờ ứng dụng có thể gây gián đoạn đáng kể dù bản thân đổi tên metadata thường nhanh.

Vì thế với database đang hoạt động, cần dự kiến **thời gian triển khai, thời gian chờ khóa và hành vi của các truy vấn đang chạy**. Khả năng transaction/rollback của PostgreSQL không tự có nghĩa rằng đổi tên là thao tác “zero downtime”.

## 5. Đổi tên trên MySQL và MariaDB

**MySQL** hỗ trợ đổi tên bảng bằng `RENAME TABLE` hoặc `ALTER TABLE ... RENAME TO`:

```sql
-- MySQL:
RENAME TABLE customer_orders TO purchase_orders;

-- Một cách thay thế, không chạy cả hai lệnh liên tiếp:
-- ALTER TABLE customer_orders RENAME TO purchase_orders;
```

MySQL 8.0+ hỗ trợ `RENAME COLUMN`:

```sql
-- MySQL 8.0+; giả sử bảng đã đổi tên:
ALTER TABLE purchase_orders
RENAME COLUMN order_note TO notes;
```

Trên những phiên bản cũ hơn, thường phải dùng `CHANGE COLUMN` và **khai báo lại định nghĩa cột đầy đủ**, ví dụ:

```sql
-- Cú pháp dùng khi cần CHANGE COLUMN trên MySQL:
ALTER TABLE purchase_orders
CHANGE COLUMN order_note notes VARCHAR(200) NULL;
```

`CHANGE COLUMN` không chỉ thay tên: nếu lỡ khai báo sai kiểu, `NULL/NOT NULL`, `DEFAULT`, `COMMENT` hoặc thuộc tính khác, bạn có thể vô tình thay đổi định nghĩa cột. Luôn xem `SHOW CREATE TABLE purchase_orders;` trước khi chọn cách này. **MariaDB** có các phiên bản và mức hỗ trợ `RENAME COLUMN` riêng; cần xác định phiên bản đang dùng thay vì mặc nhiên áp dụng tài liệu MySQL.

### Đổi tên chỉ mục khác với đổi tên constraint

MySQL hỗ trợ đổi tên một **index** thông thường bằng:

```sql
-- Chỉ chạy nếu index mang tên cũ thực sự tồn tại:
ALTER TABLE purchase_orders
RENAME INDEX ux_customer_orders_reference
TO ux_purchase_orders_reference;
```

Điều này **không phải** cú pháp đổi tên mọi loại ràng buộc. Trên MySQL, `PRIMARY KEY` có tên index cố định `PRIMARY` và không thể xem là một index tùy ý có thể đổi tên như `ux_...`.

Với **FOREIGN KEY** và **CHECK** có tên, MySQL không cung cấp một cú pháp `RENAME CONSTRAINT` tổng quát tương tự PostgreSQL. Thường cần migration **loại bỏ rồi tạo lại đúng ràng buộc với tên mới**, giữ nguyên cột, điều kiện, hành vi `ON DELETE`/`ON UPDATE` và những quy định khác.

Ví dụ với **MySQL 8.0.16+** có ràng buộc CHECK tên `ck_customer_orders_status` trên cột `order_status`:

```sql
-- Chỉ áp dụng nếu CHECK cũ tồn tại và biểu thức đúng với schema thực tế:
ALTER TABLE purchase_orders
    DROP CHECK ck_customer_orders_status,
    ADD CONSTRAINT ck_purchase_orders_status
        CHECK (order_status IN ('NEW', 'PAID', 'CANCELLED'));
```

Đây là thao tác **thay ràng buộc**, khác với chỉ đổi tên metadata. Cần bảo đảm CHECK mới có ý nghĩa và mức thực thi tương đương CHECK cũ, kiểm tra dữ liệu đã có, và xem trước yêu cầu lock/rebuild. Với FOREIGN KEY, phải giữ đúng bảng/cột được tham chiếu và quy tắc cập nhật/xóa. Tránh tự động `DROP FOREIGN KEY` mà chưa xác minh rằng việc tạo lại đã được chuẩn bị đầy đủ.

**Lưu ý transaction:** nhiều lệnh DDL của MySQL/MariaDB có **implicit commit**, nên `BEGIN ... ROLLBACK` không có ý nghĩa hoàn tác tương đương ví dụ PostgreSQL. Khả năng atomic DDL của từng engine/phiên bản cũng không đồng nghĩa một nhóm lệnh đổi tên có thể rollback chung. Hãy chuẩn bị migration đảo ngược và phương án triển khai trước khi sửa lược đồ thật.

## 6. Đổi tên bảng và cột trên SQLite

SQLite hỗ trợ:

```sql
-- SQLite:
ALTER TABLE customer_orders RENAME TO purchase_orders;

ALTER TABLE purchase_orders RENAME COLUMN order_note TO notes;
```

`RENAME COLUMN` có từ SQLite **3.25.0**. SQLite lưu định nghĩa schema dưới dạng SQL; khi đổi tên cột, SQLite cố gắng cập nhật các tham chiếu có thể xác định trong bảng, chỉ mục, trigger và view. Nếu việc đổi tên khiến một tham chiếu trở nên **mơ hồ**, lệnh có thể thất bại thay vì sửa sai.

Khi đổi tên bảng, cách cập nhật các tham chiếu trong trigger/view và FOREIGN KEY có thay đổi qua phiên bản SQLite. Với SQLite **3.26.0+**, việc cập nhật tham chiếu khóa ngoại khi đổi tên bảng được cải thiện và thông thường không phụ thuộc `PRAGMA foreign_keys` như trước; `PRAGMA legacy_alter_table` có thể kích hoạt hành vi cũ.

Xem phiên bản và cấu hình liên quan:

```sql
SELECT sqlite_version();

PRAGMA foreign_keys;
PRAGMA legacy_alter_table;
```

SQLite không có câu lệnh `ALTER TABLE ... RENAME CONSTRAINT` tổng quát. Muốn thay tên ràng buộc hoặc thay định nghĩa constraint thường cần **quy trình dựng lại bảng**: tạo bảng mới với cấu trúc chuẩn, sao chép dữ liệu, tái tạo những chỉ mục/trigger/view cần thiết và chuyển đổi tên bảng. Quy trình này phải xử lý thận trọng các khóa ngoại, đối tượng phụ thuộc và trạng thái giao dịch. Không chỉ chạy `CREATE TABLE new ...; DROP TABLE old;` rồi coi như hoàn tất.

Có thể xem định nghĩa hiện tại bằng:

```sql
SELECT type, name, tbl_name, sql
FROM sqlite_schema
WHERE tbl_name IN ('customer_orders', 'purchase_orders')
ORDER BY type, name;
```

Sau một migration liên quan khóa ngoại, công cụ SQLite có câu lệnh hỗ trợ phát hiện vấn đề tham chiếu:

```sql
PRAGMA foreign_key_check;
```

Nếu truy vấn trả về dòng lỗi, cần xem lại migration và dữ liệu liên quan. Nếu không trả dòng, không phát hiện vi phạm khóa ngoại trong phạm vi kiểm tra đó.

## 7. SQL Server: đổi tên bằng sp_rename

Trong **Microsoft SQL Server**, cú pháp phổ biến là thủ tục hệ thống `sys.sp_rename`. Ví dụ với schema `dbo`:

```sql
-- SQL Server: đổi tên bảng.
EXEC sys.sp_rename
    @objname = N'dbo.customer_orders',
    @newname = N'purchase_orders',
    @objtype = N'OBJECT';

-- Sau khi bảng đã được đổi tên, đổi tên cột.
EXEC sys.sp_rename
    @objname = N'dbo.purchase_orders.order_note',
    @newname = N'notes',
    @objtype = N'COLUMN';

-- Đổi tên ràng buộc khóa chính có tên được chỉ định.
EXEC sys.sp_rename
    @objname = N'dbo.pk_customer_orders',
    @newname = N'pk_purchase_orders',
    @objtype = N'OBJECT';
```

`@objname` chỉ định tên cũ (thường kèm schema, và tên bảng khi đổi cột); `@newname` chỉ gồm **tên mới**, không kèm schema. `@objtype` giúp xác định đối tượng cần đổi, như `OBJECT` hoặc `COLUMN`. Với constraint, hãy xác minh tên chính xác và đối tượng sở hữu trước khi chạy; SQL Server quản lý constraint như một loại object.

SQL Server cũng dùng `sp_rename` để đổi tên index với `@objtype = N'INDEX'`. Việc đổi tên một ràng buộc khóa chính/unique liên kết index có các quy tắc đồng bộ tên riêng; không tự suy luận rằng đổi bảng sẽ đổi tất cả tên chỉ mục và ràng buộc.

Tra cứu sau khi đổi tên:

```sql
-- SQL Server:
SELECT
    t.name AS table_name,
    c.name AS column_name
FROM sys.tables AS t
JOIN sys.columns AS c
    ON c.object_id = t.object_id
WHERE t.object_id = OBJECT_ID(N'dbo.purchase_orders')
ORDER BY c.column_id;

SELECT name, type_desc
FROM sys.objects
WHERE parent_object_id = OBJECT_ID(N'dbo.purchase_orders')
  AND type IN ('PK', 'UQ', 'F', 'C')
ORDER BY name;
```

**Đặc biệt quan trọng:** `sp_rename` không tự cập nhật văn bản định nghĩa của tất cả stored procedure, view, trigger hay đoạn SQL lưu ở ứng dụng. Cần tra cứu phụ thuộc và cập nhật các module dùng tên cũ; một số view không schema-bound có thể cần cập nhật metadata bằng công cụ tương ứng như `sp_refreshview` sau khi định nghĩa truy vấn đã phù hợp.

Đổi tên bảng/cột không có nghĩa ứng dụng JPA/Entity Framework, script báo cáo hay stored procedure đã dùng đúng tên mới.

## 8. Oracle Database: cú pháp ALTER TABLE RENAME

Oracle Database hỗ trợ đổi tên bảng, cột và constraint:

```sql
-- Oracle Database:
ALTER TABLE customer_orders
RENAME TO purchase_orders;

ALTER TABLE purchase_orders
RENAME COLUMN order_note TO notes;

ALTER TABLE purchase_orders
RENAME CONSTRAINT pk_customer_orders TO pk_purchase_orders;
```

Ngoài `ALTER TABLE ... RENAME TO`, Oracle còn có câu lệnh `RENAME old_table TO new_table` ở những ngữ cảnh đối tượng được hỗ trợ. Với một bảng cụ thể, `ALTER TABLE` giúp thấy rõ thao tác gắn với cấu trúc bảng.

Tra cứu bảng và cột thuộc schema hiện tại bằng các view từ điển dữ liệu:

```sql
-- Oracle Database:
SELECT table_name
FROM user_tables
WHERE table_name = 'PURCHASE_ORDERS';

SELECT column_name, data_type, nullable
FROM user_tab_columns
WHERE table_name = 'PURCHASE_ORDERS'
ORDER BY column_id;

SELECT constraint_name, constraint_type, status
FROM user_constraints
WHERE table_name = 'PURCHASE_ORDERS'
ORDER BY constraint_name;
```

Oracle mặc định thường chuyển định danh **không đặt trong dấu nháy kép** thành chữ hoa trong data dictionary; vì vậy các giá trị lọc `'PURCHASE_ORDERS'` ở ví dụ viết hoa. Nếu bảng được tạo bằng quoted identifier phân biệt chữ hoa/chữ thường, phải tra cứu đúng tên đã lưu.

Một điểm khác với PostgreSQL: DDL của Oracle thông thường **tự COMMIT** trước và sau khi thực hiện thành công; không thể dùng `ROLLBACK` để hoàn tác một chuỗi rename DDL như transaction PostgreSQL. Cần có migration đảo ngược và kiểm tra các đối tượng phụ thuộc có thể trở nên không hợp lệ.

## 9. Bảng đối chiếu cú pháp giữa các DBMS

| DBMS | Đổi tên bảng | Đổi tên cột | Đổi tên ràng buộc |
| --- | --- | --- | --- |
| **PostgreSQL** | `ALTER TABLE old RENAME TO new` | `ALTER TABLE t RENAME COLUMN old TO new` | `ALTER TABLE t RENAME CONSTRAINT old TO new` |
| **MySQL 8.0+** | `RENAME TABLE old TO new` hoặc `ALTER TABLE old RENAME TO new` | `ALTER TABLE t RENAME COLUMN old TO new` | Không có rename tổng quát; phải xem từng loại ràng buộc |
| **MariaDB** | `RENAME TABLE old TO new` (với các quyền/điều kiện liên quan) | Tùy phiên bản: `RENAME COLUMN` hoặc `CHANGE COLUMN` | Tùy loại và phiên bản; thường phải tái tạo |
| **SQLite 3.25+** | `ALTER TABLE old RENAME TO new` | `ALTER TABLE t RENAME COLUMN old TO new` | Không có `RENAME CONSTRAINT` tổng quát; thường dựng lại bảng |
| **SQL Server** | `sp_rename` với `OBJECT` | `sp_rename` với `COLUMN` | `sp_rename` với `OBJECT` cho constraint được hỗ trợ |
| **Oracle Database** | `ALTER TABLE old RENAME TO new` | `ALTER TABLE t RENAME COLUMN old TO new` | `ALTER TABLE t RENAME CONSTRAINT old TO new` |

Bảng này là bản đồ cú pháp cho các phiên bản thường dùng, không thay thế việc xác minh **engine, phiên bản và điều kiện hỗ trợ**. Chú ý MySQL và MariaDB là hai sản phẩm riêng; không lấy phiên bản của một hệ để suy luận khả năng của hệ kia.

Một số nguyên tắc dùng được ở mọi DBMS:

1. Xác định đối tượng cũ có tồn tại và tên mới chưa bị sử dụng hoặc xung đột trong phạm vi liên quan.
2. Xác định câu lệnh đổi tên là thao tác metadata trực tiếp hay cần dựng lại đối tượng.
3. Xem engine có tự cập nhật các tham chiếu nội bộ nào, rồi kiểm tra lại bằng metadata.
4. Tìm và cập nhật **mọi SQL phụ thuộc tên cũ** ở bên ngoài cơ chế quản lý nội bộ của DBMS.
5. Chuẩn bị cách đảo ngược/khôi phục phù hợp với cơ chế transaction của DBMS.

## 10. Những phụ thuộc phải xem trước khi đổi tên

Một bảng hay cột hiếm khi tồn tại độc lập trong hệ thống thật. Cần phân biệt **tham chiếu mà DBMS quản lý bằng metadata** với **văn bản SQL hoặc cấu hình bên ngoài**.

| Thành phần | Có thể bị tác động thế nào? | Việc cần làm |
| --- | --- | --- |
| **FOREIGN KEY** | Tham chiếu khóa giữa các bảng phải vẫn đúng; khả năng tự sửa khác theo engine | Tra cứu khóa ngoại, kiểm tra dữ liệu tham chiếu sau đổi tên |
| **PRIMARY KEY / UNIQUE / CHECK** | Quy tắc có thể tiếp tục hiệu lực nhưng tên constraint cũ vẫn tồn tại | Xác minh constraint, tên index liên quan và dữ liệu hợp lệ |
| **Index / sequence / trigger** | Tên hoặc định nghĩa có thể còn dùng quy ước cũ | Tra cứu catalog; đổi tên riêng nếu thật sự cần |
| **View / materialized view** | Một số DBMS cập nhật liên kết nội bộ, một số định nghĩa/query có thể hỏng | Kiểm tra kết quả và tên cột mà view công bố |
| **Stored procedure / function** | Văn bản định nghĩa có thể còn chứa tên cũ | Tìm các tham chiếu và cập nhật mã SQL |
| **Ứng dụng / ORM** | Annotation, mapping, native SQL và migration có thể trỏ tên cũ | Cập nhật đồng bộ với phiên bản ứng dụng |
| **Báo cáo / ETL / dashboard** | Câu SQL, lịch chạy và nguồn dữ liệu có thể lỗi khi triển khai | Thống kê tác vụ phụ thuộc và kiểm tra truy vấn |
| **Quyền truy cập / audit** | Quyền có thể gắn với object, nhưng rule hoặc script theo tên có thể cần cập nhật | Đối chiếu quyền, audit và cấu hình theo hệ |
| **Replica / hệ thống tích hợp** | Công cụ đồng bộ có thể phụ thuộc cấu trúc/tên cột | Kiểm tra quy tắc mapping và khả năng tiếp nhận schema mới |

**Ví dụ về view:** PostgreSQL có thể giữ được liên kết nội bộ của một view tới cột vừa đổi tên. Nhưng **tên cột đầu ra của view** có thể vẫn là alias/tên cũ được khai báo ở thời điểm tạo view. Do vậy, ngay cả khi `SELECT * FROM view_name` vẫn chạy, giao diện mà view cung cấp cho ứng dụng chưa chắc đã đổi theo ý định.

### Đừng nhầm tên ràng buộc với nội dung ràng buộc

Ví dụ `ck_customer_orders_status` là tên của một CHECK constraint, còn biểu thức `status IN ('NEW', 'PAID', 'CANCELLED')` mới là **quy tắc kiểm tra**. Đổi tên constraint chỉ sửa nhãn quản trị, không thay đổi tập giá trị hợp lệ.

Nếu muốn đổi từ `status IN (...)` sang quy tắc cho phép thêm trạng thái `RETURNED`, đó là **thay định nghĩa ràng buộc**, không phải đổi tên đơn thuần; cần xem dữ liệu hiện tại và cách DDL tương ứng của DBMS.

Tương tự, việc đổi tên constraint `fk_orders_customer` **không đổi** bảng/cột được khóa ngoại tham chiếu. Không dùng rename để kỳ vọng thay đổi ý nghĩa quan hệ.

## 11. Thứ tự migration và lựa chọn triển khai

Với thay đổi lược đồ trên một hệ thống đã có người dùng, có thể triển khai theo chuỗi công việc sau.

### 11.1. Trước khi đổi tên

1. **Xác định đầu vào:** database, schema, tên bảng/cột/constraint hiện tại và tên đích.
2. **Kiểm tra va chạm:** không có bảng/cột/constraint khác trùng tên trong phạm vi namespace mà DBMS quy định.
3. **Thống kê phụ thuộc:** truy vấn database catalog, tìm trong mã nguồn ứng dụng, script, báo cáo, tác vụ định kỳ và mapping ORM.
4. **Xác định tương thích phiên bản:** phiên bản DBMS, có hỗ trợ rename trực tiếp hay phải tái tạo object; giới hạn khóa và DDL transaction.
5. **Chuẩn bị migration tiến/lùi:** có cách hoàn tác khi các bước lỗi, dữ liệu được bảo vệ và hệ thống có kế hoạch triển khai tương ứng.

### 11.2. Khi đổi tên

Trong môi trường thử nghiệm, chạy đúng DDL trên một schema tương tự rồi kiểm tra:

- Tên cũ không còn ở vị trí mong đợi, tên mới có thể truy cập.
- Số dòng và các giá trị dữ liệu quan trọng không thay đổi chỉ vì rename.
- `PRIMARY KEY`, `UNIQUE`, `CHECK`, `FOREIGN KEY` còn hoạt động như yêu cầu.
- Các view, procedure và các truy vấn ứng dụng đều dùng tên phù hợp.
- Log và thời gian chạy phản ánh chi phí khóa/rebuild có thể chấp nhận trong môi trường triển khai.

Đối với hệ đang chạy liên tục, **rename phá vỡ các client còn dùng tên cũ** ngay khi có hiệu lực. Có thể cần triển khai ứng dụng và database trong một cửa sổ thay đổi được điều phối. Nếu cần hỗ trợ phiên bản ứng dụng cũ và mới đồng thời, thiết kế migration nhiều giai đoạn bằng cột/bảng tương thích, view hoặc cơ chế chuyển tiếp phù hợp, thay vì giả định một lệnh rename tức thời bảo đảm không gián đoạn.

### 11.3. Sau khi đổi tên

- Ghi lại DDL đã chạy, phiên bản DBMS và kết quả xác minh.
- Cập nhật migration history, tài liệu lược đồ, sơ đồ quan hệ, ORM và script triển khai.
- Kiểm tra tác vụ nền, integration và báo cáo theo thời điểm chúng thực sự chạy.
- Nếu index/constraint còn tên cũ, quyết định có đổi tên tiếp không; không thực hiện thay đổi chỉ để “đẹp” nếu việc đó phát sinh rủi ro không cần thiết.
- Với DBMS có implicit commit, xem migration đảo ngược là một **thay đổi mới phải kiểm tra**, không phải một lệnh `ROLLBACK` đơn giản.

## 12. Tên định danh, chữ hoa/chữ thường và SQL động

Tên bảng, cột và constraint là **identifier**. Chúng khác với **giá trị chuỗi**:

```sql
-- PostgreSQL: tên cột là identifier, chuỗi bên phải là literal dữ liệu.
SELECT notes
FROM public.purchase_orders
WHERE status = 'NEW';
```

Trong PostgreSQL, identifier đặt trong dấu nháy kép như `"OrderStatus"` giữ nguyên chữ hoa/thường đã khai báo; identifier không trích dẫn thường được chuẩn hóa về chữ thường. Trong Oracle, identifier không trích dẫn thường được chuyển thành chữ hoa. MySQL có sự khác biệt theo hệ điều hành và cấu hình `lower_case_table_names` đối với tên bảng; SQL Server chịu ảnh hưởng collation/cấu hình đối tượng. Vì vậy **đừng chỉ đổi kiểu chữ của tên** rồi mặc định mọi môi trường nhận đó là cùng một identifier.

Nên dùng tên dễ hiểu, nhất quán, không có khoảng trắng, ít phụ thuộc cách viết hoa/thường và tránh từ khóa SQL. Nếu cần quote identifier, hãy dùng **cú pháp của DBMS**: PostgreSQL/Oracle thường dùng `"..."`, MySQL thường dùng backtick, SQL Server hỗ trợ `[...]` hoặc dấu nháy kép khi cấu hình tương ứng.

### Đổi tên từ đầu vào ứng dụng

Một placeholder `?` hay `$1` trong prepared statement thường **chỉ bind giá trị dữ liệu**, không thay thế được tên bảng/cột trong câu lệnh DDL. Ví dụ không thể coi:

```sql
-- KHÔNG phải cách dùng placeholder hợp lệ cho identifier trong SQL thông thường:
ALTER TABLE ? RENAME TO ?;
```

là phương án đổi tên an toàn.

Nếu có công cụ migration nhận tên đối tượng động, hãy kiểm tra tên trong **danh sách hợp lệ đã xác định**, xác minh đúng schema/đối tượng và sử dụng cơ chế **quote identifier** phù hợp với driver/DBMS. Không nối trực tiếp chuỗi do người dùng nhập vào câu DDL, vì tên đối tượng và giá trị dữ liệu được parser SQL xử lý bằng quy tắc khác nhau.

## 13. Lỗi thường gặp và hướng xử lý

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| Báo “table does not exist” sau rename | Ứng dụng vẫn truy vấn tên cũ hoặc sai schema | Tra cứu catalog và cập nhật các SQL phụ thuộc |
| Báo “column does not exist” | Câu `SELECT`/`WHERE`/ORM còn dùng tên cột cũ | Cập nhật mapping, view, procedure và query |
| Báo “duplicate relation/name” | Tên mới đã được dùng hoặc trùng trong namespace của DBMS | Kiểm tra tên đích trước khi chạy DDL |
| Không nhận cú pháp `RENAME COLUMN` | DBMS/phiên bản không hỗ trợ cú pháp đó | Dùng cú pháp phiên bản phù hợp; với MySQL cũ cân nhắc `CHANGE COLUMN` |
| Không nhận `RENAME CONSTRAINT` | Engine không hỗ trợ rename trực tiếp | Xây dựng migration tái tạo constraint đúng loại |
| Vi phạm constraint sau migration | Ràng buộc tạo lại khác biểu thức/quy tắc cũ hoặc dữ liệu không hợp lệ | So sánh định nghĩa cũ/mới và kiểm tra dữ liệu |
| Lệnh `ALTER TABLE` bị chờ lâu | Đang tranh chấp khóa, hoặc DBMS phải rebuild | Kiểm tra phiên đang giữ khóa, khả năng online DDL và cửa sổ triển khai |
| `ROLLBACK` không hoàn tác rename | DBMS dùng implicit commit DDL | Dùng migration đảo ngược được chuẩn bị từ trước |
| View chạy nhưng vẫn trả tên cột cũ | View giữ tên đầu ra/alias khi đã được tạo | Xác minh và điều chỉnh giao diện của view |
| Lỗi do tên có chữ hoa hoặc ký tự đặc biệt | Quoted identifier và case folding khác nhau | Kiểm tra tên thực tế trong catalog và quote đúng dialect |

Đặc biệt khi gặp lỗi, **không chạy lại một migration rename một cách mù quáng**: lệnh thứ nhất có thể đã thành công và đối tượng cũ đã không còn. Hãy đọc trạng thái thực tế rồi mới quyết định chạy tiếp, đảo ngược hay sửa script.

## 14. Bài tập thực hành

### Bài 1 — Chọn đúng loại thay đổi

Cho các yêu cầu sau, hãy chọn thao tác thích hợp:

1. `orders` cần đổi tên thành `purchase_orders`, dữ liệu giữ nguyên.
2. Cột `created_time` cần đổi tên thành `created_at`.
3. Ràng buộc `ck_orders_status` đổi tên thành `ck_purchase_orders_status`, không đổi biểu thức CHECK.
4. Chỉ sửa `status = 'NEW'` thành `status = 'PAID'` của một đơn hàng.
5. Bổ sung giá trị `RETURNED` vào tập trạng thái được CHECK cho phép.

**Gợi ý:** ba tình huống đầu là đổi tên đối tượng; tình huống 4 là `UPDATE` dữ liệu; tình huống 5 thay đổi **nội dung** constraint và cần DDL thích hợp theo DBMS.

### Bài 2 — Viết DDL cho PostgreSQL

Bảng `public.sales_orders` có cột `memo` và ràng buộc `ck_sales_orders_amount`. Hãy viết lệnh:

- Đổi bảng thành `invoices`.
- Đổi cột `memo` thành `notes`.
- Đổi tên ràng buộc thành `ck_invoices_amount`.

**Gợi ý đáp án:**

```sql
ALTER TABLE public.sales_orders RENAME TO invoices;

ALTER TABLE public.invoices RENAME COLUMN memo TO notes;

ALTER TABLE public.invoices
RENAME CONSTRAINT ck_sales_orders_amount TO ck_invoices_amount;
```

Giả định các đối tượng nguồn thực sự tồn tại và tên đích chưa bị sử dụng. Vì mục tiêu chỉ là đổi tên, biểu thức CHECK không cần viết lại.

### Bài 3 — Hiểu giới hạn khi chuyển DBMS

Một migration PostgreSQL chứa:

```sql
ALTER TABLE purchases
RENAME CONSTRAINT ck_purchases_total TO ck_orders_total;
```

Bạn được yêu cầu áp dụng nguyên văn trên SQLite và MySQL. Vì sao không thể coi đây là SQL di động? Hãy nêu chiến lược phù hợp cho mỗi hệ.

**Gợi ý:** SQLite không có `RENAME CONSTRAINT` tổng quát và có thể phải dựng lại bảng; MySQL thường cần loại bỏ rồi thêm lại constraint theo loại của nó. Mỗi thay đổi phải giữ đúng quy tắc nghiệp vụ và tính toàn vẹn tham chiếu.

### Bài 4 — Kiểm tra migration hoàn tất

Sau khi đổi `customer_orders` thành `purchase_orders` và `order_note` thành `notes`, hãy viết hoặc mô tả cách xác minh:

1. Bảng mới tồn tại, bảng cũ không còn tên đó.
2. Cột `notes` tồn tại và có kiểu dữ liệu tương ứng.
3. Hai bản ghi thử vẫn có giá trị ghi chú như trước.
4. Constraint khóa chính và CHECK còn đúng.
5. Các client/ứng dụng sử dụng tên mới.

**Gợi ý:** đối chiếu catalog (`information_schema` hoặc bảng hệ thống của DBMS), `SELECT` bản ghi, danh sách constraint và các đường truy cập ứng dụng. Không xem chỉ một câu `SELECT` thành công là bằng chứng đủ cho toàn bộ hệ thống.

### Bài 5 — Sắp xếp kế hoạch triển khai

Hệ thống có web API, batch job ban đêm và một view cho báo cáo. Cả ba đang dùng cột `order_note`. Bạn muốn đổi cột thành `notes`. Hãy đề xuất thứ tự công việc để tránh đến đêm batch mới phát sinh lỗi.

**Gợi ý:** tìm phụ thuộc trước; sửa/triển khai chương trình đúng thời điểm; thử migration trên môi trường tương tự; kiểm tra view và batch job; xác nhận ứng dụng đã chuyển sang tên mới; giữ kế hoạch đảo ngược phù hợp. Nếu không thể chuyển đồng thời, thiết kế giai đoạn tương thích thay vì đổi tên đột ngột.

## 15. Tự đánh giá kết quả

Sau bài thực hành, bạn nên giải thích được:

- Khi nào nên **RENAME** trực tiếp và khi nào DBMS buộc phải **tái tạo ràng buộc hoặc bảng**.
- Cú pháp đổi tên bảng, cột và constraint của DBMS đang dùng.
- Vì sao đổi tên bảng/cột không nhất thiết đổi tên chỉ mục, ràng buộc hoặc mọi tham chiếu trong ứng dụng.
- Vì sao **DDL transaction**, khóa và rollback khác nhau giữa PostgreSQL, MySQL/MariaDB, SQL Server, SQLite và Oracle.
- Cách tra cứu tên, kiểu cột, constraint và dữ liệu sau migration.
- Vì sao một thay đổi tên cần **kế hoạch cập nhật các thành phần phụ thuộc** và kiểm tra thực tế.

Đổi tên bảng, cột và ràng buộc là một phần bình thường của quá trình tiến hóa lược đồ SQL. Câu lệnh có thể rất ngắn, nhưng để thay đổi an toàn cần biết **đối tượng nào đang được đổi, những thành phần nào phụ thuộc vào tên đó và DBMS bảo đảm điều gì trong quá trình DDL**.
