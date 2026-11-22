# Mô hình máy khách và máy chủ trong một phiên làm việc PostgreSQL

Khi một ứng dụng Java gửi câu lệnh `SELECT`, dữ liệu không được đọc trực tiếp từ file PostgreSQL bởi ứng dụng đó. Ứng dụng đóng vai trò **máy khách (client)**: mở kết nối tới PostgreSQL, gửi yêu cầu qua giao thức của PostgreSQL, nhận dữ liệu và đóng hoặc tái sử dụng kết nối. Phía PostgreSQL là **máy chủ (server)**: xác thực yêu cầu, quản lý phiên, xử lý SQL, điều phối giao dịch và truy cập dữ liệu lưu trữ.

Đây là nền tảng của kiến trúc PostgreSQL: **client–server**, mỗi kết nối trực tiếp tới PostgreSQL được phục vụ bởi một **backend process** riêng trong mô hình tiến trình truyền thống của PostgreSQL. Nhiều backend cùng dùng những tài nguyên chung của một PostgreSQL instance, chẳng hạn shared memory, buffer pool, hệ thống khóa, WAL và các database nằm trong cùng cluster.

Bài học đi từ lúc ứng dụng bắt đầu kết nối cho tới khi kết thúc một phiên: xác định host/port/database, xác thực, tạo backend, gửi SQL, chạy transaction, quan sát trạng thái kết nối, rồi đóng kết nối. Các ví dụ sử dụng PostgreSQL hiện đại (chẳng hạn PostgreSQL 16) và công cụ `psql`.

## 1. Các thành phần trong mô hình client–server

Xét một hệ thống bán hàng đơn giản có ứng dụng web, một công cụ quản trị và PostgreSQL:

~~~text
   Ứng dụng Java             Công cụ psql              Công cụ báo cáo
   (PostgreSQL JDBC)         (libpq)                   (driver SQL)
          |                     |                            |
          | TCP/IP              | TCP hoặc Unix socket        | TCP/IP
          +---------------------+----------------------------+
                                |
                                v
                      PostgreSQL server
                   (tiến trình quản lý chính)
                                |
                 +--------------+---------------+
                 |              |               |
                 v              v               v
           Backend #1      Backend #2       Backend #3
           cho Java        cho psql         cho báo cáo
                 |              |               |
                 +--------------+---------------+
                                |
                Bộ nhớ và tài nguyên dùng chung
            shared_buffers, locks, WAL, catalog...
                                |
                                v
                  Các tệp dữ liệu trong PGDATA
~~~

Trong sơ đồ:

- **Client** là chương trình phát sinh yêu cầu, có thể là `psql`, pgAdmin, DBeaver, Java JDBC, Python hoặc một dịch vụ khác.
- **Connection** là kênh giao tiếp giữa client và PostgreSQL. Kết nối có thể dùng TCP/IP hoặc Unix-domain socket khi môi trường hỗ trợ.
- **PostgreSQL server** là instance quản lý một database cluster và chấp nhận kết nối theo cấu hình.
- **Backend process** là tiến trình phía PostgreSQL dành cho một kết nối trực tiếp và thực thi yêu cầu của phiên đó.
- **Shared resources** hỗ trợ các backend cùng truy cập dữ liệu một cách nhất quán, nhưng không biến tất cả kết nối thành một tiến trình SQL duy nhất.

### Cluster, database và session khác nhau ra sao?

| Thuật ngữ | Nghĩa trong PostgreSQL | Ví dụ |
| --- | --- | --- |
| **Cluster** | Tập các database do một PostgreSQL instance quản lý | PGDATA có `postgres` và `shopdb` |
| **Database** | Một không gian chứa schema, table, view và các đối tượng khác | `shopdb` |
| **Role** | Danh tính có thể được dùng để đăng nhập hoặc nhận quyền | `shop_app` |
| **Connection** | Kênh truyền thông client–server | TCP tới `127.0.0.1:5432` |
| **Session** | Phiên làm việc từ khi kết nối được thiết lập tới khi kết thúc | Phiên của một `psql` |
| **Transaction** | Nhóm thao tác SQL được commit hoặc rollback | `BEGIN ... COMMIT` |
| **Backend process** | Tiến trình server thực hiện yêu cầu của một kết nối | PID hiển thị qua `pg_backend_pid()` |

Một **session có thể chứa nhiều transaction**. Ngược lại, một transaction bình thường chạy trong phạm vi một session. Các cấu hình của phiên, bảng tạm và câu lệnh chuẩn bị có vòng đời khác với những thay đổi dữ liệu được quản lý bởi transaction.

## 2. Tiến trình máy chủ và backend process

Khi PostgreSQL khởi động, tiến trình chính (thường được gọi là **postmaster**, cùng chương trình thực thi `postgres`) chuẩn bị các tài nguyên chung và lắng nghe kết nối.

Khi có một client kết nối thành công, PostgreSQL tổ chức một backend process để phục vụ kết nối đó. Backend chịu trách nhiệm giao tiếp với client, xử lý yêu cầu SQL và tham gia cơ chế quản lý transaction.

~~~text
PostgreSQL instance
│
├── Postmaster / main server process
│   ├── Tiếp nhận kết nối mới
│   ├── Quản lý tiến trình con và vòng đời server
│   └── Điều phối tài nguyên hệ thống
│
├── Client backend: PID 30101  ← phiên Java #1
├── Client backend: PID 30102  ← phiên Java #2
├── Client backend: PID 30103  ← phiên psql
│
├── Background processes
│   ├── Checkpointer
│   ├── Background writer
│   ├── WAL writer
│   ├── Autovacuum processes
│   └── Các tiến trình hỗ trợ khác tùy cấu hình
│
└── Shared memory và tệp trong PGDATA
~~~

**Điểm phân biệt quan trọng:** backend của client và những background process không phải cùng một loại. Một backend gắn với phiên kết nối, còn background process chạy những công việc chung như ghi dữ liệu, ghi WAL, tự động bảo trì hoặc hỗ trợ replication.

### Một kết nối có phải một thread?

Trong mô hình PostgreSQL truyền thống, mỗi kết nối client trực tiếp thông thường dùng **một tiến trình hệ điều hành phía server**, thay vì một luồng Java hoặc một thread dùng chung cho mọi kết nối. Vì vậy, việc mở rất nhiều kết nối đồng thời có chi phí về bộ nhớ, quản lý tiến trình và tài nguyên.

Kết luận này áp dụng cho **client nối trực tiếp tới PostgreSQL**. Nếu có proxy/pooler như PgBouncer, số kết nối client hướng vào pooler có thể **khác** số kết nối thực sự đang mở tới PostgreSQL.

### Backend dùng chung và riêng những gì?

| Tài nguyên | Phạm vi điển hình |
| --- | --- |
| `shared_buffers` và các cấu trúc shared memory | Nhiều backend trong cùng instance dùng chung |
| Dữ liệu bảng, index và WAL | Tài nguyên chung của database/cluster |
| Transaction ID, cơ chế khóa, MVCC | Được điều phối giữa các backend |
| Một PID backend | Thuộc tiến trình phục vụ một kết nối trực tiếp |
| Tham số `SET` trong session | Thường chỉ có hiệu lực trong session ấy |
| Bảng tạm và prepared statement cấp session | Gắn với session tương ứng |
| Kết quả truy vấn đang thực thi | Thuộc công việc của backend, gửi lại client |

Từ đó hiểu được hai hiện tượng tưởng trái ngược: **nhiều phiên cùng nhìn một bảng dữ liệu**, nhưng **đổi `search_path` hoặc tạo bảng tạm trong phiên A không đồng nghĩa phiên B có cùng trạng thái ấy**.

## 3. Từ client tới PostgreSQL: host, port, database, user

Để tạo một kết nối, client thường cung cấp ít nhất các thuộc tính:

~~~text
Host      = db.example.internal
Port      = 5432
Database  = shopdb
User      = shop_app
Password  = bí mật xác thực nếu được yêu cầu
TLS       = tùy cấu hình và chính sách môi trường
~~~

Ví dụ lệnh `psql`:

~~~bash
psql \
  -h 127.0.0.1 \
  -p 5432 \
  -U shop_app \
  -d shopdb \
  -W
~~~

`-W` yêu cầu `psql` chủ động hỏi mật khẩu. Nó không thay thế cấu hình xác thực phía server. `shop_app` và `shopdb` là tên **giả định**: thay bằng role/database đã tồn tại và được cấp quyền.

### 3.1. TCP/IP và Unix-domain socket

Trong môi trường Unix/Linux, hai kiểu kết nối thường gặp là:

~~~bash
# TCP/IP qua loopback:
psql -h 127.0.0.1 -p 5432 -U shop_app -d shopdb

# Unix socket: bỏ -h khi công cụ tìm được socket mặc định;
# hoặc chỉ rõ thư mục socket, ví dụ:
psql -h /var/run/postgresql -p 5432 -U shop_app -d shopdb
~~~

Khác biệt:

- `127.0.0.1` là địa chỉ TCP loopback của máy chạy client.
- Đường dẫn `/var/run/postgresql` trong `-h` chỉ định **thư mục chứa Unix socket**, không phải địa chỉ IP.
- Kết nối Unix socket có thể được cấu hình xác thực bằng phương thức `peer`; kết nối TCP chịu các quy tắc `host` tương ứng trong `pg_hba.conf`.
- `localhost` có thể được phân giải thành IPv4 hoặc IPv6; đừng mặc định nó luôn tương đương `127.0.0.1` trong mọi môi trường.

Trên Windows, cơ chế kết nối cục bộ không giống Unix socket truyền thống của Linux; hãy dùng host/port TCP thích hợp.

Nếu ứng dụng chạy trong một container khác, `127.0.0.1` bên trong container ấy trỏ về **chính container ứng dụng**. Với Docker Compose cùng mạng, thường dùng **tên service PostgreSQL** làm host và cổng nội bộ `5432`.

### 3.2. Một session kết nối tới một database

Một kết nối PostgreSQL được thiết lập tới **một database cụ thể**. Trong `psql`, đổi database bằng meta-command `\connect` sẽ tạo **kết nối mới**:

~~~text
\connect shopdb shop_app
~~~

PostgreSQL không dùng cú pháp `USE other_database;` như một số hệ quản trị khác. Một phiên SQL bình thường không thể truy vấn trực tiếp một bảng bất kỳ trong database khác chỉ bằng cách thêm tiền tố tên database. Khi cần kết nối giữa database, đó là thiết kế riêng, ví dụ dùng `postgres_fdw` hoặc `dblink`, với quyền và cấu hình phù hợp.

## 4. Vòng đời kết nối: từ bắt tay tới phiên sẵn sàng

Một chuỗi đơn giản hóa:

~~~text
Client                             PostgreSQL
  |                                     |
  |-- Mở TCP / Unix socket ----------->|
  |                                     |
  |-- Thương lượng TLS (nếu dùng) ----->|
  |<------- Phản hồi thương lượng ------|
  |                                     |
  |-- Gửi startup parameters --------->|
  |   user, database, application_name  |
  |                                     |
  |<-- Yêu cầu xác thực (nếu cần) ------|
  |-- Trả lời xác thực ---------------->|
  |                                     |
  |<-- Chấp nhận kết nối / thông số ----|
  |<-- Ready for Query -----------------|
  |                                     |
  |-- SQL query / bind / execute ------>|
  |<-- Row data / command status -------|
  |<-- Ready for Query -----------------|
  |                                     |
  |-- Các yêu cầu tiếp theo ----------->|
  |<-- Các kết quả tiếp theo -----------|
  |                                     |
  |-- Kết thúc kết nối ---------------->|
  |                                     |
~~~

Đây là mô hình khái niệm, không phải bản chép đầy đủ mọi gói tin của PostgreSQL wire protocol. Việc thương lượng có thể thêm bước như GSS encryption, lựa chọn giao thức xác thực và các thông điệp đặc thù của driver.

### Bước 1: server có lắng nghe không?

PostgreSQL cần đang chạy, lắng nghe tại địa chỉ và cổng phù hợp. Các cấu hình liên quan thường là:

- `listen_addresses`: những địa chỉ TCP mà server lắng nghe.
- `port`: cổng PostgreSQL, thường là `5432`.
- `unix_socket_directories`: nơi tạo Unix socket trên hệ điều hành hỗ trợ.
- Firewall, routing, container networking hoặc chính sách mạng phía nhà cung cấp.

Ví dụ một server chỉ nghe `localhost` sẽ không tự nhiên nhận kết nối TCP từ một máy khác, ngay cả khi user/password đúng.

### Bước 2: xác thực và quyền kết nối

Khi client tới được server, PostgreSQL đối chiếu yêu cầu với cấu hình **`pg_hba.conf`** để xác định cách xác thực. Những quy tắc khớp thường xét:

- Kiểu kết nối: `local` (Unix socket), `host`, `hostssl` hoặc biến thể phù hợp.
- Database đích.
- Role đăng nhập.
- Địa chỉ nguồn của client trong trường hợp TCP.
- Phương thức xác thực, ví dụ `scram-sha-256`, `peer` hoặc phương thức được quản trị chọn.

PostgreSQL xét các bản ghi `pg_hba.conf` **theo thứ tự**; bản ghi đầu tiên khớp quyết định cách xác thực. Khi một bản ghi đã khớp nhưng xác thực thất bại, PostgreSQL không tự chuyển sang bản ghi sau để thử phương thức khác.

Ngoài xác thực, role cần có thuộc tính `LOGIN` và quyền `CONNECT` đối với database phù hợp. Đăng nhập thành công không đồng nghĩa được `SELECT` mọi bảng.

### Bước 3: backend và trạng thái phiên

Sau khi kết nối được thiết lập, backend xử lý các yêu cầu của phiên. Client nhận thông tin phiên từ server và có thể bắt đầu gửi truy vấn. Tên ứng dụng, database, role, thiết lập timezone và một số thông tin protocol trở thành một phần ngữ cảnh của phiên.

Một client có thể kết nối thành công nhưng lỗi khi thực thi truy vấn vì thiếu quyền trên schema/table. **Lỗi kết nối, lỗi xác thực và lỗi quyền SQL là ba nhóm khác nhau**.

## 5. Luồng xử lý một câu SQL ở phía server

Sau khi kết nối, client gửi câu SQL, ví dụ:

~~~sql
SELECT order_id, total_amount
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 10;
~~~

Backend xử lý yêu cầu thông qua các giai đoạn logic:

~~~text
SQL từ client
       |
       v
  Parse (phân tích cú pháp)
       |
       v
  Analyze / Rewrite
  - hiểu cột, bảng, kiểu dữ liệu
  - kiểm tra quyền, đối tượng liên quan
  - áp dụng một số quy tắc rewrite
       |
       v
  Planner / Optimizer
  - chọn scan / index / join / sort
  - ước lượng chi phí dựa trên thống kê
       |
       v
  Executor
  - chạy plan
  - đọc trang dữ liệu qua buffer manager
  - tuân theo MVCC, khóa và transaction
       |
       v
  Kết quả trả qua protocol tới client
~~~

Trong thực tế, PostgreSQL có thể chuẩn bị và tái sử dụng câu SQL, cache những thành phần thích hợp hoặc thực hiện các bước protocol khác; không nên hiểu sơ đồ trên là mỗi lần gọi đều bắt buộc lập lại toàn bộ công việc theo đúng cách giống nhau.

### Backend và shared buffers

Backend không chỉ đọc file PostgreSQL trực tiếp rồi gửi về. Nó thường dùng các thành phần quản lý buffer và I/O:

~~~text
Backend
   |
   v
Shared buffers  <---->  File dữ liệu trên storage
   |
   +----> Lock / MVCC / WAL tùy thao tác
~~~

Trang dữ liệu được truy cập có thể đang ở `shared_buffers` hoặc cần nạp từ thiết bị lưu trữ. Với câu ghi, thay đổi trên trang trong bộ nhớ và cơ chế WAL phối hợp để bảo đảm khả năng crash recovery theo quy tắc durability của PostgreSQL.

Nhiều backend cùng dùng buffer pool nhưng có **trạng thái phiên và transaction riêng**; PostgreSQL phối hợp các truy cập bằng MVCC và cơ chế khóa thay vì trao quyền ghi tự do lên file dữ liệu.

### Một câu SQL lớn có luôn chỉ chạy trên một tiến trình?

Backend của client là đầu mối xử lý session, nhưng PostgreSQL có thể sử dụng **parallel query workers** cho một số truy vấn phù hợp. Vì vậy, “một backend cho một kết nối” không có nghĩa một câu truy vấn không bao giờ dùng thêm tiến trình hỗ trợ.

## 6. Session khác transaction như thế nào?

Đây là điểm đặc biệt quan trọng trong vận hành.

**Session** bắt đầu khi kết nối đã được thiết lập và kết thúc khi kết nối đóng. Trong một session, client có thể lần lượt chạy:

~~~text
Session A
|
|-- SELECT 1;                     transaction ngầm 1
|
|-- BEGIN;
|     UPDATE ...;
|     SELECT ...;
|   COMMIT;                        transaction 2
|
|-- SELECT now();                  transaction ngầm 3
|
|-- BEGIN;
|     UPDATE ...;
|   ROLLBACK;                      transaction 4
|
|-- Kết thúc kết nối
~~~

Mô tả “transaction ngầm” ở trên phù hợp khi `psql` hoặc driver hoạt động với chế độ **autocommit** thông thường: mỗi câu SQL riêng lẻ ngoài `BEGIN` sẽ được xử lý trong giao dịch riêng. PostgreSQL không có một thiết lập server “mọi session luôn autocommit” giống hệt cách một số thư viện JDBC diễn đạt; cách client nhóm câu SQL và gửi `BEGIN` ảnh hưởng ranh giới transaction.

### 6.1. Ví dụ transaction tường minh

~~~sql
BEGIN;

UPDATE lab_accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE lab_accounts
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
~~~

Đây là ví dụ cú pháp cho bảng `lab_accounts` giả định. Hai `UPDATE` thuộc cùng một transaction; nếu xảy ra lỗi hoặc cần hủy, `ROLLBACK` loại bỏ những thay đổi chưa commit.

Session vẫn **tiếp tục tồn tại sau `COMMIT`**. Client có thể gửi câu SQL khác trên cùng kết nối.

### 6.2. Khi transaction gặp lỗi

Trong PostgreSQL, khi một câu SQL làm transaction hiện tại rơi vào trạng thái lỗi, các câu SQL tiếp theo trong cùng transaction thường bị từ chối cho tới khi thực hiện `ROLLBACK` hoặc quay về savepoint phù hợp.

Ví dụ:

~~~sql
BEGIN;
SELECT 1 / 0;   -- Cố ý tạo lỗi.
SELECT 2;       -- Gặp lỗi vì transaction đã bị đánh dấu aborted.
ROLLBACK;
SELECT 3;       -- Chạy được trong transaction mới/implicit.
~~~

Đây là khác biệt vận hành quan trọng: **lỗi của một câu lệnh có thể làm cả transaction chưa commit không thể tiếp tục**, nhưng không nhất thiết đóng toàn bộ session.

### 6.3. SET của session và SET LOCAL của transaction

PostgreSQL hỗ trợ tham số cấu hình có phạm vi phiên:

~~~sql
SHOW search_path;

SET search_path = public;
SHOW search_path;
~~~

Nếu `SET` thành công và được commit khi nằm trong transaction, giá trị thông thường tiếp tục có hiệu lực ở session cho tới khi đổi/reset hoặc session đóng.

Trong một transaction, có thể đặt giá trị chỉ cho transaction:

~~~sql
BEGIN;
SET LOCAL statement_timeout = '2s';

SELECT current_setting('statement_timeout');

COMMIT;

SELECT current_setting('statement_timeout');
~~~

Sau `COMMIT`, thiết lập `SET LOCAL` không còn áp dụng; giá trị trước đó của session hoặc cấu hình nền được khôi phục. Điều này hữu ích để giới hạn thời gian cho một nhóm câu SQL mà không tác động tới mọi truy vấn về sau trong session.

## 7. Những thông tin và đối tượng sống theo phiên

Không phải mọi dữ liệu phát sinh trong một session đều được chia sẻ với các session khác.

### 7.1. Tham số session

~~~sql
SET application_name = 'psql-lab-A';
SET TIME ZONE 'Asia/Ho_Chi_Minh';

SHOW application_name;
SHOW TimeZone;
~~~

Các thiết lập này có thể ảnh hưởng cách phiên xử lý/hiển thị một số giá trị và cách phiên xuất hiện trong công cụ giám sát. Chúng **không đổi timezone hoặc application_name của mọi kết nối khác**.

### 7.2. Bảng tạm (temporary table)

~~~sql
CREATE TEMP TABLE session_notes (
    id integer,
    note text
);

INSERT INTO session_notes (id, note)
VALUES (1, 'Chi phien nay nhin thay bang tam');

SELECT * FROM session_notes;
~~~

Bảng tạm thường gắn với session tạo ra nó; session khác không truy cập trực tiếp bảng tạm ấy qua tên thông thường. Theo mặc định, nếu không dùng `ON COMMIT DROP` hoặc `ON COMMIT DELETE ROWS`, bảng tạm có thể còn tồn tại sau `COMMIT` trong cùng session và sẽ bị loại bỏ khi session kết thúc.

**Phân biệt:** bảng tạm theo session không có nghĩa mọi dòng trong bảng tạm bỏ qua quy tắc transaction. Một thao tác `INSERT` vào bảng tạm trong transaction bị rollback vẫn chịu cơ chế rollback phù hợp.

### 7.3. Prepared statement

~~~sql
PREPARE find_order(bigint) AS
SELECT order_id, total_amount
FROM orders
WHERE order_id = $1;

EXECUTE find_order(1001);
~~~

Ví dụ này giả định bảng `orders` tồn tại. Câu `PREPARE` tạo prepared statement cấp session; session khác không tự có tên `find_order`. Khi session kết thúc, prepared statement cấp session không còn được sử dụng qua kết nối đó.

Driver như JDBC có thể sử dụng PostgreSQL extended query protocol và prepared statements theo chính sách riêng của driver. Không nên giả định tên/đời sống prepared statement trong JDBC luôn trùng với việc viết `PREPARE ... EXECUTE` bằng SQL.

### 7.4. Session role và quyền

Các hàm thường dùng:

~~~sql
SELECT
    session_user,
    current_user,
    current_database();
~~~

`session_user` thường là role dùng để bắt đầu phiên, còn `current_user` là danh tính được sử dụng khi kiểm tra quyền tại ngữ cảnh hiện tại. Một số cơ chế như `SET ROLE` hoặc các hàm `SECURITY DEFINER` có thể làm chúng khác nhau.

Không nên lấy tên ứng dụng (application_name) hoặc địa chỉ kết nối làm bằng chứng rằng câu SQL có quyền truy cập; phải xét quyền role và các chính sách bảo mật đang áp dụng.

## 8. Tự kiểm tra một session bằng psql

Đăng nhập tới một PostgreSQL instance thực hành mà bạn được phép truy cập:

~~~bash
psql -h 127.0.0.1 -p 5432 -U lab_user -d lab_db
~~~

Lệnh trên giả định role `lab_user` và database `lab_db` đã tồn tại. Khi kết nối thành công, có thể chạy:

~~~sql
SELECT
    current_database() AS database_name,
    session_user AS login_role,
    current_user AS effective_role,
    pg_backend_pid() AS backend_pid,
    inet_client_addr() AS client_address,
    inet_client_port() AS client_port,
    inet_server_addr() AS server_address,
    inet_server_port() AS server_port;
~~~

| Hàm/thông tin | Giúp xác nhận |
| --- | --- |
| `current_database()` | Database của kết nối hiện tại |
| `session_user` | Role bắt đầu session |
| `current_user` | Role hiệu lực trong ngữ cảnh hiện tại |
| `pg_backend_pid()` | PID của backend process phục vụ kết nối |
| `inet_client_addr()` | Địa chỉ IP phía client nếu là kết nối TCP |
| `inet_client_port()` | Cổng nguồn phía client với TCP |
| `inet_server_addr()` | Địa chỉ IP phía server mà kết nối dùng |
| `inet_server_port()` | Cổng server cho kết nối TCP |

**Lưu ý:** các hàm `inet_*` có thể trả về `NULL` với kết nối Unix-domain socket. Điều đó không có nghĩa session lỗi hoặc không có backend.

Trong `psql`, dùng:

~~~text
\conninfo
~~~

Lệnh này hiển thị thông tin kết nối hiện tại, gồm user, database và địa chỉ/cổng hoặc socket tùy phương thức.

### Cách nhận biết hai kết nối độc lập

Mở hai cửa sổ `psql` cùng kết nối tới `lab_db`. Trong mỗi cửa sổ:

~~~sql
SELECT pg_backend_pid(), current_database(), current_user;
~~~

Hai kết nối trực tiếp đang đồng thời hoạt động thông thường có **hai backend PID khác nhau**. Nếu bạn đóng rồi mở lại kết nối, PID có thể thay đổi; PID không phải mã định danh vĩnh viễn của người dùng hoặc của lịch sử nghiệp vụ.

## 9. Thực nghiệm hai session cùng truy cập dữ liệu

Thí nghiệm giúp thấy rõ: session có trạng thái độc lập, nhưng hai session cùng đọc/ghi **cùng dữ liệu đã commit** theo quy tắc MVCC và isolation.

Chuẩn bị một lần bằng role có quyền tạo bảng trong schema thực hành:

~~~sql
CREATE TABLE IF NOT EXISTS session_lab_accounts (
    account_id integer PRIMARY KEY,
    balance integer NOT NULL
);

INSERT INTO session_lab_accounts (account_id, balance)
VALUES (1, 1000)
ON CONFLICT (account_id)
DO UPDATE SET balance = EXCLUDED.balance;
~~~

**Chỉ chạy trong database lab**; đoạn `ON CONFLICT ... DO UPDATE` có chủ đích đặt lại `balance = 1000` nếu hàng đã có, nên không thích hợp chạy trên dữ liệu nghiệp vụ thật.

Giả sử cả hai cửa sổ `psql` đều đang chạy ở mức isolation mặc định `READ COMMITTED` và được phép `SELECT` trên bảng. Nếu session B không có quyền viết, vẫn có thể quan sát phần đọc.

### Bước 1: Session A bắt đầu thay đổi chưa commit

Trong cửa sổ A:

~~~sql
SET application_name = 'session-lab-A';

BEGIN;
UPDATE session_lab_accounts
SET balance = 900
WHERE account_id = 1;

SELECT balance
FROM session_lab_accounts
WHERE account_id = 1;
-- A thấy 900 do chính transaction của A vừa cập nhật.
~~~

**Đừng commit ngay.** Giữ transaction A mở để chạy bước 2.

### Bước 2: Session B đọc cùng hàng

Trong cửa sổ B:

~~~sql
SET application_name = 'session-lab-B';

SELECT pg_backend_pid() AS pid_b;

SELECT balance
FROM session_lab_accounts
WHERE account_id = 1;
-- B thông thường vẫn thấy 1000 ở READ COMMITTED.
~~~

Vì A chưa commit, session B không thấy thay đổi của A qua `SELECT` thông thường ở `READ COMMITTED`. Đây là ví dụ tính cô lập của transaction, không phải vì hai session lưu hai bản sao bảng độc lập.

### Bước 3: Session A commit

Trong cửa sổ A:

~~~sql
COMMIT;
~~~

### Bước 4: Session B đọc lần nữa

~~~sql
SELECT balance
FROM session_lab_accounts
WHERE account_id = 1;
-- B thấy 900 trong giao dịch đọc mới ở READ COMMITTED.
~~~

Từ thí nghiệm:

- A và B có **backend riêng**, nhưng cùng truy cập một bảng.
- Trước `COMMIT`, thay đổi của A chưa xuất hiện trong consistent read thông thường của B.
- Sau `COMMIT`, câu `SELECT` mới của B ở `READ COMMITTED` có thể nhìn thấy dữ liệu đã commit.
- Session không tự đóng khi transaction hoàn thành.

**Ngoại lệ cần nhớ:** ở `REPEATABLE READ`, nếu B đã bắt đầu transaction và tạo ảnh chụp dữ liệu trước khi A commit, các consistent reads tiếp theo của B có thể tiếp tục nhìn ảnh chụp cũ trong cùng transaction. Đừng kết luận “sau commit, mọi phiên đang chạy đều lập tức nhìn kết quả mới” mà bỏ qua isolation level và kiểu đọc.

Sau thí nghiệm, ở một session không còn transaction mở:

~~~sql
DROP TABLE IF EXISTS session_lab_accounts;
~~~

Chỉ thực hiện thao tác dọn dẹp khi đã xác nhận đây là bảng thử nghiệm và không còn ứng dụng nào cần dữ liệu đó.

## 10. Quan sát các session bằng pg_stat_activity

PostgreSQL cung cấp view `pg_stat_activity` để quan sát hoạt động server và các backend. Đối với phiên client, những cột phổ biến gồm:

| Cột | Nội dung |
| --- | --- |
| `pid` | PID của backend |
| `usename` | Tên role đăng nhập được ghi nhận |
| `datname` | Database của kết nối |
| `application_name` | Tên ứng dụng do client thiết lập |
| `client_addr` | Địa chỉ IP client khi có |
| `client_port` | Cổng nguồn hoặc mã đặc biệt tùy loại kết nối |
| `backend_start` | Thời điểm backend được tạo |
| `xact_start` | Thời điểm transaction hiện tại bắt đầu, nếu có |
| `query_start` | Thời điểm câu truy vấn được ghi nhận bắt đầu |
| `state` | Trạng thái hiện tại, như `active` hoặc `idle` |
| `wait_event_type`, `wait_event` | Loại sự kiện chờ, nếu backend đang chờ |
| `query` | Câu truy vấn gần đây/đang chạy tùy trạng thái và quyền xem |

Ví dụ truy vấn giám sát:

~~~sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    client_addr,
    backend_start,
    xact_start,
    state,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE backend_type = 'client backend'
  AND datname = current_database()
ORDER BY backend_start, pid;
~~~

Trong PostgreSQL hiện đại, `pg_stat_activity` còn chứa các tiến trình nền; điều kiện `backend_type = 'client backend'` giúp tập trung vào các kết nối client.

### Quyền xem trạng thái của session khác

Người dùng thường có thể xem thông tin đầy đủ của **chính các phiên thuộc role của họ**, nhưng một số trường từ phiên khác có thể bị ẩn hoặc giới hạn khi thiếu quyền. Role giám sát được cấp `pg_read_all_stats` hoặc quyền tương ứng có thể xem nhiều thông tin hơn. Không cấp superuser chỉ để đọc một dashboard nếu quyền giám sát chuyên biệt là đủ.

### Một session có thể ở những trạng thái nào?

| `state` | Cách hiểu | Hướng điều tra |
| --- | --- | --- |
| `active` | Backend đang thực hiện một query | Query chạy lâu, CPU/I/O, khóa chờ |
| `idle` | Phiên đang chờ lệnh tiếp theo từ client | Pool giữ kết nối hay ứng dụng chưa đóng? |
| `idle in transaction` | Client chưa gửi lệnh mới nhưng transaction vẫn mở | Có giữ khóa/snapshot lâu không? |
| `idle in transaction (aborted)` | Transaction đã lỗi và đang chờ client rollback | Ứng dụng có quên xử lý lỗi/rollback không? |

`state = 'active'` không nhất thiết có nghĩa backend **đang dùng CPU**: nó có thể đang chờ I/O hoặc chờ lock. Để hiểu thêm, xem `wait_event_type` và `wait_event` cùng với query và log.

### Theo dõi giao dịch mở lâu

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
  AND datname = current_database()
ORDER BY xact_start;
~~~

Giao dịch kéo dài có thể giữ khóa, ảnh hưởng vacuum và làm tăng phiên bản hàng cần lưu. Tuy nhiên, thời lượng transaction **một mình** chưa đủ kết luận là lỗi; tác vụ ETL hay migration có thể được thiết kế chạy lâu. Cần kết hợp thông tin ứng dụng và mức ảnh hưởng.

## 11. Session tồn tại bao lâu? Khi nào kết nối kết thúc?

Một session thường kết thúc khi:

- Client đóng kết nối rõ ràng, ví dụ `psql` dùng `\q` hoặc ứng dụng gọi `Connection.close()`.
- Ứng dụng hoặc hệ điều hành ngắt kết nối.
- PostgreSQL bị dừng hoặc backend bị kết thúc.
- Cấu hình timeout áp dụng cho tình huống tương ứng.

Khi session kết thúc, tài nguyên phiên như bảng tạm và prepared statement cấp session được dọn dẹp theo cơ chế PostgreSQL. Những thay đổi **đã commit** vào bảng thường vẫn còn; các transaction chưa commit không được coi là đã commit chỉ vì mất kết nối.

### Đóng connection trong Java có luôn đóng kết nối PostgreSQL?

Không nhất thiết theo nghĩa vật lý. Nếu dùng connection pool như HikariCP, lệnh `Connection.close()` của ứng dụng thường **trả kết nối về pool** để tái sử dụng, thay vì đóng socket/backend ngay lập tức. Session PostgreSQL có thể còn sống sau khi request HTTP hoàn tất.

Sự khác nhau này giải thích vì sao dashboard có thể thấy hàng chục kết nối `idle` mặc dù ứng dụng hiện không xử lý nhiều truy vấn.

### Một số timeout cần nhận biết

~~~sql
SHOW statement_timeout;
SHOW lock_timeout;
SHOW idle_in_transaction_session_timeout;
SHOW idle_session_timeout;
~~~

| Tham số | Mục đích |
| --- | --- |
| `statement_timeout` | Giới hạn thời gian thực thi câu lệnh phù hợp |
| `lock_timeout` | Giới hạn thời gian chờ lấy lock trong các tình huống được áp dụng |
| `idle_in_transaction_session_timeout` | Có thể kết thúc session đang idle khi vẫn mở transaction quá thời gian cấu hình |
| `idle_session_timeout` | Có thể kết thúc session idle ngoài transaction quá thời gian cấu hình |

Những tham số này có thể đặt theo database, role, session hoặc cấu hình server tùy trường hợp. Không tự đặt timeout quá ngắn trên production: công việc hợp lệ có thể bị hủy, và pooler có thể không xử lý như mong muốn nếu server đóng kết nối mà client tưởng vẫn còn dùng được.

## 12. Connection pool và số backend process

Mở kết nối PostgreSQL có chi phí: socket, bắt tay, xác thực, khởi tạo trạng thái và một backend process tương ứng. Nếu mỗi request web tạo một kết nối mới rồi đóng ngay, ứng dụng có thể gây áp lực đáng kể lên server.

**Connection pool** giữ một tập kết nối sẵn có để nhiều request dùng lại:

~~~text
100 request HTTP đồng thời
             |
             v
         Java service
             |
             v
       Connection pool
       tối đa 20 kết nối
             |
             v
       PostgreSQL server
       khoảng 20 backend cho pool đó
~~~

Mẫu trên là ví dụ minh họa: số backend thực tế còn phụ thuộc kết nối của công cụ khác, nhiều instance ứng dụng và trạng thái pool.

### Client-side pool

Trong Java, HikariCP thường giữ các đối tượng `java.sql.Connection` và quản lý vòng đời của chúng:

- Request mượn connection.
- Chạy SQL/transaction cần thiết.
- Commit hoặc rollback theo nghiệp vụ.
- Trả connection về pool.

Khi trả connection, pool cần bảo đảm trạng thái giao dịch và các thuộc tính phiên được xử lý phù hợp. Nếu một request thay đổi `search_path`, role hoặc trạng thái session rồi trả kết nối mà không reset, request tiếp theo có thể chịu ảnh hưởng không mong muốn.

### PgBouncer và pooling ở phía server

PgBouncer là một chương trình proxy/pooler đứng giữa client và PostgreSQL. Nó có các chế độ pooling khác nhau:

| Chế độ | Quan hệ client và backend PostgreSQL |
| --- | --- |
| **Session pooling** | Một server connection được gắn cho client trong suốt session client |
| **Transaction pooling** | Server connection có thể được trả lại pool sau mỗi transaction |
| **Statement pooling** | Chia sẻ theo đơn vị statement, có nhiều hạn chế hơn |

**Hệ quả quan trọng:** với **transaction pooling**, những tính năng yêu cầu giữ nguyên **cùng một session PostgreSQL qua nhiều transaction** có thể không hoạt động như khi kết nối trực tiếp. Ví dụ cần xem xét `SET` cấp session, bảng tạm, prepared statement cấp session hoặc những thao tác dựa vào backend PID ổn định.

Một số phiên bản/configuration PgBouncer có cơ chế hỗ trợ một số prepared statements qua transaction pooling, nhưng không nên mặc định mọi trạng thái phiên đều được giữ nguyên.

### max_connections không phải thước đo throughput

~~~sql
SHOW max_connections;

SELECT COUNT(*) AS client_backends
FROM pg_stat_activity
WHERE backend_type = 'client backend';
~~~

`max_connections` đặt giới hạn kết nối server theo cơ chế PostgreSQL, nhưng **tăng ngưỡng không tự làm truy vấn nhanh hơn**. Nhiều backend đồng thời có thể dùng thêm RAM và làm tăng tranh chấp CPU, I/O, khóa. Cũng cần tính đến các slot kết nối dự phòng cho quản trị và vai trò hệ thống theo phiên bản/configuration.

Nếu một service có 10 instance và mỗi instance cấu hình pool tối đa 30 kết nối, chỉ riêng service ấy đã có thể yêu cầu **300 kết nối**. Khi hoạch định, phải tính tổng từ tất cả pool, công cụ quản trị, background jobs và các service khác.

## 13. Kết nối JDBC từ ứng dụng Java

Một ứng dụng Java thường sử dụng PostgreSQL JDBC driver để tạo kết nối:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public class PgSessionExample {
    public static void main(String[] args) throws SQLException {
        String url =
            "jdbc:postgresql://127.0.0.1:5432/lab_db"
            + "?ApplicationName=java-lab";

        // Đặt biến môi trường trước khi chạy, không hard-code bí mật.
        String user = System.getenv("PG_LAB_USER");
        String password = System.getenv("PG_LAB_PASSWORD");

        try (Connection connection =
                 DriverManager.getConnection(url, user, password);
             PreparedStatement statement = connection.prepareStatement(
                 "SELECT pg_backend_pid() AS pid, "
                 + "current_database() AS dbname")) {

            try (ResultSet rs = statement.executeQuery()) {
                if (rs.next()) {
                    System.out.println(
                        "PID = " + rs.getInt("pid")
                        + ", DB = " + rs.getString("dbname")
                    );
                }
            }
        }
    }
}
~~~

Ví dụ cần PostgreSQL JDBC driver trong classpath, server đang chạy và biến môi trường chứa user/password hợp lệ. Kết nối trong khối `try-with-resources` được đóng khi kết thúc khối; nếu dùng pool thì cách đóng logic và vật lý phụ thuộc implementation của pool.

Thực hành an toàn:

- Dùng `PreparedStatement` và các tham số ràng buộc thay vì nối trực tiếp đầu vào người dùng vào SQL.
- Dùng TLS theo chính sách môi trường khi giao tiếp qua mạng không tin cậy; cấu hình kết nối cần xác minh chứng chỉ đúng cách.
- Không đưa password vào log, source code hoặc thông báo lỗi công khai.
- Quản lý transaction bằng commit/rollback rõ ràng khi đổi `autoCommit` của JDBC.

### Autocommit trong JDBC và PostgreSQL session

JDBC `Connection` mặc định thường có `autoCommit = true`; khi gọi `setAutoCommit(false)`, driver quản lý các transaction tường minh phù hợp để nhóm nhiều statement tới commit/rollback.

~~~java
connection.setAutoCommit(false);
try {
    // Thực thi các câu SQL thuộc một transaction.
    connection.commit();
} catch (SQLException error) {
    connection.rollback();
    throw error;
}
~~~

Đây là minh họa **mẫu quản lý transaction**, không phải một chương trình độc lập hoàn chỉnh. Trong code thực tế còn cần xử lý ngoại lệ khi rollback và hoàn nguyên trạng thái connection trước khi trả về pool.

## 14. Phân biệt các nhóm lỗi khi kết nối và truy vấn

### 14.1. Connection refused hoặc không tới được server

Nguyên nhân có thể:

- PostgreSQL chưa chạy hoặc lắng nghe ở cổng khác.
- `listen_addresses` không nhận địa chỉ mà client đang dùng.
- Firewall/network hoặc mapping cổng Docker sai.
- Client dùng `localhost` trong container, trỏ nhầm về chính container.

Kiểm tra:

~~~bash
pg_isready -h 127.0.0.1 -p 5432
~~~

`pg_isready` giúp biết server có nhận kết nối ở địa chỉ/cổng không; **không chứng minh user/password và quyền truy cập bảng của ứng dụng là đúng**.

### 14.2. FATAL: password authentication failed

Client đã tới được server nhưng thông tin đăng nhập hoặc phương thức xác thực không hợp lệ. Kiểm tra role, secret, cấu hình `pg_hba.conf` và phiên bản driver/cơ chế xác thực. Không xử lý bằng cách mở `trust` toàn mạng.

### 14.3. no pg_hba.conf entry

Không có quy tắc HBA phù hợp với combination user/database/địa chỉ/kết nối (hoặc chính sách SSL), nên server từ chối. Cần điều chỉnh chính xác rule, thứ tự rule và yêu cầu mã hóa theo chính sách vận hành. `pg_hba.conf` điều khiển **xác thực/quyền kết nối**, không tự cấp `SELECT` trên bảng.

### 14.4. FATAL: database does not exist

Host/port đúng nhưng tên database đích không tồn tại. Xác nhận `-d`, database đã tạo và kết nối đang tới đúng instance.

### 14.5. permission denied for table

Session đã xác thực và kết nối thành công, nhưng role thiếu quyền trên bảng/schema. Đây là **lỗi phân quyền SQL**, không phải lỗi socket hay password.

### 14.6. too many clients already

Server gần hoặc vượt giới hạn kết nối khả dụng cho role. Cần kiểm tra tổng cấu hình connection pool, session idle, các backend đang chạy và những slot dự phòng, không chỉ tăng `max_connections` ngay.

### 14.7. relation does not exist dù bảng được tạo trước đó

Có thể do:

- Client kết nối nhầm database.
- Bảng nằm trong schema khác với `search_path`.
- Bảng tạm chỉ tồn tại trong session đã tạo, trong khi client đang dùng session khác.
- Migration tạo bảng chưa được commit hoặc không chạy thành công.

Kiểm tra:

~~~sql
SELECT current_database(), current_schema();
SHOW search_path;
~~~

Kết quả này cần được so với schema và quyền của bảng đích.

## 15. Công cụ giám sát và quản lý session

### Xem backend của chính mình

~~~sql
SELECT pg_backend_pid();
~~~

### Xem các connection client và trạng thái

~~~sql
SELECT
    datname,
    application_name,
    state,
    COUNT(*) AS connection_count
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY datname, application_name, state
ORDER BY datname, application_name, state;
~~~

Nếu thấy quá nhiều session `idle`, chưa thể kết luận lỗi. Connection pool thường giữ những connection `idle` để tránh chi phí tạo lại. Cần so với cấu hình pool và tải thật.

### Hủy query và kết thúc backend

PostgreSQL có:

~~~sql
-- Chỉ là ví dụ cú pháp khi đã xác định PID cần xử lý:
SELECT pg_cancel_backend(12345);

-- Mạnh hơn: chấm dứt backend và session tương ứng:
SELECT pg_terminate_backend(12345);
~~~

Hai PID ở trên là **số giả định**. Không chạy khi chưa xác định rõ backend thuộc ứng dụng nào và mức ảnh hưởng.

- `pg_cancel_backend(pid)` yêu cầu hủy câu query đang chạy, không nhất thiết đóng session.
- `pg_terminate_backend(pid)` yêu cầu kết thúc backend, làm gián đoạn session; transaction chưa commit sẽ bị xử lý rollback khi backend kết thúc.
- Các hàm này yêu cầu quyền phù hợp và có thể bị hạn chế với backend đặc biệt hoặc role siêu người dùng.

Không nên dùng chúng làm “cách tối ưu truy vấn”. Nếu session chờ khóa hoặc transaction bị bỏ quên, cần điều tra nguyên nhân ứng dụng và xây dựng timeout/phương án xử lý phù hợp.

## 16. Bài tập thực hành

Các bài tập dùng PostgreSQL lab. Không cần đọc hoặc thay đổi database sản xuất.

**Bài 1.** Một chương trình Java và một cửa sổ `psql` cùng nối trực tiếp tới database `shopdb`. Có bao nhiêu backend client theo mô hình PostgreSQL truyền thống khi hai kết nối cùng tồn tại? Chúng có dùng chung toàn bộ trạng thái session không?

**Bài 2.** Nêu sự khác nhau giữa **cluster**, **database**, **session** và **transaction**. Một session có thể chứa nhiều transaction không?

**Bài 3.** Viết câu `SELECT` hiển thị database hiện tại, user bắt đầu session và PID backend. Phân biệt kết quả `pg_backend_pid()` và `current_database()`.

**Bài 4.** Session A bắt đầu transaction và cập nhật một hàng nhưng chưa commit. Session B dùng `SELECT` thông thường ở `READ COMMITTED`. B có nhìn thấy giá trị A chưa commit không? Điều gì xảy ra ở câu đọc mới của B sau khi A commit?

**Bài 5.** Session A tạo `TEMP TABLE temp_demo`. Session B chạy `SELECT * FROM temp_demo;` và bị lỗi không tìm thấy quan hệ. Vì sao?

**Bài 6.** Một ứng dụng dùng connection pool 15 kết nối, có 8 instance chạy đồng thời. Nếu tất cả pool mở tối đa, riêng ứng dụng này có thể cần bao nhiêu kết nối tới PostgreSQL? Vì sao không nên tăng `max_connections` chỉ từ con số đó?

**Bài 7.** Nêu ý nghĩa khác nhau của `active`, `idle` và `idle in transaction` trong `pg_stat_activity`. Trạng thái nào có thể đáng lo nếu kéo dài?

**Bài 8.** Hai ứng dụng trong hai container cùng Compose network: PostgreSQL service tên `db`, cổng nội bộ `5432`, trên máy host map `5433`. Ứng dụng container phải dùng host và port nào?

**Bài 9.** Một ứng dụng dùng PgBouncer transaction pooling, nhưng yêu cầu một bảng tạm phải tồn tại qua nhiều transaction của client. Điều gì cần xem xét trước khi dùng cách thiết kế đó?

**Bài 10.** `pg_isready` báo server chấp nhận kết nối nhưng `psql` báo `permission denied for table`. Vì sao đây không phải hai kết quả mâu thuẫn?

### Đáp án gợi ý

| Bài | Ý chính |
| --- | --- |
| 1 | Thông thường có hai backend riêng. Chúng dùng chung dữ liệu/điều phối server nhưng không dùng chung toàn bộ trạng thái session |
| 2 | Cluster chứa các database; session là vòng đời kết nối; transaction là đơn vị commit/rollback. Một session có thể chứa nhiều transaction |
| 3 | `SELECT current_database(), session_user, pg_backend_pid();`; PID xác định backend, còn database là đích kết nối |
| 4 | Không thấy dữ liệu A chưa commit; sau commit, một consistent read mới của B ở `READ COMMITTED` có thể thấy thay đổi |
| 5 | Bảng tạm gắn với session A nên session B không có cùng bảng tạm |
| 6 | `15 × 8 = 120` kết nối tối đa riêng ứng dụng; còn các service khác, bộ nhớ, tải CPU/I/O và giới hạn dự phòng |
| 7 | `active` đang thực hiện query, `idle` chờ query mới, `idle in transaction` là phiên nhàn rỗi nhưng transaction vẫn mở. Trạng thái cuối kéo dài cần điều tra |
| 8 | Dùng `db:5432` trong mạng Compose, không dùng `localhost:5433` từ container ứng dụng |
| 9 | Transaction pooling có thể đổi server backend giữa các transaction; trạng thái bảng tạm cấp session không được giả định ổn định qua các transaction |
| 10 | `pg_isready` kiểm tra khả năng nhận kết nối; quyền `SELECT` là kiểm tra riêng khi thực thi SQL |

## 17. Ghi nhớ kiến trúc một phiên PostgreSQL

| Câu hỏi | Câu trả lời ngắn |
| --- | --- |
| Client gửi SQL cho ai? | PostgreSQL server qua kết nối và protocol |
| Ai xử lý SQL của một connection trực tiếp? | Backend process tương ứng |
| Hai backend có đọc cùng bảng được không? | Có, theo quyền, transaction isolation và cơ chế MVCC |
| Session kết thúc khi COMMIT không? | Không. COMMIT kết thúc transaction, session có thể tiếp tục |
| Có thể xem PID backend ở đâu? | `pg_backend_pid()` hoặc `pg_stat_activity.pid` |
| Session có trạng thái riêng nào? | Role, tham số `SET`, bảng tạm, prepared statements... |
| Mở rất nhiều connection có miễn phí không? | Không. Mỗi backend có chi phí tài nguyên |
| Pooler có thể làm thay đổi quan hệ client–backend? | Có, tùy session/transaction/statement pooling |
| Client mất kết nối khi transaction chưa commit thì sao? | Thay đổi chưa commit không được tự xem là đã commit |

**Mô hình cần nhớ:** một ứng dụng hoặc `psql` **mở kết nối → xác thực → có một session và backend phía PostgreSQL → gửi các truy vấn/transaction → backend xử lý trên tài nguyên chung → trả kết quả → tiếp tục hoặc đóng session**. Hiểu rõ ranh giới giữa **session**, **transaction** và **backend process** giúp bạn thiết kế connection pool đúng, giải thích trạng thái `pg_stat_activity`, xử lý lỗi kết nối và tránh những vấn đề đồng thời trong PostgreSQL.
