# Default privileges và quyền của đối tượng tạo trong tương lai trong PostgreSQL

Khi triển khai một hệ thống PostgreSQL, việc cấp quyền bằng `GRANT` cho những bảng đang tồn tại chưa đủ. Ngày mai, đội phát triển chạy migration tạo bảng `orders_2027`, view `order_summary` hoặc sequence `invoice_no_seq`. **Ai có quyền đọc, ghi hoặc gọi những đối tượng mới ấy?** Nếu không có chính sách rõ ràng, ứng dụng có thể đột ngột gặp lỗi `permission denied`, hoặc tệ hơn: một function mới được tạo và có quyền `EXECUTE` rộng hơn mong muốn.

PostgreSQL giải quyết phần **quyền mặc định cho các đối tượng sẽ được tạo trong tương lai** bằng lệnh:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE app_owner
    IN SCHEMA app
GRANT SELECT ON TABLES TO app_reader;
```

Đọc câu lệnh theo đúng nghĩa:

> Khi **role `app_owner`** tạo **bảng hoặc đối tượng thuộc nhóm TABLES** trong schema `app` **từ sau thời điểm thiết lập**, hãy tự cấp quyền `SELECT` trên đối tượng đó cho role `app_reader`.

Điều này **không** có nghĩa:

- Mọi bảng **đã tồn tại** trong schema `app` lập tức được cấp quyền.
- Mọi role cùng nhóm với `app_owner` khi tự tạo bảng đều được hưởng default privileges của `app_owner`.
- Role `app_reader` có quyền truy cập schema nếu chưa có `USAGE ON SCHEMA`.
- Quyền `SELECT` vượt qua được Row-Level Security (RLS), các chính sách truy cập hoặc ràng buộc khác.
- Lệnh cấu hình quyền mặc định thay thế việc giám sát quyền thực tế sau migration.

Bài này đi sâu vào **`ALTER DEFAULT PRIVILEGES`, `FOR ROLE`, `IN SCHEMA`, quyền toàn cục so với quyền theo schema, `PUBLIC`, quyền trên bảng/sequence/function/type/schema, tác động của `SET ROLE`, kiểm tra với `\\ddp` và `pg_default_acl`, migration an toàn, quyền ứng dụng, RLS và các bài thực hành PostgreSQL**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt `GRANT` trên đối tượng hiện có, `GRANT ... ON ALL ... IN SCHEMA` và `ALTER DEFAULT PRIVILEGES`.
2. Giải thích tại sao default privileges chỉ áp dụng vào **thời điểm tạo đối tượng**, không hồi tố.
3. Xác định **object creator/current role** quyết định bộ default privileges nào được áp dụng.
4. Sử dụng `FOR ROLE`, `IN SCHEMA` và cú pháp `GRANT`/`REVOKE` cho đối tượng tương lai.
5. Phân biệt cấu hình default privileges **global** và **per-schema**; hiểu vì sao không thể dùng per-schema `REVOKE` để xóa một default `GRANT` có phạm vi global.
6. Hiểu vai trò của `PUBLIC` và mặc định PostgreSQL về `EXECUTE` trên function, `USAGE` trên type.
7. Thiết kế quyền tương lai riêng cho **TABLES, SEQUENCES, FUNCTIONS/ROUTINES, TYPES và SCHEMAS**.
8. Cấp quyền tương lai theo nguyên tắc *least privilege*, tránh `GRANT ALL` không cần thiết.
9. Hiểu tại sao cấp `INSERT` trên bảng chưa chắc đã đủ cho code dùng `nextval()` hoặc `UPDATE ... WHERE`.
10. Kiểm tra chính sách hiện tại bằng `psql \\ddp`, catalog `pg_default_acl` và quyền thực tế bằng hàm `has_*_privilege`.
11. Thiết kế quy trình deploy với migration role, owner role, `SET ROLE` và quyền trên schema.
12. Phân biệt quyền của bảng gốc, view, partition, sequence, routine, type và schema.
13. Hiểu quyền mặc định không thay thế `GRANT USAGE ON SCHEMA`, RLS hoặc kiểm tra quyền của `SECURITY DEFINER`.
14. Viết regression tests bắt lỗi privilege drift sau khi deploy.
15. Có runbook chẩn đoán lỗi `42501 insufficient_privilege` khi object mới xuất hiện.

## 2. Mô hình ba lớp quyền trong PostgreSQL

Khi ứng dụng truy cập một bảng, cần phân biệt ba câu hỏi:

1. **Có được kết nối tới database không?** Ví dụ quyền `CONNECT ON DATABASE`.
2. **Có được truy cập namespace/schema không?** Ví dụ `USAGE ON SCHEMA`.
3. **Có quyền phù hợp trên object không?** Ví dụ `SELECT ON TABLE`, `USAGE ON SEQUENCE` hoặc `EXECUTE ON FUNCTION`.

Một luồng truy cập:

```text
Client / role app_reader
        |
        v
Database (CONNECT)
        |
        v
Schema app (USAGE)
        |
        v
Table app.orders (SELECT)
        |
        v
Row-Level Security / view semantics (nếu áp dụng)
        |
        v
Rows thực tế được phép trả về
```

`ALTER DEFAULT PRIVILEGES` chủ yếu điều khiển **quyền khởi tạo trên đối tượng mới ở lớp thứ ba**, cùng khả năng thiết lập quyền mặc định cho các schema sẽ tạo trong tương lai. Nó không tự cấp mọi quyền ở những lớp còn lại.

### 2.1. Quyền trên schema và quyền trên bảng là độc lập

Ví dụ:

```sql
GRANT USAGE ON SCHEMA app TO app_reader;
```

cho phép role tìm/truy cập tên object trong schema khi đáp ứng các quyền khác. Nó **không tự cho phép SELECT mọi bảng** của schema.

Ngược lại:

```sql
GRANT SELECT ON app.orders TO app_reader;
```

không tự cấp `USAGE ON SCHEMA app` nếu role chưa có quyền này.

### 2.2. Role được cấp quyền nhưng chưa chắc thấy mọi row

Một bảng bật RLS có thể chỉ cho phép đọc một số row. Default `GRANT SELECT` không tự bỏ qua RLS. Tương tự, view có semantics và quyền theo owner/invoker cần được xét riêng.

### 2.3. Role sở hữu object có vị trí đặc biệt

Object owner có các khả năng quản trị đối tượng gắn với ownership. Mục đích của default privileges thường là **cấp quyền cần thiết cho các role khác** khi owner tạo object mới, chứ không phải thay đổi khái niệm ownership.

## 3. Ba lệnh hay bị nhầm: GRANT, ALL và DEFAULT

Giả sử schema `app` hiện đã có bảng `customers`, `orders`, nhưng sắp có bảng `invoices`.

| Câu lệnh | Đối tượng tác động | Thời điểm |
| --- | --- | --- |
| `GRANT SELECT ON app.orders TO app_reader` | Bảng `orders` được chỉ định | Ngay lúc chạy |
| `GRANT SELECT ON ALL TABLES IN SCHEMA app TO app_reader` | Những đối tượng kiểu TABLES **đang tồn tại** trong schema | Ngay lúc chạy |
| `ALTER DEFAULT PRIVILEGES ... GRANT SELECT ON TABLES TO app_reader` | Các đối tượng thuộc loại này **được role chỉ định tạo sau này** | Khi CREATE object tương lai |

### 3.1. Hai lệnh thường phải dùng cùng nhau

Khi bắt đầu cấu hình quyền cho một ứng dụng đã có dữ liệu:

```sql
-- Cho những bảng đã có:
GRANT SELECT ON ALL TABLES IN SCHEMA app TO app_reader;

-- Cho những bảng sẽ được app_owner tạo về sau:
ALTER DEFAULT PRIVILEGES
    FOR ROLE app_owner
    IN SCHEMA app
GRANT SELECT ON TABLES TO app_reader;
```

Trong ví dụ này, các role/schema phải tồn tại và người thực thi phải có quyền tương ứng. Đây là **mẫu thiết kế**, không chạy ngay nếu chưa chuẩn bị môi trường.

### 3.2. Chỉ dùng GRANT ON ALL không đủ cho tương lai

Một tuần sau migration:

```sql
CREATE TABLE app.new_feature (...);
```

Bảng mới **không tự nhận** GRANT ON ALL TABLES đã chạy tuần trước. Nếu default privileges không cấu hình cho **creator role thực tế**, app_reader có thể bị từ chối SELECT.

### 3.3. Chỉ dùng ALTER DEFAULT PRIVILEGES không đủ cho quá khứ

Những bảng hiện có giữ ACL của chúng. PostgreSQL không quét lại và thay quyền của toàn bộ object cũ mỗi khi bạn sửa cấu hình default privileges.

## 4. Cú pháp ALTER DEFAULT PRIVILEGES

Cấu trúc:

```sql
ALTER DEFAULT PRIVILEGES
    [FOR ROLE creator_role [, ...]]
    [IN SCHEMA schema_name [, ...]]
GRANT privileges ON object_type TO grantee_role [, ...];
```

Hoặc:

```sql
ALTER DEFAULT PRIVILEGES
    [FOR ROLE creator_role [, ...]]
    [IN SCHEMA schema_name [, ...]]
REVOKE privileges ON object_type FROM grantee_role [, ...];
```

Các dấu `[...]` trong hai khối trên là **ký hiệu cú pháp để giải thích phần tùy chọn**, không phải ký tự SQL bạn nhập nguyên văn.

### 4.1. FOR ROLE

Chỉ định role **sẽ tạo object**. Nếu bỏ `FOR ROLE`, PostgreSQL sử dụng role hiện hành đang thực thi lệnh.

```sql
ALTER DEFAULT PRIVILEGES FOR ROLE app_owner
GRANT SELECT ON TABLES TO app_reader;
```

Không được hiểu rằng `app_owner` là role sẽ **nhận** quyền SELECT; role nhận quyền ở sau `TO` là `app_reader`.

### 4.2. IN SCHEMA

Giới hạn nơi các object **sẽ được tạo**. Đây là cấu hình riêng cho schema được chỉ định:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE app_owner
    IN SCHEMA app
GRANT SELECT ON TABLES TO app_reader;
```

Nếu bỏ `IN SCHEMA`, cấu hình mặc định có phạm vi **toàn cục đối với các object do creator role tạo**, bất kể schema, trừ các khác biệt theo loại object.

### 4.3. GRANT và REVOKE

- `GRANT` bổ sung quyền cho những object tương lai.
- `REVOKE` thay đổi cấu hình mặc định trong phạm vi tương ứng; có những quy tắc quan trọng khi global và per-schema cùng tồn tại.

Đây **không phải** các câu DML hoặc thao tác cập nhật ACL cho những object hiện có.

### 4.4. Những object types thường dùng

```sql
ON TABLES
ON SEQUENCES
ON FUNCTIONS
ON ROUTINES
ON TYPES
ON SCHEMAS
```

Phạm vi hỗ trợ và đặc tính của từng nhóm cần đối chiếu với phiên bản PostgreSQL trong môi trường. Ở đây tập trung vào các loại phổ biến khi triển khai ứng dụng.

## 5. Bảng tổng hợp quyền theo loại object

| Object | Quyền phổ biến | Ví dụ mục đích |
| --- | --- | --- |
| TABLES | `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, `REFERENCES`, `TRIGGER` | Đọc/ghi/khai báo ràng buộc hoặc trigger phù hợp |
| SEQUENCES | `USAGE`, `SELECT`, `UPDATE` | Gọi `nextval`, `currval`, `setval` theo quyền tương ứng |
| FUNCTIONS / ROUTINES | `EXECUTE` | Gọi hàm hoặc thủ tục được phép |
| TYPES | `USAGE` | Tham chiếu/dùng kiểu dữ liệu, domain, type tương ứng |
| SCHEMAS | `USAGE`, `CREATE` | Tìm tên object hoặc tạo object trong schema |

Một số phiên bản PostgreSQL còn có quyền bảng mới được bổ sung, như quyền phục vụ maintenance; đừng sao chép một câu `GRANT ALL` mà không biết nó bao gồm những quyền nào ở phiên bản đang chạy.

### 5.1. Vì sao không nên GRANT ALL theo thói quen?

`GRANT ALL PRIVILEGES ON TABLES` có thể cấp cả quyền không cần cho ứng dụng đọc/ghi đơn giản, chẳng hạn `TRUNCATE`, `REFERENCES` hoặc `TRIGGER` tùy loại object và phiên bản.

Nên bắt đầu từ **SELECT riêng cho reader**, và các quyền viết thật sự cần cho writer.

### 5.2. INSERT không đồng nghĩa quyền đọc

`GRANT INSERT ON TABLE` không tự cấp `SELECT`. Trong PostgreSQL, một câu `UPDATE ... WHERE some_column=...` hoặc `INSERT ... RETURNING column` có thể cần thêm SELECT trên các cột được đọc/return.

Do đó nên xét **câu SQL thật của ứng dụng**, không chỉ tên thao tác CRUD.

## 6. Thời điểm áp dụng: khi object được tạo

Quy trình:

```text
T0: app_owner tạo app.old_table
      -> Quyền được xác định tại T0

T1: ALTER DEFAULT PRIVILEGES FOR ROLE app_owner
    IN SCHEMA app GRANT SELECT ON TABLES TO app_reader
      -> Đổi chính sách cho CREATE về sau

T2: app_owner tạo app.new_table
      -> PostgreSQL khởi tạo ACL theo chính sách tại T2

T3: REVOKE default SELECT trong policy
      -> Chỉ thay policy cho các CREATE sau T3

T4: app_owner tạo app.third_table
      -> Không còn grant theo rule đã bị bỏ
```

**Điều quan trọng:** ACL đã được gán cho `new_table` tại T2 **không tự mất** khi policy default bị REVOKE ở T3.

### 6.1. GRANT trên object vẫn là trạng thái độc lập

Sau khi tạo table, owner hoặc người có grant option có thể:

```sql
GRANT SELECT ON app.new_table TO another_reader;
REVOKE SELECT ON app.new_table FROM app_reader;
```

Các lệnh này điều chỉnh quyền của **object cụ thể**, không sửa policy default.

### 6.2. ALTER OWNER không tạo lại ACL mặc định

Nếu một table được `app_deployer` tạo rồi đổi owner sang `app_owner`, PostgreSQL **không coi đó là CREATE lại bởi app_owner** để áp dụng default ACL của app_owner. Cần thiết kế GRANT hoặc recreation/migration phù hợp, không kỳ vọng `ALTER TABLE ... OWNER TO` sửa lịch sử tạo object.

## 7. Lab nhiều role: mục tiêu và điều kiện

Ta tạo:

- `acl_owner`: role sở hữu schema và tạo objects.
- `acl_reader`: role chỉ đọc tài liệu/bảng.
- `acl_writer`: role đọc/ghi bảng theo các quyền được cấp.
- `acl_deployer`: role mô phỏng migration runner, có thể tạo object.
- `acl_lab`: schema chính.
- `acl_else`: schema khác để kiểm tra global/per-schema.

**Điều kiện:** đoạn tạo role/schema dành cho database thử nghiệm và người có quyền quản lý role/schema, ví dụ superuser của môi trường lab. Nếu không có quyền `CREATEROLE` hoặc không được phép `SET ROLE` các role thử nghiệm, không chạy phần setup và chuyển sang phân tích các câu lệnh mẫu với DBA.

### 7.1. Tạo roles, schema và quyền namespace

```sql
-- Chỉ chạy một lần trong database thử nghiệm sạch.
CREATE ROLE acl_owner NOLOGIN;
CREATE ROLE acl_reader NOLOGIN;
CREATE ROLE acl_writer NOLOGIN;
CREATE ROLE acl_deployer NOLOGIN;

-- Với role đủ quyền, tạo schema thuộc owner được chỉ định.
CREATE SCHEMA acl_lab AUTHORIZATION acl_owner;
CREATE SCHEMA acl_else AUTHORIZATION acl_owner;

-- Cho phép reader/writer tìm object trong schema.
GRANT USAGE ON SCHEMA acl_lab TO acl_reader, acl_writer;
GRANT USAGE ON SCHEMA acl_else TO acl_reader, acl_writer;

-- Cho deployer quyền tạo object (mô phỏng migration runner).
GRANT CREATE ON SCHEMA acl_lab TO acl_deployer;

-- Deployer là thành viên của owner role để mô phỏng việc
-- có thể SET ROLE acl_owner trong một pipeline triển khai.
GRANT acl_owner TO acl_deployer;
```

**Lưu ý:** bản lab giả định tài khoản quản trị có đủ quyền `SET ROLE` tới các role đó. Trên hệ thống thật, tên role, cơ chế membership và quyền tạo role phải theo chính sách của tổ chức, không cấp role owner rộng cho ứng dụng runtime.

### 7.2. Tại sao role NOLOGIN vẫn cần thiết?

`NOLOGIN` không đăng nhập trực tiếp, nhưng vẫn có thể:

- Sở hữu database objects.
- Nhận GRANT.
- Là target của `SET ROLE` nếu session có quyền.
- Được cấp làm role/group cho role đăng nhập khác.

Mô hình này thường giúp tách **ownership** khỏi **định danh đăng nhập**.

### 7.3. Không cấp trực tiếp table privileges trước thử nghiệm

Chúng ta mới cấp `USAGE ON SCHEMA`. Quyền SELECT/INSERT trên tables sẽ được thử riêng để quan sát tác động của default privileges.

## 8. Tạo một bảng trước khi cấu hình default privileges

Chạy dưới role sẽ sở hữu object:

```sql
SET ROLE acl_owner;

CREATE TABLE acl_lab.before_default (
    id bigint PRIMARY KEY,
    note text NOT NULL
);

INSERT INTO acl_lab.before_default(id, note)
VALUES (1, 'created before policy');

RESET ROLE;
```

Kiểm tra:

```sql
SELECT
    has_schema_privilege('acl_reader', 'acl_lab', 'USAGE')
        AS reader_can_use_schema,
    has_table_privilege(
        'acl_reader', 'acl_lab.before_default', 'SELECT'
    ) AS reader_can_select_old_table;
```

Kỳ vọng theo lab mới, chưa có global default/GRANT nào khác:

- `reader_can_use_schema = true`.
- `reader_can_select_old_table = false`.

### 8.1. Vì sao dùng hàm has_table_privilege?

Nó kiểm tra quyền hiệu lực cho một role và object ở thời điểm hiện tại. Thông tin này dễ đưa vào test tự động hơn việc chỉ đọc phần văn bản ACL thủ công.

### 8.2. Nếu quyền trả true ngoài dự kiến?

Có thể role đang có quyền thông qua `PUBLIC`, membership hoặc GRANT khác; lab không sạch; hoặc object tồn tại từ trước. Hãy tìm **nguồn quyền thực tế**, không kết luận PostgreSQL đã cấp mặc định sai.

## 9. Cấu hình quyền mặc định cho bảng tương lai

Chạy dưới role `acl_owner`:

```sql
SET ROLE acl_owner;

ALTER DEFAULT PRIVILEGES
    IN SCHEMA acl_lab
GRANT SELECT ON TABLES TO acl_reader;

ALTER DEFAULT PRIVILEGES
    IN SCHEMA acl_lab
GRANT SELECT, INSERT, UPDATE ON TABLES TO acl_writer;

RESET ROLE;
```

Hai câu lệnh này có nghĩa:

- Khi `acl_owner` tạo object thuộc nhóm `TABLES` trong `acl_lab`, `acl_reader` sẽ nhận SELECT.
- `acl_writer` sẽ nhận SELECT, INSERT và UPDATE.
- Không tự cấp DELETE, TRUNCATE hoặc quyền quản trị cao hơn.

### 9.1. FOR ROLE tường minh

Nếu người quản trị có quyền thay default privileges cho `acl_owner`, có thể viết tương đương:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
    IN SCHEMA acl_lab
GRANT SELECT ON TABLES TO acl_reader;
```

Nên viết `FOR ROLE` tường minh trong migration/audit scripts để tránh nhầm creator khi session chạy dưới role khác.

### 9.2. Không cấp quyền cho reader nếu schema bị thiếu USAGE

Các default GRANT ở mục 9 không tự sửa schema ACL. Lab đã chủ động cấp `USAGE ON SCHEMA acl_lab` ở mục 7.

### 9.3. Không hồi tố

`acl_lab.before_default` vẫn không tự được cấp SELECT cho reader, trừ khi có một GRANT riêng hoặc các quyền khác.

## 10. Tạo bảng, view và xem quyền mới

```sql
SET ROLE acl_owner;

CREATE TABLE acl_lab.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_name text NOT NULL,
    net_amount numeric(12, 2) NOT NULL
        CHECK (net_amount >= 0)
);

CREATE VIEW acl_lab.order_overview AS
SELECT order_id, customer_name, net_amount
FROM acl_lab.orders;

RESET ROLE;
```

Kiểm tra:

```sql
SELECT
    has_table_privilege(
        'acl_reader', 'acl_lab.orders', 'SELECT'
    ) AS reader_selects_orders,
    has_table_privilege(
        'acl_writer', 'acl_lab.orders', 'INSERT'
    ) AS writer_inserts_orders,
    has_table_privilege(
        'acl_writer', 'acl_lab.orders', 'UPDATE'
    ) AS writer_updates_orders,
    has_table_privilege(
        'acl_reader', 'acl_lab.order_overview', 'SELECT'
    ) AS reader_selects_view,
    has_table_privilege(
        'acl_reader', 'acl_lab.before_default', 'SELECT'
    ) AS reader_selects_old_table;
```

Ở lab sạch:

| Điều kiện | Kỳ vọng |
| --- | --- |
| Reader SELECT bảng `orders` mới | TRUE |
| Writer INSERT bảng `orders` mới | TRUE |
| Writer UPDATE bảng `orders` mới | TRUE |
| Reader SELECT view `order_overview` mới | TRUE |
| Reader SELECT bảng `before_default` cũ | FALSE |

### 10.1. Tại sao view cũng chịu chính sách ON TABLES?

Trong hệ quyền PostgreSQL, keyword `TABLES` của `GRANT`/default ACL bao gồm những loại relation được xử lý theo nhóm quyền bảng, trong đó có regular views. Không tìm một cú pháp mặc định riêng `ON VIEWS` để giải quyết yêu cầu thông thường.

### 10.2. View cập nhật được có rủi ro nếu cấp INSERT/UPDATE

Nếu view tự động cập nhật được và writer có INSERT/UPDATE trên view, writer có thể thao tác dữ liệu bảng nguồn qua view theo quyền, owner/invoker semantics, check option và các constraints áp dụng.

Nếu một schema chứa cả **view chỉ để báo cáo** và **bảng ghi nghiệp vụ**, cấp mặc định `INSERT,UPDATE ON TABLES` có thể rộng hơn ý định. Hãy cân nhắc phân chia schema và kiểm tra quyền của view mới.

## 11. Chạy thử dưới role nhận quyền

Một role NOLOGIN vẫn có thể được dùng với `SET ROLE` bởi phiên quản trị có quyền.

### 11.1. Test reader

```sql
SET ROLE acl_reader;

SELECT order_id, customer_name, net_amount
FROM acl_lab.orders
ORDER BY order_id;

SELECT *
FROM acl_lab.order_overview;

RESET ROLE;
```

### 11.2. Test writer

```sql
SET ROLE acl_writer;

INSERT INTO acl_lab.orders(customer_name, net_amount)
VALUES ('Customer A', 100.00);

SELECT order_id, customer_name, net_amount
FROM acl_lab.orders
ORDER BY order_id;

RESET ROLE;
```

### 11.3. Câu INSERT RETURNING cần xem quyền SELECT

Vì lab đã cấp SELECT cho writer, `INSERT ... RETURNING order_id` có thể dùng được theo permissions hiện tại. Nếu một writer chỉ có INSERT mà không SELECT, các cột trong RETURNING hoặc WHERE/expressions của UPDATE có thể cần quyền đọc bổ sung.

### 11.4. Không dùng role quản trị để xác nhận quyền ứng dụng

SELECT chạy thành công dưới `acl_owner` không chứng minh `acl_reader` có quyền. Luôn kiểm tra bằng identity runtime hoặc `has_*_privilege` đối với role thực.

## 12. Chỉnh quyền của những bảng cũ

Đến đây `before_default` vẫn chưa có SELECT cho reader.

Có thể cấp cụ thể:

```sql
SET ROLE acl_owner;

GRANT SELECT ON acl_lab.before_default TO acl_reader;

RESET ROLE;
```

Hoặc nếu muốn cấp cho **mọi bảng hiện tồn tại thuộc schema** theo chính sách:

```sql
-- Chỉ thực hiện với role sở hữu các object,
-- có grant option hoặc quyền quản trị cần thiết.
GRANT SELECT ON ALL TABLES IN SCHEMA acl_lab TO acl_reader;
```

### 12.1. Lưu ý ownership khi GRANT ON ALL

Nếu schema có bảng do **nhiều role khác nhau sở hữu**, một role chỉ sở hữu schema chưa chắc có quyền GRANT trên tất cả những bảng đó. Câu `GRANT ... ON ALL TABLES` cần quyền trên từng object; có thể gặp cảnh báo/lỗi quyền ở những object không được phép cấp.

### 12.2. Migration chuẩn cho hệ thống đã có dữ liệu

Thông thường triển khai hai bước:

1. Cấp quyền phù hợp trên object **đang tồn tại**.
2. Đặt default privileges cho object **tạo về sau**.

Và sau đó **verify** bằng role thực tế.

## 13. Quyền mặc định trên SEQUENCES

Sequence là object riêng, không phải table. Một ứng dụng dùng `nextval('schema.seq')` có thể cần `USAGE` hoặc quyền thích hợp trên sequence.

```sql
SET ROLE acl_owner;

ALTER DEFAULT PRIVILEGES
    IN SCHEMA acl_lab
GRANT USAGE, SELECT ON SEQUENCES TO acl_writer;

CREATE SEQUENCE acl_lab.invoice_no_seq
    START WITH 1000
    INCREMENT BY 1;

RESET ROLE;
```

Kiểm tra:

```sql
SELECT
    has_sequence_privilege(
        'acl_writer',
        'acl_lab.invoice_no_seq',
        'USAGE'
    ) AS writer_uses_sequence,
    has_sequence_privilege(
        'acl_reader',
        'acl_lab.invoice_no_seq',
        'USAGE'
    ) AS reader_uses_sequence;
```

Ở lab:

- Writer có `USAGE`.
- Reader chưa được cấp `USAGE` trên sequence.

### 13.1. GRANT SELECT ON TABLES không cấp sequence quyền

Đây là lỗi thường gặp:

```text
Ứng dụng có INSERT trên bảng.
Cột ID dùng DEFAULT nextval('invoice_no_seq').
Ứng dụng vẫn gặp permission denied for sequence.
```

Nguyên nhân có thể do ứng dụng cần quyền USAGE trên sequence được tham chiếu.

### 13.2. SERIAL và IDENTITY không hoàn toàn giống nhau

Với cột kiểu `SERIAL` truyền thống, default dựa trên `nextval()`; role insert có thể cần quyền sequence.

Với `GENERATED ... AS IDENTITY` của PostgreSQL, việc sinh identity value khi INSERT theo semantics identity không nhất thiết yêu cầu role có quyền `USAGE` riêng trên sequence nội bộ như cách gọi `nextval()` tường minh. Tuy nhiên, nếu ứng dụng **gọi sequence trực tiếp**, vẫn phải xét sequence privileges.

Không nên xử lý mọi lỗi bằng cách cấp `ALL ON ALL SEQUENCES` mà chưa xem loại cột và SQL thực tế.

### 13.3. Quyền SELECT, USAGE, UPDATE trên sequence

Các thao tác `nextval`, `currval`, `setval` có yêu cầu quyền khác nhau. Trong nhiều tình huống, `USAGE` đủ cho `nextval`, còn `UPDATE` có quyền rộng hơn đối với sequence state. Chỉ cấp những quyền ứng dụng cần.

### 13.4. Test trực tiếp

```sql
SET ROLE acl_writer;

SELECT nextval('acl_lab.invoice_no_seq');

RESET ROLE;
```

Đây là lệnh **có side effect**: số sequence tăng, không rollback giá trị đã cấp như table row thông thường. Chỉ thực hiện trên lab.

## 14. Quyền mặc định trên FUNCTIONS và ROUTINES

Hàm và thủ tục có quyền chủ yếu cần quan tâm là `EXECUTE`.

Ví dụ:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
    IN SCHEMA acl_lab
GRANT EXECUTE ON FUNCTIONS TO acl_reader;
```

Trong các phiên bản hỗ trợ, `ROUTINES` có thể được dùng để biểu đạt nhóm routine bao gồm functions/procedures theo cú pháp.

### 14.1. Khác biệt bảo mật rất quan trọng: PUBLIC EXECUTE

Theo mặc định PostgreSQL, một function mới thường có quyền `EXECUTE` cho `PUBLIC` (toàn bộ roles) nếu không được thay đổi bởi default privilege policy.

Vì thế câu per-schema `GRANT EXECUTE ... TO acl_reader` **không nhất thiết làm function chỉ reader được gọi**. Nếu `PUBLIC` còn được EXECUTE, nhiều role khác vẫn có thể thực thi.

### 14.2. Hardening ở phạm vi global

Để thay đổi default PUBLIC EXECUTE cho những function do `acl_owner` tạo về sau:

```sql
SET ROLE acl_owner;

ALTER DEFAULT PRIVILEGES
REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

ALTER DEFAULT PRIVILEGES
    IN SCHEMA acl_lab
GRANT EXECUTE ON FUNCTIONS TO acl_reader;

RESET ROLE;
```

Lúc đó:

- Future functions của `acl_owner` không tự cấp EXECUTE cho PUBLIC theo default chung.
- Future functions trong `acl_lab` được cấp EXECUTE cho reader theo per-schema rule.

**Lưu ý:** câu global REVOKE áp dụng cho future functions của `acl_owner` ở mọi schema, không riêng `acl_lab`. Cần đánh giá tác động tới các nhóm ứng dụng khác trước khi bật trên môi trường chung.

### 14.3. Vì sao REVOKE PUBLIC trong per-schema không đủ?

Nếu default built-in hoặc một default global vẫn cấp quyền PUBLIC, một lệnh:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
    IN SCHEMA acl_lab
REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
```

**không phải** cách loại bỏ quyền EXECUTE đã được cấp ở phạm vi global. Default privileges theo schema **bổ sung** trên default global; muốn bỏ global PUBLIC EXECUTE thì phải điều chỉnh global default.

Đây là một trong những điểm dễ nhầm nhất của `ALTER DEFAULT PRIVILEGES`.

## 15. Tạo function sau khi cấu hình quyền

```sql
SET ROLE acl_owner;

CREATE FUNCTION acl_lab.calculate_tax(p_net numeric)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT p_net * 0.10
$$;

RESET ROLE;
```

Kiểm tra:

```sql
SELECT
    has_function_privilege(
        'acl_reader',
        'acl_lab.calculate_tax(numeric)',
        'EXECUTE'
    ) AS reader_executes_function,
    has_function_privilege(
        'acl_writer',
        'acl_lab.calculate_tax(numeric)',
        'EXECUTE'
    ) AS writer_executes_function;
```

Với lab sạch, sau khi global PUBLIC EXECUTE đã được REVOKE:

- `acl_reader` có EXECUTE nhờ per-schema default GRANT.
- `acl_writer` không tự có EXECUTE nếu chưa được cấp bằng đường khác.

### 15.1. Test từ role reader

```sql
SET ROLE acl_reader;

SELECT acl_lab.calculate_tax(100.00);

RESET ROLE;
```

### 15.2. Đối tượng được tạo trước khi REVOKE default vẫn giữ quyền cũ

Giả sử một function cũ đã có PUBLIC EXECUTE. Global default REVOKE hôm nay không tự gỡ quyền đó. Cần REVOKE trực tiếp trên function hiện có nếu muốn thu hẹp quyền.

```sql
-- Ví dụ cho function hiện có:
REVOKE EXECUTE ON FUNCTION acl_lab.calculate_tax(numeric)
FROM PUBLIC;
```

Khi thực hiện lệnh kiểu này trong hệ thống thật, phải bảo đảm không vô tình làm gián đoạn những clients hợp lệ đang gọi function.

## 16. Vì sao quyền PUBLIC đặc biệt nhạy cảm?

`PUBLIC` là tên nhóm bao gồm **mọi role**, kể cả role tạo sau này. Nó không phải một role riêng thông thường cần `CREATE ROLE PUBLIC`.

Ví dụ:

```sql
GRANT EXECUTE ON FUNCTION app.some_function(integer)
TO PUBLIC;
```

nếu được cấp, mọi role có quyền truy cập schema và các điều kiện bảo mật khác phù hợp đều có cơ hội gọi function.

### 16.1. Không phải function nào cũng nguy hiểm

Một hàm tính toán thuần không có quyền đặc biệt có thể được thiết kế cho nhiều role gọi. Nhưng với hàm:

- `SECURITY DEFINER`.
- Thực hiện ghi dữ liệu.
- Đọc thông tin nhạy cảm.
- Kích hoạt workflow thanh toán hoặc cấp quyền.
- Gọi extension/tài nguyên hệ thống.

PUBLIC EXECUTE mặc định có thể tạo bề mặt rủi ro đáng kể.

### 16.2. CREATE và REVOKE trong một transaction

Nếu chưa cấu hình default privilege hardening, tạo function rồi REVOKE ở hai transaction riêng có thể tạo **khoảng thời gian quyền rộng** giữa hai lần commit.

Trong một migration có kiểm soát, có thể:

```sql
BEGIN;

CREATE FUNCTION app.new_sensitive_function()
RETURNS integer
LANGUAGE sql
AS $$
    SELECT 1
$$;

REVOKE EXECUTE ON FUNCTION app.new_sensitive_function()
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION app.new_sensitive_function()
TO app_service;

COMMIT;
```

Mẫu này giả định schema/roles đã tồn tại, người chạy sở hữu function và việc tạo function có thể đặt trong transaction. **Cài đặt global default PUBLIC revoke đúng từ đầu** giúp giảm nguy cơ quên REVOKE với mỗi function mới.

### 16.3. PUBLIC khác từ khóa ALL

- `PUBLIC`: tập các role được hưởng privilege.
- `ALL PRIVILEGES`: tập các loại privilege của object.

Hai từ khóa giải quyết hai trục khác nhau và không được nhầm.

## 17. Quyền mặc định trên TYPES

Các type/domain được tạo trong schema cũng có quyền `USAGE`. PostgreSQL mặc định có thể cấp `USAGE` trên type cho `PUBLIC`, tương tự kiểu PUBLIC EXECUTE của function nhưng khác loại quyền.

Ví dụ tạo domain:

```sql
SET ROLE acl_owner;

CREATE DOMAIN acl_lab.positive_money
AS numeric(12,2)
CHECK (VALUE >= 0);

RESET ROLE;
```

### 17.1. Cấp default USAGE cho type tương lai

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
    IN SCHEMA acl_lab
GRANT USAGE ON TYPES TO acl_reader;
```

Lệnh trên **chỉ cấp cho các type được tạo sau nó**, không thay quyền của domain `positive_money` vừa tạo.

### 17.2. Per-schema GRANT không thay default PUBLIC

Nếu default global vẫn cho PUBLIC USAGE trên type, câu per-schema GRANT riêng cho reader không có nghĩa những role khác bị loại quyền.

Muốn thiết kế restrictive defaults, có thể cần đánh giá:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
REVOKE USAGE ON TYPES FROM PUBLIC;
```

Đây là **thay đổi rộng** cho future types của owner, có thể ảnh hưởng ứng dụng/dịch vụ khác. Hãy kiểm tra dependencies trước.

### 17.3. Type usage không cấp quyền đọc bảng

Một role có thể dùng domain `positive_money` nhưng không có SELECT trên bảng nào sử dụng domain đó. Quyền trên type và table là những quyền riêng.

### 17.4. Kiểm tra quyền

```sql
SELECT
    has_type_privilege(
        'acl_reader',
        'acl_lab.positive_money',
        'USAGE'
    ) AS reader_uses_type;
```

Với type đã tạo trước khi thay default, kết quả phụ thuộc quyền thực tế, bao gồm PUBLIC hoặc GRANT trực tiếp.

## 18. Quyền mặc định trên SCHEMAS tương lai

Khi một role **tạo schema mới**, cũng có thể thiết lập default privileges cho đối tượng schema được tạo về sau.

Ví dụ:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
GRANT USAGE ON SCHEMAS TO acl_reader;
```

Khi `acl_owner` tạo schema mới sau đó:

```sql
SET ROLE acl_owner;

CREATE SCHEMA acl_future;

RESET ROLE;
```

Role `acl_reader` có thể nhận USAGE trên schema `acl_future` theo cấu hình global trên, nhưng vẫn không tự nhận SELECT mọi bảng của schema mới.

### 18.1. Không dùng IN SCHEMA để cấu hình quyền trên schema tương lai

Schema không lồng nhau trong PostgreSQL. Vì vậy default privileges trên **SCHEMAS** được cấu hình ở phạm vi global cho creator role, không phải qua một `IN SCHEMA parent_schema` như với tables/sequences/functions/types.

### 18.2. USAGE khác CREATE

Cấp `USAGE ON SCHEMAS` giúp role có thể tìm và truy cập object theo quyền riêng. Cấp `CREATE ON SCHEMAS` rộng hơn nhiều: role được phép tạo object trong schema tương lai.

Đối với reader/runtime application, thường không cấp `CREATE` chỉ để khắc phục lỗi SELECT.

### 18.3. Existing schema không thay đổi

Nếu `acl_lab` được tạo **trước** lệnh default `GRANT USAGE ON SCHEMAS`, ACL của `acl_lab` vẫn là trạng thái riêng. Lab đã cấp USAGE cho reader/writer bằng `GRANT USAGE ON SCHEMA` trực tiếp.

## 19. Global default và per-schema default cộng với nhau

Hai loại default privileges:

```text
Global (không IN SCHEMA):
    Áp dụng ở thời điểm creator role CREATE object,
    bất kể schema phù hợp.

Per-schema (có IN SCHEMA):
    Bổ sung quyền cho object cùng creator
    khi CREATE trong schema được chỉ định.
```

Ví dụ:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
GRANT SELECT ON TABLES TO acl_reader;

ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
    IN SCHEMA acl_lab
GRANT INSERT ON TABLES TO acl_writer;
```

Nếu cùng chính sách này đang hoạt động:

| Schema tạo bảng | `acl_reader` | `acl_writer` |
| --- | --- | --- |
| `acl_lab` | SELECT (global) | INSERT (per-schema) |
| `acl_else` | SELECT (global) | Không tự nhận INSERT từ rule `acl_lab` |

### 19.1. Tại sao tách hai lớp?

- Global phù hợp chính sách dùng chung cho mọi schema mà một role sở hữu.
- Per-schema phù hợp một số schema có yêu cầu truy cập riêng.

### 19.2. Global quá rộng là rủi ro thiết kế

Nếu `acl_owner` cũng tạo bảng trong schema chứa dữ liệu nhạy cảm, global `GRANT SELECT TO acl_reader` có thể cấp quyền cho reader ở nơi bạn không dự định.

Khi yêu cầu phân quyền khác nhau theo domain, ưu tiên **per-schema grants** và/hoặc tách owner roles.

## 20. Điểm rất quan trọng: REVOKE theo schema không trừ global GRANT

Giả sử global policy đã cấp SELECT:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
GRANT SELECT ON TABLES TO acl_reader;
```

Bạn muốn schema `acl_else` **không** có SELECT đó và thử:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
    IN SCHEMA acl_else
REVOKE SELECT ON TABLES FROM acl_reader;
```

**Kết quả không đạt mục tiêu:** per-schema REVOKE chỉ có thể đảo ngược các per-schema grants tương ứng; nó **không gỡ** quyền phát sinh từ global defaults.

### 20.1. Cách thiết kế đúng

Nếu cần reader chỉ đọc schema `acl_lab`:

1. Không cấp SELECT global cho owner đó, hoặc REVOKE global policy đã cấu hình.
2. Cấp SELECT per-schema chỉ cho `acl_lab`.
3. Kiểm tra quyền trên object đã tồn tại và tương lai.

Ví dụ:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
REVOKE SELECT ON TABLES FROM acl_reader;

ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
    IN SCHEMA acl_lab
GRANT SELECT ON TABLES TO acl_reader;
```

### 20.2. Global REVOKE chưa đủ nếu có per-schema GRANT

Nếu một per-schema policy vẫn cấp SELECT, REVOKE global **không xóa** per-schema grant đó. Muốn loại một quyền mặc định, phải xem **cả hai lớp**.

### 20.3. Test trong transaction để không đổi lab vĩnh viễn

```sql
BEGIN;

ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
GRANT SELECT ON TABLES TO acl_reader;

ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
    IN SCHEMA acl_else
REVOKE SELECT ON TABLES FROM acl_reader;

SET ROLE acl_owner;
CREATE TABLE acl_else.global_grant_example(id integer);
RESET ROLE;

SELECT has_table_privilege(
    'acl_reader',
    'acl_else.global_grant_example',
    'SELECT'
) AS reader_still_has_global_select;

ROLLBACK;
```

Kỳ vọng TRUE trong bối cảnh lab, minh họa per-schema REVOKE không triệt tiêu global grant. Vì toàn bộ ví dụ được rollback, default ACL global chỉ được thay đổi tạm thời trong transaction này.

## 21. Object creator: yếu tố quyết định quan trọng nhất

Một lỗi rất phổ biến:

```text
Role app_owner có default privileges rất đúng.
Role deployer là member của app_owner.
Deployer kết nối và CREATE TABLE trực tiếp.
Ứng dụng reader không có quyền trên table mới.
```

Vì **default privileges dùng bộ policy của role thực sự tạo object**, không tự kế thừa bộ policy của những role mà creator là thành viên.

### 21.1. current_user, current_role, session_user

Kiểm tra:

```sql
SELECT
    current_user,
    current_role,
    session_user;
```

Khi `SET ROLE acl_owner`:

```sql
SET ROLE acl_owner;

SELECT current_user, current_role, session_user;

RESET ROLE;
```

`current_user/current_role` phản ánh role hiệu lực cho kiểm tra privilege và tạo object theo ngữ cảnh bình thường; `session_user` vẫn là người khởi đầu session.

### 21.2. Membership không thay creator role

Ngay cả khi:

```sql
GRANT acl_owner TO acl_deployer;
```

và deployer có quyền tạo bảng nhờ grants/membership, một:

```sql
SET ROLE acl_deployer;
CREATE TABLE acl_lab.created_by_deployer(id integer);
RESET ROLE;
```

vẫn tạo đối tượng **dưới role acl_deployer** nếu đó là current role tại CREATE.

### 21.3. Default của owner không tự áp dụng cho deployer

Nếu chỉ đặt:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
    IN SCHEMA acl_lab
GRANT SELECT ON TABLES TO acl_reader;
```

thì `acl_lab.created_by_deployer` không nhận GRANT SELECT nhờ policy này.

### 21.4. Kiểm chứng

```sql
SELECT
    has_table_privilege(
        'acl_reader',
        'acl_lab.created_by_deployer',
        'SELECT'
    ) AS reader_can_read_deployer_table;
```

Trong lab chưa cấp default SELECT cho creator `acl_deployer`, kết quả dự kiến là FALSE, trừ khi có grant khác.

## 22. Cách xử lý khi migration runner tạo object

Có hai hướng rõ ràng.

### 22.1. Hướng A — SET ROLE owner trước khi CREATE

Nếu `acl_deployer` được phép `SET ROLE acl_owner`:

```sql
SET ROLE acl_owner;

CREATE TABLE acl_lab.created_as_owner (
    id integer PRIMARY KEY,
    note text
);

RESET ROLE;
```

Table mới do `acl_owner` tạo, nên policy `FOR ROLE acl_owner` được áp dụng.

### 22.2. Hướng B — cấu hình default cho chính deployer

Nếu runtime migration luôn tạo object dưới `acl_deployer`:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_deployer
    IN SCHEMA acl_lab
GRANT SELECT ON TABLES TO acl_reader;
```

Sau đó:

```sql
SET ROLE acl_deployer;

CREATE TABLE acl_lab.created_after_deployer_policy (
    id integer PRIMARY KEY,
    description text
);

RESET ROLE;
```

Reader có thể nhận SELECT trên bảng mới do deployer tạo.

### 22.3. Không trộn hai chiến lược không kiểm soát

Nếu một số migration chạy dưới owner, một số khác chạy dưới deployer, quyền/ownership của các bảng tương lai có thể không nhất quán. Pipeline nên xác định rõ:

- Login/session role.
- Current role tại CREATE.
- Owner sau CREATE.
- Schema đích.
- Default ACL nào cần áp dụng.
- Cách verify sau migration.

## 23. FOR ROLE không phải role nhận privilege

Đọc câu:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
    IN SCHEMA acl_lab
GRANT SELECT ON TABLES TO acl_reader;
```

theo ba vị trí:

| Thành phần | Vai trò |
| --- | --- |
| `FOR ROLE acl_owner` | **Creator role** mà policy theo dõi |
| `IN SCHEMA acl_lab` | **Nơi tạo object** |
| `TO acl_reader` | **Grantee role** nhận quyền trên object mới |

### 23.1. Một role có thể ở nhiều vị trí

Bạn có thể thiết lập default cho chính role tạo hoặc những role nhóm khác theo chính sách, nhưng cần hiểu ownership và effective privileges. Không dùng `GRANT ... TO owner` để thay thế cơ chế ownership.

### 23.2. Ai được sửa default privileges cho role khác?

Không phải bất kỳ user nào cũng được sửa policy của bất kỳ creator role nào. PostgreSQL giới hạn việc đổi default privileges cho những object do chính user/role mà user có quan hệ membership/quyền phù hợp sẽ tạo, hoặc người có quyền quản trị tương ứng.

Một ứng dụng runtime không nên được cấp quyền chỉnh default ACL của owner chỉ để SELECT bảng mới.

### 23.3. FOR ROLE nhiều target roles

Cú pháp cho phép chỉ định nhiều creator roles trong phạm vi được phép:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE team_owner_a, team_owner_b
    IN SCHEMA app
GRANT SELECT ON TABLES TO app_reader;
```

Đây là ví dụ khái niệm với roles/schema giả định. Phân quyền thực thi phải được đáp ứng cho mọi target.

## 24. Tạo bảng ở schema khác không nhận per-schema grant

Trong lab, `acl_reader` chỉ được cấp SELECT per-schema trên `acl_lab` bởi default policy của owner.

Thử:

```sql
SET ROLE acl_owner;

CREATE TABLE acl_else.other_orders (
    other_order_id integer PRIMARY KEY,
    note text
);

RESET ROLE;
```

Kiểm tra:

```sql
SELECT
    has_table_privilege(
        'acl_reader', 'acl_else.other_orders', 'SELECT'
    ) AS reader_selects_other_schema_table;
```

Nếu không có global default SELECT cho owner hoặc GRANT khác, kết quả dự kiến FALSE.

### 24.1. USAGE ON acl_else không làm SELECT thành TRUE

Lab đã GRANT USAGE ON SCHEMA `acl_else` cho reader, nhưng role vẫn không tự có SELECT trên bảng `other_orders`.

### 24.2. Default privilege không dựa vào tên bảng

Policy mặc định đang theo **creator + schema + loại object**, không dựa vào việc bảng tên `orders`, `other_orders` hay `secret_table`.

Nếu cần phân biệt quyền theo từng bảng trong cùng schema, default grant chung chưa chắc đủ; cân nhắc chia schema, tạo các role creator khác nhau hoặc GRANT/REVOKE object-specific trong migration.

## 25. Kiểm tra default ACL trong psql bằng \\ddp

`psql` có meta-command:

```text
\ddp
```

Nó hiển thị những default privilege entries hiện được cấu hình, thường gồm:

- Owner/creator role.
- Schema (khi per-schema).
- Loại object.
- Các quyền được GRANT/REVOKE tương ứng.

### 25.1. \\ddp khác \\dp

| Lệnh psql | Dùng để xem |
| --- | --- |
| `\\ddp` | **Default privileges** cho object tương lai |
| `\\dp acl_lab.*` | ACL/quyền của các object **đang tồn tại** |
| `\\dn+ acl_lab` | Thông tin schema và access privileges |
| `\\du+` | Roles và thuộc tính/membership liên quan |
| `\\df+ acl_lab.*` | Functions/routines đang tồn tại, thông tin bổ sung |

Những lệnh bắt đầu bằng backslash là **psql meta-command**, không phải SQL chuẩn. Chạy chúng trong psql, không qua JDBC như một SQL statement.

### 25.2. Vì sao cần nhìn cả \\ddp và \\dp?

Một default policy có thể rất đúng nhưng bảng được tạo **trước** policy hoặc bởi **role khác** nên ACL hiện tại vẫn không đúng.

### 25.3. Không suy luận chỉ từ một màn hình \\ddp

Phải xét:

- Các entry global và per-schema.
- Creator role.
- Object type.
- PUBLIC và role memberships.
- ACL cụ thể của từng object.

## 26. Truy vấn catalog pg_default_acl

PostgreSQL lưu default privilege entries trong catalog `pg_default_acl`.

```sql
SELECT
    pg_get_userbyid(d.defaclrole) AS creator_role,
    CASE
        WHEN d.defaclnamespace = 0::oid THEN '<global>'
        ELSE d.defaclnamespace::regnamespace::text
    END AS scope,
    d.defaclobjtype AS object_type_code,
    d.defaclacl AS acl_items
FROM pg_default_acl AS d
ORDER BY creator_role, scope, object_type_code;
```

### 26.1. Ý nghĩa các cột

- `defaclrole`: creator role mà policy thuộc về.
- `defaclnamespace`: schema OID, hoặc 0 cho entry global.
- `defaclobjtype`: ký hiệu loại object, ví dụ nhóm relation, sequence, function, type, schema.
- `defaclacl`: các ACL items.

### 26.2. Không giả định catalog có row cho mọi giá trị mặc định built-in

Nếu một role chưa từng có cấu hình default ACL tùy chỉnh, không nhất thiết có entry trong `pg_default_acl`. PostgreSQL còn có **built-in initial privileges** theo loại object.

Do đó:

```text
Không có pg_default_acl row
    KHÔNG đồng nghĩa
không ai có quyền trên object mới.
```

Đặc biệt, cần nhớ mặc định `PUBLIC EXECUTE` trên functions và `PUBLIC USAGE` trên types trong cấu hình thông thường.

### 26.3. Đọc catalog là quan sát, không nên sửa trực tiếp

Không `UPDATE pg_default_acl` bằng SQL thủ công. Hãy dùng DDL `ALTER DEFAULT PRIVILEGES` được PostgreSQL hỗ trợ.

## 27. Giải mã ACL bằng aclexplode

Các ACL item như `role=r/owner` có thể khó đọc. PostgreSQL có hàm `aclexplode` để trình bày từng privilege:

```sql
SELECT
    pg_get_userbyid(d.defaclrole) AS creator_role,
    CASE
        WHEN d.defaclnamespace = 0::oid THEN '<global>'
        ELSE d.defaclnamespace::regnamespace::text
    END AS scope,
    d.defaclobjtype,
    CASE
        WHEN a.grantee = 0::oid THEN 'PUBLIC'
        ELSE pg_get_userbyid(a.grantee)
    END AS grantee,
    a.privilege_type,
    a.is_grantable
FROM pg_default_acl AS d
CROSS JOIN LATERAL aclexplode(d.defaclacl) AS a
ORDER BY creator_role, scope, grantee, a.privilege_type;
```

### 27.1. Tại sao grantee 0 là PUBLIC?

Trong biểu diễn ACL của PostgreSQL, OID 0 được dùng để biểu đạt `PUBLIC` trong ngữ cảnh quyền.

### 27.2. is_grantable là gì?

Phân biệt quyền được thực thi và quyền được **GRANT lại** cho người khác. Với các grant có `WITH GRANT OPTION`, quyền có thể được ủy quyền tiếp theo quy tắc PostgreSQL.

### 27.3. Không chỉ đếm một entry

Một role có thể nhận quyền từ:

- GRANT trực tiếp.
- Một hoặc nhiều group roles.
- PUBLIC.
- Ownership.

Khi đánh giá quyền hiệu lực trên object, `has_*_privilege` và test dưới role thực thường thuận tiện hơn chỉ đọc một ACL item.

## 28. Kiểm tra quyền hiện tại bằng has_*_privilege

Các hàm SQL rất hữu ích:

```sql
SELECT
    has_schema_privilege(
        'acl_reader', 'acl_lab', 'USAGE'
    ) AS can_use_schema,
    has_table_privilege(
        'acl_reader', 'acl_lab.orders', 'SELECT'
    ) AS can_select_table,
    has_sequence_privilege(
        'acl_writer', 'acl_lab.invoice_no_seq', 'USAGE'
    ) AS can_use_sequence,
    has_function_privilege(
        'acl_reader', 'acl_lab.calculate_tax(numeric)', 'EXECUTE'
    ) AS can_execute_function,
    has_type_privilege(
        'acl_reader', 'acl_lab.positive_money', 'USAGE'
    ) AS can_use_type;
```

### 28.1. Kết quả true không khẳng định mọi truy vấn luôn thành công

Ví dụ `has_table_privilege(...,'SELECT')=TRUE`:

- Chưa tự kiểm tra schema USAGE.
- Chưa nói gì về RLS row visibility.
- Chưa nói về khóa, constraints, function permissions trong expression hoặc các policy khác.

### 28.2. Role membership có thể cho quyền gián tiếp

Hàm privilege có thể xét quyền hiệu lực qua membership và PUBLIC theo quy tắc đang áp dụng. Vì vậy nếu bạn không tìm thấy một GRANT trực tiếp, chưa chắc role thiếu quyền.

### 28.3. Khi object không tồn tại

Nếu tên object sai, một số cách gọi theo tên có thể báo lỗi thay vì trả FALSE. Trước khi chạy kiểm tra quyền, xác minh schema/object có thực sự được tạo trong database đích.

## 29. Xem ACL object trong pg_class và các catalogs

Với bảng/view/sequence:

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    c.relkind,
    pg_get_userbyid(c.relowner) AS owner_role,
    c.relacl
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE n.nspname IN ('acl_lab', 'acl_else')
ORDER BY n.nspname, c.relname;
```

### 29.1. relacl NULL không có nghĩa không ai có quyền

Khi ACL chưa được custom, `relacl` có thể NULL và PostgreSQL dùng built-in defaults tùy loại object/ownership. Cần hiểu semantics này trước khi viết audit.

### 29.2. Phân biệt relation types

Một số ký hiệu trong `relkind`:

- `r`: ordinary table.
- `p`: partitioned table.
- `v`: view.
- `m`: materialized view.
- `S`: sequence.
- `f`: foreign table.

Đây là thông tin giúp bạn hiểu object nào trong schema nên được đưa vào một chính sách GRANT phù hợp.

### 29.3. Function ACL nằm ở pg_proc

`pg_class.relacl` không chứa ACL của mọi function. Các function nằm trong `pg_proc`, có `proacl` cùng thông tin signature và owner.

```sql
SELECT
    p.oid::regprocedure AS function_signature,
    pg_get_userbyid(p.proowner) AS owner_role,
    p.proacl
FROM pg_proc AS p
JOIN pg_namespace AS n
  ON n.oid = p.pronamespace
WHERE n.nspname = 'acl_lab'
ORDER BY function_signature::text;
```

## 30. Quyền trên bảng mới từ CREATE TABLE AS

Một migration có thể tạo bảng bằng:

```sql
SET ROLE acl_owner;

CREATE TABLE acl_lab.order_snapshot AS
SELECT order_id, customer_name, net_amount
FROM acl_lab.orders;

RESET ROLE;
```

Đây vẫn là một **bảng mới do acl_owner tạo trong acl_lab**, nên default table privileges tương ứng có thể được áp dụng lúc CREATE.

### 30.1. Quyền trên dữ liệu nguồn khác quyền trên bảng đích

Role chạy `CREATE TABLE AS SELECT` cần có quyền đọc nguồn và quyền CREATE ở schema đích. Đối tượng đích sau khi tạo sẽ có ACL của riêng nó.

### 30.2. Dữ liệu được sao chép không mang theo table ACL

Việc copy dữ liệu vào một bảng mới không đơn giản “sao chép toàn bộ privileges của bảng gốc”. ACL mới được xác lập theo ownership, built-in defaults và default policy của creator.

### 30.3. Snapshot có dữ liệu nhạy cảm

Nếu schema có per-schema default SELECT cho mọi bảng mới, một bảng snapshot tạm nhưng chứa dữ liệu nhạy cảm có thể lập tức có reader grant. Hãy cân nhắc **schema riêng cho staging/temp dữ liệu nhạy cảm** hoặc creator riêng thay vì coi default SELECT là vô hại.

## 31. View mới và cách kiểm tra quyền thực thi

Một view thường được tạo bằng:

```sql
SET ROLE acl_owner;

CREATE VIEW acl_lab.order_names AS
SELECT order_id, customer_name
FROM acl_lab.orders;

RESET ROLE;
```

Default `GRANT SELECT ON TABLES TO acl_reader` cho view mới không phải lời hứa tất cả query SELECT view sẽ luôn có cùng security behavior.

### 31.1. Quyền trên bảng nền của view

Trong PostgreSQL, quyền truy cập các relation được view tham chiếu phụ thuộc cách view được định nghĩa và các cơ chế kiểm tra quyền tương ứng. View mặc định thường có semantics owner-based đối với relations bên dưới; tùy chọn `security_invoker` ở các phiên bản hỗ trợ có thể làm quyền/RLS được kiểm tra theo invoker.

### 31.2. RLS và view

Một `GRANT SELECT` mặc định trên view có thể tạo một đường truy cập khác tới dữ liệu bảng nền theo view semantics. Trước khi cho reader SELECT mọi view mới, phải review:

- View có hiển thị cột nhạy cảm không?
- Chủ view là ai?
- Có `security_invoker` không?
- RLS của bảng nền sẽ áp dụng theo role nào?
- Hàm trong view có `SECURITY DEFINER` không?

### 31.3. Không dùng default GRANT như cơ chế phê duyệt tự động

Việc tạo một view mới không nhất thiết đồng nghĩa nó đã được security review. Một số tổ chức yêu cầu **explicit per-view grants** cho data marts nhạy cảm, thay vì default SELECT toàn schema.

## 32. Materialized views, foreign tables và objects tương tự

PostgreSQL có nhiều đối tượng ở nhóm relation mà cú pháp `ON TABLES` có thể tác động, tùy DDL và loại object:

- Ordinary tables.
- Views.
- Materialized views.
- Foreign tables.
- Partitioned tables và partitions.

### 32.1. Không đánh đồng quyền object với nguồn dữ liệu

Một foreign table có thể phụ thuộc foreign server/user mapping và các quyền khác. Một materialized view lưu kết quả vật lý và có cơ chế REFRESH riêng.

`GRANT SELECT` mặc định trên những objects đó **không tự giải quyết tất cả quyền nền** của FDW, refresh, ownership hay security.

### 32.2. Vì sao nên test từng loại?

Nếu migration tạo cả table, view, materialized view và foreign table, hãy xác nhận ACL thực tế sau CREATE đối với **đúng object type được dùng** trên phiên bản PostgreSQL cụ thể, không chỉ dựa vào một giả định “mọi thứ là table”.

## 33. Partitioned tables và partitions

Giả sử ứng dụng tạo bảng phân vùng:

```sql
CREATE TABLE app.events (
    event_id bigint,
    occurred_at timestamptz NOT NULL,
    payload jsonb
) PARTITION BY RANGE (occurred_at);
```

Rồi tạo partitions:

```sql
CREATE TABLE app.events_2027_01
PARTITION OF app.events
FOR VALUES FROM ('2027-01-01 00:00:00+00')
TO ('2027-02-01 00:00:00+00');
```

### 33.1. Default privilege theo creator lúc CREATE

Partition là một relation được tạo, nên cần xét default privileges của role tạo nó và schema đích.

### 33.2. Quyền truy cập qua parent và trực tiếp partition

Quyền khi truy vấn/ghi qua parent partitioned table có semantics khác với việc một user truy vấn trực tiếp vào partition con bằng tên riêng. Đừng mặc định `GRANT SELECT ON parent` luôn tương đương `GRANT SELECT ON mọi partition` cho mọi đường truy cập.

### 33.3. Retention job có thể cần quyền DDL khác

Job tạo/attach/drop/detach partition cần quyền owner/schema/DDL phù hợp. Default `SELECT,INSERT,UPDATE` không tự cho phép `ALTER TABLE ... ATTACH PARTITION` hay DROP partition.

### 33.4. Audit sau tạo partition

Trong hệ thống tự tạo partitions hàng ngày/tháng:

- Kiểm tra creator role của job.
- Kiểm tra schema và owner của partition.
- Kiểm tra table ACL nếu ứng dụng truy cập partition trực tiếp.
- Kiểm tra RLS, ownership và truy vấn qua parent.

## 34. Quyền trên column: đừng mặc định thay được bằng ALTER DEFAULT PRIVILEGES

PostgreSQL hỗ trợ GRANT theo cột trên bảng hiện có:

```sql
GRANT SELECT (order_id, customer_name)
ON acl_lab.orders
TO acl_reader;
```

Nhưng cấu hình default `GRANT SELECT ON TABLES` cấp quyền theo **đối tượng bảng**, không biểu diễn một chính sách “chỉ cột A và B của mọi bảng tương lai”.

### 34.1. Nếu cần dữ liệu cột nhạy cảm

Cân nhắc:

- Chia bảng/schema theo domain.
- Tạo view chỉ công bố cột được phép đọc.
- Cấp column-level grants cụ thể sau CREATE.
- Áp dụng policy cho dữ liệu nhạy cảm ở tầng ứng dụng và database.

### 34.2. Tại sao default table SELECT có thể quá rộng?

Hôm nay bảng `orders` chỉ có `customer_name`, ngày mai migration thêm `personal_id`. Nếu reader có table-level SELECT, quyền đọc cột mới có thể rộng hơn ý định ban đầu.

Default table grants cần được đánh giá cùng quy trình review schema changes, không chỉ tại thời điểm tạo bảng.

## 35. WITH GRANT OPTION và quyền ủy quyền tiếp

Một default privilege GRANT có thể có tùy chọn `WITH GRANT OPTION` khi cú pháp của quyền tương ứng cho phép:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE app_owner
    IN SCHEMA app
GRANT SELECT ON TABLES TO app_reader
WITH GRANT OPTION;
```

Ý nghĩa: role nhận quyền có thể được phép cấp lại SELECT cho role khác, theo các quy tắc privilege của PostgreSQL.

### 35.1. Nguyên tắc least privilege

Ứng dụng runtime thường **không cần quyền cấp lại GRANT**. Vì thế tránh `WITH GRANT OPTION` trong default policy trừ khi có use case ủy quyền rõ ràng.

### 35.2. Grant option khác membership admin option

Grant option trên object privilege không giống quyền quản trị role/membership. Đừng nhầm chúng với `ADMIN OPTION` hoặc quyền `CREATEROLE`.

### 35.3. PUBLIC và grant option

Không thiết kế ủy quyền tiếp cho PUBLIC theo cách bạn kỳ vọng ở một role riêng. Hãy đánh giá cụ thể các quy tắc hỗ trợ của PostgreSQL, và ưu tiên cấp cho named roles được quản lý.

## 36. Default privilege không cấp quyền CREATE tự động trên schema hiện có

Nhiều người kỳ vọng:

```sql
ALTER DEFAULT PRIVILEGES FOR ROLE app_owner
IN SCHEMA app GRANT SELECT ON TABLES TO app_reader;
```

sẽ cho `app_reader` tự tạo bảng. Hoàn toàn không đúng.

### 36.1. Ai được CREATE TABLE?

Tùy schema ownership, membership và quyền `CREATE ON SCHEMA`. Ví dụ:

```sql
GRANT CREATE ON SCHEMA app TO migration_role;
```

đây là cấp quyền cho migration role **tạo object trong schema hiện có**, không phải default grant trên tables tương lai.

### 36.2. Quyền CREATE rộng có thể làm creator role phân tán

Khi cấp CREATE cho nhiều roles trong cùng schema, các tables mới có thể thuộc các owner khác nhau và nhận default ACL khác nhau.

Đây là một lý do dùng migration owner role thống nhất và tránh cấp CREATE tràn lan cho runtime roles.

### 36.3. CREATER OLE và CREATE trên schema khác nhau

Quyền tạo role toàn hệ thống (`CREATEROLE`) không phải quyền tạo bảng trong một schema. Đội vận hành cần quản lý hai đặc quyền này độc lập.

## 37. Một thiết kế role tốt cho ứng dụng PostgreSQL

Ví dụ:

```text
deployment_login
   |
   +-- SET ROLE app_ddl_owner khi migration
           |
           +-- CREATE TABLE / VIEW / FUNCTION trong app schema

app_reader (runtime)
   |
   +-- USAGE ON SCHEMA app
   +-- SELECT ON các bảng/view đã được phê duyệt

app_writer (runtime)
   |
   +-- USAGE ON SCHEMA app
   +-- SELECT, INSERT, UPDATE (và DELETE nếu cần)
   +-- USAGE trên sequence nếu cần gọi nextval

app_function_caller
   |
   +-- EXECUTE chỉ trên routines được cho phép
```

### 37.1. Ưu điểm

- Migration có identity tạo object nhất quán.
- Runtime không cần CREATE/DROP TABLE.
- Default policies có scope rõ.
- Audit cấp quyền dễ hơn.
- Rủi ro tạo object khác owner ngoài ý định giảm.

### 37.2. Đừng cấp app_writer quyền quá rộng

Một user runtime chỉ tạo đơn hàng mới không nhất thiết cần:

```sql
DELETE
TRUNCATE
REFERENCES
TRIGGER
CREATE ON SCHEMA
```

Đối với các hành động quản trị, dùng role/workflow khác.

### 37.3. Không dùng NOLOGIN owner như mật khẩu chung

Role NOLOGIN dùng để sở hữu objects, còn login credentials thuộc các service accounts có chính sách riêng. Không đưa secret vào migration SQL hoặc file tài liệu.

## 38. SET ROLE và migration scripts

Một pipeline có thể:

```sql
-- Session đã đăng nhập bằng deployment_login
SET ROLE app_ddl_owner;

-- ALTER DEFAULT PRIVILEGES + CREATE TABLE + CREATE FUNCTION...

RESET ROLE;
```

### 38.1. Chọn current role nhất quán

Khi DDL được tạo dưới `app_ddl_owner`, policy của `FOR ROLE app_ddl_owner` áp dụng. Nếu pipeline quên SET ROLE trong một script, object có thể bị sở hữu bởi deployment_login và không nhận đúng ACL.

### 38.2. Kiểm tra trước migration

```sql
SELECT current_user, current_role, session_user;
```

Có thể thêm kiểm tra trong migration tool/entrypoint để từ chối chạy nếu current_role không phải owner kỳ vọng.

### 38.3. SET ROLE không tự vô hại

Khả năng `SET ROLE` phụ thuộc role membership và privilege. Nếu cho deployment_login được SET ROLE superuser hoặc owner chứa quá nhiều dữ liệu, đó có thể là privilege escalation ngoài nhu cầu.

### 38.4. Role hiện hành quan trọng hơn tên file migration

Một file tên `2027_create_table_as_owner.sql` không quyết định owner; PostgreSQL dùng quyền và role thực tế của session tại CREATE.

## 39. REVOKE default privileges an toàn

Nếu business muốn **ngừng tự cấp UPDATE cho writer trên các bảng tương lai**:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
    IN SCHEMA acl_lab
REVOKE UPDATE ON TABLES FROM acl_writer;
```

### 39.1. Điều gì thay đổi?

Các bảng tạo sau đó bởi acl_owner trong acl_lab không còn tự nhận UPDATE **do per-schema rule đã bị loại**, trừ khi có global default hoặc quyền khác.

### 39.2. Điều gì không thay đổi?

Những bảng đã tạo trước lệnh REVOKE vẫn giữ ACL cũ. Bạn cần:

```sql
REVOKE UPDATE ON acl_lab.orders FROM acl_writer;
```

nếu muốn thu hồi quyền trên bảng đang tồn tại.

### 39.3. Không nhầm per-schema REVOKE với global

Nếu global default vẫn cấp UPDATE cho writer, per-schema REVOKE không chặn quyền đó ở object mới.

### 39.4. Vì sao migration REVOKE có thể làm hỏng ứng dụng?

Nếu service cần cập nhật bảng mới nhưng default UPDATE bị thu hồi, deploy code có thể thành công còn request runtime bị `42501`. Cần rollout quyền và code theo thứ tự phù hợp.

## 40. Chỉ cấp quyền cho một số functions mới

Default GRANT có granularity theo **loại object + creator + schema**, không theo mọi signature function cụ thể.

Giả sử cùng schema `app` chứa:

- `app.public_format_name(text)`: hàm an toàn cho reader.
- `app.approve_refund(bigint)`: hàm có side effect và cần role nghiệp vụ riêng.

Nếu mặc định:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE app_owner
    IN SCHEMA app
GRANT EXECUTE ON FUNCTIONS TO app_reader;
```

thì **mọi function mới do app_owner tạo trong app** có thể nhận quyền EXECUTE cho reader, kể cả một function nhạy cảm mới nếu tác giả không kiểm tra sau migration.

### 40.1. Thiết kế tốt hơn

- Tách schema `api_read` và `api_write_privileged` với owner/default ACL riêng.
- Global REVOKE PUBLIC EXECUTE cho creator phù hợp.
- Chỉ explicit GRANT EXECUTE trên các function được phê duyệt.
- Dùng SECURITY DEFINER rất thận trọng; hạn chế EXECUTE vào role được ủy quyền.

### 40.2. Default privilege không phải allowlist theo tên function

Nếu cần whitelist chính xác function nào callable, explicit per-function GRANT cùng kiểm tra catalog thường rõ ràng hơn một default grant rộng.

## 41. SECURITY DEFINER và quyền EXECUTE tương lai

Hàm `SECURITY DEFINER` thường chạy với quyền của function owner theo quy tắc PostgreSQL, không chỉ quyền của caller.

Ví dụ chức năng nhạy cảm:

```sql
CREATE FUNCTION app.approve_refund(p_refund_id bigint)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    -- Đây là skeleton: cần kiểm tra quyền nghiệp vụ, transaction,
    -- search_path, RLS, idempotency, audit và ràng buộc thực.
    NULL;
END;
$$;
```

### 41.1. Tại sao default PUBLIC EXECUTE có thể nguy hiểm?

Một role bình thường có thể gọi function chạy với quyền owner mạnh hơn, nếu được EXECUTE và có đường truy cập schema. Nếu function thiếu validation/authorization, người gọi có thể thực hiện tác động không được dự định.

### 41.2. Hardening

Trong thiết kế an toàn:

- Không cho PUBLIC EXECUTE trên sensitive functions.
- Cấp EXECUTE cho named role cần thiết.
- Khóa `search_path` đáng tin cậy trong SECURITY DEFINER.
- Dùng schema-qualified references.
- Audit quyền và test dưới role không có quyền bảng nền.

### 41.3. Default PUBLIC REVOKE có lợi nhưng chưa đủ

Ngay cả khi không có PUBLIC EXECUTE, một named role được cấp quá rộng vẫn có thể gọi function. Kiểm soát người nhận GRANT và logic phân quyền bên trong function vẫn quan trọng.

## 42. RLS: quyền SELECT không bằng quyền nhìn mọi row

Giả sử bảng `app.orders` bật RLS, cho phép đọc chỉ đơn hàng của tenant hiện tại.

Một default:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE app_owner
    IN SCHEMA app
GRANT SELECT ON TABLES TO app_reader;
```

không tự vô hiệu hóa policy trên bảng.

### 42.1. Các lớp phối hợp

| Lớp | Trách nhiệm |
| --- | --- |
| Schema USAGE | Cho phép truy cập namespace |
| Table SELECT | Cho phép thực hiện phép đọc |
| RLS USING | Giới hạn row được nhìn thấy |
| View semantics | Có thể thay đổi role kiểm tra quyền/RLS ở relation nền |
| Application authorization | Ràng buộc người dùng, scope và dữ liệu trả ra |

### 42.2. Owner/BYPASSRLS

Một role là table owner hoặc có thuộc tính bypass RLS theo semantics PostgreSQL có thể không bị RLS áp dụng như một role bình thường. Khi test, sử dụng **đúng app role**, không chỉ owner/superuser.

### 42.3. Không suy luận default privileges là tenant isolation

Cấp SELECT trên bảng không tự tạo policy `tenant_id = current_tenant`. Phải thiết kế RLS/predicates/privileges riêng.

## 43. PostgreSQL role inheritance và creator mặc định

Một role có thể hưởng quyền SELECT qua membership, tùy thuộc cấu hình membership và role attributes.

Nhưng **quyền hiệu lực do membership** khác với **default ACL được chọn khi object tạo**.

### 43.1. Ví dụ

```text
acl_deployer is member of acl_owner

acl_deployer có thể hưởng quyền CREATE qua membership.
acl_deployer tự CREATE TABLE.

Owner của bảng mới: acl_deployer.
Default ACL được xét cho creator acl_deployer.
Không tự lấy default ACL của acl_owner.
```

### 43.2. SET ROLE thay creator identity

Nếu deployer thực hiện `SET ROLE acl_owner` trước CREATE thì creator role của đối tượng mới là acl_owner theo ngữ cảnh này, và default policy của owner được áp dụng.

### 43.3. Không nhầm GRANT owner TO deployer với GRANT mặc định TO reader

Hai GRANT có ý nghĩa hoàn toàn khác:

```sql
GRANT acl_owner TO acl_deployer;
```

quản lý role membership, còn:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
GRANT SELECT ON TABLES TO acl_reader;
```

quản lý ACL khởi tạo của future tables.

## 44. Object ownership drift

Một hệ thống có thể xuất hiện:

```text
app.orders         owner app_owner
app.invoices       owner deploy_login
app.events         owner app_owner
app.audit_log      owner emergency_admin
```

Dù tất cả objects ở cùng schema, chúng có thể nhận default privileges **khác nhau** tại thời điểm tạo.

### 44.1. Truy vấn audit ownership

```sql
SELECT
    n.nspname AS schema_name,
    c.relname,
    c.relkind,
    pg_get_userbyid(c.relowner) AS owner_name
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE n.nspname = 'acl_lab'
  AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
ORDER BY c.relkind, c.relname;
```

### 44.2. Tại sao ALTER OWNER không đủ?

Đổi owner sau CREATE không tái áp policy của owner mới. Phải kiểm tra actual ACL và cấp/thu hồi trực tiếp nếu cần.

### 44.3. Bảo vệ pipeline

Nên assert current_role trước DDL, kiểm tra new object owner sau DDL và báo lỗi khi lệch kỳ vọng.

## 45. Default privileges cho nhiều schema trong cùng deployment

Giả sử có:

```text
schema api_read
schema operations
schema internal_audit
```

Một owner tạo object ở cả ba schema nhưng quyền cần khác nhau:

- `api_read`: reader được SELECT.
- `operations`: writer được SELECT/INSERT/UPDATE.
- `internal_audit`: chỉ audit role được SELECT.

### 45.1. Cấu hình theo schema

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE app_owner
    IN SCHEMA api_read
GRANT SELECT ON TABLES TO app_reader;

ALTER DEFAULT PRIVILEGES
    FOR ROLE app_owner
    IN SCHEMA operations
GRANT SELECT, INSERT, UPDATE ON TABLES TO app_writer;

ALTER DEFAULT PRIVILEGES
    FOR ROLE app_owner
    IN SCHEMA internal_audit
GRANT SELECT ON TABLES TO audit_reader;
```

Đây là ví dụ với tên schema/roles giả định. Không thực thi nguyên văn nếu chưa có objects/roles và quyền phù hợp.

### 45.2. Tránh global SELECT nếu có audit schema

Global default SELECT cho app_reader có thể làm bảng audit mới cũng đọc được. Nếu cần tách rõ ràng, không dùng global rộng hoặc dùng creator roles riêng.

### 45.3. Chọn owner role theo domain

Với hệ thống lớn, thay vì một owner mọi schema, có thể dùng owner theo domain để giới hạn blast radius nếu migration role bị dùng sai.

## 46. Quyền trên đối tượng tạo trong tương lai không phải auto-sync service

Không có background job nào tự “quét mọi bảng theo định kỳ” được tạo chỉ vì bạn dùng `ALTER DEFAULT PRIVILEGES`. Quyền mặc định được **xác định tại CREATE**.

### 46.1. Các thay đổi sau CREATE

Nếu bảng:

- Được đổi tên.
- Chuyển schema.
- Đổi owner.
- Được GRANT/REVOKE trực tiếp.

thì ACL của chính bảng vẫn là trạng thái phải quản lý. Default policy không tự áp lại mỗi khi tên/schema/owner thay đổi.

### 46.2. Monitoring privilege drift

Hãy định kỳ hoặc sau deploy so sánh:

- Expected creator/owner.
- Expected schema.
- Actual ACL của objects.
- Effective privileges của reader/writer.
- Những chức năng mới trong migration.

### 46.3. Event trigger không thay thế kiến thức default ACL

Có thể xây hệ thống kiểm soát DDL bằng event triggers hoặc pipeline policy checks trong những trường hợp đặc biệt, nhưng đó là cơ chế riêng, có rủi ro vận hành và quyền riêng. Ưu tiên thiết kế role/default ACL rõ ràng trước.

## 47. Thay đổi default privileges trong transaction

PostgreSQL hỗ trợ transaction cho nhiều lệnh DDL/quản lý quyền phù hợp.

Ví dụ:

```sql
BEGIN;

ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
    IN SCHEMA acl_lab
GRANT SELECT ON TABLES TO acl_reader;

SET ROLE acl_owner;

CREATE TABLE acl_lab.created_in_migration (
    id integer PRIMARY KEY,
    payload text
);

RESET ROLE;

COMMIT;
```

### 47.1. Vì sao có lợi?

Nếu migration thất bại trước COMMIT, các thay đổi DDL/ACL trong cùng transaction thường được hoàn tác theo semantics PostgreSQL, tránh trạng thái triển khai nửa vời.

### 47.2. Có thể có exceptions

Không phải mọi thao tác quản trị PostgreSQL đều được thực thi trong transaction block, và các side effects ngoài database/sequence cần xem riêng. Với DDL cụ thể, đối chiếu phiên bản và migration tool.

### 47.3. SET ROLE trong migration

Nếu migration tool tự quản lý transaction, role switching và connection pool, phải kiểm tra cách tool giữ/khôi phục role, không tự lồng transaction tùy tiện.

## 48. REVOKE trên existing functions và default PUBLIC

Giả sử hôm nay bạn phát hiện function nhạy cảm đã tạo với PUBLIC EXECUTE.

Hai việc độc lập:

```sql
-- 1. Cho những function tương lai do owner tạo:
ALTER DEFAULT PRIVILEGES
    FOR ROLE app_owner
REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

-- 2. Cho một function đã có:
REVOKE EXECUTE
ON FUNCTION app.approve_refund(bigint)
FROM PUBLIC;
```

### 48.1. Thu hồi toàn schema

Nếu cần và có quyền:

```sql
REVOKE EXECUTE
ON ALL FUNCTIONS IN SCHEMA app
FROM PUBLIC;
```

Đây là thay đổi **lớn**, có thể làm nhiều ứng dụng ngừng hoạt động. Không chạy trước khi inventory callers, review SECURITY DEFINER và lập kế hoạch rollout.

### 48.2. Thứ tự an toàn

1. Xác định function/callers.
2. Cấp EXECUTE cụ thể cho role hợp lệ.
3. Thu hồi PUBLIC EXECUTE trên existing functions.
4. Đặt global default REVOKE cho owner của future functions.
5. Verify dưới app roles và theo dõi lỗi 42501.

### 48.3. Đừng dựa vào role naming để suy luận

Role tên `readonly_user` vẫn có thể được PUBLIC EXECUTE function ghi dữ liệu nếu ACL cho phép. Tên role không phải security policy.

## 49. Default privileges và các extension/migration tools

Không phải mọi DDL được viết cùng một cách:

- Tool migration có thể kết nối bằng deploy login khác owner.
- Extension installation có thể tạo nhiều object.
- Một job quản trị tạo partitions.
- Một task tạo temporary/staging tables.
- Một script manual sửa production.

### 49.1. Kiểm tra người tạo thật

Với các đối tượng được tạo bởi công cụ/migration, xác minh role effective lúc CREATE và ownership sau CREATE. Đừng giả định mọi object trong schema tự nhận default ACL của schema owner.

### 49.2. Test sau extension/migration

Nếu một extension hoặc script tạo function mới, có thể có quyền khác với function do role chuẩn tạo thủ công. Cần kiểm tra ACL thật, PUBLIC grants và ai có thể gọi các entrypoints nhạy cảm.

### 49.3. Staging schema không có nghĩa tự an toàn

Một staging table chứa dữ liệu cá nhân có thể nhận default SELECT nếu creator/schema trùng policy rộng. Cân nhắc schema riêng và role hạn chế hơn.

## 50. Backup và restore quyền

Khi sao lưu/khôi phục PostgreSQL, không chỉ cần dữ liệu:

- Object owners.
- GRANT/REVOKE hiện tại.
- Default ACL policies.
- Roles và memberships.
- Schema permissions.
- RLS policies và function privileges.

### 50.1. pg_dump không phải bản sao role toàn cluster

Một bản dump database có thể ghi nhiều DDL/ACL, nhưng roles là đối tượng cluster-level cần được chuẩn bị/di chuyển phù hợp. Một restore thiếu creator roles hoặc owner roles có thể lỗi hay thay đổi ownership khi dùng tùy chọn restore khác.

### 50.2. Đừng restore xong rồi chỉ test SELECT dưới superuser

Hãy kiểm tra:

1. `\\ddp` trên target.
2. Creator role của các bảng.
3. Quyền reader/writer trên objects cũ.
4. CREATE một table/function mới trong schema test tương ứng và xác minh default ACL.
5. RLS và SECURITY DEFINER behavior.

### 50.3. Backup tool flags có thể thay kết quả

Những chế độ bỏ ownership/privileges trong dump/restore có thể làm môi trường restore khác production. Cần kiểm tra options thực tế của công cụ và quy trình vận hành.

## 51. Thay đổi default policy khi schema đã có hàng nghìn object

Một anti-pattern là chạy:

```sql
ALTER DEFAULT PRIVILEGES ...
```

rồi nghĩ “vậy là xong toàn bộ quyền”.

### 51.1. Cần inventory trước

Liệt kê:

- Tables/views/sequences đang tồn tại.
- Functions và signatures.
- Types/domains.
- Owners.
- ACL và PUBLIC grants.
- Role memberships.

### 51.2. Cần migration two-phase

Đầu tiên thiết kế **quyền mong muốn**. Sau đó:

1. Cập nhật default policy cho đối tượng tương lai.
2. Cấp/thu hồi quyền trên đối tượng cũ.
3. Kiểm tra từng loại object và role.
4. Chạy smoke tests.

### 51.3. Quyền read-only không chỉ là SELECT

Một ứng dụng có thể cần USAGE trên schema, EXECUTE trên function, USAGE trên type, SELECT trên sequence cho `currval()`/đọc metadata tương ứng. Cần nhìn **SQL call graph** thực tế.

## 52. Lỗi 42501 insufficient_privilege: cách chẩn đoán

Khi ứng dụng nhận:

```text
SQLSTATE 42501
permission denied for table new_orders
```

hãy hỏi theo trình tự.

### 52.1. Object nào thật sự báo lỗi?

Không phải luôn là table trên cùng. Có thể:

- `permission denied for schema app`.
- `permission denied for sequence ...`.
- `permission denied for function ...`.
- `permission denied for relation ...`.

### 52.2. Ai đang thực thi?

```sql
SELECT current_user, current_role, session_user;
```

Trong connection pool, cần ghi nhận chính xác identity và `SET ROLE` đã áp dụng.

### 52.3. Object hiện thuộc ai?

Xem catalog `pg_class.relowner`/`pg_proc.proowner` và schema.

### 52.4. Quyền thực tế là gì?

```sql
SELECT
    has_schema_privilege('app_reader','app','USAGE'),
    has_table_privilege('app_reader','app.new_orders','SELECT');
```

### 52.5. Default policy có đúng creator không?

Tra `\\ddp` và `pg_default_acl`:

- Có entry `FOR ROLE deployer` hay chỉ `FOR ROLE app_owner`?
- Có `IN SCHEMA app` không?
- Có global grants vô tình không?
- Object đã tạo trước policy?

### 52.6. Sửa đúng lớp

- Thiếu schema USAGE → GRANT USAGE ON SCHEMA phù hợp.
- Thiếu quyền object cũ → GRANT trực tiếp.
- Policy future sai → ALTER DEFAULT PRIVILEGES cho creator/schema đúng.
- Runtime thiếu sequence/function privilege → điều chỉnh trên loại object tương ứng.
- Object owner khác kỳ vọng → sửa pipeline và xử lý ACL/ownership hiện có riêng.

## 53. JDBC: phát hiện lỗi quyền sau migration

Một service Java có thể nhận `SQLException` khi query bảng mới.

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT order_id, customer_name " +
        "FROM app.new_orders WHERE order_id = ?")) {
    ps.setLong(1, 101L);
    try (ResultSet rs = ps.executeQuery()) {
        // Xử lý kết quả.
    }
} catch (SQLException e) {
    if ("42501".equals(e.getSQLState())) {
        // Thiếu quyền: log object/role/request context an toàn,
        // trả lỗi phù hợp, không cấp quyền tự động từ ứng dụng.
    }
    throw e;
}
```

### 53.1. Không trả toàn bộ chi tiết database cho client

Thông báo lỗi có thể lộ tên schema, bảng hoặc cấu trúc nội bộ. Ánh xạ lỗi theo API contract và logging policy.

### 53.2. Không tự GRANT từ ứng dụng runtime

Một ứng dụng không nên có quyền quản trị ACL rộng để khi gặp 42501 nó tự cấp thêm mọi quyền. Đó là anti-pattern privilege escalation.

### 53.3. Kiểm thử chính xác role

Integration tests cần kết nối dưới role ứng dụng thật hoặc một role có quyền tương đương, không chỉ chạy dưới owner/superuser.

## 54. Smoke test sau migration tạo object mới

Một pipeline có thể kiểm tra các invariants:

```sql
SELECT
    has_schema_privilege('acl_reader','acl_lab','USAGE')
        AS reader_schema_usage,
    has_table_privilege('acl_reader','acl_lab.orders','SELECT')
        AS reader_orders_select,
    has_table_privilege('acl_writer','acl_lab.orders','INSERT')
        AS writer_orders_insert,
    has_sequence_privilege(
        'acl_writer','acl_lab.invoice_no_seq','USAGE'
    ) AS writer_sequence_usage,
    has_function_privilege(
        'acl_reader','acl_lab.calculate_tax(numeric)','EXECUTE'
    ) AS reader_function_execute;
```

### 54.1. Khi nào test phải fail?

Trong CI/deployment gate, nếu quyền bắt buộc là FALSE, pipeline nên fail thay vì chỉ ghi một dòng warning.

### 54.2. Kiểm tra cả điều **không được phép**

Ví dụ:

```sql
SELECT
    NOT has_table_privilege(
        'acl_reader','acl_lab.orders','DELETE'
    ) AS reader_not_allowed_delete,
    NOT has_function_privilege(
        'acl_writer','acl_lab.calculate_tax(numeric)','EXECUTE'
    ) AS writer_not_allowed_execute;
```

Một smoke test an ninh tốt kiểm tra cả quyền cần cấp **và quyền không được cấp**.

### 54.3. Kiểm thử RLS qua SELECT thực tế

`has_table_privilege=TRUE` không chứng minh RLS lọc row đúng. Cần các test dữ liệu thực dưới những tenant/roles phù hợp.

## 55. Tạo một kiểm tra tự động cho default policies

Ví dụ dùng `pg_default_acl` để xác nhận một creator có policy entry liên quan:

```sql
SELECT
    pg_get_userbyid(d.defaclrole) AS creator,
    CASE
        WHEN d.defaclnamespace = 0::oid THEN '<global>'
        ELSE d.defaclnamespace::regnamespace::text
    END AS schema_scope,
    a.privilege_type,
    pg_get_userbyid(a.grantee) AS grantee
FROM pg_default_acl AS d
CROSS JOIN LATERAL aclexplode(d.defaclacl) AS a
WHERE pg_get_userbyid(d.defaclrole) = 'acl_owner'
  AND d.defaclobjtype = 'r'
  AND a.grantee <> 0::oid
ORDER BY schema_scope, grantee, a.privilege_type;
```

### 55.1. Vì sao kiểm tra entry chưa đủ?

Một entry mặc định tồn tại nhưng:

- Migration tạo bảng dưới role khác.
- Bảng được tạo trước entry.
- Object cụ thể bị REVOKE sau CREATE.
- Schema thiếu USAGE.

Nên test cả **policy** lẫn **effective privilege trên objects mới**.

### 55.2. Test bằng một object tương lai thật

Trong database test, tạo một bảng dưới đúng creator, xác minh SELECT/INSERT, rồi rollback/drop theo chính sách. Đây là cách bắt lỗi ngữ nghĩa mà chỉ kiểm tra catalog có thể bỏ sót.

## 56. Những câu hỏi cần trả lời khi dùng DEFAULT PRIVILEGES

1. **Object nào sẽ tạo?** Table, sequence, function, type hay schema?
2. **Ai thực sự CREATE?** owner role, deployer login, job runner hay administrator?
3. **Schema đích là gì?** Một schema cố định hay nhiều schema?
4. **Quyền nào cần cấp?** SELECT, INSERT, UPDATE, EXECUTE, USAGE?
5. **Role nào nhận quyền?** Named role hay PUBLIC?
6. **Cấu hình toàn cục có đang mở quá rộng?**
7. **Có default PUBLIC EXECUTE/USAGE cần thu hồi global không?**
8. **Đối tượng đã tồn tại có cần GRANT/REVOKE riêng?**
9. **Đã cấp USAGE ON SCHEMA và các quyền phụ thuộc chưa?**
10. **App writer có cần quyền sequence không?**
11. **View/function mới có lộ dữ liệu hay tác động quyền cao hơn không?**
12. **RLS/security_invoker/SECURITY DEFINER có thay đổi đường truy cập không?**
13. **Có kiểm tra creator role khi chạy migration không?**
14. **Có test privilege theo app role sau deploy không?**
15. **Có quyền không được cấp cần được test phủ định không?**
16. **Có quy trình rollback khi thay policy làm ứng dụng lỗi không?**

## 57. Bảng anti-pattern và cách sửa

| Anti-pattern | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Chỉ `GRANT ON ALL TABLES` một lần | Bảng mới thiếu quyền | Thêm default policy cho creator |
| Chỉ `ALTER DEFAULT PRIVILEGES` | Bảng cũ vẫn thiếu quyền | GRANT trên existing objects |
| Đặt default cho schema owner nhưng deployer CREATE | Policy không áp dụng | SET ROLE owner hoặc đặt policy cho deployer |
| Tin role membership làm default ACL kế thừa | Object mới bị ACL lệch | Xác định current role tại CREATE |
| Per-schema REVOKE nhằm chặn global GRANT | Quyền vẫn được cấp | Sửa global policy, per-schema GRANT cần thiết |
| Per-schema REVOKE PUBLIC EXECUTE để chặn built-in default | Function vẫn callable rộng | Global REVOKE PUBLIC EXECUTE |
| GRANT SELECT ON TABLES và quên schema USAGE | Reader vẫn không truy cập được | GRANT USAGE ON SCHEMA |
| GRANT INSERT ON TABLES và quên sequence | nextval có thể báo permission denied | GRANT USAGE sequence nếu cần |
| GRANT ALL cho runtime | Có quyền DELETE/TRUNCATE/DDL ngoài nhu cầu | Least privilege |
| GRANT WITH GRANT OPTION cho runtime | Có thể ủy quyền tiếp | Chỉ cấp khi thực sự cần |
| Default SELECT mọi view mới | View nhạy cảm có thể bị lộ | Review view/security, tách schema |
| Coi role tên readonly là read-only | PUBLIC/other grants vẫn cho tác động | Audit effective privileges |
| Dùng default ACL như RLS | Không cô lập tenant | Tạo RLS/authorization riêng |
| Coi ALTER OWNER áp lại default ACL | ACL cũ không được tái tính | Kiểm tra và GRANT object cụ thể |
| Dùng PG catalog UPDATE để sửa ACL | Hỏng catalog/không được hỗ trợ | ALTER DEFAULT PRIVILEGES |
| Test bằng superuser | Che lỗi permission thực | Test bằng app role |
| Kiểm tra chỉ \\ddp | Không biết object ACL hiện tại | Xem \\dp + has_*_privilege |
| Kiểm tra chỉ \\dp | Không biết objects tương lai | Xem \\ddp + tạo object test |
| Cấp quyền theo tên bảng mới thủ công mỗi lần | Dễ quên/migration fail | Cấu hình future defaults phù hợp |
| Tách permission logic khỏi migration không có test | Drift giữa môi trường | Versioned grants + smoke tests |
| Coi CREATE OR REPLACE FUNCTION tự áp default lại | Existing object ACL không tự reset | Quản lý ACL object đang có |
| Bật PUBLIC EXECUTE cho SECURITY DEFINER thiếu review | Rủi ro privilege escalation | Revoke PUBLIC, grant hạn chế, secure search_path |
| Thêm cột nhạy cảm vào bảng reader có SELECT | Reader có thể thấy cột mới | Column/view/schema security review |
| Ghi script chỉ chạy dưới owner nhưng CI dùng login role | Ownership không nhất quán | Assert current_role/SET ROLE |
| Không đưa role grants vào restore checklist | Restore tạo sai quyền | Kiểm tra roles/owners/default ACL |
| App tự GRANT khi gặp 42501 | Privilege escalation | Để deployment/DBA sửa chính sách |

## 58. Thực hành củng cố: xây chính sách quyền tương lai

Trong phần này, người học ghép ba nhóm: **quyền hiện có**, **chính sách tương lai**, **quyền phụ thuộc**.

### 58.1. Yêu cầu

Ứng dụng có:

- `app_ddl_owner`: sở hữu các đối tượng và chạy migrations qua SET ROLE.
- `app_reader`: chỉ SELECT các bảng/view public được phê duyệt.
- `app_writer`: INSERT/UPDATE bảng nghiệp vụ và gọi một số sequence.
- `app_api_caller`: chỉ EXECUTE các function API được phê duyệt.

Schema:

```text
app_public
app_write
app_internal
```

### 58.2. Quyền namespace

```sql
GRANT USAGE ON SCHEMA app_public TO app_reader;
GRANT USAGE ON SCHEMA app_write TO app_writer;
GRANT USAGE ON SCHEMA app_public TO app_api_caller;
```

### 58.3. Quyền tương lai

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE app_ddl_owner
    IN SCHEMA app_public
GRANT SELECT ON TABLES TO app_reader;

ALTER DEFAULT PRIVILEGES
    FOR ROLE app_ddl_owner
    IN SCHEMA app_write
GRANT SELECT, INSERT, UPDATE ON TABLES TO app_writer;

ALTER DEFAULT PRIVILEGES
    FOR ROLE app_ddl_owner
    IN SCHEMA app_write
GRANT USAGE ON SEQUENCES TO app_writer;

ALTER DEFAULT PRIVILEGES
    FOR ROLE app_ddl_owner
REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
```

Với schema `app_internal`, không tự đặt default SELECT cho runtime role nếu không có yêu cầu.

### 58.4. Function API

Nếu không muốn mọi function của `app_public` đều có thể EXECUTE bởi app_api_caller, **không** dùng broad default GRANT EXECUTE trong schema đó; thay bằng explicit GRANT cho những function được review:

```sql
GRANT EXECUTE ON FUNCTION app_public.get_order(bigint)
TO app_api_caller;
```

### 58.5. Quyền quá khứ

Với objects đã có:

```sql
GRANT SELECT
ON ALL TABLES IN SCHEMA app_public
TO app_reader;

GRANT SELECT, INSERT, UPDATE
ON ALL TABLES IN SCHEMA app_write
TO app_writer;

GRANT USAGE
ON ALL SEQUENCES IN SCHEMA app_write
TO app_writer;
```

Các lệnh ví dụ này đòi roles/schemas/objects và quyền tương ứng, và phải review mọi object trước khi cấp hàng loạt.

### 58.6. Kiểm thử

Tạo một bảng mới với `SET ROLE app_ddl_owner` trong từng schema, kiểm tra:

- Reader chỉ có SELECT trên objects mong muốn.
- Writer có quyền ghi phù hợp.
- Không ai tự có SELECT trên app_internal vì global policy vô tình.
- Function mới không PUBLIC EXECUTE khi owner đã harden.
- Schema USAGE, RLS và function security đúng.

## 59. Bài tập thực hành PostgreSQL

Các bài dùng lab `acl_lab`, `acl_else` và các role đã tạo khi phù hợp. Chỉ chạy câu tạo role/đổi quyền khi có quyền quản trị trong database thử nghiệm.

1. **Khái niệm:** giải thích default privileges là gì và vì sao chúng không hồi tố.
2. **Phân loại:** `GRANT SELECT ON app.orders` khác `GRANT ON ALL TABLES IN SCHEMA app` ra sao?
3. **Thời gian:** vẽ T0 CREATE bảng cũ, T1 ALTER DEFAULT, T2 CREATE bảng mới, T3 REVOKE default và xác định bảng nào bị tác động.
4. **Schema:** vì sao `GRANT SELECT ON TABLES` chưa đủ nếu thiếu `USAGE ON SCHEMA`?
5. **Database:** quyền CONNECT có thuộc ALTER DEFAULT PRIVILEGES ON TABLES không?
6. **Lab roles:** tạo bốn role NOLOGIN cho owner/reader/writer/deployer.
7. **Lab schemas:** tạo acl_lab, acl_else thuộc acl_owner.
8. **Namespace:** GRANT USAGE ON SCHEMA acl_lab cho reader/writer.
9. **Bảng cũ:** tạo acl_lab.before_default trước default policy và kiểm tra reader SELECT.
10. **FOR ROLE:** phân biệt vị trí của creator role và grantee role trong câu ALTER DEFAULT PRIVILEGES.
11. **Table defaults:** cấp SELECT mặc định cho reader với IN SCHEMA acl_lab.
12. **Writer defaults:** cấp SELECT/INSERT/UPDATE mặc định cho writer trong acl_lab.
13. **Tạo bảng mới:** tạo acl_lab.orders dưới SET ROLE acl_owner.
14. **Effective privileges:** dùng has_table_privilege để kiểm tra reader SELECT và writer INSERT.
15. **Không hồi tố:** chứng minh before_default chưa nhận SELECT chỉ vì default policy được thêm.
16. **GRANT existing:** cấp SELECT trực tiếp cho before_default.
17. **ALL TABLES:** giải thích lệnh GRANT SELECT ON ALL TABLES IN SCHEMA và các hạn chế ownership.
18. **View:** tạo order_overview dưới acl_owner và kiểm tra ACL reader.
19. **VIEW security:** giải thích nguy cơ default SELECT cấp cho view nhạy cảm vừa được tạo.
20. **INSERT:** chạy INSERT dưới acl_writer, không sử dụng owner.
21. **RETURNING:** tại sao INSERT ... RETURNING có thể cần SELECT privilege bổ sung?
22. **Sequence:** đặt default USAGE, SELECT ON SEQUENCES cho writer.
23. **Sequence new:** tạo invoice_no_seq và dùng has_sequence_privilege.
24. **nextval:** thử nextval dưới writer, giải thích vì sao số sequence tăng không rollback.
25. **SERIAL vs IDENTITY:** phân biệt quyền sequence khi INSERT với nextval explicit.
26. **PUBLIC EXECUTE:** giải thích default EXECUTE cho PUBLIC trên functions và rủi ro.
27. **Global REVOKE:** đặt default REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC cho acl_owner.
28. **Per-schema function:** GRANT EXECUTE ON FUNCTIONS TO acl_reader trong acl_lab.
29. **Function mới:** tạo calculate_tax(numeric), kiểm tra reader có EXECUTE và writer không.
30. **Per-schema REVOKE:** giải thích vì sao REVOKE EXECUTE FROM PUBLIC chỉ trong acl_lab không loại global PUBLIC EXECUTE.
31. **Existing function:** nêu cách REVOKE EXECUTE trên một function đã tồn tại.
32. **Signature:** dùng has_function_privilege với function signature đúng khi có overload.
33. **TYPES:** tạo domain positive_money, kiểm tra USAGE hiện có.
34. **Default types:** đặt GRANT USAGE ON TYPES cho một named role; đối tượng tạo trước policy có đổi không?
35. **PUBLIC TYPES:** giải thích global REVOKE USAGE ON TYPES FROM PUBLIC và rủi ro tương thích.
36. **SCHEMAS:** tạo default USAGE ON SCHEMAS cho reader rồi tạo acl_future.
37. **Không nested schema:** tại sao không dùng IN SCHEMA với default privileges ON SCHEMAS?
38. **Global vs per-schema:** đặt global SELECT cho reader và per-schema INSERT cho writer; so acl_lab và acl_else.
39. **Global revoke trap:** REVOKE SELECT ở acl_else rồi giải thích vì sao global SELECT vẫn còn.
40. **Khắc phục:** thiết kế per-schema SELECT chỉ cho acl_lab mà không mở acl_else.
41. **Ranh giới role:** tạo bảng dưới acl_deployer thay vì acl_owner; kiểm tra quyền reader.
42. **Membership:** vì sao `GRANT acl_owner TO acl_deployer` không đồng nghĩa dùng default ACL của acl_owner khi CREATE?
43. **SET ROLE:** tạo bảng created_as_owner dưới acl_owner và đối chiếu với created_by_deployer.
44. **FOR ROLE deployer:** đặt default policy riêng cho acl_deployer và tạo bảng mới để kiểm tra.
45. **current_user:** so current_user, current_role, session_user trước/sau SET ROLE.
46. **ALTER OWNER:** đổi owner một bảng sau CREATE; policy của owner mới có được áp lại không?
47. **Other schema:** tạo acl_else.other_orders bằng acl_owner, giải thích quyền reader khác acl_lab.
48. **psql:** dùng `\\ddp` để xem default ACL.
49. **Existing ACL:** dùng `\\dp acl_lab.*` và đối chiếu `\\ddp`.
50. **Catalog:** truy vấn pg_default_acl, giải thích defaclrole/defaclnamespace/defaclobjtype.
51. **Global scope:** vì sao defaclnamespace=0 biểu diễn phạm vi global?
52. **aclexplode:** giải mã từng privilege_type, grantee và is_grantable.
53. **PUBLIC code:** vì sao grantee OID 0 có nghĩa PUBLIC?
54. **relacl:** tra pg_class.relacl, owner và relkind của tables/views/sequences.
55. **proacl:** tra pg_proc.proacl cho function trong acl_lab.
56. **NULL ACL:** vì sao relacl=NULL không đồng nghĩa object vô quyền?
57. **has_*_privilege:** viết query kiểm tra schema/table/sequence/function/type hiệu lực.
58. **Member grants:** giải thích role nhận SELECT thông qua membership dù không có GRANT trực tiếp.
59. **CREATE TABLE AS:** tạo order_snapshot rồi xác minh quyền theo creator/schema.
60. **Partition:** tạo một partition lab, xét owner và direct partition privileges.
61. **Materialized view:** nêu các điểm cần test riêng về quyền và REFRESH.
62. **Column security:** tại sao default table SELECT có thể lộ cột nhạy cảm thêm sau này?
63. **Grant option:** giải thích rủi ro WITH GRANT OPTION trên default SELECT cho runtime.
64. **Least privilege:** thiết kế role chỉ được tạo orders, không DELETE/TRUNCATE.
65. **Schema CREATE:** phân biệt GRANT CREATE ON SCHEMA và ALTER DEFAULT PRIVILEGES ON TABLES.
66. **Schema segmentation:** lập default policy riêng cho app_public, operations và internal_audit.
67. **Function allowlist:** thiết kế vì sao nên explicit GRANT sensitive API functions thay vì default all functions EXECUTE.
68. **SECURITY DEFINER:** giải thích vì sao PUBLIC EXECUTE trên function quyền cao đặc biệt nguy hiểm.
69. **RLS:** vì sao table SELECT hiệu lực TRUE chưa chứng minh tenant isolation?
70. **View invoker:** giải thích cách security_invoker có thể làm thay đổi quyền được kiểm tra ở bảng nền.
71. **Migration:** tạo bảng trong transaction cùng default policy và xem kết quả.
72. **REVOKE future:** bỏ UPDATE default cho writer; bảng đã có giữ quyền nào?
73. **REVOKE existing:** thu hồi UPDATE trực tiếp trên acl_lab.orders.
74. **Restore:** liệt kê role, owner, grants và default ACL cần verify sau khôi phục.
75. **42501:** lập runbook khi service đọc bảng mới bị permission denied.
76. **Java:** trong SQLException.getSQLState, phân biệt 42501 với lỗi SQL khác.
77. **CI positive test:** assert reader SELECT được bảng mới và writer INSERT được.
78. **CI negative test:** assert reader không DELETE và writer không EXECUTE function nhạy cảm.
79. **Permission drift:** thiết kế truy vấn audit ownership + ACL sau mỗi deployment.
80. **Thiết kế tổng hợp:** xây kiến trúc permissions cho hệ thống nhiều schema với migration owner, reader/writer/function caller, RLS, default ACL, GRANT existing, PUBLIC hardening và smoke tests.

## 60. Checklist triển khai an toàn

Trước khi merge hoặc chạy migration có `ALTER DEFAULT PRIVILEGES`:

1. Xác định đúng **creator role** cho mỗi loại object.
2. Đảm bảo migration chạy dưới `current_role` dự kiến.
3. Liệt kê các schema cần áp dụng.
4. Phân biệt default global và per-schema; không tạo global grant rộng ngoài chủ đích.
5. Chọn các quyền nhỏ nhất phù hợp SQL thực tế.
6. Cấp USAGE ON SCHEMA cho role cần truy cập.
7. Cấp riêng sequence privileges khi nextval/currval cần.
8. Review PUBLIC EXECUTE trên functions và PUBLIC USAGE trên types.
9. Kiểm tra hàm SECURITY DEFINER và quyền EXECUTE.
10. Kiểm tra views/RLS/security_invoker, không chỉ bảng trực tiếp.
11. Đừng mặc định GRANT SELECT cho mọi dữ liệu mới nếu schema chứa thông tin nhạy cảm.
12. Thiết lập quyền cho **existing objects** và **future objects** riêng biệt.
13. Không coi ALTER OWNER là cách áp lại default ACL.
14. Dùng `\\ddp` và `pg_default_acl` để xem policy.
15. Dùng `\\dp`, catalogs và `has_*_privilege` để xem actual/effective rights.
16. Test bằng runtime role, không chỉ owner/superuser.
17. Test cả quyền cần cấp và quyền tuyệt đối không được cấp.
18. Test một object mới tạo trong môi trường thử nghiệm.
19. Ghi nhận audit trail cho changes, reviewers, rollout và rollback plan.
20. Sau deploy, theo dõi lỗi 42501 và owner drift.

## 61. Tổng kết

Hãy ghi nhớ mô hình:

```text
ROLE THỰC SỰ CREATE OBJECT
            |
            v
DEFAULT PRIVILEGES CỦA CREATOR ROLE
            |
            +---- GLOBAL defaults
            |
            +---- PER-SCHEMA defaults (bổ sung)
            |
            v
OBJECT MỚI NHẬN ACL TẠI THỜI ĐIỂM CREATE
            |
            v
ROLE NHẬN GRANT CÓ THỂ TRUY CẬP
KHI CŨNG ĐỦ SCHEMA PRIVILEGES / RLS / CÁC QUYỀN KHÁC
```

Những nguyên tắc quan trọng nhất:

- **`ALTER DEFAULT PRIVILEGES` chỉ áp dụng cho object tương lai.** Nó không cấp/thu hồi quyền cho tables/functions/sequences đã tồn tại.
- **`FOR ROLE` là creator role, `TO` là grantee role, `IN SCHEMA` là nơi tạo object.** Nhầm một trong ba thành phần sẽ gây quyền sai.
- **Role membership không làm default ACL của parent role tự áp dụng.** Nếu migration tạo dưới deployer thay vì owner, phải dùng `SET ROLE` hoặc cấu hình riêng cho deployer.
- **Global và per-schema defaults được kết hợp theo quy tắc cộng quyền.** Per-schema REVOKE không thể triệt tiêu một global GRANT.
- **PUBLIC EXECUTE trên future functions và PUBLIC USAGE trên future types cần được cân nhắc.** Với function nhạy cảm, global default REVOKE PUBLIC và explicit GRANT là mô hình an toàn hơn broad default EXECUTE.
- **TABLES, SEQUENCES, FUNCTIONS, TYPES và SCHEMAS có các quyền khác nhau.** Cấp SELECT bảng không tự cấp USAGE schema/sequence hay EXECUTE function.
- **Least privilege là một quá trình**, không phải lệnh `GRANT ALL` chạy một lần. Review schema, cột nhạy cảm, views, RLS, SECURITY DEFINER và ownership.
- **Luôn kiểm tra cả policy lẫn quyền thực tế:** `\\ddp`/`pg_default_acl` cho tương lai; `\\dp`, catalog và `has_*_privilege` cho object đang có.
- **Kiểm thử dưới role ứng dụng** và xác minh cả những thao tác bị cấm, đặc biệt sau migration hoặc restore.

Thiết kế tốt default privileges giúp các object mới được tạo ra với quyền phù hợp ngay từ đầu, giảm lỗi `permission denied` khi mở rộng hệ thống, đồng thời tránh mở rộng quyền truy cập ngoài chủ đích. Giá trị lớn nhất của nó không chỉ là tự động hóa `GRANT`, mà là **duy trì một mô hình ownership, quyền tối thiểu và kiểm chứng bảo mật nhất quán khi PostgreSQL liên tục có bảng, sequence, view, function và schema mới**.
