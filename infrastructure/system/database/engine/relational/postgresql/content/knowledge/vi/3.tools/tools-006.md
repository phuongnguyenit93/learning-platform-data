# Sử dụng pgAdmin hoặc công cụ SQL để khám phá dữ liệu trong PostgreSQL

## 1. Khám phá dữ liệu là bước đầu tiên trước khi viết ứng dụng

Khi tiếp nhận một PostgreSQL database chưa quen thuộc, lập trình viên thường phải trả lời nhiều câu hỏi:

- Đang kết nối đến **server**, **database** và **schema** nào?
- Có những bảng và view nào, mỗi bảng có những cột và kiểu dữ liệu gì?
- Cột nào là **primary key**, cột nào tham chiếu bảng khác qua **foreign key**?
- Một cột có cho phép `NULL` không, có `DEFAULT` hoặc `IDENTITY` không?
- Dữ liệu thực tế có những giá trị, định dạng, khoảng thời gian và trường hợp thiếu nào?
- Truy vấn giữa các bảng nên viết theo quan hệ nào?
- Một bảng có nhiều dòng không, chỉ mục nào đang tồn tại và PostgreSQL dự kiến đọc dữ liệu ra sao?
- Có thể tìm hiểu dữ liệu mà **không vô tình sửa hoặc làm chậm hệ thống** không?

Các công cụ đồ họa như **pgAdmin** cho phép xem cấu trúc và thực thi SQL qua giao diện. Công cụ dòng lệnh **psql** giúp tra cứu, lưu script và lặp lại các bước trên môi trường không có giao diện đồ họa. Ngoài ra, các SQL client như DBeaver hoặc DataGrip cũng phục vụ những nhu cầu tương tự.

Bài này trình bày một quy trình **khám phá từ kết nối đến cấu trúc, dữ liệu, quan hệ và kế hoạch truy vấn**, dùng PostgreSQL làm ví dụ xuyên suốt. Mục tiêu là biết **cần quan sát gì và SQL nào có thể kiểm chứng kết luận**, thay vì chỉ nhớ vị trí một nút bấm cụ thể của một phiên bản giao diện.

> **Quy tắc thực hành:** trên database chưa rõ nguồn gốc hoặc production, hãy ưu tiên tài khoản **chỉ đọc** và câu `SELECT` có giới hạn hợp lý. Mọi lệnh tạo bảng, nạp dữ liệu hoặc thay đổi schema trong bài chỉ chạy trên **database thực hành** được phép.

## 2. Lựa chọn công cụ khám phá dữ liệu

| Công cụ | Phong cách thao tác | Điểm mạnh | Khi nên dùng |
|---|---|---|---|
| **pgAdmin** | Đồ họa, Object Explorer, Query Tool | Nhìn cây server/database/schema/table, xem metadata, chạy SQL và xem kết quả | Mới học PostgreSQL, cần duyệt schema trực quan |
| **psql** | Dòng lệnh | Nhanh, dễ tự động hóa, có meta-command như `\dt` và `\d+` | Terminal, SSH, container, script hoặc kiểm tra trực tiếp |
| **DBeaver** | SQL IDE đồ họa đa hệ CSDL | Duyệt database, chỉnh sửa script, xem dữ liệu, xuất kết quả | Làm việc với nhiều DBMS hoặc nhiều kết nối |
| **DataGrip** | SQL IDE tích hợp môi trường phát triển | Hỗ trợ viết SQL, điều hướng đối tượng và kiểm tra kết quả | Lập trình viên muốn thao tác trong IDE |
| **Ứng dụng SQL qua JDBC/Python** | Code | Lặp lại truy vấn, truy xuất dữ liệu có kiểm soát | Tự động hóa phân tích hoặc xử lý tích hợp |

**pgAdmin không phải PostgreSQL Server.** pgAdmin là một **client** kết nối vào server; việc cài pgAdmin không tự đồng nghĩa PostgreSQL Server đã chạy hoặc database mẫu đã tồn tại.

Tương tự, `psql` là công cụ client. Bạn cần một PostgreSQL Server đang chạy và thông tin kết nối phù hợp. Các câu SQL khám phá ở phần sau có thể chạy trong **pgAdmin Query Tool**, `psql` hoặc hầu hết SQL client khác; những lệnh bắt đầu bằng dấu `\` như `\dt` là **meta-command riêng của psql**, không gửi nguyên văn qua JDBC hoặc Query Tool.

### 2.1. Những khái niệm cấp kết nối

~~~text
PostgreSQL server / instance
├── database: postgres
├── database: learning_db
│   ├── schema: public
│   └── schema: explore_lab
│       ├── table: customers
│       ├── table: products
│       ├── table: orders
│       └── view: v_paid_orders
└── database: another_db
~~~

- **Server/instance** là tiến trình PostgreSQL nhận kết nối và quản lý các database.
- **Database** là phạm vi đối tượng mà một kết nối PostgreSQL truy cập trực tiếp.
- **Schema** là không gian tên trong một database, chứa table, view, function và đối tượng khác.
- **Table** lưu các hàng dữ liệu; **view** là truy vấn được đặt tên (view thông thường không tự chứa dữ liệu kết quả).
- **Role/user** quản lý xác thực và quyền. Tên login role không nhất thiết trùng tên schema.

Không nên nhầm **database** với **schema**. Ví dụ `explore_lab.orders` là bảng `orders` trong schema `explore_lab` của **database đang kết nối**, không phải đường dẫn đến một database khác.

## 3. Thông tin cần có trước khi mở kết nối

Hãy lấy từ người quản trị hoặc cấu hình môi trường được phép:

| Thông tin | Ví dụ minh họa | Mục đích |
|---|---|---|
| Host | `db-lab.example.internal` | Máy hoặc endpoint nhận kết nối |
| Port | `5432` | Cổng PostgreSQL; có thể không dùng mặc định |
| Database | `learning_db` | Database chứa dữ liệu cần tìm hiểu |
| Username | `report_reader` | Login role được cấp quyền |
| Password/credential | Do secret manager cấp | Xác thực |
| TLS/SSL mode | `verify-full` nếu hạ tầng hỗ trợ đúng CA/hostname | Mã hóa/xác thực kết nối |
| Schema mục tiêu | `explore_lab` | Phạm vi khám phá |
| Chính sách | Chỉ đọc, hạn mức query, môi trường staging | Tránh ảnh hưởng hệ thống |

Không lưu mật khẩu thật trong tài liệu, Git repository hoặc lệnh được chia sẻ công khai. Nếu dùng trình quản lý bí mật, hãy lấy thông tin qua cơ chế được tổ chức cho phép. Khi kết nối qua VPN, SSH tunnel hoặc proxy, địa chỉ trong SQL client có thể khác địa chỉ thật của server.

### 3.1. Kiểm tra đúng đích sau khi kết nối

Câu SQL dưới đây có thể chạy ở bất cứ SQL client nào:

~~~sql
SELECT
    current_database() AS database_name,
    current_user AS current_role,
    session_user AS login_role,
    current_schema() AS default_schema,
    current_setting('search_path') AS search_path,
    current_setting('TimeZone') AS session_timezone,
    version() AS server_version;
~~~

Giải thích:

- `current_database()` trả database hiện tại.
- `current_user` là role hiệu lực để kiểm tra quyền; có thể khác `session_user` nếu đã đổi role.
- `current_schema()` phản ánh schema hiện hành theo `search_path`, không phải toàn bộ schema trong database.
- `search_path` quyết định cách PostgreSQL tìm đối tượng khi viết tên không kèm schema.
- `TimeZone` ảnh hưởng hiển thị/tính toán một số giá trị thời gian.

Nếu ứng dụng có cả staging và production, nên xác minh endpoint bằng thông tin hạ tầng ngoài tên database. Hai server khác nhau hoàn toàn có thể cùng có database tên `learning_db`.

## 4. Kết nối và duyệt dữ liệu trong pgAdmin

### 4.1. Đăng ký PostgreSQL Server

Các phiên bản pgAdmin có thể khác về bố trí nút, nhưng quy trình phổ biến:

1. Mở pgAdmin, tìm **Register > Server** hoặc chức năng đăng ký server mới trong nhóm **Servers**.
2. Trong phần **General**, đặt tên hiển thị dễ nhận diện, ví dụ `PostgreSQL Lab - Read Only`. Đây là tên trong pgAdmin, **không phải** tên database hoặc PostgreSQL server thật.
3. Trong phần **Connection**, nhập host, port, maintenance database, username và cơ chế xác thực.
4. Nếu môi trường yêu cầu TLS, cấu hình SSL/TLS theo CA, server name và chính sách của tổ chức.
5. Lưu cấu hình và mở kết nối.
6. Kiểm tra SQL ở mục 3.1 để bảo đảm đang kết nối đúng database/role.

**Maintenance database** trong màn đăng ký thường là database dùng để mở kết nối quản trị ban đầu, ví dụ `postgres` hoặc một database được cấp quyền. Nó không có nghĩa bạn đã mở đúng database nghiệp vụ. Hãy chọn **database thực tế** trong Object Explorer trước khi mở Query Tool.

Việc bật chức năng lưu mật khẩu trong GUI cần tuân theo chính sách thiết bị và bảo mật; không mặc định mọi máy đều đủ an toàn để lưu mật khẩu dưới dạng có thể tự đăng nhập lại.

### 4.2. Duyệt cây đối tượng (Object Explorer)

Một đường dẫn thường thấy trong pgAdmin:

~~~text
Servers
└── PostgreSQL Lab
    └── Databases
        └── learning_db
            └── Schemas
                └── explore_lab
                    ├── Tables
                    │   ├── customers
                    │   │   ├── Columns
                    │   │   ├── Constraints
                    │   │   └── Indexes
                    │   ├── products
                    │   └── orders
                    ├── Views
                    │   └── v_paid_orders
                    ├── Functions
                    └── Procedures
~~~

Ở từng bảng có thể xem:

- **Columns:** tên cột, kiểu dữ liệu, nullable, default/identity.
- **Constraints:** primary key, unique, foreign key, check.
- **Indexes:** chỉ mục thường, composite index, unique index, phương thức truy cập.
- **Properties:** những thuộc tính được giao diện hỗ trợ.
- **SQL/DDL:** câu lệnh tái tạo đối tượng khi pgAdmin hiển thị được.

Nếu không thấy schema hoặc bảng mong đợi, hãy kiểm tra đúng **database**, quyền của role, bộ lọc Object Explorer và việc cần **Refresh** cây đối tượng sau khi schema thay đổi. Không kết luận bảng đã bị xóa chỉ từ việc nó chưa hiện trong một danh sách bị lọc.

### 4.3. Xem dữ liệu qua menu View/Edit Data

pgAdmin thường có chức năng **View/Edit Data**, với các lựa chọn như xem một số dòng đầu hoặc toàn bộ dòng tùy phiên bản/giao diện.

Chức năng này rất tiện để nhìn nhanh giá trị thực tế, nhưng cần lưu ý:

- Một bảng lớn có thể rất tốn kém nếu yêu cầu xem **tất cả dữ liệu**.
- Khi không có thứ tự xác định, “100 dòng đầu” không phải 100 dòng mới nhất.
- Giao diện có thể cho sửa trực tiếp nếu role có quyền; **đừng sửa dữ liệu chỉ để khám phá**.
- Các giá trị JSONB, array, bytea, timestamp hoặc text dài có thể được hiển thị theo format của GUI.
- Kết quả bị giới hạn/phân trang trong công cụ **không cho biết tổng số hàng của bảng**.

Để kiểm soát chính xác tập dữ liệu, nên chuyển sang **Query Tool** và tự viết `SELECT ... ORDER BY ... LIMIT`.

### 4.4. Mở Query Tool

Chọn database mục tiêu rồi mở **Tools > Query Tool** hoặc chức năng tương đương trong giao diện. Trong Query Tool:

1. Nhập một câu `SELECT`.
2. Chạy bằng nút Execute/Run hoặc phím tắt hiện trong công cụ.
3. Xem bảng kết quả ở vùng **Data Output**.
4. Xem thông báo, thời gian chạy và lỗi ở vùng messages/history nếu công cụ có.
5. Sử dụng giải thích kế hoạch truy vấn khi cần, nhưng phân biệt thao tác **Explain** với **Explain Analyze**.
6. Lưu những câu SQL hữu ích thành file `.sql` để có thể lặp lại.

Ví dụ đầu tiên nên là:

~~~sql
SELECT *
FROM information_schema.tables
WHERE table_schema = 'explore_lab'
ORDER BY table_name
LIMIT 50;
~~~

**Một script có nhiều statement** có thể thực hiện nhiều thao tác nếu nhấn chạy toàn bộ. Khi mục đích chỉ xem dữ liệu, chọn đúng câu hoặc vùng SQL trước khi chạy và kiểm tra kỹ những câu như `DELETE`, `UPDATE`, `DROP`, `TRUNCATE` hoặc `ALTER`.

### 4.5. Lưu kết quả hoặc xuất CSV

Có thể dùng chức năng tải/xuất result set từ GUI tùy phiên bản. Khi xuất dữ liệu:

- Chỉ chọn những cột cần thiết, tránh `SELECT *` trên bảng chứa dữ liệu cá nhân.
- Xác định encoding (thường UTF-8), delimiter, tên cột và cách biểu diễn `NULL`.
- Xem giới hạn số dòng của Query Tool; file được xuất từ result grid **có thể chỉ chứa tập dòng đã tải**.
- Bảo vệ file xuất vì dữ liệu trong CSV không được bảo vệ tự động bởi quyền truy cập PostgreSQL sau khi đã rời server.

Nếu cần trích dữ liệu có thể lặp lại và kiểm soát kích thước, `psql \copy` là một phương án khác sẽ được giới thiệu sau.

## 5. Khám phá bằng psql

`psql` là client dòng lệnh chính thức của PostgreSQL, thường có sẵn khi cài bộ công cụ PostgreSQL.

### 5.1. Kết nối

~~~bash
psql -h db-lab.example.internal -p 5432 -U report_reader -d learning_db
~~~

Theo cấu hình xác thực, client có thể hỏi password hoặc dùng một phương án xác thực khác. Có thể sử dụng connection string:

~~~bash
psql "host=db-lab.example.internal port=5432 dbname=learning_db user=report_reader sslmode=verify-full"
~~~

`verify-full` yêu cầu kết nối TLS và xác minh host/certificate phù hợp. Nếu chưa có CA và tên host hợp lệ, không thể coi việc thêm chuỗi này là đủ để bảo mật; phải cấu hình chứng chỉ theo yêu cầu hạ tầng.

Không gắn mật khẩu thật vào argument hoặc URL được ghi trong log. Với kết nối nội bộ thử nghiệm và yêu cầu bảo mật khác nhau, tham số SSL mode phải do chính sách của môi trường quyết định.

### 5.2. Meta-command thường dùng

Trong prompt `psql`:

| Lệnh | Công dụng |
|---|---|
| `\conninfo` | Xem thông tin kết nối hiện tại |
| `\l` | Liệt kê databases (theo quyền và khả năng hiển thị) |
| `\c learning_db` | Chuyển kết nối sang database khác |
| `\dn` | Liệt kê schemas |
| `\dt explore_lab.*` | Liệt kê bảng trong schema `explore_lab` |
| `\dv explore_lab.*` | Liệt kê views trong schema |
| `\di explore_lab.*` | Liệt kê indexes |
| `\d explore_lab.orders` | Mô tả bảng, cột, index và ràng buộc |
| `\d+ explore_lab.orders` | Thêm một số thông tin chi tiết tùy phiên bản |
| `\df explore_lab.*` | Tìm functions trong schema |
| `\du` | Xem roles có thể hiển thị |
| `\timing on` | Hiển thị thời gian thực hiện câu lệnh |
| `\x auto` | Tự chuyển sang kiểu hiển thị dọc khi phù hợp |
| `\h SELECT` | Xem trợ giúp cú pháp SQL cho `SELECT` |
| `\?` | Xem trợ giúp meta-command của psql |
| `\q` | Thoát psql |

Meta-command **không có dấu chấm phẩy ở cuối** như câu SQL. Ví dụ:

~~~text
learning_db=> \dn
learning_db=> \dt explore_lab.*
learning_db=> \d+ explore_lab.orders
learning_db=> \timing on
learning_db=> SELECT current_database(), current_user;
learning_db=> \q
~~~

Không chạy `\d`, `\dt` hoặc `\copy` dưới dạng JDBC `Statement.execute(...)`: đó là cú pháp của client `psql`, không phải SQL server.

### 5.3. Chạy một script SQL

~~~bash
psql -h db-lab.example.internal -U report_reader -d learning_db \
  -v ON_ERROR_STOP=1 -f inspect_schema.sql
~~~

`-f` cho psql đọc file ở **máy chạy psql**. `ON_ERROR_STOP=1` làm psql dừng khi gặp lỗi SQL trong script, phù hợp khi cần nhận diện lỗi thay vì tiếp tục và có thể bỏ qua kết quả sai. Với những script có khả năng ghi, cần quản lý transaction và quyền, không mặc định `ON_ERROR_STOP` tự rollback mọi câu đã thực thi.

Lệnh `-X` có thể được dùng để tránh đọc file cấu hình khởi động riêng `psqlrc` khi cần hành vi client nhất quán:

~~~bash
psql -X -v ON_ERROR_STOP=1 -d learning_db -f inspect_schema.sql
~~~

Trong script khảo sát, nên đặt tên schema đầy đủ và dùng câu `SELECT` tường minh để giảm phụ thuộc vào cấu hình session.

## 6. Chuẩn bị bộ dữ liệu mẫu để thực hành

Từ đây, các thao tác **CREATE/INSERT** chỉ chạy trên database thực hành nơi bạn có quyền tạo schema. Khi chỉ có quyền đọc production, **bỏ qua phần này** và dùng các câu khám phá metadata ở các mục sau với schema được phép.

### 6.1. Tạo schema và bảng

~~~sql
CREATE SCHEMA IF NOT EXISTS explore_lab;

CREATE TABLE explore_lab.customers (
    customer_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    tier TEXT NOT NULL CHECK (tier IN ('VIP', 'STANDARD'))
);

CREATE TABLE explore_lab.products (
    product_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    current_price NUMERIC(12, 2) NOT NULL CHECK (current_price >= 0),
    tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]
);

CREATE TABLE explore_lab.orders (
    order_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES explore_lab.customers(customer_id),
    ordered_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    total_amount NUMERIC(12, 2) NOT NULL CHECK (total_amount >= 0),
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB
);

CREATE INDEX idx_orders_customer_time
ON explore_lab.orders (customer_id, ordered_at DESC);
~~~

Ở đây:

- `BIGINT GENERATED BY DEFAULT AS IDENTITY` cho PostgreSQL tự sinh ID nếu không truyền giá trị. Ví dụ sẽ **cố định ID** khi nạp dữ liệu để kết quả dễ theo dõi.
- `TIMESTAMPTZ` biểu diễn một mốc thời gian; cách hiển thị có thể thay đổi theo time zone của session.
- `NUMERIC(12,2)` thích hợp cho những giá trị tiền có hai chữ số thập phân.
- `TEXT[]` là kiểu array của PostgreSQL.
- `JSONB` lưu dữ liệu JSON ở dạng nhị phân có hỗ trợ các toán tử đặc trưng.
- `CHECK` áp dụng quy tắc giá trị cho cột `status` và `tier`.
- Foreign key từ `orders.customer_id` tới `customers.customer_id` đảm bảo đơn tham chiếu khách hàng có thật.

### 6.2. Nạp dữ liệu

~~~sql
INSERT INTO explore_lab.customers
    (customer_id, email, full_name, joined_at, tier)
VALUES
    (1, 'an@example.com', 'Nguyen An',
        TIMESTAMPTZ '2026-01-01 08:00:00+07', 'VIP'),
    (2, 'binh@example.com', 'Tran Binh',
        TIMESTAMPTZ '2026-01-02 08:00:00+07', 'STANDARD'),
    (3, 'chi@example.com', 'Le Chi',
        TIMESTAMPTZ '2026-01-03 08:00:00+07', 'VIP');

INSERT INTO explore_lab.products
    (product_id, sku, product_name, current_price, tags)
VALUES
    (11, 'KB-01', 'Ban phim', 350000.00, ARRAY['accessory', 'office']),
    (12, 'MS-01', 'Chuot', 150000.00, ARRAY['accessory']),
    (13, 'MN-01', 'Man hinh', 2200000.00, ARRAY['display', 'office']);

INSERT INTO explore_lab.orders
    (order_id, customer_id, ordered_at, status, total_amount, metadata)
VALUES
    (1001, 1, TIMESTAMPTZ '2026-01-05 10:00:00+07',
        'PAID', 500000.00, '{"channel":"web","coupon":null}'::jsonb),
    (1002, 2, TIMESTAMPTZ '2026-01-05 15:00:00+07',
        'PAID', 2200000.00, '{"channel":"mobile"}'::jsonb),
    (1003, 1, TIMESTAMPTZ '2026-01-08 16:00:00+07',
        'NEW', 350000.00, '{"channel":"web"}'::jsonb),
    (1004, 3, TIMESTAMPTZ '2026-01-10 09:00:00+07',
        'PAID', 150000.00, '{"channel":"store"}'::jsonb),
    (1005, 2, TIMESTAMPTZ '2026-02-01 11:00:00+07',
        'CANCELLED', 900000.00, '{}'::jsonb);
~~~

Vì dữ liệu mẫu truyền ID tường minh cho identity columns, sequence nội bộ có thể vẫn ở giá trị khởi đầu. Nếu muốn thêm bản ghi mới **không chỉ định ID** sau này, cần đồng bộ sequence theo cách có kiểm soát hoặc tạo schema lab mới. Các bước khám phá trong bài **không yêu cầu ghi thêm hàng** sau khi nạp dữ liệu mẫu.

Từ dữ liệu này có:

| Tập dữ liệu | Số dòng |
|---|---:|
| `explore_lab.customers` | 3 |
| `explore_lab.products` | 3 |
| `explore_lab.orders` | 5 |

Trong `orders`: ba đơn `PAID` có tổng `2.850.000`, một đơn `NEW` và một đơn `CANCELLED`. Các kết quả sau lấy chính bộ dữ liệu này làm cơ sở.

### 6.3. Tạo một view để khám phá

~~~sql
CREATE VIEW explore_lab.v_paid_orders AS
SELECT
    o.order_id,
    o.ordered_at,
    c.full_name,
    o.total_amount
FROM explore_lab.orders AS o
JOIN explore_lab.customers AS c
  ON c.customer_id = o.customer_id
WHERE o.status = 'PAID';
~~~

View chỉ chứa câu truy vấn định nghĩa. Khi đọc view thông thường, PostgreSQL thực thi logic truy vấn dựa trên dữ liệu nguồn tại thời điểm phù hợp. **View khác materialized view**, vốn lưu kết quả đã tính và cần refresh.

## 7. Khám phá danh mục schema và đối tượng

### 7.1. Liệt kê các schema

~~~sql
SELECT
    schema_name,
    schema_owner
FROM information_schema.schemata
WHERE schema_name NOT IN ('pg_catalog', 'information_schema')
ORDER BY schema_name;
~~~

Tùy role và quyền, một số schema có thể không xuất hiện. Vì vậy “không thấy schema” chưa chắc là schema không tồn tại; có thể user không có quyền hoặc bạn đang kết nối sai database.

Trong psql:

~~~text
\dn
~~~

Trong pgAdmin: chọn database rồi mở nhóm **Schemas**.

### 7.2. Liệt kê các bảng và view trong một schema

~~~sql
SELECT
    table_schema,
    table_name,
    table_type
FROM information_schema.tables
WHERE table_schema = 'explore_lab'
ORDER BY table_type, table_name;
~~~

Kỳ vọng có ba `BASE TABLE` và một `VIEW`.

Nếu muốn dùng PostgreSQL catalog:

~~~sql
SELECT
    schemaname,
    tablename,
    tableowner
FROM pg_catalog.pg_tables
WHERE schemaname = 'explore_lab'
ORDER BY tablename;
~~~

`information_schema` là giao diện metadata theo chuẩn SQL, thuận tiện cho thông tin chung. `pg_catalog` cung cấp nhiều chi tiết riêng của PostgreSQL, gồm index, ràng buộc, thống kê và kiểu đối tượng không thể hiện hết trong information schema.

### 7.3. Tên đủ schema và search_path

Hai câu sau có thể có hành vi khác:

~~~sql
SELECT * FROM orders LIMIT 5;

SELECT * FROM explore_lab.orders LIMIT 5;
~~~

Câu thứ nhất chỉ tìm `orders` trong các schema thuộc `search_path`. Nếu không có `explore_lab` trong path hoặc có bảng `orders` ở schema khác đứng trước, kết quả có thể lỗi hoặc đọc **nhầm bảng**.

Kiểm tra:

~~~sql
SHOW search_path;

SELECT current_schema();
~~~

Có thể chọn schema ưu tiên trong **session thực hành**:

~~~sql
SET search_path TO explore_lab, public;

SELECT order_id, status
FROM orders
ORDER BY order_id
LIMIT 5;
~~~

Sau khi chuyển session hoặc mở Query Tool mới, `search_path` có thể trở lại cấu hình mặc định. Khi viết câu SQL dùng trong tài liệu, script quản trị hoặc khám phá nhiều schema, **tên có schema đầy đủ** như `explore_lab.orders` giúp tránh nhầm lẫn.

## 8. Khám phá cột, kiểu dữ liệu và giá trị mặc định

### 8.1. Dùng information_schema.columns

~~~sql
SELECT
    ordinal_position,
    column_name,
    data_type,
    udt_name,
    is_nullable,
    column_default,
    identity_generation
FROM information_schema.columns
WHERE table_schema = 'explore_lab'
  AND table_name = 'orders'
ORDER BY ordinal_position;
~~~

Các trường cần đọc:

| Trường | Ý nghĩa |
|---|---|
| `ordinal_position` | Thứ tự cột trong định nghĩa bảng |
| `column_name` | Tên cột |
| `data_type` | Kiểu được trình bày theo information schema |
| `udt_name` | Tên kiểu nền của PostgreSQL; hữu ích với kiểu riêng hoặc array |
| `is_nullable` | Có cho phép giá trị SQL `NULL` hay không |
| `column_default` | Biểu thức default nếu có |
| `identity_generation` | `ALWAYS` / `BY DEFAULT` đối với identity column, nếu áp dụng |

Với kiểu domain, enum, array hoặc kiểu do người dùng định nghĩa, `information_schema.columns.data_type` có thể chưa đủ mô tả toàn bộ. Khi cần kiểu PostgreSQL chính xác, dùng `psql \d+` hoặc `pg_catalog`.

### 8.2. Dùng pg_attribute và format_type

~~~sql
SELECT
    a.attnum AS column_position,
    a.attname AS column_name,
    pg_catalog.format_type(a.atttypid, a.atttypmod) AS pg_type,
    a.attnotnull AS not_null,
    pg_catalog.pg_get_expr(d.adbin, d.adrelid) AS default_expr
FROM pg_catalog.pg_attribute AS a
JOIN pg_catalog.pg_class AS c
  ON c.oid = a.attrelid
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.relnamespace
LEFT JOIN pg_catalog.pg_attrdef AS d
  ON d.adrelid = a.attrelid
 AND d.adnum = a.attnum
WHERE n.nspname = 'explore_lab'
  AND c.relname = 'orders'
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
~~~

Truy vấn này dùng PostgreSQL catalog để lấy **kiểu được định dạng đầy đủ**, hữu ích khi muốn thấy `numeric(12,2)` hoặc phân biệt kiểu với độ dài/precision. Đối với thông tin identity/generated, cần xem thêm metadata tương ứng, không mặc định `default_expr` một mình thể hiện hết.

Trong psql:

~~~text
\d+ explore_lab.orders
~~~

Trong pgAdmin: mở bảng `orders` rồi xem **Columns** và những thuộc tính tương ứng.

### 8.3. Phân biệt SQL NULL, JSON null và chuỗi rỗng

Trong bảng `orders` có `metadata JSONB`; một object có thể chứa key `"coupon": null`. Cần phân biệt:

- **SQL `NULL`:** cột không có giá trị SQL.
- **JSON `null`:** một giá trị nằm trong tài liệu JSON.
- **Chuỗi rỗng `''`:** giá trị text có độ dài bằng 0.
- **Key JSON vắng mặt:** không hề có key trong object.

Ví dụ:

~~~sql
SELECT
    order_id,
    metadata,
    metadata ? 'coupon' AS has_coupon_key,
    metadata -> 'coupon' AS coupon_json_value,
    metadata ->> 'coupon' AS coupon_text_value
FROM explore_lab.orders
ORDER BY order_id;
~~~

Với `order_id = 1001`, key `coupon` tồn tại và chứa JSON null. Với các đơn không có key này, toán tử `?` trả false. Toán tử `->>` trả kiểu text và có thể cho SQL NULL đối với JSON null hoặc key vắng, nên phải kiểm tra sự tồn tại của key khi cần phân biệt hai trường hợp.

## 9. Khám phá khóa, ràng buộc và các quan hệ

### 9.1. Dùng pg_constraint

~~~sql
SELECT
    c.conname AS constraint_name,
    c.contype AS constraint_type_code,
    c.conrelid::regclass AS table_name,
    pg_catalog.pg_get_constraintdef(c.oid, true) AS definition
FROM pg_catalog.pg_constraint AS c
JOIN pg_catalog.pg_class AS t
  ON t.oid = c.conrelid
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = t.relnamespace
WHERE n.nspname = 'explore_lab'
ORDER BY t.relname, c.contype, c.conname;
~~~

Trong `pg_constraint.contype`, những mã thường gặp là:

| Mã | Loại ràng buộc |
|---|---|
| `p` | Primary key |
| `u` | Unique constraint |
| `f` | Foreign key |
| `c` | Check constraint |
| `x` | Exclusion constraint |

Một số thuộc tính NOT NULL được lưu trong metadata cột hoặc cơ chế catalog tùy phiên bản, vì vậy không nên chỉ dùng truy vấn `pg_constraint` để kết luận đầy đủ về **mọi** điều kiện nullability.

### 9.2. Liệt kê khóa ngoại bằng information_schema

~~~sql
SELECT
    tc.table_schema,
    tc.table_name,
    tc.constraint_name,
    kcu.column_name,
    ccu.table_schema AS referenced_schema,
    ccu.table_name AS referenced_table,
    ccu.column_name AS referenced_column
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
  ON kcu.constraint_catalog = tc.constraint_catalog
 AND kcu.constraint_schema = tc.constraint_schema
 AND kcu.constraint_name = tc.constraint_name
JOIN information_schema.constraint_column_usage AS ccu
  ON ccu.constraint_catalog = tc.constraint_catalog
 AND ccu.constraint_schema = tc.constraint_schema
 AND ccu.constraint_name = tc.constraint_name
WHERE tc.table_schema = 'explore_lab'
  AND tc.constraint_type = 'FOREIGN KEY'
ORDER BY tc.table_name, tc.constraint_name, kcu.ordinal_position;
~~~

Đối với khóa ngoại **nhiều cột**, nếu cần ghép đúng từng cột nguồn với từng cột đích theo vị trí, nên dùng thông tin `pg_constraint.conkey` / `confkey` hoặc ghép các view information schema có định vị cột phù hợp. Truy vấn đơn giản trên đây thích hợp nhất để **nhìn quan hệ**, không nên dùng làm máy sinh DDL cho mọi khóa ghép.

### 9.3. Quan hệ bảng trong dữ liệu mẫu

~~~mermaid
erDiagram
    CUSTOMERS ||--o{ ORDERS : places
    CUSTOMERS {
        bigint customer_id PK
        text email
        text full_name
    }
    ORDERS {
        bigint order_id PK
        bigint customer_id FK
        timestamptz ordered_at
        text status
    }
    PRODUCTS {
        bigint product_id PK
        text sku
        numeric current_price
    }
~~~

`customers` liên quan `orders` qua `customer_id`; `products` chưa liên quan đến `orders` trong bộ dữ liệu tối giản này. **Không tự suy luận rằng hai cột tên giống nhau luôn có khóa ngoại.** Muốn kết luận quan hệ được database bảo vệ, kiểm tra FK thật trong catalog.

### 9.4. Dùng JOIN để kiểm chứng hiểu biết

~~~sql
SELECT
    o.order_id,
    o.status,
    o.total_amount,
    c.customer_id,
    c.full_name
FROM explore_lab.orders AS o
JOIN explore_lab.customers AS c
  ON c.customer_id = o.customer_id
ORDER BY o.order_id;
~~~

Kỳ vọng trả năm dòng đơn hàng, kèm tên khách tương ứng.

Nếu muốn xem **mọi khách hàng**, kể cả khách chưa có đơn, dùng `LEFT JOIN`:

~~~sql
SELECT
    c.customer_id,
    c.full_name,
    COUNT(o.order_id) AS order_count
FROM explore_lab.customers AS c
LEFT JOIN explore_lab.orders AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.full_name
ORDER BY c.customer_id;
~~~

Ở dữ liệu mẫu: An có 2 đơn, Binh có 2 đơn, Chi có 1 đơn. `COUNT(o.order_id)` đúng hơn `COUNT(*)` cho yêu cầu đếm đơn trên `LEFT JOIN`, vì hàng khách chưa có đơn vẫn có một dòng NULL-extended trong kết quả JOIN.

## 10. Khám phá dữ liệu mà không đọc toàn bộ bảng

### 10.1. Xem vài dòng có thứ tự xác định

~~~sql
SELECT
    order_id,
    customer_id,
    ordered_at,
    status,
    total_amount
FROM explore_lab.orders
ORDER BY order_id
LIMIT 10;
~~~

`LIMIT 10` giới hạn số dòng trả về nhưng **không bảo đảm** query rẻ trong mọi trường hợp. Chẳng hạn, nếu `ORDER BY` yêu cầu sắp hàng triệu bản ghi mà không có index phù hợp, PostgreSQL vẫn có thể xử lý nhiều dòng để chọn Top 10.

Nếu chỉ muốn xem cấu trúc của result set, có thể chạy câu `SELECT` chỉ lấy các cột quan tâm và `LIMIT 0`:

~~~sql
SELECT
    order_id,
    status,
    total_amount
FROM explore_lab.orders
LIMIT 0;
~~~

Kết quả không có hàng nhưng SQL client vẫn có thể trình bày các cột/kiểu dữ liệu của result set.

### 10.2. Tránh SELECT * trên bảng thật

`SELECT *` hữu ích khi **mới học** và bảng nhỏ, nhưng trên hệ thống có dữ liệu nhạy cảm hoặc cột `JSONB`/`BYTEA` lớn, nó có thể:

- Truyền nhiều byte không cần thiết qua mạng.
- Hiện dữ liệu cá nhân trong result grid hoặc log.
- Làm SQL client tốn bộ nhớ.
- Khiến người đọc khó nhận diện những cột quan trọng.

Nên chọn cột cụ thể và có bộ lọc liên quan đến mục tiêu khám phá.

### 10.3. Tìm giá trị riêng biệt

~~~sql
SELECT DISTINCT status
FROM explore_lab.orders
ORDER BY status;
~~~

Kỳ vọng có `CANCELLED`, `NEW`, `PAID`.

Nếu muốn biết phân bố:

~~~sql
SELECT
    status,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_value
FROM explore_lab.orders
GROUP BY status
ORDER BY order_count DESC, status;
~~~

Đây là bước khảo sát thiết thực trước khi viết báo cáo hoặc tạo bộ lọc UI: biết giá trị hợp lệ, tần suất và trường hợp bất thường.

## 11. Khám phá chất lượng dữ liệu

### 11.1. NULL, giá trị trùng và khoảng giá trị

~~~sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (WHERE email IS NULL) AS email_missing,
    COUNT(DISTINCT email) AS distinct_emails,
    MIN(joined_at) AS first_joined_at,
    MAX(joined_at) AS last_joined_at
FROM explore_lab.customers;
~~~

Trong bảng mẫu `email NOT NULL UNIQUE` nên email thiếu bằng 0 và số email phân biệt bằng 3. Nhưng trong bảng thật, **ràng buộc có thể khác**, dữ liệu nhập từ nguồn ngoài có thể có giá trị bất thường hoặc một chuỗi rỗng.

Để tìm email trùng trong bảng **không có UNIQUE constraint**:

~~~sql
SELECT
    lower(trim(email)) AS normalized_email,
    COUNT(*) AS duplicate_count
FROM explore_lab.customers
WHERE email IS NOT NULL
GROUP BY lower(trim(email))
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC, normalized_email;
~~~

Ở schema mẫu không có kết quả. Truy vấn còn giúp minh họa một khác biệt: database đang unique theo **giá trị email gốc và collation/quy tắc so sánh tương ứng**, nhưng nghiệp vụ có thể định nghĩa trùng theo **email đã chuẩn hóa**. Cần xác nhận quy tắc trước khi dùng kết quả để sửa dữ liệu hoặc thêm unique index trên biểu thức.

### 11.2. Dữ liệu thời gian

~~~sql
SELECT
    MIN(ordered_at) AS first_order_at,
    MAX(ordered_at) AS last_order_at,
    COUNT(*) AS number_of_orders
FROM explore_lab.orders;
~~~

Để phân nhóm theo ngày địa phương:

~~~sql
SELECT
    (ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS order_day,
    COUNT(*) AS orders_count
FROM explore_lab.orders
GROUP BY 1
ORDER BY 1;
~~~

`TIMESTAMPTZ` lưu một mốc thời gian; hiển thị của `ordered_at` có thể phụ thuộc `TimeZone` của session. Với báo cáo “đơn ngày 05/01 theo Việt Nam”, dùng múi giờ rõ ràng giúp kết quả ổn định hơn.

### 11.3. Kiểm tra JSONB

~~~sql
SELECT
    order_id,
    metadata ->> 'channel' AS channel,
    jsonb_typeof(metadata) AS metadata_type
FROM explore_lab.orders
ORDER BY order_id;
~~~

Đếm theo kênh:

~~~sql
SELECT
    COALESCE(metadata ->> 'channel', '(missing)') AS channel,
    COUNT(*) AS order_count
FROM explore_lab.orders
GROUP BY 1
ORDER BY order_count DESC, channel;
~~~

Kỳ vọng `web` có 2, `mobile` có 1, `store` có 1 và `(missing)` có 1.

Một câu lọc JSONB:

~~~sql
SELECT order_id, status
FROM explore_lab.orders
WHERE metadata @> '{"channel":"web"}'::jsonb
ORDER BY order_id;
~~~

Toán tử `@>` kiểm tra JSONB chứa cấu trúc được đưa vào. Từ cách dữ liệu được lưu và toán tử truy vấn, bạn mới có cơ sở xem xét **GIN index** cho JSONB nếu một workload lớn thực sự cần.

### 11.4. Khám phá array

~~~sql
SELECT
    product_id,
    product_name,
    tags
FROM explore_lab.products
WHERE 'office' = ANY(tags)
ORDER BY product_id;
~~~

Kỳ vọng có `Ban phim` và `Man hinh`. PostgreSQL hỗ trợ array và toán tử array; không nên giả định dữ liệu array có thể dùng cú pháp truy vấn giống JSONB.

## 12. Đếm số dòng và ước lượng kích thước bảng

### 12.1. COUNT(*) chính xác

~~~sql
SELECT COUNT(*) AS exact_rows
FROM explore_lab.orders;
~~~

Trên lab kết quả bằng 5. Tuy nhiên, với PostgreSQL và MVCC, `COUNT(*)` chính xác trên bảng rất lớn thường phải xem xét nhiều tuple/index entries tương ứng với snapshot. Nó **không tự động là phép đọc một con số tổng cố định với chi phí O(1)**.

### 12.2. Ước lượng qua thống kê

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname = 'explore_lab'
ORDER BY relname;
~~~

- `n_live_tup` là **ước lượng** số hàng còn sống theo thống kê.
- `n_dead_tup` là **ước lượng** số tuple chết theo cơ chế thống kê.
- `last_analyze` và `last_autoanalyze` cho biết thời điểm thống kê được cập nhật (nếu có).

Các số có thể bằng 0 hoặc chưa cập nhật trên bảng vừa tạo. Không nên coi chúng bằng row count chính xác, và quyền xem thống kê có thể bị giới hạn.

Một cách khác:

~~~sql
SELECT
    c.oid::regclass AS relation_name,
    c.reltuples::bigint AS estimated_rows
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE n.nspname = 'explore_lab'
  AND c.relkind = 'r'
ORDER BY c.relname;
~~~

`reltuples` cũng là **ước lượng** và có thể chưa phản ánh các thay đổi mới.

### 12.3. Kích thước bảng và index

~~~sql
SELECT
    pg_size_pretty(pg_relation_size('explore_lab.orders'::regclass))
        AS table_heap_size,
    pg_size_pretty(pg_indexes_size('explore_lab.orders'::regclass))
        AS indexes_size,
    pg_size_pretty(pg_total_relation_size('explore_lab.orders'::regclass))
        AS total_relation_size;
~~~

Trong đó:

- `pg_relation_size` (khi không chỉ định fork) đo main fork của relation tương ứng.
- `pg_indexes_size` đo tổng kích thước các index liên quan.
- `pg_total_relation_size` bao gồm phần bảng, index, TOAST và thành phần liên quan theo định nghĩa hàm.

Giá trị thực tế phụ thuộc dữ liệu, phiên bản, storage và tình trạng bloat; không nên so trực tiếp với số byte trong CSV hay SQL dump.

Để xem các bảng lớn nhất trong một schema:

~~~sql
SELECT
    c.oid::regclass AS table_name,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE n.nspname = 'explore_lab'
  AND c.relkind IN ('r', 'p')
ORDER BY pg_total_relation_size(c.oid) DESC;
~~~

Đối với partitioned tables (`relkind = 'p'`), cần hiểu kích thước parent và các partitions; không nên coi kích thước relation parent bằng tổng mọi partition nếu hàm không cộng theo cách bạn kỳ vọng.

## 13. Khám phá chỉ mục và phương pháp truy cập

### 13.1. Liệt kê định nghĩa index

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'explore_lab'
ORDER BY tablename, indexname;
~~~

Kỳ vọng tìm thấy index của primary key/unique key và `idx_orders_customer_time` được tạo tường minh.

Trong psql:

~~~text
\di explore_lab.*
\d+ explore_lab.orders
~~~

Trong pgAdmin: mở nhóm **Indexes** dưới bảng, xem DDL/Properties của từng index.

### 13.2. Vì sao tồn tại index chưa chắc được dùng?

~~~sql
EXPLAIN
SELECT
    order_id,
    customer_id,
    ordered_at
FROM explore_lab.orders
WHERE customer_id = 1
ORDER BY ordered_at DESC
LIMIT 10;
~~~

Trên bảng năm dòng, `Seq Scan` có thể rẻ hơn việc đi qua index. PostgreSQL chọn kế hoạch dựa trên thống kê và chi phí ước lượng, không dựa trên việc người lập trình muốn nhìn thấy `Index Scan`.

Nếu bảng lớn có rất nhiều đơn cho nhiều khách hàng, index bắt đầu bằng `customer_id` có thể hữu ích cho câu trên. Muốn kết luận, phải kiểm tra **kế hoạch và dữ liệu đại diện**, không nhìn một thử nghiệm vài dòng.

### 13.3. Không tạo index tùy tiện

Index có tác dụng với truy vấn nhưng tăng chi phí `INSERT`, `UPDATE`, `DELETE` và dung lượng. Một index phù hợp cho điều kiện `WHERE customer_id = ...` không nhất thiết hỗ trợ tốt báo cáo `GROUP BY status` trên toàn bảng.

Khi chỉ làm nhiệm vụ **khám phá**, ưu tiên **quan sát** các index đã có. Việc thêm/bỏ index phải thuộc bước thiết kế và thay đổi schema được kiểm duyệt, không phải phản xạ ngay khi gặp câu SQL chậm.

## 14. Giải thích kế hoạch truy vấn bằng EXPLAIN

### 14.1. EXPLAIN chỉ ước lượng

~~~sql
EXPLAIN
SELECT
    o.order_id,
    o.total_amount,
    c.full_name
FROM explore_lab.orders AS o
JOIN explore_lab.customers AS c
  ON c.customer_id = o.customer_id
WHERE o.status = 'PAID'
ORDER BY o.order_id;
~~~

Bạn có thể thấy các node như:

| Node | Vai trò |
|---|---|
| `Seq Scan` | Quét tuần tự bảng |
| `Index Scan` | Dùng index tìm vị trí rồi đọc các hàng tương ứng |
| `Index Only Scan` | Có thể đọc từ index với điều kiện visibility phù hợp |
| `Bitmap Index Scan` / `Bitmap Heap Scan` | Thu thập vị trí ứng viên từ index rồi đọc heap theo bitmap |
| `Nested Loop` | Nối bảng theo vòng lặp |
| `Hash Join` | Xây/dùng bảng băm để nối |
| `Merge Join` | Nối hai nguồn có thứ tự phù hợp |
| `HashAggregate` | Tính nhóm bằng cấu trúc hash |
| `GroupAggregate` | Tính nhóm trên nguồn đã có thứ tự thích hợp |
| `Sort` | Sắp xếp kết quả trung gian |
| `Limit` | Giới hạn kết quả |

`cost=...` và `rows=...` trong `EXPLAIN` là **ước lượng của optimizer**, không phải số mili giây hay số hàng đã thực sự đọc.

### 14.2. EXPLAIN ANALYZE thực thi truy vấn

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    status,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_value
FROM explore_lab.orders
GROUP BY status
ORDER BY status;
~~~

`ANALYZE` làm PostgreSQL **chạy truy vấn thật** rồi xuất thêm thời gian và số dòng thực tế; `BUFFERS` cung cấp thông tin về hoạt động buffer. Nếu áp dụng lên `UPDATE` hoặc `DELETE`, câu DML thực sự được thực thi. Vì vậy ở giai đoạn khám phá an toàn, dùng `EXPLAIN ANALYZE` trước hết với `SELECT` thích hợp và không quá nặng.

`EXPLAIN (ANALYZE, BUFFERS)` trên query đọc lớn vẫn có thể tiêu tốn CPU/I/O và gây ảnh hưởng workload; không chạy tùy ý trên production trong giờ cao điểm.

### 14.3. Những câu hỏi khi xem kế hoạch

1. Bảng nào được truy cập trước? Tại sao?
2. Các điều kiện `WHERE` lọc từ đầu hay chỉ được áp dụng sau khi đã đọc nhiều hàng?
3. PostgreSQL ước lượng bao nhiêu `rows` ở từng node? `actual rows` khác nhiều không?
4. Có sort/hash lớn hoặc file tạm không?
5. Một truy vấn trả năm dòng phải xử lý bao nhiêu dòng đầu vào?
6. Có thể viết lại điều kiện hoặc bổ sung index phù hợp hơn không, sau khi đã đo?

Đừng tối ưu chỉ để loại một node `Sort` khi dữ liệu đang có vài dòng. Mục tiêu là **tính đúng đắn và chi phí tổng thể** của workload thật.

## 15. Khám phá phiên làm việc và hoạt động hệ thống

### 15.1. Thông tin giao dịch hiện tại

~~~sql
SELECT
    current_database(),
    current_user,
    current_setting('transaction_isolation') AS isolation_level,
    current_setting('statement_timeout') AS statement_timeout,
    current_setting('TimeZone') AS session_timezone;
~~~

Đặc biệt, `statement_timeout` có thể được cấu hình ở role/database/session để hạn chế câu SQL chạy quá lâu. Không nên tự điều chỉnh global settings chỉ vì một truy vấn khảo sát cần thêm thời gian.

### 15.2. pg_stat_activity

~~~sql
SELECT
    pid,
    usename,
    datname,
    state,
    wait_event_type,
    wait_event,
    query_start
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY query_start NULLS LAST
LIMIT 30;
~~~

Bảng/việc xem thông tin phụ thuộc quyền. Role thông thường có thể chỉ thấy chi tiết đầy đủ của phiên của chính nó hoặc thông tin bị giới hạn đối với phiên người khác. Không mặc định có quyền đọc toàn bộ SQL của mọi user.

Một số trạng thái:

- `active`: phiên đang thực hiện một câu lệnh.
- `idle`: kết nối đang rảnh, có thể đến từ connection pool.
- `idle in transaction`: phiên đang mở transaction nhưng không chạy câu lệnh tại thời điểm quan sát; giữ quá lâu là dấu hiệu cần điều tra.

Không dùng `pg_terminate_backend` hoặc `pg_cancel_backend` chỉ để khám phá khi chưa có quyền hạn/trách nhiệm vận hành phù hợp; chúng có thể ngắt công việc của người khác.

### 15.3. Khả năng quan sát phụ thuộc quyền

Một account chỉ đọc dữ liệu không nhất thiết được quyền xem mọi thống kê hệ thống, thông tin role khác hoặc định nghĩa object đặc biệt. Nếu gặp `permission denied`, hãy hỏi rõ quyền cần thiết; **không dùng superuser cho toàn bộ việc khám phá** chỉ để tránh một lỗi metadata.

## 16. Khám phá an toàn trên production

Một truy vấn `SELECT` vẫn có thể gây tải nặng hoặc tiết lộ thông tin. Phải phân biệt **không sửa dữ liệu** với **không gây ảnh hưởng**.

### 16.1. Nên có role chỉ đọc

Một ví dụ mô hình quyền do quản trị viên thiết lập trên database được phép:

~~~sql
-- Ví dụ dành cho người quản trị, KHÔNG chạy trên production
-- nếu chưa có quyền/phê duyệt:
CREATE ROLE explore_reader LOGIN;

GRANT CONNECT ON DATABASE learning_db TO explore_reader;
GRANT USAGE ON SCHEMA explore_lab TO explore_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA explore_lab TO explore_reader;
~~~

Đây là **mẫu quyền**, không phải quy trình cấp tài khoản hoàn chỉnh: còn cơ chế xác thực, quản lý mật khẩu, default privileges cho bảng tạo sau, row-level security, quyền trên sequences/functions và chính sách truy cập mạng. Các đối tượng tạo mới sau này không tự động nhận mọi quyền nếu chưa cấu hình default privileges phù hợp.

### 16.2. Transaction chỉ đọc khi cần

~~~sql
BEGIN READ ONLY;
SET LOCAL statement_timeout = '5s';

SELECT order_id, status, total_amount
FROM explore_lab.orders
ORDER BY order_id
LIMIT 20;

COMMIT;
~~~

- `BEGIN READ ONLY` bắt đầu transaction có cờ read-only, giúp ngăn nhiều loại thao tác ghi qua SQL trong transaction.
- `SET LOCAL` giới hạn thiết lập vào phạm vi transaction.
- `statement_timeout` là giới hạn thực thi câu SQL, không phải bảo đảm mọi loại I/O hay thao tác đều an toàn.
- `COMMIT`/`ROLLBACK` kết thúc transaction, tránh giữ phiên ở trạng thái `idle in transaction`.

**Không coi read-only transaction là lớp bảo mật duy nhất.** Quyền role và chính sách RLS mới quyết định đối tượng/hàng nào người dùng được đọc. Một `SELECT` có thể gọi function với tác dụng phụ nếu quyền/chức năng cho phép; vì vậy vẫn cần xem SQL trước khi thực thi.

### 16.3. Tránh truy vấn đắt không cần thiết

- Ưu tiên lọc theo khóa hoặc khoảng thời gian chọn lọc.
- Không chạy `COUNT(*)` trên bảng hàng tỷ dòng chỉ để biết “to hay nhỏ”; bắt đầu từ thống kê ước lượng.
- Không dùng `SELECT *` lấy mọi cột và hàng ở bảng chứa dữ liệu nhạy cảm.
- Không chạy `EXPLAIN ANALYZE` trên SQL chưa biết chi phí trong giờ tải cao.
- Đừng mở transaction rồi để màn hình SQL client rảnh hàng giờ.
- Không xuất dữ liệu cá nhân ra CSV/clipboard khi chưa có mục đích và quyền phù hợp.
- Ghi rõ server/schema trong script để tránh tác động nhầm môi trường.

### 16.4. Đừng dùng LIMIT như một biện pháp bảo vệ toàn diện

`LIMIT 100` có thể giúp giảm số dòng **trả về**, nhưng một câu `ORDER BY` phức tạp, aggregate hoặc join vẫn có thể phải xử lý khối lượng lớn. Giới hạn thời gian chạy, quyền truy cập và lựa chọn điều kiện truy vấn vẫn cần thiết.

## 17. Xuất dữ liệu bằng psql và lưu bằng chứng khám phá

### 17.1. Xuất CSV phía client với \copy

Trong psql, lệnh:

~~~text
\copy (SELECT order_id, status, total_amount FROM explore_lab.orders ORDER BY order_id) TO 'orders_sample.csv' WITH (FORMAT csv, HEADER true)
~~~

xuất ra file ở **máy chạy psql**, theo quyền của tiến trình client. Meta-command `\copy` khác câu SQL `COPY ... TO '/path/file'` vốn ghi file phía PostgreSQL Server và có yêu cầu quyền server đặc biệt.

Nếu chạy từ terminal, có thể dùng:

~~~bash
psql -h db-lab.example.internal -U report_reader -d learning_db \
  -c "\copy (SELECT order_id, status, total_amount FROM explore_lab.orders ORDER BY order_id LIMIT 100) TO 'orders_sample.csv' WITH (FORMAT csv, HEADER true)"
~~~

File có thể chứa dữ liệu nhạy cảm. Hãy dùng dữ liệu tối thiểu, thư mục được phép và chính sách lưu giữ/xóa phù hợp.

### 17.2. Lưu script khám phá

Một file `inspect_explore_lab.sql` có thể chứa những truy vấn như:

~~~sql
-- 1) Xác định session.
SELECT current_database(), current_user;

-- 2) Liệt kê bảng.
SELECT table_name, table_type
FROM information_schema.tables
WHERE table_schema = 'explore_lab'
ORDER BY table_name;

-- 3) Xem vài đơn gần nhất theo ID.
SELECT order_id, status, total_amount
FROM explore_lab.orders
ORDER BY order_id DESC
LIMIT 10;

-- 4) Phân bố trạng thái.
SELECT status, COUNT(*) AS orders_count
FROM explore_lab.orders
GROUP BY status
ORDER BY status;
~~~

Có thể chạy cùng file qua pgAdmin Query Tool hoặc `psql -f`. Script này không cần quyền ghi và tạo được một **quy trình kiểm tra có thể lặp lại**.

Khi lưu kết quả khám phá, nên ghi thêm:

- Database/server (không ghi bí mật).
- Tên schema, bảng và thời điểm khảo sát.
- PostgreSQL version nếu liên quan.
- SQL cụ thể đã chạy.
- Giải thích mẫu số, bộ lọc và time zone nếu báo cáo.
- Độ tin cậy của số liệu: **COUNT chính xác** hay **ước lượng thống kê**.

## 18. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Bước kiểm tra |
|---|---|---|
| `connection refused` | Host/port sai, server chưa chạy, firewall, tunnel | Kiểm tra endpoint và đường mạng |
| `password authentication failed` | Sai credential hoặc cơ chế xác thực | Kiểm tra user, password, `pg_hba.conf` theo quyền quản trị |
| `database does not exist` | Chọn sai database hoặc chưa tạo | Xác minh database có thật trên đúng server |
| `permission denied for schema` | Thiếu `USAGE` trên schema | Kiểm tra quyền theo role |
| `permission denied for table` | Thiếu `SELECT` hoặc RLS/role | Kiểm tra quyền đối tượng và chính sách |
| `relation "orders" does not exist` | Sai schema, sai `search_path` hoặc tên viết hoa có quote | Dùng tên `explore_lab.orders`, xem `\dt` |
| Bảng có trong pgAdmin nhưng query không thấy | Query Tool đang nối database khác hoặc schema khác | Chạy `current_database()`, `SHOW search_path` |
| Dữ liệu giờ lệch vài giờ | Time zone hiển thị không như dự định | Kiểm tra `TimeZone`, `AT TIME ZONE` |
| `LIMIT` trả các hàng khác nhau | Không có `ORDER BY` xác định | Thêm `ORDER BY` theo khóa duy nhất |
| `COUNT(*)` rất chậm | Bảng quá lớn, cần quét nhiều tuple | Xem `pg_stat_user_tables` nếu chỉ cần ước lượng |
| Index có nhưng `Seq Scan` | Dữ liệu nhỏ/điều kiện ít chọn lọc/thống kê | Xem `EXPLAIN`, không ép index vô cớ |
| Không thấy định nghĩa function | Thiếu quyền hoặc cách client lọc object | Kiểm tra quyền và pg_catalog phù hợp |
| Query Tool hiển thị ít dòng hơn dự đoán | Có row limit/pagination của client hoặc SQL | Đối chiếu câu SQL và cấu hình kết quả |
| Query báo lỗi thời gian chờ | `statement_timeout`, mạng, lock hoặc công cụ | Xem thông báo lỗi và nơi áp dụng timeout |

### 18.1. Tên có chữ hoa hoặc ký tự đặc biệt

PostgreSQL chuyển các tên **không đặt dấu ngoặc kép** về chữ thường:

~~~sql
SELECT * FROM explore_lab.orders;

-- Nếu từng tạo bảng với tên định danh chính xác "SalesOrders":
SELECT * FROM explore_lab."SalesOrders";
~~~

`"SalesOrders"` và `salesorders` không cùng tên trong PostgreSQL. Tránh dùng camel-case có dấu ngoặc kép không cần thiết khi thiết kế schema mới; đối với schema đã tồn tại, phải dùng đúng tên.

### 18.2. Nhầm VIEW và MATERIALIZED VIEW

Một view thường được xác định bằng truy vấn và trả kết quả từ bảng nguồn theo snapshot thích hợp. Materialized view lưu kết quả đã vật chất hóa và có thể **cũ** nếu chưa `REFRESH MATERIALIZED VIEW`. Khi thấy một object báo cáo, cần phân biệt loại trước khi tin rằng nó phản ánh mọi commit mới.

### 18.3. Nhầm kết quả NULL với chuỗi hiển thị của client

Một số công cụ hiển thị SQL `NULL` dưới dạng ô trống, chữ `[null]` hoặc màu sắc đặc biệt. Một ô trống trong GUI không chứng minh giá trị là chuỗi rỗng. Dùng SQL:

~~~sql
SELECT
    COUNT(*) FILTER (WHERE metadata ->> 'channel' IS NULL) AS no_channel,
    COUNT(*) FILTER (WHERE metadata ->> 'channel' = '') AS empty_channel
FROM explore_lab.orders;
~~~

Hai điều kiện trả lời hai câu hỏi khác nhau.

## 19. Quy trình khám phá một schema chưa quen thuộc

Có thể sử dụng checklist sau như một phương pháp làm việc lặp lại:

~~~mermaid
flowchart TD
    A["Xác minh đúng server / database / role"] --> B["Liệt kê schemas và các đối tượng"]
    B --> C["Xem cột, kiểu, PK/FK, CHECK, index"]
    C --> D["Đọc vài dòng có ORDER BY và LIMIT"]
    D --> E["Khảo sát NULL, distinct, min/max và phân bố"]
    E --> F["JOIN kiểm chứng quan hệ nghiệp vụ"]
    F --> G["Ước lượng kích thước và xem kế hoạch EXPLAIN"]
    G --> H["Ghi SQL, kết luận và mức độ tin cậy"]
~~~

Diễn giải chi tiết:

1. **Xác minh kết nối:** `current_database()`, `current_user`, server và time zone.
2. **Xem đối tượng:** schema, table, view và các object cần thiết.
3. **Hiểu dữ liệu:** kiểu cột, nullability, default, identity, check, PK, unique, FK, index.
4. **Nhìn dữ liệu mẫu:** vài dòng được sắp xếp có chủ đích; tránh thu thập dư thừa.
5. **Khảo sát phân bố:** giá trị phân biệt, `NULL`, khoảng ngày, tổng theo nhóm.
6. **Hiểu quan hệ:** kiểm tra FK thật và viết JOIN có ý nghĩa.
7. **Đánh giá quy mô:** `COUNT(*)` khi hợp lý, thống kê ước lượng và kích thước relation.
8. **Xem hiệu năng:** `EXPLAIN` trước; `EXPLAIN ANALYZE` khi được phép và phù hợp.
9. **Lưu kết quả:** script, quan sát, câu hỏi còn mở, nguồn gốc kết luận và phạm vi quyền truy cập.

Điểm quan trọng là **không biến khám phá dữ liệu thành thay đổi dữ liệu** khi chưa được giao nhiệm vụ thiết kế/migration.

## 20. Bài tập thực hành

Các bài dưới dùng `explore_lab` đã được nạp từ mục 6. Không cần thao tác ghi thêm.

### Bài 1 — Xác định môi trường

Viết câu SQL hiển thị database, current user, schema mặc định và time zone của session. Giải thích vì sao phải làm bước này trước khi mở Query Tool trên server có cả staging và production.

### Bài 2 — Tìm bảng, cột và kiểu

Viết câu SQL dùng `information_schema` để liệt kê mọi bảng/view trong `explore_lab`; sau đó xem tất cả cột của `orders` theo thứ tự định nghĩa. Nêu kiểu dữ liệu của `ordered_at` và `metadata`.

### Bài 3 — Xác định quan hệ

Viết câu SQL hoặc meta-command để tìm foreign key của `orders`. Nêu bảng/cột nguồn và bảng/cột được tham chiếu. Từ đó viết JOIN lấy tên khách của các đơn.

### Bài 4 — Khảo sát phân bố trạng thái

Đếm số đơn theo `status` và tổng `total_amount` theo từng trạng thái. Từ dữ liệu mẫu, có bao nhiêu đơn `PAID` và tổng của chúng là bao nhiêu?

### Bài 5 — Khám phá JSONB

Liệt kê các kênh mua hàng (`metadata.channel`) và số đơn ở mỗi kênh. Các đơn không có key `channel` được phân biệt ra sao so với chuỗi rỗng?

### Bài 6 — Xem index và giải thích plan

Liệt kê mọi index của bảng `explore_lab.orders`. Viết `EXPLAIN` cho truy vấn tìm đơn của khách 1 theo thứ tự thời gian giảm dần. Vì sao PostgreSQL có thể chọn `Seq Scan` trên tập dữ liệu mẫu dù có index?

### Bài 7 — Đếm chính xác và thống kê ước lượng

Dùng `COUNT(*)` để đếm chính xác các đơn. Sau đó lấy `n_live_tup` từ `pg_stat_user_tables`. Nếu hai số khác nhau, có phải dữ liệu bị mất không?

### Bài 8 — Khám phá an toàn

Bạn nhận một kết nối production chỉ đọc, bảng có 100 triệu đơn. Người quản lý hỏi “bảng lớn khoảng bao nhiêu hàng và có cột nào?”. Hãy chọn chuỗi bước không phải chạy ngay `SELECT * FROM orders` hoặc `COUNT(*)` trên toàn bảng.

### Bài 9 — Phân biệt công cụ client

Lệnh `\d+ explore_lab.orders` có chạy trong pgAdmin Query Tool bằng cách dán nguyên văn không? Nếu không, trong pgAdmin bạn dùng gì và câu SQL nào có thể thay thế một phần chức năng?

## 21. Gợi ý lời giải

### Bài 1

~~~sql
SELECT
    current_database(),
    current_user,
    current_schema(),
    current_setting('TimeZone');
~~~

Bước này ngăn việc suy luận từ tên hiển thị của kết nối, đặc biệt khi nhiều môi trường có cùng tên bảng.

### Bài 2

~~~sql
SELECT table_name, table_type
FROM information_schema.tables
WHERE table_schema = 'explore_lab'
ORDER BY table_name;

SELECT ordinal_position, column_name, data_type, udt_name
FROM information_schema.columns
WHERE table_schema = 'explore_lab'
  AND table_name = 'orders'
ORDER BY ordinal_position;
~~~

`ordered_at` là `timestamp with time zone` (`timestamptz`); `metadata` là kiểu PostgreSQL `jsonb`. Kiểu nền có thể xuất hiện trong `udt_name`.

### Bài 3

~~~sql
SELECT
    conname,
    pg_get_constraintdef(oid, true) AS definition
FROM pg_constraint
WHERE conrelid = 'explore_lab.orders'::regclass
  AND contype = 'f';

SELECT o.order_id, c.full_name
FROM explore_lab.orders AS o
JOIN explore_lab.customers AS c
  ON c.customer_id = o.customer_id
ORDER BY o.order_id;
~~~

FK là `orders.customer_id → customers.customer_id`.

### Bài 4

~~~sql
SELECT status,
       COUNT(*) AS order_count,
       SUM(total_amount) AS total_value
FROM explore_lab.orders
GROUP BY status
ORDER BY status;
~~~

Có **3 đơn PAID**, tổng **2.850.000,00**. Đơn `NEW` và `CANCELLED` không được cộng vào doanh thu đã thanh toán nếu nghiệp vụ định nghĩa doanh thu như vậy.

### Bài 5

~~~sql
SELECT
    COALESCE(metadata ->> 'channel', '(missing)') AS channel,
    COUNT(*) AS cnt
FROM explore_lab.orders
GROUP BY 1
ORDER BY channel;
~~~

Dữ liệu mẫu có `web = 2`, `mobile = 1`, `store = 1`, `(missing) = 1`. Để phân biệt key vắng với JSON null cần dùng `metadata ? 'channel'`; chuỗi rỗng là `= ''`, không đồng nghĩa `IS NULL`.

### Bài 6

~~~sql
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'explore_lab'
  AND tablename = 'orders';

EXPLAIN
SELECT order_id, customer_id, ordered_at
FROM explore_lab.orders
WHERE customer_id = 1
ORDER BY ordered_at DESC
LIMIT 10;
~~~

PostgreSQL có thể dùng `Seq Scan` vì bảng chỉ năm dòng và chi phí đọc toàn bộ rất nhỏ. Không ép index chỉ để làm cho plan “đẹp”.

### Bài 7

~~~sql
SELECT COUNT(*) AS exact_rows
FROM explore_lab.orders;

SELECT n_live_tup, last_analyze, last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname = 'explore_lab'
  AND relname = 'orders';
~~~

`COUNT(*)` ở snapshot là kết quả chính xác cho câu SQL; `n_live_tup` là **ước lượng thống kê** và có thể chưa cập nhật. Hai số lệch không đủ kết luận có mất dữ liệu.

### Bài 8

Trước hết xác minh server/role/schema, dùng `\d+` hoặc `information_schema.columns` để xem metadata; lấy ước lượng số hàng từ `pg_stat_user_tables.n_live_tup` hoặc `pg_class.reltuples`, kết hợp `pg_total_relation_size` để đánh giá quy mô. Nếu cần xem mẫu, chọn cột không nhạy cảm với bộ lọc và `LIMIT` cùng `ORDER BY` phù hợp. Chỉ chạy `COUNT(*)` chính xác khi chi phí, quyền và mục đích được chấp thuận.

### Bài 9

Không. `\d+` là meta-command của **psql**, không phải SQL. Trong pgAdmin có thể xem **Columns**, **Constraints**, **Indexes** và **Properties** trong Object Explorer; hoặc dùng `information_schema.columns`, `pg_constraint` và `pg_indexes` để lấy metadata bằng SQL.

## 22. Kết luận

Khám phá PostgreSQL hiệu quả bắt đầu từ **xác định đúng kết nối**, sau đó đi từ **schema → bảng/view → cột/kiểu → ràng buộc/chỉ mục → dữ liệu mẫu → phân bố/quan hệ → kích thước/kế hoạch truy vấn**. pgAdmin giúp duyệt các đối tượng trực quan và chạy SQL trong Query Tool; psql thuận lợi cho terminal, script và meta-command như `\dt`, `\d+`. Các SQL client khác có thể hỗ trợ quy trình tương đương.

Đừng chỉ dựa vào cách dữ liệu trông như thế nào trong result grid. Hãy **kiểm chứng bằng SQL và catalog**: `information_schema` cho metadata phổ biến; `pg_catalog` cho chi tiết PostgreSQL; `pg_stat_*` cho thống kê thường mang tính ước lượng; `EXPLAIN` cho kế hoạch dự kiến và `EXPLAIN ANALYZE` cho việc thực thi thực tế.

Quan trọng nhất, khám phá dữ liệu phải **an toàn và có mục đích**: dùng quyền tối thiểu, giới hạn tập cột/hàng trả về, hiểu rằng `SELECT` lớn vẫn tốn tài nguyên, và giữ lại script cùng những kết luận có thể kiểm chứng. Khi làm được các bước này, người học có nền tảng để viết truy vấn đúng, hiểu mô hình dữ liệu và đề xuất tối ưu PostgreSQL mà không cần đoán từ tên bảng hay giao diện.
