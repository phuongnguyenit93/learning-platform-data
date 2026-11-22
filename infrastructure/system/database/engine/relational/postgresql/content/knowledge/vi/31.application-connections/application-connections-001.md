# Giao thức kết nối, phiên làm việc và cấu trúc URI trong PostgreSQL

## 1. Một URL kết nối không chỉ là “địa chỉ của database”

Khi ứng dụng Java kết nối đến PostgreSQL, lập trình viên thường thấy một chuỗi ngắn:

~~~text
jdbc:postgresql://db.example.internal:5432/shopdb
~~~

Hoặc dùng công cụ dựa trên **libpq**:

~~~text
postgresql://app_reader@db.example.internal:5432/shopdb?sslmode=verify-full
~~~

Đằng sau chuỗi này là một chuỗi hoạt động có nhiều lớp: xác định host, DNS hoặc Unix-domain socket, tạo kết nối TCP, thương lượng TLS nếu được cấu hình, trao đổi thông điệp giao thức PostgreSQL, xác thực bằng phương pháp server yêu cầu, mở phiên làm việc, chạy câu SQL và quản lý trạng thái giao dịch. Nếu ứng dụng sử dụng connection pool, đối tượng `Connection` mà lập trình viên nhận được còn có thể là **một lượt mượn** kết nối vật lý đã tồn tại chứ không phải một phiên database vừa mới tạo.

Những lỗi thường gặp xuất phát từ việc nhầm các lớp:

- “Máy ping được” nhưng PostgreSQL chưa lắng nghe ở port TCP.
- TCP kết nối được nhưng server từ chối theo `pg_hba.conf`.
- Username/password đúng nhưng TLS certificate không khớp hostname.
- Thực thi SQL thành công nhưng ứng dụng giữ transaction mở, gây lock và VACUUM pressure.
- Sau khi trả connection về pool, session vẫn giữ `search_path` hoặc biến cấu hình không mong muốn.
- Cùng một connection URI nhưng thư viện Java JDBC và libpq **không** hiểu mọi tùy chọn giống nhau.
- Sử dụng transaction pooling nhưng vẫn dựa vào temporary tables, session-level `SET` hoặc prepared statements tồn tại qua nhiều lần mượn.
- Đưa password thẳng vào URI và vô tình lộ trong log, crash report hoặc lịch sử shell.

**Mục tiêu:** nắm chắc giao thức và các cấp trạng thái để lựa chọn kết nối đúng, bảo mật, có thể quan sát và vận hành ổn định.

### 1.1. Kết quả học tập

Sau bài, bạn có thể:

1. Phân biệt **client driver**, **TCP/Unix socket**, **TLS**, **PostgreSQL wire protocol**, **authentication**, **backend process** và **SQL transaction**.
2. Mô tả thông điệp startup, authentication, `ParameterStatus`, `BackendKeyData`, `ReadyForQuery`.
3. Giải thích **simple query protocol** và **extended query protocol** với `Parse`, `Bind`, `Execute`, `Sync`.
4. Đọc và viết chính xác chuỗi kết nối dạng URI theo cú pháp libpq, bao gồm escape ký tự đặc biệt.
5. Phân biệt **libpq URI**, **key=value connection string**, **JDBC URL** và công cụ môi trường.
6. Chọn `sslmode`, quản lý CA, xác minh hostname và hiểu SCRAM/TLS khác nhau.
7. Giải thích **session**, **transaction**, **statement**, **connection pool checkout** và trạng thái giữ qua transaction.
8. Chẩn đoán các lỗi DNS/TCP, authentication, TLS, database/role, capacity, timeout và pooling.
9. Dùng `pg_stat_activity`, `pg_stat_ssl`, `SHOW`, `pg_backend_pid()` và một số lệnh `psql` để kiểm tra phiên.
10. Viết ví dụ Java JDBC an toàn, dùng parameterized queries, transaction boundaries và pooling hợp lý.
11. Hiểu multi-host URI, failover, read/write routing và các giới hạn của connection string.
12. Hoàn thành các bài tập có lời giải cho tình huống triển khai thực tế.

> **Phạm vi:** bài trình bày hành vi phổ biến của giao thức PostgreSQL phiên bản 3 và libpq/JDBC hiện đại. Một số tùy chọn phụ thuộc PostgreSQL/client-driver version hoặc nền tảng. Khi triển khai production, đối chiếu phiên bản **client và server** cụ thể; đừng suy luận rằng mọi PostgreSQL-compatible proxy đều hỗ trợ trọn bộ giao thức và session features.

---

## 2. Bức tranh nhiều tầng của một lần kết nối

~~~mermaid
flowchart TD
    A["Ứng dụng Java / psql / pgAdmin"] --> B["Client driver: JDBC hoặc libpq"]
    B --> C["Đọc cấu hình: host, port, database, user, TLS"]
    C --> D["DNS, TCP hoặc Unix-domain socket"]
    D --> E["TLS / GSS encryption negotiation nếu sử dụng"]
    E --> F["PostgreSQL StartupMessage"]
    F --> G["Authentication: SCRAM, peer hoặc phương pháp hợp lệ"]
    G --> H["BackendKeyData, ParameterStatus, ReadyForQuery"]
    H --> I["Phiên kết nối sẵn sàng thực thi SQL"]
    I --> J["Transaction / statements / results"]
    J --> K["COMMIT/ROLLBACK, release pool hoặc đóng kết nối"]
~~~

### 2.1. Bốn câu hỏi phải tách riêng

| Câu hỏi | Thành phần giải quyết | Ví dụ lỗi |
|---|---|---|
| Có tìm thấy và kết nối đến endpoint không? | DNS, TCP/port, Unix socket, firewall | Connection refused / timeout |
| Kết nối có được mã hóa và xác minh server không? | TLS, CA, hostname validation | Certificate verify failed |
| Client có được đăng nhập database không? | `pg_hba.conf`, role, auth method, credentials | No pg_hba.conf entry / password authentication failed |
| Trong phiên, câu SQL có quyền và dữ liệu đúng không? | `GRANT`, ownership, RLS, SQL transactions | Permission denied for table / row filtered by RLS |

Một lỗi ở tầng thấp phải xử lý ở tầng đó. Nếu TCP còn không thông, đổi password PostgreSQL không giúp được.

### 2.2. Driver không phải database server

- **PostgreSQL server** nhận kết nối và thực thi SQL.
- **JDBC driver** triển khai giao thức tương tác với PostgreSQL từ Java.
- **libpq** là thư viện client PostgreSQL gốc được dùng bởi `psql` và nhiều công cụ.
- **PgBouncer/proxy** có thể đứng giữa client và PostgreSQL, làm thay đổi cách mapping kết nối và session.
- **Connection pool** trong ứng dụng có thể tái sử dụng các physical connections.

Không phải mọi tính năng của `libpq` tự động có mặt trong `pgJDBC`. Hai client có thể đều nói PostgreSQL wire protocol nhưng cung cấp **API và tham số cấu hình khác nhau**.

---

## 3. Kết nối TCP và Unix-domain socket

### 3.1. Host và port

Port PostgreSQL thường dùng là **5432** nếu không được cấu hình khác. Một endpoint kiểu TCP gồm host/IP và port:

~~~text
db.example.internal:5432
127.0.0.1:5432
[2001:db8::10]:5432
~~~

`localhost` có thể được hệ điều hành/driver phân giải thành IPv4 `127.0.0.1` hoặc IPv6 `::1`. Nếu server chỉ lắng nghe một bên, kết quả có thể khác; kiểm tra cả địa chỉ server đang lắng nghe và client chọn.

### 3.2. listen_addresses của server

Thông số `listen_addresses` chi phối địa chỉ mạng mà PostgreSQL lắng nghe; `port` chi phối port. Kiểm tra trong SQL nếu đã có quyền kết nối:

~~~sql
SHOW listen_addresses;
SHOW port;
~~~

Ví dụ `listen_addresses='localhost'` thường chỉ nhận kết nối TCP local, không nhận từ một máy ứng dụng bên ngoài.

Đừng đổi thành `'*'` chỉ để “chữa không kết nối được” mà không kiểm soát firewall, private networking, `pg_hba.conf` và TLS.

### 3.3. Kết nối socket trên máy chủ

Trên Unix-like systems, PostgreSQL có thể hỗ trợ **Unix-domain socket**. Với libpq, khi không chỉ định host mạng (và theo cấu hình build/nền tảng), kết nối local có thể đi qua socket thay vì TCP.

Ví dụ libpq dạng key/value:

~~~text
host=/var/run/postgresql dbname=shopdb user=app_reader
~~~

Ở đây `host` là **thư mục socket**, không phải hostname DNS. `pg_hba.conf` phân biệt `local` (Unix socket) và `host`/`hostssl` (TCP).

### 3.4. Unix socket không đồng nghĩa TLS

Unix-domain socket là IPC local, không đi qua TCP/TLS theo cách một remote TCP connection sử dụng TLS. Cơ chế truy cập có thể phụ thuộc quyền file/socket và authentication như `peer`. Cần đánh giá quyền local OS, không gán nhãn “an toàn tuyệt đối”.

### 3.5. JDBC cần chú ý

pgJDBC thông thường sử dụng TCP tới host/port và không mặc định tương đương với libpq local Unix socket handling. Kết nối Unix socket bằng Java có thể cần socket factory/extension hoặc khả năng driver/version cụ thể. Đừng copy URI `host=/var/run/postgresql` của libpq sang JDBC URL rồi giả định driver sẽ tự hiểu.

### 3.6. NAT, proxy và cloud endpoints

Một DNS name có thể trỏ load balancer/proxy, trong khi backend PostgreSQL thật nằm ở host khác. Nếu dùng TLS hostname verification, tên phải phù hợp với certificate của endpoint thực tế; nếu proxy terminate/re-encrypt TLS, cần threat model cho **cả hai chặng**.

---

## 4. Tổng quan PostgreSQL wire protocol

### 4.1. Protocol phiên bản 3

PostgreSQL hiện đại chủ yếu dùng **frontend/backend protocol version 3.x**. Client gửi các thông điệp nhị phân theo cấu trúc đã định nghĩa; server phản hồi trạng thái, lỗi, row descriptions, dữ liệu và signal hoàn tất.

Điều này không giống một HTTP REST API:

~~~text
HTTP: GET /api/orders -> JSON
PostgreSQL: Startup/Auth -> Query/Parse/Bind/Execute -> DataRow/CommandComplete/ReadyForQuery
~~~

Driver xử lý hầu hết các thông điệp; ứng dụng thường không cần viết protocol parser.

### 4.2. Kết nối có trạng thái

Một PostgreSQL connection có state: authenticated role, current database, configuration parameters, transaction status, prepared statements, temporary objects và backend identity. Vì vậy việc tùy ý “chuyển connection sang server khác” giữa hai câu SQL có thể làm thay đổi semantics.

### 4.3. Lược đồ các nhóm thông điệp

| Nhóm | Frontend hoặc backend | Mục đích |
|---|---|---|
| SSLRequest / GSSENCRequest | Client | Đề xuất thiết lập transport security tương ứng |
| StartupMessage | Client | Yêu cầu mở session với user, database và các startup parameters |
| Authentication* | Server/client | Thực hiện cơ chế xác thực đã chọn |
| ParameterStatus | Server | Thông báo một số session parameters |
| BackendKeyData | Server | Dữ liệu dùng để định danh backend cho cancel request |
| ReadyForQuery | Server | Hoàn tất chu kỳ xử lý và báo trạng thái transaction |
| Query | Client | Simple Query protocol |
| Parse, Bind, Describe, Execute, Sync | Client | Extended Query protocol |
| RowDescription, DataRow | Server | Mô tả và dữ liệu các rows |
| CommandComplete | Server | Lệnh đã hoàn tất và command tag |
| ErrorResponse, NoticeResponse | Server | Lỗi/thông báo |
| NotificationResponse | Server | Thông báo LISTEN/NOTIFY |

Danh sách không liệt kê mọi kiểu message. Các drivers/proxies phải tuân thủ giao thức theo phiên bản chúng hỗ trợ.

### 4.4. Đừng tự parse dữ liệu SQL bằng split chuỗi

Protocol có field encoding, message length, message type và text/binary formats. Thứ tự các messages và error handling có quy tắc; không thể triển khai PostgreSQL client đúng chỉ bằng cách mở socket rồi gửi chuỗi SQL thuần kết thúc bằng newline.

---

## 5. Startup, TLS và authentication handshake

### 5.1. Trình tự khái quát

~~~text
Client                             PostgreSQL server
  |                                       |
  |--- TCP connect / local socket ------->|
  |                                       |
  |--- TLS request (nếu cần) ------------>|
  |<-- chấp nhận/từ chối -----------------|
  |        TLS handshake nếu chấp nhận    |
  |                                       |
  |--- StartupMessage: user, database --->|
  |<-- Authentication request -----------|
  |--- Credential/SASL exchange --------->|
  |<-- AuthenticationOk ------------------|
  |<-- ParameterStatus* ------------------|
  |<-- BackendKeyData --------------------|
  |<-- ReadyForQuery ---------------------|
  |                                       |
  |--- Query hoặc Parse/Bind/Execute ---->|
  |<-- RowDescription, DataRow*, ... -----|
  |<-- ReadyForQuery ---------------------|
~~~

Tùy authentication mechanism, proxy, encryption mode và protocol extension, số vòng trao đổi thay đổi. Đây là **mô hình tư duy**, không phải packet capture đầy đủ.

### 5.2. StartupMessage chứa gì?

Một StartupMessage của protocol v3 mang protocol version và cặp parameter name/value như:

- `user`: database role muốn sử dụng.
- `database`: database muốn vào.
- `application_name`: tên ứng dụng để server hiển thị/giám sát.
- Những startup options được hỗ trợ theo server/client protocol.

Password **không** được gửi trong StartupMessage như một URL nguyên văn; authentication diễn ra qua các thông điệp sau.

### 5.3. Authentication không nhất thiết luôn là password

PostgreSQL có thể chọn cơ chế tùy `pg_hba.conf` và phương pháp được hỗ trợ: `scram-sha-256`, `peer` với local socket, certificate-based auth và các cơ chế khác. Không suy rằng mọi kết nối PostgreSQL phải chứa username/password trong URI.

### 5.4. AuthenticationOk chưa phải bảo đảm SQL có quyền

Sau xác thực và database-level access, role có thể truy cập session, nhưng SELECT/INSERT/UPDATE từng object còn phụ thuộc `GRANT`, schema usage, ownership, Row-Level Security và SQL privileges. “Kết nối thành công” không bằng “được đọc mọi bảng”.

### 5.5. ParameterStatus

Server có thể gửi `ParameterStatus` cho những session parameters nhất định. Client driver dùng chúng để biết các đặc tính như encoding, timezone-related settings và những giá trị mà driver cần cho protocol/SQL.

Không phải mọi custom GUC đều được gửi qua `ParameterStatus`. Muốn đọc session setting trong SQL, dùng `SHOW` hoặc `current_setting`.

### 5.6. BackendKeyData và cancel

Server gửi dữ liệu định danh để client có thể yêu cầu hủy một query đang chạy. **Không được coi** process ID hoặc cancel key là session login token cho phép chạy SQL. Cancel request là đường điều khiển riêng với giới hạn và quyền của nó; ứng dụng nên dùng API cancellation của driver thay vì tự xây packet.

---

## 6. Kết thúc một chu kỳ query: ReadyForQuery

Sau khi hoàn tất query cycle, server gửi `ReadyForQuery` để báo có thể nhận một chu kỳ khác và kèm trạng thái transaction.

| Trạng thái | Ký hiệu protocol | Ý nghĩa |
|---|---|---|
| Idle | `I` | Hiện không ở trong explicit transaction block |
| In transaction | `T` | Đang trong transaction block còn hợp lệ |
| Failed transaction | `E` | Đang trong transaction block đã lỗi, cần rollback hoặc điều khiển giao dịch phù hợp |

### 6.1. Trạng thái E là nguyên nhân lỗi dây chuyền

Trong một explicit transaction:

~~~sql
BEGIN;

SELECT 1 / 0; -- division_by_zero

SELECT 42; -- lỗi tiếp vì transaction đã aborted

ROLLBACK;
~~~

Sau câu lỗi đầu, PostgreSQL không cho chạy SQL nghiệp vụ bình thường trong cùng transaction đến khi transaction được rollback hoặc được xử lý bằng savepoint phù hợp.

Ứng dụng Java phải có `try/catch` và rollback khi transaction thất bại; trả Connection về pool với trạng thái `E` mà không cleanup là lỗi nghiêm trọng.

### 6.2. “Auto-commit true” không đồng nghĩa không có transaction

Ngay cả một câu SELECT đơn lẻ trong PostgreSQL cũng chạy dưới semantics của một transaction. Với JDBC auto-commit mặc định thường true, mỗi statement hoàn tất/commit theo driver semantics; khi `setAutoCommit(false)`, ứng dụng quản lý transaction rõ ràng qua `commit()` hoặc `rollback()`.

### 6.3. Một query request khác một transaction

Simple Query có thể mang nhiều SQL statements, extended protocol có chu kỳ riêng, và SQL transaction boundaries vẫn được xác định bởi `BEGIN`/`COMMIT`/`ROLLBACK` hoặc driver. Không dùng số lần network round trip làm số transaction.

---

## 7. Simple Query Protocol

### 7.1. Mô hình

Client gửi một thông điệp `Query` chứa SQL text:

~~~text
Frontend: Query("SELECT order_id FROM orders WHERE customer_id=101")
Backend:  RowDescription
          DataRow*
          CommandComplete
          ReadyForQuery
~~~

Driver quyết định sử dụng simple hay extended protocol tùy API/configuration. `psql` và thư viện khác nhau có thể chọn đường khác nhau.

### 7.2. Ưu và hạn chế

Simple Query dễ hình dung nhưng không cung cấp cùng cơ chế `Bind` parameters của extended protocol. Việc tự ghép SQL string từ input vẫn dễ SQL injection:

~~~text
SQL = "SELECT * FROM customers WHERE email='" + email + "'"
~~~

Đừng dùng SQL text concatenation vì cảm thấy protocol đơn giản hơn.

### 7.3. Các kết quả server có thể trả

Một SELECT thường có row description, data rows, command completion. Một UPDATE không RETURNING thường có command completion chứa thông tin affected rows; nếu query lỗi, có `ErrorResponse`. Driver chuyển những message này thành rows/update count/exceptions ở API.

### 7.4. Nhiều statements trong một Query message

Simple Query protocol có thể chứa nhiều statements ngăn bởi semicolon. Chúng có semantics về implicit transaction block và error handling riêng; **không** mặc định coi một chuỗi nhiều statements là an toàn để thay thế explicit transactions và error management.

Để bảo đảm atomicity của nhiều thao tác nghiệp vụ, hãy quản lý transaction rõ ràng và hiểu cách client/driver thực thi batch statements.

---

## 8. Extended Query Protocol

### 8.1. Mục đích

Extended protocol tách bước chuẩn bị SQL và gán giá trị tham số. Các thông điệp quan trọng:

1. `Parse`: tạo prepared statement từ SQL và type information.
2. `Bind`: cung cấp giá trị parameters, tạo portal.
3. `Describe`: yêu cầu mô tả prepared statement/portal khi cần.
4. `Execute`: thực thi portal.
5. `Sync`: đồng bộ chu kỳ, server gửi ReadyForQuery theo quy tắc.
6. `Close`: đóng statement/portal khi client cần.

### 8.2. Dòng dữ liệu minh họa

~~~text
Client:
    Parse("SELECT name FROM customers WHERE id=$1")
    Bind(parameter 1 = 101)
    Describe(portal)
    Execute(portal)
    Sync

Server:
    ParseComplete
    BindComplete
    RowDescription
    DataRow*
    CommandComplete
    ReadyForQuery
~~~

Đây là một sequence minh họa; thực tế có thể có thêm/bớt Describe, NoData, PortalSuspended, Format codes và các thông điệp khác.

### 8.3. Parameter là dữ liệu, không phải SQL identifier

`$1` trong SQL PostgreSQL biểu thị parameter value:

~~~sql
SELECT customer_id, customer_name
FROM app.customers
WHERE customer_id = $1;
~~~

Bạn không thể dùng parameter thay tên bảng/cột theo kiểu:

~~~sql
SELECT * FROM $1; -- không hợp lệ như parameter identifier
~~~

Tên đối tượng phải do SQL text xác định và cần whitelist/quote đúng khi động. Values dùng bind parameters.

### 8.4. Text vs binary formats

Extended protocol có các format codes cho values/results; nhiều drivers dùng text format hoặc binary format tùy kiểu dữ liệu và configuration. Đừng giả định mọi row values đều là UTF-8 text strings ở tầng wire; driver chịu trách nhiệm decode đúng kiểu.

### 8.5. Parse/Bind khác SQL-level PREPARE

Protocol-level named prepared statements, unnamed statements và SQL `PREPARE/EXECUTE` có liên quan nhưng không hoàn toàn đồng nhất về API/lifetime. Driver có thể cache hoặc chuyển sang server-side preparation sau một ngưỡng, hoặc luôn dùng unnamed statements. Chi tiết của pgJDBC phụ thuộc version và cấu hình như prepare threshold.

### 8.6. Prepared statement và session affinity

Named server-side prepared statement thuộc một PostgreSQL session/backend. Nếu connection pool hoặc proxy chuyển lần thực thi kế tiếp sang một backend khác, prepared statement có thể **không tồn tại ở backend mới** hoặc proxy cần cơ chế tracking/preparation riêng.

Không kết luận “JDBC PreparedStatement luôn còn tồn tại trên server sau khi Java object bị close” — đó là driver/proxy implementation detail.

---

## 9. Giao thức và chống SQL injection

### 9.1. Dùng prepared statement

Trong JDBC:

~~~java
String sql =
    "SELECT customer_id, customer_name " +
    "FROM app.customers WHERE customer_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, customerId);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("customer_id"));
        }
    }
}
~~~

Dấu hỏi `?` ở JDBC là placeholder ở API driver; driver biên dịch/chuyển đổi phù hợp với PostgreSQL protocol. Đừng nhầm ký hiệu JDBC `?` với syntax `$1` của PostgreSQL SQL.

### 9.2. Parameterization giải quyết gì?

- Tách **cấu trúc lệnh** và **giá trị dữ liệu**.
- Giảm SQL injection do input bị coi là code SQL.
- Giúp driver quản lý loại dữ liệu và bind parameters.
- Có thể hỗ trợ reuse execution plans trong các điều kiện thích hợp.

### 9.3. Parameterization không thay authorization

Một query có parameter an toàn vẫn có thể trả dữ liệu người dùng không có quyền xem nếu application role có SELECT rộng và thiếu RLS/tenant filters. Database authorization và API permission checks vẫn phải thiết kế riêng.

### 9.4. Không nhầm escaping URI với SQL parameterization

Escape password `@` thành `%40` trong connection URI là **mã hóa thành phần URI**, không liên quan việc bind values của câu SQL. Cả hai cần thiết ở **hai lớp khác nhau**.

---

## 10. Dạng URI của libpq

### 10.1. Cấu trúc tổng quát

PostgreSQL libpq hỗ trợ URI dạng:

~~~text
postgresql://[user[:password]@][host][:port][/dbname][?param1=value1&param2=value2]
~~~

Tên scheme `postgres://` cũng được libpq chấp nhận trong những tình huống thông thường.

Ví dụ:

~~~text
postgresql://report_user@db.internal.example:5432/salesdb?sslmode=verify-full&application_name=reporter
~~~

### 10.2. Các thành phần

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| Scheme | `postgresql://` | Libpq connection URI |
| User | `report_user` | PostgreSQL role requested |
| Password (tùy chọn) | `:secret@` | Credential; **tránh nhúng** vào URL |
| Host | `db.internal.example` | DNS name/IP/host value |
| Port | `5432` | TCP port |
| Database | `salesdb` | Database name |
| Query parameter | `sslmode=verify-full` | Tùy chọn client/TLS |
| Query parameter | `application_name=reporter` | Tên ứng dụng |
| Query parameter | `connect_timeout=5` | Timeout mở kết nối theo libpq semantics |

### 10.3. Ví dụ nên dùng: URI không chứa password

~~~text
postgresql://app_reader@db.internal.example:5432/shopdb?sslmode=verify-full&connect_timeout=5&application_name=orders-api
~~~

Mật khẩu lấy từ secret store, passfile hoặc thông số riêng qua driver/app configuration. **Không log URI sau khi đã thêm credential.**

### 10.4. Không nhầm username với database

~~~text
postgresql://alice@db.example.internal:5432/shopdb
~~~

`alice` là role; `shopdb` là database. Hai chuỗi không nhất thiết giống nhau. Nếu không chỉ định user/database, libpq áp các giá trị mặc định theo môi trường và cấu hình cụ thể; không giả định mọi máy chọn cùng database.

### 10.5. Cẩn thận với IPv6

Trong authority URI, IPv6 literal cần có dấu ngoặc vuông để không nhầm dấu hai chấm với port:

~~~text
postgresql://app@[2001:db8::10]:5432/shopdb
~~~

Đây là địa chỉ IPv6 tài liệu ví dụ, không phải endpoint thực. Với TLS verify-full, việc kết nối bằng IP đòi certificate khớp IP theo cơ chế client; DNS name thường dễ quản trị certificate hơn.

---

## 11. Percent-encoding: ký tự đặc biệt trong URI

### 11.1. Vì sao cần mã hóa?

Khi username, database name hoặc password chứa ký tự đặc biệt, những ký tự đó có thể bị nhầm với dấu phân tách URI:

| Ký tự | Escape trong URI | Ý nghĩa khi chưa escape |
|---|---|---|
| Khoảng trắng | `%20` | Không được dùng nguyên theo cấu trúc URI an toàn |
| `@` | `%40` | Phân cách userinfo và host |
| `:` | `%3A` | Phân cách user/password hoặc host/port |
| `/` | `%2F` | Phân tách path |
| `?` | `%3F` | Bắt đầu query parameters |
| `&` | `%26` | Phân cách query parameters |
| `=` | `%3D` | Phân cách parameter name/value |
| `#` | `%23` | Dấu fragment |
| `%` | `%25` | Prefix của percent-encoding |

Ví dụ **giả định** password `p@ss/word#1` được biểu diễn trong URI bằng `p%40ss%2Fword%231`:

~~~text
postgresql://demo:p%40ss%2Fword%231@db.example.internal:5432/shopdb
~~~

**Không dùng cách nhúng password trực tiếp trong URL ở production.** Mã hóa percent chỉ bảo đảm parse đúng; nó **không phải encryption hoặc bảo vệ bí mật**. Full URI vẫn có thể xuất hiện trong logs, exception, shell history và monitoring.

### 11.2. Encode từng phần, không encode cả URL

Sai: biến tất cả ký tự cấu trúc `://?&=` thành percent-encoded text, khiến chuỗi không còn URI có thể parse.

Đúng: encode component values trước, sau đó đặt đúng dấu phân cách.

### 11.3. Tránh double-encoding

Nếu `@` thành `%40` rồi tiếp tục encode lần nữa thành `%2540`, client có thể giải mã thành literal `%40` thay vì `@`. Đây là một nguyên nhân khó nhận ra của lỗi password authentication.

### 11.4. Khoảng trắng và dấu +

Để không phụ thuộc khác biệt giữa URI parsing và form-urlencoded conventions của từng công cụ, nên dùng `%20` cho khoảng trắng trong thành phần URI thay vì giả định dấu `+` có nghĩa giống nhau ở mọi parser.

---

## 12. Query parameters trong libpq URI

### 12.1. Ví dụ nhiều tùy chọn

~~~text
postgresql://app_reader@db.internal.example:5432/shopdb?sslmode=verify-full&connect_timeout=5&application_name=orders-api
~~~

Các tùy chọn có những vai trò riêng:

| Parameter | Ý nghĩa |
|---|---|
| `sslmode=verify-full` | Yêu cầu TLS và xác minh certificate/hostname theo libpq |
| `connect_timeout=5` | Thời gian chờ mở kết nối, đơn vị giây trong libpq |
| `application_name=orders-api` | Gắn tên phiên để giám sát |
| `sslrootcert=...` | Đường dẫn CA certificate phía client |
| `options=...` | Startup options được server cho phép |
| `target_session_attrs=...` | Lọc endpoint đáp ứng thuộc tính mong muốn khi có nhiều hosts |

### 12.2. Đường dẫn CA

~~~text
postgresql://app_reader@db.internal.example/shopdb?sslmode=verify-full&sslrootcert=%2Fetc%2Fpostgresql%2Fca.pem
~~~

`sslrootcert` ở đây là file trên **máy ứng dụng/client**, không phải trên PostgreSQL server.

### 12.3. Startup options

Trong những môi trường thích hợp, libpq cho phép `options` truyền tham số khởi tạo, ví dụ:

~~~text
postgresql://app_reader@db.internal.example/shopdb?options=-c%20statement_timeout%3D5000
~~~

Đây là minh họa percent-encoding của khoảng trắng và dấu bằng; phải kiểm tra server cho phép setting nào và quản trị quyền phù hợp.

### 12.4. Ký tự & trong shell

Khi chạy lệnh trên shell, `&` có thể là ký tự điều khiển. Đặt URI trong dấu nháy hoặc dùng file cấu hình thay vì paste không quote. Không đặt password thật trong command-line arguments vì chúng có thể bị ghi lại.

### 12.5. Không chuyển option một cách máy móc sang JDBC

Một tham số libpq có thể không tồn tại, có tên khác hoặc có đơn vị khác trong pgJDBC. Tra đúng tài liệu client đang chạy, đặc biệt với SSL, timeout, keepalive và failover.

---

## 13. Unix-domain socket trong libpq URI

### 13.1. Local socket directory

Libpq có thể chỉ định thư mục socket qua `host`:

~~~text
host=/var/run/postgresql port=5432 dbname=shopdb user=app_reader
~~~

Dạng URI:

~~~text
postgresql:///shopdb?host=%2Fvar%2Frun%2Fpostgresql&user=app_reader
~~~

Dấu `%2F` mã hóa separator của đường dẫn trong parameter value. Trên những OS/build khác, directory socket có thể khác; không giả định tất cả server có socket ở `/var/run/postgresql`.

### 13.2. Local không đồng nghĩa TCP localhost

- `host=/var/run/postgresql`: Unix-domain socket.
- `host=localhost` hoặc `host=127.0.0.1`: TCP loopback.
- Không ghi host: libpq có thể chọn local socket trên nền tảng hỗ trợ, hoặc một mặc định khác.

Hai đường có thể khớp các dòng **khác nhau** trong `pg_hba.conf`: `local` so với `host`/`hostssl`.

### 13.3. peer authentication

Trên local Unix socket, server có thể cấu hình `peer` để ánh xạ OS identity. Qua TCP, phương pháp xác thực được chọn từ HBA records dành cho kết nối TCP; đừng cho rằng cùng database role sẽ dùng cùng phương pháp.

### 13.4. JDBC là trường hợp khác

pgJDBC thường dùng TCP theo URL thông thường. Dạng socket directory của libpq không tự biến thành JDBC socket connection; một số ứng dụng cần socket factory hoặc cấu hình riêng theo driver/OS.

---

## 14. Chuỗi key=value của libpq

Ngoài URI, libpq hỗ trợ:

~~~text
host=db.internal.example port=5432 dbname=shopdb user=app_reader sslmode=verify-full connect_timeout=5 application_name=orders-api
~~~

### 14.1. Quoting value

Một value có khoảng trắng có thể dùng quotation theo cú pháp libpq:

~~~text
host=db.internal.example dbname=shopdb application_name='order processing worker'
~~~

**Đừng** áp dụng percent-encoding URI vào dạng key/value mà không hiểu parser của connection string.

### 14.2. Vì sao cấu hình tường minh tốt hơn?

Nếu client đồng thời lấy host/user/database từ environment, service file và URL, lựa chọn thực tế có thể khó dự đoán. Đặt rõ host, port, database, role, TLS mode, CA, timeout và application name trong cấu hình được quản trị.

### 14.3. Không đặt credentials trong command line

Các chuỗi connection có password có thể bị lộ qua process listing, shell history hoặc log lỗi. Đưa secret vào mechanism có quyền đọc hạn chế và đảm bảo logging đã redacted.

---

## 15. JDBC URL khác libpq URI

### 15.1. JDBC form

~~~text
jdbc:postgresql://db.internal.example:5432/shopdb
~~~

Ví dụ có options:

~~~text
jdbc:postgresql://db.internal.example:5432/shopdb?sslmode=verify-full&ApplicationName=orders-api
~~~

`jdbc:postgresql://` là cú pháp của **PostgreSQL JDBC driver**, không phải libpq URI. Dù cùng nói wire protocol PostgreSQL, JDBC và libpq không nhất thiết hỗ trợ cùng bộ properties.

### 15.2. Cấp credential qua Properties

~~~java
String url = "jdbc:postgresql://db.internal.example:5432/shopdb";

Properties props = new Properties();
props.setProperty("user", System.getenv("DB_USER"));
props.setProperty("password", System.getenv("DB_PASSWORD"));
props.setProperty("sslmode", "verify-full");
props.setProperty("ApplicationName", "orders-api");

try (Connection connection = DriverManager.getConnection(url, props)) {
    System.out.println(connection.isValid(3));
}
~~~

Ví dụ cần import `java.sql.*`, `java.util.Properties` và PostgreSQL JDBC dependency trong project thực tế. Environment variable là một hình thức triển khai; production nên dùng secret management phù hợp và không in password.

### 15.3. Tên/đơn vị timeout khác nhau

- Libpq `connect_timeout`: thời gian chờ thiết lập kết nối theo libpq, tính bằng giây.
- PgJDBC `connectTimeout`: tham số tương ứng của driver với quy tắc riêng.
- HikariCP `connectionTimeout`: thời gian chờ **mượn connection từ pool**, thường tính bằng mili giây.
- `statement_timeout` PostgreSQL: giới hạn thời gian thực thi câu SQL theo server/session setting.

Không lấy `connectionTimeout=30000` của pool để suy driver đang chờ TCP trong 30.000 giây.

### 15.4. JDBC dấu hỏi trong SQL khác URL

Trong JDBC URL `?sslmode=...` mở query parameters. Trong `PreparedStatement`:

~~~sql
SELECT order_id FROM app.orders WHERE customer_id = ?
~~~

`?` là một parameter placeholder của JDBC API. Nó không dùng để bind host, database hoặc tên table trong URL.

### 15.5. Cấu hình qua Spring Boot

Ví dụ `application.properties`:

~~~properties
spring.datasource.url=jdbc:postgresql://db.internal.example:5432/shopdb?sslmode=verify-full
spring.datasource.username=DB_USER_FROM_CONFIGURATION
spring.datasource.password=DB_PASSWORD_FROM_SECRET_STORE
~~~

Các giá trị uppercase ở đây chỉ là **placeholder minh họa**, không phải cú pháp Spring interpolation. Trong hệ thống thật, sử dụng cơ chế environment/secret binding của Spring deployment thay vì commit password vào file.

---

## 16. Environment variables của libpq

Một số biến thường gặp:

| Biến | Mục đích |
|---|---|
| `PGHOST` | Host hoặc socket directory |
| `PGHOSTADDR` | Địa chỉ mạng cụ thể |
| `PGPORT` | Port |
| `PGDATABASE` | Database |
| `PGUSER` | Role |
| `PGPASSWORD` | Password — **không khuyến nghị** do rủi ro môi trường/process exposure |
| `PGSSLMODE` | TLS policy |
| `PGSSLROOTCERT` | CA root file |
| `PGAPPNAME` | Application name |
| `PGCONNECT_TIMEOUT` | Timeout kết nối |
| `PGSERVICE` | Tên service configuration |
| `PGPASSFILE` | Password file path |

### 16.1. Ví dụ psql trên Unix-like shell

~~~bash
export PGHOST=db.internal.example
export PGPORT=5432
export PGDATABASE=shopdb
export PGUSER=app_reader
export PGSSLMODE=verify-full
export PGSSLROOTCERT=/etc/postgresql/ca.pem

psql
~~~

Giả định đã cấu hình nguồn credential hợp lệ. Không paste password thật vào shell history.

### 16.2. Quy tắc ưu tiên

Với libpq, connection parameters được cung cấp tường minh thường ưu tiên hơn environment defaults tương ứng. Service file và password file có quy tắc phối hợp riêng. Không giả định pgJDBC tự đọc toàn bộ `PG*`: Java frameworks/driver dùng cấu hình riêng.

### 16.3. .pgpass

Password file libpq có entries theo dạng:

~~~text
hostname:port:database:username:password
~~~

Trên Unix, permissions cho file chứa password cần được giới hạn, thường chỉ owner đọc/ghi. `PGPASSFILE`/`passfile` có thể điều khiển location theo libpq. Không in nội dung file chứa secret trong logs hoặc trả lời hỗ trợ.

### 16.4. Password file không thay TLS

Passfile chỉ cung cấp credential khi cần. Nó không tự mã hóa traffic, xác minh certificate, kiểm soát RLS hoặc thay SQL privileges.

---

## 17. Service file của libpq

### 17.1. Nhóm cấu hình dưới một tên

Ví dụ service configuration:

~~~ini
[shop_readonly]
host=db-read.internal.example
port=5432
dbname=shopdb
user=app_reader
sslmode=verify-full
sslrootcert=/etc/postgresql/ca.pem
application_name=reporting-cli
connect_timeout=5
~~~

Client libpq có thể dùng:

~~~bash
psql "service=shop_readonly"
~~~

Đường dẫn service files và biến như `PGSERVICEFILE` phụ thuộc OS/libpq configuration; xác nhận vị trí trên host thực.

### 17.2. Lợi ích

- Không sao chép endpoint/SSL config ở nhiều scripts.
- Dễ chuyển environment theo quản trị tập trung.
- Có thể đặt profile khác nhau cho read-only/reporting/admin theo least privilege.

### 17.3. Rủi ro

Nếu cấu hình `shop_readonly` bất ngờ trỏ primary hoặc database khác, scripts không đổi vẫn đi đến target mới. Cần change management cho service file; không nhúng password vào service profiles được chia sẻ.

---

## 18. TLS: mã hóa và xác minh danh tính server

### 18.1. SSL mode của libpq

| `sslmode` | Mô tả | Nên dùng khi nào |
|---|---|---|
| `disable` | Không dùng TLS | Chỉ nơi đã đánh giá an toàn và có kiểm soát riêng |
| `allow` | Có thể thử không TLS trước | Không bảo đảm encryption |
| `prefer` | Ưu tiên TLS, có thể fallback | Không bảo đảm verify hostname |
| `require` | Bắt buộc TLS | Chưa phải cấu hình rõ ràng đảm bảo server identity |
| `verify-ca` | TLS + CA chain verification | Không tự xác nhận endpoint hostname |
| `verify-full` | TLS + CA + hostname verification | Phù hợp production khi có PKI/certificate đúng |

Ở một số phiên bản/config của libpq, `require` có hành vi tương thích khi có CA file; **không dùng require thay verify-full** nếu cần xác thực endpoint.

### 18.2. Ví dụ production-like

~~~text
postgresql://app@db.prod.internal.example:5432/shopdb?sslmode=verify-full&sslrootcert=%2Fetc%2Fpostgresql%2Fca.pem
~~~

File CA ở máy client. Certificate server phải hợp lệ và phù hợp DNS hostname/IP theo policy của client.

### 18.3. Các lỗi phổ biến

- Server/proxy không hỗ trợ TLS nhưng client yêu cầu.
- CA bundle sai, thiếu intermediate hoặc certificate hết hạn.
- URL dùng IP còn chứng thư chỉ có DNS name.
- Client clock không đúng.
- Proxy terminate TLS rồi kết nối backend không có chính sách TLS tương đương.
- Cấu hình mTLS client cert/key không phù hợp.

### 18.4. TLS khác authorization

TLS bảo vệ vận chuyển và xác thực server theo mode; nó không cấp SELECT trên bảng và không thay RLS. Một kết nối `verify-full` vẫn có thể bị từ chối vì PostgreSQL role, HBA hoặc SQL privileges.

---

## 19. SCRAM và pg_hba.conf

### 19.1. SCRAM khác TLS

`scram-sha-256` là phương pháp xác thực mật khẩu dựa trên challenge–response. TLS là bảo vệ transport và có thể xác minh server. Sử dụng SCRAM qua TLS thường giải quyết các yêu cầu khác nhau.

### 19.2. Các loại HBA rules

Ví dụ **không áp nguyên vào production**:

~~~text
# TYPE   DATABASE USER         ADDRESS       METHOD
local    shopdb   app_reader                 peer
hostssl  shopdb   app_reader   10.20.0.0/16  scram-sha-256
~~~

`local` áp dụng cho Unix socket. `hostssl` áp dụng cho TCP connections dùng TLS. Address range ở đây chỉ là ví dụ private network, không phải chính sách phù hợp với mọi deployment.

### 19.3. Quy tắc matching

PostgreSQL xét HBA records theo thứ tự và chọn record phù hợp connection type/database/user/address. Khi một record phù hợp nhưng authentication thất bại, server không đơn giản thử record tiếp theo như một fallback password method.

### 19.4. Auth methods

| Method | Ý nghĩa |
|---|---|
| `scram-sha-256` | Password authentication hiện đại khi client/server hỗ trợ |
| `peer` | Authentication dựa trên OS user cho local socket |
| `cert` | Authentication dựa trên client certificate |
| `reject` | Chặn kết nối khớp |
| `trust` | Không yêu cầu password proof; **không nên dùng trên mạng untrusted** |
| `md5` | Legacy; cần kế hoạch chuyển đổi để hỗ trợ SCRAM phù hợp |

Nếu chuyển từ MD5 sang SCRAM, cần xem cấu hình `password_encryption`, password hashes của roles và khả năng hỗ trợ của client driver. Không chỉ sửa một dòng HBA rồi giả định mọi ứng dụng sẽ hoạt động.

### 19.5. HBA không thay GRANT

Qua HBA và password thành công nghĩa là client có thể đăng nhập theo các điều kiện còn lại. Quyền trên database, schema, table, function và RLS vẫn được kiểm tra riêng.

---

## 20. DNS host, hostaddr và certificate name

### 20.1. Hostname

`host=db.internal.example` cho phép DNS resolution và hỗ trợ kiểm tra hostname trong TLS verify-full.

### 20.2. hostaddr của libpq

`hostaddr=10.20.30.40` chỉ IP cần kết nối. Trong những cấu hình libpq, có thể cung cấp cả `host` (tên phục vụ các thao tác cần tên như TLS certificate/credential matching) và `hostaddr` (địa chỉ network) để kiểm soát resolve. Quy tắc chính xác phụ thuộc libpq và auth method.

### 20.3. Đừng bỏ xác minh certificate vì kết nối IP

Nếu certificate chỉ hợp lệ cho `db.internal.example`, chuyển URL sang IP thô có thể khiến verify-full thất bại. Sửa endpoint/certificate cấu hình đúng thay vì hạ sslmode xuống disable để “chữa” lỗi.

### 20.4. DNS failover không giữ kết nối cũ

Khi DNS endpoint trỏ sang primary mới, những **kết nối đã mở** vẫn gắn với socket/backend cũ cho đến khi mất hoặc đóng. Ứng dụng phải xử lý reconnect và retry khi failover; DNS không tự chuyển một PostgreSQL transaction đang chạy sang server mới.

---

## 21. Kết nối vật lý, phiên, giao dịch và statement

### 21.1. Phân biệt bốn phạm vi

| Phạm vi | Vòng đời | Ví dụ trạng thái |
|---|---|---|
| Physical connection | TCP/socket kết nối với server/proxy | Endpoint, socket, TLS |
| PostgreSQL session | Một backend session sau authentication | Backend PID, `SET`, temporary objects, prepared statements |
| SQL transaction | `BEGIN` → `COMMIT/ROLLBACK` hoặc implicit transaction | Snapshots, locks, `SET LOCAL` |
| SQL statement | Một `SELECT/UPDATE/...` | Command tag, `ROW_COUNT`, kết quả |
| Pool checkout | Một lần ứng dụng mượn `Connection` | Application resource lease, có thể tái dùng physical connection |

### 21.2. Một session có nhiều transactions

~~~sql
BEGIN;
SELECT * FROM app.orders WHERE order_id=1001;
COMMIT;

BEGIN;
UPDATE app.orders SET status='paid' WHERE order_id=1002;
ROLLBACK;
~~~

Không có lý do bắt buộc phải mở TCP connection mới giữa hai transactions. Nhưng với PgBouncer transaction pooling, hai transactions có thể **được gán hai backends khác nhau** dù client connection tới proxy không đổi.

### 21.3. JDBC close() qua pool

Trong nhiều pools, `connection.close()` của Java **trả logical connection về pool**, không nhất thiết đóng physical socket. Nếu quên close, pool có thể bị cạn tài nguyên. Dùng try-with-resources.

### 21.4. Backend PID

`pg_backend_pid()` cho biết PID của backend **đang thực thi SQL**. Không dùng nó làm user ID, HTTP request ID hoặc mã định danh bền vững; PID có thể thay khi reconnect/pool routing và có thể được tái sử dụng theo vòng đời process.

---

## 22. Lab quan sát session identity

### 22.1. Query nhận diện session

~~~sql
SELECT
    current_database() AS database_name,
    current_user AS effective_role,
    session_user AS login_role,
    pg_backend_pid() AS backend_pid,
    inet_client_addr() AS client_ip,
    inet_client_port() AS client_port,
    inet_server_addr() AS server_ip,
    inet_server_port() AS server_port,
    current_setting('application_name') AS application_name,
    current_setting('TimeZone') AS timezone;
~~~

Với Unix-domain socket, `inet_client_addr()`/`inet_server_addr()` có thể NULL; đây là hành vi hợp lệ.

### 22.2. Hai cửa sổ psql

Mở hai cửa sổ `psql` độc lập và chạy:

~~~sql
SELECT pg_backend_pid(), current_database(), current_user;
~~~

Với kết nối trực tiếp, thông thường hai sessions đang hoạt động có PID khác nhau. Với transaction pooling, backend PID của cùng client có thể thay giữa các transactions.

### 22.3. Đổi application_name

~~~sql
SET application_name='learning-order-worker';
SELECT current_setting('application_name');
~~~

Dùng `application_name` để nhận diện workload trong logs/`pg_stat_activity`, không để token/password/PII. Client có thể tự đặt tên nên nó **không phải bằng chứng xác thực**.

---

## 23. Trạng thái session so với SET LOCAL

### 23.1. SET session-level

~~~sql
SET TIME ZONE 'UTC';

BEGIN;
SELECT current_setting('TimeZone');
COMMIT;

SELECT current_setting('TimeZone');
~~~

`SET TIME ZONE` có thể tồn tại qua nhiều transactions trong cùng backend session. Nếu pool không reset state, request sau có thể kế thừa giá trị không mong muốn.

### 23.2. SET LOCAL

~~~sql
BEGIN;

SET LOCAL statement_timeout='2s';
SELECT current_setting('statement_timeout');

COMMIT;

SHOW statement_timeout;
~~~

`SET LOCAL` chỉ tồn tại trong transaction đang chạy. Sau COMMIT, giá trị trở về session-level setting trước đó (không nhất thiết là system default).

### 23.3. Session state và tenant isolation

Giả sử request A chạy:

~~~sql
SET search_path TO tenant_a, public;
~~~

Rồi trả connection về pool mà không reset. Request B có thể sử dụng bảng của tenant_a nếu tiếp tục dựa vào search_path cũ. Cần context gắn với request/transaction, SQL được schema-qualified khi thích hợp, và **cleanup/validation** rõ ràng.

### 23.4. Custom GUC không tự là identity proof

~~~sql
BEGIN;
SET LOCAL app.tenant_id='10';
-- Những query trong transaction.
COMMIT;
~~~

Mẫu chỉ có thể hỗ trợ RLS/tenant logic khi giá trị `app.tenant_id` được đặt bởi trusted authenticated layer và caller không thể tự giả mạo. Một biến cấu hình mà user tùy ý SET được không phải authentication mechanism.

### 23.5. RESET ALL vs DISCARD ALL

- `RESET ALL` reset các session configuration parameters; nó **không dọn sạch mọi trạng thái khác**.
- `DISCARD ALL` dọn nhiều session resources/state, có giới hạn và **không được thực thi bên trong transaction block**.
- Dọn state quá mạnh có thể hủy prepared statement cache/temporary objects và tốn chi phí.

Pool/driver có thể tự reset một tập state khi trả connection; luôn kiểm tra contract thay vì giả định mọi state đã sạch.

---

## 24. Java JDBC và transaction boundaries

### 24.1. Auto-commit

JDBC `Connection` thông thường ban đầu ở `autoCommit=true`. Để gộp nhiều statements vào một transaction:

~~~java
connection.setAutoCommit(false);
try {
    // SQL 1
    // SQL 2
    connection.commit();
} catch (SQLException error) {
    connection.rollback();
    throw error;
}
~~~

Trong code thật cần xử lý rollback failure, finally/cleanup và framework transaction manager đúng. Không tự commit/rollback một connection do Spring `@Transactional` đã quản lý nếu contract không cho phép.

### 24.2. Java method sử dụng PreparedStatement

~~~java
import java.sql.*;

public class OrderService {
    public static int markPaid(Connection connection, long orderId)
            throws SQLException {
        boolean oldAutoCommit = connection.getAutoCommit();

        try {
            connection.setAutoCommit(false);

            int rows;
            try (PreparedStatement ps = connection.prepareStatement(
                    "UPDATE app.orders SET status='paid' " +
                    "WHERE order_id=? AND status='new'")) {
                ps.setLong(1, orderId);
                rows = ps.executeUpdate();
            }

            connection.commit();
            return rows;

        } catch (SQLException error) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                error.addSuppressed(rollbackError);
            }
            throw error;
        } finally {
            connection.setAutoCommit(oldAutoCommit);
        }
    }
}
~~~

Mẫu giả định bảng `app.orders` tồn tại và method được gọi ngoài một transaction do framework quản lý. Trong môi trường thật, lệnh khôi phục autoCommit cũng có thể lỗi nếu socket đã hỏng; pool phải loại physical connection bị lỗi thay vì reuse.

### 24.3. PreparedStatement không thay transaction

Parameter binding chống SQL injection ở giá trị dữ liệu; nó không tự đảm bảo hai cập nhật orders/inventory atomic. Transaction, constraints và concurrency design vẫn cần thiết.

### 24.4. SQLSTATE

Trong JDBC `SQLException.getSQLState()` có thể dùng phân loại:

| Mã | Ý nghĩa |
|---|---|
| `23505` | Unique violation |
| `23503` | Foreign key violation |
| `40001` | Serialization failure |
| `40P01` | Deadlock detected |
| `57014` | Query canceled |

Lỗi constraint khác lỗi socket/TLS. Không bắt tất cả SQLException rồi trả cùng một business code “không tìm thấy”.

---

## 25. Temp objects, prepared statements và advisory locks

### 25.1. Temporary table

~~~sql
CREATE TEMP TABLE tmp_request_ids (
    id bigint PRIMARY KEY
) ON COMMIT DROP;
~~~

`ON COMMIT DROP` làm temp table bị drop khi transaction kết thúc theo semantics phù hợp. Temp table không có ON COMMIT DROP thường có session lifetime và có thể tồn tại giữa các pool checkouts nếu backend không đổi.

### 25.2. Named prepared statement

~~~sql
PREPARE get_customer(bigint) AS
SELECT customer_id,customer_name
FROM app.customers WHERE customer_id=$1;

EXECUTE get_customer(101);
DEALLOCATE get_customer;
~~~

SQL `PREPARE`/`EXECUTE` thuộc backend session. Protocol-level named prepared statements do driver tạo có semantics riêng nhưng cũng phụ thuộc backend state; khi chuyển sang server connection khác, tên đó không nhất thiết tồn tại.

### 25.3. Cursors

Một số cursors được khai báo trong transaction và không tồn tại sau COMMIT; holdable cursors có lifetime đặc biệt. Không giả định cursor có thể tiếp tục FETCH ở backend mới sau PgBouncer transaction pooling.

### 25.4. Advisory locks

Session-level:

~~~sql
SELECT pg_advisory_lock(12345);
SELECT pg_advisory_unlock(12345);
~~~

`pg_advisory_lock` có thể giữ lock **qua COMMIT**, cho đến khi unlock/session kết thúc. Đó là rủi ro khi trả backend về pool.

Transaction-level:

~~~sql
BEGIN;
SELECT pg_advisory_xact_lock(12345);
COMMIT;
~~~

`pg_advisory_xact_lock` tự giải phóng khi transaction kết thúc, thường dễ kiểm soát hơn cho scope nghiệp vụ một transaction.

### 25.5. LISTEN

~~~sql
LISTEN order_events;
~~~

LISTEN registration là session state. Client phải tiếp tục sử dụng backend phù hợp để nhận notifications; transaction pooling không bảo đảm session affinity xuyên transactions.

---

## 26. Connection pool và chi phí tài nguyên

### 26.1. Mục đích của pool

Mở physical connection mới đòi networking, TLS/auth handshake và PostgreSQL backend resources. Pool giữ kết nối sẵn, application requests mượn và trả lại:

~~~text
Request A ---> [Connection 1] ---> Backend 1
Request B ---> [Connection 2] ---> Backend 2
Request C ---> [busy pool; wait] 
Request D ---> [Connection 3] ---> Backend 3
~~~

### 26.2. Pool saturation khác lỗi TCP

Khi mọi slots đang bận, ứng dụng có thể báo “connection acquisition timeout”. Điều này không có nghĩa PostgreSQL hostname không resolve hoặc port bị chặn.

Các nguyên nhân điển hình: query chậm, transaction dài, lock contention, thiếu close/release, backend capacity hạn chế hoặc pool sizing sai.

### 26.3. Tổng số connections

Ví dụ 20 application instances × maximum pool size 30 = **600 connections tiềm năng**. Cần cộng thêm background jobs, monitoring, admin sessions, reporting và các proxies. PostgreSQL `max_connections` không phải mục tiêu nên luôn sử dụng hết.

### 26.4. Pool càng lớn không đồng nghĩa throughput càng cao

Nếu DB đang bị giới hạn CPU, I/O, locks, một pool lớn hơn có thể làm contention nặng hơn và latency tăng. Chọn kích thước dựa vào benchmark, query durations, concurrency và DB resource budget.

### 26.5. Nhiều loại timeout

| Timeout | Đối tượng được giới hạn |
|---|---|
| Pool checkout timeout | Thời gian client đợi mượn connection |
| TCP connect timeout | Thời gian thiết lập network connection |
| TLS/auth handshake timeout | Chờ quá trình handshake tương ứng |
| Socket/read timeout | Chờ I/O/response |
| `statement_timeout` | Thời gian thực thi SQL statement trên server |
| `lock_timeout` | Chờ lock |
| `idle_in_transaction_session_timeout` | Transaction mở nhưng idle quá lâu |

Tên, đơn vị và phạm vi tùy driver/pool/server. Không sao chép một con số mà không kiểm tra units.

---

## 27. Ví dụ HikariCP

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import java.sql.*;

public class PgPool {
    public static HikariDataSource create() {
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(
            "jdbc:postgresql://db.internal.example:5432/shopdb" +
            "?sslmode=verify-full&ApplicationName=orders-api"
        );
        config.setUsername(System.getenv("DB_USER"));
        config.setPassword(System.getenv("DB_PASSWORD"));
        config.setMaximumPoolSize(12);
        config.setMinimumIdle(2);
        config.setConnectionTimeout(5000); // ms
        config.setValidationTimeout(2000); // ms
        return new HikariDataSource(config);
    }

    public static void query(HikariDataSource pool)
            throws SQLException {
        try (Connection c = pool.getConnection();
             PreparedStatement ps =
                c.prepareStatement("SELECT pg_backend_pid()");
             ResultSet rs = ps.executeQuery()) {
            if (rs.next()) {
                System.out.println(rs.getInt(1));
            }
        }
    }
}
~~~

Đây là ví dụ cấu trúc, cần dependencies pgJDBC/HikariCP, CA trust đúng và secret configuration trong project. Các pool sizes/timeout là **minh họa**, không phải khuyến nghị định lượng cho mọi hệ thống.

### 27.1. Lifecycle

`maxLifetime`, `idleTimeout`, connection validation và keepalives ảnh hưởng connection churn. Đặt không phù hợp với backend/proxy/NAT idle limits có thể dẫn đến lỗi connection reset bất thường.

### 27.2. try-with-resources

Đảm bảo `Connection.close()` được gọi ở finally/try-with-resources. Trong pool, close thường trả logical connection, không đóng backend ngay.

---

## 28. PgBouncer và session/transaction/statement pooling

### 28.1. Hai phía của proxy

~~~text
Application --client socket--> PgBouncer --server socket--> PostgreSQL
~~~

Số client connections tới PgBouncer có thể lớn hơn số PostgreSQL server connections đang được giữ.

### 28.2. Session pooling

Backend được gắn với client session trong giai đoạn session tương ứng; các tính năng dựa trên session affinity có khả năng hoạt động giống direct connection hơn, tùy cấu hình proxy.

### 28.3. Transaction pooling

Backend connection được gán cho **một transaction** rồi trả về server pool khi transaction kết thúc.

~~~text
Client X tx1 --> Backend A --> COMMIT
Client X tx2 --> Backend B --> COMMIT
~~~

Vì thế, session-level state tạo ở backend A không được bảo đảm ở B.

### 28.4. Statement pooling

Backend có thể được cấp theo statement, khiến ứng dụng cần explicit multi-statement transaction không tương thích nếu proxy không hỗ trợ giữ session đúng. Chỉ dùng khi workload phù hợp.

### 28.5. Bảng tương thích

| Feature | Session pooling | Transaction pooling |
|---|---|---|
| SELECT/UPDATE SQL đơn giản | Thường được | Thường được |
| BEGIN/COMMIT nhiều câu | Thường được | Được nếu transaction giữ một backend |
| SET LOCAL trong transaction | Được | Được khi mọi SQL cùng transaction |
| Session-level SET qua nhiều transactions | Có thể giữ | **Không được giả định** |
| Temporary table qua nhiều transactions | Có thể giữ | Không an toàn |
| Session advisory lock | Có thể giữ | Không an toàn |
| LISTEN lâu dài | Có thể giữ | Thường không tương thích |
| SQL named PREPARE | Session-bound | Không mặc định portable |
| Protocol prepared statement | Session-bound | Một số PgBouncer version có tracking nếu cấu hình |
| pg_backend_pid() không đổi qua transactions | Thường có | Không bảo đảm |

### 28.6. Prepared statements với PgBouncer mới

Một số phiên bản PgBouncer hiện đại hỗ trợ tracking protocol-level named prepared statements ở transaction pooling theo cấu hình như `max_prepared_statements`. Không suy luận tương đương SQL `PREPARE`, và phải thử với pgJDBC version/pool mode thực tế.

### 28.7. Double pooling

HikariCP + PgBouncer có thể phù hợp, nhưng cần đo hai hàng đợi/timeout và tổng concurrency. Double pooling không tự khắc phục DB overload.

---

## 29. Idle in transaction

### 29.1. Vấn đề

~~~sql
BEGIN;
SELECT * FROM app.orders WHERE order_id=1001;
-- Ứng dụng ngừng gửi SQL, chưa COMMIT/ROLLBACK.
~~~

Session có thể hiển thị `idle in transaction` trong `pg_stat_activity`.

### 29.2. Hậu quả

- Giữ transaction/snapshot/locks tùy statement và isolation.
- Làm VACUUM cleanup chậm hoặc tăng bloat.
- Chiếm pool slot.
- Gây lock waits và tắc nghẽn các requests khác.

### 29.3. Timeout

~~~sql
SHOW idle_in_transaction_session_timeout;
SHOW statement_timeout;
SHOW lock_timeout;
~~~

`idle_in_transaction_session_timeout` là một safety net, không thay việc application commit/rollback đúng. Khi server chấm dứt backend vì timeout, pool phải loại connection đã chết.

### 29.4. Không đánh đồng active và healthy

Một session có thể không chạy query lúc quan sát mà vẫn giữ transaction mở. Cần giám sát transaction duration và wait events, không chỉ CPU usage.

---

## 30. Savepoint và failed transaction

### 30.1. Giao dịch lỗi

~~~sql
BEGIN;
SELECT 1/0; -- division_by_zero
SELECT 42;  -- bị từ chối vì transaction đang aborted
ROLLBACK;
~~~

Trong protocol, `ReadyForQuery` có thể trả transaction status `E`.

### 30.2. Savepoint

~~~sql
BEGIN;
SAVEPOINT before_optional;
-- SQL có nguy cơ lỗi.
-- Nếu SQL đã báo lỗi và transaction còn có savepoint:
ROLLBACK TO SAVEPOINT before_optional;
SELECT 42;
COMMIT;
~~~

Đoạn này minh họa control flow, không phải một script có lỗi tự động được bắt. Ứng dụng phải quyết định khi nào cần rollback tới savepoint và khi nào rollback cả transaction.

### 30.3. JDBC savepoint

~~~java
connection.setAutoCommit(false);
Savepoint checkpoint = connection.setSavepoint();
try {
    // Thực thi một statement.
} catch (SQLException error) {
    connection.rollback(checkpoint);
    // Chỉ tiếp tục nếu error có thể được xử lý an toàn.
}
connection.commit();
~~~

Không cố tiếp tục mọi transaction sau serialization_failure/deadlock hoặc khi physical connection đã mất. Các trường hợp này thường cần retry lại toàn transaction hoặc tạo connection mới theo chính sách application.

### 30.4. Không trả connection trạng thái E về pool

Pool cần rollback/cleanup theo contract, hoặc loại kết nối hỏng. Caller tiếp theo không được nhận một backend đang ở failed transaction rồi bị lỗi `current transaction is aborted` không liên quan tới code của mình.

---

## 31. URI có nhiều hosts và chọn server phù hợp

### 31.1. Multi-host trong libpq

Libpq hỗ trợ connection string có danh sách hosts trong những cấu hình được hỗ trợ:

~~~text
postgresql://app_reader@pg-a.internal.example:5432,pg-b.internal.example:5432/shopdb?target_session_attrs=read-write&connect_timeout=5
~~~

Nhiều hosts cho phép libpq thử endpoints theo quy tắc lựa chọn/connection attempts của thư viện, nhưng **không** có nghĩa PostgreSQL tự thực hiện load balancing, leader election hoặc replication.

### 31.2. target_session_attrs

`target_session_attrs` giúp client chỉ chấp nhận server có một thuộc tính mong muốn. Ví dụ `read-write` để tránh kết nối vào server đang ở trạng thái read-only trong những ngữ cảnh phù hợp.

~~~text
postgresql://app@pg-a,pg-b/shopdb?target_session_attrs=read-write
~~~

Nếu cả hai không thể chấp nhận write transactions hoặc không có host nào reachable, kết nối sẽ thất bại. Hành vi của các giá trị khác như `primary`, `read-only`, `prefer-standby` phụ thuộc libpq version; hãy kiểm tra tài liệu của client đang dùng.

### 31.3. Multi-host không thay HA

Để có high availability thực sự, hệ thống vẫn cần:

- Đồng bộ hoặc replication phù hợp giữa nodes.
- Cơ chế chọn primary/leader.
- Cấu hình endpoint/DNS/proxy để clients kết nối đúng node.
- Fencing/split-brain prevention trong hệ thống HA.
- Quy tắc retry/transaction recovery ở application.

Một connection URI không giải quyết tính đúng của replication hay failover.

### 31.4. Failover không chuyển transaction đang dang dở

Nếu backend mất kết nối giữa COMMIT và phản hồi của server, application có thể **không biết transaction đã commit hay chưa**. Retry mù một INSERT có side effects có thể tạo duplicate.

Dùng transaction idempotency keys, unique constraints và quy trình reconciliation để xử lý tình huống commit outcome unknown. Đừng coi mọi lỗi `connection reset` nghĩa là “SQL chưa từng chạy”.

### 31.5. Read replica không luôn thích hợp cho mọi SELECT

Một SELECT trên replica có thể đọc dữ liệu trễ so với primary do replication lag. Nếu ứng dụng yêu cầu read-your-writes, cần route tới primary hoặc sử dụng consistency strategy phù hợp, không chỉ chọn `read-only` endpoint.

### 31.6. Retry hợp lý

Có thể retry mở kết nối khi DNS/TCP/auth target fail theo policy; nhưng retry **cả nghiệp vụ** cần phân biệt:

- Statement có chạy trước disconnect không?
- Transaction outcome có xác định không?
- Operation có idempotent không?
- Có external calls hay outbox events liên quan không?
- Retry có làm tăng tải khi DB đang quá tải không?

Exponential backoff có jitter, retry limit và circuit breaker có thể giúp ổn định hệ thống. Không retry vô hạn hàng triệu clients cùng lúc.

---

## 32. Query timeout, cancellation và shutdown

### 32.1. statement_timeout

~~~sql
SET statement_timeout='5s';

SELECT pg_sleep(10);
~~~

Query ngủ 10 giây dự kiến bị hủy sau khoảng timeout, tùy môi trường. Lỗi SQLSTATE thường là `57014` (query_canceled).

Đây là ví dụ **cố ý gây lỗi**; chỉ chạy trong session lab, không đưa trực tiếp vào migration hoặc production application.

### 32.2. lock_timeout

~~~sql
SET lock_timeout='2s';
~~~

`lock_timeout` giới hạn việc chờ lock. Khác `statement_timeout`: một query có thể bị chậm do CPU/I/O mà không chờ lock, nên lock_timeout không tác động theo cách tương tự.

### 32.3. JDBC Statement.setQueryTimeout

Một driver có thể cung cấp `Statement.setQueryTimeout(seconds)`. Cách driver thực hiện có thể sử dụng cancellation và các cơ chế riêng; không giả định hoàn toàn giống server `statement_timeout` trong mọi tình huống.

### 32.4. Cancel request

PostgreSQL wire protocol có cơ chế gửi cancel request riêng dựa trên thông tin backend key từ connection. Driver cung cấp API để hủy query; không khuyến khích ứng dụng tự viết protocol cancel packets nếu không có lý do đặc biệt và kiểm thử an toàn.

### 32.5. pg_cancel_backend vs pg_terminate_backend

~~~sql
SELECT pg_cancel_backend(<backend_pid>);
SELECT pg_terminate_backend(<backend_pid>);
~~~

**Đây chỉ là minh họa cú pháp với placeholder**, không phải SQL có thể chạy nguyên. `pg_cancel_backend` yêu cầu hủy query đang chạy, còn `pg_terminate_backend` yêu cầu chấm dứt backend session theo quyền. Cả hai có thể ảnh hưởng transaction và application clients.

Không chạy trên PID lạ hoặc production chỉ để “dọn idle connections”. Kiểm tra quyền, query, tuổi transaction và người sở hữu session; ưu tiên sửa gốc pool leaks/long transactions.

### 32.6. Cancel không phải rollback tự động mọi nghiệp vụ

Một statement bị cancel trong transaction có thể khiến transaction vào trạng thái failed, cần rollback. Nếu SQL đã thực hiện external side effects trước đó, cancellation/rollback không đảm bảo chúng được thu hồi.

---

## 33. Theo dõi kết nối bằng pg_stat_activity

### 33.1. Query căn bản

~~~sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    client_addr,
    backend_start,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE backend_type = 'client backend'
ORDER BY backend_start;
~~~

Một số fields/details phụ thuộc quyền giám sát. Role không có quyền monitor có thể không thấy tất cả dữ liệu phiên khác. Không cấp `pg_monitor` hoặc quyền tương tự quá rộng chỉ để chạy một dashboard không cần thiết.

### 33.2. Các state thường gặp

| State | Ý nghĩa khái quát |
|---|---|
| `active` | Đang chạy query |
| `idle` | Chờ lệnh mới, không ở trong transaction |
| `idle in transaction` | Transaction vẫn mở, hiện không chạy query |
| `idle in transaction (aborted)` | Transaction đã lỗi nhưng chưa rollback |
| `disabled` | Tracking state có thể bị tắt theo cấu hình |

Không dùng `state='idle'` như kết luận session bị leak. Một pool bình thường có thể cố tình giữ idle server connections để phục vụ requests nhanh.

### 33.3. Query tìm transactions lâu

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
ORDER BY xact_start
LIMIT 30;
~~~

Đây là một snapshot tại thời điểm query. Trong transaction dài, `now()` là transaction timestamp của chính session giám sát; nếu muốn đo thời gian đồng hồ hiện tại có thể dùng `clock_timestamp()`.

### 33.4. Query tìm idle in transaction

~~~sql
SELECT
    pid, usename, application_name, client_addr,
    now() - xact_start AS transaction_age,
    state
FROM pg_stat_activity
WHERE state LIKE 'idle in transaction%'
ORDER BY xact_start;
~~~

Một transaction idle lâu có thể giữ locks/snapshot, ảnh hưởng VACUUM. Xem application traces và transaction ownership trước khi terminate.

### 33.5. Connection count theo ứng dụng

~~~sql
SELECT
    application_name,
    state,
    COUNT(*) AS connections
FROM pg_stat_activity
WHERE backend_type='client backend'
GROUP BY application_name,state
ORDER BY connections DESC, application_name,state;
~~~

Nếu nhiều applications dùng cùng application_name rỗng, kết quả không phân biệt được. Hãy cấu hình application_name hữu ích và không chứa secret.

### 33.6. Connection limit

~~~sql
SHOW max_connections;
SHOW superuser_reserved_connections;
~~~

Một số phiên bản PostgreSQL có thêm reserved connection settings. Không suy số connection slots ứng dụng được phép bằng `max_connections` nếu không xét reserved slots, role limits, poolers và kết nối khác.

---

## 34. Xem TLS thực tế từ phía server

### 34.1. pg_stat_ssl

~~~sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    s.ssl,
    s.version AS tls_version,
    s.cipher,
    s.client_dn
FROM pg_stat_activity AS a
JOIN pg_stat_ssl AS s
  ON s.pid=a.pid
WHERE a.pid=pg_backend_pid();
~~~

Trên kết nối TCP TLS trực tiếp, `ssl=true` thường chứng minh chặng **tới backend đó** đang được mã hóa. Với Unix socket có thể false hoặc trường phù hợp khác.

### 34.2. ssl=true không chứng minh verify-full

Server có thể thấy kết nối TLS nhưng không biết client đã xác minh hostname hay CA theo đúng policy của client. `ssl=true` không đủ để kết luận “client xác thực server an toàn”.

### 34.3. Proxy làm thay đổi quan sát

Nếu app --TLS--> PgBouncer --TLS--> PostgreSQL, `pg_stat_ssl` trên PostgreSQL chỉ quan sát chặng PgBouncer→PostgreSQL, không tự nói chặng app→PgBouncer có TLS hay không.

### 34.4. Client-side inspection

`psql` có lệnh hiển thị thông tin connection hiện tại (như `\conninfo`). Kết hợp quan sát client, proxy config và server pg_stat_ssl để hiểu toàn bộ đường truyền.

### 34.5. TLS version/cipher

TLS protocol/cipher suite phụ thuộc server/client/OpenSSL hoặc thư viện TLS tương ứng. Không hardcode “mọi phiên đều TLS 1.3” nếu đang chạy môi trường không đồng nhất; đo thực tế và cấu hình minimum theo chính sách bảo mật.

---

## 35. psql: bộ công cụ chẩn đoán kết nối cơ bản

### 35.1. Kết nối TCP bằng tham số tường minh

~~~bash
psql -h db.internal.example -p 5432 -U app_reader -d shopdb
~~~

Nếu cần TLS/CA, cấu hình service/environment/connection string thay vì chỉ cung cấp host và mong client tự xác minh hostname đúng.

### 35.2. Kết nối bằng URI

~~~bash
psql "postgresql://app_reader@db.internal.example:5432/shopdb?sslmode=verify-full&connect_timeout=5"
~~~

Không gắn password thật vào câu lệnh sẽ được lưu trong shell history.

### 35.3. Một số lệnh psql hữu ích

| Lệnh | Tác dụng |
|---|---|
| `\conninfo` | Hiển thị kết nối hiện tại (theo psql/client capabilities) |
| `\c dbname` | Chuyển database/thiết lập kết nối mới |
| `\dt` | Liệt kê relations loại table có thể thấy |
| `\dn` | Liệt kê schemas |
| `\du` | Liệt kê roles (theo quyền xem metadata) |
| `\timing on` | Hiện thời gian thực thi câu lệnh phía client |
| `\set ON_ERROR_STOP on` | Dừng script khi SQL error, hữu ích trong migration theo yêu cầu |
| `\q` | Thoát psql |

### 35.4. \c có thể tạo session khác

Khi dùng `\c` để kết nối lại/đổi database, backend session mới có thể được tạo và mất những prepared statements, temp tables hoặc `SET` của session cũ. Không coi `\c` giống SQL `SET search_path`.

### 35.5. Một query xác minh end-to-end

~~~sql
SELECT
    current_database(),
    current_user,
    pg_backend_pid(),
    current_setting('application_name'),
    pg_is_in_recovery() AS is_standby;
~~~

`pg_is_in_recovery()=true` gợi ý server đang trong recovery/hot standby mode ở thời điểm query; nó không tự thay thế khả năng kiểm tra primary/read-write status theo HA/client routing config.

---

## 36. Chẩn đoán lỗi theo lớp

| Triệu chứng | Lớp có thể gặp | Cách khoanh vùng |
|---|---|---|
| Không phân giải được hostname | DNS | Kiểm tra tên, resolver, network policy |
| Connection refused | TCP/listener | Kiểm tra host/port, listen_addresses, firewall |
| Connection timed out | Network/firewall/load | Kiểm tra route, security groups, proxy, connect timeout |
| Server không hỗ trợ SSL/TLS như client yêu cầu | TLS negotiation | Kiểm tra server/proxy TLS config |
| Certificate verify failed | PKI/TLS | Kiểm tra CA, hostname, expiry, clock |
| No pg_hba.conf entry | Admission/auth rule | Kiểm tra connection type, source IP, HBA order |
| Password authentication failed | Auth | Kiểm tra role/credential/hash/auth method |
| Database does not exist | Startup/DB name | Kiểm tra tên database/endpoint |
| Role does not exist | Login identity | Kiểm tra `user` và role configuration |
| Permission denied for table | SQL authorization | GRANT, ownership, schema USAGE, RLS |
| Too many connections | Server capacity | max_connections, reserved slots, pools/leaks |
| Failed transaction after SQL error | Transaction | Rollback/retry theo contract |
| Pool acquisition timeout | Application pool | Active/idle/waiting, leaks, transactions |
| Connection reset by peer | Socket/proxy/server | Failover/restart, timeout, NAT, backend termination |
| Query canceled | Query timeout/cancellation | SQLSTATE, statement_timeout, client cancel |
| Session state lạ | Pool reuse | RESET/DISCARD, SET LOCAL, backend affinity |

### 36.1. Kiểm tra từ ngoài vào trong

1. Endpoint/URI thực tế (không lộ password).
2. DNS và network route.
3. TCP port/listener/proxy.
4. TLS mode, certificate và trust roots.
5. Role/database/HBA authentication.
6. SQL privileges và RLS.
7. Pool checkout, query timeout và transaction state.
8. Session settings và proxy routing.

Một lỗi `permission denied` không nên được sửa bằng cách đổi `listen_addresses` hoặc vô hiệu hóa TLS.

### 36.2. Không ghi log password khi debug

Log redacted có thể chứa `host, port, database, application_name, sslmode` và sanitized error class/SQLSTATE. Nếu driver exception nhúng connection string, cần redaction trước khi đẩy lên observability systems.

---

## 37. Một sơ đồ quyết định khi không kết nối được

~~~mermaid
flowchart TD
    A["Ứng dụng không kết nối PostgreSQL"] --> B{"DNS/endpoint hợp lệ?"}
    B -- "Không" --> C["Kiểm tra tên miền, DNS, proxy, network"]
    B -- "Có" --> D{"TCP/socket mở được?"}
    D -- "Không" --> E["Port, listen_addresses, firewall, timeout"]
    D -- "Có" --> F{"TLS negotiation/verify thành công?"}
    F -- "Không" --> G["CA, hostname, mode, proxy TLS"]
    F -- "Có" --> H{"Authentication và database CONNECT thành công?"}
    H -- "Không" --> I["pg_hba, role, credential, database"]
    H -- "Có" --> J{"SQL SELECT/UPDATE được phép?"}
    J -- "Không" --> K["GRANT, schema USAGE, RLS"]
    J -- "Có" --> L{"Pool/transactions hoạt động ổn?"}
    L -- "Không" --> M["Checkout waits, idle in transaction, RESET, capacity"]
    L -- "Có" --> N["Giám sát và benchmark workload"]
~~~

### 37.1. Một nguyên tắc

**Đừng giảm cơ chế bảo mật của tầng cao hơn để chữa lỗi ở tầng thấp hơn.** Ví dụ không nên dùng `sslmode=disable` để né lỗi certificate, hoặc grant superuser để né lỗi ứng dụng thiếu SELECT một bảng.

---

## 38. Multi-tenant và quyền: database session không tự biết HTTP user

### 38.1. Database role trong application pool

Nhiều apps dùng một role `app_runtime` cho mọi HTTP requests. Khi session PostgreSQL đã được xác thực bằng `app_runtime`, database **không tự biết** browser user nào đứng sau từng request.

### 38.2. RLS với trusted context

Nếu policies dựa trên tenant identity, phải bảo đảm identity được xác thực, được đặt bởi trusted layer và **không thể bị client giả mạo qua input hoặc SQL quyền rộng**.

### 38.3. Transaction-local context

`SET LOCAL` trong một transaction có thể giúp tránh rò state qua pool, nhưng vẫn cần:

- Authentication/authorization trước khi chọn tenant.
- Đảm bảo mọi queries dùng đúng transaction.
- Không cấp cho caller quyền chạy SQL tùy ý thay đổi context.
- Rollback/cleanup khi lỗi.
- Kiểm thử nhiều requests/tenants khi pool reuse cùng physical connection.

### 38.4. Transaction pooling và set local

Khi dùng PgBouncer transaction pooling, `SET LOCAL` được thực thi trong cùng explicit transaction với các SQL phía sau có thể áp dụng đúng trên backend được giữ cho transaction đó. `SET` session-level qua transactions **không được dựa vào**.

### 38.5. Không suy từ application_name

`application_name` chỉ là tên client/worker, không phải user identity được xác thực. Không tạo RLS policy bằng cách tin mù giá trị application_name do client tự khai báo.

---

## 39. Capacity planning cho nhiều ứng dụng

### 39.1. Một ví dụ ước lượng

Giả sử có:

- 12 application instances.
- Mỗi instance HikariCP maximumPoolSize = 15.
- 4 background workers, mỗi worker tối đa 5 DB connections.
- 10 monitoring/admin connections dự phòng.

Tổng tiềm năng = **12 × 15 + 4 × 5 + 10 = 210** kết nối client, trước khi xét proxy/HA và hệ thống khác.

Nếu dùng PgBouncer transaction pooling, số backend server connections có thể nhỏ hơn tổng client connections, nhưng cần sizing pooler server pool và queueing theo workload.

### 39.2. Những chỉ số cần theo dõi

- Active, idle và pending connections ở pool.
- Checkout wait time (p50/p95/p99).
- PostgreSQL backend count theo app/db/user.
- Transaction duration, `idle in transaction` sessions.
- Query latency, locks, deadlocks và waits.
- Backend connection churn.
- TLS/auth handshake latency và failures.
- CPU, memory, WAL, I/O, autovacuum lag.
- PgBouncer client/server connections và queue waits nếu dùng.

### 39.3. Connection budget không phải throughput budget

Mỗi connection là một resource. Một DB với 500 connections active đều chạy query nặng có thể chậm hơn DB chỉ có 80 connections được giới hạn concurrency tốt. Hãy benchmark theo requests/second, transaction durations và resource bottleneck.

### 39.4. Phân biệt idle connections với leak

Một pool giữ 20 idle physical connections trong khi không có traffic có thể là hành vi bình thường. Leak là **application không trả lease** hoặc transaction không đóng, gây pool exhaustion. Cần dùng metrics và traces thay vì chỉ đếm idle backends.

---

## 40. Session hygiene: checklist triển khai

### 40.1. Định nghĩa hợp đồng mỗi request

- [ ] Request nhận connection từ pool và luôn trả connection (try-with-resources).
- [ ] Transactions được commit hoặc rollback đúng mọi nhánh.
- [ ] Không trả connection đang ở failed transaction.
- [ ] Session SET/role/search_path được reset theo pool/framework contract.
- [ ] Dùng `SET LOCAL` khi cần context transaction, không dựa vào state của request trước.
- [ ] Không để session advisory locks, temp objects, LISTEN registrations không chủ đích.
- [ ] Không dựa vào backend PID/SQL prepared statements tồn tại khi transaction pooling.

### 40.2. Bảo mật cấu hình

- [ ] Không hardcode password trong URI/source/log.
- [ ] Mỗi service có DB role ít quyền.
- [ ] TLS verify-full và CA đúng theo endpoint.
- [ ] Không dùng trust HBA trên mạng untrusted.
- [ ] SCRAM/auth policies phù hợp client/server.
- [ ] Firewall/private network chỉ mở phạm vi cần thiết.
- [ ] application_name hữu ích nhưng không có secret.

### 40.3. Vận hành

- [ ] Kết nối/pool có timeout phù hợp từng tầng.
- [ ] Tổng pool sizes nằm trong connection budget.
- [ ] Có alert cho pool pending, idle in transaction và errors.
- [ ] Có circuit breaker/backoff cho DB outage.
- [ ] Có strategy failover/DNS refresh và idempotency.
- [ ] Có quan sát pg_stat_activity/pg_stat_ssl phù hợp quyền.
- [ ] Có playbook thu hồi/rotation credentials và CA.
- [ ] Có kiểm thử proxy pooling với session-specific features.

---

## 41. Tình huống thực tế: kết nối thành công trên laptop nhưng lỗi trong container

### 41.1. Mô tả

Một ứng dụng Java chạy trên laptop dùng:

~~~text
jdbc:postgresql://localhost:5432/shopdb
~~~

Khi đóng gói Docker và chạy container, kết nối báo `Connection refused` dù PostgreSQL vẫn chạy trên host.

### 41.2. Vì sao?

`localhost` trong container chỉ **loopback của network namespace của container**, không nhất thiết là host OS nơi PostgreSQL đang lắng nghe. Nếu app và database là hai containers khác nhau, mỗi container có `localhost` riêng.

### 41.3. Giải pháp

- Trong Docker Compose network, dùng hostname/service name của database theo cấu hình network.
- Nếu DB ở host, sử dụng endpoint được environment hỗ trợ và bảo vệ network.
- Kiểm tra PostgreSQL `listen_addresses`, HBA và firewall.
- Không hardcode `localhost` cho mọi deployment.

### 41.4. Thêm TLS và role

Khi đổi endpoint sang host/service name, certificate verification phải phù hợp tên endpoint. Đừng tắt `verify-full` như giải pháp mặc định. Role/password phải được quản lý qua secrets và đúng HBA source IP/path của container.

---

## 42. Tình huống thực tế: pool trả dữ liệu của tenant trước

### 42.1. Mô tả

Request A thuộc tenant 10 chạy:

~~~sql
SET search_path=tenant_10,public;
~~~

Sau đó đóng logical connection nhưng pool tái sử dụng backend. Request B thuộc tenant 20 mượn đúng physical connection và vô tình query table unqualified mà không set lại search_path.

### 42.2. Nguyên nhân

Session-level `SET` tồn tại qua COMMIT và pool checkout. Nếu pool/framework không reset đủ state, request B có thể đọc nhầm schema.

### 42.3. Hướng xử lý

1. Không dùng application-controlled search_path không được validate như security boundary duy nhất.
2. Dùng schema-qualified SQL hoặc trusted tenant mapping.
3. Nếu cần context theo request, đặt `SET LOCAL` trong một explicit transaction đúng.
4. Đảm bảo transaction thành công hoặc rollback luôn dọn context.
5. Test 2 tenants chạy xen kẽ trên pool size 1 để quan sát state leakage dễ hơn.
6. Review RLS/GRANT để ngay cả khi app bug, database vẫn không cho đọc dữ liệu không được phép.

### 42.4. Kết luận

Một connection pool bình thường có thể tái sử dụng backend session. Điều này tốt cho hiệu năng nhưng đòi **session hygiene** và quyền truy cập database không phụ thuộc state cũ.

---

## 43. Tình huống thực tế: lỗi chuẩn bị câu lệnh qua PgBouncer

### 43.1. Mô tả

Ứng dụng dùng pgJDBC PreparedStatement qua PgBouncer transaction pooling. Sau nhiều requests, một số câu query báo lỗi rằng prepared statement không tồn tại hoặc tên statement xung đột.

### 43.2. Nguyên nhân có thể

- Client driver cache server-side prepared statements thuộc backend trước.
- PgBouncer chuyển transaction tới backend khác.
- PgBouncer version/config chưa hỗ trợ protocol-level prepared statement tracking theo cách driver yêu cầu.
- SQL PREPARE tồn tại trong backend state nhưng app tin nó gắn với client session.

### 43.3. Cách xử lý

1. Xác nhận PgBouncer mode: session, transaction hay statement.
2. Xác nhận pgJDBC version và server preparation settings.
3. Xác nhận khả năng/trạng thái `max_prepared_statements` của PgBouncer nếu version hỗ trợ.
4. Đo thực tế đường Parse/Bind/Execute và lỗi theo backend PIDs.
5. Nếu không tương thích, dùng session pooling hoặc điều chỉnh driver/server preparation theo tài liệu; không tắt mọi parameter binding.
6. Vẫn dùng JDBC PreparedStatement để tách SQL/data cho an toàn SQL injection, kể cả khi thay server-side prepare caching behavior.

### 43.4. Không đánh đồng parameterization với server-side plan caching

Tắt hoặc điều chỉnh server-side prepared statement reuse **không đồng nghĩa** phải chuyển sang ghép raw SQL input. Parameter binding vẫn là yêu cầu bảo mật.

---

## 44. Tình huống thực tế: lỗi sau failover nhưng commit chưa rõ

### 44.1. Mô tả

API ghi payment và gửi `COMMIT`. Ngay sau đó network disconnect trước khi client nhận response. Ứng dụng biết kết nối đã mất nhưng không biết database đã commit hay chưa.

### 44.2. Vì sao không được retry INSERT đơn thuần?

Nếu transaction đã commit rồi mà API retry bằng một ID mới, có thể tạo hai payment rows hoặc hai external side effects.

### 44.3. Thiết kế an toàn hơn

- Mỗi nghiệp vụ payment có **idempotency key** được lưu và enforce UNIQUE trong database.
- Khi reconnect, truy vấn trạng thái giao dịch theo business key.
- Dùng transactionally written outbox cho external effects và idempotent consumers.
- Xử lý unique conflict như một phần bình thường của idempotency protocol, không coi mọi `23505` là “thành công” nếu payload khác nhau.
- Có giới hạn retries và backoff.

### 44.4. Connection string không thay giải pháp này

Dù multi-host URI có thể giúp thử endpoint mới, nó không tự xác định transaction outcome của kết nối cũ. Đây là bài toán atomicity + idempotency ở tầng nghiệp vụ.

---

## 45. Các ngộ nhận phổ biến

| Ngộ nhận | Vì sao không đúng | Cách hiểu đúng |
|---|---|---|
| “Kết nối PostgreSQL chỉ là một TCP socket” | Còn TLS, startup, auth, protocol state | Phân lớp kết nối |
| “Ping được host nghĩa là DB accessible” | Ping khác TCP/TLS/auth | Kiểm tra endpoint và các tầng riêng |
| “Port 5432 luôn đúng” | PostgreSQL có thể đổi port | Kiểm tra config thực tế |
| “localhost luôn là host OS” | Trong container khác namespace | Dùng endpoint của deployment |
| “Unix socket giống TCP localhost” | IPC, HBA và auth khác | Phân biệt local/host rules |
| “TLS require nghĩa đã verify hostname” | Encryption khác server identity | verify-full với CA đúng |
| “Percent-encode password làm password bí mật” | Chỉ URI escaping | Secret store/redaction |
| “Cứ dùng sslmode=disable để sửa certificate” | Mất bảo vệ transport | Sửa PKI/hostname |
| “SCRAM thay TLS” | SCRAM xác thực credential, TLS bảo vệ kênh | Dùng các lớp phù hợp |
| “pg_hba.conf là quyền SELECT trên bảng” | HBA cho admission/auth | GRANT/RLS riêng |
| “HBA tự thử rule sau khi password sai” | Quy tắc first matching record | Sửa matching/auth |
| “JDBC URL giống libpq URI mọi options” | Client properties khác | Tra pgJDBC docs |
| “connect_timeout là query timeout” | Chờ mở kết nối khác thực thi SQL | Timeout từng tầng |
| “pool timeout nghĩa TCP không thông” | Có thể bận slot | Đo checkout waits |
| “Connection.close() luôn đóng physical socket” | Pool trả logical connection | Understand pool lifecycle |
| “Một HTTP request là một PostgreSQL session” | Pool reuse | Theo dõi transaction/checkout |
| “COMMIT luôn làm mất SET session-level” | Session SET tồn tại qua transaction | SET LOCAL/reset |
| “RESET ALL làm mất mọi prepared/temp/locks” | Không dọn toàn bộ session state | DISCARD ALL/correct cleanup |
| “DISCARD ALL dùng được trong BEGIN” | Bị cấm trong transaction block | Cleanup đúng thời điểm |
| “pg_backend_pid là user ID” | Là process ID của backend | Dùng proper identity |
| “Backend PID không đổi qua pool proxy” | Transaction pooling có thể đổi | Không dựa session affinity |
| “PreparedStatement luôn là SQL PREPARE” | Driver/protocol caching khác | Hiểu Parse/Bind và driver |
| “? trong URL và ? SQL giống nhau” | Hai lớp hoàn toàn khác | URL options vs bind param |
| “Param binding dùng được cho tên bảng” | Parameters là values | Whitelist/quote identifiers |
| “Có bind params là có authorization” | SQL injection khác quyền dữ liệu | GRANT/RLS |
| “ReadyForQuery I nghĩa session đã đóng” | I là idle transaction status | Session còn sống |
| “Failed transaction vẫn SELECT tiếp được” | State E cần rollback | Error handling |
| “Timeout cancellation tự hoàn tác mọi external side effect” | External systems khác transaction | Outbox/idempotency |
| “Pool lớn hơn luôn nhanh hơn” | Tăng contention và resources | Benchmark/sizing |
| “Idle connections đều là leaks” | Pool chủ động giữ idle | Đo active/checkout |
| “Idle in transaction vô hại vì không chạy query” | Có thể giữ locks/snapshot | Commit/rollback sớm |
| “PgBouncer transaction pool giữ mọi SET state” | Backends đổi | SET LOCAL/avoid session state |
| “PgBouncer luôn không dùng được prepared statements” | Version/config có tracking | Verify compatibility |
| “Multi-host tự làm load balancing và replication” | Chỉ connection selection | HA infrastructure riêng |
| “Read replica luôn thấy write ngay lập tức” | Replication lag | Consistency strategy |
| “Connection reset nghĩa transaction chưa commit” | Outcome có thể unknown | Idempotency/reconcile |
| “pg_stat_ssl.ssl=true chứng minh client verify-full” | Server không biết client hostname validation | Client-side PKI config |
| “pg_notify là durable message queue” | Notification không lưu durable cho offline clients | Outbox/broker |
| “application_name là authenticated identity” | Client tự khai báo | Authentication/RLS riêng |
| “Mọi SQLException là network failure” | Constraint/auth/query khác nhau | SQLSTATE and layer diagnosis |
| “Không nên đặt timeout vì gây lỗi” | Không có giới hạn dễ treo tài nguyên | Chọn timeouts theo SLO |
| “Gửi password vào exception cho DBA dễ debug” | Có thể lộ secret | Log redacted metadata |

---

## 46. Checklist cấu hình PostgreSQL production

### 46.1. URI/driver

- [ ] Chọn đúng cú pháp libpq URI, key=value hoặc pgJDBC URL.
- [ ] Hostname/port/database/user explicit cho môi trường.
- [ ] Encode URI components đúng, không double-encode.
- [ ] Credentials lấy từ secret store/passfile, không trong source.
- [ ] JDBC properties được kiểm tra theo pgJDBC version.
- [ ] `application_name` có ích cho monitoring, không chứa secret.
- [ ] Timeout kết nối/query/pool phân biệt rõ về units.

### 46.2. Network và TLS

- [ ] Endpoint reachable chỉ từ network được phép.
- [ ] PostgreSQL listen_addresses/port và HBA phù hợp.
- [ ] TLS mode verify-full khi yêu cầu xác minh server.
- [ ] Root CA ở client đúng, có kế hoạch rotation.
- [ ] Hostname khớp certificate; không bypass validation.
- [ ] Nếu dùng proxy, kiểm soát TLS trên cả client–proxy và proxy–server.
- [ ] SCRAM/auth method tương thích client/role/server.

### 46.3. Quyền và dữ liệu

- [ ] Database roles ít quyền cho từng service.
- [ ] GRANT/RLS/USAGE schema được review.
- [ ] Client không được tự giả mạo tenant identity.
- [ ] API dùng parameterized SQL và validates dynamic identifiers.
- [ ] Không dùng backend PID/application_name làm authenticated user ID.

### 46.4. Pool/session

- [ ] Tổng maximum pool size phù hợp max_connections và CPU/IO.
- [ ] Connection luôn release trong finally/try-with-resources.
- [ ] Transactions có COMMIT/ROLLBACK trên mọi nhánh.
- [ ] Session SET/ROLE/search_path không rò qua lượt checkout.
- [ ] Không giữ idle in transaction.
- [ ] Transaction pooling không phụ thuộc TEMP/LISTEN/advisory locks session-level.
- [ ] Prepared statements tương thích PgBouncer/driver version.
- [ ] Pool loại connection hỏng sau failover/socket errors.

### 46.5. Vận hành/failover

- [ ] Có pg_stat_activity/pg_stat_ssl observations.
- [ ] Có alerts cho pool pending, auth/TLS errors, idle transactions.
- [ ] Có retry/backoff và idempotency khi commit outcome unknown.
- [ ] Có kiểm tra replica lag nếu dùng read replicas.
- [ ] Có kế hoạch credential/certificate rotation.
- [ ] Có staging tests cho DNS failover, proxy restart và application rolling deployments.

---

## 47. Sơ đồ vòng đời kết nối ứng dụng

~~~mermaid
flowchart LR
    A["Application request"] --> B["Get Connection từ pool"]
    B --> C{"Pool có connection hợp lệ?"}
    C -- "Có" --> D["Mượn physical session"]
    C -- "Không" --> E["DNS/TCP/TLS/Startup/Auth"]
    E --> D
    D --> F["Begin transaction nếu cần"]
    F --> G["SET LOCAL context / Prepared SQL"]
    G --> H{"SQL thành công?"}
    H -- "Có" --> I["COMMIT"]
    H -- "Không" --> J["ROLLBACK / retry policy"]
    I --> K["Reset session state theo contract"]
    J --> K
    K --> L["Trả logical connection cho pool"]
    L --> M["Physical connection được tái sử dụng hoặc đóng"]
~~~

### 47.1. Ba nguyên tắc phải bảo toàn

**Thứ nhất**, credential và TLS chỉ quyết định cách phiên được thiết lập/an toàn, không thay quyền trên rows.

**Thứ hai**, pool reuse là tối ưu tài nguyên nhưng biến việc reset session state thành yêu cầu về tính đúng/bảo mật.

**Thứ ba**, retry sau disconnect không bảo đảm idempotency; transaction outcome unknown phải được giải quyết ở tầng nghiệp vụ.

---

## 48. Bài tập thực hành

Các bài tập sử dụng các ví dụ trong bài. Những câu hỏi có SQL sửa cấu hình hoặc tạo transaction lỗi chỉ nên chạy ở **database thử nghiệm** được phép; không tắt TLS, tạo role quyền rộng hoặc terminate backend trong production để thử.

### Bài 1 — Các lớp của kết nối

Một ứng dụng Java báo `Connection refused` khi gọi DB. Hãy liệt kê thứ tự các lớp cần kiểm tra từ DNS tới quyền SQL và giải thích vì sao sửa password không phải bước đầu.

### Bài 2 — Hostname, port và database

Giải thích vai trò của `db.internal.example`, `5432` và `shopdb` trong chuỗi `postgresql://app@db.internal.example:5432/shopdb`. Host và database có thể đặt tên giống nhau không?

### Bài 3 — TCP so với Unix socket

Trên cùng máy, `psql` không có `-h` kết nối được, nhưng `psql -h 127.0.0.1` thất bại. Nêu hai lý do có thể.

### Bài 4 — StartupMessage

Kể ít nhất ba loại thông tin có thể được client gửi khi startup một PostgreSQL session. Password có nhất thiết được gửi dưới dạng plaintext trong StartupMessage không?

### Bài 5 — Authentication và authorization

Một role đã đăng nhập PostgreSQL thành công nhưng SELECT bảng báo `permission denied`. Vì sao HBA authentication thành công chưa đủ?

### Bài 6 — ReadyForQuery

Giải thích ba transaction status `I`, `T` và `E`. Trong tình huống nào cần `ROLLBACK`?

### Bài 7 — Simple query

Mô tả một luồng simple query SELECT từ frontend tới backend. Nêu các loại message có thể được server trả về.

### Bài 8 — Extended query

Sắp xếp các thao tác `Parse`, `Bind`, `Execute`, `Sync` và giải thích mục đích parameter binding.

### Bài 9 — Bind tên bảng?

Có thể dùng `SELECT * FROM $1` và bind `$1='customers'` để thay tên bảng không? Đề xuất cách xây dynamic identifiers an toàn.

### Bài 10 — Dạng URI libpq

Viết URI cho user `reporter`, host `db.example.internal`, port 5433, database `analytics`, yêu cầu `sslmode=verify-full` và `application_name=nightly-report`. Không nhúng password.

### Bài 11 — Percent-encoding

Giá trị thử nghiệm `p@ss/word#1` phải được viết như thế nào nếu buộc phải đặt vào password component của URI? Vì sao encode không bảo mật password?

### Bài 12 — Double encoding

Giá trị `%40` bị encode thêm lần nữa sẽ trở thành gì? Client có thể hiểu thành ký tự gì sau khi decode một lần?

### Bài 13 — Query string

Viết thêm `connect_timeout=5` và `sslrootcert=/etc/postgresql/ca.pem` vào URI libpq có sslmode=verify-full. Chỉ ra phần URL cần percent-encoding.

### Bài 14 — IPv6 literal

Viết dạng URI đúng cho host IPv6 `2001:db8::5`, port 5432 và database `shopdb`.

### Bài 15 — key=value

Viết lại URI của bài 10 theo key=value libpq connection string. Nếu `application_name` có dấu cách, phải xử lý thế nào?

### Bài 16 — Service file

Tạo một profile `shop_readonly` chứa host/port/db/user/TLS. Viết lệnh `psql` sử dụng profile đó. Vì sao service file không nhất thiết là chỗ nên lưu password?

### Bài 17 — JDBC URL

Viết JDBC URL tương đương với endpoint của bài 10. Dạng JDBC có giống hệt libpq URI về scheme và mọi query property không?

### Bài 18 — JDBC PreparedStatement

Viết đoạn Java JDBC query theo `customer_id` dùng bind parameter và try-with-resources. Phân biệt `?` trong SQL JDBC với `?` mở query parameters của URL.

### Bài 19 — So sánh timeout

Phân biệt `connect_timeout` libpq, `connectionTimeout` HikariCP, `statement_timeout` PostgreSQL và `socketTimeout` của pgJDBC.

### Bài 20 — TLS modes

So sánh `require`, `verify-ca` và `verify-full`. Trong production, khi cần xác minh chính xác server hostname, nên chọn cái nào?

### Bài 21 — IP và certificate

Certificate chỉ có DNS `db.example.internal`, nhưng ứng dụng đổi URL sang IP `10.0.0.8`. Vì sao `sslmode=verify-full` có thể thất bại? Có nên tắt verification không?

### Bài 22 — SCRAM

SCRAM-SHA-256 và TLS giải quyết hai nhiệm vụ nào khác nhau? Có nên chọn chỉ SCRAM mà không có TLS cho network không tin cậy không?

### Bài 23 — HBA

Viết dòng HBA minh họa cho role `app_reader` kết nối database `shopdb` từ CIDR `10.20.0.0/16` qua TLS, dùng `scram-sha-256`.

### Bài 24 — First-match rule

Nếu một HBA rule phù hợp nhưng password sai, PostgreSQL có tự thử rule tiếp theo để tìm một method khác không?

### Bài 25 — pg_backend_pid

Viết query trả PID của backend, database, user và application_name hiện tại. Tại sao PID không nên dùng làm một business identity?

### Bài 26 — Hai sessions

Mở hai kết nối psql độc lập, so sánh `pg_backend_pid()`. Khi dùng PgBouncer transaction pooling, PID có thể thay thế nào giữa hai transactions?

### Bài 27 — SET và SET LOCAL

Nêu khác biệt giữa `SET TIME ZONE 'UTC'` và `SET LOCAL TIME ZONE 'UTC'`. Viết ví dụ transaction kiểm chứng.

### Bài 28 — Session state leak

Pool size = 1. Request A chạy `SET search_path=tenant_a` rồi trả connection; request B truy vấn bảng không schema-qualified. Nguy cơ gì xảy ra và cách xử lý?

### Bài 29 — Temp table

Một request tạo TEMP TABLE không ON COMMIT DROP. Request sau nhận đúng backend có thể nhìn thấy bảng đó không? Viết syntax tạo temp table chỉ tồn tại tới COMMIT.

### Bài 30 — Advisory lock

So sánh `pg_advisory_lock` và `pg_advisory_xact_lock` về lifetime. Vì sao session-level lock rủi ro khi dùng connection pool?

### Bài 31 — LISTEN

Vì sao `LISTEN channel` không phù hợp với giả định rằng transaction pool giữ cùng backend qua nhiều transactions?

### Bài 32 — Pool checkout

Một ứng dụng có 10 instances, mỗi HikariCP pool tối đa 20 connections; thêm 10 background connections. Tổng connections tiềm năng là bao nhiêu? Vì sao đây không phải throughput guarantee?

### Bài 33 — Pool leak

Một endpoint quên gọi `Connection.close()` trên một error path. Biểu hiện nào có thể xảy ra? Viết một cấu trúc Java giúp đảm bảo trả connection.

### Bài 34 — Idle in transaction

Giải thích vì sao backend `idle in transaction` có thể gây VACUUM/lock problems dù CPU không cao. Viết query tìm 10 transactions có `xact_start` cũ nhất.

### Bài 35 — Transaction state E

Sau `BEGIN; SELECT 1/0; SELECT 42;`, câu SELECT thứ hai thường thế nào? Cần thực hiện gì trước khi tiếp tục?

### Bài 36 — Savepoint

Viết SQL minh họa việc rollback một statement lỗi về savepoint và tiếp tục transaction. Khi nào không nên coi savepoint là giải pháp cho mọi lỗi kết nối?

### Bài 37 — PgBouncer pooling modes

So sánh session, transaction và statement pooling. Mode nào thuận lợi nhất cho session-level prepared statements, temp tables và LISTEN?

### Bài 38 — Prepared statements qua proxy

Một ứng dụng Java dùng prepared statements nhưng qua PgBouncer transaction pooling bị lỗi statement không tồn tại. Nêu ba thông số/thành phần cần kiểm tra trước khi bỏ parameterization.

### Bài 39 — pg_stat_activity

Viết query nhóm số connections theo application_name và state, đồng thời giải thích vì sao `idle` không đồng nghĩa leak.

### Bài 40 — pg_stat_ssl

Viết query xác minh kết nối backend hiện tại có SSL hay không và TLS version. Nếu `ssl=true`, có chứng minh client đã dùng verify-full không?

### Bài 41 — Container localhost

Một ứng dụng chạy trong Docker container dùng JDBC host `localhost` để kết nối PostgreSQL nằm trong container khác. Vì sao thất bại, và nên dùng hostname nào?

### Bài 42 — Multi-host / failover

Viết URI libpq gồm hai hosts `pg-a.internal.example`, `pg-b.internal.example`, database shopdb, target_session_attrs=read-write. URI này có tự tạo replication hoặc đảm bảo không split-brain không?

### Bài 43 — Read replica consistency

Ứng dụng vừa INSERT vào primary rồi SELECT ngay từ replica nhưng chưa thấy row. Giải thích và nêu hai hướng xử lý khi cần read-your-writes.

### Bài 44 — Unknown commit

Network mất ngay sau khi client gửi COMMIT nhưng trước khi nhận response. Có được giả định transaction rollback và retry INSERT với ID mới không? Nêu thiết kế idempotency.

### Bài 45 — Cancel query

Phân biệt query cancel, backend termination, statement_timeout và lock_timeout. Tại sao không nên gọi pg_terminate_backend trên PID bất kỳ để giảm số connections?

### Bài 46 — Phân lớp lỗi

Phân loại năm lỗi sau: DNS lookup failed, certificate verify failed, password authentication failed, permission denied for table, pool acquisition timeout. Với mỗi lỗi, nêu một hướng chẩn đoán.

### Bài 47 — Multi-tenant context

Một RLS policy dựa vào `current_setting('app.tenant_id')` nhưng HTTP client tự chọn được tenant_id. Vì sao không an toàn? SET LOCAL có tự giải quyết vấn đề identity spoofing không?

### Bài 48 — Chẩn đoán tổng hợp

Một service dùng HikariCP qua PgBouncer transaction pooling với TLS, khoảng 20 instances. Sau failover, app báo vừa `connection reset`, vừa `prepared statement does not exist`, pool waiting tăng và transaction đang xử lý bị retry. Hãy đề xuất runbook điều tra/tối ưu ít nhất tám bước, bao gồm transaction outcome, credentials, TLS, pool/proxy, prepared statements, session state, retry và observability.

---

## 49. Lời giải và giải thích — bài 1 đến 24

### Bài 1 — Lần lượt kiểm tra từng lớp

Thứ tự hợp lý: DNS/hostname → TCP port/socket và routing/firewall → TLS negotiation/certificate → StartupMessage/role/database → HBA/password authentication → database privileges/SQL permissions → pool/session state.

`Connection refused` thường xuất hiện ở tầng transport khi không có service lắng nghe trên endpoint hoặc kết nối bị từ chối. Password chỉ được dùng sau khi đã đến giai đoạn authentication; đổi password ngay không xử lý đúng nguyên nhân.

### Bài 2 — Host, port, database

- `db.internal.example`: endpoint host mạng.
- `5432`: port TCP server/proxy.
- `shopdb`: tên database trong cluster PostgreSQL.
- `app`: tên database role yêu cầu đăng nhập.

Tên host và database có thể trùng chuỗi về mặt cú pháp, nhưng chúng là hai namespace/khái niệm khác nhau. Không tự suy database name từ hostname.

### Bài 3 — Socket khác TCP

Có ít nhất hai nguyên nhân:

1. `psql` không có `-h` có thể dùng Unix socket, trong khi `-h 127.0.0.1` bắt buộc TCP. PostgreSQL có thể không lắng nghe TCP hoặc port sai.
2. `pg_hba.conf` có rule `local ... peer` cho socket nhưng rule `host ...` cho TCP yêu cầu password hoặc từ chối source.

Kiểm tra `SHOW listen_addresses; SHOW port;` sau khi vào server qua socket và xem HBA records được áp dụng. Không đổi rule thành `trust` trên network untrusted để “chữa” kết nối.

### Bài 4 — StartupMessage

Client có thể gửi `user`, `database`, `application_name` và một số startup parameters hợp lệ. Password authentication diễn ra qua các message riêng sau khi server chọn auth method; StartupMessage không đơn giản chứa plaintext password giống một query string.

### Bài 5 — Authentication khác authorization

HBA/role authentication quyết định người dùng có được vào session không. Sau đó:

- `CONNECT` trên database có thể cần được kiểm tra.
- `USAGE` schema, `SELECT` table/column, quyền function và RLS kiểm soát SQL.
- Một role kết nối thành công vẫn có thể không đọc được bảng.

Sửa lỗi bằng grant đúng scope/role hoặc policies, không cấp superuser chỉ để chạy SELECT.

### Bài 6 — I, T, E

- `I`: idle, không trong explicit transaction block.
- `T`: đang trong transaction hợp lệ.
- `E`: đang ở failed transaction block, cần `ROLLBACK` hoặc thao tác phục hồi qua savepoint phù hợp.

Nếu một lệnh lỗi trong BEGIN block, câu SQL thông thường sau đó có thể báo “current transaction is aborted”; phải xử lý transaction state trước.

### Bài 7 — Simple query messages

Client gửi `Query("SELECT ...")`; server có thể phản hồi `RowDescription`, nhiều `DataRow`, `CommandComplete` và `ReadyForQuery`. Nếu lỗi, `ErrorResponse` thay/chen vào luồng kết quả phù hợp.

Giao thức vẫn dùng binary-framed messages, không chỉ gửi dòng SQL text qua TCP rồi đợi một dòng JSON.

### Bài 8 — Extended query

Một trình tự đơn giản: **Parse → Bind → [Describe] → Execute → Sync**. Parse xác định prepared statement và SQL structure, Bind truyền parameter values và tạo portal, Execute chạy, Sync kết thúc chu kỳ theo protocol rules.

Parameter binding tách dữ liệu khỏi SQL syntax; nó giảm nguy cơ injection do input bị ghép thành code.

### Bài 9 — Parameter không thay identifier

Không dùng `FROM $1` để bind tên bảng. Parameters biểu diễn **values**, không phải table/column/schema names.

Nếu phải chọn table động:

- Xác thực identifier nằm trong allowlist.
- Với PL/pgSQL dynamic SQL dùng `format('%I', identifier)` để quote tên đối tượng.
- Dùng `EXECUTE ... USING` cho values.
- Trong Java, chọn giữa các SQL statements fixed từ danh sách được phép thay vì nối raw input.

### Bài 10 — URI đúng

~~~text
postgresql://reporter@db.example.internal:5433/analytics?sslmode=verify-full&application_name=nightly-report
~~~

Không có password trong URL. Client vẫn cần authentication phù hợp qua passfile/secret provider hoặc phương pháp khác. TLS verify-full cần CA và endpoint certificate tương ứng.

### Bài 11 — Escape password giả

`p@ss/word#1` → `p%40ss%2Fword%231`.

Dạng cấu trúc:

~~~text
postgresql://demo:p%40ss%2Fword%231@db.internal.example:5432/shopdb
~~~

Ví dụ chỉ nhằm minh họa parsing, **không phải khuyến nghị đưa secret vào URI**. URI percent-encoding có thể đảo ngược dễ dàng và không mã hóa bí mật.

### Bài 12 — Double-encoding

`%40` → `%2540`. Client decode một lần thành literal `%40` chứ không phải ký tự `@`. Nếu password thực sự có @, authentication có thể thất bại do input sai.

### Bài 13 — connect_timeout và CA

~~~text
postgresql://reporter@db.example.internal:5433/analytics?sslmode=verify-full&application_name=nightly-report&connect_timeout=5&sslrootcert=%2Fetc%2Fpostgresql%2Fca.pem
~~~

`%2F` mã hóa slash của file path. File CA phải tồn tại **phía client**. Không đưa password vào URI để tiện vận hành.

### Bài 14 — IPv6

~~~text
postgresql://app@[2001:db8::5]:5432/shopdb
~~~

Bracket `[ ]` bọc IPv6 literal để dấu `:` trong IP không bị nhầm với separator host/port. Địa chỉ này chỉ dùng làm ví dụ.

### Bài 15 — key=value

~~~text
host=db.example.internal port=5433 dbname=analytics user=reporter sslmode=verify-full application_name=nightly-report
~~~

Nếu tên ứng dụng có dấu cách:

~~~text
application_name='nightly report'
~~~

Libpq key=value có quy tắc quoting/escaping riêng; không áp URI percent-encoding máy móc.

### Bài 16 — Service profile

Ví dụ:

~~~ini
[shop_readonly]
host=db-read.internal.example
port=5432
dbname=shopdb
user=app_reader
sslmode=verify-full
sslrootcert=/etc/postgresql/ca.pem
~~~

Kết nối:

~~~bash
psql "service=shop_readonly"
~~~

Không nhúng password vào profile chung nếu có passfile/secret store an toàn hơn. Service file là config, không thay cơ chế credential storage và TLS identity validation.

### Bài 17 — JDBC URL

~~~text
jdbc:postgresql://db.example.internal:5433/analytics?sslmode=verify-full&ApplicationName=nightly-report
~~~

Nó **không** giống libpq URI về scheme; JDBC dùng prefix `jdbc:postgresql://`. Các property names/units và các extension features phải kiểm tra theo pgJDBC version.

### Bài 18 — PreparedStatement

~~~java
String sql =
    "SELECT customer_id, customer_name " +
    "FROM app.customers WHERE customer_id=?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, customerId);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getString("customer_name"));
        }
    }
}
~~~

`?` của PreparedStatement là SQL bind placeholder; `?` của URL là dấu bắt đầu danh sách connection query parameters. Không dùng raw string concatenation cho customerId khi đã có bind API.

### Bài 19 — Timeouts

| Cấu hình | Phạm vi |
|---|---|
| `connect_timeout` libpq | Chờ mở kết nối, theo semantics libpq |
| `connectionTimeout` HikariCP | Chờ checkout connection từ pool, thường milliseconds |
| `statement_timeout` PostgreSQL | Server hủy statement vượt thời gian giới hạn |
| `socketTimeout` pgJDBC | I/O/socket read waiting theo driver semantics |

Nếu DB đã có 12 connections bận, HikariCP checkout timeout có thể xảy ra dù endpoint TCP vẫn reachable. Nếu query quá lâu, statement_timeout mới là một trong những biện pháp cắt statement.

### Bài 20 — TLS require/verify-ca/verify-full

- `require`: bắt buộc TLS nhưng không diễn đạt rõ việc xác minh đúng hostname.
- `verify-ca`: xác minh CA chain.
- `verify-full`: xác minh CA và hostname endpoint.

Khi cần chống kết nối nhầm server trên mạng không tin cậy và có PKI phù hợp, dùng `verify-full` cùng root CA đúng.

### Bài 21 — Certificate host mismatch

Certificate chỉ chứng thực `db.example.internal`, nhưng kết nối IP `10.0.0.8` được kiểm tra theo tên/IP endpoint. Nếu certificate không có IP identity phù hợp, verify-full có thể từ chối. Không nên hạ xuống `sslmode=disable`; dùng DNS name hợp lệ hoặc cấp certificate đúng.

### Bài 22 — SCRAM và TLS

SCRAM chứng minh client biết credential theo auth method; TLS bảo vệ traffic và xác thực server certificate nếu cấu hình verification đúng. Chỉ dùng SCRAM trên đường truyền không được bảo vệ có thể không đáp ứng yêu cầu bảo mật dữ liệu SQL/response và server identity. Thiết kế thường dùng cả hai khi remote connections qua network cần bảo vệ.

### Bài 23 — HBA hostssl

~~~text
hostssl  shopdb  app_reader  10.20.0.0/16  scram-sha-256
~~~

Ví dụ chỉ cho kết nối PostgreSQL TCP SSL/TLS từ phạm vi IP được ghi đến role/db tương ứng theo HBA; còn cần server TLS configuration và rules liên quan khác. Không copy range mẫu vào firewall production mà không xác định network thực.

### Bài 24 — First-match

Không. Khi một HBA record phù hợp được chọn và xác thực thất bại, PostgreSQL không đơn giản thử các rules tiếp theo. Phải sửa credentials, auth method, role hoặc HBA rule order chính xác; không thêm một `trust` rule rộng ở cuối để hy vọng fallback.

---

## 50. Lời giải và giải thích — bài 25 đến 48

### Bài 25 — Query session identity

~~~sql
SELECT
    pg_backend_pid() AS backend_pid,
    current_database() AS database_name,
    current_user AS db_role,
    current_setting('application_name') AS app_name;
~~~

Backend PID là identity của process đang phục vụ phiên tại thời điểm query, không phải principal đã xác thực, không bền vững qua restart/reconnect/pool routing và có thể được tái sử dụng. Không dùng làm khóa dữ liệu nghiệp vụ.

### Bài 26 — Hai sessions và PgBouncer

Mở hai psql sessions trực tiếp:

~~~sql
SELECT pg_backend_pid();
~~~

Thông thường nhận hai PIDs khác nhau. Với PgBouncer transaction pooling, cùng một client session có thể dùng backend A trong transaction 1 và backend B trong transaction 2. Khi muốn chẩn đoán, đo PID **trong mỗi transaction**, không suy từ một lần checkout.

### Bài 27 — SET vs SET LOCAL

~~~sql
SET TIME ZONE 'UTC';

BEGIN;
SELECT current_setting('TimeZone');
COMMIT;

SELECT current_setting('TimeZone');
~~~

Giá trị `UTC` có thể còn lại vì SET session-level.

~~~sql
BEGIN;
SET LOCAL TIME ZONE 'Asia/Ho_Chi_Minh';
SELECT current_setting('TimeZone');
ROLLBACK;
SHOW TIME ZONE;
~~~

Sau ROLLBACK, `SET LOCAL` hết hiệu lực, session quay về giá trị trước transaction (ở ví dụ là UTC). Không chạy `SET LOCAL` mà không hiểu transaction scope.

### Bài 28 — Session state rò qua pool

Request B có thể dùng sai `search_path` và đọc/update nhầm schema của tenant A nếu quyền DB cho phép. Cần:

- Dùng explicit schema/tenant mapping được xác thực hoặc RLS đúng.
- Đặt context theo transaction bằng `SET LOCAL` khi phù hợp.
- Đảm bảo rollback/cleanup khi lỗi.
- Pool reset session state theo contract.
- Test luân phiên tenant A/B trên pool size=1.
- Không chỉ dựa vào app-level filter để chống dữ liệu cross-tenant.

### Bài 29 — Temp table

Nếu cùng backend session và temp table còn sống, lượt checkout sau **có thể thấy temp table**. Mẫu transaction-scoped:

~~~sql
BEGIN;

CREATE TEMP TABLE tmp_ids(
    id bigint PRIMARY KEY
) ON COMMIT DROP;

INSERT INTO tmp_ids(id) VALUES (1),(2);
SELECT * FROM tmp_ids;

COMMIT;
~~~

Sau COMMIT, bảng tạm được drop theo `ON COMMIT DROP`. Không dựa vào tên temp table để chia sẻ data giữa hai backends của transaction pool.

### Bài 30 — Advisory lock lifetime

- `pg_advisory_lock(key)`: session-level lock, có thể tồn tại sau COMMIT và được giải phóng bằng unlock/session end.
- `pg_advisory_xact_lock(key)`: transaction-level lock, được giải phóng khi transaction kết thúc.

Session lock rò qua pool có thể làm các requests kế tiếp giữ lock không mong muốn hoặc chờ lâu. Khi lock chỉ phục vụ transaction, ưu tiên transaction-level nếu phù hợp.

### Bài 31 — LISTEN và backend affinity

`LISTEN order_events` là registration thuộc một backend session. Transaction pool có thể cấp backend khác sau COMMIT; listener không được bảo đảm tiếp tục có registration trên backend đang dùng để nhận notifications. Dùng dedicated session connection hoặc phương án messaging/outbox tùy mục tiêu.

### Bài 32 — Connection budget

10 × 20 + 10 = **210 connections tiềm năng**. Đây là số connection slots có thể được yêu cầu, không phải throughput guarantee. DB còn giới hạn CPU/I/O/locks, nhiều queries chậm có thể giảm throughput dù pool có đủ slots.

### Bài 33 — Leak do thiếu close

Khi một code path không trả Connection, `active/in-use` trong pool tăng dần, requests mới chờ checkout, có thể bị timeout dù server còn sống.

Mẫu đúng:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(
         "SELECT current_database()");
     ResultSet rs = ps.executeQuery()) {

    if (rs.next()) {
        System.out.println(rs.getString(1));
    }
}
~~~

Try-with-resources đóng ResultSet, PreparedStatement và logical Connection khi thoát block, kể cả khi exception xảy ra.

### Bài 34 — Idle in transaction

Một transaction idle vẫn có thể giữ locks và snapshot, hạn chế cleanup của MVCC/VACUUM. Quan sát:

~~~sql
SELECT
    pid,usename,application_name,state,
    xact_start,
    clock_timestamp()-xact_start AS age
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start
LIMIT 10;
~~~

Khi điều tra, đừng terminate backend chỉ vì nó đứng đầu danh sách; cần xác định business transaction hợp lệ, wait events và quyền thao tác.

### Bài 35 — Failed transaction

Sau `SELECT 1/0` trong `BEGIN`, transaction có thể ở failed state. `SELECT 42` thường bị từ chối với thông báo dạng “current transaction is aborted”. Cần `ROLLBACK` hoặc rollback tới savepoint phù hợp nếu có, rồi mới tiếp tục SQL nghiệp vụ.

### Bài 36 — Savepoint

Một mẫu thao tác gồm các lệnh chạy **tách theo phản hồi lỗi**:

~~~sql
BEGIN;
SAVEPOINT before_optional;
-- Chạy SQL có thể lỗi.
-- Khi thấy lỗi, không tiếp tục SELECT tùy ý:
ROLLBACK TO SAVEPOINT before_optional;
SELECT 42;
COMMIT;
~~~

Đây là pseudo-sequence để hướng dẫn caller. Nếu connection đã chết, không có backend session đáng tin để `ROLLBACK TO SAVEPOINT`. Serialization/deadlock failures thường cần transaction retry logic ở application, không coi savepoint là phép chữa chung.

### Bài 37 — Ba pooling modes

- **Session pooling:** backend gắn với client session, hợp hơn với state như temp tables, LISTEN, session advisory locks và server-side prepared statements.
- **Transaction pooling:** backend được giữ trong một transaction rồi trả pool, phù hợp SQL stateless/transaction-local state.
- **Statement pooling:** backend được gán theo statement, hạn chế multi-statement transaction patterns.

Không có mode tốt nhất cho mọi workload; lựa chọn theo app's reliance on session state, DB connection capacity và proxy/driver support.

### Bài 38 — Prepared statements qua PgBouncer

Kiểm tra:

1. PgBouncer pooling mode và version.
2. PgBouncer `max_prepared_statements`/tracking capability nếu phiên bản hỗ trợ.
3. pgJDBC version và server-side prepare threshold/caching.
4. SQL-level PREPARE so với protocol-level named statements.
5. Lỗi xuất hiện sau đổi backend PID hoặc pool checkout nào.
6. Khả năng chuyển sang session pooling cho workload yêu cầu.

**Không chuyển sang SQL concatenation**; vẫn dùng JDBC PreparedStatement parameter binding để chống injection, dù thay đổi server-side prepare reuse.

### Bài 39 — Group connection counts

~~~sql
SELECT
    application_name,
    state,
    COUNT(*) AS connection_count
FROM pg_stat_activity
WHERE backend_type='client backend'
GROUP BY application_name,state
ORDER BY connection_count DESC,application_name,state;
~~~

Một pool chủ động giữ idle backends có thể là bình thường. Leak thường thể hiện ở **checkout không được release**, pool active/in-use quá cao và pending queue tăng; cần so pool metrics với DB metadata.

### Bài 40 — Kiểm tra pg_stat_ssl

~~~sql
SELECT
    s.ssl,
    s.version AS tls_version,
    s.cipher
FROM pg_stat_ssl AS s
WHERE s.pid=pg_backend_pid();
~~~

`ssl=true` cho biết PostgreSQL backend thấy TLS trên chặng kết nối đó. Nó **không chứng minh** client đã verify-full certificate/hostname, cũng không mô tả đầy đủ đường client→proxy→backend.

### Bài 41 — localhost trong container

Trong app container, `localhost` chỉ network namespace của chính app container. PostgreSQL ở container khác nên hostname nên là **service name**/DNS name trong network được quản trị (ví dụ `postgres-db` nếu Docker Compose đặt tên service như vậy).

Còn cần PostgreSQL listener/HBA/firewall và certificate hostname phù hợp. Không tự mở DB cho toàn Internet để chữa lỗi Docker networking.

### Bài 42 — Multi-host URI

~~~text
postgresql://app@pg-a.internal.example:5432,pg-b.internal.example:5432/shopdb?target_session_attrs=read-write&connect_timeout=5
~~~

Đây là cấu hình **libpq URI** minh họa, không nhất thiết là cùng cú pháp failover của pgJDBC. Nó giúp thử endpoint đáp ứng thuộc tính read-write theo libpq rules, nhưng **không tự tạo replication, election, fencing hoặc split-brain protection**.

### Bài 43 — Replica lag

Asynchronous replication có thể làm replica chưa thấy row vừa commit trên primary. Hai hướng:

1. Đọc những dữ liệu cần read-your-writes từ primary hoặc session/routing strategy đảm bảo consistency.
2. Nếu phải dùng replica, đợi replay tới vị trí WAL/consistency token thích hợp theo cơ chế có kiểm soát, hoặc chấp nhận eventual consistency trong API contract.

Không chỉ tăng client timeout và suy replica sẽ lập tức đồng bộ.

### Bài 44 — Unknown COMMIT

Không được tự giả định rollback. Client mất response có thể xảy ra **sau khi server đã commit** hoặc trước lúc commit. Mẫu:

- Mỗi payment có idempotency key do API cấp.
- Database enforce UNIQUE idempotency key và check payload consistency.
- Khi reconnect, truy vấn theo business/idempotency key để đối chiếu.
- Transactional outbox gắn với commit DB cho side effects.
- Retry có giới hạn/backoff; không tạo bản sao payment khi chưa xác nhận outcome.

### Bài 45 — Cancel và terminate

- **Cancel query:** yêu cầu hủy statement đang thực thi, connection có thể vẫn tồn tại.
- **Terminate backend:** chấm dứt session/backend, làm mất connection và transaction chưa hoàn tất.
- **statement_timeout:** server giới hạn thời gian thực thi statement.
- **lock_timeout:** giới hạn thời gian chờ lock.

Terminate backend tùy tiện có thể rollback nghiệp vụ quan trọng hoặc gây tải reconnect hàng loạt. Điều tra owner/application/query/waits và dùng runbook với quyền thích hợp trước khi can thiệp.

### Bài 46 — Phân lớp năm lỗi

| Lỗi | Lớp | Điều tra |
|---|---|---|
| DNS lookup failed | Name resolution | DNS hostname/resolver/private zone |
| Certificate verify failed | TLS/PKI | CA file, hostname, expiry, proxy |
| Password authentication failed | Authentication | Role/password/SCRAM/HBA rule |
| Permission denied for table | SQL authorization | GRANT, schema, RLS, ownership |
| Pool acquisition timeout | Application pooling | Pool active/pending, checkout leaks, long transactions |

Không sửa lỗi HBA bằng cách tăng pool; không sửa certificate mismatch bằng cách grant quyền bảng.

### Bài 47 — Tenant context không đáng tin

Nếu HTTP client tự chọn `app.tenant_id` tùy ý, policy dựa vào `current_setting` có thể tin giá trị giả mạo. `SET LOCAL` chỉ thay **scope/lifetime của setting**, không xác minh ai có quyền chọn tenant.

Cần một trusted authenticated layer/role mapping, database permissions/RLS phù hợp và session/transaction context không bị client thao túng.

### Bài 48 — Runbook sau failover

Một runbook:

1. Ghi mốc thời gian failover, affected services, endpoint và phiên bản proxy/driver.
2. Khoanh vùng lỗi theo SQLSTATE/network errors, không gộp mọi failures.
3. Kiểm tra DNS, TCP, firewall, hostname/TLS certificate/CA đối với endpoint mới.
4. Kiểm tra PgBouncer client/server pool status và health của primary/replicas.
5. So pool HikariCP active/pending/idle, checkout timeout, connection churn và DB max_connections.
6. Kiểm tra pgJDBC prepared statement behavior, PgBouncer pooling mode/version/tracking.
7. Loại các broken connections và đảm bảo transaction rollback/session cleanup trước khi reuse.
8. Kiểm tra những operations có **unknown commit outcome** bằng idempotency keys, không retry INSERT vô điều kiện.
9. Kiểm tra read/write routing, `pg_is_in_recovery()` và replication lag.
10. Giới hạn retries/backoff để tránh reconnect storm.
11. Quan sát `pg_stat_activity`, `pg_stat_ssl`, wait events, logs và SQLSTATE sanitized.
12. Đối chiếu dữ liệu nghiệp vụ/outbox, sửa cấu hình, test failure injection trên staging.
13. Triển khai thay đổi theo canary và có rollback path được phê duyệt.
14. Tách root causes: network failover, prepared statement session affinity, pool exhaustion và retry/idempotency có thể là **nhiều lỗi độc lập**.

Không vô hiệu hóa TLS hoặc cấp superuser để làm connection “thành công” trước khi có root-cause analysis.

---

## 51. Thực hành bổ sung: một kịch bản kiểm tra session bằng hai kết nối

Đây là lab nhỏ không yêu cầu quyền tạo bảng. Mở hai cửa sổ `psql` vào cùng database, nếu có thể là kết nối trực tiếp để quan sát backend state rõ.

### 51.1. Session A

~~~sql
SELECT pg_backend_pid() AS pid_a;
SET application_name='lesson-session-A';
SET TIME ZONE 'UTC';

BEGIN;
SET LOCAL statement_timeout='3s';
SELECT current_setting('TimeZone') AS timezone_a,
       current_setting('statement_timeout') AS timeout_a;
COMMIT;

SELECT current_setting('TimeZone') AS timezone_after,
       current_setting('statement_timeout') AS timeout_after;
~~~

Timezone session-level vẫn có thể là UTC, còn statement_timeout local trở về giá trị trước transaction.

### 51.2. Session B

~~~sql
SELECT pg_backend_pid() AS pid_b,
       current_setting('application_name') AS app_b,
       current_setting('TimeZone') AS timezone_b;
~~~

Session B không tự nhận SET của A khi hai connections thực sự trỏ hai backend sessions riêng. Nếu dùng PgBouncer transaction pooling, cần giải thích sự khác biệt về session mapping.

### 51.3. Quan sát pg_stat_activity

~~~sql
SELECT
    pid,
    application_name,
    state,
    backend_start,
    xact_start
FROM pg_stat_activity
WHERE datname=current_database()
ORDER BY backend_start DESC
LIMIT 20;
~~~

Bạn có thể thấy sessions A/B nếu role có quyền xem metadata tương ứng. Không dùng query này để kết luận mọi clients đều hiện đầy đủ khi quyền giám sát bị giới hạn.

### 51.4. Làm sạch lab state

~~~sql
RESET application_name;
RESET TIME ZONE;
RESET statement_timeout;
~~~

Nếu muốn phiên sạch hoàn toàn, đóng connection và mở session mới; không coi `RESET ALL` tương đương xóa tất cả temp objects/locks/prepared statements.

---

## 52. Tài liệu chính thức và cách tra theo phiên bản

Khi cấu hình production, ưu tiên tài liệu **đúng major version của client và server**, nhất là TLS/proxy pooling:

- [PostgreSQL — Frontend/Backend Protocol](https://www.postgresql.org/docs/current/protocol.html): cấu trúc tổng quan wire protocol.
- [PostgreSQL — Protocol Flow](https://www.postgresql.org/docs/current/protocol-flow.html): startup, authentication, simple và extended query.
- [PostgreSQL — Message Formats](https://www.postgresql.org/docs/current/protocol-message-formats.html): loại thông điệp, các fields và ReadyForQuery.
- [PostgreSQL — libpq Connection Strings](https://www.postgresql.org/docs/current/libpq-connect.html): URI/key=value, host list, target_session_attrs.
- [PostgreSQL — libpq Environment Variables](https://www.postgresql.org/docs/current/libpq-envars.html): PGHOST, PGUSER, PGSERVICE và các biến khác.
- [PostgreSQL — libpq Password File](https://www.postgresql.org/docs/current/libpq-pgpass.html): cấu trúc/permissions của passfile.
- [PostgreSQL — libpq Service Files](https://www.postgresql.org/docs/current/libpq-pgservice.html): profile kết nối có tên.
- [PostgreSQL — SSL/TLS Support](https://www.postgresql.org/docs/current/ssl-tcp.html): cấu hình TLS phía server/client.
- [PostgreSQL — Client Authentication](https://www.postgresql.org/docs/current/client-authentication.html): pg_hba.conf và auth methods.
- [PostgreSQL — pg_stat_activity](https://www.postgresql.org/docs/current/monitoring-stats.html): session state, wait events, statistics.
- [PostgreSQL — Run-time Configuration](https://www.postgresql.org/docs/current/runtime-config.html): timeouts, connection limits, logging và session settings.
- [PostgreSQL — SET](https://www.postgresql.org/docs/current/sql-set.html): session và transaction-local configuration.
- [PostgreSQL — DISCARD](https://www.postgresql.org/docs/current/sql-discard.html): dọn session state.
- [PostgreSQL — LISTEN](https://www.postgresql.org/docs/current/sql-listen.html): session notification behavior.
- [PostgreSQL — Advisory Locks](https://www.postgresql.org/docs/current/explicit-locking.html): session-level và transaction-level advisory locks.
- [PostgreSQL JDBC Driver — Documentation](https://jdbc.postgresql.org/documentation/): pgJDBC URL, connection properties, prepared statements và TLS.
- [HikariCP — Project Documentation](https://github.com/brettwooldridge/HikariCP): pool lifecycle và configuration.
- [PgBouncer — Documentation](https://www.pgbouncer.org/config.html): pool_mode, prepared statements, authentication, TLS/proxy config.

Các URL `/current/` trỏ PostgreSQL docs mới nhất, không bảo đảm giống server đang chạy. Khi nói về protocol extension, libpq attributes, TLS negotiation, `pgJDBC` và `PgBouncer`, phải kiểm tra **versions của từng thành phần**, không chỉ server.

---

## 53. Tổng kết

**Giao thức kết nối PostgreSQL có trạng thái, còn URI chỉ là một cách mô tả cách client tìm và thiết lập phiên.** Muốn ứng dụng vận hành an toàn, cần phân biệt đầy đủ các lớp:

1. **Network endpoint**: DNS, TCP port, Unix socket, firewall, proxy routing.
2. **Transport security**: TLS, root CA và hostname verification (thường `sslmode=verify-full` khi sử dụng libpq và PKI phù hợp).
3. **PostgreSQL startup/auth**: StartupMessage, HBA, SCRAM/peer/cert, ParameterStatus và ReadyForQuery.
4. **Wire protocol**: Simple Query hoặc Extended Query với Parse/Bind/Execute/Sync; ứng dụng nên dùng parameterized queries để tách data khỏi SQL.
5. **Connection string**: libpq URI, libpq key=value và pgJDBC URL **không hoàn toàn tương đương**; các ký tự đặc biệt trong URI phải percent-encode đúng, credentials cần lưu ngoài URL.
6. **Session**: có backend state sống qua nhiều transactions, bao gồm session SET, temporary objects, LISTEN, advisory locks và prepared statements.
7. **Transaction**: đơn vị atomicity/isolation; COMMIT/ROLLBACK giải phóng tài nguyên transaction, nhưng không nhất thiết đóng session hoặc reset mọi state.
8. **Connection pool**: logical `close()` có thể chỉ trả connection về pool. Pool cần reset session state, không trả backend đang ở failed transaction và giới hạn tổng connections hợp lý.
9. **PgBouncer**: session pooling giữ affinity phù hợp hơn với session features; transaction pooling có thể đổi backend giữa transactions, cần kiểm tra prepared statement support theo version.
10. **TLS và auth không thay quyền**: kết nối thành công không chứng minh role có SELECT/UPDATE đối tượng hoặc tenant isolation đúng.
11. **Timeout theo từng tầng**: connect, pool checkout, SQL statement, lock và socket/read timeout không dùng thay nhau.
12. **Quan sát**: `pg_stat_activity`, `pg_stat_ssl`, `pg_backend_pid()`, `application_name` và SQLSTATE giúp định vị lỗi đúng tầng.
13. **Failover và retry**: multi-host URI giúp lựa chọn endpoint nhưng không tạo HA; mất kết nối lúc COMMIT có thể để lại transaction outcome unknown, cần idempotency/reconciliation.
14. **Bảo mật dài hạn**: secret management, certificate rotation, least-privilege roles, session hygiene, proper RLS và kiểm thử staging là các yêu cầu vận hành chứ không chỉ thiết lập ban đầu.

Quy trình nên ghi nhớ: **đọc URI và driver config → xác minh DNS/TCP/socket → bắt tay TLS và authentication → xác định session/backend identity → thực thi SQL có bind parameters và transaction boundaries → trả connection đúng pool contract → quan sát timeout/locks/state → xử lý failover/retry theo idempotency và dữ liệu nghiệp vụ**.
