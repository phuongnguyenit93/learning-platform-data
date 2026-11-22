# Lệnh trợ giúp, liệt kê đối tượng và mô tả cấu trúc trong psql

Khi mới kết nối vào một PostgreSQL server, bạn thường chưa biết database hiện tại có những schema nào, bảng nằm ở đâu, tên cột được khai báo ra sao hay một khóa ngoại đang tham chiếu bảng nào. Bạn cũng có thể quên cú pháp một lệnh SQL như `ALTER TABLE` hoặc cần kiểm tra một view, index, function trước khi sửa chương trình.

**`psql`** là chương trình khách dòng lệnh chính thức, rất hữu ích để khám phá cấu trúc PostgreSQL. Ngoài khả năng gửi SQL đến server, psql có một hệ thống **meta-command** bắt đầu bằng dấu gạch chéo ngược `\`. Những lệnh như `\?`, `\h`, `\l`, `\dn`, `\dt`, `\d` và `\d+` giúp nhận trợ giúp, liệt kê đối tượng và đọc cấu trúc ngay trong terminal.

Bài học này hướng dẫn cách dùng chúng để **đi từ một kết nối chưa biết gì đến bản đồ các đối tượng trong database**, biết cách lọc theo schema, nhận diện quyền và những bẫy thường gặp. Nội dung tập trung vào PostgreSQL và **các lệnh chạy bên trong psql**, không nhầm chúng với lệnh SQL hay chương trình shell khác.

## 1. Phân biệt ba loại câu lệnh khi làm việc với PostgreSQL

Một người học thường gõ được `SELECT` nhưng không hiểu tại sao `\dt` không chạy trong một JDBC client, hoặc ngược lại gõ `psql -U ...` ngay trong cửa sổ SQL.

Hãy tách ba lớp:

| Loại | Chạy ở đâu? | Ví dụ | Vai trò |
|---|---|---|---|
| **Lệnh hệ điều hành / shell** | Terminal của hệ điều hành | `psql -h localhost -U app_user -d appdb` | Mở chương trình psql và kết nối |
| **SQL** | Gửi tới PostgreSQL server | `SELECT current_database();` | Truy vấn hoặc thay đổi dữ liệu/đối tượng |
| **Meta-command psql** | Được psql xử lý ở client | `\dt`, `\d public.orders` | Trợ giúp, điều khiển client, truy vấn metadata |

Ví dụ trong terminal:

~~~bash
psql -h localhost -p 5432 -U app_user -d appdb
~~~

Sau khi kết nối, có thể gặp lời nhắc:

~~~text
appdb=>
~~~

Gõ SQL:

~~~sql
SELECT current_database();
~~~

Hoặc meta-command:

~~~text
\dt
~~~

**SQL** thông thường kết thúc bằng dấu chấm phẩy `;`. **Meta-command** bắt đầu bằng `\` và thường kết thúc ở cuối dòng nhập, **không cần dấu chấm phẩy**. Viết `\dt;` không phải cách chuẩn để kết thúc meta-command; dấu chấm phẩy có thể bị hiểu là một phần của đối số.

Nếu bạn dùng DBeaver, pgAdmin, trình soạn thảo SQL của cloud hoặc JDBC, hãy kiểm tra công cụ có hỗ trợ meta-command psql hay không. Nhiều công cụ gửi trực tiếp SQL và **không nhận `\d` hoặc `\?` như SQL**.

### 1.1. Lệnh psql không tạo ra một "ngôn ngữ SQL mới"

Các lệnh `\d`, `\dt` hay `\df` là **giao diện thuận tiện** của psql để đọc catalog PostgreSQL. Chúng có thể thực hiện các truy vấn metadata ở phía sau, nhưng bạn không thể giả định server hiểu trực tiếp cú pháp gạch chéo ngược.

Muốn tự động hóa bằng JDBC hoặc xây công cụ hỗ trợ nhiều khách SQL, thường dùng `pg_catalog`, `information_schema` hoặc PostgreSQL JDBC `DatabaseMetaData`, thay vì gửi nguyên văn `\dt`.

## 2. Kết nối vào đúng server và database

Một cách gọi phổ biến từ shell:

~~~bash
psql -h localhost -p 5432 -U app_user -d appdb
~~~

Giải thích các tùy chọn:

| Tùy chọn | Ý nghĩa |
|---|---|
| `-h` | Hostname hoặc địa chỉ server |
| `-p` | Cổng kết nối; 5432 là mặc định thường gặp |
| `-U` | Tên role đăng nhập |
| `-d` | Database sẽ kết nối |
| `-f` | Đọc câu lệnh từ một tệp script |
| `-c` | Chạy một chuỗi lệnh hoặc một meta-command thích hợp rồi thoát |
| `-X` | Không đọc tệp khởi tạo psql của người dùng; hữu ích cho chạy script có tính lặp lại |
| `-v` | Đặt một biến psql, ví dụ kiểm soát dừng khi lỗi |

Không đưa mật khẩu thật trực tiếp vào câu lệnh terminal hoặc commit vào repository. Cơ chế xác thực có thể dùng prompt, password file được bảo vệ, biến môi trường theo chính sách triển khai hoặc dịch vụ quản lý secret.

### 2.1. Xác nhận thông tin kết nối với \conninfo

Ngay khi vào psql, nên gõ:

~~~text
\conninfo
~~~

Lệnh cho biết thông tin kết nối hiện tại, chẳng hạn database, user, host, port và TLS khi thích hợp. Đây là bước đơn giản để tránh thao tác nhầm trên production thay vì môi trường phát triển.

Đối chiếu bằng SQL:

~~~sql
SELECT
    current_database() AS database_name,
    current_user AS active_role,
    session_user AS session_role,
    current_schema() AS current_schema,
    inet_server_addr() AS server_address,
    inet_server_port() AS server_port;
~~~

`inet_server_addr()` có thể trả `NULL` khi kết nối qua Unix-domain socket; đây không phải bằng chứng kết nối bị lỗi.

### 2.2. Chuyển database trong psql

~~~text
\c appdb
~~~

Hoặc nêu tên database, user và host nếu cần:

~~~text
\connect appdb app_user localhost 5432
~~~

`\c` là dạng viết tắt của `\connect`. Khi chuyển database, psql tạo một kết nối đến database mục tiêu theo quy tắc kết nối của nó.

Trong PostgreSQL, **schema nằm bên trong database**. Thay đổi database khác với chỉ đổi schema. Một session PostgreSQL bình thường không thể dùng cú pháp tên ba phần để trực tiếp JOIN bảng thuộc hai database khác nhau giống một số hệ RDBMS khác.

### 2.3. Thoát khỏi psql

~~~text
\q
~~~

Đây là meta-command để thoát client, không phải SQL `QUIT;` gửi tới server.

## 3. Hai công cụ trợ giúp quan trọng nhất: \? và \h

Khi quên cú pháp, hãy sử dụng hệ thống trợ giúp sẵn có thay vì đoán.

### 3.1. \? — trợ giúp meta-command psql

~~~text
\?
~~~

Lệnh này hiển thị các lệnh điều khiển psql cùng mô tả ngắn. Bạn có thể tìm nhóm lệnh dành cho:

- Truy cập kết nối và database.
- Định dạng kết quả hiển thị.
- Liệt kê và mô tả các đối tượng.
- Nhập/xuất, script, biến và công cụ hỗ trợ.
- Quản lý bộ đệm câu lệnh và điều khiển vòng lặp tương tác.

Đây là **trợ giúp cho chương trình psql**. Nếu muốn biết `\dt` nhận mẫu lọc nào hoặc cách bật chế độ hiển thị mở rộng, hãy bắt đầu với `\?`.

Ở các phiên bản psql mới, hệ thống trợ giúp có thể hỗ trợ các chủ đề bổ sung như `\? commands` hoặc `\? options`. Khả năng đó phụ thuộc phiên bản client; **`\?` đơn giản là điểm bắt đầu tương thích nhất**.

### 3.2. \h — trợ giúp cú pháp SQL

~~~text
\h
~~~

`\h` (*help*) hiển thị danh sách các chủ đề SQL mà psql có tài liệu cú pháp.

Muốn xem một lệnh cụ thể:

~~~text
\h SELECT
\h CREATE TABLE
\h ALTER TABLE
\h CREATE INDEX
\h INSERT
\h UPDATE
\h GRANT
\h VACUUM
~~~

Ví dụ `\h CREATE TABLE` cho một mô tả cú pháp rộng, có thể giúp nhận ra những phần như định nghĩa cột, ràng buộc và tùy chọn bảng.

`\h` không liệt kê cấu trúc bảng đã tạo trong database; nó là **tham chiếu cú pháp SQL** của phiên bản psql đang chạy.

### 3.3. Khi nào dùng \? và khi nào dùng \h?

| Bạn đang hỏi... | Dùng lệnh |
|---|---|
| Cách liệt kê bảng trong psql là gì? | `\?` |
| Cú pháp tạo bảng PostgreSQL? | `\h CREATE TABLE` |
| Có meta-command nào để mô tả một index? | `\?`, sau đó `\d ten_index` |
| Cú pháp `INSERT ... ON CONFLICT`? | `\h INSERT` |
| Làm sao định dạng kết quả theo chiều dọc? | `\?`, xem nhóm format rồi `\x` |
| Có những bảng nào trong schema hiện tại? | `\dt` (không phải `\h`) |

### 3.4. Đừng nhầm help SQL với trạng thái runtime

Cú pháp từ `\h ALTER TABLE` không cho biết một lệnh DDL sẽ mất bao lâu, chờ khóa hay dùng bao nhiêu đĩa. Help giúp viết **đúng cú pháp**; để đánh giá ảnh hưởng runtime cần xem bảng thực tế, quy mô dữ liệu, loại thao tác và phiên bản PostgreSQL.

## 4. Hiểu cây đối tượng PostgreSQL trước khi liệt kê

PostgreSQL tổ chức dữ liệu theo nhiều cấp:

~~~text
PostgreSQL server / cluster
|
+-- Database: appdb
|     |
|     +-- Schema: public
|     |     +-- Table: customers
|     |     +-- Table: orders
|     |     +-- View: recent_orders
|     |
|     +-- Schema: accounting
|           +-- Table: invoices
|           +-- Sequence: invoice_number_seq
|           +-- Function: calculate_tax(...)
|
+-- Database: analyticsdb
      |
      +-- Schema: mart
            +-- Materialized view: daily_revenue
~~~

Cần nhớ:

- `\l` liệt kê **database** trong cluster mà tài khoản được phép nhìn thấy.
- `\dn` liệt kê **schema** trong database hiện tại.
- `\dt` liệt kê **table** theo quy tắc pattern và khả năng nhìn thấy.
- `\dv` liệt kê **view**.
- `\dm` liệt kê **materialized view**.
- `\di` liệt kê **index**.
- `\ds` liệt kê **sequence**.
- `\df` liệt kê **function/procedure** theo tùy chọn và khả năng của phiên bản.

Một database có thể có nhiều schema cùng chứa một tên bảng, ví dụ `public.orders` và `archive.orders`. Vì vậy, khi cần mô tả chính xác, **hãy ghi đầy đủ tên schema.table**.

## 5. Chuẩn bị bài thực hành trong một schema riêng

Để thấy hiệu quả của các lệnh liệt kê, ta tạo vài đối tượng mẫu. Phần này chỉ cần thực hiện **một lần** trong database PostgreSQL thử nghiệm mà bạn có quyền `CREATE` trên database/schema.

Ví dụ hướng tới PostgreSQL hiện đại (PostgreSQL 12+). Nếu đã có schema hoặc đối tượng cùng tên, hãy dùng tên khác thay vì xóa dữ liệu tùy ý.

### 5.1. Tạo schema và bảng

~~~sql
CREATE SCHEMA IF NOT EXISTS psql_lab;

CREATE TABLE psql_lab.customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE psql_lab.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES psql_lab.customers(customer_id),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'paid', 'cancelled')),
    amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_psql_lab_orders_customer_created
ON psql_lab.orders (customer_id, created_at DESC);
~~~

Các thành phần đáng quan sát:

- Hai bảng `customers` và `orders`.
- Cột định danh sinh tự động bằng `IDENTITY`.
- Ràng buộc `PRIMARY KEY`, `UNIQUE`, `CHECK` và `FOREIGN KEY`.
- Một chỉ mục ghép trên `customer_id`, `created_at`.

Đối với PostgreSQL, identity column được hỗ trợ bởi cơ chế sequence. Vì vậy, các lệnh quan sát sequence có thể thấy những đối tượng liên quan đến các cột identity.

### 5.2. Tạo view, materialized view và function

~~~sql
CREATE VIEW psql_lab.v_active_customers AS
SELECT
    customer_id,
    customer_name,
    email
FROM psql_lab.customers
WHERE is_active = TRUE;

CREATE MATERIALIZED VIEW psql_lab.mv_order_totals AS
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(amount) AS total_amount
FROM psql_lab.orders
GROUP BY customer_id;

CREATE FUNCTION psql_lab.normalize_email(p_email TEXT)
RETURNS TEXT
LANGUAGE SQL
IMMUTABLE
STRICT
AS $$
    SELECT lower(btrim(p_email));
$$;
~~~

**View** mô tả một truy vấn được đánh tên; nó không tự lưu toàn bộ kết quả như bảng vật lý. **Materialized view** có lưu kết quả tại thời điểm khởi tạo/làm mới và cần `REFRESH MATERIALIZED VIEW` để cập nhật theo quy tắc. **Function** là đối tượng có thể gọi từ SQL và có chữ ký gồm tên cùng kiểu đối số.

Dù bảng đang rỗng, `\dv`, `\dm` và `\df` vẫn có đối tượng để liệt kê.

### 5.3. Thêm mô tả có chủ đích

~~~sql
COMMENT ON TABLE psql_lab.customers
IS 'Khach hang cua schema thuc hanh psql';

COMMENT ON COLUMN psql_lab.orders.status
IS 'Trang thai nghiep vu cua don hang';
~~~

Các comment giúp tạo tài liệu lược đồ và có thể được psql hiển thị ở chế độ mô tả chi tiết hoặc thông qua lệnh liệt kê comment phù hợp.

**Phạm vi bài thực hành:** những ví dụ trên chỉ tạo đối tượng trong `psql_lab` ở database đang kết nối. Các chương tiếp theo về DDL, transaction, index hoặc PL/pgSQL có thể đi sâu hơn; ở bài này mục tiêu là **đọc cấu trúc đối tượng bằng psql**.

## 6. Liệt kê database: \l và \l+

Trong psql:

~~~text
\l
~~~

Hoặc viết đầy đủ:

~~~text
\list
~~~

Lệnh hiển thị danh sách database và các thuộc tính có thể gồm:

- Tên database.
- Owner.
- Encoding.
- Locale/collation hoặc thông tin môi trường tương ứng.
- Access privileges.

Để xem nhiều thông tin hơn:

~~~text
\l+
~~~

Tùy phiên bản PostgreSQL/psql, dạng chi tiết có thể bao gồm kích thước, tablespace và các cột metadata bổ sung.

Nếu nhiều database cùng xuất hiện, điều đó không có nghĩa bạn đã kết nối vào tất cả; lệnh `\conninfo` mới giúp xác định **database kết nối hiện tại**.

### 6.1. Kiểm tra database bằng SQL

~~~sql
SELECT current_database() AS current_database;

SELECT
    datname,
    datallowconn
FROM pg_catalog.pg_database
ORDER BY datname;
~~~

Lệnh SQL trên giúp thấy metadata database trong catalog. Tùy quyền, môi trường và chính sách, việc nhìn thấy tên database khác với quyền thực sự **CONNECT** tới database đó.

### 6.2. Tránh nhầm \l với \dn

`\l` chỉ cấp **database**. Nếu muốn biết trong `appdb` có những schema nào, trước hết kết nối đúng database, sau đó dùng `\dn`.

## 7. Liệt kê schema: \dn và \dn+

Sau khi kết nối vào database thực hành:

~~~text
\dn
~~~

Lệnh hiển thị các schema nhìn thấy theo quy tắc của psql. Muốn thêm thông tin chủ sở hữu và quyền:

~~~text
\dn+
~~~

Lọc theo tên:

~~~text
\dn psql_lab
\dn psql_*
~~~

Bạn có thể thấy `public`, `psql_lab` hoặc những schema khác đã được tạo trong database.

### 7.1. Schema không giống database

Nếu một database có hai schema `sales` và `hr`, mỗi schema có bảng `employees`, chúng là hai đối tượng khác nhau:

~~~sql
SELECT * FROM sales.employees;
SELECT * FROM hr.employees;
~~~

Ngược lại, bạn không dùng `\dn` để liệt kê schema thuộc **database chưa kết nối** theo cách trực tiếp. Muốn khám phá database khác, cần kết nối vào đó hoặc dùng phương án quản trị riêng.

### 7.2. Liệt kê các schema hệ thống

Thông thường còn có schema phục vụ PostgreSQL như `pg_catalog` và `information_schema`. psql có một số quy tắc mặc định nhằm tránh tràn danh sách với đối tượng hệ thống. Ký hiệu `S` có thể được dùng với nhiều lệnh mô tả/liệt kê để bao gồm đối tượng hệ thống khi cần.

Nếu mục đích chỉ là đọc schema ứng dụng, không nên bắt đầu bằng việc liệt kê mọi bảng hệ thống.

## 8. \dt: liệt kê các bảng

Đây là một trong những lệnh được dùng nhiều nhất:

~~~text
\dt
~~~

Nó hiển thị những bảng theo quy tắc visibility/search path của psql, thường có các cột như:

~~~text
Schema   | Name      | Type  | Owner
---------+-----------+-------+---------
psql_lab | customers | table | ...
psql_lab | orders    | table | ...
~~~

Kết quả ở trên là **minh họa**. Nếu không thấy bảng nào, không nhất thiết database trống; bảng có thể nằm ngoài `search_path`, bạn đang kết nối sai database, hoặc không đủ quyền xem.

### 8.1. Liệt kê bảng trong một schema cụ thể

~~~text
\dt psql_lab.*
~~~

Mẫu `psql_lab.*` bao gồm tên schema trước dấu chấm và wildcard cho tên bảng. Cách này rất hữu ích khi schema không nằm trong `search_path`.

Liệt kê các bảng có tên bắt đầu bằng `order` trong schema đó:

~~~text
\dt psql_lab.order*
~~~

Liệt kê ở nhiều schema với một pattern rộng:

~~~text
\dt *.*
~~~

Lệnh cuối có thể tạo nhiều dòng trong database lớn và tùy quy tắc hiển thị đối tượng hệ thống; chỉ sử dụng khi phạm vi thực sự cần.

### 8.2. Xem bản chi tiết

~~~text
\dt+ psql_lab.*
~~~

Với một số đối tượng, dấu `+` có thể thêm kích thước và mô tả. Dữ liệu và dung lượng được trình bày theo phiên bản psql/server và quyền hiện có.

**`\dt+` không phải phép đo chuyên sâu về bloat, WAL hoặc dung lượng toàn server.** Nó chỉ là công cụ kiểm kê thuận tiện; công việc phân tích lưu trữ lớn cần các thống kê và truy vấn phù hợp.

### 8.3. \dt không liệt kê mọi loại relation

Một **view**, **materialized view**, **sequence** hoặc **index** không nhất thiết được hiển thị khi bạn chỉ dùng `\dt`. PostgreSQL có nhiều loại relation/object; lệnh `\dt` tập trung vào bảng.

Muốn khám phá đầy đủ, dùng nhóm lệnh đúng loại ở phần tiếp theo.

## 9. Các lệnh liệt kê đối tượng thường gặp

| Lệnh | Đối tượng | Ví dụ |
|---|---|---|
| `\dt` | Table | `\dt psql_lab.*` |
| `\dv` | View | `\dv psql_lab.*` |
| `\dm` | Materialized view | `\dm psql_lab.*` |
| `\di` | Index | `\di psql_lab.*` |
| `\ds` | Sequence | `\ds psql_lab.*` |
| `\df` | Function/routine theo chế độ tương ứng | `\df psql_lab.*` |
| `\dT` | Data type do người dùng định nghĩa và kiểu phù hợp | `\dT psql_lab.*` |
| `\dD` | Domain | `\dD psql_lab.*` |
| `\dx` | Extension đã cài trong database | `\dx` |
| `\du` | Role | `\du` |
| `\dp` | Access privileges trên đối tượng | `\dp psql_lab.*` |
| `\ddp` | Default privileges đã thay đổi | `\ddp` |
| `\db` | Tablespace | `\db` |

Một số cách viết dạng `\d...+` sẽ yêu cầu phần thông tin chi tiết hơn. Không phải mọi lệnh đều có đầy đủ loại metadata giống nhau; nội dung trả về phụ thuộc loại đối tượng và phiên bản.

### 9.1. View: \dv và \dv+

~~~text
\dv psql_lab.*
\dv+ psql_lab.*
~~~

Các lệnh này liệt kê view trong schema thực hành. Nếu muốn xem cột và câu truy vấn định nghĩa của một view cụ thể, hãy dùng `\d` hoặc `\d+` với tên view:

~~~text
\d psql_lab.v_active_customers
\d+ psql_lab.v_active_customers
~~~

View thông thường là một câu truy vấn được định nghĩa trong catalog. Nó không tự chứa bản sao đầy đủ của dữ liệu nguồn.

### 9.2. Materialized view: \dm

~~~text
\dm psql_lab.*
\dm+ psql_lab.*
~~~

Bạn có thể tìm thấy `mv_order_totals`. Đây là loại đối tượng khác với view thường: nó lưu kết quả và phải được làm mới khi cần.

Việc có một materialized view không bảo đảm dữ liệu bên trong được cập nhật tức thì khi bảng nguồn đổi. Lệnh `\dm` cho bạn biết đối tượng tồn tại, **không chứng minh dữ liệu trong đó đang mới**.

### 9.3. Index: \di

~~~text
\di psql_lab.*
\di+ psql_lab.*
~~~

Danh sách index có thể bao gồm cả index được tạo để hỗ trợ primary key/unique constraint và index do người quản trị tạo thủ công.

Muốn biết **index được tạo trên bảng nào, gồm những cột nào, dùng phương thức gì và có phải unique không**, hãy mô tả index cụ thể hoặc dùng catalog:

~~~text
\d psql_lab.idx_psql_lab_orders_customer_created
~~~

Không nên xem chỉ có tên index là đủ để quyết định xóa index: cần hiểu truy vấn, ràng buộc phụ thuộc, write overhead và kế hoạch thực thi thực tế.

### 9.4. Sequence: \ds

~~~text
\ds psql_lab.*
~~~

Những cột `GENERATED ... AS IDENTITY` thường liên quan đến sequence được PostgreSQL tạo và quản lý. Có thể có cả sequence được tạo bằng `CREATE SEQUENCE` độc lập.

Một sequence có thể có quyền và trạng thái riêng; đừng sửa `setval()` hay `nextval()` chỉ để "kiểm tra metadata" nếu không muốn tác động tới giá trị được cấp sau này.

### 9.5. Function và procedure: \df

~~~text
\df psql_lab.*
\df+ psql_lab.*
~~~

Lệnh `\df` hiển thị routine phù hợp, các thông tin như tên, kiểu đối số và kết quả trả về theo cách của phiên bản psql. PostgreSQL hỗ trợ **function overloading**, nghĩa là nhiều function có thể cùng tên nhưng khác kiểu đối số.

Ví dụ, các function:

~~~text
calculate_total(integer)
calculate_total(numeric)
~~~

là những chữ ký khác nhau. Khi xem chi tiết hoặc viết script, có thể cần chỉ rõ **chữ ký** chứ không chỉ tên function.

Với một function cụ thể:

~~~text
\df+ psql_lab.normalize_email
~~~

Muốn xem phần thân function khi có quyền, có thể dùng lệnh psql:

~~~text
\sf psql_lab.normalize_email(text)
~~~

`\sf` hiển thị định nghĩa function thay vì thực thi nó. Quyền xem định nghĩa và khả năng hiển thị có thể khác nhau theo phiên bản và quyền người dùng.

### 9.6. Các lệnh mở rộng

~~~text
\dT
\dD
\dx
\du
\db
~~~

Những lệnh này giúp phát hiện user-defined types, domains, extensions, roles và tablespaces. Không phải hệ thống nào cũng có tất cả loại đối tượng tùy biến; một danh sách rỗng có thể là kết quả đúng.

Các lệnh liệt kê role/tablespace chủ yếu phục vụ kiểm kê và phân quyền; bản thân chúng không cấp thêm quyền hay thay đổi cấu trúc.

## 10. \d: mô tả cấu trúc một đối tượng

Đối với một bảng đã biết, lệnh quan trọng nhất là:

~~~text
\d psql_lab.orders
~~~

Nó cho bạn một bảng mô tả cột, kiểu dữ liệu, nullable/default, cùng những thông tin như:

- Primary key.
- Index của bảng.
- Ràng buộc check.
- Foreign key đi ra.
- Những bảng tham chiếu tới bảng hiện tại, khi phù hợp.
- Trigger và các thuộc tính liên quan, tùy đối tượng.

Kết quả minh họa (rút gọn, không cố tái hiện chính xác định dạng của một phiên bản):

~~~text
Table "psql_lab.orders"
Column       | Type                     | Nullable | Default
-------------+--------------------------+----------+---------
order_id     | bigint                   | not null | identity
customer_id  | bigint                   | not null |
status       | text                     | not null | 'pending'
amount       | numeric(12,2)            | not null |
created_at   | timestamp with time zone | not null | CURRENT_TIMESTAMP

Indexes:
    orders_pkey PRIMARY KEY (order_id)
    idx_psql_lab_orders_customer_created (customer_id, created_at DESC)

Check constraints:
    status IN (...)
    amount >= 0

Foreign-key constraints:
    customer_id REFERENCES psql_lab.customers(customer_id)
~~~

Bản xuất thực tế có thể thể hiện cú pháp index/constraint chi tiết hơn, tên constraint được PostgreSQL tự tạo và các phần khác.

### 10.1. \d không chỉ dùng cho table

Thử:

~~~text
\d psql_lab.customers
\d psql_lab.v_active_customers
\d psql_lab.mv_order_totals
\d psql_lab.idx_psql_lab_orders_customer_created
~~~

psql chọn kiểu mô tả dựa trên loại đối tượng được tìm thấy. Với view, nó có thể hiển thị danh sách cột và view definition. Với index, nó có thể hiển thị biểu thức khóa/index và bảng liên quan.

### 10.2. Khi chưa biết tên đối tượng

Nhập:

~~~text
\d
~~~

Không kèm tên, `\d` có thể liệt kê nhóm relation theo ngữ cảnh hiển thị thay vì mô tả một bảng cụ thể. Khi đã tìm được tên, dùng `\d schema.object` để xem chi tiết.

Trong môi trường lớn, cần thu hẹp bằng schema và mẫu tên để tránh hàng trăm dòng không liên quan.

## 11. \d+ khác \d thế nào?

Dấu cộng `+` ở nhiều meta-command psql yêu cầu thông tin chi tiết hơn:

~~~text
\d+ psql_lab.orders
~~~

Thông tin mở rộng có thể bao gồm:

- Phương thức truy cập bảng/index (tùy phiên bản).
- Kiểu lưu trữ cột, compression/column statistics khi phù hợp.
- Kích thước relation/tablespace.
- Comment trên bảng và cột.
- Các thuộc tính riêng của loại đối tượng.

Khi xem bảng có cột lớn như `TEXT`, `JSONB` hoặc thay đổi storage settings, `\d+` rất hữu ích để có bức tranh rộng hơn `\d` cơ bản.

### 11.1. \d+ không thay thế lệnh tạo DDL đầy đủ

PostgreSQL không có một câu lệnh SQL chuẩn `SHOW CREATE TABLE` tương đương nguyên vẹn với mọi hệ quản trị khác.

`\d+` hiển thị **mô tả cấu trúc cho người đọc**, không phải cam kết có một script `CREATE TABLE` hoàn chỉnh để replay.

Nếu cần xuất DDL thực tế, có thể dùng công cụ dòng lệnh `pg_dump` với phạm vi schema-only thích hợp. Ví dụ từ terminal:

~~~bash
pg_dump --schema-only --table=psql_lab.orders --dbname=appdb
~~~

`pg_dump` là **chương trình khác**, không phải meta-command `\d` hoặc câu SQL gửi tới server. DDL xuất ra còn cần xem phạm vi dependency/đối tượng phụ thuộc và sự phù hợp với môi trường đích trước khi dùng để triển khai.

## 12. Dùng pattern để tìm đúng đối tượng

Phần lớn meta-command liệt kê/mô tả trong psql chấp nhận **pattern** để lọc.

Một số mẫu thường gặp:

| Pattern | Ví dụ | Ý nghĩa |
|---|---|---|
| Tên chính xác | `\d psql_lab.orders` | Mô tả bảng cụ thể |
| Dấu `*` | `\dt psql_lab.order*` | Tên bắt đầu bằng `order` trong schema |
| Dấu `?` | `\dt psql_lab.ord?rs` | Một ký tự ở vị trí dấu hỏi |
| Schema và mọi tên | `\dv psql_lab.*` | View trong schema |
| Pattern không kèm schema | `\dt *order*` | Tìm theo phạm vi hiển thị mặc định |
| Schema wildcard | `\dt *.*` | Quét theo pattern rộng trên nhiều schema |

**Cú pháp pattern của psql không hoàn toàn giống cú pháp `LIKE` trong SQL.** Trong meta-command, dấu `*` thường là wildcard cho chuỗi ký tự, còn trong SQL:

~~~sql
SELECT *
FROM pg_catalog.pg_tables
WHERE tablename LIKE 'order%';
~~~

mẫu `LIKE` sử dụng `%` và `_`, không phải `*` và `?`.

### 12.1. Tên có chữ hoa và dấu nháy

PostgreSQL chuyển các identifier không được trích dẫn thành chữ thường theo quy tắc parser SQL. Nếu bạn đã tạo đối tượng có tên phân biệt chữ hoa, ví dụ:

~~~sql
CREATE TABLE psql_lab."SalesOrder" (
    id BIGINT PRIMARY KEY
);
~~~

thì cần chú ý cách ghi pattern/identifier trong psql:

~~~text
\d psql_lab."SalesOrder"
~~~

Đừng gõ `\d psql_lab.salesorder` rồi mặc định đó là cùng một đối tượng. Với những tên có khoảng trắng hoặc ký tự đặc biệt, cần áp dụng cú pháp quote phù hợp của psql/identifier PostgreSQL.

Khi thiết kế schema mới, nhiều nhóm chọn quy ước **snake_case chữ thường** để tránh phải trích dẫn identifier liên tục.

### 12.2. Đừng dùng tên không kèm schema khi có trùng lặp

Ví dụ:

~~~text
\d orders
~~~

có thể mô tả một bảng trong `search_path` hiện hành, hoặc không tìm thấy đối tượng như bạn mong muốn. Trong khi:

~~~text
\d psql_lab.orders
~~~

chỉ rõ đúng bảng thuộc schema thực hành.

Khi viết tài liệu và xử lý sự cố production, tên đầy đủ **schema.object** đáng tin cậy hơn.

## 13. search_path quyết định danh sách mặc định

Trong PostgreSQL, `search_path` là danh sách schema được tìm kiếm khi bạn dùng tên đối tượng không kèm schema.

Xem cấu hình:

~~~sql
SHOW search_path;

SELECT current_schema();

SELECT current_schemas(TRUE);
~~~

Ví dụ một session có:

~~~text
"$user", public
~~~

Nếu schema `psql_lab` không nằm trong phạm vi tìm kiếm, `\dt` có thể không hiện hai bảng vừa tạo. Nhưng:

~~~text
\dt psql_lab.*
~~~

vẫn chỉ rõ schema để tìm.

### 13.1. Đổi search_path trong session thử nghiệm

~~~sql
SET search_path TO psql_lab, public;
~~~

Sau đó:

~~~text
\dt
\d orders
~~~

có thể hiển thị các bảng ở `psql_lab` thông qua tên không kèm schema.

Bạn có thể trả lại cấu hình session theo quy định môi trường, ví dụ:

~~~sql
RESET search_path;
~~~

**Không coi `SET search_path` là thao tác không có ảnh hưởng bảo mật.** Trong routine chạy với quyền cao hoặc hệ thống có schema do bên không tin cậy được phép tạo đối tượng, cách phân giải tên hàm/bảng theo search path có thể gây rủi ro. Khi phát triển ứng dụng, nên dùng schema qualification và chính sách search path rõ ràng.

### 13.2. Trường hợp “Did not find any relations”

Nếu chạy:

~~~text
\dt
~~~

và psql báo không tìm thấy relation, hãy thử:

~~~text
\conninfo
\dn
\dt psql_lab.*
~~~

Nếu lệnh có schema rõ ràng tìm thấy bảng, nguyên nhân có thể là **search_path**, không phải bảng biến mất.

Nếu vẫn không tìm thấy, kiểm tra database, quyền người dùng, tên đối tượng và chữ hoa/chữ thường trước khi đưa ra kết luận.

## 14. Liệt kê và đọc quyền bằng \du, \dp, \ddp

Khi khảo sát một hệ thống lạ, cấu trúc đối tượng chỉ là một phần. Cần biết ai được phép đọc/ghi.

### 14.1. \du — liệt kê roles

~~~text
\du
\du+
~~~

Thông tin có thể gồm role name, các thuộc tính như `LOGIN`, `CREATEDB`, `CREATEROLE`, và membership tùy phiên bản.

PostgreSQL dùng **role** cho cả tài khoản đăng nhập và nhóm quyền. Một role không có quyền `LOGIN` vẫn có thể được cấp quyền cho các role khác.

`\du` là lệnh **quan sát**, không cho biết đầy đủ mọi quyền đối tượng có hiệu lực ở các tầng thừa kế, ownership và default privilege. Để điều tra sâu, cần xem thêm lệnh grant và các catalog quyền liên quan.

### 14.2. \dp — liệt kê access privileges

~~~text
\dp psql_lab.*
~~~

`\dp` (cũng có alias `\z` trong psql) hiển thị thông tin đặc quyền của những relation phù hợp như bảng/view/sequence, theo cách PostgreSQL biểu diễn ACL.

Các mã quyền trong output psql có thể khá ngắn, chẳng hạn:

~~~text
r  SELECT
a  INSERT
w  UPDATE
d  DELETE
D  TRUNCATE
x  REFERENCES
t  TRIGGER
~~~

Đây là ví dụ cho một số ký hiệu thường gặp; không nên dùng bảng rút gọn này như một bảng đặc quyền đầy đủ cho mọi loại đối tượng. Với function, schema, database hoặc sequence, cách phân loại và ký hiệu có khác biệt.

Nếu cần kiểm tra một quyền cụ thể trong SQL, có thể dùng các hàm như `has_table_privilege()` với đúng tên đối tượng và ngữ cảnh thích hợp.

### 14.3. \ddp — default privileges

~~~text
\ddp
~~~

Lệnh hiển thị các **default privileges đã được thay đổi** so với mặc định thích hợp. Những quyền mặc định ảnh hưởng đến **đối tượng được tạo trong tương lai** trong phạm vi khai báo, không tự đổi mọi bảng hiện có.

Phân biệt rõ:

- `\dp`: quyền hiện tại trên đối tượng.
- `\ddp`: cấu hình default privileges cho đối tượng tạo sau này.

Nếu output quyền trống ở một cột, không được tự suy ra rằng “mọi người có quyền” hoặc “không ai có quyền”. Ownership, quyền mặc định và role membership cần được đọc theo chính sách PostgreSQL.

### 14.4. Kiểm tra role đang dùng

~~~sql
SELECT
    current_user,
    session_user,
    current_database();
~~~

Một session có thể đổi role theo quyền được cấp. Vì vậy, một lệnh metadata chạy trong session khác có thể hiện kết quả khác; hãy luôn xác định **ngữ cảnh đang kết nối**.

## 15. Comment đối tượng: \dd và phần mô tả mở rộng

Nếu dự án sử dụng `COMMENT ON TABLE` hoặc `COMMENT ON COLUMN`, tài liệu ngắn được lưu cùng metadata.

Ví dụ đã khai báo:

~~~sql
COMMENT ON TABLE psql_lab.customers
IS 'Khach hang cua schema thuc hanh psql';
~~~

Có thể xem mô tả đối tượng bằng những meta-command phù hợp:

~~~text
\dd psql_lab.*
\d+ psql_lab.customers
\d+ psql_lab.orders
~~~

`\dd` liệt kê những mô tả/comment có thể nhìn thấy theo pattern. `\d+` thường hiển thị thông tin cột và thuộc tính mở rộng, trong đó có comment khi có.

Việc ghi `COMMENT` không thay thế tài liệu nghiệp vụ chi tiết hoặc quy trình migration, nhưng nó giúp những người dùng psql hiểu mục đích cơ bản của một bảng/cột ngay trong công cụ.

## 16. Một số lệnh quan sát cấu trúc khác đáng biết

### 16.1. Partitioned table và index

Ở những phiên bản psql hiện đại, các lệnh như:

~~~text
\dP
~~~

có thể dùng để liệt kê các đối tượng partitioned theo nhóm loại phù hợp và những tùy chọn được hỗ trợ. Khi điều tra một bảng lớn có phân vùng, mô tả parent table và các partition là hai câu hỏi khác nhau.

Không mặc định một partitioned table có kiểu lưu trữ giống một table thường hoặc rằng chỉ xem một partition là đã đủ hiểu toàn bộ cây phân vùng.

### 16.2. Extension

~~~text
\dx
\dx+
~~~

Các extension như `pg_trgm`, `uuid-ossp` hoặc PostGIS (nếu được cài) có thể tạo thêm function, type, operator và index operator class. Liệt kê extension giúp biết vì sao trong database có những khả năng không thuộc bộ tính năng cơ bản của một phiên bản PostgreSQL.

Một extension **không xuất hiện** trong `\dx` không chứng minh package của extension không được cài trên server; có thể extension chưa được `CREATE EXTENSION` trong database hiện tại hoặc quyền quan sát có giới hạn.

### 16.3. Enum, domain và user-defined type

~~~text
\dT psql_lab.*
\dD psql_lab.*
~~~

Những lệnh này hữu ích khi bảng có kiểu dữ liệu tùy biến và `\d table` hiển thị một kiểu mà bạn chưa nhận ra. Domain có thể mang constraint/default riêng; enum có tập giá trị cụ thể.

### 16.4. Tablespace

~~~text
\db
\db+
~~~

Lệnh cho biết các tablespace nhìn thấy và có thể cung cấp thêm metadata ở chế độ chi tiết. Đây là phần nâng cao khi theo dõi vị trí lưu trữ, không phải cách thay đổi file dữ liệu trực tiếp từ terminal.

## 17. Định dạng kết quả để danh sách dài dễ đọc

Không ít lần các lệnh `\d+`, `\l+` hay truy vấn catalog trả rất nhiều cột, khiến terminal bị tràn chiều ngang. psql có những meta-command để điều chỉnh cách hiển thị.

### 17.1. \x — expanded output

~~~text
\x on
~~~

Khi bật, mỗi hàng kết quả có thể được hiển thị theo chiều dọc, thuận tiện với hàng nhiều cột:

~~~text
-[ RECORD 1 ]------+------------------
table_name         | orders
column_name        | created_at
data_type          | timestamp with time zone
~~~

Tắt:

~~~text
\x off
~~~

Hoặc để psql tự quyết định ở những tình huống phù hợp:

~~~text
\x auto
~~~

### 17.2. \pset — thay đổi một số tùy chọn hiển thị

~~~text
\pset pager off
\pset border 2
\pset null '(NULL)'
~~~

Những tùy chọn này giúp kiểm soát pager, đường viền bảng kết quả và cách hiển thị SQL `NULL`.

Khi làm việc tương tác, pager có thể thuận tiện để cuộn kết quả. Khi chạy script thu thập output, bạn có thể muốn tắt pager để tránh làm gián đoạn luồng xuất dữ liệu.

### 17.3. \timing — đo thời gian thực thi

~~~text
\timing on
~~~

Sau đó, các lệnh được thực thi có thể có thông tin thời gian hiển thị. Muốn tắt:

~~~text
\timing off
~~~

`\timing` là một công cụ tiện lợi để cảm nhận thời gian từ phía client, **không thay thế** `EXPLAIN (ANALYZE, BUFFERS)`, statistics server hoặc đo p95/p99 trong ứng dụng. Kết quả chịu ảnh hưởng của kết nối, cách hiển thị output, cache và tải máy.

### 17.4. \watch — xem lại một truy vấn theo chu kỳ

Với những truy vấn quan sát **chỉ đọc**, psql có thể thực thi lại chúng định kỳ:

~~~sql
SELECT count(*) AS active_sessions
FROM pg_stat_activity
WHERE state = 'active';
~~~

Sau đó, dùng `\watch 5` theo cách sử dụng bộ đệm/lệnh cuối của phiên bản psql để xem lại mỗi 5 giây.

Không dùng `\watch` với `UPDATE`, `DELETE` hoặc các câu có tác động nếu không có chủ đích rất rõ, bởi nó có thể lặp lại thao tác ghi nhiều lần. Một truy vấn catalog quá nặng chạy lặp cũng có thể tạo tải không cần thiết.

## 18. Từ psql sang SQL metadata: khi nào cần truy vấn pg_catalog?

Meta-command rất nhanh cho người thao tác, nhưng đôi khi cần kết quả có thể lọc/join và dùng trong ứng dụng. PostgreSQL cung cấp các catalog và view như:

- `pg_catalog.pg_namespace`: namespace/schema.
- `pg_catalog.pg_class`: relation như table, index, view...
- `pg_catalog.pg_attribute`: mô tả thuộc tính/cột ở cấp hệ thống.
- `pg_catalog.pg_constraint`: constraint.
- `pg_catalog.pg_index`: thông tin index.
- `information_schema.tables` và `information_schema.columns`: các view metadata theo mô hình SQL.
- `pg_catalog.pg_indexes`: view thuận tiện về index.

### 18.1. Thay \dt bằng SQL

~~~sql
SELECT
    schemaname,
    tablename,
    tableowner
FROM pg_catalog.pg_tables
WHERE schemaname = 'psql_lab'
ORDER BY tablename;
~~~

### 18.2. Đọc danh sách cột

~~~sql
SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'psql_lab'
  AND table_name = 'orders'
ORDER BY ordinal_position;
~~~

Câu SQL này có thể dùng trong JDBC hoặc ứng dụng kiểm kê, nhưng không nhất thiết mô tả **tất cả thuộc tính PostgreSQL-specific** mà `\d+` hoặc catalog nội bộ cung cấp.

### 18.3. Liệt kê index bằng SQL

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_catalog.pg_indexes
WHERE schemaname = 'psql_lab'
ORDER BY tablename, indexname;
~~~

`indexdef` hữu ích để xem cách PostgreSQL mô tả định nghĩa index theo metadata.

### 18.4. Xem định nghĩa view và function

~~~sql
SELECT pg_get_viewdef(
    'psql_lab.v_active_customers'::regclass,
    TRUE
) AS view_sql;

SELECT pg_get_functiondef(
    'psql_lab.normalize_email(text)'::regprocedure
) AS function_sql;
~~~

Những cách này hữu ích khi cần một biểu diễn SQL của định nghĩa object. Tuy nhiên, việc đọc metadata và khả năng truy cập nội dung có thể phụ thuộc quyền, tên đối tượng và kiểu/chữ ký phù hợp. `pg_get_viewdef` là cách lấy câu truy vấn của view, không phải script hoàn chỉnh gồm đầy đủ quyền và comment.

### 18.5. Không thay thế psql bằng một câu truy vấn catalog khổng lồ

Truy vấn trực tiếp `pg_catalog` rất linh hoạt nhưng nhiều quan hệ chứa mã nội bộ, OID, phụ thuộc và cấu trúc không tiện đọc nếu chưa hiểu. Cho nhu cầu khám phá nhanh, `\dt` và `\d+` thường dễ hơn. Chỉ chuyển sang SQL metadata khi cần tự động hóa, kiểm kê quy mô lớn hoặc tùy biến báo cáo.

## 19. Tình huống thực tế: kiểm tra cấu trúc trước khi sửa một bảng

Giả sử bạn được giao thêm một cột `shipping_address` cho bảng đơn hàng. Trước khi chạy `ALTER TABLE`, hãy khảo sát.

### Bước 1 — Xác nhận kết nối

~~~text
\conninfo
~~~

Phải biết rõ đang ở development, staging hay production; không dựa duy nhất vào tên prompt.

### Bước 2 — Tìm schema và bảng

~~~text
\dn
\dt psql_lab.*
~~~

Nếu không thấy bảng, kiểm tra database và quyền trước khi làm tiếp.

### Bước 3 — Đọc cấu trúc hiện tại

~~~text
\d psql_lab.orders
\d+ psql_lab.orders
~~~

Xác định các cột đang có, default, nullable, primary key, foreign key và index.

### Bước 4 — Đọc mối liên hệ

Ví dụ `orders.customer_id` tham chiếu `customers.customer_id`. Khi thay kiểu cột khóa hoặc xóa bảng, cần kiểm tra những ràng buộc tham chiếu đi vào/đi ra, không chỉ kiểu cột.

### Bước 5 — Xem kích thước và ảnh hưởng

Một bảng 10 hàng và một bảng hàng trăm triệu hàng có chi phí DDL khác nhau. `\d+` có thể giúp định hướng, nhưng cần thêm thống kê và kế hoạch vận hành nếu thay đổi nặng.

### Bước 6 — Xem trợ giúp cú pháp

~~~text
\h ALTER TABLE
~~~

Đọc cú pháp đúng của PostgreSQL đang dùng; không sao chép nguyên câu DDL của hệ quản trị khác.

### Bước 7 — Viết migration riêng và kiểm soát triển khai

Ví dụ về mặt cú pháp:

~~~sql
ALTER TABLE psql_lab.orders
ADD COLUMN shipping_address TEXT;
~~~

Không chạy thay đổi này chỉ vì đã đọc metadata. Cần xác nhận yêu cầu dữ liệu, backward compatibility, thời điểm triển khai, quyền và khả năng rollback trước khi sửa production.

## 20. Một lộ trình 10 phút khám phá database chưa biết

Nếu lần đầu được cấp quyền vào một PostgreSQL database, có thể theo thứ tự dưới đây:

| Bước | Lệnh | Câu hỏi được trả lời |
|---:|---|---|
| 1 | `\conninfo` | Tôi đang ở server/database nào? |
| 2 | `\?` | psql có những meta-command nào? |
| 3 | `\h SELECT` | Cú pháp SQL cơ bản có thể tra ở đâu? |
| 4 | `\l` | Cluster có những database nào? |
| 5 | `\dn` | Database này có những schema nào? |
| 6 | `SHOW search_path;` | Vì sao một tên bảng không kèm schema lại trỏ vào nơi này? |
| 7 | `\dt schema_name.*` | Schema mục tiêu có những bảng nào? |
| 8 | `\dv schema_name.*` | Có những view nào? |
| 9 | `\d schema_name.table_name` | Cột và ràng buộc của một bảng là gì? |
| 10 | `\d+ schema_name.table_name` | Còn thuộc tính chi tiết, comment hoặc kích thước nào? |

Sau đó, tùy công việc mà tiếp tục với `\di`, `\ds`, `\df`, `\du` hoặc `\dp`.

Lộ trình này cố ý bắt đầu bằng các thao tác **đọc**, giúp hạn chế rủi ro làm thay đổi dữ liệu khi chỉ đang khám phá.

## 21. Những lỗi và hiểu lầm phổ biến

### 21.1. “\dt không thấy bảng nào, chắc database rỗng”

Không nhất thiết. Có thể bạn đang kết nối sai database, schema nằm ngoài `search_path`, role thiếu quyền hoặc pattern không khớp. Hãy thử `\conninfo`, `\dn` và `\dt ten_schema.*`.

### 21.2. “Tôi chạy \d trong SQL editor nhưng báo syntax error”

`\d` là meta-command của **psql**, không phải SQL server. Nếu editor không triển khai cú pháp psql, hãy dùng truy vấn `information_schema` hoặc `pg_catalog` tương ứng.

### 21.3. “\l liệt kê schema”

Sai. `\l` liệt kê **database**. `\dn` liệt kê **schema** trong database hiện tại.

### 21.4. “\dt sẽ hiển thị cả view và materialized view”

Không nên giả định vậy. Dùng các lệnh đúng loại: `\dv` cho view và `\dm` cho materialized view.

### 21.5. “\d và \d+ là hai lệnh hoàn toàn không liên quan”

Thực tế, dấu `+` thường yêu cầu **chi tiết bổ sung** của cùng loại đối tượng. `\d+ schema.table` là cách mở rộng từ `\d schema.table`.

### 21.6. “Tên bảng không phân biệt chữ hoa trong mọi trường hợp”

Identifier không trích dẫn trong PostgreSQL thường được gập thành chữ thường. Tên được tạo bằng dấu nháy kép có thể phân biệt chữ hoa, nên cần viết đúng pattern/identifier khi mô tả.

### 21.7. “Meta-command có thể có dấu chấm phẩy giống SQL”

Thông thường không. Meta-command được psql kết thúc theo dòng nhập. Gõ `\dt;` có thể được hiểu khác với `\dt` và gây khó tìm nguyên nhân.

### 21.8. “\d+ xuất ra câu CREATE TABLE hoàn chỉnh”

Không. `\d+` tạo bản mô tả cho người đọc. Muốn xuất DDL có thể dùng `pg_dump --schema-only` với phạm vi được xác định đúng.

### 21.9. “\di không thấy index nên bảng không có ràng buộc unique”

Cần kiểm tra schema/pattern và mô tả bảng. PostgreSQL có thể tạo index phục vụ primary key/unique constraint; việc tên index không xuất hiện theo pattern mặc định không chứng minh không tồn tại.

### 21.10. “\du cho tôi mọi quyền của mọi tài khoản”

`\du` chủ yếu cho biết role và thuộc tính/membership. Đặc quyền cụ thể trên relation và default privilege cần được khảo sát bằng `\dp`, `\ddp`, catalog quyền và ngữ cảnh role có hiệu lực.

### 21.11. “\timing là benchmark cuối cùng của query”

Không. Nó là chỉ số từ phía psql, có thể chịu ảnh hưởng mạng, client và output. Đánh giá query thực tế cần `EXPLAIN`, metrics server và đo tải đại diện.

### 21.12. “Cứ dùng wildcard *.* trên production cho chắc”

Wildcard rộng có thể tạo kết quả rất lớn và gây chi phí/khó quan sát. Dùng pattern theo schema hoặc nhóm đối tượng bạn đang khảo sát sẽ dễ kiểm soát hơn.

## 22. Bài tập thực hành

### Bài 1 — Trợ giúp psql hay SQL?

Bạn quên cách liệt kê index và cũng quên cú pháp tạo index. Hãy chọn lệnh trợ giúp cho từng vấn đề.

**Gợi ý:** `\?` để tìm meta-command `\di`; `\h CREATE INDEX` để xem cú pháp SQL.

### Bài 2 — Database và schema

Bạn kết nối vào database `appdb`, trong đó có schema `public` và `psql_lab`. Lệnh nào liệt kê database, lệnh nào liệt kê schema?

**Đáp án gợi ý:**

~~~text
\l
\dn
~~~

### Bài 3 — Bảng không nằm trong search_path

Bạn đã tạo `psql_lab.orders` nhưng `\dt` trả không có relation. Làm thế nào kiểm tra mà không cần đổi cấu hình session?

**Gợi ý:**

~~~text
\conninfo
\dn
\dt psql_lab.*
\d psql_lab.orders
~~~

### Bài 4 — Tìm đối tượng theo loại

Viết meta-command để liệt kê các đối tượng sau trong `psql_lab`: bảng, view, materialized view, index, sequence.

**Đáp án gợi ý:**

~~~text
\dt psql_lab.*
\dv psql_lab.*
\dm psql_lab.*
\di psql_lab.*
\ds psql_lab.*
~~~

### Bài 5 — Mô tả cấu trúc đơn hàng

Bạn muốn biết `orders.customer_id` tham chiếu bảng nào, cột `amount` có kiểu gì và bảng có index nào. Hãy chọn lệnh phù hợp.

**Gợi ý:**

~~~text
\d psql_lab.orders
\d+ psql_lab.orders
~~~

### Bài 6 — Phân biệt tên quoted identifier

Bảng `"SalesOrder"` được tạo trong schema `psql_lab`. Vì sao `\d psql_lab.salesorder` có thể không tìm thấy? Hãy viết cách mô tả đúng.

**Gợi ý:**

~~~text
\d psql_lab."SalesOrder"
~~~

### Bài 7 — Xem function

Bạn thấy `psql_lab.normalize_email(text)` và muốn biết chữ ký, phần thân function nhưng không muốn thực thi nó. Chọn lệnh nào?

**Gợi ý:**

~~~text
\df+ psql_lab.normalize_email
\sf psql_lab.normalize_email(text)
~~~

### Bài 8 — Kiểm tra quyền

Ứng dụng chạy được `SELECT` trên một view nhưng không xem được bảng nguồn. Bạn muốn quan sát role và quyền trên đối tượng. Dùng những lệnh psql nào?

**Gợi ý:**

~~~text
\du
\dp psql_lab.*
~~~

Cần xem thêm ngữ cảnh hiện tại, ownership, grant và chính sách bảo mật của view trước khi kết luận.

### Bài 9 — Nhận biết trợ giúp khác DDL

Bạn muốn biết cú pháp `ALTER TABLE` trước khi sửa một bảng lớn. `\d+` có đủ không?

**Gợi ý:** Không. `\d+` cho cấu trúc hiện tại; `\h ALTER TABLE` cho cú pháp. Việc đánh giá khóa, thời gian và dung lượng vẫn cần bước vận hành khác.

### Bài 10 — Chuyển lệnh psql thành SQL

Một chương trình Java cần liệt kê các cột của `psql_lab.orders`. Có thể gửi nguyên văn `\d psql_lab.orders` qua JDBC không?

**Gợi ý:** Không. Sử dụng `information_schema.columns`, `pg_catalog` hoặc JDBC `DatabaseMetaData`.

### Bài 11 — Nhận diện nguy cơ dùng \watch

Một người dùng chạy `UPDATE ...` rồi gọi `\watch 1`. Tại sao hành động này có thể nguy hiểm?

**Gợi ý:** Nếu lệnh được lặp lại, thao tác ghi có thể xảy ra nhiều lần. Chỉ dùng cơ chế giám sát lặp với những truy vấn **thực sự chỉ đọc** và có chi phí được kiểm soát.

### Bài 12 — Xây bản đồ một schema

Từ database thử nghiệm, hãy tìm: mọi bảng, tất cả index, các view, sequence và function trong schema `psql_lab`. Sau đó mô tả bảng `orders` và ghi lại tên các foreign key.

**Gợi ý:** Kết hợp `\dt`, `\di`, `\dv`, `\ds`, `\df` với `\d+ psql_lab.orders`. Kết quả là một bản kiểm kê các đối tượng thực tế.

## 23. Bảng tra nhanh khi dùng psql

| Muốn làm gì? | Lệnh |
|---|---|
| Xem trợ giúp psql | `\?` |
| Xem trợ giúp cú pháp SQL | `\h`, `\h CREATE TABLE` |
| Xem thông tin kết nối | `\conninfo` |
| Liệt kê database | `\l`, `\l+` |
| Chuyển database | `\c ten_database` |
| Liệt kê schema | `\dn`, `\dn+` |
| Liệt kê bảng | `\dt`, `\dt schema.*` |
| Liệt kê view | `\dv schema.*` |
| Liệt kê materialized view | `\dm schema.*` |
| Liệt kê index | `\di schema.*` |
| Liệt kê sequence | `\ds schema.*` |
| Liệt kê function/routine | `\df schema.*` |
| Xem mã function | `\sf schema.function(type)` |
| Mô tả bảng | `\d schema.table` |
| Mô tả chi tiết bảng | `\d+ schema.table` |
| Liệt kê role | `\du` |
| Xem quyền trên đối tượng | `\dp schema.*` |
| Xem default privileges | `\ddp` |
| Xem comment/description | `\dd schema.*` |
| Liệt kê extension | `\dx` |
| Liệt kê data type/domain | `\dT`, `\dD` |
| Xem search path | `SHOW search_path;` |
| Hiển thị kết quả theo chiều dọc | `\x on`, `\x auto` |
| Tắt pager | `\pset pager off` |
| Bật thời gian thực thi | `\timing on` |
| Thoát psql | `\q` |

---

## Kết luận

`psql` không chỉ là nơi nhập câu `SELECT`. Hệ thống meta-command của nó giúp người học và người vận hành **khám phá PostgreSQL một cách có phương pháp**: `\?` trợ giúp các lệnh của client, `\h` tra cứu cú pháp SQL, `\l` và `\dn` xác định database/schema, các lệnh `\dt`, `\dv`, `\di`, `\ds`, `\df` liệt kê đối tượng, còn `\d` và `\d+` cho biết cấu trúc cụ thể.

Khi làm việc trên một database chưa quen, hãy luôn xác nhận **đúng kết nối, đúng schema, đúng tên đối tượng và đúng quyền**. Đừng nhầm meta-command với SQL, đừng kết luận bảng bị xóa chỉ vì `\dt` không nhìn thấy, và đừng xem bản mô tả `\d+` là một script migration đầy đủ. Những thói quen này giúp bạn kiểm kê cấu trúc nhanh, hiểu quan hệ giữa các đối tượng và chuẩn bị an toàn trước mọi thay đổi lược đồ.
