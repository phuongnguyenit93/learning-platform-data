# Tạo role, database và bảng đầu tiên trong PostgreSQL

## 1. Mục tiêu và kết quả của bài thực hành

Sau khi PostgreSQL đã được cài đặt và dịch vụ đang chạy, việc đầu tiên để bắt đầu một ứng dụng thường là **tạo tài khoản đăng nhập**, **tạo database riêng** và **tạo bảng lưu dữ liệu đầu tiên**. Trong PostgreSQL, ba công việc này liên quan nhau nhưng ở các cấp quản lý khác nhau:

- **Role** xác định danh tính và các quyền mà một người hoặc ứng dụng có thể sử dụng.
- **Database** là không gian dữ liệu mà một connection PostgreSQL kết nối tới.
- **Schema** là namespace bên trong database, giúp tổ chức bảng và các đối tượng.
- **Table** định nghĩa các cột và ràng buộc; các hàng (*rows*) được lưu trong bảng.

Đến cuối bài, bạn sẽ có một môi trường thực hành như sau:

```text
PostgreSQL server / database cluster
│
├── Role: pg38_app (LOGIN)
│   └── Đăng nhập, sở hữu database pg38_demo
│
├── Database: postgres
│   └── Dùng để kết nối quản trị ban đầu
│
└── Database: pg38_demo
    └── Schema: app
        └── Table: app.tasks
            ├── task_id
            ├── title
            ├── status
            ├── priority
            ├── due_date
            └── created_at
```

Bài cũng hướng dẫn dùng `psql` để kiểm tra kết nối, thêm hàng, truy vấn, sửa dữ liệu, chạy transaction cơ bản và thử một tài khoản runtime có quyền hạn chế.

**Điều kiện tiên quyết:** PostgreSQL đã được cài đặt, có một instance đang hoạt động, có công cụ `psql` và có tài khoản quản trị **trong môi trường học tập** đủ quyền tạo role/database. Các ví dụ dùng cú pháp PostgreSQL hiện đại, phù hợp với các phiên bản được hỗ trợ như PostgreSQL 16, 17 hoặc 18; những chi tiết về xác thực và quyền mặc định có thể thay đổi theo phiên bản và cách cài đặt.

> **Phạm vi an toàn:** tên `pg38_app` và `pg38_demo` chỉ dành cho lab. Không tự tạo/xóa role hoặc database trên môi trường sản xuất, không dùng mật khẩu ví dụ làm mật khẩu thật, và không dùng role superuser làm tài khoản kết nối thường ngày của ứng dụng.

## 2. Hiểu đúng quan hệ giữa role, database, schema và table

PostgreSQL tổ chức các đối tượng theo những phạm vi khác nhau:

| Đối tượng | Phạm vi | Ví dụ | Ý nghĩa |
|---|---|---|---|
| **PostgreSQL instance/cluster** | Instance PostgreSQL đang chạy và quản lý vùng dữ liệu | Máy phục vụ cổng 5432 | Chứa nhiều database và các role dùng chung |
| **Role** | Cấp database cluster | `pg38_app` | Danh tính, thành viên role khác và các đặc quyền |
| **Database** | Nằm trong database cluster | `pg38_demo` | Không gian chứa schema, bảng và dữ liệu |
| **Schema** | Nằm trong một database | `app` | Namespace để đặt tên và quản lý đối tượng |
| **Table** | Thuộc một schema | `app.tasks` | Cấu trúc lưu hàng dữ liệu |
| **Row** | Nằm trong table | Một công việc có `task_id = 1` | Bản ghi logic gồm các giá trị cột |

Một **role có thể truy cập nhiều database** nếu có quyền tương ứng, vì role không được “tạo bên trong” một database riêng lẻ. Ngược lại, một **bảng thuộc đúng một schema của một database** tại một thời điểm. Hai database có thể cùng có bảng `app.tasks`, nhưng đó là hai bảng độc lập.

Quan trọng: PostgreSQL không có lệnh `USE database_name` kiểu MySQL. Khi muốn thao tác database khác, bạn phải **kết nối lại** hoặc tạo connection mới.

### 2.1. Role khác user ở điểm nào?

Trong PostgreSQL, **role là khái niệm chung**. Role có thuộc tính `LOGIN` là một tài khoản có thể dùng để đăng nhập; role không có `LOGIN` thường dùng để nhóm quyền hoặc sở hữu đối tượng.

Hai câu sau mang ý nghĩa gần tương đương trong tình huống tạo tài khoản đăng nhập:

```sql
CREATE ROLE example_login LOGIN;
CREATE USER another_login;
```

`CREATE USER` về cơ bản tạo role có `LOGIN` mặc định. Ngược lại, `CREATE ROLE example_group;` mặc định không bật `LOGIN`.

Những role chỉ để nhóm quyền có thể được cấp cho các role đăng nhập. Cách này giúp tách **định danh người dùng hoặc ứng dụng** khỏi **tập quyền** được chia sẻ.

### 2.2. Chủ sở hữu không đồng nghĩa superuser

Khi một role sở hữu database hoặc bảng, nó có một số quyền quản lý đối tượng đó. Nhưng **database owner không tự trở thành PostgreSQL superuser**. Nó không đương nhiên được quyền quản trị mọi role, đọc mọi database hoặc thay đổi mọi cấu hình server.

Trong bài lab, role `pg38_app` sẽ sở hữu database để tự tạo schema/bảng dễ dàng. Trong production, cách an toàn hơn thường là **tách role sở hữu schema (migration owner) khỏi role runtime của ứng dụng**, vì ứng dụng lúc chạy bình thường hiếm khi cần quyền DDL.

## 3. Kiểm tra PostgreSQL và công cụ `psql`

Trước khi tạo bất kỳ đối tượng nào, kiểm tra PostgreSQL đang chạy và bạn có thể kết nối.

### 3.1. Kiểm tra công cụ trên máy

Trong terminal hoặc PowerShell:

```sh
psql --version
```

Một kết quả minh họa có dạng:

```text
psql (PostgreSQL) 17.x
```

Con số thực tế tùy môi trường. Phiên bản công cụ `psql` không nhất thiết giống hoàn toàn phiên bản PostgreSQL server; muốn biết server, hãy truy vấn sau khi kết nối.

Nếu terminal báo không tìm thấy `psql`, có thể công cụ client chưa được cài hoặc chưa nằm trong `PATH`. Đây là vấn đề công cụ cục bộ, không đủ để kết luận server PostgreSQL chưa chạy.

### 3.2. Kết nối bằng role quản trị lab

Ví dụ một instance trên máy local đang lắng nghe cổng mặc định 5432:

```sh
psql -h 127.0.0.1 -p 5432 -U postgres -d postgres
```

Các tham số:

| Tham số | Ý nghĩa |
|---|---|
| `-h 127.0.0.1` | Địa chỉ server; dùng TCP tới máy local |
| `-p 5432` | Cổng lắng nghe |
| `-U postgres` | Role đăng nhập, thường là role quản trị được tạo khi cài đặt |
| `-d postgres` | Database ban đầu để kết nối và thực hiện tác vụ quản trị |

Role `postgres` thường được tạo khi khởi tạo cluster nhưng cách xác thực tùy bản cài đặt. Trên Linux, có cấu hình dùng **peer authentication** qua Unix socket cho tài khoản hệ điều hành `postgres`; khi đó câu lệnh kết nối TCP như trên có thể yêu cầu mật khẩu hoặc bị từ chối. Với Docker, cloud hoặc managed PostgreSQL, role quản trị cũng có thể mang tên khác và không phải superuser.

**Không thay đổi cấu hình xác thực bừa bãi chỉ để chạy bài.** Nếu không được cấp tài khoản quản trị trong lab, hãy dùng connection và quyền mà người quản trị đã chuẩn bị.

### 3.3. Xác minh đang ở đúng server và database

Trong `psql`:

```sql
SELECT
    version() AS server_version,
    current_database() AS connected_database,
    current_user AS current_role,
    session_user AS login_role,
    inet_server_port() AS tcp_port;
```

Đồng thời có thể dùng lệnh của `psql`:

```text
\conninfo
```

Đây là **psql meta-command**, không phải SQL gửi tới PostgreSQL server. Nó mô tả database, user và endpoint mà client đang sử dụng.

Để xem ngắn gọn phiên bản server:

```sql
SHOW server_version;
```

Khi chạy lệnh tạo role và database, hãy chắc chắn đây là **instance lab**, không phải production.

## 4. Tạo role đăng nhập đầu tiên

### 4.1. Tạo role bằng `CREATE ROLE ... LOGIN`

Trong phiên quản trị đang kết nối database `postgres`, chạy:

```sql
CREATE ROLE pg38_app LOGIN;
```

Ý nghĩa:

- `CREATE ROLE`: tạo một role ở cấp PostgreSQL cluster.
- `pg38_app`: tên role mới.
- `LOGIN`: cho phép role được dùng làm danh tính đăng nhập.
- Nếu không chỉ định `SUPERUSER`, role thông thường không có quyền superuser.
- Lệnh trên **chưa đặt mật khẩu** cho role.

Để xem role trong `psql`:

```text
\du
```

Hoặc dùng SQL:

```sql
SELECT rolname, rolcanlogin, rolsuper, rolcreatedb
FROM pg_roles
WHERE rolname = 'pg38_app';
```

Kết quả mong đợi về thuộc tính:

| rolname | rolcanlogin | rolsuper | rolcreatedb |
|---|---|---|---|
| pg38_app | true | false | false |

Giá trị `rolcreatedb = false` là phù hợp cho role ứng dụng ở bài này. **Nó vẫn có thể sở hữu database do quản trị viên tạo và chỉ định owner**, dù bản thân không có quyền tự tạo database khác.

### 4.2. Đặt mật khẩu an toàn bằng `\password`

Thay vì ghi mật khẩu vào câu SQL được lưu trong lịch sử, ở **psql của quản trị viên** có thể dùng:

```text
\password pg38_app
```

`psql` sẽ yêu cầu nhập và xác nhận mật khẩu. Hãy tạo mật khẩu lab ngẫu nhiên, đủ mạnh và **không sử dụng lại mật khẩu sản xuất**.

Ưu điểm so với câu:

```sql
-- Chỉ minh họa cú pháp; không khuyến khích đưa secret thật vào script/log.
ALTER ROLE pg38_app PASSWORD 'your_plaintext_secret';
```

là `\password` tránh việc đặt chuỗi mật khẩu rõ trong command history hoặc trong file SQL. Với môi trường tự động hóa, nên sử dụng secret manager/cơ chế phân phối secret thích hợp và xác thực được cấu hình an toàn.

**Lưu ý xác thực:** đặt password cho role không tự bảo đảm role sẽ đăng nhập được. Server còn áp dụng quy tắc trong `pg_hba.conf` hoặc lớp cấu hình xác thực tương đương. Một số kết nối yêu cầu password, một số yêu cầu certificate/peer và một số cấu hình có thể không cho phép endpoint bạn đang dùng.

### 4.3. Đừng cấp quyền quản trị không cần thiết

Một số thuộc tính đặc biệt của role:

| Thuộc tính | Công dụng | Có nên cấp cho runtime application? |
|---|---|---|
| `LOGIN` | Cho phép đăng nhập | Có, nếu role là tài khoản kết nối |
| `SUPERUSER` | Bỏ qua nhiều kiểm tra quyền | **Không** |
| `CREATEDB` | Cho phép tạo database | Thường **không** |
| `CREATEROLE` | Quản lý role trong phạm vi quy tắc PostgreSQL | **Không** |
| `REPLICATION` | Dùng cho một số kết nối/tác vụ replication | Không cho ứng dụng thông thường |
| `BYPASSRLS` | Bỏ qua Row-Level Security trong phạm vi cho phép | Không cho ứng dụng thông thường |

Mẫu:

```sql
CREATE ROLE pg38_app LOGIN;
```

là điểm bắt đầu tốt hơn nhiều so với việc cho ứng dụng `SUPERUSER` chỉ để “khỏi bị lỗi permission denied”.

## 5. Tạo database đầu tiên và xác định owner

### 5.1. Tạo database từ phiên quản trị

Role quản trị chạy:

```sql
CREATE DATABASE pg38_demo OWNER pg38_app;
```

PostgreSQL tạo database `pg38_demo` trong **cluster đang kết nối**, với owner là `pg38_app`. Lệnh không tạo server mới, không thay đổi cổng và không tự tạo thêm account.

Dùng `psql` để liệt kê database:

```text
\l
```

Hoặc SQL:

```sql
SELECT
    datname AS database_name,
    pg_get_userbyid(datdba) AS owner_name
FROM pg_database
WHERE datname = 'pg38_demo';
```

Kết quả mong đợi là một database tên `pg38_demo` với owner `pg38_app`.

### 5.2. Tại sao owner quan trọng?

Database owner có các đặc quyền quản lý đối tượng cấp database theo ngữ nghĩa PostgreSQL. Trong ví dụ, `pg38_app` có thể tạo schema mới trong database do nó sở hữu mà không cần quyền `CREATEDB` toàn cluster.

Tuy nhiên:

- Owner của **database** không đồng nghĩa owner của **mọi bảng đã có** bên trong.
- Owner database không tự có quyền đọc/ghi mọi bảng do các role khác sở hữu.
- Quyền thao tác còn liên quan owner của từng đối tượng, privilege và role membership.

Do đó, “tạo database” và “cấp quyền trên các bảng trong database” là hai việc cần hiểu riêng.

### 5.3. `CREATE DATABASE` không chạy trong transaction block

Khác với nhiều DDL thông thường, lệnh sau **không hợp lệ**:

```sql
BEGIN;
CREATE DATABASE pg38_demo OWNER pg38_app;
COMMIT;
```

PostgreSQL không cho `CREATE DATABASE` chạy bên trong một transaction block. Hãy chạy nó như một câu lệnh riêng trong phiên quản trị. Nhiều công cụ migration mặc định bọc script trong transaction; nếu script tạo database, cần cấu hình cách chạy riêng phù hợp.

**Đừng dùng `DROP DATABASE` để “thử lại” trong một hệ thống có dữ liệu thật.** Nếu database `pg38_demo` đã tồn tại, hãy xác nhận nó có thực sự là đối tượng lab của mình trước khi quyết định đổi tên bài thực hành hoặc dọn dẹp theo quy trình.

### 5.4. Không nhầm database với schema

```sql
CREATE DATABASE pg38_demo OWNER pg38_app;
```

tạo **database** thuộc cluster, còn:

```sql
CREATE SCHEMA app;
```

tạo **schema** trong **database hiện tại**. Nếu phiên đang kết nối `postgres`, câu `CREATE SCHEMA app` sẽ tạo schema trong database `postgres`, **không** phải tự động trong `pg38_demo`.

Vì thế, trước khi tạo bảng, phải chuyển sang **connection đúng database**.

## 6. Kết nối lại bằng role vừa tạo

Thoát phiên quản trị nếu muốn:

```text
\q
```

Mở terminal mới hoặc dùng terminal hiện tại:

```sh
psql -h 127.0.0.1 -p 5432 -U pg38_app -d pg38_demo
```

Sau khi xác thực thành công, chạy:

```sql
SELECT
    current_database() AS db_name,
    current_user AS active_role,
    session_user AS login_role;
```

Mong đợi:

| db_name | active_role | login_role |
|---|---|---|
| pg38_demo | pg38_app | pg38_app |

Bây giờ các câu `CREATE SCHEMA` và `CREATE TABLE` phía dưới sẽ được thực thi trong **database `pg38_demo`**, không phải database quản trị `postgres`.

### 6.1. Đổi database từ bên trong psql

Nếu đang ở một phiên `psql` và muốn kết nối lại, dùng meta-command:

```text
\connect pg38_demo pg38_app
```

hoặc:

```text
\c pg38_demo pg38_app
```

Tùy môi trường, `psql` sẽ giữ hoặc hỏi lại thông số host/port/password. Đây là hành động **reconnect của client**. PostgreSQL không hỗ trợ `USE pg38_demo;` như câu SQL để chuyển database bên trong connection hiện có.

### 6.2. Nếu đăng nhập thất bại

Một số lỗi điển hình:

| Lỗi | Nguyên nhân khả dĩ | Cách kiểm tra |
|---|---|---|
| `connection refused` | Server chưa chạy, sai host/port hoặc không lắng nghe TCP | Kiểm tra dịch vụ, host, port và `listen_addresses` |
| `password authentication failed` | Sai mật khẩu, role hoặc phương thức xác thực | Kiểm tra account, password, cấu hình xác thực |
| `no pg_hba.conf entry` | Kết nối không khớp quy tắc xác thực/nguồn truy cập | Kiểm tra cấu hình `pg_hba.conf` và yêu cầu TLS |
| `role "pg38_app" does not exist` | Role chưa tạo ở instance đang kết nối hoặc sai tên | Kiểm tra server endpoint và `\du` bằng admin |
| `database "pg38_demo" does not exist` | Database chưa tạo ở instance này hoặc sai tên | Kiểm tra `\l` bằng admin |
| `permission denied for database` | Role không có quyền `CONNECT` phù hợp | Kiểm tra owner và `GRANT CONNECT` |
| `Peer authentication failed` | Xác thực peer trên local socket, khác role OS hoặc PG role | Dùng kết nối/quy tắc xác thực đúng; không tắt bảo mật tùy tiện |

**Không nên sửa `pg_hba.conf` thành `trust` cho mọi địa chỉ để vượt qua lỗi mật khẩu.** Cấu hình đó có thể cho phép đăng nhập không cần xác thực theo phạm vi quy tắc, đặc biệt nguy hiểm nếu server nghe mạng ngoài.

## 7. Tạo schema để tổ chức bảng ứng dụng

Trong kết nối **`pg38_app@pg38_demo`**, chạy:

```sql
CREATE SCHEMA app AUTHORIZATION pg38_app;
```

Ý nghĩa:

- `app` là namespace bên trong `pg38_demo`.
- `AUTHORIZATION pg38_app` đặt owner schema là role `pg38_app`.
- Schema này chứa bảng và những đối tượng liên quan của ứng dụng.

Kiểm tra:

```text
\dn
```

Hoặc SQL:

```sql
SELECT schema_name, schema_owner
FROM information_schema.schemata
WHERE schema_name = 'app';
```

Lệnh `CREATE SCHEMA` cần quyền tạo schema trong database. Với role là owner database `pg38_demo`, ví dụ này sử dụng được nếu không có chính sách cấu hình đặc biệt làm thay đổi khả năng tạo object.

### 7.1. Tại sao không tạo tất cả bảng trong `public`?

PostgreSQL thường tạo sẵn schema `public` trong database mới. Nhưng dùng một schema riêng cho ứng dụng có những lợi ích:

- Phân biệt rõ bảng ứng dụng với các object dùng chung hoặc thử nghiệm.
- Giảm rủi ro xung đột tên.
- Tổ chức quyền và migration theo module.
- Làm rõ đường dẫn đối tượng trong câu SQL, ví dụ `app.tasks`.
- Không phải phụ thuộc vào quyền `CREATE` mặc định trên `public`, vốn khác nhau giữa phiên bản/cấu hình.

Trong các PostgreSQL mới, đặc biệt từ PostgreSQL 15, mặc định về quyền tạo đối tượng ở `public` đã được siết chặt so với nhiều cài đặt cũ. Vì vậy, nên học cách dùng schema riêng và hiểu quyền trên schema ngay từ đầu.

### 7.2. Tên đủ điều kiện `schema.table`

Khi viết:

```sql
SELECT * FROM app.tasks;
```

`app` là schema; `tasks` là bảng. Database không được đặt trong tên này vì connection đã chỉ định database `pg38_demo`.

Câu:

```sql
SELECT * FROM tasks;
```

chỉ hoạt động nếu PostgreSQL có thể phân giải tên `tasks` theo cấu hình **`search_path`** và quyền của role. Để các ví dụ rõ ràng, bài dùng tên đầy đủ `app.tasks`.

## 8. Tạo bảng đầu tiên bằng `CREATE TABLE`

Đây là bước trung tâm của bài. Trong kết nối `pg38_app@pg38_demo`, chạy:

```sql
CREATE TABLE app.tasks (
    task_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title text NOT NULL,
    status text NOT NULL DEFAULT 'TODO',
    priority smallint NOT NULL DEFAULT 3,
    due_date date,
    created_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT tasks_status_check
      CHECK (status IN ('TODO', 'IN_PROGRESS', 'DONE')),

    CONSTRAINT tasks_priority_check
      CHECK (priority BETWEEN 1 AND 5)
);
```

Bảng mới thuộc schema `app` trong database `pg38_demo`. Vì `pg38_app` là người chạy lệnh, role này sẽ sở hữu bảng được tạo theo quy tắc ownership thông thường.

### 8.1. Phân tích từng cột

| Cột | Kiểu | Ràng buộc/mặc định | Ý nghĩa |
|---|---|---|---|
| `task_id` | `bigint` | `GENERATED ALWAYS AS IDENTITY PRIMARY KEY` | Định danh duy nhất, PostgreSQL tự sinh |
| `title` | `text` | `NOT NULL` | Nội dung công việc, bắt buộc có giá trị |
| `status` | `text` | `NOT NULL DEFAULT 'TODO'`, `CHECK` | Trạng thái công việc |
| `priority` | `smallint` | `DEFAULT 3`, `CHECK 1..5` | Độ ưu tiên hợp lệ từ 1 tới 5 |
| `due_date` | `date` | Cho phép `NULL` | Ngày đến hạn, có thể chưa xác định |
| `created_at` | `timestamptz` | `DEFAULT now()` | Thời điểm tạo hàng |

Các câu hỏi thường gặp:

**`PRIMARY KEY` là gì?** Nó xác định khóa chính của bảng. Giá trị của khóa chính phải không NULL và duy nhất, có thể được bảng khác tham chiếu bằng `FOREIGN KEY`.

**`IDENTITY` là gì?** PostgreSQL quản lý một cơ chế sinh số định danh thông qua sequence liên quan. Với `GENERATED ALWAYS`, việc cung cấp tường minh giá trị ID thường bị từ chối, trừ khi dùng cú pháp override được hỗ trợ. Đây không phải cam kết rằng các ID luôn liên tiếp không có khoảng trống.

**`text` khác `varchar(200)` thế nào?** `text` chứa chuỗi độ dài biến thiên mà không có giới hạn ký tự khai báo tại cột. Nếu nghiệp vụ yêu cầu giới hạn độ dài, có thể dùng `varchar(n)` hoặc `CHECK (char_length(title) <= n)` theo mục tiêu. Không cần dùng `varchar(255)` chỉ vì thói quen của hệ quản trị khác.

**`DEFAULT` có tự thay mọi `NULL` không?** Không. Mặc định được dùng khi cột **bị bỏ qua** trong lệnh `INSERT` hoặc được chỉ định `DEFAULT`. Nếu ứng dụng chủ động chèn `NULL` cho cột `status NOT NULL`, PostgreSQL báo vi phạm ràng buộc thay vì tự đổi thành `'TODO'`.

**`timestamptz` có lưu tên múi giờ gốc không?** Không. PostgreSQL lưu một thời điểm có ngữ nghĩa tuyệt đối và hiển thị nó theo timezone của session. Nếu nghiệp vụ cần biết múi giờ gốc của người dùng, hãy lưu riêng vùng múi giờ hoặc thông tin tương ứng.

**`CHECK` bảo đảm gì?** Nó ngăn một số trạng thái không hợp lệ ở tầng database. Một `CHECK` thông thường không coi kết quả biểu thức `UNKNOWN` do `NULL` là vi phạm, nên cột có ý nghĩa bắt buộc vẫn cần `NOT NULL` khi thích hợp. Trong bảng này `status` và `priority` đã có `NOT NULL`.

### 8.2. Kiểm tra bảng vừa tạo

Trong `psql`:

```text
\dt app.*
\d app.tasks
```

Kết quả `\d app.tasks` cho bạn biết định nghĩa cột, kiểu dữ liệu, default, khóa chính và các constraint. Đây là lệnh riêng của `psql`.

Dùng SQL nếu kết nối qua driver:

```sql
SELECT
    table_schema,
    table_name,
    table_type
FROM information_schema.tables
WHERE table_schema = 'app'
ORDER BY table_name;

SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'app'
  AND table_name = 'tasks'
ORDER BY ordinal_position;
```

`information_schema` là giao diện metadata được chuẩn hóa ở mức SQL; một số đặc điểm PostgreSQL cụ thể như identity, constraint và sequence có thể cần truy vấn thêm metadata/công cụ riêng.

### 8.3. Phân biệt tạo bảng với chèn hàng

`CREATE TABLE` chỉ định nghĩa **cấu trúc**. Ngay sau khi tạo, bảng chưa có hàng:

```sql
SELECT COUNT(*) AS task_count
FROM app.tasks;
```

Kết quả kỳ vọng là `0`, trừ khi có ai đó đã chèn dữ liệu vào bảng trong thời gian bạn thực hành.

## 9. Thêm những hàng đầu tiên bằng `INSERT`

Thêm hai công việc:

```sql
INSERT INTO app.tasks (title, priority, due_date)
VALUES
    ('Học cách tạo role PostgreSQL', 2, DATE '2026-11-20'),
    ('Tạo database và bảng đầu tiên', 1, DATE '2026-11-21')
RETURNING
    task_id, title, status, priority, due_date, created_at;
```

PostgreSQL tự sinh `task_id`; các cột `status` và `created_at` nhận giá trị mặc định. Chú ý câu `INSERT` **không truyền `task_id`** vì cột đó được khai báo `GENERATED ALWAYS AS IDENTITY`.

Kết quả minh họa, lược bỏ thời gian tạo cụ thể:

| task_id | title | status | priority | due_date |
|---:|---|---|---:|---|
| 1 | Học cách tạo role PostgreSQL | TODO | 2 | 2026-11-20 |
| 2 | Tạo database và bảng đầu tiên | TODO | 1 | 2026-11-21 |

Nếu đã chạy bài nhiều lần, giá trị `task_id` có thể không còn là 1 và 2. Sequence tạo identity không bảo đảm số liên tục khi có transaction rollback, insert lỗi hoặc thao tác khác.

### 9.1. Lấy dữ liệu đã lưu

```sql
SELECT
    task_id,
    title,
    status,
    priority,
    due_date,
    created_at
FROM app.tasks
ORDER BY task_id;
```

Dùng `ORDER BY` khi muốn thứ tự ổn định. PostgreSQL không cam kết thứ tự output của `SELECT` không có `ORDER BY`, kể cả nếu bảng có primary key.

### 9.2. Lọc các hàng chưa hoàn tất

```sql
SELECT task_id, title, priority
FROM app.tasks
WHERE status = 'TODO'
ORDER BY priority ASC, task_id ASC;
```

Câu truy vấn chỉ đọc các hàng thỏa điều kiện. Nó không tạo role, schema hay bảng mới.

### 9.3. Cập nhật trạng thái một công việc

```sql
UPDATE app.tasks
SET status = 'IN_PROGRESS'
WHERE title = 'Học cách tạo role PostgreSQL'
RETURNING task_id, title, status;
```

Trong dữ liệu mẫu, tiêu đề chỉ được chèn một lần. Trong ứng dụng thật, nên cập nhật theo **khóa chính** hoặc khóa duy nhất phù hợp, thay vì dựa vào một tiêu đề có thể trùng.

Ví dụ khi đã biết ID:

```sql
UPDATE app.tasks
SET status = 'DONE'
WHERE task_id = 1
RETURNING task_id, status;
```

Nếu ID được sinh khác 1, hãy thay ID bằng giá trị thực nhận từ `RETURNING`.

### 9.4. Thử vi phạm ràng buộc

Câu sau cố tình tạo giá trị ưu tiên không hợp lệ:

```sql
INSERT INTO app.tasks (title, priority)
VALUES ('Công việc sai độ ưu tiên', 9);
```

PostgreSQL sẽ từ chối vì `tasks_priority_check` chỉ cho phép độ ưu tiên từ 1 đến 5. Câu sau cũng không hợp lệ:

```sql
INSERT INTO app.tasks (title, status)
VALUES ('Công việc có trạng thái sai', 'UNKNOWN');
```

Hai ví dụ này cho thấy ràng buộc ở tầng database bảo vệ chất lượng dữ liệu, không chỉ dựa vào kiểm tra phía ứng dụng. Nếu chạy những câu này **bên trong transaction đang mở**, bạn có thể cần `ROLLBACK` trước khi tiếp tục vì PostgreSQL đánh dấu transaction đang có lỗi.

## 10. Transaction đầu tiên với `BEGIN`, `COMMIT` và `ROLLBACK`

PostgreSQL hỗ trợ transaction để gom nhiều câu SQL thành một đơn vị công việc. Khi đang ở chế độ autocommit thông thường của `psql`, mỗi câu lệnh SQL độc lập thường được commit khi hoàn tất thành công. Muốn chủ động điều phối nhiều bước, hãy mở transaction tường minh.

### 10.1. Thử thay đổi rồi rollback

```sql
BEGIN;

UPDATE app.tasks
SET priority = 5
WHERE task_id = 1;

SELECT task_id, priority
FROM app.tasks
WHERE task_id = 1;

ROLLBACK;
```

Trong cùng transaction, bạn có thể thấy giá trị vừa cập nhật. Sau `ROLLBACK`, thay đổi chưa commit được hoàn tác.

Kiểm tra lại:

```sql
SELECT task_id, priority
FROM app.tasks
WHERE task_id = 1;
```

Giá trị trở về trước thử nghiệm, nếu không có transaction khác tác động và ID 1 thật sự là hàng được chọn.

### 10.2. Khi nào dùng `COMMIT`?

```sql
BEGIN;

UPDATE app.tasks
SET status = 'DONE'
WHERE task_id = 1;

COMMIT;
```

Sau `COMMIT`, thay đổi được ghi nhận theo bảo đảm transaction của PostgreSQL và có thể được các session khác quan sát theo quy tắc isolation/snapshot tương ứng.

**Lưu ý quan trọng:** PostgreSQL có tính năng transactional DDL cho nhiều lệnh như `CREATE TABLE`, nhưng `CREATE DATABASE` là ngoại lệ không chạy được trong transaction block. Đừng dùng một transaction bao quanh mọi loại câu lệnh quản trị mà không xét từng lệnh.

### 10.3. Nếu một câu lệnh trong transaction bị lỗi

Ví dụ:

```sql
BEGIN;

INSERT INTO app.tasks (title, priority)
VALUES ('Sai constraint', 99);

-- Câu INSERT thất bại.
-- Transaction thường ở trạng thái lỗi cho đến khi được kết thúc.

ROLLBACK;
```

Sau một lỗi SQL trong transaction PostgreSQL, các câu lệnh tiếp theo có thể báo `current transaction is aborted, commands ignored until end of transaction block`. Giải pháp trong bài thực hành là `ROLLBACK`, sửa lệnh rồi tạo transaction mới. Trong ứng dụng, cần quản lý lỗi và rollback ở tầng transaction manager/JDBC tương ứng.

## 11. Thiết lập `search_path` để dùng tên bảng ngắn

PostgreSQL xác định bảng không kèm schema bằng **`search_path`**. Kiểm tra:

```sql
SHOW search_path;
SELECT current_schema();
```

Một cấu hình thường gặp là:

```text
"$user", public
```

Điều này không tự chứa schema `app`. Vì thế:

```sql
SELECT * FROM tasks;
```

có thể báo `relation "tasks" does not exist` dù `app.tasks` thực sự tồn tại.

Bạn có thể thay đổi cho **session hiện tại**:

```sql
SET search_path TO app, public;

SELECT task_id, title
FROM tasks
ORDER BY task_id;

SELECT task_id, title
FROM app.tasks
ORDER BY task_id;
```

Cả hai câu có thể truy cập cùng bảng khi search path và quyền phù hợp.

Muốn hoàn tác cấu hình session:

```sql
RESET search_path;
```

Trong SQL quan trọng hoặc migration, viết `app.tasks` tường minh thường dễ hiểu và an toàn hơn vì không phụ thuộc cấu hình `search_path` của connection.

**Lưu ý bảo mật:** không đưa schema cho phép người dùng không tin cậy tạo đối tượng vào đầu `search_path` của ứng dụng quan trọng. Việc phân giải function/operator/object theo search path có thể gây lỗi hoặc rủi ro bảo mật nếu namespace không được kiểm soát.

## 12. Phân quyền cho tài khoản ứng dụng runtime: tách owner và DML

Trong phần trước, `pg38_app` vừa là người đăng nhập vừa là owner của database/schema/table. Cách này tiện cho bài lab, nhưng ứng dụng production thường không cần quyền tự ý `ALTER TABLE` hoặc `DROP TABLE`.

Một mô hình tốt hơn:

```text
Migration/owner role:
    CREATE, ALTER, DROP đối tượng theo quy trình triển khai

Runtime application role:
    CONNECT vào database
    USAGE trên schema
    SELECT, INSERT, UPDATE, DELETE đúng bảng cần sử dụng

Reporting role:
    CONNECT, USAGE, SELECT theo phạm vi báo cáo
```

Bạn có thể thực hành tạo một role runtime quyền hạn chế **ngay trên bảng đã tạo**.

### 12.1. Tạo role runtime bằng quản trị viên lab

Mở một phiên `psql` quản trị riêng, kết nối vào database `postgres` của **cùng instance**:

```sql
CREATE ROLE pg38_runtime LOGIN;
```

Trong `psql` quản trị:

```text
\password pg38_runtime
```

Sau đó kết nối tới database `pg38_demo` bằng role có quyền cấp privilege (ví dụ admin hoặc owner đối tượng):

```text
\connect pg38_demo
```

Cấp quyền:

```sql
GRANT CONNECT ON DATABASE pg38_demo TO pg38_runtime;
GRANT USAGE ON SCHEMA app TO pg38_runtime;

GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE app.tasks
TO pg38_runtime;
```

Ý nghĩa:

- `CONNECT` cho phép kết nối database.
- `USAGE` cho phép phân giải các đối tượng được phép truy cập trong schema.
- Các quyền DML trên bảng cho phép những thao tác dữ liệu tương ứng.
- **Không có `CREATE` trên schema hoặc database** trong các lệnh GRANT trên.
- Role này **không phải owner** của bảng.

Với database mới, `CONNECT` có thể đã được cấp cho `PUBLIC` theo mặc định, nên câu `GRANT CONNECT` đôi khi không làm thay đổi kết quả trước mắt. Nhưng nó vẫn minh họa rõ quyền cần thiết; trong hệ thống có chính sách hạn chế quyền mặc định, cần quản lý cả `PUBLIC` và account cụ thể.

**Về sequence:** với cột dùng `GENERATED ... AS IDENTITY`, PostgreSQL có cơ chế xử lý identity gắn với bảng. Với kiểu cũ `serial` dùng `nextval()` và sequence độc lập, runtime account có thể cần quyền `USAGE` hoặc quyền thích hợp trên sequence khi chèn dữ liệu. Không cấp `USAGE ON ALL SEQUENCES` một cách máy móc nếu chỉ cần một số sequence.

### 12.2. Xác nhận bằng chính tài khoản runtime

Mở một terminal mới:

```sh
psql -h 127.0.0.1 -p 5432 -U pg38_runtime -d pg38_demo
```

Thử truy vấn:

```sql
SELECT current_user, current_database();

SELECT task_id, title, status
FROM app.tasks
ORDER BY task_id;
```

Truy vấn đọc sẽ hoạt động nếu bạn đã cấp các quyền ở trên và không có chính sách hạn chế khác.

Thử thao tác **không được phép**:

```sql
CREATE TABLE app.unauthorized_test (
    id integer PRIMARY KEY
);
```

Mong đợi PostgreSQL báo lỗi thiếu quyền tạo đối tượng trong schema `app`. Nếu câu lệnh lại thành công, hãy kiểm tra `current_user`, ownership, role membership và các privilege cấp cho `PUBLIC` hoặc thông qua role khác; không kết luận user có quyền tối thiểu khi chưa kiểm chứng.

### 12.3. Kiểm tra quyền bằng SQL

Dưới một role có thể đọc thông tin phù hợp:

```sql
SELECT
    has_database_privilege('pg38_runtime', 'pg38_demo', 'CONNECT')
        AS can_connect,
    has_schema_privilege('pg38_runtime', 'app', 'USAGE')
        AS can_use_app_schema,
    has_schema_privilege('pg38_runtime', 'app', 'CREATE')
        AS can_create_in_app,
    has_table_privilege('pg38_runtime', 'app.tasks', 'SELECT')
        AS can_select_tasks;
```

Kết quả mục tiêu:

- `can_connect = true`
- `can_use_app_schema = true`
- `can_create_in_app = false`
- `can_select_tasks = true`

Nếu role đã được cấp các quyền thông qua thành viên role khác hoặc chính sách bổ sung, kết quả có thể khác. Mục đích là kiểm tra **quyền hiệu lực thực tế** thay vì chỉ đọc một dòng `GRANT` trong script.

Trong `psql`, có thể xem quyền bảng:

```text
\dp app.tasks
```

Hoặc từ phiên quản trị dùng `\du pg38_runtime` để quan sát thuộc tính role, nhưng đừng nhầm thuộc tính role với đầy đủ quyền trên từng bảng.

### 12.4. Tại sao không dùng account owner trong ứng dụng thật?

Nếu app runtime kết nối bằng role sở hữu table, một lỗi trong code hoặc lỗ hổng SQL injection có thể thực hiện DDL ngoài dự kiến nếu role có quyền tương ứng. Một account chỉ có DML thích hợp sẽ có phạm vi thiệt hại nhỏ hơn.

Tuy nhiên, **DML cũng có thể phá dữ liệu**, ví dụ `DELETE FROM app.tasks;` khi runtime account có quyền DELETE. Nếu ứng dụng không cần xóa bản ghi, có thể bỏ quyền `DELETE`, dùng tài khoản riêng theo mục đích hoặc kiểm soát lệnh qua API/stored routine phù hợp.

## 13. Tạo bảng thứ hai và hiểu quyền mặc định

Giả sử module ứng dụng thêm bảng `app.task_notes`:

```sql
-- Chạy bằng owner/migration role có quyền tạo bảng trong schema app.
CREATE TABLE app.task_notes (
    note_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    task_id bigint NOT NULL REFERENCES app.tasks(task_id),
    note_text text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
```

Bảng mới có khóa ngoại tham chiếu `app.tasks`. Mặc dù role `pg38_runtime` đã được cấp quyền trên `app.tasks`, **nó không tự có quyền SELECT/INSERT trên bảng mới**.

Cấp quyền cho bảng mới nếu nghiệp vụ cần:

```sql
GRANT SELECT, INSERT
ON TABLE app.task_notes
TO pg38_runtime;
```

### 13.1. Quyền mặc định cho những bảng tạo sau này

Để thiết lập privilege cho các bảng tương lai, **role thực sự tạo bảng** có thể cấu hình default privileges cho các đối tượng nó tạo trong schema:

```sql
-- Chạy bằng role tạo bảng, ví dụ pg38_app.
ALTER DEFAULT PRIVILEGES IN SCHEMA app
GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLES TO pg38_runtime;
```

Ý nghĩa:

- Áp dụng cho **bảng tạo trong tương lai** bởi role tương ứng theo quy tắc default privileges.
- Không tự thay đổi quyền của mọi bảng đã tồn tại.
- Không mặc nhiên áp dụng cho bảng do một owner khác tạo nếu không cấu hình theo đúng role tạo object.
- Cần cân nhắc kỹ tập quyền; có ứng dụng không cần `DELETE` hoặc `UPDATE` trên mọi bảng mới.

Với hệ thống nhiều service, nên thiết kế ownership, migration role và default privileges một cách nhất quán. Việc cấu hình theo schema không tự thay thế cho đánh giá quyền ở mức bảng.

## 14. Tạo bảng từ ứng dụng Java/JDBC

PostgreSQL thường được dùng với Java qua **PostgreSQL JDBC Driver (pgJDBC)**. JDBC URL chứa địa chỉ, cổng và database:

```text
jdbc:postgresql://127.0.0.1:5432/pg38_demo
```

Trong mã ứng dụng, cần sử dụng role runtime thích hợp, không phải superuser hoặc migration owner:

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

public class FirstPostgresQuery {
    public static void main(String[] args) throws Exception {
        String url = "jdbc:postgresql://127.0.0.1:5432/pg38_demo";
        String user = System.getenv("PG_APP_USER");
        String password = System.getenv("PG_APP_PASSWORD");

        if (user == null || password == null) {
            throw new IllegalStateException("Missing DB credentials");
        }

        String sql = """
            SELECT task_id, title, status
            FROM app.tasks
            WHERE status = ?
            ORDER BY task_id
            """;

        try (Connection connection =
                    DriverManager.getConnection(url, user, password);
             PreparedStatement statement = connection.prepareStatement(sql)) {

            statement.setString(1, "TODO");

            try (ResultSet rows = statement.executeQuery()) {
                while (rows.next()) {
                    long taskId = rows.getLong("task_id");
                    String title = rows.getString("title");
                    String status = rows.getString("status");

                    System.out.printf("%d: %s (%s)%n", taskId, title, status);
                }
            }
        }
    }
}
```

Ví dụ dùng **Java 15+ text blocks**; dự án cần có dependency pgJDBC và cấu hình kết nối thực tế. Hai biến môi trường:

```text
PG_APP_USER=pg38_runtime
PG_APP_PASSWORD=<mật khẩu lấy từ cấu hình bí mật>
```

được nêu để mô tả nguồn cấu hình, không phải file có mật khẩu mẫu nên commit vào repository.

Trong production:

- Lấy secret từ cơ chế quản lý secret phù hợp; biến môi trường chỉ là một trong các phương án và cần quản trị quyền truy cập.
- Bật và xác minh TLS theo kiến trúc mạng.
- Dùng connection pool được cấu hình giới hạn kết nối/timeouts phù hợp.
- Sử dụng `PreparedStatement` và tham số, không nối chuỗi dữ liệu người dùng trực tiếp vào SQL.
- Tách migration khỏi ứng dụng runtime, không tự tạo database/schema mỗi khi service khởi động.
- Cần xử lý lỗi mất kết nối, deadlock, timeout và transaction rõ ràng ở tầng ứng dụng.

Đoạn Java minh họa **đọc bảng đã tồn tại**; nó không tự thực hiện câu `CREATE TABLE` trong runtime. Tạo và thay đổi bảng nên thuộc một quy trình migration riêng khi ứng dụng vận hành nghiêm túc.

## 15. Những lỗi thường gặp khi tạo role, database và bảng

### 15.1. `ERROR: permission denied to create role`

Role đang kết nối không có quyền tạo role phù hợp. Kiểm tra:

```sql
SELECT current_user;

SELECT rolname, rolcreaterole, rolsuper
FROM pg_roles
WHERE rolname = current_user;
```

Chỉ dùng tài khoản quản trị trong môi trường lab hoặc nhờ quản trị viên cấp role cần thiết. Không cấp `CREATEROLE` cho application runtime chỉ để chạy bài.

### 15.2. `ERROR: permission denied to create database`

Người chạy `CREATE DATABASE` thiếu `CREATEDB` hoặc quyền phù hợp. Nếu role ứng dụng không có quyền này, đó thường là cấu hình **đúng**, không phải lỗi cần “chữa” bằng `SUPERUSER`. Quản trị viên nên tạo database và gán owner theo yêu cầu.

### 15.3. `ERROR: CREATE DATABASE cannot run inside a transaction block`

Đang chạy câu tạo database bên trong `BEGIN ... COMMIT` hoặc một công cụ đã tự mở transaction. Tách lệnh `CREATE DATABASE` ra thành câu độc lập theo quy tắc PostgreSQL.

### 15.4. `ERROR: database "pg38_demo" does not exist`

Có thể đã tạo database trên instance khác, sai tên, sai host/port hoặc chưa thực hiện bước tạo. Dùng tài khoản quản trị ở **cùng endpoint** để kiểm tra:

```sql
SELECT datname
FROM pg_database
WHERE datname = 'pg38_demo';
```

### 15.5. `ERROR: role "pg38_app" does not exist`

Role chưa được tạo trong cluster đang kết nối, hoặc tên bị sai. Kiểm tra:

```sql
SELECT rolname
FROM pg_roles
WHERE rolname = 'pg38_app';
```

Một role tồn tại ở cluster A không tự xuất hiện ở cluster B, dù hai cluster đều có database mang cùng tên.

### 15.6. `ERROR: permission denied for schema app`

Account có thể kết nối vào database nhưng không có `USAGE` trên schema, hoặc không có `CREATE` khi tạo bảng trong schema. Cần phân biệt:

- `CONNECT`: vào database.
- `USAGE`: được tham chiếu tới đối tượng trong schema theo quyền tương ứng.
- `CREATE` trên schema: tạo đối tượng phù hợp trong schema.
- `SELECT/INSERT/UPDATE/DELETE`: thao tác dữ liệu trên bảng.

Một quyền không tự thay thế tất cả quyền khác.

### 15.7. `ERROR: relation "tasks" does not exist`

Bảng có thể thực sự tồn tại dưới tên `app.tasks`, nhưng `search_path` không chứa `app` hoặc bạn đang ở database khác. Kiểm tra:

```sql
SELECT current_database();
SHOW search_path;

SELECT to_regclass('app.tasks') AS fully_qualified,
       to_regclass('tasks') AS resolved_by_search_path;
```

Nếu `fully_qualified` có giá trị còn `resolved_by_search_path` là `NULL`, hãy dùng tên `app.tasks` hoặc sửa search path phù hợp.

### 15.8. `ERROR: relation "app.tasks" already exists`

Có thể bạn đã chạy lệnh `CREATE TABLE` trước đó. **Không vội `DROP TABLE` để chạy lại**: bảng có thể đã có dữ liệu. Dùng `\d app.tasks`, kiểm tra schema và quyết định có dùng bảng hiện có hay lập môi trường lab sạch.

`CREATE TABLE IF NOT EXISTS` giúp tránh lỗi khi bảng tồn tại, nhưng nó không bảo đảm định nghĩa bảng cũ **giống hệt** định nghĩa mong muốn; vì vậy nó không thay thế migration có kiểm soát.

### 15.9. `INSERT` không sinh được identity

Đầu tiên kiểm tra định nghĩa cột:

```text
\d app.tasks
```

Nếu cột không được khai báo identity đúng hoặc code cố đưa giá trị cụ thể vào `GENERATED ALWAYS AS IDENTITY`, câu lệnh có thể lỗi. Với ví dụ này, hãy bỏ `task_id` khỏi danh sách cột INSERT và dùng `RETURNING task_id` để lấy ID được sinh.

### 15.10. Lệnh báo lỗi “current transaction is aborted”

Một câu SQL trước đó trong `BEGIN ... COMMIT` đã thất bại. Kết thúc transaction bằng `ROLLBACK`, rồi chạy lại thao tác hợp lệ trong transaction mới. Không phải lỗi liên quan host/port hay schema.

### 15.11. Nhầm chữ hoa/thường trong tên đối tượng

PostgreSQL chuyển các **identifier không đặt trong dấu ngoặc kép** về chữ thường. Ví dụ:

```sql
CREATE TABLE app.FirstTasks (
    id bigint PRIMARY KEY
);
```

thường tạo bảng có tên logic `app.firsttasks`. Nếu cố tình tạo:

```sql
CREATE TABLE app."FirstTasks" (
    id bigint PRIMARY KEY
);
```

thì về sau phải trích dẫn đúng `"FirstTasks"` khi truy vấn. Để giảm lỗi, nên đặt tên kiểu `lowercase_with_underscores`.

### 15.12. Nhầm role trong connection pool

Ứng dụng đổi cấu hình từ `pg38_app` sang `pg38_runtime` nhưng các connection cũ còn mở bằng role trước. Hãy kiểm tra `current_user` trên chính connection của ứng dụng và dùng quy trình rotation/recycle pool phù hợp khi thay account/quyền.

## 16. Quan sát cấu trúc bằng system catalog

PostgreSQL lưu metadata trong các catalog. Sau khi tạo role, database, schema và bảng, có thể dùng các truy vấn sau để hiểu quan hệ giữa chúng.

### 16.1. Danh sách role trên cluster

```sql
SELECT rolname, rolcanlogin, rolcreatedb, rolsuper
FROM pg_roles
WHERE rolname IN ('pg38_app', 'pg38_runtime')
ORDER BY rolname;
```

`pg_roles` cung cấp thông tin role; đừng tìm các role này trong riêng một schema.

### 16.2. Danh sách database trong cluster

```sql
SELECT datname, pg_get_userbyid(datdba) AS owner_name
FROM pg_database
WHERE datname = 'pg38_demo';
```

`pg_database` quản lý metadata database của cluster.

### 16.3. Schema đang có trong database

Kết nối vào `pg38_demo` rồi chạy:

```sql
SELECT nspname AS schema_name,
       pg_get_userbyid(nspowner) AS owner_name
FROM pg_namespace
WHERE nspname = 'app';
```

`pg_namespace` mô tả schema của **database hiện tại**.

### 16.4. Bảng trong schema

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    c.relkind
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE n.nspname = 'app'
  AND c.relkind IN ('r', 'p')
ORDER BY c.relname;
```

Trong đó `relkind = 'r'` biểu thị ordinary table, `'p'` biểu thị partitioned table. `pg_class` còn chứa metadata về nhiều loại relation khác như index, view hoặc sequence, nên truy vấn trên cố ý lọc.

### 16.5. Hàng trong bảng

```sql
SELECT task_id, title, status, priority
FROM app.tasks
ORDER BY task_id;
```

Đây là **dữ liệu nghiệp vụ**, không phải metadata. Một bảng mới tạo có thể rỗng dù catalog đã ghi nhận sự tồn tại của bảng.

## 17. Khi làm việc theo nhóm, nên phân tách role thế nào?

Sau khi đã hiểu cách tạo đơn giản trong lab, hãy cân nhắc mô hình gần với hệ thống sản xuất:

```text
PostgreSQL cluster
├── Role: app_owner       (NOLOGIN)
│    └── Sở hữu schema/table theo thiết kế
├── Role: app_migrator    (LOGIN, quyền migration phù hợp)
│    └── Chạy Flyway/Liquibase hoặc script DDL
├── Role: app_runtime     (LOGIN, DML cần thiết)
│    └── Ứng dụng Java dùng để chạy API
└── Role: report_reader   (LOGIN, SELECT)
     └── Công cụ báo cáo
```

Chẳng hạn:

```sql
-- Minh họa thuộc tính vai trò, thực hiện bằng admin trong lab riêng.
CREATE ROLE app_owner NOLOGIN;
CREATE ROLE app_runtime LOGIN;
```

**Không chạy những lệnh này trùng tên trên môi trường đang tồn tại nếu chưa xác định ownership.** Để một role migration quản lý object do `app_owner` sở hữu, cần thiết kế role membership/khả năng `SET ROLE` hoặc cách cấp quyền đúng phiên bản. Không mặc nhiên mọi role có `CREATE` đều được `ALTER/DROP` object do role khác sở hữu.

Các lợi ích của tách vai trò:

- Runtime bị hạn chế quyền thay đổi cấu trúc.
- Migration có audit trail và thời điểm triển khai riêng.
- Đọc báo cáo không có quyền ghi.
- Có thể thay/rotate credentials theo từng thành phần.
- Khi một secret bị lộ, phạm vi quyền bị giới hạn hơn so với superuser.

Một database chứa nhiều schema cũng có thể dùng những role khác nhau cho từng module. Nếu các service cần bảo mật mạnh, tách database/instance và chính sách mạng cũng cần được cân nhắc, không chỉ là `GRANT`.

## 18. Dọn dẹp lab mà không xóa nhầm dữ liệu

Bài đã tạo những đối tượng chính:

```text
Role:      pg38_app
Role:      pg38_runtime            (nếu làm phần phân quyền nâng cao)
Database:  pg38_demo
Schema:    app
Tables:    app.tasks
           app.task_notes          (nếu làm phần mở rộng)
```

Nếu muốn **giữ dữ liệu để học các bài tiếp theo**, không cần xóa gì. Đây thường là lựa chọn thuận tiện nhất.

Nếu thật sự muốn dọn toàn bộ lab, cần:

1. Xác nhận database và role là **đối tượng thử nghiệm do chính bạn tạo**.
2. Không còn ứng dụng hoặc connection cần sử dụng database đó.
3. Backup trước nếu dữ liệu còn giá trị.
4. Kết nối tới database **khác** (ví dụ `postgres`), vì không thể drop database đang được connection hiện tại sử dụng.
5. Xóa theo thứ tự phụ thuộc, không dùng tên wildcard hoặc thay lệnh trên production.

Ví dụ **chỉ để tham khảo, không chạy trên database thật**:

```sql
-- Chạy khi đã chuyển sang database postgres, bằng admin lab,
-- và đã đảm bảo không còn session đang kết nối pg38_demo.
DROP DATABASE pg38_demo;

-- Chỉ thực hiện khi xác nhận không còn đối tượng/phụ thuộc khác.
DROP ROLE pg38_runtime;
DROP ROLE pg38_app;
```

Nếu đã tạo bảng/quyền có liên quan role, một lệnh `DROP ROLE` có thể bị từ chối do còn quyền hoặc dependency ở database khác. PostgreSQL làm như vậy để bảo vệ đối tượng; không nên cố sử dụng lệnh xóa quyền toàn diện mà không hiểu phạm vi tác động.

**Không đặt `DROP DATABASE` ở đầu một script học tập “để chạy lại cho sạch”**. Dùng database/schema lab mới hoặc công cụ migration được kiểm soát sẽ an toàn hơn khi dữ liệu có thể cần giữ lại.

## 19. Bài tập tự luyện có lời giải

### Bài 1. Role nào có thể đăng nhập?

Cho:

```sql
CREATE ROLE role_a;
CREATE ROLE role_b LOGIN;
```

**Câu hỏi:** role nào có thể được dùng làm account đăng nhập?

**Lời giải:** `role_b` có `LOGIN`. `role_a` mặc định là role không có `LOGIN`; nó có thể dùng làm role nhóm quyền hoặc owner tùy nhu cầu. Ngoài `LOGIN`, việc đăng nhập thực sự còn phụ thuộc chính sách xác thực và password/certificate.

### Bài 2. Ai sở hữu database?

Quản trị viên chạy:

```sql
CREATE DATABASE demo_training OWNER developer_role;
```

**Câu hỏi:** database thuộc role nào? Lệnh có tự tạo `developer_role` không?

**Lời giải:** `developer_role` được chỉ định làm owner; role đó **phải tồn tại trước** và lệnh `CREATE DATABASE` không tự tạo role. Người thực hiện câu lệnh cần đủ quyền tạo database và gán owner phù hợp.

### Bài 3. Bảng được tạo ở database nào?

Bạn kết nối database `postgres` rồi chạy:

```sql
CREATE SCHEMA training;
CREATE TABLE training.tasks (
    id bigint PRIMARY KEY
);
```

**Câu hỏi:** bảng nằm ở `postgres` hay database mới khác?

**Lời giải:** bảng ở schema `training` của **database `postgres` đang kết nối**. Tạo schema không tạo database mới; phải reconnect tới đúng database khi muốn tạo đối tượng ở đó.

### Bài 4. Vì sao thiếu schema làm truy vấn lỗi?

Bảng `app.tasks` đã tồn tại nhưng:

```sql
SELECT * FROM tasks;
```

báo `relation does not exist`.

**Lời giải:** `search_path` có thể không chứa `app`. Chạy `SELECT * FROM app.tasks;` hoặc kiểm tra và thiết lập search path nếu phù hợp. Đồng thời xác nhận đúng database và quyền `USAGE`/`SELECT`.

### Bài 5. Vì sao `CONNECT` không đủ để đọc bảng?

Một role được cấp:

```sql
GRANT CONNECT ON DATABASE pg38_demo TO report_user;
```

nhưng không đọc được `app.tasks`.

**Lời giải:** `CONNECT` chỉ cho phép vào database. Role còn cần `USAGE` trên schema và `SELECT` trên bảng, theo quyền hiệu lực và owner. Các mức phân quyền không tự thay thế nhau.

### Bài 6. Giá trị mặc định và `NULL`

Bảng `app.tasks` có `status text NOT NULL DEFAULT 'TODO'`. Hai câu sau khác gì?

```sql
INSERT INTO app.tasks(title)
VALUES ('Không truyền status');

INSERT INTO app.tasks(title, status)
VALUES ('Truyền NULL', NULL);
```

**Lời giải:** câu đầu dùng mặc định `'TODO'`; câu sau vi phạm `NOT NULL`, không tự dùng mặc định.

### Bài 7. Tạo role runtime chỉ đọc

**Yêu cầu:** role `report_reader` được đăng nhập và chỉ đọc bảng `app.tasks`.

**Gợi ý:**

```sql
-- Admin tạo role, đặt mật khẩu an toàn qua psql \password.
CREATE ROLE report_reader LOGIN;

-- Sau khi kết nối tới pg38_demo với quyền cấp GRANT:
GRANT CONNECT ON DATABASE pg38_demo TO report_reader;
GRANT USAGE ON SCHEMA app TO report_reader;
GRANT SELECT ON TABLE app.tasks TO report_reader;
```

Kiểm tra role bằng một connection mới. Đừng cấp `SUPERUSER`, `CREATEDB` hay `CREATE` chỉ để nó xem một bảng.

### Bài 8. Phân biệt database và schema

Bạn cần tạo hai module `sales` và `audit`, thường xuyên join dữ liệu giữa chúng.

**Gợi ý:** dùng hai schema trong cùng database có thể thuận tiện, ví dụ `sales.orders` và `audit.events`. Nếu đặt ở hai database khác nhau, PostgreSQL không cho join xuyên database bằng một tên ba thành phần trong SQL thông thường; cần cách tích hợp riêng.

### Bài 9. Vì sao primary key không bảo đảm thứ tự SELECT?

Bảng `app.tasks` có khóa chính `task_id`. Bạn chạy:

```sql
SELECT task_id, title FROM app.tasks;
```

**Lời giải:** PostgreSQL không cam kết thứ tự dòng nếu không có `ORDER BY`. Hãy dùng `ORDER BY task_id` khi muốn hiển thị theo mã tăng dần.

### Bài 10. Transaction bị lỗi ràng buộc

Bạn thực hiện:

```sql
BEGIN;
INSERT INTO app.tasks(title, priority)
VALUES ('Sai dữ liệu', 99);
```

Lệnh `INSERT` lỗi. Tiếp theo nên làm gì?

**Lời giải:** chạy `ROLLBACK;` để kết thúc transaction đang lỗi, sau đó bắt đầu transaction mới nếu muốn thử lại với giá trị hợp lệ. Không tiếp tục `COMMIT` với kỳ vọng PostgreSQL bỏ qua riêng câu thất bại và tự giữ những câu sau.

## 20. Checklist vận hành và ghi nhớ

| Công việc | Lệnh/công cụ | Cần xác nhận |
|---|---|---|
| Xem client PostgreSQL | `psql --version` | Có CLI hoạt động |
| Đăng nhập server lab | `psql -h ... -p ... -U ... -d ...` | Đúng host, port, role, database |
| Xem connection | `\conninfo` / `current_database()` | Không thao tác nhầm database |
| Tạo login role | `CREATE ROLE name LOGIN` | Không có quyền superuser ngoài nhu cầu |
| Đặt mật khẩu | `\password name` trong psql | Không đưa secret vào history/code |
| Tạo database | `CREATE DATABASE name OWNER role` | Owner đúng, câu lệnh ngoài transaction |
| Kết nối database mới | `psql -d name` / `\connect` | Session đang ở database cần dùng |
| Tạo schema | `CREATE SCHEMA app ...` | Namespace và owner phù hợp |
| Tạo table | `CREATE TABLE app.tasks (...)` | Cột, type và constraint đúng |
| Xem cấu trúc | `\dt app.*`, `\d app.tasks` | Bảng tồn tại trong schema mong muốn |
| Chèn hàng | `INSERT ... RETURNING` | ID và giá trị mặc định hợp lệ |
| Đọc và sửa hàng | `SELECT`, `UPDATE ... RETURNING` | Có `WHERE`, đúng số hàng |
| Kiểm tra transaction | `BEGIN` / `COMMIT` / `ROLLBACK` | Không để session ở trạng thái lỗi |
| Tách runtime account | `GRANT CONNECT/USAGE/DML` | App không có DDL hay superuser |
| Kiểm tra quyền thực tế | `SHOW GRANTS` không phải cú pháp PostgreSQL; dùng `\dp` và các hàm `has_*_privilege` | Không áp dụng nhầm cú pháp MySQL |

### Tóm tắt ba bước trọng tâm

**Bước 1 — Tạo login role bằng admin lab:**

```sql
CREATE ROLE pg38_app LOGIN;
-- Trong psql, chạy: \password pg38_app
```

**Bước 2 — Tạo database và gán owner:**

```sql
CREATE DATABASE pg38_demo OWNER pg38_app;
```

**Bước 3 — Kết nối bằng `pg38_app` tới `pg38_demo`, rồi tạo schema và table:**

```sql
CREATE SCHEMA app AUTHORIZATION pg38_app;

CREATE TABLE app.tasks (
    task_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title text NOT NULL,
    status text NOT NULL DEFAULT 'TODO',
    created_at timestamptz NOT NULL DEFAULT now()
);
```

Đoạn bước 3 ở phần tổng kết là **phiên bản tối giản** của bảng thực hành chính, không có các cột `priority`, `due_date` và constraint bổ sung. Nếu đã tạo bảng bằng phiên bản đầy đủ ở phần 8, **không chạy lại câu `CREATE TABLE` tối giản** vì bảng đã tồn tại; hãy xem đây là mẫu nhớ cú pháp cho một lab mới.

**Nguyên tắc cốt lõi:** Role trả lời “**ai được kết nối và làm gì?**”; database trả lời “**đang làm việc trong không gian dữ liệu nào?**”; schema trả lời “**đối tượng thuộc namespace nào?**”; table trả lời “**hàng dữ liệu có cấu trúc ra sao?**”. Khi tạo đúng từng cấp, chọn đúng connection và kiểm tra quyền từ chính tài khoản ứng dụng, bạn đã có nền tảng để phát triển các truy vấn và chức năng PostgreSQL tiếp theo.

