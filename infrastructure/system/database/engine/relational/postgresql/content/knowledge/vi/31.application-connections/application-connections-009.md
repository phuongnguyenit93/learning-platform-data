# Timeout kết nối, truy vấn, mạng và hủy câu lệnh trong PostgreSQL

## 1. Vì sao “database timeout” không phải một cấu hình duy nhất?

Một API Java gọi PostgreSQL để lấy danh sách đơn hàng. Bình thường truy vấn mất 80 ms, nhưng hôm nay request treo 30 giây rồi trả HTTP 504. Người vận hành hỏi:

- Ứng dụng có **không lấy được connection từ pool**?
- DNS, TCP, TLS hoặc PostgreSQL authentication có bị chậm?
- Connection đã có nhưng câu SQL đang chờ row lock?
- SQL đang quét hàng triệu rows và bị chặn bởi `statement_timeout`?
- Server xử lý xong nhưng client đang mất kết nối hoặc không nhận được response?
- Người dùng đóng trình duyệt thì query trong PostgreSQL đã được **hủy** chưa?
- Driver báo timeout thì `COMMIT` trước đó có chắc chắn thất bại không?

Mỗi câu hỏi liên quan đến **một đồng hồ đo thời gian và một cơ chế xử lý lỗi khác nhau**.

```text
HTTP request / background job
        |
        v
[1] Chờ connection từ pool       -> pool connectionTimeout
        |
        v
[2] Tạo physical connection      -> loginTimeout / connectTimeout
    DNS -> TCP -> TLS -> auth        + network/proxy budgets
        |
        v
[3] Gửi SQL / chờ kết quả        -> statement_timeout (server)
    + chờ lock                   -> lock_timeout (server)
    + JDBC queryTimeout          -> Statement.setQueryTimeout
    + đọc socket                  -> socketTimeout / networkTimeout
        |
        v
[4] Nhận rows, xử lý, COMMIT     -> transaction budget / request deadline
        |
        v
[5] Trả response / trả pool      -> HTTP deadline, connection cleanup

Ngoài request:
- idle_in_transaction_session_timeout: session bỏ không trong transaction
- idle_session_timeout: session rảnh ngoài transaction
- transaction_timeout (PG 17+): giới hạn đời sống transaction
- pg_cancel_backend / Statement.cancel: yêu cầu hủy câu SQL hiện tại
- pg_terminate_backend: chấm dứt backend/session
```

**Thông điệp chính:** cấu hình timeout theo từng lớp để có thời hạn xử lý dễ dự đoán; phân biệt **hủy statement** với **đóng connection**; và không tự động retry thao tác ghi khi chưa biết transaction đã commit hay chưa.

## 2. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt pool checkout timeout, connection establishment timeout, query timeout, socket/read timeout và request deadline.
2. Biết vai trò của pgJDBC `connectTimeout`, `loginTimeout`, `socketTimeout`, `cancelSignalTimeout` và `tcpKeepAlive`.
3. Biết `HikariCP connectionTimeout` không phải PostgreSQL `statement_timeout`.
4. Dùng `Statement.setQueryTimeout(int seconds)` và `Statement.cancel()` trong JDBC.
5. Đặt PostgreSQL `statement_timeout` và `lock_timeout` theo role, session hoặc transaction.
6. Hiểu `idle_in_transaction_session_timeout`, `idle_session_timeout` và `transaction_timeout` (PostgreSQL 17+).
7. Hiểu `SET LOCAL`, `SET`, `ALTER ROLE ... SET` và ảnh hưởng đến connection pool.
8. Thực hành một truy vấn bị hủy bằng `pg_sleep`.
9. Thực hành chờ row lock và lỗi `lock_timeout` bằng hai sessions.
10. Hiểu cơ chế cancel request riêng, sự khác nhau với `pg_terminate_backend`.
11. Phân biệt kết quả server-side `SQLSTATE 57014` với network failure/connection error.
12. Biết transaction trong trạng thái **aborted** sau lỗi statement và cách `ROLLBACK` đúng.
13. Nhận biết kết quả ghi **không chắc chắn** khi client mất kết nối gần thời điểm COMMIT.
14. Thiết kế retry theo idempotency key, SQLSTATE, deadline và backoff.
15. Dùng `pg_stat_activity`, `pg_blocking_pids` và `pg_locks` để điều tra truy vấn đang chờ.
16. Cấu hình pool/JDBC timeout hợp lý cho HTTP API và background jobs.
17. Tránh giữ transaction mở trong khi chờ mạng hoặc thao tác người dùng.
18. Phân biệt TCP keepalive, pool keepalive và query timeout.
19. Hiểu ảnh hưởng của proxy/load balancer/PgBouncer đối với timeout.
20. Kiểm thử các tình huống cancel, lock timeout, backend termination, socket failure và recovery.

## 3. Bản đồ các loại timeout

| Lớp | Cơ chế ví dụ | Đo thời gian nào? | Kết quả thường gặp |
| --- | --- | --- | --- |
| HTTP/gRPC | Request deadline | Tổng thời gian request | Client nhận timeout; SQL **chưa chắc** đã dừng |
| Connection pool | HikariCP `connectionTimeout` | Chờ lấy connection từ pool | Ứng dụng không lấy được connection |
| Driver | pgJDBC `connectTimeout` | Chờ socket connect | Kết nối vật lý không lập được |
| Driver | pgJDBC `loginTimeout` | Thiết lập connection/login theo driver | Establishment thất bại quá hạn |
| Driver | pgJDBC `socketTimeout` | Một socket **read** chờ dữ liệu quá lâu | Read timeout; connection có thể hỏng |
| JDBC | `Statement.setQueryTimeout` | Thời gian thực hiện statement do driver quản lý | Driver yêu cầu cancel; SQLException |
| JDBC | `Statement.cancel` | Chủ động yêu cầu hủy statement | Câu SQL có thể bị hủy |
| PostgreSQL | `statement_timeout` | Thực thi statement ở server | Lỗi query canceled |
| PostgreSQL | `lock_timeout` | Chờ lấy từng lock | Lỗi lock acquisition |
| PostgreSQL | `idle_in_transaction_session_timeout` | Session idle khi transaction còn mở | Backend/session bị chấm dứt |
| PostgreSQL | `idle_session_timeout` | Session idle ngoài transaction | Backend/session bị chấm dứt |
| PostgreSQL 17+ | `transaction_timeout` | Thời gian tồn tại transaction | Backend/session bị chấm dứt khi quá hạn |
| Network/OS | TCP keepalive, proxy idle timeout | Sự sống của kết nối TCP hoặc độ rảnh | Connection drop/detection; không phải SQL deadline |

Mỗi timeout có **scope, đơn vị, điểm bắt đầu và hậu quả** riêng. Không nên sao chép một con số `5000` vào mọi setting và giả định đó là 5 giây.

### 3.1. Một request có thể đi qua nhiều ngưỡng

Ví dụ, một web request có deadline 8 giây, pool checkout có giới hạn 1 giây, SQL có server-side timeout 5 giây và socket read timeout 12 giây. Cấu hình này chỉ có ý nghĩa khi ứng dụng **truyền và thực thi deadline** qua các bước; không thể chỉ cộng/trừ số liệu mà bỏ qua cancellation hoặc thời gian ngoài SQL.

### 3.2. Timeout không phải lời hứa xử lý chính xác đến mili-giây

Một timeout có thể được kiểm tra theo event loop, tín hiệu, chu kỳ interrupt, scheduler hoặc network I/O. Khi hệ thống quá tải, thời điểm callback/lỗi xuất hiện có thể muộn hơn ngưỡng đặt ra.

### 3.3. Timeout có thể cùng xảy ra

Một query vừa đang chờ lock vừa vượt `statement_timeout`, trong khi HTTP client đã đóng kết nối. Lỗi nào hiện ra trước phụ thuộc thời điểm và cơ chế tương ứng. Điều tra phải xét **đồng hồ nào thực sự hết hạn**.

## 4. Phân biệt “chờ pool” và “kết nối PostgreSQL”

Tưởng tượng HikariCP có 10 physical connections, cả 10 đều đang được sử dụng. Request thứ 11 gọi:

```java
Connection conn = dataSource.getConnection();
```

Nó có thể phải chờ một connection được trả về pool, dù PostgreSQL và mạng vẫn khỏe.

### 4.1. HikariCP `connectionTimeout`

Đây là thời gian tối đa client chờ **lấy connection từ pool**. Nếu quá giới hạn, `getConnection()` có thể ném SQLException.

Điều này **không đồng nghĩa** PostgreSQL đã chạy query quá lâu, hoặc PostgreSQL `statement_timeout` đã xảy ra.

### 4.2. Nguyên nhân pool exhaustion

- Connection leak: không close/return.
- Transaction giữ connection quá lâu.
- Query chậm/lock waits.
- Pool quá nhỏ so với concurrency hợp lý.
- Downstream network khiến một số connection bị giữ.
- Background job dùng chung pool với HTTP traffic.
- Kết nối vật lý được tạo quá chậm hoặc backend limit đã đạt.

### 4.3. Không chỉ tăng `maximumPoolSize`

Tăng pool không giới hạn có thể tạo thêm backend processes, memory, context switching và contention ở PostgreSQL. Cần kiểm tra truy vấn/transaction bị giữ trước khi tăng số connections.

### 4.4. Một tình huống khác: pool có slot nhưng server không nhận connection mới

Khi cần tạo physical connection, PostgreSQL có thể từ chối vì `max_connections`, sai credentials, TLS, network hoặc authentication. Khi đó driver `connectTimeout`/`loginTimeout` và server errors mới đáng quan tâm.

## 5. Driver connect timeout và login timeout

pgJDBC có nhiều connection properties. Các tên dưới đây thuộc **PostgreSQL JDBC Driver**, không phải mọi JDBC driver đều có cùng property.

### 5.1. `connectTimeout`

Điều khiển thời gian chờ thao tác **socket connect** khi thiết lập kết nối tới PostgreSQL. Đơn vị cấu hình pgJDBC là **giây**.

```text
connectTimeout=3
```

Không nên suy rằng property này bao quát tuyệt đối thời gian DNS, TLS/auth, mọi host failover và retry của toàn ứng dụng.

### 5.2. `loginTimeout`

Giới hạn thời gian chờ thiết lập connection/login theo cơ chế driver. Nó khác với việc chỉ chờ TCP connect; cũng được cấu hình bằng **giây** trong pgJDBC.

### 5.3. Kết nối tới nhiều hosts

Với JDBC URL chứa nhiều PostgreSQL hosts, quá trình chọn host/failover có thể gồm nhiều bước connect. Tổng thời gian application thấy có thể lớn hơn timeout socket của một host. Đừng xây một SLO dựa trên giả định “connectTimeout 3s nghĩa mọi tình huống trả lỗi trước 3s”.

### 5.4. Kết nối thành công vẫn có thể có query timeout

Sau khi authentication xong, `connectTimeout` đã hoàn thành nhiệm vụ. Một `SELECT` chậm không được giới hạn chỉ bởi connectTimeout.

### 5.5. Ví dụ JDBC URL cho môi trường lab

```text
jdbc:postgresql://localhost:5432/appdb?connectTimeout=3&loginTimeout=5&socketTimeout=15&cancelSignalTimeout=5&tcpKeepAlive=true&ApplicationName=orders-api
```

Lưu ý:

- `appdb` và host cần thay bằng môi trường thực.
- `connectTimeout=3`, `loginTimeout=5`, `socketTimeout=15`, `cancelSignalTimeout=5` là **giây**.
- `tcpKeepAlive=true` là cơ chế TCP keepalive, không phải câu SQL timeout.
- `ApplicationName` hỗ trợ quan sát session.
- Các giá trị chỉ là **minh họa**, không phải cấu hình chuẩn cho mọi production.

## 6. `socketTimeout`: thời gian đợi network read, không phải server query deadline

pgJDBC `socketTimeout` đặt giới hạn thời gian chờ ở **socket read operation**, đơn vị giây.

Giả sử:

```text
socketTimeout=10
```

Nếu driver chờ server gửi dữ liệu trong một lần đọc quá thời gian đó, thao tác đọc có thể bị timeout.

### 6.1. Nó khác `statement_timeout`

- `statement_timeout` chạy ở **server** và hủy lệnh SQL khi đạt giới hạn.
- `socketTimeout` xảy ra ở **client/driver** nếu không nhận được dữ liệu qua socket theo cơ chế timeout.

Nếu `socketTimeout` xảy ra, không thể tự kết luận PostgreSQL đã rollback lệnh.

### 6.2. Nó không đo chính xác toàn bộ query duration

Một query trả dữ liệu thành nhiều đợt có thể liên tục có các socket reads thành công, trong khi tổng thời gian request vẫn dài hơn socketTimeout. Vì vậy socketTimeout **không thay** deadline bao trùm toàn statement/request.

### 6.3. Socket timeout có thể khiến connection không còn tin cậy

Nếu driver timeout khi đọc protocol response, trạng thái client/server protocol hoặc connection có thể không đồng bộ/không dùng lại được. Driver/pool có thể đóng hoặc đánh dấu connection broken.

**Không tự trả connection đó vào một cơ chế tái sử dụng tùy biến** chỉ vì `Connection.isClosed()` chưa phản ánh ngay mọi lỗi.

### 6.4. Đặt socketTimeout quá nhỏ là phản tác dụng

Một lệnh SQL được phép chạy 8 giây mà socketTimeout chỉ 2 giây có thể khiến client bỏ connection trước khi server-side statement timeout/cancel xử lý sạch sẽ. Thường cần giới hạn mạng đủ có khoảng đệm cho server timeout và cancellation.

### 6.5. Connection.setNetworkTimeout

JDBC cung cấp `Connection.setNetworkTimeout(Executor, milliseconds)`, tùy driver hỗ trợ. Đây là cơ chế giới hạn network operations ở connection, không phải cùng một thứ với `Statement.setQueryTimeout`. Nếu vượt hạn, driver có thể đóng connection; cần xem semantics và khả năng hỗ trợ của driver/phiên bản thực tế.

Không tự coi `networkTimeout` là một `statement_timeout` mới hay bảo đảm transaction rollback.

## 7. JDBC query timeout: `Statement.setQueryTimeout`

Ví dụ:

```java
String sql = """
    SELECT order_id, status, amount
    FROM orders
    WHERE tenant_id = ?
    ORDER BY order_id
    LIMIT 100
    """;

try (PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setInt(1, tenantId);
    ps.setQueryTimeout(5); // giây theo JDBC API

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Xử lý các row trả về.
        }
    }
}
```

### 7.1. Giới hạn này ở đâu?

`setQueryTimeout` là JDBC API trên statement. Với pgJDBC, khi quá thời gian, driver có thể phát **cancel request** tới PostgreSQL để yêu cầu dừng câu SQL.

Thời điểm nhận SQLException có thể bị ảnh hưởng bởi scheduler/network/backend response. Không nên coi đây là đồng hồ cứng bảo đảm mọi code đã dừng đúng giây thứ 5.

### 7.2. Timeout ≠ PostgreSQL đã commit hoặc rollback chắc chắn

Nếu server gửi lỗi `query_canceled`, bạn biết statement đã bị hủy theo server response. Nếu client chỉ gặp lỗi mạng trong khi chờ, kết quả server-side có thể **không chắc chắn**, đặc biệt gần ranh giới `COMMIT`.

### 7.3. Query timeout khác thời gian xử lý kết quả ở application

Việc Java duyệt ResultSet, gọi downstream HTTP service hoặc serialize JSON có thể kéo dài request ngoài thời gian thực thi statement. Cần **request deadline** và giới hạn toàn workflow.

### 7.4. Không đặt setQueryTimeout bằng 0 rồi kỳ vọng tự dừng

Theo JDBC API, giá trị 0 thường chỉ **không giới hạn query timeout ở layer này**. Nếu PostgreSQL có `statement_timeout` thì nó vẫn có thể hủy query; hai lớp độc lập.

## 8. pgJDBC `cancelSignalTimeout` và cancel request

PostgreSQL có cơ chế **CancelRequest** riêng để yêu cầu backend đang chạy một statement hủy tác vụ. pgJDBC thường dùng một network connection riêng để gửi yêu cầu cancel.

`cancelSignalTimeout` giới hạn phần thời gian kết nối/gửi/chờ theo cơ chế cancel mà driver quản lý, **không phải thời gian thực thi toàn query**.

### 8.1. Vì sao cần một channel khác?

Connection chính có thể đang chờ response hoặc đang bận thực hiện query. Cancel request gửi qua kênh riêng với thông tin backend cần thiết, thay vì chèn một SQL command vào stream connection đang chờ.

### 8.2. Cancel là yêu cầu, không phải xác nhận ngay

Khi gửi thành công cancel request:

- Backend có thể đang thực thi statement và nhận yêu cầu.
- Backend có thể đã chạy xong trước khi cancel đến.
- Mạng có thể mất thông điệp hoặc kênh cancel có lỗi.
- Application có thể nhận lỗi do race khi statement đã hoàn tất.

**Không xem việc gọi `cancel()` là bằng chứng statement đã dừng**. Cần quan sát SQLException/result, trạng thái connection và hậu quả nghiệp vụ.

### 8.3. Secret của cancel protocol

Cancel request sử dụng thông tin backend để xác thực yêu cầu hủy theo protocol. Không công khai các thông tin nội bộ/protocol secrets trong logs hoặc API.

### 8.4. Timeout của cancel có thể khác timeout của query

Một query timeout 5 giây và `cancelSignalTimeout=5` không có nghĩa client sẽ luôn nhận lỗi chính xác sau 5 giây. Thời gian gửi và xử lý cancel có thể cần thêm thời gian.

## 9. PostgreSQL `statement_timeout`: server-side SQL deadline

PostgreSQL cung cấp GUC:

```sql
SHOW statement_timeout;
```

Giá trị `0` nghĩa là **không giới hạn** ở lớp này. Bạn có thể cấu hình time unit như milliseconds, seconds, minutes.

### 9.1. Cấu hình trong session lab

```sql
SET statement_timeout = '1500ms';

SELECT pg_sleep(3);

RESET statement_timeout;
```

Truy vấn `pg_sleep(3)` dự kiến bị server hủy sau khoảng 1,5 giây với lỗi tương tự:

```text
ERROR: canceling statement due to statement timeout
SQLSTATE: 57014
```

Khi chạy trong psql autocommit, statement lỗi không làm session tự mất kết nối; câu lệnh sau có thể chạy. Nếu đang ở explicit transaction, transaction có thể chuyển sang trạng thái aborted và cần `ROLLBACK`.

### 9.2. Nó bắt đầu khi nào?

`statement_timeout` áp dụng cho thời gian một statement được server xử lý theo protocol tương ứng, từ lúc server nhận request thích hợp đến lúc statement hoàn thành. Đây **không phải đồng hồ tổng** từ khi user bấm nút trong trình duyệt.

Với simple-query protocol và nhiều SQL statements trong một message, PostgreSQL hiện đại áp dụng timeout riêng theo từng statement theo semantics version tương ứng.

### 9.3. Nó có bao gồm chờ lock không?

**Có.** Một statement đứng chờ lock vẫn chưa hoàn thành; `statement_timeout` có thể hủy statement đó khi vượt giới hạn.

### 9.4. Nó có giới hạn transaction gồm nhiều statements không?

**Không theo nghĩa tổng thời gian giao dịch.** Mỗi statement có timeout riêng; một transaction với nhiều statements nhanh xen lẫn thời gian idle có thể sống rất lâu nếu không có các giới hạn khác.

### 9.5. Đặt rất thấp trên toàn server có rủi ro

Một `statement_timeout` áp rộng cho mọi workload có thể làm hỏng migrations, maintenance và report jobs dài hợp lệ. Ưu tiên cấu hình theo role/workload/session phù hợp.

## 10. Phạm vi cấu hình: `SET`, `SET LOCAL` và role defaults

### 10.1. Session-level

```sql
SET statement_timeout = '5s';

SHOW statement_timeout;

RESET statement_timeout;
```

Setting tồn tại trong session theo rules PostgreSQL; connection pool có thể dùng lại session giữa các request. Nếu quên `RESET`/cleanup, request sau có thể bị giới hạn không như kỳ vọng.

### 10.2. Transaction-level với `SET LOCAL`

```sql
BEGIN;

SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '1s';

SELECT COUNT(*)
FROM pg_catalog.pg_class;

COMMIT;
```

`SET LOCAL` có hiệu lực trong transaction hiện tại và được PostgreSQL khôi phục theo transaction/savepoint semantics.

Đây thường là lựa chọn tốt khi một thao tác cần timeout riêng mà không muốn để lại session state cho connection pool.

### 10.3. Khi statement timeout xảy ra trong transaction

Ví dụ:

```sql
BEGIN;

SET LOCAL statement_timeout = '1s';

SELECT pg_sleep(3);

-- Nếu ở đây vừa nhận lỗi, transaction đã aborted.
-- Hãy ROLLBACK trước khi chạy SQL tiếp.
ROLLBACK;
```

Nếu client dùng một batch script, dòng `ROLLBACK` có thể cần gửi sau khi xử lý lỗi từ statement trước, tùy công cụ.

### 10.4. Role defaults

Với role/database **thật sự tồn tại**, người quản trị có thể cấu hình:

```sql
ALTER ROLE app_runtime IN DATABASE appdb
SET statement_timeout = '5s';
```

Đây là ví dụ cú pháp, **không tự chạy** nếu chưa có role `app_runtime`/database `appdb` phù hợp.

Thay đổi mặc định như vậy áp dụng khi session mới được thiết lập theo PostgreSQL config precedence; **connections đã mở trong pool không tự đổi ngay**.

### 10.5. Phân biệt role defaults và SET LOCAL

- Role/database default: bảo đảm nền cho một nhóm workload và các session mới.
- `SET`: thay đổi session.
- `SET LOCAL`: thay đổi transaction hiện tại.
- `ALTER SYSTEM`/`postgresql.conf`: mức server, cần cân nhắc phạm vi rộng.

### 10.6. Cách xác minh

```sql
SHOW statement_timeout;
SHOW lock_timeout;
SHOW idle_in_transaction_session_timeout;
SHOW idle_session_timeout;

SELECT
    name,
    setting,
    unit,
    source
FROM pg_catalog.pg_settings
WHERE name IN (
    'statement_timeout',
    'lock_timeout',
    'idle_in_transaction_session_timeout',
    'idle_session_timeout'
)
ORDER BY name;
```

Cột `source` giúp tìm nguồn giá trị hiệu lực, không chỉ nhìn con số hiện tại.

## 11. `lock_timeout`: chỉ dành cho thời gian chờ khóa

`lock_timeout` giới hạn khoảng chờ mỗi lần một statement cần **lấy lock**.

```sql
SET lock_timeout = '1s';
```

Nếu một statement chờ lock lâu hơn, PostgreSQL có thể báo:

```text
ERROR: canceling statement due to lock timeout
SQLSTATE: 55P03
```

### 11.1. Khác `statement_timeout`

`statement_timeout` đo tổng thời gian statement server đang xử lý, **bao gồm** lock wait.

`lock_timeout` chỉ đo thời gian **chờ lock acquisition**, không giới hạn thời gian quét/aggregate nếu đã lấy được lock.

### 11.2. Khi cả hai cùng bật

```sql
SET statement_timeout = '5s';
SET lock_timeout = '1s';
```

Với một statement bị giữ ở lock 2 giây, `lock_timeout` dự kiến đến trước.

Nếu đặt `lock_timeout` bằng hoặc lớn hơn một `statement_timeout` khác đã áp dụng cho cùng statement, trong nhiều tình huống statement timeout sẽ đến trước, làm lock_timeout không còn hữu ích.

### 11.3. Lock timeout không phải deadlock detector

`deadlock_timeout` là setting liên quan đến thời gian trước khi PostgreSQL kiểm tra deadlock/log lock waits. Nó không phải “sau X giây sẽ hủy mọi lock wait” như `lock_timeout`.

Deadlock phát hiện có SQLSTATE `40P01`; lock timeout có SQLSTATE `55P03`. Cần phân loại riêng.

## 12. Lab hai sessions: tạo một row lock wait

Để minh họa lock timeout, tạo bảng trong database lab:

```sql
CREATE SCHEMA IF NOT EXISTS timeout402;

CREATE TABLE timeout402.jobs (
    job_id integer PRIMARY KEY,
    owner_id integer NOT NULL,
    status text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO timeout402.jobs (job_id, owner_id, status)
VALUES (1, 10, 'NEW'),
       (2, 20, 'NEW');
```

Mở **hai kết nối PostgreSQL riêng** tới cùng database.

### 12.1. Session A: giữ lock, chưa commit

```sql
BEGIN;

UPDATE timeout402.jobs
SET status = 'RUNNING',
    updated_at = clock_timestamp()
WHERE job_id = 1;

-- Giữ transaction mở để session B phải chờ.
-- Không COMMIT/ROLLBACK ngay ở bước này.
```

### 12.2. Session B: chờ row lock

```sql
BEGIN;

SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '1s';

UPDATE timeout402.jobs
SET status = 'CANCELLED'
WHERE job_id = 1;

-- Dự kiến lỗi lock_timeout SQLSTATE 55P03.
-- Sau lỗi, transaction đã aborted.
ROLLBACK;
```

Session B cần lock trên row mà A đang giữ; nếu A chưa kết thúc transaction, B có thể chờ rồi nhận lock timeout.

### 12.3. Session A: giải phóng lock

```sql
ROLLBACK;
```

Thao tác này trả `status` về `NEW` trong lab.

### 12.4. Những quan sát quan trọng

- `lock_timeout` giới hạn chờ lock, **không tự rollback transaction A**.
- Sau lỗi ở B, phải rollback transaction B.
- `ROLLBACK` A giải phóng lock cho các sessions khác.
- Nếu A đã COMMIT trước khi B hết hạn, B có thể tiếp tục, không có lỗi; đó là race bình thường.

### 12.5. Nếu chỉ SET statement_timeout?

B có thể chờ tối đa theo statement timeout và nhận lỗi `57014` thay vì `55P03`, tùy các giới hạn thực tế và thời điểm.

## 13. `idle_in_transaction_session_timeout`: bảo vệ khỏi transaction bỏ quên

Một connection có thể:

```sql
BEGIN;
UPDATE timeout402.jobs
SET status = 'RUNNING'
WHERE job_id = 1;

-- Ứng dụng không gửi lệnh tiếp theo trong nhiều phút.
```

Session ở trạng thái **idle in transaction** có thể giữ locks, giữ snapshot cũ, cản trở vacuum hoặc gây bloat.

PostgreSQL có:

```sql
SHOW idle_in_transaction_session_timeout;
```

### 13.1. Tác dụng

Khi session **idle trong transaction** quá ngưỡng, PostgreSQL **chấm dứt session** để transaction mở được rollback và tài nguyên/locks được giải phóng.

Đây không chỉ là “hủy query hiện tại”, vì tại thời điểm idle có thể không có query nào đang chạy.

### 13.2. Demo trong session riêng

```sql
SET idle_in_transaction_session_timeout = '3s';

BEGIN;
SELECT 1;

-- Dừng gửi SQL khoảng 4 giây trong psql/session riêng.
-- PostgreSQL có thể chấm dứt connection.

-- Sau đó cần reconnect, không tiếp tục dùng session cũ.
```

Không chạy lab này qua connection pool đang phục vụ request thật.

### 13.3. Nó không giới hạn một query đang chạy lâu

Nếu `SELECT pg_sleep(100)` đang active, session không phải “idle in transaction” trong khoảng đó. Dùng `statement_timeout` cho một statement active.

### 13.4. Không giữ transaction khi chờ network

Một anti-pattern:

```text
BEGIN
UPDATE một row
gọi HTTP service mất 20 giây
COMMIT
```

Trong 20 giây, transaction đang mở dù PostgreSQL session có thể ở trạng thái idle-in-transaction. Dùng kiến trúc transaction ngắn, không để lock chờ external service.

## 14. `idle_session_timeout`: session rảnh ngoài transaction

`idle_session_timeout` giới hạn thời gian session **idle ngoài transaction** và có thể làm backend chấm dứt connection khi quá ngưỡng.

### 14.1. Cẩn thận với connection pool

Connection trong pool thường **idle giữa các requests**. Nếu server đóng chúng mà pool chưa phát hiện, request sau có thể lấy phải một connection hỏng và gặp lỗi.

### 14.2. Không áp mặc định quá thấp cho pooled sessions

PostgreSQL docs khuyến nghị cân nhắc kỹ `idle_session_timeout` với pool/middleware. Pool có thể có cơ chế keepalive/validation/maxLifetime riêng; cấu hình phải được phối hợp với infrastructure idle timeouts.

### 14.3. Phân biệt với pool idleTimeout

- PostgreSQL `idle_session_timeout`: server chấm dứt backend sau thời gian idle theo điều kiện.
- HikariCP `idleTimeout`: pool quản lý thời gian giữ **idle pool connections**, tùy cấu hình minIdle/size.
- Network device idle timeout: router/NAT/proxy có thể drop TCP flow.

Cùng có từ “idle” nhưng không phải một đồng hồ duy nhất.

## 15. `transaction_timeout` trên PostgreSQL 17 trở lên

PostgreSQL 17 giới thiệu `transaction_timeout` để giới hạn thời gian tồn tại của một transaction theo cơ chế server.

```sql
-- PostgreSQL 17+:
SHOW transaction_timeout;
```

Nếu đặt ngưỡng khác 0, transaction sống quá lâu có thể khiến backend/session bị chấm dứt.

### 15.1. So với statement_timeout

`statement_timeout` giới hạn **mỗi statement**; một transaction gồm nhiều SQL statements ngắn có thể kéo dài quá tổng ngưỡng đó.

`transaction_timeout` giúp giới hạn **cả transaction lifetime**.

### 15.2. Phải nhận biết phiên bản

Trên PostgreSQL 16 hoặc cũ hơn, `SHOW transaction_timeout` sẽ lỗi vì setting không tồn tại. Không viết migration/config áp dụng máy móc cho mọi server.

### 15.3. Tương tác các timeout

PostgreSQL có quy tắc tương tác giữa `transaction_timeout` với các timeout khác. Khi transaction_timeout bằng hoặc ngắn hơn một số timeout của statement/idle transaction, ngưỡng transaction có thể đến trước. Kiểm tra tài liệu đúng phiên bản và test bằng workload thực, thay vì giả định tất cả timers luôn hoạt động độc lập.

### 15.4. Connection pool và transaction timeout

Nếu server terminates backend, ứng dụng phải xử lý **broken connection**, không chỉ ROLLBACK rồi dùng lại vô điều kiện.

## 16. Hủy câu lệnh từ JDBC bằng `Statement.cancel()`

JDBC có:

```java
statement.cancel();
```

Khi PostgreSQL đang thực hiện một statement, `cancel()` gửi yêu cầu hủy qua driver.

### 16.1. Tình huống thực tế

- Người dùng nhấn “Cancel report”.
- HTTP client ngắt kết nối, application có cơ chế propagate cancellation.
- Background job bị hủy do shutdown hoặc deadline.
- Operator muốn dừng truy vấn đang chạy mà không cắt session.

### 16.2. Cancel từ thread khác

`Statement.cancel()` có thể được dùng như lối hủy từ control thread đối với một statement đang chạy, theo JDBC/driver semantics. Nhưng **không dùng cùng `Connection` để chạy các SQL statements đồng thời từ nhiều threads**.

Cần giữ vòng đời statement rõ ràng: nếu statement đã đóng hoặc driver đã chuyển sang truy vấn khác, cancel có thể xảy ra trễ/race.

### 16.3. Ví dụ mô hình kiểm soát

```java
// Worker thread (sở hữu conn/statement):
try (PreparedStatement ps =
         conn.prepareStatement("SELECT pg_sleep(30)")) {

    ps.setQueryTimeout(5);

    // Control path giữ reference tới statement nếu cần hủy.
    // Khi user cancel: ps.cancel() từ control thread.
    ps.execute();
}
```

Trong sản phẩm thật, xây một lifecycle manager cho request-to-statement mapping, thread-safety và cleanup. Đừng chia sẻ `Connection` làm nơi cho nhiều threads tùy ý gọi SQL.

### 16.4. Không nhầm cancel với close connection

Cancel yêu cầu dừng **statement hiện tại**. Connection có thể vẫn tồn tại và cần xử lý transaction state.

Đóng/terminate connection là thao tác khác, ảnh hưởng cả session.

## 17. Hủy từ PostgreSQL bằng `pg_cancel_backend`

Mỗi backend có process ID:

```sql
SELECT pg_backend_pid();
```

Trong một session giám sát có quyền phù hợp, có thể yêu cầu backend khác hủy truy vấn:

```sql
SELECT pg_cancel_backend(12345);
```

Ở đây `12345` là **ví dụ**; chỉ dùng PID thật đã xác minh trong lab.

### 17.1. Quyền hủy backend

Quyền gọi `pg_cancel_backend` đối với một backend phụ thuộc quyền/role ownership và đặc quyền như `pg_signal_backend` hoặc superuser theo PostgreSQL rules.

Không cấp rộng quyền hủy query của users khác chỉ để thuận tiện.

### 17.2. Hàm trả true chưa chắc query đã dừng

Giá trị trả về cho biết yêu cầu signal/cancel được gửi theo cơ chế hỗ trợ, **không phải xác nhận truy vấn đã bị hủy và transaction đã rollback**.

### 17.3. Một target là một backend

Nếu pool có nhiều backends, cần xác minh đúng `pid`/`application_name`/`usename`/`state` và thời điểm. PID có thể được tái sử dụng sau khi backend cũ kết thúc; tránh lưu PID lâu rồi hủy mù.

### 17.4. Cẩn thận với privileged sessions

Không nhắm vào migrations, replication, maintenance hoặc sessions của người khác khi chưa xác minh hậu quả và quyền điều hành.

## 18. `pg_terminate_backend`: chấm dứt connection, khác cancel

Khi query hoặc session không thể tiếp tục, DBA có thể cần:

```sql
SELECT pg_terminate_backend(12345);
```

Tác dụng khái quát:

- Yêu cầu chấm dứt backend process/session mục tiêu.
- Transaction đang mở được rollback theo database crash/session-termination semantics.
- Locks và tài nguyên session được giải phóng khi backend thật sự kết thúc.
- Ứng dụng sẽ thấy connection bị mất và phải reconnect.

### 18.1. Khi nào ưu tiên cancel?

Nếu chỉ cần dừng một truy vấn runaway mà muốn giữ session nếu có thể, **cancel** là bước ít phá hủy hơn.

### 18.2. Khi nào terminate?

Khi backend không phản hồi, session không còn hợp lệ, có transaction idle giữ locks nguy hiểm, hoặc runbook vận hành yêu cầu ngắt kết nối.

### 18.3. Không coi terminate là “đã dừng ngay”

Cơ chế signal/termination có thể có độ trễ. Phải xác nhận state trong `pg_stat_activity`, locks và ứng dụng.

### 18.4. Terminate không giải quyết connection leak ở code

Nếu Java không close connections đúng, kết nối mới vẫn có thể bị leak sau khi DBA terminate những cái cũ.

## 19. Transaction sau query timeout: chuyện gì xảy ra?

Trong PostgreSQL, một statement lỗi bên trong **explicit transaction** thường khiến transaction ở trạng thái aborted.

Ví dụ:

```sql
BEGIN;

SET LOCAL statement_timeout = '1s';

SELECT pg_sleep(3);
-- ERROR SQLSTATE 57014.

SELECT 1;
-- Có thể nhận:
-- ERROR: current transaction is aborted
-- SQLSTATE 25P02.

ROLLBACK;

SELECT 1;
-- Hoạt động bình thường sau khi rollback.
```

### 19.1. Vì sao không tiếp tục UPDATE?

Sau khi statement đã lỗi, transaction không ở trạng thái có thể tiếp tục SQL bình thường. PostgreSQL yêu cầu rollback transaction hoặc rollback về savepoint hợp lệ theo semantics.

### 19.2. Savepoint là trường hợp có thể kiểm soát

```sql
BEGIN;

SAVEPOINT before_work;

-- Chạy statement có thể bị timeout.
-- Nếu statement lỗi:
ROLLBACK TO SAVEPOINT before_work;

-- Transaction có thể tiếp tục sau khi rollback đúng scope.
COMMIT;
```

Đây là pattern minh họa. Chỉ dùng khi business transaction được thiết kế chấp nhận retry một phần và driver/connection còn sử dụng được.

### 19.3. Auto-commit

Với JDBC `autoCommit=true`, một statement thường nằm trong transaction riêng; lỗi statement có thể không để lại explicit transaction còn mở cho ứng dụng rollback như khi `autoCommit=false`.

Tuy nhiên, **read/socket failure hoặc kết nối hỏng** có thể khiến outcome không chắc chắn. Không đồng nhất auto-commit với an toàn tuyệt đối cho retries.

## 20. JDBC transaction code: rollback trên SQLException

Ví dụ service sử dụng một connection riêng cho transaction:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class JobService {
    private final DataSource ds;

    public JobService(DataSource ds) {
        this.ds = ds;
    }

    public void markRunning(int jobId) throws SQLException {
        try (Connection conn = ds.getConnection()) {
            conn.setAutoCommit(false);

            try {
                try (PreparedStatement ps = conn.prepareStatement("""
                    UPDATE timeout402.jobs
                    SET status = 'RUNNING',
                        updated_at = clock_timestamp()
                    WHERE job_id = ?
                    """)) {

                    ps.setInt(1, jobId);
                    ps.setQueryTimeout(3);

                    int changed = ps.executeUpdate();
                    if (changed != 1) {
                        throw new SQLException(
                            "Expected exactly one job row"
                        );
                    }
                }

                conn.commit();
            } catch (SQLException original) {
                try {
                    conn.rollback();
                } catch (SQLException rollbackError) {
                    original.addSuppressed(rollbackError);
                }
                throw original;
            }
        }
    }
}
```

### 20.1. Vì sao rollback cần try/catch riêng?

Nếu connection đã bị đóng do network timeout, `rollback()` cũng có thể thất bại. Không che lỗi gốc; lưu rollback error làm suppressed exception để điều tra.

### 20.2. Vì sao close connection trong finally/try-with-resources?

Để tránh pool leak. Trong pool, `close()` thường trả proxy connection cho pool, không nhất thiết đóng physical TCP socket; pool cần nhận diện các connection đã broken.

### 20.3. Một vấn đề còn lại: commit outcome uncertainty

Nếu `conn.commit()` đã được gửi tới server nhưng kết nối mất trước khi client nhận kết quả, code có thể thấy SQLException **dù transaction đã commit**. Chỉ nhìn `SQLException` không xác nhận rollback đã xảy ra.

Thiết kế business cần idempotency và reconciliation riêng nếu có thao tác ghi quan trọng.

### 20.4. Một vấn đề khác: timeout có thể đến trước commit

`ps.setQueryTimeout(3)` giới hạn statement UPDATE, không áp dụng một cách giống hệt cho mọi bước commit/đọc network hoặc toàn business transaction. Cần deadline/transaction timeout/network policy riêng.

## 21. SQLSTATE: phân loại lỗi thay vì chỉ tìm chữ “timeout”

PostgreSQL cung cấp SQLSTATE để phân loại lỗi có cấu trúc. Một số mã thường gặp:

| SQLSTATE | Tên/loại | Ngữ cảnh |
| --- | --- | --- |
| `57014` | `query_canceled` | `statement_timeout` hoặc cancel request làm hủy statement |
| `55P03` | `lock_not_available` | `lock_timeout` hoặc `NOWAIT` không lấy được lock |
| `40P01` | `deadlock_detected` | Deadlock detector tìm thấy chu trình khóa |
| `40001` | `serialization_failure` | Transaction isolation yêu cầu retry toàn transaction |
| `25P02` | `in_failed_sql_transaction` | Query tiếp theo khi transaction đã aborted |
| `08xxx` | Connection exception class | Network/protocol/connection failure tùy mã cụ thể |

### 21.1. `57014` có thể do nhiều nguồn

Một câu SQL bị user cancel hoặc server statement timeout có thể đều có `57014`. Nếu cần phân biệt chính xác, kết hợp message/log, cấu hình timeout, request ID và thời điểm; không chỉ dựa trên mỗi mã.

### 21.2. `55P03` cũng có thể do NOWAIT

`SELECT ... FOR UPDATE NOWAIT` có thể báo `55P03` ngay khi không lấy được lock. Không phải mỗi `55P03` đều chứng minh một lock timeout đã đếm hết giây.

### 21.3. Connection error không đồng nghĩa database rollback

Lỗi `08xxx` hoặc `SocketTimeoutException` có thể biểu thị client mất khả năng biết server đã làm gì. Với thao tác ghi, phải xử lý trạng thái mơ hồ.

### 21.4. Trong Java

```java
try {
    // Query...
} catch (SQLException ex) {
    String state = ex.getSQLState();

    if ("57014".equals(state)) {
        // Query canceled / statement timeout.
    } else if ("55P03".equals(state)) {
        // Lock wait failed, hoặc NOWAIT.
    } else if ("40001".equals(state)) {
        // Serialization retry có kiểm soát.
    } else if (state != null && state.startsWith("08")) {
        // Connection issue: outcome có thể bất định.
    }

    throw ex;
}
```

Không dựa duy nhất vào kiểu `SQLTimeoutException` hoặc substring trong error message để quyết định retry các thao tác ghi.

## 22. Client timeout khi server đã COMMIT: “unknown outcome”

Một trường hợp nguy hiểm:

```text
Ứng dụng                            PostgreSQL
    |                                   |
    |--------- INSERT order ----------->|
    |                                   |
    |----------- COMMIT --------------->|
    |                                   | COMMIT hoàn tất
    |                    [mất gói / đứt network]
    |<----- không nhận confirmation -----X
    |
    +-- SQLException / timeout
    +-- Không biết giao dịch đã commit hay chưa!
```

### 22.1. Không retry INSERT vô điều kiện

Nếu gửi lại thao tác đặt hàng mà transaction đầu tiên **đã commit**, có thể tạo đơn hàng trùng hoặc trừ tiền hai lần.

### 22.2. Idempotency key

Ứng dụng phát một mã giao dịch nghiệp vụ duy nhất, ví dụ `request_id`, có unique constraint:

```sql
CREATE TABLE timeout402.requests (
    request_id uuid PRIMARY KEY,
    tenant_id integer NOT NULL,
    result_text text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
```

Một retry dùng **cùng request_id** và logic idempotent để không tạo side effect lần hai.

### 22.3. Dữ liệu phải nhất quán với request ID

Một key không được tái sử dụng cho hai request khác nội dung. Production thường lưu thêm hash payload, status/result và quy tắc conflict để trả lại kết quả cũ hoặc từ chối mismatch.

### 22.4. `ON CONFLICT` không tự giải quyết mọi side effect

`INSERT ... ON CONFLICT` có thể ngăn insert trùng theo một unique key, nhưng nếu code gửi email/call payment service ở ngoài transaction mà không có idempotency tương ứng, side effect bên ngoài vẫn có thể lặp.

### 22.5. Phân biệt retry lỗi transaction và retry lỗi mất mạng

- `40001`: PostgreSQL đã báo transaction phải retry; retry **toàn bộ** transaction theo business policy.
- `40P01`: deadlock victim cần retry có kiểm soát.
- `57014` do server hủy statement: kiểm tra deadline và có nên retry không.
- Network timeout quanh commit: outcome mơ hồ; **reconcile bằng idempotency key**, không gửi lại như chưa từng chạy.

## 23. HTTP request timeout không tự hủy PostgreSQL query

Giả sử reverse proxy trả `504 Gateway Timeout` sau 10 giây. PostgreSQL query được gọi từ backend vẫn có thể chạy thêm 1 phút nếu application không hủy statement hoặc server không có timeout.

### 23.1. Client disconnect khác driver cancel

Trình duyệt đóng tab không tự tương đương với `Statement.cancel()`. Framework/server có thể propagate cancellation hoặc không, tùy cách ứng dụng được viết.

### 23.2. Deadline nên được truyền xuống database layer

Tại thời điểm bắt đầu request, tính deadline. Khi cần query, lấy **remaining time budget** thay vì luôn cho SQL thêm một số giây cố định bất kể request đã tốn bao lâu.

### 23.3. Chặn công việc mới sau deadline

Nếu không còn budget, không lấy connection rồi chạy một query mới chỉ vì mặc định statement timeout còn 30 giây.

### 23.4. Dọn tài nguyên khi request bị cancel

- Hủy statement đang active khi phù hợp.
- Rollback transaction nếu cần và connection còn tốt.
- Đóng statement/result set.
- Trả/discard connection qua pool đúng contract.
- Ghi metrics outcome và correlation ID.
- Không để transaction idle giữ lock vì response đã kết thúc.

### 23.5. Không cancel nhầm job đã được thiết kế chạy nền

Nếu workflow chuyển thành background job có lifecycle riêng, HTTP disconnect có thể không phải lý do dừng job. Cần phân biệt synchronous request-bound query và durable async work.

## 24. Thiết kế timeout budget cho API

Ví dụ một request đọc dữ liệu có SLO 8 giây. Một cấu hình khởi đầu có thể là:

| Thành phần | Ngưỡng minh họa | Ý nghĩa |
| --- | ---: | --- |
| HTTP application deadline | 8 s | Trần tổng request |
| Chờ pool checkout | 0,8 s | Không xếp hàng pool quá lâu |
| Driver connectTimeout | 2 s/attempt | Nếu cần physical connection |
| Server lock_timeout | 0,8 s | Giảm thời gian chờ lock |
| Server statement_timeout | 5 s | Giới hạn SQL |
| JDBC queryTimeout | 6 s | Client có lớp cancel bổ sung |
| Socket read timeout | 12 s | Backstop lỗi mạng; không phải HTTP deadline |
| Cancel signaling | 3 s | Giới hạn đường yêu cầu cancel |

Các số là **ví dụ phân tích**, không phải công thức áp dụng mọi hệ thống.

### 24.1. Đừng cộng như các tầng luôn tuần tự

Một số ngưỡng chạy **chồng lên nhau** (server/JDBC/socket query) chứ không được cộng hết. Ngược lại, pool wait + connect + query + xử lý kết quả có thể là các đoạn tuần tự.

### 24.2. Cần để khoảng đệm

Nếu HTTP deadline 8s mà JDBC query timeout 8s, ứng dụng có thể không còn thời gian rollback/logging/response khi query bị hủy.

### 24.3. Query budget phải phụ thuộc thời gian còn lại

Nếu request đã tiêu 4 giây cho authentication và gọi downstream, không nên cho DB thêm 5 giây dù server default vẫn là 5s. Giới hạn hiệu lực cần xét remaining deadline.

### 24.4. Socket read timeout dài hơn query timeout không làm HTTP deadline tự được giữ

Socket timeout 12s là **backstop transport**. Muốn phản hồi trước 8s, application phải thực thi deadline/cancel và không tiếp tục chờ socket trong cùng request mãi.

### 24.5. Background job có budget khác

Batch migration/report có thể chấp nhận phút/giờ và nên dùng connection/job pool, role defaults và metrics riêng. Không áp timeout 5s của API tương tác lên mọi workload.

## 25. HikariCP: phân biệt cấu hình pool với JDBC/network

Một ví dụ Java minh họa sử dụng HikariCP (cần dependency HikariCP, PostgreSQL JDBC Driver):

```java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import java.util.Properties;

HikariConfig config = new HikariConfig();

config.setJdbcUrl(
    "jdbc:postgresql://localhost:5432/appdb"
);
config.setUsername("app_runtime");
config.setPassword(System.getenv("DB_PASSWORD"));

config.setMaximumPoolSize(10);
config.setMinimumIdle(2);

// HikariCP: mili-giây.
config.setConnectionTimeout(1000);
config.setValidationTimeout(1000);
config.setIdleTimeout(600000);
config.setMaxLifetime(1800000);
config.setKeepaliveTime(120000);

// pgJDBC: phần lớn timeout ở đây là giây.
Properties props = new Properties();
props.setProperty("connectTimeout", "3");
props.setProperty("loginTimeout", "5");
props.setProperty("socketTimeout", "15");
props.setProperty("cancelSignalTimeout", "5");
props.setProperty("tcpKeepAlive", "true");
props.setProperty("ApplicationName", "orders-api");

config.setDataSourceProperties(props);

try (HikariDataSource ds = new HikariDataSource(config)) {
    // Sử dụng ds.getConnection() trong service.
}
```

Đây là cấu hình **minh họa**, không yêu cầu bạn tự tạo database, role hoặc password theo tên này.

### 25.1. Đơn vị khác nhau

- HikariCP `connectionTimeout`, `validationTimeout`, `idleTimeout`, `maxLifetime` và `keepaliveTime` là **milliseconds**.
- pgJDBC `connectTimeout`, `loginTimeout`, `socketTimeout` và `cancelSignalTimeout` là **seconds**.

Nhầm `5000` giữa hai thư viện có thể biến 5 giây thành hàng chục phút/giờ.

### 25.2. `maxLifetime` không phải query timeout

Nó là cơ chế quản lý vòng đời connection trong pool; một connection đang được sử dụng không đơn thuần bị cắt ngay giữa query chỉ vì thời hạn pool lifecycle đã đến.

### 25.3. `keepaliveTime` không giống TCP keepalive

Hikari keepalive có thể kiểm tra/giữ sống **idle pool connection** theo pool policy; TCP keepalive sử dụng network socket probes ở OS/network layer.

Cả hai không thay `statement_timeout`.

### 25.4. Cần theo dõi pool metrics

Quan sát active/idle/pending connections, thời gian checkout, số connection creations và failures. Nếu pool thường xuyên cạn, phải điều tra query latency/transactions/concurrency, không chỉ tăng `connectionTimeout`.

## 26. TCP keepalive và network equipment

Các thiết bị mạng có thể cắt kết nối lâu không có traffic: NAT, firewall, load balancer, proxy hoặc service mesh.

### 26.1. TCP keepalive

Khi bật `tcpKeepAlive`, TCP stack có thể gửi probes theo **cấu hình OS**. Nó giúp phát hiện một số half-open connections, nhưng không cung cấp SQL execution deadline 5s hay phát hiện mọi network partition ngay lập tức.

### 26.2. Network idle timeout

Load balancer có thể drop một TCP flow idle. Nếu pool giữ connection lâu hơn device idle policy, lần dùng sau có thể nhận `connection reset`/EOF/read timeout.

### 26.3. Pool validation

Pool có thể gọi JDBC validation để phát hiện connection không dùng được trước khi cấp cho app. Tuy nhiên, validation thành công tại T1 không bảo đảm network còn tốt ở T2.

### 26.4. Kết hợp cấu hình

- Biết chính sách idle timeout của thiết bị hạ tầng.
- Đặt pool maxLifetime/keepalive hợp lý với server/network.
- Bật TCP keepalive khi phù hợp.
- Sử dụng validation và cơ chế loại bỏ broken connections.
- Có retry riêng cho thao tác **an toàn/idempotent**.
- Theo dõi các lỗi `08xxx` và socket exceptions.

### 26.5. Không dùng keepalive để chữa slow query

Một query đang chờ lock không nhanh hơn vì TCP keepalive. Cần điều tra locks và statement/lock timeouts.

## 27. PgBouncer/proxy có thể thêm một lớp timeout

Nếu kiến trúc dùng connection pooler hoặc proxy trước PostgreSQL:

```text
Java/Hikari
    |
    | client TCP
    v
PgBouncer / cloud proxy / LB
    |
    | server TCP
    v
PostgreSQL backend
```

Có thể có thêm:

- Connection establishment/health checks của proxy.
- Timeout chờ server connection.
- Query timeout/idle timeout theo tính năng/config cụ thể.
- Socket lifetime/server recycling.
- Transaction-pooling restrictions với session state.

### 27.1. Không mặc định một connection vật lý = một backend cố định

Trong **transaction pooling**, nhiều client operations có thể được phân phối tới các server connections khác nhau qua các transactions. Session-level `SET`/prepared statements và backend PID assumptions phải được thiết kế theo khả năng thực tế của pooler/phiên bản.

### 27.2. Ưu tiên transaction-scoped settings khi phù hợp

`SET LOCAL statement_timeout` trong một explicit transaction phù hợp hơn việc kỳ vọng một session default tuỳ biến sẽ luôn gắn với cùng backend qua transaction pooler, nhưng phải xác minh hành vi cụ thể của pooler/config.

### 27.3. Xem log ở cả hai phía

Nếu app báo timeout, kiểm tra driver/pooler/backend logs để xác định timeout từ layer nào. Một proxy đóng socket không nhất thiết khiến server SQL được cancel theo cách mong đợi.

### 27.4. Server setting có thể vẫn là backstop

`statement_timeout` do PostgreSQL thực thi giúp giới hạn SQL ngay cả khi HTTP client/proxy đã lỗi, miễn statement thuộc scope mà setting áp dụng.

## 28. Điều tra query đang chạy bằng `pg_stat_activity`

Một công cụ đầu tiên:

```sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    clock_timestamp() - query_start AS query_age,
    clock_timestamp() - xact_start AS transaction_age,
    query
FROM pg_catalog.pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid()
ORDER BY query_start NULLS LAST;
```

### 28.1. `state = 'active'`

Backend đang xử lý query (có thể đang **chờ lock/I/O**). Không có nghĩa CPU đang chạy liên tục.

### 28.2. `state = 'idle in transaction'`

Session hiện không chạy query nhưng vẫn còn transaction mở, có thể giữ locks/snapshot.

### 28.3. `wait_event_type`

- `Lock`: chờ lock.
- `IO`: có thể liên quan I/O.
- `Client`: liên quan chờ client/network.
- NULL: không chờ một event được instrumented tại thời điểm lấy snapshot, không khẳng định backend không có vấn đề.

### 28.4. `query_start` khác `xact_start`

Một transaction có thể bắt đầu từ lâu và chứa nhiều statements. `query_start` của session hiện tại/last query không đồng nghĩa transaction lifetime.

Khi đo query age, nên diễn giải trong ngữ cảnh `state`. Với session idle, `query_start` có thể là thời điểm của query trước đó.

### 28.5. Quyền quan sát

Một role có thể bị hạn chế xem SQL text hoặc thông tin sessions khác. Dùng role giám sát phù hợp (ví dụ một số predefined monitoring roles) và bảo vệ privacy vì `query` có thể chứa dữ liệu nhạy cảm.

## 29. Tìm lock blockers bằng `pg_blocking_pids`

PostgreSQL có helper:

```sql
SELECT
    a.pid AS waiting_pid,
    a.usename,
    a.application_name,
    a.wait_event_type,
    a.wait_event,
    pg_catalog.pg_blocking_pids(a.pid) AS blocking_pids,
    a.query
FROM pg_catalog.pg_stat_activity AS a
WHERE a.datname = current_database()
  AND a.wait_event_type = 'Lock'
ORDER BY a.pid;
```

### 29.1. Vì sao dùng pg_blocking_pids?

`pg_locks` chứa nhiều records cho locks, nhưng tự join để xác định blocker chính xác có nhiều chi tiết khó (lock modes, wait queues, parallel workers). `pg_blocking_pids` giúp lấy danh sách PIDs đang chặn theo cơ chế PostgreSQL.

### 29.2. Không terminate ngay blocker đầu tiên

Trước tiên xác định:

- Query/transaction đó đang làm gì?
- Có migration hợp lệ đang chạy?
- Blocker có đang ở trạng thái idle-in-transaction do ứng dụng quên commit?
- Dữ liệu chưa commit có cần bảo toàn không?
- Có thể yêu cầu ứng dụng rollback trước không?

### 29.3. Nếu cần thêm chi tiết

```sql
SELECT
    l.pid,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation_name
FROM pg_catalog.pg_locks AS l
WHERE l.pid IS NOT NULL
ORDER BY l.pid, l.granted;
```

Không phải mọi `pg_locks` row có `relation`; giá trị NULL là bình thường với lock types khác.

### 29.4. Snapshot có tính thời điểm

Giữa lúc đọc PIDs và gửi cancel, query/connection có thể đã đổi. Dùng thêm `backend_start`, `application_name`, user và transaction metadata khi cần tránh nhắm nhầm PID.

## 30. Logging và giám sát timeout

Những chỉ số nên đo:

| Metric | Mục đích |
| --- | --- |
| API request latency và timeout rate | Hiểu trải nghiệm người dùng |
| Pool pending/active/idle connections | Phát hiện pool pressure |
| Connection establishment failures | Phát hiện DNS/TLS/auth/network |
| Query execution time / SQLSTATE 57014 | Theo dõi statement cancellation |
| Lock wait counts / 55P03 | Phát hiện contention |
| Deadlocks / 40P01 | Phát hiện giao dịch khóa lẫn nhau |
| Socket/read failures / SQLSTATE 08xxx | Theo dõi transport |
| Idle-in-transaction sessions | Phát hiện leaks của transaction |
| Broken connections discarded | Đánh giá pool recovery |
| Backend termination events | Phát hiện session-level timeout |
| Retry counts và idempotency conflicts | Quan sát hành vi sau lỗi |
| Commit outcome reconciliation | Tránh ghi trùng nghiệp vụ |

### 30.1. `application_name`

Đặt theo ứng dụng/workload:

```text
ApplicationName=orders-api
```

Sau đó có thể lọc `pg_stat_activity`, nhưng đừng đưa PII/secret/token vào application_name.

### 30.2. Slow query logging

Các setting như `log_min_duration_statement` có thể giúp quan sát statement chậm, khi được quản trị theo môi trường. Bật logging rộng có thể tăng I/O và lộ SQL/literals trong log.

### 30.3. `log_lock_waits` và `deadlock_timeout`

PostgreSQL có cơ chế log những waits dài khi cấu hình `log_lock_waits` và `deadlock_timeout` phù hợp. Đây là **observability**, không phải thay thế `lock_timeout`.

### 30.4. `pg_stat_statements`

Nếu extension được cài/cấu hình, nó giúp xem aggregate query stats. Không phải lúc nào cũng sẵn; ngay cả khi có, nó không cho biết đầy đủ vì sao một request HTTP cụ thể timeout.

### 30.5. Correlation ID

Gắn request/job ID vào application logs và trace spans, liên kết tới query template, pool wait, DB duration và SQLSTATE. Không log credentials hoặc thông tin người dùng nhạy cảm tùy tiện.

## 31. Retry: khi nào hợp lý và khi nào nguy hiểm?

Một retry policy tốt phải xét:

1. **Operation**: read-only hay ghi dữ liệu?
2. **Lỗi**: lock wait, deadlock, serialization, query canceled hay network failure?
3. **Deadline**: còn đủ thời gian cho retry không?
4. **Idempotency**: gửi lại có gây tác dụng lần hai không?
5. **State**: transaction đã aborted, connection broken hay commit outcome unknown?
6. **Contention**: retry ngay có làm tải tăng thêm không?

### 31.1. SELECT read-only

Một SELECT có thể retry khi gặp một số lỗi kết nối tạm thời, nhưng phải bảo vệ consistency requirements, paging/snapshot semantics và request deadline.

### 31.2. `55P03` do lock timeout

Retry có thể hữu ích khi contention ngắn. Dùng bounded retries, jitter/backoff và giảm lock duration thay vì retry không giới hạn.

### 31.3. `40P01` và `40001`

Thường cần retry **toàn bộ transaction** từ điểm bắt đầu logic nghiệp vụ, không chỉ câu SQL vừa lỗi, theo PostgreSQL transaction isolation semantics.

### 31.4. `57014` do user cancel

Nếu user chủ động hủy, retry tự động sẽ đi ngược ý định của họ.

### 31.5. HTTP deadline đã hết

Không tiếp tục retry query chỉ vì DB báo có thể retry, trừ khi tác vụ được thiết kế thành một background workflow độc lập.

### 31.6. Network lỗi gần COMMIT

Kiểm tra idempotency/result trong hệ thống đáng tin, không giả định rollback. Đối với thanh toán/đặt hàng, đây là một yêu cầu correctness cốt lõi.

## 32. Tránh retry storm sau outage

Giả sử 1.000 HTTP requests đồng thời bị SQL timeout. Nếu tất cả retry ngay 3 lần, DB có thể nhận 3.000 queries bổ sung đúng lúc đang quá tải.

### 32.1. Bounded exponential backoff với jitter

Ví dụ policy khái niệm:

```text
lần 1 lỗi 40P01
    |
    +-- còn deadline?
         |
         +-- có -> random wait 50..150ms -> retry
         |
         +-- không -> fail có kiểm soát
```

Không cần dùng cùng các số cho mọi workload.

### 32.2. Circuit breaker và bulkhead

Tách query pools cho workload nặng và API latency-sensitive khi phù hợp. Sử dụng concurrency caps, load shedding, circuit breakers ở tầng ứng dụng/hạ tầng.

### 32.3. Timeout cần đi cùng capacity controls

Chỉ đặt timeout 1 giây không chữa được query plan xấu; nó có thể tạo thêm lỗi/retries, tăng contention nếu traffic tiếp tục.

### 32.4. Đo error budget

Quan sát cả tỷ lệ timeout **và** tỷ lệ thành công theo latency. Không tối ưu “số query bị hủy” bằng cách tắt tất cả timeouts khi DB vẫn thường xuyên treo request.

## 33. Các lỗi cấu hình thường gặp

| Lỗi | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Tưởng pool connectionTimeout là query timeout | SQL vẫn chạy lâu | Thiết lập JDBC/server query timeout |
| Tưởng connectTimeout là total HTTP deadline | Request chậm dù TCP connect nhanh | Request deadline và per-stage budgets |
| Socket timeout ngắn hơn statement timeout nhiều | Driver bỏ connection khi SQL còn chạy | Phối hợp timeout + cancellation |
| Chỉ dùng HTTP timeout | Query tiếp tục sau khi HTTP fail | Propagate cancel + server timeout |
| `statement_timeout=0` mà không có lớp khác | Query có thể chạy rất lâu | Timeout theo workload |
| `lock_timeout` lớn hơn `statement_timeout` | Chỉ statement_timeout thường đến trước | Lock timeout thấp hơn khi cần |
| `idle_in_transaction_session_timeout` quá thấp | Sessions bị terminate đột ngột | Giữ transaction ngắn; cấu hình hợp lý |
| `idle_session_timeout` quá thấp với pool | Nhiều stale connections | Phối hợp server/pool/network |
| Áp 5s timeout cho mọi migration | Schema change hợp lệ fail | Phân role/workload |
| `SET statement_timeout` rồi không RESET | Rò session state qua pool | `SET LOCAL`/reset |
| Không ROLLBACK sau lỗi trong transaction | SQLSTATE 25P02 trên lệnh sau | Rollback đúng scope |
| Retry INSERT sau socket failure | Có thể trùng nghiệp vụ | Idempotency/reconciliation |
| Coi cancel() luôn dừng query ngay | Race, connection/driver lỗi | Quan sát response/outcome |
| Dùng terminate để xử lý mọi query chậm | Mất connection, rollback rộng | Cancel trước khi phù hợp |
| Hủy PID không xác minh | Có thể tác động session khác | Xác minh application/user/backend_start |
| Không close connection khi lỗi | Pool leak | try-with-resources |
| Chia sẻ Connection cho threads SQL đồng thời | Protocol/state races | Per-request ownership |
| Chỉ đếm query age khi state idle | Diễn giải sai thời gian | Xem state/xact_start |
| Tăng maximumPoolSize vô hạn | PostgreSQL overload | Chẩn đoán root cause |
| Dùng TCP keepalive làm query timeout | Không giới hạn SQL duration | statement/query timeout |
| Dùng network timeout làm transaction outcome guarantee | Commit mơ hồ | Idempotency |
| Không đo lock blockers | Chỉ thấy “query chậm” | pg_blocking_pids và logs |
| Không tách bg jobs/API | Báo cáo dài làm nghẽn API pool | Pools/roles budgets riêng |

## 34. Bộ test thực hành kiểm tra các timeout

Để thử, sử dụng database `timeout402` riêng và ít nhất hai sessions khi cần.

### 34.1. Case A — server-side query timeout

```sql
SET statement_timeout = '1s';
SELECT pg_sleep(3);
RESET statement_timeout;
```

Kỳ vọng lỗi SQLSTATE `57014`, session thường vẫn hoạt động nếu không bị mất connection.

### 34.2. Case B — transaction aborted sau statement timeout

```sql
BEGIN;
SET LOCAL statement_timeout = '1s';
SELECT pg_sleep(3);
SELECT 1;
ROLLBACK;
```

Kỳ vọng `SELECT 1` (nếu thực hiện sau lỗi mà chưa rollback) báo `25P02`.

### 34.3. Case C — lock timeout

Dùng hai sessions như phần 12. Kỳ vọng B nhận `55P03` nếu lock của A còn giữ quá thời gian.

### 34.4. Case D — cancel thủ công

Session A:

```sql
SELECT pg_backend_pid();
SELECT pg_sleep(30);
```

Session B (có quyền phù hợp):

```sql
SELECT pg_cancel_backend(<pid_cua_session_A>);
```

Dòng `<pid_cua_session_A>` là placeholder mô tả, **không phải SQL chạy nguyên văn**. Thay bằng PID thật đã xác minh. Kỳ vọng A nhận `57014` nếu yêu cầu đến khi query còn chạy.

### 34.5. Case E — terminate

Trong lab và với quyền cần thiết, session B:

```sql
-- Ví dụ với PID thật, chỉ chạy trên session lab:
SELECT pg_terminate_backend(12345);
```

Kỳ vọng session mục tiêu mất connection. Không dùng PID ví dụ hoặc hủy backend hệ thống/người khác.

### 34.6. Case F — pool checkout timeout

Dùng pool rất nhỏ trong integration test:

- Checkout và giữ tất cả connections.
- Gọi `getConnection()` lần nữa.
- Xác minh ứng dụng nhận lỗi pool timeout theo ngưỡng.
- Trả connections trong finally.

Không tạo connection leaks cố ý trong production.

### 34.7. Case G — network/socket failure

Dùng môi trường tích hợp có network fault injection được cho phép để mô phỏng mất kết nối hoặc proxy close. Xác minh ứng dụng discard connection và xử lý ambiguous write outcome.

**Không dùng firewall/network disruption lên production chỉ để thử nghiệm.**

### 34.8. Case H — idle in transaction

Dùng connection lab riêng với `idle_in_transaction_session_timeout` nhỏ và dừng gửi SQL. Quan sát session bị terminate rồi reconnect.

### 34.9. Case I — transaction timeout PG17+

Kiểm tra `server_version_num` và chạy test theo tài liệu version, không gửi `SHOW transaction_timeout` trên PG16 hoặc thấp hơn.

### 34.10. Case J — cancel trước và sau khi query kết thúc

Quan sát race: cancel request đến quá muộn có thể không hủy statement đã hoàn tất. Hệ thống không được chỉ căn cứ vào việc đã gửi signal để kết luận transaction chưa commit.

## 35. Thiết kế integration test với JDBC

Một test tốt nên xác nhận cả exception và trạng thái backend:

1. Tạo DataSource dành riêng cho test.
2. Sử dụng table/roles chỉ trong database test.
3. Đặt server timeout thấp cho test bằng `SET LOCAL`.
4. Chạy `SELECT pg_sleep(...)` và xác minh `SQLSTATE 57014`.
5. Sau lỗi trong explicit transaction, xác minh connection yêu cầu rollback.
6. Rollback rồi chạy `SELECT 1` trên connection còn khỏe.
7. Thử row lock với hai physical connections.
8. Đo pool pending connections khi toàn pool bận.
9. Test `Statement.cancel()` trên một statement sở hữu riêng.
10. Test mất mạng có kiểm soát và connection eviction.
11. Test idempotent retries khi không biết outcome COMMIT.
12. Kiểm tra application logs không rò password/SQL sensitive values.

### 35.1. Vì sao không chỉ mock SQLException?

Mock có ích cho logic branching, nhưng không chứng minh transaction aborted semantics, signal delivery hoặc socket behavior. Cần integration tests trên PostgreSQL thật.

### 35.2. Query timeout test có thể lệch thời gian

Scheduler, CI load và network có thể khiến timing dao động. Kiểm tra loại lỗi, trạng thái và khoảng thời gian hợp lý, không assert chính xác từng millisecond.

### 35.3. Test environment phải ổn định

Không chạy stress tests hàng trăm connections trên shared development database mà không có giới hạn, vì dễ ảnh hưởng những người làm việc khác.

## 36. Runbook xử lý sự cố “API treo vì PostgreSQL”

### Bước 1. Xác định triệu chứng

- HTTP 504 từ proxy hay timeout từ ứng dụng?
- Pool `getConnection()` timeout hay JDBC query timeout?
- SQLException SQLSTATE nào?
- Chỉ một endpoint hay tất cả endpoints?
- Một database host/zone hay toàn hệ thống?

### Bước 2. Nhìn pool metrics

Active connections, idle connections, pending requests, checkout latency và error rate.

Nếu pool pending cao nhưng SQL time bình thường, tìm leaks/transaction duration; nếu SQL time cao, tiếp tục phân tích queries.

### Bước 3. Xem `pg_stat_activity`

Tập trung:

- `state='active'`, query_age cao.
- `wait_event_type='Lock'`.
- `state='idle in transaction'` và transaction_age cao.
- `application_name` để biết nguồn workload.

### Bước 4. Tìm blockers

`pg_blocking_pids` và `pg_locks`. Xác định transaction giữ lock trước khi can thiệp.

### Bước 5. Kiểm tra server logs

Tìm `statement timeout`, `lock timeout`, deadlock, connection reset, backend termination, failover và authentication failures.

### Bước 6. Hành động an toàn theo mức độ

- Hạn chế request concurrency hoặc traffic tới query nặng.
- Yêu cầu ứng dụng rollback/đóng session idle-in-transaction.
- `pg_cancel_backend` đúng PID khi cần dừng query.
- `pg_terminate_backend` chỉ khi cần và hiểu tác động transaction.
- Nếu SQL plan xấu, dùng index/query optimization, không chỉ tăng timeout.

### Bước 7. Phục hồi ứng dụng

Xác minh pool đã loại broken connections, connection acquisition trở lại bình thường và retry không gây duplicate orders/jobs.

### Bước 8. Ngăn tái diễn

Điều chỉnh budgets, query plans, timeout defaults, transaction boundaries, concurrency limits và monitoring theo nguyên nhân thực tế.

## 37. Các tình huống đặc biệt

### 37.1. COPY hoặc truy vấn trả nhiều dữ liệu

Truyền dữ liệu lớn có thể làm thời gian network/client processing dài hơn thời gian xử lý SQL cốt lõi. Phải có backpressure, limits và timeout phù hợp. Không giả định `statement_timeout` đo đúng toàn bộ business export workflow.

### 37.2. Cursor/fetch nhiều lần

Một cursor có thể thực hiện nhiều fetch calls; scope của `statement_timeout` theo từng command/statement và transaction context, không tự giới hạn tổng thời gian duyệt toàn bộ dataset.

### 37.3. DDL migration và lock_timeout

Một migration `ALTER TABLE` có thể cần lock mạnh. `lock_timeout` nhỏ giúp fail fast thay vì chờ lâu; nhưng trước khi chạy lại, cần xử lý state/locks, không retry DDL vô hạn.

### 37.4. Long-running report

Report hợp lệ mất 2 phút có thể chạy bằng background queue với riêng pool/role, statement_timeout và job timeout khác HTTP API. Cần cách lưu trạng thái tiến trình và cancel job an toàn.

### 37.5. Failover

Failover có thể làm connections cũ mất hiệu lực, DNS/host selection thay đổi và transactions chưa rõ outcome. Xử lý reconnect, pool eviction và idempotency; không tự coi failover là rollback chắc chắn mọi business action.

### 37.6. Câu SQL gọi external service

Không giữ DB transaction/row locks trong khi gọi service mạng dài. Nếu cần phối hợp side effects, cân nhắc transactional outbox và workflow idempotent.

### 37.7. Multi-host libpq/driver differences

Không nhầm config syntax của pgJDBC với libpq/psql hoặc driver khác. Ví dụ libpq có `connect_timeout` (underscore) trong connection parameters, còn pgJDBC dùng `connectTimeout` (camelCase). Các đơn vị/defaults cần tra theo client library cụ thể.

## 38. Bài tập thực hành có đáp án

Các bài tập dùng mô hình PostgreSQL + Java/JDBC, với schema `timeout402` khi cần. Chỉ chạy cancellation/termination trên những sessions bạn sở hữu trong database lab.

### Bài 1. Pool checkout timeout là gì?

**Đáp án:** thời gian client chờ `getConnection()` nhận connection từ pool; không phải thời gian một SQL chạy ở server.

### Bài 2. HikariCP `connectionTimeout` dùng đơn vị gì?

**Đáp án:** milliseconds.

### Bài 3. pgJDBC `connectTimeout` dùng đơn vị gì?

**Đáp án:** seconds; nó liên quan thao tác socket connect, không phải query execution.

### Bài 4. `loginTimeout` khác connectTimeout thế nào?

**Đáp án:** loginTimeout kiểm soát thời gian establishment/login theo driver, còn connectTimeout tập trung socket connection operation.

### Bài 5. `socketTimeout` đo gì?

**Đáp án:** thời gian chờ một socket read, không phải absolute wall-clock deadline cho toàn query.

### Bài 6. Vì sao socketTimeout 5s không chứng minh SELECT bị server rollback?

**Đáp án:** lỗi xảy ra ở client transport; server có thể vẫn đang chạy hoặc đã hoàn tất. Cần biết outcome thực tế.

### Bài 7. Java đặt query timeout bằng API nào?

```java
ps.setQueryTimeout(5);
```

**Đáp án:** JDBC Statement-level timeout, đơn vị giây.

### Bài 8. PostgreSQL giới hạn SQL bằng setting nào?

**Đáp án:** `statement_timeout`.

### Bài 9. `statement_timeout=0` nghĩa là gì?

**Đáp án:** vô hiệu hóa giới hạn timeout ở layer này, không có nghĩa các timeout khác đều bị tắt.

### Bài 10. PostgreSQL đặt statement timeout 1,5 giây thế nào?

```sql
SET statement_timeout = '1500ms';
```

**Đáp án:** setting có time units.

### Bài 11. Một SELECT chờ lock có chịu statement_timeout không?

**Đáp án:** có; thời gian chờ lock là một phần thời gian statement.

### Bài 12. `lock_timeout` khác statement_timeout?

**Đáp án:** lock_timeout giới hạn chờ acquire lock, statement_timeout giới hạn toàn statement.

### Bài 13. Vì sao lock_timeout nên nhỏ hơn statement_timeout trong cùng tình huống?

**Đáp án:** nếu statement_timeout đến trước, lock_timeout dài hơn có thể không còn hiệu lực thực tiễn.

### Bài 14. SQLSTATE của query cancel/statement timeout?

**Đáp án:** `57014`.

### Bài 15. SQLSTATE thường thấy với lock_timeout?

**Đáp án:** `55P03`, cũng có thể xuất hiện khi `NOWAIT` không lấy được lock.

### Bài 16. SQLSTATE của deadlock?

**Đáp án:** `40P01`.

### Bài 17. SQLSTATE serialization failure?

**Đáp án:** `40001`.

### Bài 18. SQLSTATE khi query tiếp trong transaction aborted?

**Đáp án:** `25P02`.

### Bài 19. Cách xem cấu hình hiện tại?

```sql
SHOW statement_timeout;
SHOW lock_timeout;
```

**Đáp án:** `SHOW` hoặc `pg_settings`.

### Bài 20. SET LOCAL có lợi gì với connection pool?

**Đáp án:** timeout chỉ trong transaction, tránh rò session-level setting sang request sau nếu dùng đúng scope.

### Bài 21. Chạy SET LOCAL trong transaction nào?

```sql
BEGIN;
SET LOCAL statement_timeout = '5s';
SELECT 1;
COMMIT;
```

**Đáp án:** explicit transaction giúp bảo đảm scope.

### Bài 22. Role default đã thay có áp ngay lên physical connections mở sẵn không?

**Đáp án:** không tự đổi session đã thiết lập; cần quản lý connection lifecycle và kiểm tra config hiệu lực.

### Bài 23. Vì sao role default timeout không nên giống nhau cho API và migration?

**Đáp án:** workload và thời gian hợp lệ khác nhau; timeout API có thể phá migrations/report dài.

### Bài 24. `idle_in_transaction_session_timeout` làm gì?

**Đáp án:** chấm dứt session idle khi transaction vẫn mở quá lâu để giải phóng transaction/locks.

### Bài 25. `idle_session_timeout` có thể ảnh hưởng Hikari như thế nào?

**Đáp án:** PostgreSQL đóng backend idle, pool có thể có stale connections nếu không phát hiện/validate thích hợp.

### Bài 26. PostgreSQL 16 có `transaction_timeout` không?

**Đáp án:** không; setting này được hỗ trợ từ PostgreSQL 17.

### Bài 27. `transaction_timeout` khác statement_timeout?

**Đáp án:** giới hạn đời sống transaction, không chỉ một statement.

### Bài 28. JDBC `Statement.cancel()` có đóng connection không?

**Đáp án:** mục tiêu chính là hủy statement; connection có thể còn, nhưng vẫn cần kiểm tra transaction/driver state.

### Bài 29. Có thể dùng một Connection chạy SQL đồng thời trên nhiều threads cho nhanh không?

**Đáp án:** không nên; cần connection ownership/thread safety. Một control thread gửi `cancel()` là trường hợp khác với tùy ý chạy statements song song trên cùng connection.

### Bài 30. Vì sao cancelSignalTimeout không phải queryTimeout?

**Đáp án:** nó giới hạn giao tiếp gửi yêu cầu cancel, không giới hạn toàn bộ statement.

### Bài 31. `pg_cancel_backend` khác `pg_terminate_backend`?

**Đáp án:** cancel yêu cầu dừng query đang chạy; terminate yêu cầu kết thúc cả backend/session.

### Bài 32. `pg_cancel_backend(pid)` trả true có nghĩa transaction chắc rollback?

**Đáp án:** không. Phải quan sát outcome và state; có thể race với query đã xong.

### Bài 33. Xác định PID session hiện tại?

```sql
SELECT pg_backend_pid();
```

**Đáp án:** trả PostgreSQL backend process ID của connection.

### Bài 34. Hủy session người khác cần quyền gì?

**Đáp án:** quyền theo PostgreSQL role/ownership/signal model, ví dụ đặc quyền `pg_signal_backend` hoặc superuser khi phù hợp; không tự cấp rộng.

### Bài 35. Dùng gì tìm session chờ lock?

**Đáp án:** `pg_stat_activity.wait_event_type='Lock'` và `pg_blocking_pids(pid)`.

### Bài 36. `state='active'` có nghĩa CPU luôn bận?

**Đáp án:** không; active backend có thể đang chờ lock/I/O/network theo instrumented wait events.

### Bài 37. `state='idle in transaction'` nguy hiểm ra sao?

**Đáp án:** có thể giữ lock/snapshot, cản vacuum và làm kéo dài transaction age dù không chạy query.

### Bài 38. Nếu SELECT lỗi trong BEGIN, có thể SELECT tiếp ngay không?

**Đáp án:** thường không; transaction aborted cần `ROLLBACK` hoặc xử lý bằng savepoint theo semantics.

### Bài 39. Tại sao rollback trong Java cũng cần catch?

**Đáp án:** network failure có thể làm connection unusable; rollback cũng có thể ném SQLException, nên giữ lỗi gốc và log lỗi rollback.

### Bài 40. Socket failure khi COMMIT có chứng minh DB chưa commit?

**Đáp án:** không. Đây có thể là unknown outcome; phải dùng idempotency/reconciliation.

### Bài 41. Idempotency key cần bảo vệ gì?

**Đáp án:** mỗi business request có key duy nhất/unique constraint, retry dùng cùng key và không lặp side effects; cần kiểm tra payload consistency.

### Bài 42. Retry `57014` do người dùng nhấn Cancel có hợp lý không?

**Đáp án:** thường không, vì trái ý định người dùng.

### Bài 43. Retry `40001` chỉ câu UPDATE cuối có đủ không?

**Đáp án:** thông thường phải retry **toàn transaction**, gồm phần tính quyết định nghiệp vụ.

### Bài 44. Vì sao bounded retries cần backoff/jitter?

**Đáp án:** tránh retry storm gây tăng tải và contention khi DB đang gặp sự cố.

### Bài 45. HTTP 504 có tự dừng query không?

**Đáp án:** không thể giả định; ứng dụng phải propagate cancellation hoặc server timeout phải giới hạn query.

### Bài 46. Socket timeout 12s có giữ HTTP deadline 8s không?

**Đáp án:** không. Cần application deadline/cancellation với remaining budget.

### Bài 47. TCP keepalive có thay statement_timeout không?

**Đáp án:** không. TCP keepalive kiểm tra network connection viability, không giới hạn query runtime.

### Bài 48. Hikari `maxLifetime` có bằng PostgreSQL transaction_timeout?

**Đáp án:** không. maxLifetime quản lý vòng đời connection trong pool, transaction_timeout là giới hạn server-side transaction từ PostgreSQL 17.

### Bài 49. PgBouncer transaction pooling ảnh hưởng SET session thế nào?

**Đáp án:** client session có thể không gắn cố định một backend giữa transactions; cần thiết kế state/SET/prepare phù hợp pooler config/version.

### Bài 50. Hãy lập một timeout budget cho HTTP API

**Đáp án gợi ý:** đặt HTTP deadline tổng; giới hạn pool checkout; giới hạn connect/login; đặt lock_timeout nhỏ hơn statement_timeout; thêm JDBC query timeout/cancel; dùng socketTimeout dài hơn ngưỡng query phù hợp làm transport backstop; truyền remaining budget và bảo đảm rollback/cleanup, quan sát SQLSTATE.

### Bài 51. Làm sao thử lock_timeout không cần phá database?

**Đáp án:** tạo bảng lab, mở hai connections; session A cập nhật một row trong BEGIN chưa commit; B đặt `SET LOCAL lock_timeout` rồi UPDATE cùng row; sau lỗi rollback B và rollback A.

### Bài 52. Một migration `ALTER TABLE` bị lock_timeout nên làm gì?

**Đáp án:** rollback nếu cần, điều tra blocker và lịch triển khai, tối ưu migration/lock acquisition rồi retry có kế hoạch; không tăng timeout vô hạn.

### Bài 53. `query_start` và `xact_start` khác nhau?

**Đáp án:** query_start là thời điểm query hiện tại/cuối bắt đầu theo session state, xact_start là thời điểm transaction bắt đầu. Không thay thế lẫn nhau.

### Bài 54. Metrics pool checkout timeout tăng nhưng SQL duration bình thường: điều tra gì?

**Đáp án:** leaks, transactions giữ connection, pool sizing, concurrency, physical connect failures và quá trình close/return.

### Bài 55. Nếu query bị cancel rồi app vẫn dùng transaction để COMMIT?

**Đáp án:** transaction có thể aborted; phải rollback/rollback-to-savepoint theo semantics. Không cố commit một transaction lỗi và coi dữ liệu đã đúng.

### Bài 56. Nếu driver báo `08xxx` sau INSERT, nên retry ngay?

**Đáp án:** phải xét auto-commit/commit boundary và idempotency; có thể unknown outcome, không retry ghi mù.

### Bài 57. Phân biệt slow query với lock wait?

**Đáp án:** xem `pg_stat_activity`, `wait_event_type`, `pg_blocking_pids`, query plan và metrics; cả hai đều làm tăng latency nhưng cách xử lý khác.

### Bài 58. Timeout nào phù hợp cho report nền 10 phút?

**Đáp án:** một cấu hình riêng có job deadline, server statement timeout, pool và monitoring phù hợp; không dùng nguyên timeout 5 giây của API tương tác.

### Bài 59. Vì sao dùng server statement_timeout như backstop?

**Đáp án:** giúp hủy câu SQL ở PostgreSQL khi client/proxy/app layer không còn giám sát đúng, trong scope đã cấu hình.

### Bài 60. Viết checklist xử lý lỗi “timeout” trước khi retry

**Đáp án gợi ý:**

1. Xác định timeout xảy ra ở HTTP, pool, connect, socket, JDBC, SQL, lock hay transaction.
2. Thu SQLSTATE và message từ nguồn đáng tin.
3. Xác định statement/transaction đã fail, aborted, completed hay outcome unknown.
4. Kiểm tra connection khỏe hay cần discard.
5. Rollback đúng scope nếu còn khả thi.
6. Kiểm tra authorization và idempotency trước khi retry.
7. Kiểm tra còn request deadline hay không.
8. Dùng bounded backoff/jitter nếu retry được phép.
9. Theo dõi pool/pg_stat_activity/lock blockers.
10. Ghi metric và runbook để xử lý root cause, không chỉ kéo dài timeout.

## 39. Ma trận quyết định nhanh

| Tình huống | Quan sát đầu tiên | Hành động ban đầu |
| --- | --- | --- |
| `getConnection()` timeout | Hikari pending/active | Tìm leak, transaction dài, pool pressure |
| PostgreSQL không nhận TCP connection | Driver connect error | DNS/port/TLS/auth/max_connections |
| Query quá lâu nhưng không chờ lock | pg_stat_activity, EXPLAIN | Query/index/statement_timeout |
| Query chờ lock | wait_event_type Lock, pg_blocking_pids | Tìm/giảm blocker, lock_timeout |
| JDBC timeout có `57014` | SQLSTATE và server logs | Rollback transaction, xem retry policy |
| Driver read/socket timeout | Socket/08xxx, network logs | Đánh giá connection broken/outcome |
| Backend idle in transaction | state/xact_start | Rollback/terminate theo runbook |
| Bị hủy theo yêu cầu user | Request cancellation event | Không tự retry |
| DB session bị terminate | Connection error/backend logs | Discard connection, reconnect |
| COMMIT response bị mất | Idempotency record | Reconcile, không retry blind |
| HTTP 504 nhưng DB query còn chạy | Backend active/application_name | Cancel/deadline propagation |
| Migration bị lock_timeout | Blockers, DDL lock needs | Plan retry/lịch bảo trì |
| Pool có stale connections sau idle | Network/proxy/pool metrics | Keepalive/validation/lifetime tuning |

## 40. Checklist triển khai production

| Kiểm tra | Kỳ vọng |
| --- | --- |
| Phân biệt pool checkout và physical connect? | Có metrics riêng |
| Có ứng dụng-level request deadline? | Có |
| Có propagate cancel khi request kết thúc? | Có chính sách rõ |
| Có statement_timeout ở PostgreSQL? | Theo workload |
| Có lock_timeout hợp lý? | Thấp hơn statement timeout khi cần |
| Có xử lý idle-in-transaction? | Timeout và transaction boundaries |
| Có cần PG17+ transaction_timeout? | Xác minh version |
| Có cấu hình pgJDBC đúng đơn vị? | Seconds đúng property |
| Có cấu hình Hikari đúng đơn vị? | Milliseconds |
| socketTimeout có là transport backstop? | Không thay statement timeout |
| Có cancelSignalTimeout hợp lý? | Không nhầm query timeout |
| Có TCP/pool keepalive? | Phù hợp network policies |
| Có PgBouncer/proxy? | Biết pooling mode/timeout layer |
| Có dùng SET LOCAL tránh rò session setting? | Khi thích hợp |
| Có role defaults cho API/migration khác nhau? | Có |
| Có Statement.setQueryTimeout? | Theo request budget |
| Có code gọi Statement.cancel an toàn? | Không chia sẻ Connection tùy ý |
| Có rollback sau SQLSTATE 57014 trong txn? | Có |
| Có discard broken connection? | Theo driver/pool contract |
| Có SQLSTATE-based error handling? | Không chỉ substring matching |
| Có idempotency cho ghi dữ liệu? | Có |
| Có policy xử lý unknown commit outcome? | Có |
| Có bounded retries/backoff/jitter? | Có |
| Có giới hạn concurrency? | Có |
| Có pg_stat_activity và blockers queries? | Có |
| Có monitoring idle transactions? | Có |
| Có logging query timeout/lock timeout? | Đúng privacy policy |
| Có connection/application_name? | Không chứa secrets |
| Có staging fault-injection tests? | Có |
| Có test failover/proxy idle? | Khi hạ tầng liên quan |
| Có test JDBC pool exhaustion? | Có |
| Có test cancellation race? | Có |
| Có dashboard query/lock/network latency? | Có |
| Có runbook hủy/terminate đúng PID? | Có và quyền giới hạn |
| Có review slow SQL plans? | `EXPLAIN ANALYZE BUFFERS` |
| Có review timeout trước migrations? | Có |
| Có giới hạn report/export jobs riêng? | Có |
| Có theo dõi retry amplification? | Có |
| Có cơ chế recovery khi DB bị lỗi? | Có |

## 41. Tổng kết

Khi PostgreSQL hoặc Java báo “timeout”, việc đầu tiên không phải tăng mọi ngưỡng lên gấp đôi; đó là **xác định chính xác timeout thuộc lớp nào và hậu quả ở server là gì**.

Những điều cần nhớ:

1. **Pool `connectionTimeout`** là thời gian chờ mượn connection, không phải SQL timeout.
2. **pgJDBC `connectTimeout`/`loginTimeout`** thuộc giai đoạn thiết lập physical connection.
3. **pgJDBC `socketTimeout`** giới hạn chờ network read, không bảo đảm server query đã bị hủy.
4. **JDBC `setQueryTimeout`** có thể phát yêu cầu cancel statement; `cancelSignalTimeout` điều khiển đường gửi yêu cầu cancel.
5. **PostgreSQL `statement_timeout`** là server-side giới hạn thời gian statement và có thể hủy query chờ lock.
6. **`lock_timeout`** chuyên giới hạn chờ lock acquisition; không giống deadlock detection.
7. **`idle_in_transaction_session_timeout`** bảo vệ khỏi connection bỏ quên transaction, có thể giải phóng locks bằng cách kết thúc backend.
8. **`idle_session_timeout`** có thể ảnh hưởng các pooled idle connections; cần phối hợp pool/network.
9. **`transaction_timeout` có trên PostgreSQL 17+**, giới hạn đời sống transaction thay vì chỉ từng statement.
10. **`SET LOCAL`** phù hợp với transaction-scoped timeout trong nhiều ứng dụng dùng pool.
11. **`Statement.cancel()` và `pg_cancel_backend`** yêu cầu hủy statement; **`pg_terminate_backend`** chấm dứt session.
12. **Cancel không phải một xác nhận lập tức**; phải xét race, error response và trạng thái backend.
13. **Lỗi query trong explicit transaction thường cần `ROLLBACK`**; nếu không, các lệnh sau có thể gặp `25P02`.
14. **Lỗi mạng/timeout quanh COMMIT có thể khiến outcome mơ hồ**. Dùng idempotency/reconciliation trước khi retry ghi dữ liệu.
15. **HTTP 504 không tự đảm bảo database query đã dừng**. Deadline/cancellation phải được truyền xuống database layer.
16. **Connection pool, PostgreSQL backend, OS và proxy có nhiều ngưỡng độc lập**. Phải thiết kế theo toàn đường request.
17. **SQLSTATE giúp phân loại nguyên nhân**: `57014`, `55P03`, `40P01`, `40001`, `08xxx`, `25P02`.
18. **`pg_stat_activity`, `pg_blocking_pids` và logs** là công cụ quan trọng để phân biệt query chậm với chờ lock/transaction idle.
19. **Retries phải bounded và idempotent**, có deadline và backoff; user cancel không nên tự động retry.
20. **Timeout là lớp bảo vệ, không thay query tuning hay transaction design**. Truy vấn có index phù hợp, locks ngắn và pool lifecycle tốt vẫn là nền tảng.

Mẫu ghi nhớ khi xử lý một request JDBC có transaction:

```text
1. Lấy connection từ pool với checkout deadline
2. Đảm bảo connect/network settings phù hợp
3. BEGIN / setAutoCommit(false)
4. SET LOCAL lock_timeout, statement_timeout khi cần
5. Execute prepared SQL với query deadline
6. Nếu cancel/error: xác định SQLSTATE, ROLLBACK
7. Nếu commit failure mất mạng: outcome UNKNOWN -> reconcile
8. Close statement/result set/connection
9. Retry chỉ khi idempotent, còn deadline và chính sách cho phép
```

**Quy tắc cuối cùng:** khi thấy chữ “timeout”, hãy hỏi: **“Ai đã hết thời gian — pool, driver, socket, PostgreSQL statement, lock hay transaction? Yêu cầu cancel đã đến server chưa? Connection/transaction hiện ở trạng thái nào? Nếu retry, có thể tạo tác dụng hai lần không?”**. Bốn câu hỏi đó giúp xây hệ thống PostgreSQL + Java có độ tin cậy cao hơn và xử lý sự cố nhanh hơn.
