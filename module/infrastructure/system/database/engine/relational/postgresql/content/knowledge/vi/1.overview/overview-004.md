# Phân biệt máy chủ, cụm cơ sở dữ liệu, database, schema, bảng và hàng trong PostgreSQL

## 1. Vì sao cần phân biệt đúng từng cấp?

Khi mới học PostgreSQL, các từ **server**, **cluster**, **database**, **schema**, **table** và **row** thường bị dùng lẫn nhau. Chẳng hạn, một nhóm phát triển có thể nói “tạo một database cho ứng dụng” nhưng thực tế chỉ tạo thêm một **schema** trong database hiện có; hoặc “đã kết nối server” nhưng chưa biết session đang ở **database** nào.

Phân biệt đúng giúp bạn:

- Kết nối tới đúng PostgreSQL instance, database và schema.
- Hiểu vì sao hai bảng cùng tên vẫn có thể cùng tồn tại.
- Không nhầm việc tạo database với việc tạo schema.
- Thiết kế phân quyền và phân tách các ứng dụng một cách hợp lý.
- Đọc chính xác câu lệnh SQL, đường dẫn đối tượng và lỗi “relation does not exist”.
- Biết một truy vấn tìm kiếm **hàng dữ liệu** ở cấp nào.
- Hiểu giới hạn truy vấn giữa hai database khác nhau trên PostgreSQL.
- Tránh nhầm **PostgreSQL database cluster** với **cụm máy chủ HA/replication**.

Hệ thống phân cấp cơ bản:

```text
Máy tính / VM / container (host)
└── PostgreSQL server instance
    └── Database cluster (được khởi tạo bởi initdb)
        ├── Các đối tượng dùng chung cấp cluster
        │   ├── Roles / users
        │   └── Tablespaces, thông số và một số system catalogs
        ├── Database: postgres
        ├── Database: app_db
        │   ├── Schema: public
        │   │   └── Table: public.settings
        │   ├── Schema: sales
        │   │   ├── Table: sales.customers
        │   │   │   ├── Row: customer_id = 1
        │   │   │   └── Row: customer_id = 2
        │   │   └── Table: sales.orders
        │   └── Schema: audit
        │       └── Table: audit.events
        └── Database: analytics_db
            └── Schema: reporting
                └── Table: reporting.daily_metrics
```

Sơ đồ cho thấy một **instance PostgreSQL đang phục vụ một database cluster** chứa nhiều database, mỗi database có nhiều schema, mỗi schema chứa bảng và những đối tượng liên quan. Mỗi bảng có thể chứa nhiều hàng.

Về mặt kỹ thuật, **server instance** và **database cluster** gắn rất chặt với nhau và đôi khi được gọi thay thế trong vận hành. Tuy nhiên, *server* nhấn mạnh **tiến trình dịch vụ và kết nối**; *database cluster* nhấn mạnh **tập dữ liệu được khởi tạo, quản lý chung trong một data directory**. Trong những phần tiếp theo, sự khác biệt này được giải thích cụ thể.

## 2. Bảng so sánh nhanh sáu khái niệm

| Cấp | Tên tiếng Anh | Nó là gì? | Chứa hoặc quản lý gì? | Ví dụ |
|---|---|---|---|---|
| 1 | Server / PostgreSQL instance | Hệ thống tiến trình PostgreSQL đang chạy, nhận kết nối và xử lý SQL | Một database cluster được instance phục vụ | PostgreSQL lắng nghe tại `db.example.internal:5432` |
| 2 | Database cluster | Tập database cùng các đối tượng toàn cục, được khởi tạo trong một data directory | Nhiều database, roles, tablespaces và metadata dùng chung | Cluster có các database `postgres` và `app_db` |
| 3 | Database | Không gian lưu trữ/đối tượng tương đối độc lập bên trong cluster | Schemas và các đối tượng thuộc database | `app_db` |
| 4 | Schema | Namespace (không gian tên) bên trong một database | Tables, views, sequences, functions, types… | `sales` |
| 5 | Table | Quan hệ lưu dữ liệu theo cột và hàng | Các hàng cùng định nghĩa cột, ràng buộc, chỉ mục liên quan | `sales.orders` |
| 6 | Row | Một bản ghi logic trong bảng | Các giá trị cột của một thực thể hoặc sự kiện | `(order_id=1001, status='PAID')` |

Các mối quan hệ quan trọng:

- Một **database cluster** có thể chứa nhiều database.
- Mỗi **database** có nhiều schema, trong đó `public` thường được tạo sẵn.
- Một **schema** có thể chứa nhiều bảng.
- Một **bảng** chứa các hàng; mỗi hàng tuân theo định nghĩa cột và các ràng buộc tương ứng.
- **Roles** được quản lý ở cấp cluster, **không** nằm riêng bên trong một schema.
- Câu SQL thông thường được thực thi trong **một database cụ thể** của kết nối.

**Lưu ý:** bảng trên là phân cấp **logic**. Các tệp lưu trữ vật lý có thể nằm ở những tablespace khác nhau, và một relation lớn có thể dùng nhiều segment file. Không nên suy luận rằng mỗi bảng luôn tương ứng đúng một file duy nhất trên ổ đĩa.

## 3. Máy chủ PostgreSQL: tiến trình phục vụ kết nối

### 3.1. Server không đồng nghĩa máy tính vật lý

Một PostgreSQL **server instance** là dịch vụ PostgreSQL đang chạy với cấu hình, cổng kết nối và khu vực dữ liệu riêng. Nó có thể chạy:

- Trực tiếp trên máy tính cá nhân.
- Trong máy ảo.
- Trong container Docker.
- Trên dịch vụ PostgreSQL do nhà cung cấp cloud quản lý.
- Cùng host với một hay nhiều instance PostgreSQL khác.

Vì thế, câu “một máy chủ” có thể mơ hồ:

- **Host**: máy/VM/container chạy phần mềm.
- **PostgreSQL server instance**: tiến trình dịch vụ PostgreSQL phục vụ một cluster dữ liệu.

Một host có thể chạy hai instance PostgreSQL dùng hai **data directory** và hai **cổng khác nhau**. Ngược lại, một ứng dụng có thể kết nối tới một endpoint cloud mà phía sau có nhiều máy vận hành bởi nhà cung cấp dịch vụ.

Ví dụ mô hình hai instance trên cùng host:

```text
Host: db-lab
  ├── PostgreSQL instance A
  │     port: 5432
  │     data directory: /data/pg_a
  │     databases: postgres, app_db
  └── PostgreSQL instance B
        port: 5433
        data directory: /data/pg_b
        databases: postgres, test_db
```

Đây là đường dẫn minh họa. **Không dùng chung data directory cho hai PostgreSQL instance đang chạy**; mỗi instance cần sở hữu và quản lý vùng dữ liệu của riêng nó.

### 3.2. Server nhận yêu cầu như thế nào?

Khi ứng dụng kết nối PostgreSQL qua driver JDBC, psycopg hoặc công cụ `psql`, nó chọn:

1. **Host** hoặc socket.
2. **Port** của PostgreSQL server (mặc định thường là `5432`).
3. **Database name**.
4. **User/role** để xác thực.
5. Các tham số bảo mật/kết nối như TLS, tùy môi trường.

Ví dụ kết nối bằng `psql`:

```sh
psql -h 127.0.0.1 -p 5432 -U app_user -d app_db
```

Trong PostgreSQL, một kết nối được gắn với một **database** cụ thể. Sau khi kết nối, bạn có thể chọn schema bằng tên đầy đủ hoặc `search_path`, nhưng không chuyển tùy ý sang database khác bằng một lệnh SQL kiểu `USE other_database`.

### 3.3. Kiểm tra instance đang kết nối

Trong phiên đã kết nối:

```sql
SELECT
    current_database() AS database_name,
    current_user AS effective_role,
    session_user AS login_role,
    inet_server_addr() AS server_ip,
    inet_server_port() AS server_port,
    pg_postmaster_start_time() AS server_start_time;
```

Các ý nghĩa:

- `current_database()`: database của connection hiện tại.
- `current_user`: role hiện đang dùng để kiểm tra quyền trong session.
- `session_user`: role đăng nhập ban đầu (có thể khác khi dùng `SET ROLE`).
- `inet_server_addr()` và `inet_server_port()`: địa chỉ/cổng kết nối TCP phía server.
- `pg_postmaster_start_time()`: thời điểm instance PostgreSQL được khởi động.

Nếu kết nối qua Unix-domain socket, các hàm địa chỉ/cổng IP có thể trả `NULL`. Điều đó **không** có nghĩa kết nối thất bại.

Trong `psql`, lệnh client:

```text
\conninfo
```

cho biết thông tin connection, như database, user, host và port đang sử dụng. Đây là **meta-command của psql**, không phải một câu SQL chuẩn gửi trực tiếp qua JDBC.

## 4. Database cluster: tập database được quản lý chung

### 4.1. Cluster được tạo bởi `initdb`

Trong PostgreSQL, **database cluster** là tên gọi kỹ thuật cho tập các database được quản lý bởi một PostgreSQL server instance. Nó thường được khởi tạo bằng công cụ `initdb`, công cụ chuẩn bị **data directory**, các system catalog ban đầu và một số database mặc định.

Ví dụ minh họa cú pháp quản trị:

```sh
initdb -D /path/to/new/data-directory
```

**Không chạy câu lệnh này trên data directory đang chứa dữ liệu thật.** Công cụ này dành cho bước khởi tạo cluster mới, không phải lệnh cần chạy mỗi khi muốn tạo thêm một database.

Một cluster PostgreSQL thông thường có các database ban đầu:

- `postgres`: thường dùng làm database quản trị/bảo trì.
- `template1`: template mặc định được sao chép để tạo database mới.
- `template0`: template cơ sở đặc biệt, hữu ích khi cần tạo database sạch theo quy tắc hỗ trợ.

Những database này đều thuộc cùng một **cluster**; `postgres` không phải “server” hoặc “cluster” riêng chỉ vì trùng tên với sản phẩm.

### 4.2. Cluster có những đối tượng dùng chung nào?

Một số thông tin được quản lý ở phạm vi **toàn cluster**, điển hình:

- **Roles/users**: danh tính và quyền đăng nhập.
- **Tablespaces**: nơi lưu trữ vật lý có thể được sử dụng bởi đối tượng trong các database.
- Danh sách các **database**.
- Một số catalog dùng chung và thông số của instance.

Trong `pg_catalog`, catalog `pg_database` chứa thông tin danh sách database; catalog `pg_roles` giúp xem thông tin role được phép hiển thị.

Ví dụ:

```sql
SELECT datname, datallowconn
FROM pg_database
ORDER BY datname;

SELECT rolname, rolcanlogin
FROM pg_roles
ORDER BY rolname;
```

**Không phải mọi catalog đều dùng chung toàn cluster.** Danh sách schema, bảng và nhiều metadata quan hệ được lưu theo **từng database**. Vì vậy, khi muốn xem bảng trong database khác, bạn thường cần kết nối tới database đó thay vì đọc `pg_class` của connection hiện tại rồi mong thấy toàn bộ cluster.

### 4.3. “Database cluster” khác “cụm HA/replication”

Đây là điểm dễ nhầm nhất:

| Thuật ngữ | Trong PostgreSQL, thường nói về |
|---|---|
| **Database cluster** | Tập database được tạo và quản lý bởi một instance/data directory |
| **HA cluster** | Nhiều máy/instance phối hợp để đạt tính sẵn sàng cao |
| **Primary/standby topology** | Primary nhận ghi, standby nhận và replay WAL theo cấu hình |
| **Cluster orchestrator** | Phần mềm điều phối failover/leader, ví dụ các giải pháp HA tùy môi trường |

Một database cluster theo định nghĩa `initdb` **không bắt buộc có nhiều máy**. Ngược lại, một hệ thống HA có thể gồm nhiều PostgreSQL instances, mỗi instance có data directory riêng; những instance đó phối hợp sao chép hoặc chuyển vai trò nhưng không dùng chung một data directory.

Khi tài liệu ghi “deploy a PostgreSQL cluster”, cần đọc ngữ cảnh: họ đang nói **khởi tạo data directory** hay **triển khai HA nhiều node**?

## 5. Database: ranh giới kết nối và không gian đối tượng

### 5.1. Database nằm bên trong một cluster

Một cluster có thể chứa các database:

```text
PostgreSQL database cluster
├── postgres
├── billing_db
├── crm_db
└── analytics_db
```

Mỗi database có tập schema, bảng, view, function và dữ liệu riêng. Hai database khác nhau có thể cùng có schema `public` và bảng `public.users` nhưng đó là **hai đối tượng khác nhau**.

Ví dụ:

```text
billing_db.public.users     -- bảng trong billing_db
crm_db.public.users         -- bảng trong crm_db
```

Tài khoản `app_user` có thể là role **dùng chung ở cấp cluster**, nhưng quyền `CONNECT` và quyền trên các đối tượng trong từng database là những vấn đề riêng. Việc một role truy cập được `billing_db` không có nghĩa nó tự được đọc mọi bảng trong `crm_db`.

### 5.2. Tạo database: quyền và quy tắc

Trong một kết nối có quyền phù hợp, ví dụ role có thuộc tính `CREATEDB`:

```sql
CREATE DATABASE pg_intro_24;
```

Lệnh `CREATE DATABASE` tạo **một database mới trong cluster hiện có**. Nó không tạo PostgreSQL instance mới, không mở cổng mới và cũng không khởi tạo lại cluster.

Một lưu ý kỹ thuật: `CREATE DATABASE` **không chạy bên trong một transaction block** như:

```sql
-- Không hợp lệ:
BEGIN;
CREATE DATABASE pg_intro_24;
COMMIT;
```

Nếu không có quyền `CREATEDB` hoặc tương đương, người học cần dùng database lab đã được quản trị viên cấp sẵn. Không tự ý xin/sử dụng superuser chỉ để làm bài thực hành tạo bảng.

### 5.3. Chọn database của một connection

Dùng `psql` để kết nối trực tiếp:

```sh
psql -h localhost -p 5432 -U lab_user -d pg_intro_24
```

Trong phiên `psql` đang mở, có thể **ngắt và kết nối lại** sang database khác bằng meta-command:

```text
\connect pg_intro_24
```

hoặc dạng ngắn:

```text
\c pg_intro_24
```

Đây là lệnh của **psql client**, không phải câu SQL chạy bên trong server. PostgreSQL **không hỗ trợ** câu lệnh MySQL-style:

```sql
-- Không phải cú pháp PostgreSQL:
USE pg_intro_24;
```

Nếu dùng Java/JDBC, việc chọn database được đặt trong JDBC URL hoặc thông số kết nối, ví dụ:

```text
jdbc:postgresql://127.0.0.1:5432/pg_intro_24
```

Muốn thao tác với database khác, ứng dụng thông thường cần mở **connection khác** trỏ tới database đó.

### 5.4. Truy vấn trực tiếp giữa hai database có được không?

Trong một connection PostgreSQL thông thường, bạn có thể truy vấn nhiều **schema cùng database** bằng tên hai thành phần `schema.table`, nhưng không thể thực hiện join hai bảng nằm ở hai database khác nhau đơn giản bằng cách viết:

```sql
-- Không dùng cú pháp này để đọc database khác:
SELECT *
FROM other_database.public.customers;
```

PostgreSQL không cung cấp truy vấn xuyên database kiểu này theo cơ chế SQL thông thường; nếu tên database chỉ sang database khác, bạn có thể gặp thông báo kiểu **cross-database references are not implemented**.

Nếu thật sự cần giao tiếp giữa database:

- Kết nối riêng tới từng database ở tầng ứng dụng.
- Dùng các công cụ/extension phù hợp như `postgres_fdw` hoặc `dblink` nếu hạ tầng cho phép.
- Đồng bộ dữ liệu qua ETL, message/event hoặc luồng tích hợp được thiết kế rõ.

Những lựa chọn này có chi phí, quyền và ngữ nghĩa transaction riêng. Đừng chọn tách database chỉ vì muốn có hai nhóm bảng nếu nghiệp vụ cần join liên tục, giao dịch chặt chẽ giữa chúng.

## 6. Schema: namespace bên trong một database

### 6.1. Schema không phải database

**Schema** là một **không gian tên** bên trong database. Nó giúp gom nhóm và đặt tên cho các đối tượng:

```text
Database: pg_intro_24
├── Schema: public
│   ├── Table: settings
│   └── View: current_settings
├── Schema: sales
│   ├── Table: customers
│   ├── Table: orders
│   └── Sequence: order_seq
└── Schema: audit
    └── Table: events
```

Lưu ý: sequence, view, function và kiểu dữ liệu cũng là đối tượng có thể thuộc schema. Schema không phải một “thư mục dữ liệu” đơn giản chỉ chứa bảng.

Hai schema cùng một database có thể chứa bảng trùng tên:

```text
sales.events
audit.events
```

Chúng không phải cùng bảng. Câu:

```sql
SELECT * FROM sales.events;
```

chỉ tới đối tượng trong schema `sales` của database hiện tại.

### 6.2. Tạo schema

Sau khi kết nối tới database lab, có thể chạy:

```sql
CREATE SCHEMA IF NOT EXISTS sales;
CREATE SCHEMA IF NOT EXISTS audit;
```

Tạo schema **không** tạo database mới. Lệnh này yêu cầu quyền `CREATE` trên database hoặc quyền quản trị/ownership phù hợp. Nếu chỉ được cấp quyền sử dụng schema có sẵn, hãy dùng schema do người quản trị tạo, thay vì cố nâng quyền.

Liệt kê schema qua SQL:

```sql
SELECT schema_name
FROM information_schema.schemata
ORDER BY schema_name;
```

Hoặc trong `psql`:

```text
\dn
```

Kết quả của `information_schema` có thể phụ thuộc quyền của role đang kết nối. Các schema hệ thống như `pg_catalog`, `information_schema` và `pg_toast` có mục đích khác schema ứng dụng; không nên tạo bảng nghiệp vụ trong đó.

### 6.3. Schema `public`

Khi tạo một database PostgreSQL thông thường, schema `public` thường đã tồn tại, nên câu:

```sql
CREATE TABLE customers (
    customer_id bigint PRIMARY KEY
);
```

có thể tạo bảng `public.customers` **nếu search path hiện tại trỏ đến `public` là schema hợp lệ để tạo đối tượng**.

Tuy nhiên, không nên mặc định mọi user đều có quyền tạo bảng ở `public`. Trong các database mới tạo bởi PostgreSQL 15 trở lên, quyền `CREATE` trên `public` mặc định được hạn chế hơn so với nhiều cài đặt PostgreSQL cũ; cấu hình đã nâng cấp hoặc được quản trị viên điều chỉnh có thể khác.

Khi dạy hoặc viết migration, sử dụng **schema tường minh** là cách rõ ràng hơn:

```sql
CREATE TABLE sales.customers (
    customer_id bigint PRIMARY KEY
);
```

Cách này tránh phụ thuộc vào `search_path` đang được cấu hình.

## 7. Tên đủ điều kiện và cơ chế `search_path`

### 7.1. `schema.table` có ý nghĩa gì?

Trong PostgreSQL, tên đối tượng theo schema thường viết:

```text
schema_name.table_name
```

Ví dụ:

```sql
SELECT * FROM sales.customers;
SELECT * FROM audit.events;
```

Tên hai thành phần nói rõ **schema** và **bảng** trong database hiện tại. PostgreSQL có cú pháp định danh nhiều thành phần trong một số ngữ cảnh, nhưng đó **không** phải cơ chế truy vấn xuyên database tùy ý như nhiều người mới học suy luận.

### 7.2. Khi bỏ schema, PostgreSQL tìm bảng ở đâu?

Nếu viết:

```sql
SELECT * FROM customers;
```

PostgreSQL tìm đối tượng bằng **`search_path`**. Xem cấu hình:

```sql
SHOW search_path;

SELECT current_schema();

SELECT current_schemas(true);
```

Một giá trị mặc định thường gặp là:

```text
"$user", public
```

Ý nghĩa: PostgreSQL thử schema có tên trùng role hiện tại nếu schema đó tồn tại và có thể sử dụng, rồi đến `public`. Các schema hệ thống như `pg_catalog` có quy tắc tra cứu đặc biệt và có thể xuất hiện trong danh sách schema hiệu lực ngay cả khi không được khai báo tường minh.

Nếu database có:

```text
sales.customers
public.customers
```

thì `SELECT * FROM customers` có thể trỏ tới **bảng khác nhau** nếu `search_path` thay đổi.

Ví dụ điều chỉnh trong session lab:

```sql
SET search_path TO sales, public;

SELECT * FROM customers;       -- ưu tiên sales.customers
SELECT * FROM public.customers; -- luôn chỉ rõ public
```

Chú thích trên giả sử hai bảng có tồn tại và role có quyền tương ứng.

### 7.3. Rủi ro của `search_path`

`search_path` không chỉ ảnh hưởng tên bảng mà còn có thể ảnh hưởng việc resolve một số function, type và operator. Nếu đưa một schema mà user không đáng tin cậy có quyền tạo object vào đầu search path, có thể phát sinh rủi ro chọn nhầm đối tượng.

Một số thực hành:

- Trong migration hoặc tác vụ nhạy cảm, ưu tiên tên đối tượng tường minh `schema.table`.
- Thiết kế quyền `CREATE` trên schema phù hợp; không cho role không tin cậy tạo object trong schema được các ứng dụng quan trọng ưu tiên tra cứu.
- Kiểm tra `SHOW search_path` trong **chính connection của ứng dụng**, không chỉ connection của DBA.
- Tránh dựa vào việc chỉ cần tên bảng không có schema để bảo đảm ứng dụng đang đọc đúng dữ liệu.

### 7.4. Schema không được lồng schema

Cấu trúc:

```text
database -> schema -> table
```

không tương đương cấu trúc file:

```text
database -> schema -> schema -> table
```

Trong PostgreSQL, schema là namespace ở **một cấp bên trong database**; không có schema con trực tiếp theo cách thư mục con trong filesystem.

Nếu cần phân nhóm nhiều lớp, dùng cách đặt tên, nhiều schema song song, module ứng dụng hoặc các mô hình quan hệ phù hợp, thay vì giả định `sales.eu.orders` biểu thị schema `eu` nằm trong `sales`.

## 8. Bảng: quan hệ có cột, hàng và ràng buộc

### 8.1. Table là gì?

Một **table** chứa các hàng (*rows*) theo cấu trúc cột đã định nghĩa. Ví dụ bảng khách hàng:

| customer_id | full_name | email |
|---:|---|---|
| 1 | An Nguyễn | an@example.test |
| 2 | Bình Trần | binh@example.test |

Khái niệm:

- **Tên bảng**: `customers`.
- **Schema chứa bảng**: ví dụ `sales`.
- **Cột**: `customer_id`, `full_name`, `email`.
- **Kiểu dữ liệu**: `bigint`, `text`, …
- **Ràng buộc**: `PRIMARY KEY`, `NOT NULL`, `UNIQUE`, `CHECK`, `FOREIGN KEY`.
- **Hàng**: một bộ giá trị cho các cột, ví dụ khách hàng có `customer_id = 1`.

Trong PostgreSQL, nhiều đối tượng được gọi chung là **relation** trong system catalog, bao gồm table, view, materialized view, sequence và một số dạng relation khác. **Không phải mọi relation đều là bảng lưu hàng nghiệp vụ theo cách của ordinary table**.

### 8.2. Tạo bảng có khóa chính

Trong một database lab đã có schema `sales`:

```sql
CREATE TABLE sales.customers (
    customer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name text NOT NULL,
    email text NOT NULL UNIQUE
);
```

Giải thích:

- `GENERATED ALWAYS AS IDENTITY`: PostgreSQL quản lý việc sinh giá trị định danh khi chèn hàng theo cơ chế identity.
- `PRIMARY KEY`: mỗi hàng phải có khóa chính khác nhau và không NULL.
- `NOT NULL`: cột bắt buộc có giá trị không NULL.
- `UNIQUE`: email không được trùng theo quy tắc so sánh/constraint của cột và cấu hình liên quan.

`bigint` là kiểu số nguyên lớn; `text` chứa văn bản biến độ dài. Không sử dụng `customer_id` như một “vị trí hàng trên ổ đĩa”; nó là **định danh logic** của dữ liệu.

### 8.3. Tạo bảng đơn hàng và quan hệ giữa hai bảng

```sql
CREATE TABLE sales.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL,
    total_amount numeric(12, 2) NOT NULL CHECK (total_amount >= 0),
    status text NOT NULL DEFAULT 'NEW',
    placed_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES sales.customers(customer_id)
);
```

Ở đây:

- `orders` và `customers` là **hai bảng trong cùng schema**.
- Cột `customer_id` ở `orders` tham chiếu khóa chính của `customers`.
- `numeric(12,2)` phù hợp cho ví dụ số tiền thập phân hai chữ số.
- `timestamptz` biểu diễn thời điểm có ngữ nghĩa múi giờ trong PostgreSQL; cách hiển thị chịu ảnh hưởng timezone của session.
- `CHECK (total_amount >= 0)` ngăn các giá trị âm theo quy tắc constraint; nếu nghiệp vụ cần hoàn tiền âm, cần mô hình riêng cho thao tác đó.

Một **database** có thể có hàng chục schema, một **schema** có thể có hàng trăm bảng, và một **table** có thể chứa hàng triệu hàng. Số lượng này không quyết định trực tiếp nên chia schema/database thế nào; lựa chọn cần dựa vào quyền, vòng đời triển khai, mức độ liên quan dữ liệu và khả năng vận hành.

## 9. Hàng: đơn vị dữ liệu logic, không phải một file nhỏ

### 9.1. Thêm hàng vào bảng

Giả sử đã tạo `sales.customers`:

```sql
INSERT INTO sales.customers (full_name, email)
VALUES
    ('An Nguyễn', 'an@example.test'),
    ('Bình Trần', 'binh@example.test')
RETURNING customer_id, full_name, email;
```

Mỗi bộ giá trị trong `VALUES` tạo một **hàng logic**. `RETURNING` cho phép trả về dữ liệu của những hàng vừa chèn, rất hữu ích khi khóa chính được database sinh ra.

Sau đó tạo đơn hàng, tìm khóa khách theo email:

```sql
INSERT INTO sales.orders (customer_id, total_amount, status)
SELECT customer_id, 150000.00, 'PAID'
FROM sales.customers
WHERE email = 'an@example.test'
RETURNING order_id, customer_id, total_amount, status;
```

Câu `SELECT` bên trong phải khớp đúng khách hàng dự định. Vì `email` có ràng buộc `UNIQUE`, truy vấn tìm theo email hợp lệ sẽ có tối đa một hàng trong ví dụ này.

Đọc dữ liệu:

```sql
SELECT customer_id, full_name, email
FROM sales.customers
ORDER BY customer_id;

SELECT order_id, customer_id, total_amount
FROM sales.orders
ORDER BY order_id;
```

### 9.2. Một hàng không có “số thứ tự tự nhiên”

Khi chạy:

```sql
SELECT * FROM sales.customers;
```

PostgreSQL **không cam kết** thứ tự trả về nếu không có `ORDER BY`. Dữ liệu có thể được truy xuất theo sequential scan, index scan hoặc kế hoạch khác; thứ tự có thể đổi sau `UPDATE`, `VACUUM`, thay chỉ mục hay thay đổi kế hoạch tối ưu.

Nếu màn hình yêu cầu khách theo ID tăng dần, hãy ghi rõ:

```sql
SELECT customer_id, full_name
FROM sales.customers
ORDER BY customer_id;
```

`PRIMARY KEY` bảo đảm tính duy nhất, **không** có nghĩa mọi câu `SELECT` tự động sắp theo khóa chính.

### 9.3. UPDATE/DELETE thay đổi các hàng nào?

```sql
UPDATE sales.customers
SET full_name = 'An Nguyễn (mới)'
WHERE email = 'an@example.test'
RETURNING customer_id, full_name;

DELETE FROM sales.orders
WHERE status = 'CANCELLED'
RETURNING order_id;
```

`WHERE` quyết định những hàng logic nào cần tác động; `RETURNING` giúp ứng dụng biết những hàng thực sự bị thay đổi/xóa. Trong hệ thống thật, lệnh `DELETE` có thể bị ràng buộc khóa ngoại chặn, hoặc cần cách lưu trạng thái thay vì xóa vật lý theo nghiệp vụ.

Đừng viết `UPDATE sales.customers SET ...` hoặc `DELETE FROM sales.orders` mà quên `WHERE` nếu chỉ muốn xử lý một vài hàng: việc đó có thể ảnh hưởng **toàn bộ bảng**.

### 9.4. Row và tuple trong PostgreSQL/MVCC

Ở mức SQL, **row** là một bản ghi logic. Ở mức triển khai PostgreSQL, các phiên bản vật lý của row thường được gọi là **tuple**. PostgreSQL dùng **MVCC** (*Multi-Version Concurrency Control*) để cho phép nhiều transaction đọc/ghi đồng thời theo mức cô lập và trạng thái snapshot.

Ví dụ:

1. Transaction A đang đọc một snapshot có tên khách là `An Nguyễn`.
2. Transaction B cập nhật tên và commit.
3. A có thể vẫn thấy phiên bản cũ tùy mức cô lập và snapshot đọc.
4. Một transaction mới có thể thấy phiên bản sau cập nhật.

Về mặt vật lý, `UPDATE` có thể tạo **phiên bản tuple mới** thay vì sửa đè dữ liệu cũ tại chỗ. Các phiên bản không còn cần thiết sẽ được dọn dẹp theo cơ chế vacuum và các điều kiện liên quan.

Vì vậy:

- **Một hàng logic** không phải luôn tương ứng duy nhất một vị trí vật lý cố định.
- Cột hệ thống `ctid` định vị một phiên bản tuple vật lý ở thời điểm truy vấn, **không phải khóa nghiệp vụ ổn định**; `UPDATE` và thao tác bảo trì có thể làm vị trí thay đổi.
- Để tham chiếu hàng giữa các bảng hoặc từ ứng dụng, dùng **primary key/unique key** phù hợp, không dùng `ctid` làm định danh bền vững.

## 10. Phân quyền đi theo những cấp nào?

Phân biệt các cấp còn giúp tránh hai lỗi: **cấp quyền quá rộng** hoặc **tưởng đã có quyền nhưng vẫn truy vấn lỗi**.

| Cấp đối tượng | Quyền/thuộc tính điển hình | Ý nghĩa |
|---|---|---|
| Server/cluster | Role có `LOGIN`, `CREATEDB`, `CREATEROLE`… | Ai được đăng nhập hoặc quản lý đối tượng cấp cao |
| Database | `CONNECT`, `CREATE`, `TEMPORARY` | Có thể kết nối và tạo schema/đối tượng phù hợp |
| Schema | `USAGE`, `CREATE` | Có thể phân giải/truy cập đối tượng trong schema hoặc tạo đối tượng |
| Table | `SELECT`, `INSERT`, `UPDATE`, `DELETE`… | Được đọc/ghi những hàng của bảng theo chính sách |
| Column | Một số quyền ở mức cột | Giới hạn thao tác trên các cột cụ thể |
| Row | Chính sách **Row-Level Security (RLS)** nếu được thiết kế và bật | Hạn chế những hàng một role có thể thấy/sửa |

Ví dụ một role chỉ đọc báo cáo có thể cần:

```sql
-- Được thực thi bởi chủ sở hữu/quản trị viên có quyền phù hợp.
GRANT CONNECT ON DATABASE pg_intro_24 TO app_reader;
GRANT USAGE ON SCHEMA sales TO app_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA sales TO app_reader;
```

Đây là ví dụ khi role `app_reader` đã được tạo. Quyền `CONNECT` chỉ cho phép vào database, **không tự cấp quyền đọc tất cả bảng**; quyền `USAGE` trên schema giúp truy cập các object bên trong theo tên, nhưng **không tự cấp quyền SELECT từng bảng**.

Lưu ý:

- Role là đối tượng cấp **cluster**, nhưng quyền trên bảng thuộc database cụ thể.
- `GRANT SELECT ON ALL TABLES IN SCHEMA sales` cấp cho **các bảng hiện có** trong schema tại thời điểm đó; bảng tạo **sau này** có thể cần cấu hình `ALTER DEFAULT PRIVILEGES` đúng chủ thể tạo bảng.
- RLS là lớp kiểm soát chi tiết hơn ở **mức hàng**; không phải PostgreSQL tự chia mỗi hàng thành một schema.
- Quyền của object, ownership, role membership và một số quyền mặc định có thể ảnh hưởng kết quả thực tế; hãy kiểm tra bằng chính account ứng dụng.

### 10.1. Vì sao phân tách schema có ích?

Trong một database, tạo các schema `sales`, `audit` và `reporting` có thể giúp:

- Tách tên object và tránh xung đột.
- Cấp quyền theo module.
- Phân vùng trách nhiệm migration/ownership.
- Tổ chức những bảng liên quan mà vẫn **join và transaction thuận tiện** trong cùng database.

Tuy vậy, **schema không phải một database độc lập về tài nguyên**. Các schema trong cùng database vẫn chia sẻ instance, database-level settings, WAL/transaction infrastructure và nhiều tài nguyên vận hành. Nếu cần tách riêng chu kỳ nâng cấp, chính sách kết nối hoặc mức cô lập vận hành mạnh hơn, cần đánh giá database hoặc instance riêng.

## 11. Thực hành tổng hợp từ database xuống hàng

Phần thực hành sau sử dụng một database lab riêng, không cần quyền superuser để thao tác hàng/bảng nếu role đã được cấp đủ quyền.

### Bước 1: Kết nối đúng database

Nếu có quyền `CREATEDB` trong môi trường test, người quản trị hoặc role được phép có thể tạo:

```sql
CREATE DATABASE pg_intro_24;
```

Nếu không có quyền, sử dụng database test được cấp sẵn và thay `pg_intro_24` trong các lệnh phù hợp. Không chạy `CREATE DATABASE` trong `BEGIN ... COMMIT`.

Kết nối bằng `psql`:

```text
\connect pg_intro_24
```

Xác nhận:

```sql
SELECT current_database(), current_user;
```

Mong đợi `current_database()` phản ánh database vừa kết nối.

### Bước 2: Tạo schema riêng

```sql
CREATE SCHEMA IF NOT EXISTS lab24;
```

Câu này chỉ tạo một namespace `lab24` **bên trong database hiện tại**, không tạo database thứ hai.

Trong `psql`:

```text
\dn
```

### Bước 3: Tạo hai bảng trong schema

```sql
CREATE TABLE lab24.customers (
    customer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name text NOT NULL,
    email text NOT NULL UNIQUE
);

CREATE TABLE lab24.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL
        REFERENCES lab24.customers(customer_id),
    amount numeric(12, 2) NOT NULL CHECK (amount >= 0),
    status text NOT NULL DEFAULT 'NEW'
);
```

Kiểm tra schema và bảng:

```text
\dt lab24.*
\d lab24.customers
\d lab24.orders
```

`\dt` và `\d` là **meta-command của psql**. Dùng câu truy vấn system catalog hoặc `information_schema` nếu kết nối qua driver/ứng dụng không hỗ trợ chúng.

### Bước 4: Thêm hàng

```sql
INSERT INTO lab24.customers (full_name, email)
VALUES
    ('An', 'an@example.test'),
    ('Bình', 'binh@example.test')
RETURNING customer_id, full_name;

INSERT INTO lab24.orders (customer_id, amount, status)
SELECT customer_id, 150000.00, 'PAID'
FROM lab24.customers
WHERE email = 'an@example.test'
RETURNING order_id, customer_id, amount, status;
```

Kết quả: hai hàng khách hàng và một hàng đơn hàng. Các giá trị identity do PostgreSQL cấp có thể khác ví dụ bảng trước nếu đã thao tác trong database này; không nên mặc định ID luôn bắt đầu bằng 1 sau những lần thử trước.

### Bước 5: Đọc theo tên có schema

```sql
SELECT customer_id, full_name
FROM lab24.customers
ORDER BY customer_id;

SELECT
    o.order_id,
    c.full_name,
    o.amount,
    o.status
FROM lab24.orders AS o
JOIN lab24.customers AS c
  ON c.customer_id = o.customer_id
ORDER BY o.order_id;
```

Trong cùng database, hai bảng có schema được chỉ định rõ; PostgreSQL có thể thực hiện `JOIN` bình thường.

### Bước 6: Xem tác động của `search_path`

```sql
SHOW search_path;

SET search_path TO lab24, public;

SELECT * FROM customers ORDER BY customer_id;

SELECT * FROM lab24.customers ORDER BY customer_id;
```

Nếu `lab24` tồn tại và role có quyền, hai câu `SELECT` có thể trả cùng hàng vì schema `lab24` đang là nơi tìm tên trước tiên. Tuy nhiên, chỉ câu thứ hai là **độc lập với search path**.

Khôi phục cài đặt search path của session:

```sql
RESET search_path;
```

`RESET` ở đây chỉ đưa **cấu hình session `search_path`** về giá trị mặc định theo nguồn thiết lập phù hợp, **không** xóa schema hay dữ liệu.

### Bước 7: Xem cấu trúc từ system catalog

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    c.relkind
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE n.nspname = 'lab24'
  AND c.relkind IN ('r', 'p')
ORDER BY c.relname;
```

Ở đây:

- `pg_namespace` lưu thông tin schema của **database hiện tại**.
- `pg_class` lưu metadata về nhiều loại relation trong **database hiện tại**.
- `relkind = 'r'` là ordinary table; `'p'` là partitioned table.
- Những index, sequence, view cũng có entry trong `pg_class` nhưng mang relkind khác; câu truy vấn cố ý chỉ hiển thị hai loại bảng.

Bên cạnh đó, có thể dùng giao diện chuẩn:

```sql
SELECT table_schema, table_name, table_type
FROM information_schema.tables
WHERE table_schema = 'lab24'
ORDER BY table_name;
```

Kết quả `information_schema` được lọc theo ngữ nghĩa quyền và loại đối tượng; nó phù hợp cho nhiều công việc khám phá metadata ứng dụng, còn system catalog PostgreSQL chứa chi tiết nội bộ rộng hơn.

## 12. Cùng tên nhưng khác cấp: những ví dụ rất dễ nhầm

### Tình huống A: Hai database đều có schema `public`

```text
Database A:
  public.users

Database B:
  public.users
```

Hai bảng này khác nhau. Khi connection trỏ tới A, câu `SELECT * FROM public.users` đọc bảng trong **A**. Nó không tự tìm đến B.

### Tình huống B: Một database có hai schema chứa bảng cùng tên

```text
Database: app_db
  sales.events
  audit.events
```

Bạn có thể truy vấn rõ ràng:

```sql
SELECT * FROM sales.events;
SELECT * FROM audit.events;
```

Hai bảng trong cùng database nhưng ở hai namespace khác nhau. Nếu viết `SELECT * FROM events`, kết quả phụ thuộc `search_path`.

### Tình huống C: Một role được tạo ở cluster, không nằm ở schema

Role `app_user` có thể đăng nhập vào nhiều database **nếu được phép CONNECT**, nhưng các bảng của từng database không tự trở thành dữ liệu chung của role. Role là danh tính và tập quyền, không phải nơi chứa hàng.

### Tình huống D: Hai PostgreSQL instances cùng host

Instance A đang nghe cổng 5432, instance B ở cổng 5433. Cả hai có thể cùng có database `app_db` và schema `public`, nhưng đó vẫn là những đối tượng thuộc **hai database clusters độc lập**.

### Tình huống E: Bảng có nhiều hàng nhưng chỉ một định nghĩa cột

Bảng `sales.customers` có một định nghĩa `customer_id, full_name, email`, nhưng mỗi `INSERT` tạo thêm row. Không “tạo schema mới” hay “tạo bảng mới” cho từng khách hàng.

## 13. Phân biệt cấp logic với cấu trúc vật lý

Sơ đồ phân cấp **database → schema → table → row** là góc nhìn logic để tổ chức dữ liệu và SQL. PostgreSQL còn có cấu trúc vật lý:

- **Data directory**: vùng dữ liệu của database cluster.
- **Tablespace**: vị trí lưu dữ liệu có thể được cấu hình.
- **Relation files/segments**: cách PostgreSQL lưu bảng/index trên ổ đĩa theo quy tắc nội bộ.
- **Pages**: đơn vị trang lưu trữ, thường có kích thước mặc định 8 KiB.
- **Tuples**: các phiên bản bản ghi ở mức lưu trữ.
- **WAL** (*Write-Ahead Log*): thông tin hỗ trợ độ bền và phục hồi khi có crash, đồng thời phục vụ một số cơ chế replication.

Không thể coi **schema** là một thư mục OS có cùng tên, hay mỗi **row** là một file riêng. Một bảng có thể lớn hơn một segment file, nằm trong tablespace được chỉ định và có nhiều index tạo thêm cấu trúc lưu trữ.

Nếu học viên chạy:

```sql
SELECT pg_relation_size('lab24.customers'::regclass);
```

thì hàm trả kích thước lưu trữ của relation được chỉ định theo ngữ nghĩa PostgreSQL; nó không đồng nghĩa đếm số hàng. Để đếm hàng theo snapshot hiện tại, dùng:

```sql
SELECT COUNT(*) AS customer_count
FROM lab24.customers;
```

Số hàng và kích thước byte là hai đại lượng khác nhau.

## 14. Khi nào chọn nhiều database, khi nào nhiều schema?

Không có quy tắc “một ứng dụng phải dùng một database” đúng cho mọi hệ thống. Một số câu hỏi định hướng:

| Tiêu chí | Nhiều schema trong cùng database | Nhiều database trong cùng cluster |
|---|---|---|
| Truy vấn `JOIN` giữa các module | Thuận tiện với `schema.table` | Không join trực tiếp bằng tên ba thành phần; cần tích hợp riêng |
| Transaction tác động nhiều bảng | Có thể thuộc cùng transaction trong một connection | Không có transaction SQL thông thường tự bao phủ hai DB qua một connection |
| Phân tách namespace và quyền object | Tốt cho module cùng hệ thống | Mạnh hơn ở ranh giới kết nối/database |
| Vòng đời schema migration | Có thể triển khai theo module nhưng vẫn chung DB | Tách đối tượng DB rõ hơn; cần nhiều connection/migration target |
| Roles, server config, tài nguyên instance | Vẫn dùng chung cluster | Cũng vẫn dùng chung cluster |
| Cần nâng cấp server độc lập | Không giải quyết | Không giải quyết nếu các DB vẫn ở cùng instance/cluster |
| Muốn tách hạ tầng vận hành mạnh | Hạn chế | Nên xem xét **instance/cluster riêng**, không chỉ database riêng |

Một cách tiếp cận thường hợp lý:

- Dùng **nhiều schema** khi các nhóm bảng liên quan chặt, cần join/transaction trực tiếp, nhưng muốn phân tách tên và quyền theo module.
- Dùng **nhiều database** khi ứng dụng/khối dữ liệu có ranh giới kết nối và quyền vận hành riêng, ít yêu cầu join trực tiếp.
- Dùng **PostgreSQL instance riêng** khi cần giới hạn tài nguyên, chính sách upgrade, quản trị, bảo mật hoặc vòng đời vận hành độc lập rõ ràng hơn.

Việc tạo hai database trên cùng instance **không** tự tách CPU, RAM, WAL, cấu hình phần cứng hay tình trạng hỏng của instance như hai server độc lập.

## 15. Một số lỗi thường gặp và cách xác định đúng cấp

### 15.1. `relation "customers" does not exist`

Nguyên nhân có thể là:

- Chưa tạo bảng.
- Đang kết nối **sai database**.
- Bảng nằm trong **schema khác**.
- `search_path` không chứa schema cần tìm.
- Tên object có phân biệt chữ hoa/thường do được tạo bằng dấu ngoặc kép.

Cách chẩn đoán:

```sql
SELECT current_database(), current_schema();
SHOW search_path;

SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_name ILIKE 'customers';
```

Nếu thấy bảng trong `sales`, hãy dùng `sales.customers` hoặc thiết lập search path phù hợp.

### 15.2. `permission denied for schema sales`

Account có thể đã được phép `CONNECT` vào database và được cấp `SELECT` trên bảng, nhưng chưa có `USAGE` trên schema. Cần kiểm tra quyền **từng cấp**, thay vì chỉ `GRANT SELECT ON TABLE` rồi bỏ qua schema.

### 15.3. `database "x" does not exist`

Kết nối đang yêu cầu một database không tồn tại trong cluster **được server endpoint đó phục vụ** hoặc tên bị sai. Một database cùng tên trên server/port khác không tự có mặt trong instance hiện tại.

### 15.4. Không dùng được `USE db_name`

`USE` là cú pháp quen thuộc ở một số DBMS khác nhưng không phải lệnh chuyển database của PostgreSQL. Dùng `\connect` trong `psql` hoặc tạo connection mới trỏ tới database cần dùng.

### 15.5. Phân biệt chữ hoa/thường trong tên đối tượng

PostgreSQL chuyển **identifier không trích dẫn** về chữ thường. Ví dụ:

```sql
CREATE TABLE sales.CustomerProfiles (
    id bigint PRIMARY KEY
);
```

Nếu schema tồn tại, tên thực tế thông thường sẽ là `sales.customerprofiles`.

Trong khi đó:

```sql
CREATE TABLE sales."CustomerProfiles" (
    id bigint PRIMARY KEY
);
```

tạo identifier có phân biệt chữ hoa/thường; những truy vấn sau phải dùng dấu ngoặc kép và đúng cách viết. Để giảm lỗi, nên dùng tên lowercase, phân tách bằng underscore, ví dụ `customer_profiles`.

### 15.6. Tưởng `PRIMARY KEY` đồng nghĩa hàng có thứ tự

Primary key là ràng buộc duy nhất/không NULL và thường có index hỗ trợ. PostgreSQL **không cam kết thứ tự hiển thị** nếu không có `ORDER BY`.

### 15.7. Nhầm row logic với physical tuple

Một hàng có `id = 42` vẫn là cùng thực thể nghiệp vụ sau `UPDATE`, nhưng PostgreSQL có thể tạo tuple version khác về mặt vật lý. Không dùng `ctid` làm định danh lâu dài của dữ liệu.

### 15.8. Nhầm PostgreSQL database cluster với HA cluster

Một directory tạo bằng `initdb` đã được gọi là database cluster dù có đúng **một instance**. Tính sẵn sàng cao cần thêm cấu hình standby, replication, failover, backup và các cơ chế vận hành tương ứng.

## 16. Bài tập tự luyện

### Bài 1. Xác định cấp đối tượng

Cho đường dẫn logic:

```text
PostgreSQL server: db.internal:5432
Database: shop_db
Schema: inventory
Table: products
Row: product_id = 501
```

**Câu hỏi:** `inventory` là gì? `products` là gì? Giá trị `501` định danh cấp nào?

**Lời giải:** `inventory` là schema bên trong database `shop_db`; `products` là table; `product_id = 501` là giá trị cột dùng để xác định một row logic (giả sử `product_id` là khóa chính hoặc khóa duy nhất). Cả ba không phải ba database khác nhau.

### Bài 2. Hai bảng cùng tên có được không?

Trong `shop_db`, muốn có `sales.events` và `audit.events`.

**Lời giải:** được, vì schema là namespace. Hai đối tượng có tên đầy đủ khác nhau. Dùng:

```sql
SELECT * FROM sales.events;
SELECT * FROM audit.events;
```

Chỉ khi role có quyền trên các schema/bảng và đối tượng đã tồn tại, các truy vấn mới chạy thành công.

### Bài 3. Vì sao kết nối lại cần database name?

Một ứng dụng kết nối `db.internal:5432` với user `app_user` nhưng quên cung cấp database.

**Lời giải:** connection PostgreSQL phải gắn với **một database**. Driver/client có thể áp dụng giá trị mặc định cho tên database dựa trên user hoặc cấu hình, nhưng không nên dựa vào đó. Khai báo database tường minh trong URL/connection parameters rồi xác nhận bằng `current_database()`.

### Bài 4. `search_path` có thể đổi bảng truy vấn không?

Database có:

```text
public.settings
tenant_a.settings
```

Nếu `search_path = tenant_a, public`, `SELECT * FROM settings` ưu tiên bảng nào?

**Lời giải:** ưu tiên `tenant_a.settings` nếu schema và đối tượng hợp lệ theo quyền/trạng thái session. Dùng `public.settings` khi muốn xác định chính xác bảng `public` bất kể search path.

### Bài 5. Vì sao hai database không tự join?

Có `billing_db.public.invoices` và `crm_db.public.customers` trong cùng cluster. Một lập trình viên muốn join bằng cú pháp `billing_db.public.invoices JOIN crm_db.public.customers` trong một connection.

**Lời giải:** kết nối PostgreSQL thông thường làm việc trong **một database**. Dùng tên đủ điều kiện schema không biến nó thành cross-database query. Cần thiết kế kết nối/integration hoặc công cụ như `postgres_fdw`/`dblink` nếu thực sự cần.

### Bài 6. Vai trò của primary key là gì?

Bảng `customers` có hai hàng với tên giống nhau. Khóa chính là `customer_id`.

**Lời giải:** hai người có thể trùng tên nhưng phải có `customer_id` khác nhau. Primary key xác định hàng ở mức logic, hỗ trợ tham chiếu bằng foreign key; nó không quyết định thứ tự output của mọi câu `SELECT`.

### Bài 7. Database cluster có bao nhiêu máy?

Một quản trị viên chạy `initdb` trên một VM, khởi động một PostgreSQL instance và tạo ba database.

**Lời giải:** đó đã là **một PostgreSQL database cluster** theo thuật ngữ PostgreSQL, dù chỉ có một máy và chưa cấu hình HA/standby. Ba database không phải ba cluster.

### Bài 8. Vì sao account không đọc được bảng?

Admin cấp `CONNECT` cho database và `SELECT` trên `sales.orders` nhưng không cấp `USAGE` trên schema `sales`.

**Lời giải:** quyền đi theo nhiều cấp. Account cần được phép sử dụng namespace schema cùng quyền truy cập bảng thích hợp. Cấp `CONNECT` chỉ giải quyết ranh giới vào database, không thay thế `USAGE` trên schema hoặc `SELECT` trên bảng.

## 17. Ghi nhớ cốt lõi

| Câu hỏi | Trả lời ngắn |
|---|---|
| Phần mềm đang nhận kết nối ở đâu? | **PostgreSQL server instance**, theo host/port hoặc socket |
| Tập database do instance đó quản lý là gì? | **Database cluster** |
| Tên database của connection hiện tại là gì? | `SELECT current_database();` |
| Không gian tên bên trong database gọi là gì? | **Schema** |
| Hai bảng cùng tên có thể cùng nằm trong một database không? | Có, nếu ở **schema khác nhau** |
| Tên bảng tường minh thông dụng viết thế nào? | `schema.table` |
| `search_path` dùng làm gì? | Tìm object khi viết tên **không kèm schema** |
| Một table chứa gì? | Các **rows** với dữ liệu theo định nghĩa cột và ràng buộc |
| Làm sao nhận diện một hàng ổn định? | Bằng **primary key/unique key**, không phải `ctid` |
| Role là đối tượng cấp nào? | **Cluster-wide**, còn quyền trên object được áp dụng theo cấp tương ứng |
| Có thể dùng `USE other_db` không? | Không; kết nối lại sang database khác |
| Database cluster có bắt buộc nhiều máy không? | Không; đó là nghĩa khác với **HA cluster** |

**Tư duy nền tảng của PostgreSQL:** một **server instance** phục vụ một **database cluster**; cluster chứa nhiều **database**; mỗi database có nhiều **schema**; mỗi schema chứa nhiều **table**; mỗi table chứa các **row**. Phân biệt các cấp này là bước đầu để viết SQL chính xác, thiết kế mô hình dữ liệu, quản lý quyền và vận hành PostgreSQL an toàn.

