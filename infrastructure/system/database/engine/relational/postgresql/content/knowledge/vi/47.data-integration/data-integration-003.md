# IMPORT FOREIGN SCHEMA và quản lý cấu trúc nguồn

`IMPORT FOREIGN SCHEMA` là lệnh SQL của PostgreSQL dùng để tạo các foreign table ở database hiện tại dựa trên cấu trúc bảng và view của một schema nằm trên máy chủ từ xa. Lệnh này thường được dùng cùng `postgres_fdw` để tích hợp dữ liệu giữa các PostgreSQL database. Sau khi import, ứng dụng có thể truy vấn đối tượng từ xa bằng cú pháp SQL quen thuộc như truy vấn bảng cục bộ.

Điểm quan trọng là lệnh chỉ nhập **metadata và định nghĩa foreign table**. Dữ liệu vẫn nằm trên máy chủ nguồn; PostgreSQL truy cập dữ liệu từ xa khi thực thi truy vấn. Cấu trúc được import cũng không tự cập nhật khi schema nguồn thay đổi. Vì vậy, cần có quy trình quản lý thay đổi để định nghĩa foreign table ở database đích luôn tương thích với cấu trúc thực tế của nguồn.

## 1. Vai trò của IMPORT FOREIGN SCHEMA trong tích hợp dữ liệu

Khi tích hợp hai database, ta thường cần một lớp đối tượng ở database đích đại diện cho các bảng hoặc view trên database nguồn. Với Foreign Data Wrapper (FDW), PostgreSQL cung cấp lớp trừu tượng này thông qua foreign table.

Một cấu hình `postgres_fdw` thường có các thành phần sau:

- **Foreign data wrapper**: extension hoặc thành phần xử lý giao tiếp với loại nguồn dữ liệu. `postgres_fdw` là FDW dành cho PostgreSQL.
- **Foreign server**: mô tả máy chủ và database từ xa mà PostgreSQL cần kết nối.
- **User mapping**: ánh xạ role ở database cục bộ sang thông tin đăng nhập ở database từ xa.
- **Local schema**: schema ở database hiện tại dùng để chứa các foreign table.
- **Foreign table**: định nghĩa cục bộ mô tả một bảng hoặc view ở nguồn từ xa.

Luồng truy cập có thể hình dung như sau:

```text
Ứng dụng / truy vấn SQL
          |
          v
Database đích: schema ext_sales
          |
          | foreign table: ext_sales.orders
          v
postgres_fdw + foreign server + user mapping
          |
          | kết nối tới database nguồn
          v
Database nguồn: schema public, bảng orders
          |
          v
Dữ liệu thực tế vẫn được lưu ở database nguồn
```

Ví dụ, database nguồn có bảng `public.orders`. Sau khi import vào schema `ext_sales` ở database đích, truy vấn có thể viết:

```sql
SELECT order_id, customer_id, order_date, total_amount
FROM ext_sales.orders
WHERE order_date >= DATE '2026-01-01';
```

`ext_sales.orders` là foreign table trong catalog của database đích. Khi truy vấn được thực thi, `postgres_fdw` kết nối đến nguồn và đọc dữ liệu tương ứng. Lệnh import không sao chép hàng dữ liệu sang database đích như `COPY`, `INSERT INTO ... SELECT` hoặc một quy trình ETL.

`IMPORT FOREIGN SCHEMA` là tính năng của cơ chế FDW. FDW cần hỗ trợ thao tác import schema thì lệnh mới có thể lấy metadata và tạo foreign table. Các tùy chọn cụ thể phụ thuộc FDW; những ví dụ về `import_collate`, `import_default`, `import_generated` và `import_not_null` dưới đây là các tùy chọn của `postgres_fdw`.

## 2. Điều kiện trước khi import

Trước khi chạy lệnh, cần chuẩn bị kết nối tới database nguồn và schema đích.

### 2.1. Cài đặt postgres_fdw

Thực hiện ở database đích:

```sql
CREATE EXTENSION IF NOT EXISTS postgres_fdw;
```

Lệnh tạo extension cung cấp foreign data wrapper `postgres_fdw`. Người thực hiện cần có quyền phù hợp để cài extension trên database.

### 2.2. Khai báo foreign server

Ví dụ database nguồn có địa chỉ `db.example.net`, cổng `5432` và tên database `sales`:

```sql
CREATE SERVER sales_source
FOREIGN DATA WRAPPER postgres_fdw
OPTIONS (
    host 'db.example.net',
    port '5432',
    dbname 'sales'
);
```

Các giá trị trong `OPTIONS` là thông tin kết nối. Với môi trường thật, cần cấu hình TLS, xác thực và mạng theo chính sách bảo mật của hệ thống. Không nên đưa mật khẩu thật vào script được lưu trong Git hoặc tài liệu dùng chung.

### 2.3. Tạo user mapping

User mapping xác định tài khoản từ xa mà một role cục bộ sẽ sử dụng. Ví dụ, tạo mapping cho role đang thực hiện migration:

```sql
CREATE USER MAPPING FOR CURRENT_USER
SERVER sales_source
OPTIONS (
    user 'sales_reader',
    password '<secret-managed-outside-source-control>'
);
```

Role `sales_reader` ở database nguồn cần có quyền truy cập schema và các bảng hoặc view được import. Nếu nhiều role cục bộ cần truy cập, có thể tạo mapping riêng cho từng role hoặc cho một role dùng chung theo thiết kế bảo mật. Mapping phải tồn tại cho role thực hiện truy vấn; mapping của một role khác không tự động được dùng thay thế.

### 2.4. Tạo schema đích và cấp quyền

```sql
CREATE SCHEMA IF NOT EXISTS ext_sales;

GRANT USAGE ON FOREIGN SERVER sales_source TO analytics_reader;
GRANT USAGE ON SCHEMA ext_sales TO analytics_reader;
```

Role thực hiện `IMPORT FOREIGN SCHEMA` cần quyền sử dụng foreign server và quyền tạo đối tượng trong schema đích. Người dùng truy vấn sau đó cần quyền `USAGE` trên schema, quyền phù hợp trên foreign table và user mapping hợp lệ.

Ví dụ cấp quyền đọc cho role phân tích sau khi các foreign table đã được tạo:

```sql
GRANT SELECT ON ALL TABLES IN SCHEMA ext_sales TO analytics_reader;
```

Ngoài quyền cục bộ, tài khoản được khai báo trong user mapping cũng phải được cấp quyền ở database nguồn. Với nguồn chỉ phục vụ đọc, nên dùng một tài khoản có quyền tối thiểu cần thiết, chẳng hạn chỉ có `USAGE` trên schema và `SELECT` trên các đối tượng được phép truy cập.

## 3. Cú pháp IMPORT FOREIGN SCHEMA

Cú pháp tổng quát:

```sql
IMPORT FOREIGN SCHEMA remote_schema
    [ LIMIT TO ( table_name [, ...] )
    | EXCEPT ( table_name [, ...] ) ]
    FROM SERVER server_name
    INTO local_schema
    [ OPTIONS ( option 'value' [, ...] ) ];
```

Ý nghĩa các thành phần:

| Thành phần | Ý nghĩa |
|---|---|
| `remote_schema` | Tên schema ở database nguồn cần lấy metadata. |
| `LIMIT TO` | Chỉ import các bảng hoặc view được liệt kê. |
| `EXCEPT` | Import các đối tượng trong schema nguồn, ngoại trừ các tên được liệt kê. |
| `FROM SERVER` | Chọn foreign server đã khai báo ở database đích. |
| `INTO` | Chọn schema cục bộ sẽ chứa các foreign table được tạo. Schema này phải tồn tại. |
| `OPTIONS` | Truyền các tùy chọn riêng cho FDW. |

Tên đối tượng trong danh sách là identifier SQL. Nếu tên được tạo có chữ hoa, dấu cách hoặc ký tự đặc biệt, cần đặt trong dấu ngoặc kép theo quy tắc identifier của PostgreSQL.

### 3.1. Import toàn bộ schema

Nếu không dùng `LIMIT TO` hoặc `EXCEPT`, lệnh yêu cầu FDW import các đối tượng mà FDW hỗ trợ trong schema nguồn:

```sql
IMPORT FOREIGN SCHEMA public
FROM SERVER sales_source
INTO ext_sales;
```

Với `postgres_fdw`, thao tác này tạo foreign table tương ứng với các bảng và view được hỗ trợ trong schema `public` ở database nguồn.

### 3.2. Chỉ import các đối tượng cần thiết bằng LIMIT TO

Trong môi trường thực tế, nên xác định rõ tập đối tượng cần tích hợp. Ví dụ chỉ import khách hàng, đơn hàng và chi tiết đơn hàng:

```sql
IMPORT FOREIGN SCHEMA public
    LIMIT TO (customers, orders, order_items)
    FROM SERVER sales_source
    INTO ext_sales;
```

`LIMIT TO` giúp schema đích chỉ chứa những đối tượng mà ứng dụng cần dùng. Cách này giảm phạm vi phụ thuộc vào nguồn, hạn chế vô tình mở rộng quyền truy cập và giúp việc theo dõi thay đổi dễ dàng hơn.

### 3.3. Loại trừ một số đối tượng bằng EXCEPT

Khi cần import phần lớn schema nhưng muốn bỏ qua một số bảng, có thể dùng `EXCEPT`:

```sql
IMPORT FOREIGN SCHEMA public
    EXCEPT (audit_log, temporary_imports)
    FROM SERVER sales_source
    INTO ext_sales;
```

`EXCEPT` hữu ích khi schema nguồn có nhiều bảng dùng chung. Tuy nhiên, nếu chỉ một số ít bảng được phép tích hợp, danh sách cho phép bằng `LIMIT TO` thường dễ kiểm soát hơn danh sách loại trừ.

### 3.4. Chọn tùy chọn import của postgres_fdw

`postgres_fdw` hỗ trợ các tùy chọn sau trong lệnh import:

| Tùy chọn | Mặc định | Tác dụng |
|---|---:|---|
| `import_collate` | `true` | Có đưa thông tin `COLLATE` của cột vào định nghĩa foreign table hay không. |
| `import_default` | `false` | Có đưa biểu thức `DEFAULT` của cột vào định nghĩa hay không. |
| `import_generated` | `true` | Có đưa biểu thức của cột `GENERATED` vào định nghĩa hay không. |
| `import_not_null` | `true` | Có đưa thuộc tính `NOT NULL` của cột vào định nghĩa hay không. |

Ví dụ:

```sql
IMPORT FOREIGN SCHEMA public
    LIMIT TO (customers, orders)
    FROM SERVER sales_source
    INTO ext_sales
    OPTIONS (
        import_collate 'true',
        import_default 'false',
        import_generated 'true',
        import_not_null 'true'
    );
```

Một số điểm cần lưu ý khi chọn tùy chọn:

- `import_default` mặc định là `false`. Nếu bật, biểu thức mặc định được sao chép vào định nghĩa cục bộ. Biểu thức đó có thể được tính khác ở hai máy chủ; ví dụ `nextval()` có thể tham chiếu sequence hoặc trạng thái khác. Import cũng có thể thất bại nếu biểu thức dùng function hoặc operator không tồn tại ở database đích.
- `import_generated` mặc định là `true`. Biểu thức generated được import phải tham chiếu các kiểu, function và operator tương thích ở database đích.
- `import_collate` mặc định là `true`. Tên collation hoặc collation mặc định giữa hai máy chủ có thể khác nhau, đặc biệt khi hai hệ điều hành khác nhau. Tắt tùy chọn này không phải cách sửa an toàn trong mọi trường hợp: collation không tương thích có thể làm thay đổi kết quả so sánh và sắp xếp.
- `import_not_null` mặc định là `true`, nên thuộc tính `NOT NULL` được đưa vào định nghĩa foreign table.

`postgres_fdw` không tự import các constraint khác như `CHECK`, khóa chính, khóa duy nhất hoặc khóa ngoại. Nếu cần dùng những ràng buộc đó ở database đích, phải thiết kế và tạo thủ công sau khi xác minh rằng biểu thức và ý nghĩa của chúng phù hợp với dữ liệu từ xa. Các kiểu dữ liệu do người dùng định nghĩa ở nguồn cũng cần có kiểu tương thích với cùng tên ở database đích.

## 4. Ví dụ hoàn chỉnh

Giả sử database `sales` ở máy chủ nguồn có schema `public` với các bảng `customers`, `orders`, `order_items`. Database đích cần truy vấn ba đối tượng này để phục vụ báo cáo.

Các lệnh cấu hình ở database đích:

```sql
-- 1. Cài FDW.
CREATE EXTENSION IF NOT EXISTS postgres_fdw;

-- 2. Khai báo database nguồn.
CREATE SERVER sales_source
FOREIGN DATA WRAPPER postgres_fdw
OPTIONS (
    host 'db.example.net',
    port '5432',
    dbname 'sales'
);

-- 3. Khai báo thông tin đăng nhập từ xa cho role thực hiện migration.
CREATE USER MAPPING FOR CURRENT_USER
SERVER sales_source
OPTIONS (
    user 'sales_reader',
    password '<secret-managed-outside-source-control>'
);

-- 4. Chuẩn bị schema cục bộ.
CREATE SCHEMA IF NOT EXISTS ext_sales;

-- 5. Import đúng các đối tượng cần dùng.
IMPORT FOREIGN SCHEMA public
    LIMIT TO (customers, orders, order_items)
    FROM SERVER sales_source
    INTO ext_sales
    OPTIONS (
        import_default 'false',
        import_generated 'true',
        import_not_null 'true'
    );
```

Sau khi import thành công, có thể truy vấn:

```sql
SELECT order_id, customer_id, order_date, total_amount
FROM ext_sales.orders
WHERE order_date >= DATE '2026-01-01'
ORDER BY order_date DESC
LIMIT 20;
```

Có thể kết hợp foreign table với bảng cục bộ trong cùng một câu truy vấn:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS order_count
FROM ext_sales.customers AS c
LEFT JOIN ext_sales.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY order_count DESC;
```

Truy vấn vẫn chịu ảnh hưởng của quyền truy cập, trạng thái kết nối, độ trễ mạng và khả năng xử lý của database nguồn. Foreign table không phải bản sao dữ liệu cục bộ; mỗi truy vấn cần đọc dữ liệu từ nguồn theo kế hoạch thực thi của FDW.

## 5. Kiểm tra cấu trúc đã import

Sau khi import, cần biết foreign table nào đã được tạo và các cột được khai báo ra sao. Có thể dùng `psql` hoặc các view hệ thống.

### 5.1. Liệt kê foreign table

Trong `psql`, lệnh sau hiển thị các foreign table:

```text
\det+ ext_sales.*
```

Hoặc dùng `information_schema.foreign_tables`:

```sql
SELECT
    foreign_table_schema,
    foreign_table_name,
    foreign_server_name
FROM information_schema.foreign_tables
WHERE foreign_table_schema = 'ext_sales'
ORDER BY foreign_table_name;
```

### 5.2. Xem định nghĩa cột

```sql
SELECT
    table_name,
    ordinal_position,
    column_name,
    data_type,
    udt_schema,
    udt_name,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'ext_sales'
ORDER BY table_name, ordinal_position;
```

View `information_schema.columns` cho biết định nghĩa cột mà database đích hiện đang lưu. Đây là metadata cục bộ của foreign table; nó không tự truy vấn để so sánh với schema mới nhất trên nguồn. Muốn biết nguồn đã thay đổi hay chưa, cần đọc metadata trực tiếp ở database nguồn hoặc import vào một schema kiểm tra riêng.

### 5.3. Kiểm tra khả năng truy cập dữ liệu

```sql
SELECT *
FROM ext_sales.orders
LIMIT 5;
```

Truy vấn nhỏ giúp xác nhận kết nối, user mapping, quyền từ xa và ánh xạ cột hoạt động. Khi cần xem phần truy vấn được đẩy sang máy chủ từ xa, có thể dùng:

```sql
EXPLAIN (VERBOSE, COSTS OFF)
SELECT order_id, total_amount
FROM ext_sales.orders
WHERE customer_id = 1001;
```

Với `postgres_fdw`, phần `Remote SQL` trong kế hoạch chi tiết giúp hiểu câu truy vấn được gửi đến database nguồn như thế nào.

## 6. Quản lý thay đổi cấu trúc ở nguồn

Import schema là thao tác lấy metadata tại một thời điểm. Sau khi foreign table được tạo, database đích giữ định nghĩa cột cục bộ của nó. Nếu quản trị viên thêm, xóa, đổi tên hoặc đổi kiểu cột ở nguồn, định nghĩa foreign table không tự thay đổi theo.

Ví dụ nguồn có bảng:

```sql
CREATE TABLE public.orders (
    order_id bigint,
    customer_id bigint,
    order_date date,
    total_amount numeric(12, 2)
);
```

Sau đó nguồn bổ sung cột:

```sql
ALTER TABLE public.orders
ADD COLUMN sales_channel text;
```

Foreign table `ext_sales.orders` hiện có không tự xuất hiện cột `sales_channel`. Truy vấn cột mới qua foreign table sẽ thất bại cho đến khi định nghĩa cục bộ được cập nhật. Tương tự, thay đổi kiểu dữ liệu, đổi tên hoặc xóa cột ở nguồn có thể làm truy vấn cũ lỗi hoặc trả về kết quả không còn đúng với kỳ vọng của ứng dụng.

### 6.1. Phân loại thay đổi

| Thay đổi ở nguồn | Ảnh hưởng có thể gặp ở database đích | Hướng xử lý |
|---|---|---|
| Thêm cột | Foreign table cũ chưa khai báo cột mới. | Cập nhật foreign table hoặc import lại vào schema kiểm tra rồi chuyển đổi. |
| Xóa cột | Truy vấn còn tham chiếu cột đã bị xóa ở nguồn có thể thất bại. | Tìm và cập nhật consumer trước khi xóa; sau đó sửa định nghĩa cục bộ. |
| Đổi tên cột | Tên cột cục bộ cũ có thể không còn ánh xạ đúng tới nguồn. | Cập nhật ánh xạ cột hoặc định nghĩa foreign table và sửa truy vấn liên quan. |
| Đổi kiểu dữ liệu | Kiểu cục bộ có thể không còn tương thích với kiểu ở nguồn. | Kiểm tra khả năng chuyển đổi, cập nhật kiểu cục bộ và kiểm thử truy vấn. |
| Thêm hoặc xóa bảng | Danh sách foreign table cục bộ không tự đồng bộ. | Import đối tượng mới hoặc gỡ đối tượng không còn dùng sau khi kiểm tra phụ thuộc. |
| Đổi tên bảng hoặc schema | Foreign table có thể tiếp tục trỏ đến tên nguồn cũ. | Cập nhật tùy chọn ánh xạ tên của FDW hoặc tạo lại foreign table. |

Thay đổi bổ sung như thêm cột thường ít gây gián đoạn hơn thay đổi phá vỡ như xóa hoặc đổi kiểu cột. Tuy nhiên, ngay cả thay đổi bổ sung cũng cần cập nhật metadata nếu ứng dụng muốn sử dụng cột mới.

### 6.2. Import vào schema kiểm tra trước khi chuyển đổi

Với thay đổi quan trọng, có thể tạo schema tạm để import cấu trúc mới:

```sql
CREATE SCHEMA ext_sales_stage;

IMPORT FOREIGN SCHEMA public
    LIMIT TO (customers, orders, order_items)
    FROM SERVER sales_source
    INTO ext_sales_stage;
```

Sau đó kiểm tra danh sách bảng và cột trong `ext_sales_stage`, chạy truy vấn thử, so sánh với schema đang dùng và xác định các truy vấn hoặc view cần điều chỉnh. Cách này cho phép chuẩn bị metadata mới mà không phải thay đổi ngay các foreign table đang được ứng dụng sử dụng.

Khi đã xác nhận cấu trúc mới, cập nhật lớp truy cập ổn định của ứng dụng theo kế hoạch triển khai. Ví dụ, có thể tạo view cục bộ với danh sách cột rõ ràng:

```sql
CREATE SCHEMA IF NOT EXISTS reporting;

CREATE OR REPLACE VIEW reporting.orders AS
SELECT
    order_id,
    customer_id,
    order_date,
    total_amount
FROM ext_sales_stage.orders;
```

View giúp tách tên và hình dạng dữ liệu mà ứng dụng sử dụng khỏi tên foreign table. Nên liệt kê cột tường minh thay vì `SELECT *`, nhờ đó việc nguồn thêm cột không vô tình làm thay đổi giao diện dữ liệu của view. Nếu thay đổi làm mất hoặc đổi kiểu cột mà ứng dụng đang phụ thuộc, cần migration tương ứng hoặc tạo phiên bản view mới.

Chỉ xóa schema hoặc foreign table cũ sau khi đã kiểm tra các view, function, báo cáo và ứng dụng không còn phụ thuộc vào chúng. `DROP ... CASCADE` có thể xóa thêm đối tượng phụ thuộc, vì vậy cần hiểu rõ phạm vi trước khi sử dụng.

### 6.3. Cập nhật foreign table thủ công

Nếu thay đổi nhỏ và đã xác định chính xác metadata cần cập nhật, có thể dùng `ALTER FOREIGN TABLE`. Ví dụ thêm cột tương ứng với cột mới ở nguồn:

```sql
ALTER FOREIGN TABLE ext_sales.orders
ADD COLUMN sales_channel text;
```

Nếu nguồn đổi tên cột nhưng muốn giữ tên cột cục bộ để tránh sửa nhiều truy vấn, `postgres_fdw` hỗ trợ tùy chọn `column_name` ở cấp cột. Ví dụ ánh xạ cột cục bộ `customer_id` sang cột `buyer_id` ở nguồn:

```sql
ALTER FOREIGN TABLE ext_sales.orders
ALTER COLUMN customer_id
OPTIONS (ADD column_name 'buyer_id');
```

Tương tự, tùy chọn `table_name` ở cấp foreign table có thể dùng để ánh xạ tên cục bộ ổn định sang tên bảng đã đổi ở nguồn:

```sql
ALTER FOREIGN TABLE ext_sales.orders
OPTIONS (ADD table_name 'sales_orders');
```

Chỉ dùng `ADD` khi tùy chọn chưa tồn tại; nếu tùy chọn đã có, dùng thao tác `SET` phù hợp. Cần xác minh tên cột, tên bảng và kiểu dữ liệu thực tế ở nguồn trước khi thay đổi ánh xạ. Việc đổi metadata cục bộ không tự sửa cấu trúc ở database nguồn.

Khi phải thay đổi nhiều cột hoặc có thay đổi phá vỡ, import vào schema mới thường dễ kiểm soát hơn việc chỉnh từng cột tại chỗ. Nếu cần xóa và tạo lại foreign table, hãy xem xét các đối tượng phụ thuộc trước; thao tác `DROP FOREIGN TABLE` có thể bị từ chối khi còn dependency, còn `CASCADE` sẽ xóa cả những đối tượng phụ thuộc đó.

### 6.4. Thiết lập quy trình quản lý schema

Một quy trình quản lý thay đổi nguồn có thể gồm các bước sau:

1. **Ghi nhận thay đổi từ chủ sở hữu nguồn**: xác định bảng, cột, kiểu dữ liệu, nullability và thời điểm thay đổi.
2. **Đọc metadata mới**: kiểm tra trực tiếp schema nguồn, không giả định foreign table hiện tại phản ánh trạng thái mới nhất.
3. **Đánh giá ảnh hưởng**: tìm các truy vấn, view, báo cáo và job đang dùng bảng hoặc cột liên quan.
4. **Chuẩn bị định nghĩa mới**: dùng `ALTER FOREIGN TABLE` cho thay đổi nhỏ hoặc import vào schema kiểm tra cho thay đổi lớn.
5. **Kiểm tra quyền và dữ liệu**: xác nhận user mapping, quyền từ xa, kiểu dữ liệu và các truy vấn đại diện.
6. **Triển khai theo thứ tự tương thích**: nếu có thể, thêm cấu trúc mới trước, chuyển consumer sang cấu trúc mới, rồi mới loại bỏ cấu trúc cũ.
7. **Ghi lại phiên bản và thời điểm áp dụng**: lưu script migration, schema nguồn tương ứng và kết quả triển khai để có thể truy vết.

Nên coi thay đổi schema là một phần của hợp đồng tích hợp giữa nhóm sở hữu database nguồn và nhóm sử dụng dữ liệu. Thông báo trước các thay đổi phá vỡ giúp nhóm đích có thời gian cập nhật và kiểm tra.

## 7. Các giới hạn cần hiểu khi import

`IMPORT FOREIGN SCHEMA` giúp khởi tạo nhanh định nghĩa foreign table, nhưng không thay thế toàn bộ quá trình thiết kế schema ở database đích.

- **Không sao chép dữ liệu**: dữ liệu được đọc từ nguồn khi truy vấn. Nếu cần bản sao độc lập để phân tích hoặc lưu trữ, cần thiết kế ETL, logical replication hoặc cơ chế sao chép phù hợp.
- **Không đồng bộ schema liên tục**: thêm hoặc đổi cột ở nguồn không tự cập nhật foreign table đã tạo.
- **Không import mọi ràng buộc**: với `postgres_fdw`, chỉ `NOT NULL` được hỗ trợ qua tùy chọn import tương ứng; các constraint khác cần xử lý thủ công.
- **Không thay thế phân quyền**: quyền trên foreign server, schema và foreign table ở database đích vẫn cần cấu hình; tài khoản từ xa cũng phải có quyền truy cập nguồn.
- **Không bảo đảm mọi kiểu dữ liệu tùy chỉnh tương thích**: kiểu do người dùng định nghĩa cần có kiểu tương ứng ở database đích.
- **Không loại bỏ chi phí mạng**: truy vấn chịu độ trễ và khả năng sẵn sàng của database nguồn. Nên chọn cột và lọc dữ liệu hợp lý, đồng thời kiểm tra kế hoạch thực thi.
- **Không tự giải quyết khác biệt ngữ nghĩa**: collation, biểu thức mặc định, generated expression và cách xử lý kiểu dữ liệu có thể khác nhau giữa hai máy chủ.

Ngoài ra, `postgres_fdw` mặc định giả định foreign table có thể được cập nhật, nhưng thao tác `INSERT`, `UPDATE`, `DELETE` hoặc `TRUNCATE` chỉ thành công khi đối tượng và tài khoản từ xa thực sự cho phép. Với tích hợp chỉ đọc, nên cấp quyền đọc ở nguồn và cân nhắc cấu hình `updatable 'false'` hoặc `truncatable 'false'` ở mức phù hợp để tránh thao tác ngoài ý muốn.

## 8. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra hoặc khắc phục |
|---|---|---|
| `permission denied for foreign server` | Role thực hiện truy vấn hoặc import chưa có quyền `USAGE` trên foreign server. | Cấp `GRANT USAGE ON FOREIGN SERVER ...` cho role phù hợp. |
| `user mapping not found` | Chưa có user mapping cho role đang thực hiện truy vấn. | Tạo mapping cho đúng role hoặc thiết kế mapping chung theo chính sách bảo mật. |
| Kết nối từ xa bị từ chối | Sai host, port, database, mật khẩu, TLS hoặc cấu hình `pg_hba.conf` ở nguồn. | Kiểm tra thông tin server, xác thực và quyền kết nối ở máy chủ nguồn. |
| `permission denied` trên bảng nguồn | Tài khoản trong user mapping chưa có quyền trên schema hoặc bảng nguồn. | Cấp `USAGE` trên schema và quyền cần thiết trên bảng hoặc view ở nguồn. |
| `schema does not exist` hoặc không tìm thấy đối tượng | Tên schema nguồn sai, sai database hoặc role từ xa không nhìn thấy đối tượng. | Kiểm tra database trong foreign server, tên schema và quyền metadata ở nguồn. |
| Lỗi kiểu dữ liệu hoặc function không tồn tại khi import | Nguồn dùng kiểu tùy chỉnh hoặc biểu thức mặc định/generated không có thành phần tương thích ở đích. | Tạo kiểu/function tương thích hoặc điều chỉnh tùy chọn import sau khi đánh giá tác động. |
| Lỗi collation | Collation ở nguồn không có hoặc không tương thích ở đích. | Kiểm tra collation hai máy chủ; chỉ thay đổi `import_collate` khi đã xác minh ngữ nghĩa so sánh. |
| Lỗi đối tượng đã tồn tại | Schema đích đã có foreign table trùng tên. | Import vào schema kiểm tra hoặc lập kế hoạch cập nhật/xóa đối tượng cũ sau khi xử lý dependency. |
| Truy vấn không thấy cột mới | Foreign table được import trước khi nguồn thêm cột. | Cập nhật định nghĩa bằng `ALTER FOREIGN TABLE` hoặc import lại vào schema mới. |
| Truy vấn lỗi sau khi nguồn đổi tên/xóa cột | Metadata cục bộ vẫn ánh xạ tới tên nguồn cũ. | Cập nhật column mapping hoặc định nghĩa foreign table và sửa consumer liên quan. |

Khi xử lý lỗi, nên phân biệt lỗi ở ba lớp: kết nối và xác thực, quyền truy cập, và sự tương thích của metadata. Kiểm tra từng lớp giúp xác định đúng nơi cần sửa thay vì thay đổi schema một cách không cần thiết.

## 9. Kinh nghiệm vận hành

- Chỉ import những bảng và view thật sự cần dùng; ưu tiên `LIMIT TO` khi danh sách tích hợp đã biết.
- Dùng role từ xa có quyền tối thiểu. Tách role thực hiện migration khỏi role ứng dụng nếu quy trình vận hành yêu cầu.
- Quản lý SQL tạo server, user mapping, schema và import bằng migration có phiên bản. Không lưu mật khẩu thật trong repository.
- Dùng schema kiểm tra để tiếp nhận thay đổi lớn, so sánh metadata và chạy truy vấn đại diện trước khi chuyển ứng dụng.
- Tạo view cục bộ làm lớp giao diện ổn định khi nhiều ứng dụng cùng dùng dữ liệu nguồn. Liệt kê cột rõ ràng và thay đổi giao diện qua migration có kiểm soát.
- Theo dõi thay đổi schema nguồn cùng chủ sở hữu nguồn. Không coi việc import thành công trước đây là bằng chứng rằng metadata hiện tại vẫn tương thích.
- Kiểm tra kế hoạch truy vấn và độ trễ mạng đối với truy vấn lớn. `postgres_fdw` có thể đẩy một số phép lọc và phép nối sang nguồn, nhưng không phải mọi biểu thức đều được đẩy xuống.
- Dọn foreign table hoặc schema cũ sau khi xác nhận không còn dependency và consumer đã chuyển đổi.

## 10. Tổng kết

`IMPORT FOREIGN SCHEMA` giúp tạo nhanh foreign table từ các bảng và view ở schema từ xa. Với `postgres_fdw`, có thể giới hạn đối tượng bằng `LIMIT TO` hoặc `EXCEPT`, điều chỉnh metadata được import bằng các tùy chọn và truy vấn nguồn bằng SQL thông thường. Dữ liệu vẫn nằm ở máy chủ nguồn, còn định nghĩa foreign table được lưu ở database đích.

Vì định nghĩa cục bộ không tự đồng bộ khi schema nguồn thay đổi, việc quản lý cấu trúc cần có kiểm tra metadata, migration có phiên bản, schema kiểm tra cho thay đổi lớn và lớp view ổn định cho ứng dụng. Cách làm này giúp duy trì hợp đồng dữ liệu rõ ràng giữa database nguồn và database tích hợp.

## Tài liệu tham khảo

- [PostgreSQL — IMPORT FOREIGN SCHEMA](https://www.postgresql.org/docs/current/sql-importforeignschema.html)
- [PostgreSQL — postgres_fdw](https://www.postgresql.org/docs/current/postgres-fdw.html)
- [PostgreSQL — Foreign Data](https://www.postgresql.org/docs/current/ddl-foreign-data.html)
