# Kiểm thử mất kết nối, timeout, deadlock và tính an toàn khi retry

Ứng dụng dùng Oracle JDBC phải xử lý được những tình huống database hoặc network không phản hồi đúng như mong đợi. Connection có thể bị đứt giữa lúc gửi SQL, query có thể chạy lâu hơn timeout, transaction có thể chờ row lock, hai session có thể tạo deadlock và client có thể mất kết nối ngay trong lúc COMMIT.

Khó khăn lớn nhất không phải chỉ là bắt SQLException. Khi client nhận lỗi, trạng thái transaction ở database có thể đã khác với điều mà ứng dụng biết. Đặc biệt, nếu connection bị mất trong lúc COMMIT, ứng dụng có thể không biết transaction đã commit hay chưa. Retry mù quáng có thể tạo đơn hàng, thanh toán hoặc side effect trùng lặp.

Bài học này xây dựng cách kiểm thử có chủ đích cho các failure mode đó. Trọng tâm là tạo tình huống tái hiện được bằng nhiều session, phân biệt timeout ở từng tầng, xác định transaction outcome, thiết kế idempotency và retry toàn transaction một cách có giới hạn.

Sau bài học, bạn có thể:

- Phân biệt lỗi connect, lỗi đọc response, query timeout, lock wait timeout và transaction timeout.
- Kiểm thử mất kết nối ở các thời điểm khác nhau của một transaction.
- Giải thích ambiguous commit và cách xác minh transaction outcome.
- Tạo deadlock Oracle có kiểm soát bằng hai session.
- Phân biệt rollback statement với rollback toàn transaction.
- Phân loại lỗi có thể retry và lỗi cần sửa dữ liệu/cấu hình.
- Thiết kế idempotency key, unique constraint và transactional outbox.
- Dùng retry có giới hạn, exponential backoff và jitter.
- Xử lý connection hỏng trong JDBC connection pool.
- Viết integration test có thể lặp lại và thu thập bằng chứng.
- Đo RPO/RTO và xác nhận ứng dụng phục hồi đúng sau sự cố.

> Các lỗi Oracle, timeout property và failover behavior có thể khác theo Oracle Database release, Oracle JDBC driver, pool và topology RAC/Data Guard. Chạy fault injection trong database/schema lab cô lập. Không chủ động ngắt network, kill session hoặc làm đầy resource trên production để thử nghiệm.

## 1. Mô hình lỗi từ ứng dụng tới Oracle

### 1.1. Các tầng có thể phát sinh lỗi

Một request JDBC đi qua nhiều tầng:

```text
APPLICATION
    |
    v
JDBC CONNECTION POOL
    |
    v
ORACLE JDBC DRIVER
    |
    v
TCP / TLS / NETWORK
    |
    v
LISTENER / SERVICE
    |
    v
ORACLE SESSION
    |
    v
SQL EXECUTION / LOCK / TRANSACTION
    |
    v
REDO / COMMIT / STORAGE
```

Một exception ở tầng ứng dụng không nhất thiết cho biết lỗi bắt đầu ở đâu. Ví dụ:

- Connect timeout có thể xảy ra trước khi database session được tạo.
- Read timeout có thể xảy ra sau khi SQL đã được gửi và đang chạy.
- Socket bị reset có thể xảy ra trước, trong hoặc sau COMMIT.
- Query timeout có thể khiến driver gửi cancel request, nhưng cancel request cũng cần network hoạt động.
- Pool có thể trả về connection đã chết mà chưa phát hiện nếu validation policy không phù hợp.

### 1.2. Failure mode và câu hỏi cần trả lời

| Failure mode | Câu hỏi vận hành |
| --- | --- |
| Connect failure | Session có được tạo chưa? |
| Network disconnect | Server có nhận request chưa? |
| Read timeout | SQL còn chạy hay đã hoàn tất? |
| Query timeout | Statement bị cancel chưa? Transaction còn mở không? |
| Lock wait timeout | Session đang chờ lock nào? |
| Deadlock | Statement nào bị chọn làm victim? Transaction còn thay đổi nào chưa commit? |
| Commit response lost | Transaction đã commit hay chưa? |
| Database restart/failover | Connection cũ còn hợp lệ không? Transaction outcome ra sao? |

### 1.3. Lỗi có thể retry và trạng thái không xác định

Một lỗi xảy ra trước khi gửi request thường có thể retry an toàn hơn vì database chưa thực hiện thao tác. Nhưng nếu lỗi xảy ra sau khi request được gửi, client có thể không biết server đã xử lý tới đâu.

Phân loại cần dựa trên operation và thời điểm:

- **Definitely not sent:** có bằng chứng request chưa được gửi tới database.
- **Sent, outcome known failed:** database trả lỗi xác định và transaction/statement semantics cho biết thao tác thất bại.
- **Sent, outcome unknown:** client mất response, nhất là trong COMMIT.
- **Succeeded and acknowledged:** client nhận xác nhận thành công.

Không suy ra “rollback” chỉ từ việc JDBC ném SQLException hoặc connection đã đóng.

## 2. Transaction và commit outcome

### 2.1. Auto-commit

JDBC connection thường mặc định auto-commit. Khi auto-commit bật, mỗi statement được commit như một transaction riêng khi thực thi thành công theo JDBC semantics.

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(true);

    try (PreparedStatement ps = connection.prepareStatement(
            "UPDATE account SET status = ? WHERE account_id = ?")) {
        ps.setString(1, "ACTIVE");
        ps.setLong(2, accountId);
        int rows = ps.executeUpdate();
    }
}
```

Nếu connection mất trong lúc execute, client có thể không nhận được update count dù server đã thực hiện statement. Với auto-commit, transaction boundary gắn với statement nên vẫn có thể có kết quả không rõ ở phía client.

### 2.2. Explicit transaction

Khi cần nhiều DML atomic, tắt auto-commit và tự quản lý commit/rollback:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        debit(connection, fromAccount, amount);
        credit(connection, toAccount, amount);
        insertTransferAudit(connection, requestId);
        connection.commit();
    } catch (SQLException | RuntimeException e) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            e.addSuppressed(rollbackError);
        }
        throw e;
    }
}
```

Đoạn code trên thể hiện transaction boundary cơ bản. Nếu lỗi là network disconnect, rollback qua connection đã hỏng có thể thất bại; rollback thất bại không chứng minh server chưa rollback hoặc đã commit. Khi connection mất, database sẽ xử lý session/transaction theo trạng thái server và failure detection.

### 2.3. COMMIT có hai phía

Commit gồm thao tác server commit và phản hồi về client:

```text
CLIENT                         ORACLE
  |                              |
  |----------- COMMIT ---------->|
  |                              | Commit transaction
  |                              | Persist commit record
  |<--------- SUCCESS -----------|
  |                              |
```

Nếu connection đứt sau khi server commit nhưng trước khi response tới client, database đã commit nhưng ứng dụng thấy exception.

### 2.4. Ambiguous commit

Đây là trường hợp commit outcome không xác định từ góc nhìn client. Ví dụ:

```text
CLIENT                         ORACLE
  |                              |
  |----------- COMMIT ---------->|
  |                              | Commit thành công
  |          X NETWORK CUT        |
  |                              |
  |---- SQLException / timeout   |
  |                              |
  | Client không biết commit     |
  | đã hoàn tất hay chưa         |
```

Không được mặc định retry toàn bộ business operation với một request ID mới. Nếu transaction đầu đã commit, lần retry có thể tạo side effect lần hai.

### 2.5. Xác minh outcome sau reconnect

Thiết kế transaction để ghi một request identifier duy nhất cùng thay đổi nghiệp vụ. Sau khi reconnect, tra cứu request ID:

- Có record đã commit: trả lại kết quả đã lưu.
- Không có record: request có thể chưa commit hoặc transaction cũ chưa kết thúc; retry với cùng request ID để unique constraint phân xử, hoặc chờ/reconcile theo protocol.
- Có trạng thái đang xử lý: kiểm tra owner/lease và xử lý theo state machine có giới hạn.

Một truy vấn không tìm thấy record ngay lập tức không phải bằng chứng tuyệt đối rằng transaction cũ chắc chắn không commit; request cũ có thể vẫn đang xử lý.

## 3. Idempotency và retry an toàn

### 3.1. Idempotent operation

Một thao tác idempotent có thể được thực hiện lặp lại với cùng identity mà kết quả nghiệp vụ cuối cùng vẫn như một lần thực hiện. HTTP PUT là ví dụ khái niệm; trong database, idempotency cần được thiết kế bằng khóa duy nhất và transaction.

Ví dụ client gửi request tạo payment với request_id cố định. Mọi retry của cùng một yêu cầu phải dùng cùng request_id.

### 3.2. Bảng deduplication

```sql
CREATE TABLE request_dedup (
    request_id      VARCHAR2(64) PRIMARY KEY,
    request_hash    VARCHAR2(64) NOT NULL,
    result_code     VARCHAR2(30),
    result_payload  CLOB,
    created_at      TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);
```

request_id định danh yêu cầu. request_hash giúp phát hiện client dùng lại cùng key cho một payload khác. Không chỉ lưu key mà bỏ qua việc xác nhận nội dung request.

### 3.3. Atomicity giữa dedup record và business DML

Dedup record và business data phải commit trong cùng một database transaction:

```java
connection.setAutoCommit(false);
try {
    insertRequestKey(connection, requestId, requestHash);
    createOrder(connection, order);
    String result = buildResult(order);
    saveRequestResult(connection, requestId, result);
    connection.commit();
    return result;
} catch (SQLException e) {
    rollbackQuietly(connection, e);
    throw e;
}
```

Nếu transaction rollback, cả request key lẫn business DML rollback. Nếu commit thành công nhưng response bị mất, request key và kết quả đã lưu vẫn tồn tại để lần retry tra cứu.

### 3.4. Xử lý duplicate request

Khi insert request_id gặp unique constraint violation (ORA-00001), ứng dụng không nên trả lỗi chung. Nó phải đọc record hiện có:

1. So sánh request_hash.
2. Nếu hash khác, từ chối vì cùng key được dùng cho payload khác.
3. Nếu hash giống và kết quả đã hoàn tất, trả lại kết quả đã lưu.
4. Nếu state còn pending, chờ/reconcile theo protocol; không chạy lại business DML song song.

Trong mô hình transaction đơn giản, request row và kết quả cùng commit nên client chỉ nhìn thấy row sau khi business DML commit. Nếu thiết kế workflow nhiều transaction, cần state machine/lease/owner và recovery policy rõ.

### 3.5. Cạnh tranh cùng request_id

Hai request đồng thời cùng request_id sẽ tranh chấp unique key. Oracle unique constraint đảm bảo không có hai row đã commit cùng key. Một transaction có thể chờ transaction kia commit/rollback; sau đó insert sẽ thành công hoặc nhận ORA-00001.

Khi xử lý ORA-00001, chỉ coi là duplicate request nếu constraint vi phạm đúng là khóa idempotency. Không bắt mọi unique violation rồi trả kết quả cũ; lỗi có thể đến từ business key khác.

### 3.6. Transactional outbox

Nếu business transaction còn cần gửi email, publish message hoặc gọi payment provider, không gọi service ngoài trong lúc giữ database transaction lâu. Ghi outbox event trong cùng transaction với business data:

```sql
CREATE TABLE outbox_event (
    event_id       VARCHAR2(64) PRIMARY KEY,
    aggregate_id   VARCHAR2(64) NOT NULL,
    event_type     VARCHAR2(100) NOT NULL,
    payload        CLOB NOT NULL,
    created_at     TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    published_at   TIMESTAMP
);
```

Worker đọc outbox và publish theo retry policy. Consumer cũng phải idempotent vì message delivery thường có thể lặp. Outbox giúp tránh tình huống database commit thành công nhưng process chết trước khi gửi message.

### 3.7. Không retry side effect bên ngoài một cách mù quáng

Nếu client gọi payment API, gửi email hoặc publish event rồi mất response, side effect ngoài database cũng có thể có outcome không xác định. Dùng provider idempotency key, transactional outbox, inbox/dedup ở consumer hoặc reconciliation API. Database request_id không tự động làm service bên ngoài idempotent.

## 4. Các loại timeout và phạm vi tác động

### 4.1. Connect timeout

Connect timeout giới hạn thời gian thiết lập network/database connection. Nó thường xảy ra trước khi ứng dụng có connection usable và trước khi transaction business được gửi trên connection đó.

Trong Oracle JDBC Thin, các thuộc tính thường gặp gồm:

- oracle.net.CONNECT_TIMEOUT: thời gian chờ kết nối tới endpoint theo đơn vị mà driver/release quy định.
- oracle.net.OUTBOUND_CONNECT_TIMEOUT: timeout kết nối outbound theo Oracle Net.

Đơn vị và cách precedence giữa URL, connection properties, DESCRIPTION/ADDRESS và pool phải được xác nhận theo driver/Oracle Net version. Không giả định timeout đặt ở pool thay thế timeout của Oracle Net.

### 4.2. Read/socket timeout

Read timeout giới hạn thời gian chờ dữ liệu từ socket sau khi kết nối đã được thiết lập. Oracle JDBC Thin thường cung cấp thuộc tính oracle.jdbc.ReadTimeout tính bằng milliseconds trong các driver hỗ trợ.

Read timeout có thể xảy ra trong lúc query đang chạy hoặc khi chờ response. Nó không tự chứng minh server đã dừng SQL hay rollback transaction. Sau lỗi đọc socket, connection thường phải được xem là không đáng tin cậy và loại khỏi pool.

### 4.3. Statement query timeout

JDBC Statement.setQueryTimeout nhận số giây:

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT * FROM large_table WHERE status = ?")) {
    ps.setString(1, "PENDING");
    ps.setQueryTimeout(10);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // process rows
        }
    }
}
```

Khi quá thời gian, driver cố hủy statement và thường ném SQLException. Đây là request cancel từ JDBC; nó không phải deadline end-to-end cho toàn bộ request và không tự động rollback transaction chứa các statement trước đó.

### 4.4. Lock wait timeout

Lock wait timeout giới hạn thời gian một statement chờ resource lock. Oracle hỗ trợ cú pháp như SELECT FOR UPDATE WAIT n và NOWAIT:

```sql
SELECT *
FROM inventory
WHERE item_id = :item_id
FOR UPDATE WAIT 5;

SELECT *
FROM inventory
WHERE item_id = :item_id
FOR UPDATE NOWAIT;
```

WAIT 5 giới hạn chờ lock theo số giây; NOWAIT báo lỗi ngay nếu không lấy được lock. Các DML update/delete có thể chờ row lock theo behavior mặc định, trừ khi transaction/SQL kết thúc hoặc bị cancel.

### 4.5. DDL lock timeout

DDL có thể chờ lock object. Oracle cung cấp DDL_LOCK_TIMEOUT trong các release hỗ trợ để đặt thời gian chờ DDL lock. Nó không phải timeout tổng quát cho DML/query:

```sql
ALTER SESSION SET DDL_LOCK_TIMEOUT = 10;
```

Kiểm tra quyền, release và phạm vi session/system trước khi áp dụng.

### 4.6. Transaction timeout ở application layer

JDBC không có một transaction timeout portable duy nhất đảm bảo server tự rollback mọi transaction khi hết thời gian. Framework có thể quản lý deadline và yêu cầu statement cancel/rollback, nhưng network có thể đã mất và server outcome cần được xử lý riêng.

Đặt deadline ở request layer, truyền remaining budget xuống pool/statement/service, nhưng vẫn cần server-side lock/query controls và transaction cleanup.

### 4.7. Timeout không đồng nghĩa với cancel thành công

Khi client timeout, cancel request có thể bị mất do network partition. Server có thể tiếp tục chạy cho tới khi session bị phát hiện chết hoặc statement tự kết thúc. Vì vậy:

- Theo dõi session và SQL ở server trong lab.
- Đo thời gian từ client timeout tới server dừng.
- Kiểm tra transaction/locks sau timeout.
- Không trả connection lỗi về pool.

### 4.8. Kết hợp timeout theo thứ tự

Thiết kế timeout theo deadline tổng thể. Ví dụ, pool acquisition 2 giây, connect 3 giây, statement 8 giây và request deadline 12 giây là một minh họa; cần cộng thêm thời gian rollback/cleanup/serialization và network jitter. Không đặt timeout từng tầng dài hơn deadline request nếu tầng trên cần phản hồi sớm.

## 5. Cấu hình timeout cho Oracle JDBC

### 5.1. Thin driver properties

Ví dụ properties cho Oracle JDBC Thin:

```java
Properties properties = new Properties();
properties.setProperty("user", dbUser);
properties.setProperty("password", dbPassword);
properties.setProperty("oracle.net.CONNECT_TIMEOUT", "5000");
properties.setProperty("oracle.jdbc.ReadTimeout", "15000");

Connection connection =
    DriverManager.getConnection(jdbcUrl, properties);
```

Đây là ví dụ minh họa; xác nhận đơn vị và property name trong Oracle JDBC guide của driver đang dùng. Không ghi password vào log hoặc source control.

### 5.2. JDBC URL

Một số Oracle Net timeout có thể được cấu hình trong connect descriptor:

```text
jdbc:oracle:thin:@(DESCRIPTION=
  (CONNECT_TIMEOUT=5)
  (TRANSPORT_CONNECT_TIMEOUT=3)
  (ADDRESS=(PROTOCOL=TCP)(HOST=db.example)(PORT=1521))
  (CONNECT_DATA=(SERVICE_NAME=APP_SERVICE))
)
```

Các descriptor attribute có syntax và unit riêng. Không trộn giá trị giây với property milliseconds. Dùng descriptor chính thức theo release và kiểm thử cả multi-address/failover connect.

### 5.3. setQueryTimeout

Query timeout là thuộc tính statement:

```java
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setQueryTimeout(5);
    // bind parameters
    ps.executeUpdate();
}
```

Timeout được tính theo giây, không phải milliseconds. Không dùng giá trị 5000 với ý định 5 giây.

### 5.4. setNetworkTimeout

JDBC Connection có setNetworkTimeout(Executor, milliseconds) trong JDBC 4.1. Driver phải hỗ trợ. Khi timeout, driver có thể abort connection; hành vi phụ thuộc driver:

```java
Executor executor = Executors.newFixedThreadPool(1);
connection.setNetworkTimeout(executor, 15_000);
```

Quản lý Executor lifecycle và không chia sẻ executor bị shutdown giữa các connection. Kiểm tra driver implementation; network timeout không thay thế Oracle Net connect timeout hoặc application deadline.

### 5.5. Pool acquisition timeout

Connection pool thường có giới hạn chờ lấy connection, ví dụ maximum wait. Timeout ở đây nghĩa pool không cấp được connection trong thời gian cho phép; nó không phải query timeout và không nói gì về database execution.

Theo dõi pool active/idle/pending, acquisition latency, leak detection và validation failures. Khi pool cạn do connection bị giữ bởi request chờ lock, tăng pool size có thể chỉ làm tăng tải/lock contention.

### 5.6. Validation timeout

Connection.isValid(timeout) và pool validation query có thể dùng để phát hiện connection không còn sống. Validation timeout là thời gian dành cho health check; một lần validation thành công không bảo đảm connection sẽ sống tới lần execute kế tiếp.

### 5.7. Oracle Net keepalive và dead connection detection

TCP keepalive/Oracle Net dead connection detection giúp phát hiện kết nối chết trong một số failure mode, đặc biệt khi network partition không gửi FIN/RST. Detection có thể mất thời gian và phụ thuộc OS/network/Oracle Net settings. Đừng coi keepalive là request timeout.

### 5.8. Timeout matrix

| Timeout | Đơn vị thường gặp | Bảo vệ phần nào? | Khi hết hạn |
| --- | --- | --- | --- |
| Pool acquisition | giây | Chờ connection từ pool | Pool không cấp connection |
| Oracle Net connect | phụ thuộc property/descriptor | Thiết lập TCP/service connection | Connect attempt thất bại |
| JDBC ReadTimeout | milliseconds trong Oracle JDBC Thin | Chờ socket response | Driver ném lỗi đọc/timeout; connection có thể hỏng |
| Statement.setQueryTimeout | giây | Thực thi statement | Driver cố cancel statement |
| SELECT FOR UPDATE WAIT | giây | Chờ row lock của statement | Oracle báo resource busy/lock timeout |
| Connection.setNetworkTimeout | milliseconds | Network operation trên connection | Driver có thể abort connection |
| Application deadline | ứng dụng tự định nghĩa | Toàn bộ request/workflow | Application dừng chờ và xử lý compensation/outcome |

Không cộng các timeout một cách máy móc; một timeout có thể bao phủ hoặc kích hoạt timeout khác tùy driver/pool.

## 6. Kiểm thử mất kết nối theo thời điểm

### 6.1. Ma trận fault injection

Kiểm thử disconnect phải xác định fault được đưa vào ở đâu:

| Điểm ngắt | Server có thể đã nhận request? | Kết quả client |
| --- | --- | --- |
| Trước khi gửi SQL | Thường chưa | Connect/write error |
| Sau khi gửi SQL, trước khi server hoàn tất | Có | Read timeout/reset; statement có thể còn chạy |
| Sau DML, trước COMMIT | Có | Session/transaction có thể còn tồn tại cho tới khi server phát hiện disconnect |
| Trong COMMIT | Có | Outcome có thể không xác định |
| Sau server commit, trước response | Có, đã commit | Client thấy exception nhưng transaction đã commit |
| Sau khi client nhận success | Đã commit theo response | Request thành công; reconnect không cần retry |

Fault injection nên dùng proxy/network tool hoặc harness riêng để ngắt kết nối có kiểm soát và ghi timestamp hai phía.

### 6.2. Test trước khi gửi request

Ngăn kết nối trước khi execute statement. Xác nhận ứng dụng không báo business success, connection không được reuse và retry chỉ tạo một business operation. Đây là test connect/transport establishment.

### 6.3. Test sau khi server nhận DML

Trong transaction explicit, chạy DML rồi ngắt network trước commit. Sau đó kiểm tra server session/transaction trong lab. Khi session bị đóng và transaction rollback, dữ liệu không còn; nhưng thời gian server phát hiện dead connection phụ thuộc network detection.

### 6.4. Test trong COMMIT

Đây là test quan trọng nhất cho ambiguous outcome. Tạo một transaction có request_id, dùng proxy để drop response trong cửa sổ commit và quan sát:

- Client nhận SQLException/timeout.
- Database có row dedup/business record hay không.
- Retry cùng request_id có tạo duplicate không.
- Ứng dụng trả kết quả cũ hay chạy lại business DML.

Không dựa vào sleep cố định để giả định chính xác commit window. Dùng proxy/test hook có thể chặn chiều response sau khi request COMMIT được gửi, hoặc instrument server/client timestamps.

### 6.5. Test sau commit

Commit thành công, nhận success, sau đó đóng connection. Xác nhận reconnect và đọc record vẫn thấy dữ liệu. Đây là baseline đối chứng với ambiguous commit.

### 6.6. Network blackhole và TCP reset

Hai kiểu fault khác nhau:

- TCP reset/connection refused thường được phát hiện nhanh.
- Blackhole/drop packet có thể khiến client chờ tới socket/read timeout hoặc TCP retransmission timeout.

Test cả hai vì behavior timeout và thời gian recovery khác nhau.

### 6.7. Database session kill

Trong lab, DBA có thể kết thúc session để kiểm tra client nhận lỗi:

```sql
ALTER SYSTEM KILL SESSION 'sid,serial#' IMMEDIATE;
```

Lệnh minh họa; xác định đúng SID/SERIAL# và instance trong RAC. Session kill không mô phỏng đầy đủ network disconnect hoặc lost commit response. Transaction đang chạy thường cần rollback/cleanup theo Oracle session termination.

### 6.8. Database shutdown/restart

Có thể test restart instance trong môi trường riêng để quan sát connection invalidation, recovery và pool reconnect. Dùng shutdown mode theo scenario lab; không dùng ABORT trên shared/production để tạo lỗi thử nghiệm.

### 6.9. Assertions cho disconnect test

Mỗi test cần xác nhận:

- Client exception type/vendor code/SQLState.
- Connection bị đánh dấu unusable và không quay lại pool.
- Server transaction outcome sau reconnect.
- Không có business row duplicate.
- Request ID vẫn giữ nguyên qua retry.
- Metrics/log có đủ timestamp để phân tích.

## 7. Kiểm thử query timeout và lock timeout

### 7.1. Query timeout bằng JDBC

Tạo một statement có thể chạy lâu trong lab rồi đặt setQueryTimeout. Một cách dùng PL/SQL sleep cần quyền EXECUTE DBMS_LOCK:

```java
try (CallableStatement cs = connection.prepareCall(
        "BEGIN DBMS_LOCK.SLEEP(?); END;")) {
    cs.setInt(1, 30);
    cs.setQueryTimeout(5);
    cs.execute();
}
```

Nếu DBMS_LOCK không được cấp quyền, dùng một truy vấn lab có workload đủ dài và có giới hạn resource. Không cấp quyền DBMS_LOCK rộng cho ứng dụng production chỉ để test.

### 7.2. Xác minh server-side cancel

Sau khi client nhận query timeout, kiểm tra session và SQL trên database lab. Xác nhận statement dừng trong thời gian mong muốn, lock được giải phóng và transaction còn lại ở trạng thái nào.

### 7.3. SELECT FOR UPDATE NOWAIT

Session A giữ row lock:

```sql
UPDATE inventory
SET quantity = quantity - 1
WHERE item_id = 100;
-- Chưa COMMIT
```

Session B:

```sql
SELECT *
FROM inventory
WHERE item_id = 100
FOR UPDATE NOWAIT;
```

Session B phải nhận lỗi resource busy ngay nếu Session A còn giữ lock. Rollback Session A sau test.

### 7.4. SELECT FOR UPDATE WAIT

Thay NOWAIT bằng WAIT 3 để kiểm tra timeout lock:

```sql
SELECT *
FROM inventory
WHERE item_id = 100
FOR UPDATE WAIT 3;
```

Giữ lock ở session A lâu hơn 3 giây và xác nhận session B kết thúc bằng lỗi lock timeout tương ứng. Error code có thể khác theo SQL form/release; assert vendor code và scenario, không phụ thuộc message text.

### 7.5. DML lock wait

Session A:

```sql
UPDATE inventory
SET quantity = quantity + 1
WHERE item_id = 100;
-- Chưa COMMIT
```

Session B chạy UPDATE cùng row và quan sát wait. DML không có cú pháp WAIT phổ quát giống SELECT FOR UPDATE; dùng statement timeout/application deadline hoặc kiểm soát transaction blocker trong lab.

### 7.6. Cleanup

Luôn rollback Session A, đóng session B và xác nhận row value ban đầu. Nếu test bị fail giữa chừng, dùng finally/cleanup hook để không để lock treo làm hỏng các test sau.

## 8. Kiểm thử deadlock

### 8.1. Deadlock là gì?

Deadlock xảy ra khi các transaction giữ resource mà transaction khác cần, tạo thành chu trình chờ. Oracle phát hiện deadlock và chọn một statement làm victim để phá chu trình. Ứng dụng thường nhận ORA-00060.

Deadlock khác lock wait kéo dài:

- Lock wait: một session chờ session khác; không có chu trình.
- Deadlock: có chu trình phụ thuộc; Oracle phát hiện và phá chu trình.

### 8.2. Tạo bảng lab

```sql
CREATE TABLE deadlock_lab (
    id NUMBER PRIMARY KEY,
    value_text VARCHAR2(30)
);

INSERT INTO deadlock_lab VALUES (1, 'A');
INSERT INTO deadlock_lab VALUES (2, 'B');
COMMIT;
```

### 8.3. Kịch bản hai session

Mở hai SQL*Plus session hoặc hai JDBC connections riêng.

Session A:

```sql
UPDATE deadlock_lab
SET value_text = 'A1'
WHERE id = 1;
-- Giữ transaction mở
```

Session B:

```sql
UPDATE deadlock_lab
SET value_text = 'B2'
WHERE id = 2;
-- Giữ transaction mở
```

Sau đó Session A:

```sql
UPDATE deadlock_lab
SET value_text = 'A2'
WHERE id = 2;
-- Chờ Session B
```

Trong lúc A đang chờ, Session B:

```sql
UPDATE deadlock_lab
SET value_text = 'B1'
WHERE id = 1;
```

Session B cần row 1 do A đang giữ; A cần row 2 do B đang giữ. Oracle phát hiện cycle và trả ORA-00060 cho một statement/transaction victim.

### 8.4. Không giả định session nào luôn là victim

Victim được Oracle chọn theo deadlock detection; thứ tự scheduling và execution có thể làm session A hoặc B nhận lỗi. Test phải chấp nhận một trong hai, nhưng xác nhận deadlock được phát hiện và cycle bị phá.

### 8.5. Statement rollback và transaction rollback

Khi Oracle phát hiện deadlock, statement được chọn làm victim bị rollback để phá chu trình. Các statement trước đó trong cùng transaction có thể vẫn còn pending. Ứng dụng nên rollback toàn bộ transaction business rồi retry transaction từ đầu nếu operation có thể retry an toàn.

Không giả định ORA-00060 tự động rollback tất cả DML trước đó của transaction.

### 8.6. Xác nhận bằng alert/trace

Oracle có thể ghi deadlock graph vào trace/diagnostic destination và alert log. Graph cho biết resource, session và SQL liên quan. DBA dùng graph để xác định thứ tự lock và thiết kế lại transaction/access order.

### 8.7. Xem blocking session

Trong lab, xem session/blocker:

```sql
SELECT
    sid,
    serial#,
    username,
    status,
    blocking_session,
    event,
    seconds_in_wait,
    sql_id
FROM v$session
WHERE username IS NOT NULL
ORDER BY blocking_session NULLS FIRST, sid;
```

V$SESSION cho thấy blocker/waiter tại thời điểm truy vấn; deadlock graph/trace thường có chi tiết hơn cho chu trình đã phát hiện.

### 8.8. Cleanup deadlock lab

Sau khi một session nhận ORA-00060, rollback cả hai session và xác nhận giá trị ban đầu:

```sql
ROLLBACK;
SELECT * FROM deadlock_lab ORDER BY id;
```

Nếu test tự động, mỗi connection phải được rollback/close trong finally. Không để transaction còn pending sang test kế tiếp.

## 9. Thiết kế để giảm deadlock

### 9.1. Thứ tự truy cập nhất quán

Nếu mọi transaction lock nhiều account/item, hãy truy cập theo cùng một thứ tự khóa, ví dụ account_id tăng dần. Điều này giảm khả năng hai transaction giữ resource theo thứ tự ngược nhau.

Ví dụ:

```java
List<Long> ids = List.of(firstAccountId, secondAccountId)
    .stream()
    .sorted()
    .toList();

for (Long id : ids) {
    lockAccount(connection, id);
}
```

Đây là nguyên tắc; cần đảm bảo SQL/locking thực tế cũng tuân theo thứ tự đã định, kể cả foreign key, trigger và index maintenance.

### 9.2. Giữ transaction ngắn

Không gọi REST API, chờ user input, xử lý file lớn hoặc sleep khi đang giữ row lock. Tách chuẩn bị dữ liệu khỏi transaction; chỉ giữ transaction trong khoảng cần thiết để kiểm tra và ghi dữ liệu atomic.

### 9.3. Lock theo tập dữ liệu nhỏ

Dùng predicate/index phù hợp để tránh lock nhiều row ngoài dự kiến. Kiểm tra execution plan và row count thực tế. Một UPDATE không có index trên predicate có thể scan rộng và tăng contention.

### 9.4. Tránh read-then-write race

Mẫu SELECT số dư rồi UPDATE sau có thể race. Có thể dùng conditional UPDATE atomic:

```sql
UPDATE account
SET balance = balance - :amount
WHERE account_id = :id
  AND balance >= :amount;
```

Kiểm tra update count để xác định đủ điều kiện. Điều này giảm khoảng thời gian giữa read và write, nhưng vẫn cần transaction và business validation.

### 9.5. Foreign key và index

DML trên parent/child table có thể tương tác lock qua foreign key. Đảm bảo index foreign key khi phù hợp với workload để giảm locking/scan rộng. Phân tích deadlock graph trước khi thay index.

### 9.6. Deadlock không phải luôn là bug Oracle

ORA-00060 thường phản ánh thứ tự khóa/transaction concurrency của workload. DBA cần graph để xác định SQL/resource; developer cần sửa transaction access order hoặc chia workload. Tăng timeout không giải quyết deadlock vì chu trình cần bị phá.

## 10. Retry policy cho Oracle JDBC

### 10.1. Retry phải có điều kiện

Chỉ retry khi:

- Lỗi được phân loại là transient/recoverable trong ngữ cảnh cụ thể.
- Business operation idempotent hoặc có idempotency key.
- Transaction cũ đã rollback/được xác minh outcome.
- Còn thời gian trong request deadline.
- Số lần retry chưa vượt giới hạn.
- Backoff không làm tăng tải trong outage.

### 10.2. Phân loại lỗi

| Lỗi/triệu chứng | Cách xử lý thường gặp | Lưu ý |
| --- | --- | --- |
| ORA-00060 deadlock | Rollback transaction rồi retry toàn unit nếu an toàn | Giảm deadlock bằng lock order; không retry statement đơn lẻ |
| ORA-08177 serialization failure | Rollback và retry transaction | Phổ biến với SERIALIZABLE; phải replay toàn transaction |
| ORA-00054 resource busy NOWAIT | Retry có giới hạn hoặc báo conflict | Phụ thuộc business semantics |
| ORA-30006 lock wait timeout | Rollback/đánh giá retry | Xác định blocker và deadline |
| ORA-01013 user requested cancel | Không retry tự động mặc định | Có thể do query timeout/cancel; transaction cần cleanup |
| ORA-01722 invalid number | Không retry cùng input | Lỗi dữ liệu/type conversion |
| ORA-01861 date format mismatch | Không retry cùng input | Sửa mapping/format |
| ORA-00001 unique constraint | Tra cứu duplicate/idempotency | Chỉ coi là duplicate request nếu đúng constraint |
| ORA-03113/03114/03135 | Connection mất; outcome có thể chưa rõ | Reconnect, xác minh idempotency/commit |
| ORA-12541 no listener | Retry có backoff khi service dự kiến phục hồi | Có thể là cấu hình/service outage |
| ORA-12170/12535 timeout | Retry connect theo deadline/circuit breaker | Xác định connect hay read stage |
| ORA-12514 service unknown | Thường cần xử lý service registration/config | Không retry liên tục như transient network |

Đây là hướng xử lý phổ biến, không phải quy tắc tự động cho mọi operation. Phân loại theo SQLState, Oracle vendor code, exception class, transaction state và application context.

### 10.3. Retry toàn transaction

Với deadlock hoặc serialization failure, retry unit transaction từ đầu:

1. Rollback transaction hiện tại.
2. Đóng/loại bỏ connection nếu connection lỗi.
3. Chờ backoff.
4. Lấy connection hợp lệ mới nếu cần.
5. Bắt đầu transaction mới.
6. Thực thi lại toàn bộ business unit bằng cùng idempotency key.
7. Commit và trả kết quả.

Không chỉ lặp lại câu UPDATE cuối nếu các statement trước đó là một phần logic atomic.

### 10.4. Exponential backoff

Backoff tăng dần khoảng chờ sau mỗi lần retry để tránh nhiều client cùng retry đồng thời:

```text
attempt 1: 100 ms
attempt 2: 200 ms
attempt 3: 400 ms
attempt 4: 800 ms
```

Giá trị chỉ minh họa. Thêm jitter ngẫu nhiên và giới hạn max delay. Backoff phải nằm trong request deadline.

### 10.5. Jitter

Nếu mọi client retry đúng cùng thời điểm, database có thể nhận một đợt retry spike (thundering herd). Jitter phân tán retry time trong một khoảng. Full jitter thường chọn random delay từ 0 tới exponential cap; equal jitter hoặc decorrelated jitter là các biến thể khác.

### 10.6. Giới hạn retry

Đặt max attempts và max elapsed time. Ví dụ 3 lần retry hoặc tổng 2 giây là policy minh họa, không phải giá trị phổ quát. Một request không được retry vô hạn hoặc vượt deadline người dùng.

### 10.7. Circuit breaker

Nếu connect/service failure tăng mạnh, circuit breaker có thể tạm ngừng request mới tới database/service và cho phép thử lại sau cooldown. Nó bảo vệ pool và database khỏi retry storm. Circuit breaker không xác định transaction outcome; ambiguous commit vẫn cần idempotency.

### 10.8. Không retry ở nhiều tầng cùng lúc

Nếu DAO retry 3 lần, service retry 3 lần và HTTP client retry 3 lần, một request có thể nhân lên 27 attempts. Chọn một tầng sở hữu retry policy cho business operation; tầng thấp hơn chỉ phân loại/throw lỗi hoặc retry connection establishment rất hẹp.

## 11. Exception handling trong JDBC

### 11.1. SQLState và vendor code

SQLException cung cấp:

- getSQLState()
- getErrorCode() — vendor-specific code, Oracle thường trả ORA code number.
- getNextException()
- getCause()

Không chỉ parse message string vì message có thể đổi theo NLS/driver version.

### 11.2. Ví dụ phân loại Oracle error code

```java
static int oracleCode(SQLException e) {
    return e.getErrorCode();
}

static boolean isDeadlock(SQLException e) {
    return e.getErrorCode() == 60;
}

static boolean isSerializationFailure(SQLException e) {
    return e.getErrorCode() == 8177;
}
```

Trong thực tế, duyệt cả chained exceptions và cause chain. Driver/pool có thể bọc exception; không chỉ kiểm tra exception ngoài cùng.

### 11.3. SQLTransientException và SQLRecoverableException

JDBC có exception subclasses để phân loại lỗi transient/recoverable. Driver không nhất thiết map mọi Oracle error vào subclass tương ứng. Dùng cả SQLState/vendor code và behavior thực tế; không dựa vào instanceof duy nhất.

### 11.4. Chained SQLException

```java
static void logSqlExceptions(SQLException error) {
    for (SQLException e = error; e != null; e = e.getNextException()) {
        log.error("SQLState={}, vendorCode={}, message={}",
            e.getSQLState(), e.getErrorCode(), e.getMessage());
    }
}
```

Không log bind value nhạy cảm trong exception diagnostics.

### 11.5. Commit exception

Nếu commit() ném exception do connection failure, đánh dấu outcome UNKNOWN cho business operation. Đừng gọi rollback rồi trả “thất bại chắc chắn” nếu rollback không thể xác nhận. Reconnect và tra cứu request_id qua idempotency protocol.

### 11.6. Rollback exception

Nếu rollback() cũng lỗi, lưu cả lỗi gốc và lỗi rollback dưới dạng suppressed/cause. Loại connection khỏi pool và không tái sử dụng. Server có thể tự rollback khi session kết thúc, nhưng ứng dụng phải xác minh business state bằng request ID.

### 11.7. Connection.isClosed và isValid

isClosed chỉ cho biết client-side Connection đã được đóng theo JDBC object; nó không đảm bảo socket/server session còn sống nếu false. isValid(timeout) gửi validation theo driver implementation, nhưng connection vẫn có thể mất ngay sau validation. Dùng pool validation/recycle và xử lý lỗi execute thực tế.

## 12. Connection pool và connection hỏng

### 12.1. Connection không nên quay lại pool sau fatal network error

Sau lỗi socket/read timeout, connection có thể không còn đồng bộ protocol với server. Không trả nó về pool để request tiếp theo dùng. Pool/driver có thể tự đánh dấu fatal connection, nhưng ứng dụng cần kiểm tra behavior và cấu hình exception classifier.

### 12.2. Đóng logical connection

Với pooled DataSource, Connection.close() thường trả logical connection về pool thay vì đóng physical socket ngay. Nếu connection bị hỏng, pool phải nhận biết và loại physical connection. Dùng API/pool mechanism chính thức; không cast wrapper hoặc đóng socket bên dưới.

### 12.3. Validation on borrow

Pool có thể validate connection khi mượn hoặc khi idle lâu. Validation query/isValid có overhead; chọn interval phù hợp. Validation chỉ kiểm tra tại thời điểm borrow, không ngăn network disconnect ngay sau đó.

### 12.4. Keepalive và idle timeout

Pool maxLifetime, idleTimeout, keepaliveTime và Oracle Net/TCP keepalive cần phối hợp với firewall/NAT/load balancer idle timeout. Nếu firewall đóng connection sau 10 phút idle nhưng pool giữ connection lâu hơn mà không validate, request có thể nhận stale connection.

### 12.5. Fatal SQL exception classification

Một số pool cho phép cấu hình SQLState/vendor code để nhận diện connection fatal. Không đánh dấu mọi ORA error là fatal: ORA-00060/ORA-00054 là lỗi statement/transaction nhưng session có thể vẫn dùng được; ORA-03113/03135 thường cho biết connection bị mất.

### 12.6. Connection pool leak và lock leak

Nếu ứng dụng không đóng connection/rollback transaction khi exception, connection có thể bị giữ lâu và row locks tiếp tục tồn tại. Dùng try-with-resources, transaction manager cleanup và leak detection. Khi request timeout, đảm bảo cleanup được thực hiện ngay cả khi thread bị interrupt/cancel.

### 12.7. Không tăng pool size để chữa lock wait

Tăng maximumPoolSize khi transaction chờ lock có thể tạo thêm session cùng tranh chấp row, tăng memory/process pressure và làm incident nặng hơn. Tìm blocker, transaction duration và access pattern trước khi đổi pool size.

### 12.8. Pool metrics

Theo dõi:

- Active/idle/total connections.
- Pending threads và acquisition timeout.
- Connection creation/validation failures.
- Connection lifetime và idle duration.
- Leak detection.
- SQL execution latency và transaction duration.
- Fatal connection evictions.

Kết hợp pool metrics với V$SESSION để xác định connection nào giữ transaction/lock.

## 13. RAC, service failover và application continuity

### 13.1. RAC connection loss

Trong RAC, node/instance hoặc service có thể chuyển trạng thái. Connection gắn với instance bị lỗi có thể mất; client cần reconnect tới service còn hoạt động. Không dùng SID/instance-specific connect descriptor cho workload cần service failover nếu kiến trúc yêu cầu service-level routing.

### 13.2. FAN

Fast Application Notification (FAN) gửi event về service/instance availability. Oracle UCP và một số integration/pool có thể subscribe FAN để nhanh chóng loại connection tới instance/service bị lỗi.

FAN giúp phát hiện sự kiện nhanh hơn timeout thụ động, nhưng không giải quyết ambiguous commit. Transaction outcome vẫn phải xử lý theo request id/idempotency.

### 13.3. TAF

Transparent Application Failover (TAF) hỗ trợ một số kiểu session failover, chủ yếu cho OCI/driver/API được hỗ trợ và giới hạn theo operation. Nó không đảm bảo replay mọi DML/transaction đã thực hiện.

### 13.4. Application Continuity và Transaction Guard

Oracle Application Continuity (AC) và Transparent Application Continuity (TAC) có thể replay request/session call theo điều kiện hỗ trợ. Transaction Guard cung cấp transaction outcome protection/query capability cho client được tích hợp.

Các feature này phụ thuộc Oracle Database/driver/service configuration, licensing và application coding rules. Không bật feature rồi bỏ idempotency/business semantics. Kiểm thử với driver và pool thực tế, đặc biệt các thao tác không replay-safe hoặc side effect ngoài database.

### 13.5. Service configuration

Ứng dụng nên connect bằng service name phù hợp với workload, role và failover policy. DBA cấu hình preferred/available instances, service goals, role-based service và FAN theo kiến trúc. Không hardcode node host/instance nếu service abstraction đã được thiết kế.

### 13.6. Reconnect storm

Khi một instance phục hồi, hàng loạt client có thể reconnect đồng thời. Dùng bounded retry, jitter, pool ramp-up và service placement để tránh connection storm. Không để mỗi request mở nhiều connection retry song song.

### 13.7. Session state sau failover

Connection mới không tự động giữ mọi session state của connection cũ: NLS, timezone, schema, package state, temporary table state và application context có thể mất. Khởi tạo lại session state theo connection initialization/reset policy.

## 14. Kiểm thử dead connection và pool recovery

### 14.1. Kiểm tra stale idle connection

1. Mượn connection từ pool.
2. Xác nhận query đơn giản thành công.
3. Trả connection về pool và để idle lâu hơn idle timeout của network lab.
4. Dùng firewall/proxy đóng idle socket.
5. Mượn connection lại và chạy query.
6. Xác nhận pool validate/evict stale connection và cấp connection mới.

### 14.2. Kiểm tra connection đang execute

1. Bắt đầu query/PLSQL call có thời gian chạy đủ dài trong lab.
2. Ngắt network giữa chừng.
3. Chờ client timeout.
4. Xác nhận connection bị evict.
5. Kiểm tra server session và SQL còn chạy hay đã dừng.
6. Xác nhận request outcome được xử lý đúng.

### 14.3. Kiểm tra pool không trả connection hỏng

Sau khi gây lỗi, lấy một connection mới từ pool và chạy query đơn giản. Xác nhận connection mới có thể thực thi và số connection active/pending trở về bình thường.

### 14.4. Kiểm tra rollback on return

Với pool/framework, xác nhận connection được trả về sau exception có transaction pending sẽ rollback hoặc được transaction manager cleanup. Không giả định mọi pool tự rollback theo mọi configuration; viết test chứng minh hành vi.

### 14.5. Kiểm tra leak

Lặp nhiều lần test exception, timeout và cancellation. Theo dõi active connection count; sau khi test kết thúc, số active phải trở về baseline. Kiểm tra database session không còn transaction/lock của test.

## 15. Thiết kế integration test

### 15.1. Unit test không đủ

Mock PreparedStatement có thể kiểm tra code gọi setNull/setBigDecimal, nhưng không tái hiện Oracle lock manager, redo commit, driver network protocol hoặc Data Guard behavior. Các scenario này cần integration test với Oracle thật/instance test và driver version giống môi trường triển khai.

### 15.2. Test environment

Ưu tiên database Oracle lab cô lập, có thể disposable/recreated. Có thể dùng Oracle Database Free container hoặc môi trường Oracle test được cấp phép; xác nhận image, license terms, version và resource requirements trước khi đưa vào CI.

### 15.3. Toxiproxy/network fault harness

Proxy TCP có thể mô phỏng latency, bandwidth limit, reset và blackhole. Đặt proxy giữa test JVM và listener/service; không dùng proxy để sửa nội dung protocol. Ghi lại rule/fault start/stop timestamp và luôn dọn proxy state sau test.

### 15.4. JUnit 5 và hai connection

Deadlock test cần hai connection vật lý độc lập. Không dùng cùng một Connection hoặc transaction manager context cho cả hai session.

```java
@Test
void detectsDeadlockBetweenTwoTransactions() throws Exception {
    ExecutorService pool = Executors.newFixedThreadPool(2);
    CountDownLatch bothHaveFirstLock = new CountDownLatch(2);
    CountDownLatch allowSecondLock = new CountDownLatch(1);

    Future<SQLException> first = pool.submit(() ->
        runDeadlockSide(dataSource, 1, 2,
            bothHaveFirstLock, allowSecondLock));
    Future<SQLException> second = pool.submit(() ->
        runDeadlockSide(dataSource, 2, 1,
            bothHaveFirstLock, allowSecondLock));

    bothHaveFirstLock.await(10, TimeUnit.SECONDS);
    allowSecondLock.countDown();

    SQLException firstError = first.get(15, TimeUnit.SECONDS);
    SQLException secondError = second.get(15, TimeUnit.SECONDS);

    assertTrue(isDeadlock(firstError) || isDeadlock(secondError));
    pool.shutdownNow();
}
```

Đây là khung minh họa, không phải test hoàn chỉnh: helper phải bắt SQLException, rollback từng connection trong finally và đồng bộ barrier sao cho hai transaction chắc chắn giữ lock đầu tiên trước khi yêu cầu lock thứ hai.

### 15.5. Không dùng Thread.sleep làm đồng bộ chính

Sleep cố định dễ tạo test flaky do CI load, scheduling và database latency. Dùng CountDownLatch, CyclicBarrier, Future timeout và server-side observation để xác nhận trạng thái. Sleep chỉ phù hợp khi test đúng timer/timeout behavior.

### 15.6. Test fixture và cleanup

Tạo dữ liệu bằng ID riêng cho mỗi test, dùng transaction cleanup hoặc delete fixture theo test ID. Nếu test tạo deadlock/network fault, cleanup phải chạy trong finally và có timeout riêng. Một test fail không được để lại lock ảnh hưởng suite sau.

### 15.7. Parallel test execution

Không chạy các test lock/deadlock trên cùng row nếu không có isolation. Dùng schema/table riêng, ID range riêng hoặc serialize test class. Nếu test dùng DDL, lưu ý DDL Oracle implicit commit và không thể rollback như DML.

### 15.8. Không assert message text

Assert Oracle vendor code/SQLState và semantic outcome. Message có thể khác theo language/driver release. Với deadlock, kiểm tra code 60 hoặc error classification trong chained SQLException.

### 15.9. Test timeout bằng Future

JUnit Future timeout kiểm soát thời gian test thread chờ kết quả, nhưng không tự cancel SQL server operation. Khi Future timeout, test phải cancel task, request Statement.cancel/connection abort theo harness và kiểm tra server-side cleanup.

### 15.10. Test có kiểm soát môi trường

Ghi nhận:

- Oracle version và database role.
- JDBC driver name/version.
- JDK version.
- Pool implementation/config.
- Network proxy/fault profile.
- Timeout settings và đơn vị.
- SQL_ID/session identifiers trong lab.
- Request ID, attempt number và transaction result.

## 16. Kịch bản kiểm thử end-to-end

### 16.1. Baseline transaction

Tạo request id, chạy business DML, commit, nhận response. Kiểm tra một business record, một dedup record và không có duplicate.

### 16.2. Disconnect trước execute

Ngắt kết nối trước khi gửi statement. Xác nhận request chưa tạo business row. Retry cùng request ID và xác nhận chỉ có một record.

### 16.3. Disconnect trong DML

Ngắt network khi statement đang chạy. Sau reconnect, xác minh server statement/session state, transaction rollback hoặc kết quả đã được commit theo boundary. Không đoán từ client exception.

### 16.4. Disconnect sau DML trước COMMIT

Ngắt kết nối sau khi DML hoàn tất nhưng trước khi gửi COMMIT. Kiểm tra transaction cuối cùng không tạo business state đã commit sau session cleanup. Sau retry cùng request ID, một kết quả duy nhất phải tồn tại.

### 16.5. Disconnect trong COMMIT

Drop response quanh commit window. Client phải đánh dấu outcome UNKNOWN, reconnect và lookup idempotency key. Nếu transaction đã commit, trả kết quả cũ; nếu chưa commit, retry cùng key.

### 16.6. Query timeout

Đặt statement timeout ngắn hơn query runtime. Kiểm tra client nhận timeout/cancel, server dừng statement và transaction được rollback/cleanup theo policy. Xác nhận connection được tái sử dụng chỉ khi driver/pool xác định nó vẫn hợp lệ.

### 16.7. Lock timeout

Session A giữ lock, session B dùng NOWAIT/WAIT. Xác nhận error classification, thời gian chờ và transaction state. Thử retry có backoff sau khi blocker commit.

### 16.8. Deadlock

Tạo hai session khóa row theo thứ tự ngược. Xác nhận một statement nhận ORA-00060, transaction victim được rollback toàn bộ ở application layer và retry business transaction từ đầu.

### 16.9. Pool stale connection

Để idle connection bị network đóng. Xác nhận pool evict và cấp connection mới. Đo thời gian phục hồi và không để pending requests vô hạn.

### 16.10. Retry storm

Mô phỏng database/service unavailable trong lab với nhiều client. Xác nhận bounded retry, jitter, circuit breaker, pool cap và recovery ramp. Không để request retry tạo tải lớn hơn workload gốc.

## 17. Ví dụ transaction retry có giới hạn

### 17.1. Phân tách business work và transaction boundary

Một transaction worker nên nhận request ID cố định và mở connection mới cho mỗi attempt:

```java
@FunctionalInterface
interface TransactionWork<T> {
    T execute(Connection connection) throws SQLException;
}

static <T> T runTransaction(
        DataSource dataSource,
        TransactionWork<T> work) throws SQLException {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);
        try {
            T result = work.execute(connection);
            connection.commit();
            return result;
        } catch (SQLException | RuntimeException e) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                e.addSuppressed(rollbackError);
            }
            throw e;
        }
    }
}
```

Đây là primitive transaction đơn giản. Nó chưa quyết định retry và không thể tự giải quyết ambiguous commit. Caller phải phân loại commit exception và dùng idempotency.

### 17.2. Retry chỉ cho lỗi transaction abort đã biết

Với deadlock/serialization failure, transaction đã có statement bị Oracle từ chối. Có thể rollback và replay toàn transaction nếu business logic deterministic/idempotent:

```java
for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
        return runTransaction(dataSource, work);
    } catch (SQLException e) {
        if (!isKnownTransactionAbort(e) || attempt == maxAttempts) {
            throw e;
        }
        sleep(backoffWithJitter(attempt));
    }
}
throw new IllegalStateException("unreachable");
```

Không đưa mọi SQLException vào isKnownTransactionAbort. Ví dụ ORA-01722 là lỗi input/type; retry không sửa được.

### 17.3. Ambiguous commit cần protocol khác

Nếu commit exception có thể xảy ra sau khi server đã commit, đừng gọi retry wrapper thông thường mà không có idempotency:

```text
COMMIT RESPONSE LOST
       |
       v
Mark outcome = UNKNOWN
       |
       v
Reconnect using same request_id
       |
       v
Lookup committed request/result
       |
       +-- Found, hash matches --> Return stored result
       |
       +-- Found, hash differs --> Reject key reuse
       |
       +-- Not found / unresolved
                |
                v
       Retry same request_id under unique constraint
       or wait/reconcile within deadline
```

### 17.4. Không tạo request ID mới khi retry

Request ID được tạo ở biên nhận request đầu tiên và giữ nguyên qua mọi retry nội bộ, HTTP retry và worker redelivery. Nếu tạo key mới mỗi attempt, unique constraint không thể deduplicate.

### 17.5. Exponential backoff có jitter

```java
static Duration backoffWithJitter(int attempt) {
    long capMillis = Math.min(2_000L, 100L << (attempt - 1));
    long delay = ThreadLocalRandom.current()
        .nextLong(0, capMillis + 1);
    return Duration.ofMillis(delay);
}
```

Ví dụ này dùng shift và cap minh họa. Cần bảo vệ overflow khi attempt lớn, áp dụng max elapsed time và dùng clock/deadline chung cho request.

### 17.6. Deadline-aware retry

Trước mỗi attempt, tính thời gian còn lại của request. Nếu không còn đủ thời gian cho connection acquisition, transaction, commit và response, dừng retry và trả trạng thái có thể reconcile sau. Không bắt đầu attempt mới chỉ vì số lần retry còn.

### 17.7. Retry policy theo loại lỗi

Tách ít nhất ba kết quả:

- RETRYABLE_ABORT: transaction chắc chắn chưa commit và có thể replay.
- OUTCOME_UNKNOWN: cần tra cứu idempotency/request status.
- PERMANENT_FAILURE: input, constraint, permission hoặc SQL lỗi cần sửa.

Không gộp ba nhóm thành một boolean retryable.

## 18. Ví dụ xử lý idempotency trong JDBC

### 18.1. DDL business và request record

Ví dụ schema:

```sql
CREATE TABLE api_request (
    request_id   VARCHAR2(64) PRIMARY KEY,
    request_hash VARCHAR2(64) NOT NULL,
    order_id     NUMBER,
    response_json CLOB,
    created_at   TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);

CREATE TABLE api_order (
    order_id NUMBER PRIMARY KEY,
    request_id VARCHAR2(64) NOT NULL UNIQUE,
    customer_id NUMBER NOT NULL,
    amount NUMBER(12,2) NOT NULL
);
```

Schema minh họa; đặt FK/index/check constraints theo nghiệp vụ và retention policy. Nếu response lớn, cân nhắc lưu reference tới result resource.

### 18.2. Transaction logic

```java
connection.setAutoCommit(false);
try {
    insertApiRequest(connection, requestId, requestHash);
    long orderId = insertOrder(connection, requestId, customerId, amount);
    String response = serializeOrderResult(orderId);
    updateApiRequestResult(connection, requestId, orderId, response);
    connection.commit();
    return response;
} catch (SQLException e) {
    rollbackQuietly(connection, e);
    throw e;
}
```

Trong transaction này, api_request và api_order cùng commit/rollback. Nếu commit response bị mất, request record đã commit cho phép trả lại response cũ.

### 18.3. Duplicate request flow

Khi insertApiRequest nhận ORA-00001:

1. Rollback transaction hiện tại.
2. Mở connection mới.
3. Đọc request_id và request_hash đã lưu.
4. Nếu hash khác, trả conflict.
5. Nếu response đã có, trả response đã lưu.
6. Nếu record tồn tại nhưng response chưa có, kiểm tra state machine/owner; không tự chạy lại DML.

Nếu request row chỉ được commit cùng business operation, trạng thái “row có nhưng response chưa có” không nên xuất hiện trong thiết kế đơn transaction; nếu có, có thể là workflow nhiều phase và cần trạng thái explicit.

### 18.4. Unique violation có thể đến từ constraint khác

SQLException vendor code 1 không nói tên constraint qua mọi driver/API theo cùng một cách. Có thể parse constraint name từ message như tín hiệu bổ sung, nhưng thiết kế tốt hơn là insert idempotency row riêng ở bước đầu và bắt lỗi ngay tại câu lệnh đó. Không biến mọi ORA-00001 trong business DML thành duplicate request.

### 18.5. Cùng key, khác payload

Nếu request_id tồn tại nhưng request_hash khác, trả conflict/error nghiệp vụ. Không trả response cũ cho payload mới vì có thể làm client hiểu nhầm thao tác đã thực hiện.

### 18.6. Retention của idempotency record

Giữ request key ít nhất bằng thời gian client/provider có thể retry hoặc redeliver cộng thêm khoảng an toàn. Nếu xóa key quá sớm, request cũ có thể được thực hiện lại. Thiết kế cleanup theo retention và audit requirement.

## 19. Test deadlock bằng Java hai connection

### 19.1. Helper khóa row

```java
static void updateRow(
        Connection connection, long id, String value)
        throws SQLException {
    try (PreparedStatement ps = connection.prepareStatement(
            "UPDATE deadlock_lab SET value_text = ? WHERE id = ?")) {
        ps.setString(1, value);
        ps.setLong(2, id);
        ps.executeUpdate();
    }
}
```

### 19.2. Kịch bản đồng bộ

Test cần đảm bảo:

1. Connection A lock row 1.
2. Connection B lock row 2.
3. Barrier xác nhận cả hai đã giữ lock đầu tiên.
4. A và B đồng thời yêu cầu row còn lại.
5. Một phía nhận ORA-00060.
6. Cả hai transaction rollback và connection đóng.

Không dùng cùng connection cho hai worker. Connection pool cần ít nhất hai physical connections khả dụng và không bật transaction sharing.

### 19.3. Xác nhận victim và recovery

Test assert một trong hai worker nhận vendor code 60. Sau rollback/cleanup, query lại bảng để xác nhận không có thay đổi partial được commit. Sau đó chạy lại business transaction với cùng request key và xác nhận kết quả duy nhất.

### 19.4. Lặp nhiều lần

Deadlock test có yếu tố scheduling. Chạy lặp trong lab với barrier chắc chắn và timeout tổng. Nếu không tạo deadlock, kiểm tra thứ tự barrier/lock thay vì tăng sleep tùy tiện.

## 20. Observability cho timeout/retry

### 20.1. Correlation fields

Mỗi log event nên chứa:

- request_id/idempotency key (mask/hash nếu nhạy cảm).
- attempt number và retry reason.
- transaction phase: acquire, execute, commit, outcome lookup.
- SQL_ID hoặc operation name, không nhất thiết log full SQL/value.
- pool name, connection acquisition duration.
- driver version, database service/role nếu có.
- timeout setting/deadline remaining.
- SQLState, Oracle vendor code, exception class.
- connection disposition: reused, evicted, aborted.

### 20.2. Metrics

Theo dõi:

- Connect/acquisition timeout rate.
- Read timeout và query timeout rate.
- ORA-00060/deadlock count.
- ORA-00054/ORA-30006 lock contention.
- Retry attempts per request và retry success rate.
- Unknown commit outcome count.
- Idempotency duplicate hits/key conflicts.
- Connection eviction/reconnect rate.
- Transaction duration và lock wait time.
- Pool pending/active/idle count.

### 20.3. Alert

Alert khi deadlock tăng đột biến, retry rate vượt baseline, pool pending tăng, unknown commit outcome xuất hiện liên tục, hoặc connection creation fail. Một vài lỗi transient riêng lẻ không nhất thiết cần page; xem trend, tỷ lệ và business impact.

### 20.4. Trace và bind values

Có thể dùng DBMS_APPLICATION_INFO để đặt MODULE/ACTION/CLIENT_IDENTIFIER cho session:

```sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'order-service',
        action_name => 'create-order'
    );
    DBMS_SESSION.SET_IDENTIFIER('request-opaque-id');
END;
/
```

Đặt identifier không chứa PII/secret. Reset session state khi trả connection về pool. Không bật trace bind đầy đủ trên production nếu chưa đánh giá dữ liệu nhạy cảm và overhead.

### 20.5. Correlate với V$SESSION

```sql
SELECT
    sid,
    serial#,
    username,
    module,
    action,
    client_identifier,
    status,
    event,
    blocking_session,
    sql_id
FROM v$session
WHERE module = 'order-service';
```

Quyền xem V$SESSION phụ thuộc DBA privileges. Với RAC, dùng GV$SESSION và include INST_ID.

## 21. Runbook xử lý incident

### 21.1. Database/network không kết nối được

1. Phân biệt connect timeout, DNS/TNS, listener, service và authentication.
2. Kiểm tra pool pending/creation failure.
3. Kiểm tra Oracle alert/listener log và network telemetry.
4. Mở circuit breaker nếu retry storm.
5. Không retry nhanh vô hạn.
6. Khi service phục hồi, ramp connection pool từ từ.

### 21.2. Query timeout tăng

1. Xác định SQL_ID/operation và timeout tầng nào kích hoạt.
2. Kiểm tra SQL plan, wait event, blocking session và I/O.
3. Xác nhận cancel có dừng server statement.
4. Kiểm tra transaction/locks sau timeout.
5. Điều chỉnh SQL/index/resource hoặc deadline dựa trên số đo.

### 21.3. Deadlock tăng

1. Thu thập deadlock graph/trace.
2. Xác định hai hay nhiều SQL và resource.
3. Kiểm tra transaction access order, trigger và foreign key.
4. Sửa lock ordering/transaction scope.
5. Giữ bounded retry ORA-00060 cho operation idempotent.
6. Kiểm thử regression bằng hai connection.

### 21.4. Commit outcome unknown

1. Gắn trạng thái request là UNKNOWN, không báo chắc chắn thất bại.
2. Loại connection hỏng khỏi pool.
3. Reconnect bằng cùng request_id.
4. Lookup dedup/business result.
5. Nếu đã commit, trả kết quả đã lưu.
6. Nếu chưa có kết quả, retry cùng key hoặc chờ/reconcile theo protocol.
7. Escalate manual reconciliation nếu không xác định được outcome trong deadline.

### 21.5. Pool cạn

Kiểm tra connection leak, transaction lâu, lock wait, request thread bị block, validation timeout và database session limit. Không tăng pool size một cách phản xạ; xác định bottleneck và capacity trước.

### 21.6. Sau incident

Ghi lại timeline client/server, request ID, SQL_ID, transaction phase, exception chain, pool metrics và database trace. Tạo test regression tái hiện failure window và xác nhận idempotency/retry.
