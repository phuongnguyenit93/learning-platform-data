# Rò rỉ kết nối, giao dịch bỏ quên và phiên nhàn rỗi trong giao dịch

## 1. Vì sao kết nối bị giữ lâu có thể làm database chậm?

Ứng dụng thường dùng connection pool để tái sử dụng kết nối tới cơ sở dữ liệu. Một kết nối được mượn khi cần truy vấn, thực hiện công việc rồi trả lại pool. Nếu mã ứng dụng không đóng kết nối, statement hoặc result set đúng cách, kết nối có thể bị giữ mãi và pool dần cạn. Request mới phải chờ lấy kết nối, tăng latency hoặc timeout dù database chưa chắc đã hết CPU hay I/O.

Một vấn đề nghiêm trọng hơn xuất hiện khi kết nối vẫn tồn tại và giao dịch chưa kết thúc, hoặc connection được trả về pool mà transaction không được reset đúng cách. Phiên `idle in transaction` (nhàn rỗi trong giao dịch) không chạy câu SQL nào tại thời điểm quan sát, nhưng transaction vẫn mở. Nó có thể giữ khóa, giữ snapshot cũ, ngăn cơ chế dọn phiên bản dữ liệu, làm log hoặc undo tăng và cản trở các giao dịch khác. Trong hệ quản trị khác, trạng thái này có thể được biểu diễn bằng session `Sleep` nhưng vẫn có transaction đang mở, hoặc session `sleeping` có `open_transaction_count` lớn hơn 0.

Trong tối ưu hiệu năng cơ sở dữ liệu, rò rỉ kết nối và giao dịch bỏ quên là vấn đề ở ranh giới giữa ứng dụng, pool, driver, mạng và database. Chúng có thể gây connection exhaustion, lock contention, transaction log growth, vacuum/purge chậm và tail latency tăng. Cần phân biệt một kết nối idle bình thường trong pool với một transaction idle bị bỏ quên, đồng thời đo thời gian mượn kết nối, tuổi transaction và trạng thái session.

Bài học này trình bày vòng đời kết nối, các kiểu rò rỉ thường gặp, tác hại của giao dịch mở lâu, cách quản lý tài nguyên bằng JDBC và framework, cách đặt timeout, cách quan sát PostgreSQL/MySQL/SQL Server và quy trình xử lý an toàn. Các trạng thái, câu lệnh quản trị và cấu hình khác nhau theo engine và phiên bản; hãy kiểm tra tài liệu đúng môi trường trước khi áp dụng.

## 2. Phân biệt connection leak, idle connection và idle transaction

### 2.1. Connection leak — kết nối bị mượn nhưng không được trả

Connection leak xảy ra khi ứng dụng lấy kết nối từ pool nhưng không đóng handle hoặc không trả nó về pool sau khi hoàn tất công việc. Một số nguyên nhân phổ biến:

- Thiếu `close()` trong nhánh xử lý lỗi hoặc `return` sớm.
- Exception xảy ra trước khi cleanup.
- `ResultSet` hoặc `Statement` không được đóng, khiến kết nối bị giữ theo chuỗi tài nguyên.
- Luồng xử lý streaming giữ connection trong khi ứng dụng đọc dữ liệu chậm.
- Callback hoặc tác vụ bất đồng bộ giữ connection lâu hơn request ban đầu.
- Mã lưu connection vào field hoặc context dùng chung và quên giải phóng.
- Một transaction bắt đầu nhưng nhánh commit/rollback không được chạy.

Hậu quả trực tiếp là số connection active trong pool tăng, số connection idle giảm, hàng đợi chờ mượn connection tăng và request mới bị timeout. Pool có thể báo leak warning nếu một connection được mượn lâu hơn ngưỡng theo dõi, nhưng cảnh báo này không phải lúc nào cũng chứng minh có leak: một truy vấn hợp lệ hoặc export lớn cũng có thể giữ kết nối lâu.

### 2.2. Idle connection — kết nối nhàn rỗi bình thường

Một connection idle trong pool đã được trả lại pool và sẵn sàng được request khác mượn. Nó thường không có transaction đang mở và không giữ tài nguyên transaction như một phiên idle in transaction. Pool giữ một số connection idle để tránh chi phí thiết lập TCP, TLS, xác thực và session mới cho mỗi request.

Quá nhiều idle connection vẫn có thể gây vấn đề: mỗi session tiêu thụ bộ nhớ và tài nguyên phía server, làm tăng số connection cần quản lý và có thể chạm giới hạn `max_connections` hoặc giới hạn worker. Tuy nhiên, không nên kết luận connection leak chỉ vì database có nhiều session `idle`/`Sleep`; cần xem pool đang giữ chúng có chủ đích hay không và transaction có mở không.

### 2.3. Idle in transaction — phiên nhàn rỗi nhưng transaction vẫn mở

Một session idle in transaction đã bắt đầu transaction, thực hiện ít nhất một câu lệnh rồi không gửi lệnh tiếp theo trong khi chưa `COMMIT` hoặc `ROLLBACK`. Database vẫn xem transaction đó đang hoạt động về mặt vòng đời dù không có truy vấn đang chạy.

Trạng thái này nguy hiểm hơn idle bình thường vì transaction có thể:

- Giữ row lock, table lock hoặc lock tài nguyên khác tùy engine và câu lệnh đã chạy.
- Giữ snapshot/transaction ID cũ, ngăn dọn các phiên bản dữ liệu không còn cần thiết.
- Giữ metadata lock hoặc khóa schema trong một số tình huống.
- Làm transaction log không thể truncate/reuse hoặc làm undo history tồn tại lâu hơn.
- Khiến DDL, vacuum, purge hoặc giao dịch khác phải chờ.

Không phải mọi idle transaction đều giữ cùng loại lock. Ví dụ, một transaction chỉ đọc có thể không giữ row lock nhưng vẫn giữ snapshot cũ trong hệ thống MVCC. Vì vậy, phải kiểm tra tuổi transaction, loại lệnh đã chạy, lock và wait thay vì chỉ dựa vào trạng thái session.

### 2.4. Bảng phân biệt nhanh

| Trạng thái | Có connection tới database? | Có transaction mở? | Tác động thường gặp |
|---|---|---|---|
| Connection idle trong pool | Có | Không | Chiếm một slot/session; thường là bình thường |
| Connection active chạy query | Có | Thường có hoặc đang thực thi ngoài transaction tường minh | Dùng CPU/I/O, có thể giữ lock trong lúc chạy |
| Connection leak | Có thể còn ở server | Có thể có hoặc không | Pool cạn vì ứng dụng không trả connection |
| Idle in transaction | Có | Có | Có thể giữ lock/snapshot, cản cleanup và gây contention |
| Session chết/stale do mạng | Có thể còn entry tạm thời ở server | Có thể có cho tới khi server phát hiện disconnect | Tài nguyên được giải phóng trễ; thao tác commit có thể có kết quả không rõ |

## 3. Vòng đời đúng của một kết nối

Một kết nối nên có phạm vi sống rõ ràng và ngắn nhất có thể:

```text
Request / job cần truy cập database
              |
              v
       Mượn connection từ pool
              |
              v
     Thực hiện câu lệnh cần thiết
              |
              v
   Đóng ResultSet / Statement
              |
              v
     COMMIT hoặc ROLLBACK
              |
              v
      Đóng handle Connection
              |
              v
   Pool reset session và tái sử dụng
```

Đóng handle `Connection` lấy từ pool thường trả connection logic về pool, không nhất thiết đóng socket vật lý. Pool có thể reset trạng thái như auto-commit, isolation, schema, read-only hoặc network timeout trước khi cho request khác dùng. Hành vi reset tùy pool và driver; không nên giả định mọi session state đều tự được dọn.

Các nguyên tắc:

1. Chỉ mượn connection khi sắp thực hiện công việc database.
2. Không giữ connection trong lúc gọi HTTP, chờ người dùng, sleep hoặc xử lý CPU dài không cần database.
3. Đóng result set và statement sau khi dùng.
4. Kết thúc transaction trên mọi đường đi: commit khi thành công, rollback khi lỗi.
5. Đóng connection trong `finally` hoặc cơ chế quản lý tài nguyên tự động.
6. Không chia sẻ cùng một JDBC connection cho nhiều luồng đồng thời trừ khi driver/framework và cách dùng cụ thể hỗ trợ rõ ràng; thông thường nên xem connection là tài nguyên không dùng đồng thời.
7. Không trả connection về pool trong khi result stream, cursor hoặc tác vụ bất đồng bộ còn sử dụng nó.

## 4. Rò rỉ kết nối trong Java/JDBC

### 4.1. Mẫu dễ gây leak

Đoạn mã sau có thể làm connection không được trả về pool nếu câu lệnh ném exception:

```java
Connection connection = dataSource.getConnection();
PreparedStatement statement = connection.prepareStatement(
    "SELECT id, email FROM customers WHERE active = ?"
);
statement.setBoolean(1, true);
ResultSet resultSet = statement.executeQuery();

while (resultSet.next()) {
    process(resultSet.getLong("id"), resultSet.getString("email"));
}

connection.close();
```

Nếu `prepareStatement`, `executeQuery`, `next` hoặc `process` ném exception, dòng `connection.close()` có thể không chạy. Statement và result set cũng chưa được đóng rõ ràng.

### 4.2. Dùng try-with-resources

JDBC hỗ trợ `AutoCloseable`, vì vậy try-with-resources giúp đóng tài nguyên kể cả khi có exception:

```java
String sql = "SELECT id, email FROM customers WHERE active = ?";

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setBoolean(1, true);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            process(
                resultSet.getLong("id"),
                resultSet.getString("email")
            );
        }
    }
}
```

Khi khối kết thúc, `ResultSet`, `PreparedStatement` và `Connection` được đóng theo thứ tự ngược. Với pooled connection, `close()` trên handle thường trả connection về pool để tái sử dụng. Nếu `process` thực hiện công việc chậm hoặc gọi dịch vụ ngoài, connection vẫn bị giữ trong suốt vòng lặp; hãy cân nhắc đọc theo batch, lấy dữ liệu cần thiết rồi xử lý ngoài phạm vi connection nếu yêu cầu nghiệp vụ cho phép.

### 4.3. Transaction phải có cả commit và rollback

Khi tắt auto-commit, ứng dụng phải bảo đảm transaction kết thúc trên cả đường thành công và thất bại. Ví dụ sau là phần thân của một method khai báo `throws SQLException`; các hàm cập nhật dùng connection được truyền vào và không tự commit:

```java
public void createOrder(long orderId, long productId, int quantity)
        throws SQLException {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);

        try {
            updateInventory(connection, productId, quantity);
            insertOrder(connection, orderId, productId, quantity);
            connection.commit();
        } catch (SQLException | RuntimeException error) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                error.addSuppressed(rollbackError);
            }
            throw error;
        }
    }
}
```

Ví dụ giả định các hàm cập nhật dùng chính connection được truyền vào và không tự commit. Khi khối kết thúc, connection handle được đóng và pool có cơ hội reset session. Nếu `commit()` ném lỗi do mất mạng, kết quả commit có thể chưa rõ: server có thể đã commit nhưng phản hồi không tới ứng dụng. Gọi rollback sau đó không chứng minh transaction chưa commit. Với thao tác nghiệp vụ cần retry, hãy dùng idempotency key hoặc cơ chế tra cứu trạng thái giao dịch để tránh thực hiện lặp.

Không dựa vào việc `close()` sẽ tự động rollback theo một semantics giống nhau ở mọi pool/driver. Hãy kết thúc transaction tường minh trước khi đóng và kiểm tra hành vi reset của pool đang dùng.

### 4.4. Đóng stream và cursor

Một API trả `Stream<T>`, iterator hoặc cursor có thể thực thi truy vấn lười (lazy) và giữ result set cùng connection cho đến khi stream đóng. Ví dụ, trả một Java Stream từ method nhưng đóng connection ngay khi method return có thể làm stream lỗi; ngược lại, để stream mở cho tới khi consumer xử lý xong có thể giữ connection quá lâu.

Thiết kế API cần làm rõ ai sở hữu và đóng stream. Nếu dữ liệu lớn, xử lý theo batch có ranh giới rõ, đóng cursor sau mỗi batch và tránh giữ transaction trong khi consumer chờ mạng hoặc ghi file chậm.

## 5. Rò rỉ trong framework và xử lý bất đồng bộ

### 5.1. Transaction scope quá rộng

Framework có thể mở transaction quanh một method, nhưng method đó lại gọi API bên ngoài, chờ message broker hoặc thực hiện tính toán lâu. Trong toàn bộ thời gian đó, transaction và connection có thể vẫn được giữ.

Ví dụ không nên làm:

```java
@Transactional
public void placeOrder(OrderRequest request) {
    orderRepository.save(request.toOrder());
    paymentClient.authorize(request.payment()); // gọi mạng bên ngoài
    notificationClient.send(request.email());   // có thể chờ lâu
}
```

Nếu hai lời gọi bên ngoài mất 2 giây, transaction có thể giữ connection và snapshot trong khoảng thời gian đó dù database chỉ cần vài mili giây để ghi đơn hàng. Cách tổ chức phù hợp hơn là giữ transaction quanh thao tác database cần atomicity, ghi outbox trong cùng transaction nếu cần phát sự kiện, rồi xử lý thanh toán/thông báo bằng workflow có trạng thái và retry idempotent phù hợp.

Không phải mọi nghiệp vụ đều có thể tách transaction mà không đổi semantics. Hãy xác định ranh giới atomicity, trạng thái trung gian, cách bù trừ và idempotency trước khi tách.

### 5.2. Transaction context qua thread và async task

Một số framework gắn transaction với thread hoặc execution context. Khi chuyển sang executor, callback hoặc coroutine, transaction context có thể không được truyền như mong muốn. Có thể xảy ra hai kiểu lỗi:

- Tác vụ bất đồng bộ không tham gia transaction dự kiến và chạy bằng connection/transaction khác.
- Thread ban đầu vẫn giữ transaction trong khi chờ tác vụ bất đồng bộ hoàn tất, khiến connection bị giữ lâu.

Không truyền JDBC connection qua nhiều thread tùy tiện. Hãy dùng cơ chế transaction-aware được framework hỗ trợ, hoặc tạo transaction riêng cho từng đơn vị công việc có semantics rõ ràng. Không để transaction bao quanh `Future.get()`, queue wait hoặc callback có thời gian không xác định nếu không thật sự cần.

### 5.3. Lazy loading và Open Session in View

Một số ORM giữ session/connection trong suốt vòng đời request để hỗ trợ lazy loading ở tầng trình bày. Nếu response serialization truy cập quan hệ lazy, database query có thể phát sinh muộn, kéo dài thời gian giữ session và tạo N+1 query. Khi response chậm do client hoặc network, connection có thể bị giữ lâu hơn cần thiết.

Hãy xác định rõ thời điểm tải dữ liệu, dùng projection/fetch plan phù hợp, chuyển entity thành DTO trước khi rời transaction và cân nhắc tắt Open Session in View nếu nó che giấu truy vấn phát sinh ngoài service layer. Việc tắt tính năng cần đi kèm sửa các điểm lazy loading để không tạo lỗi runtime.

## 6. Giao dịch bỏ quên và tác hại theo từng hệ quản trị

### 6.1. Giữ khóa và tạo blocking chain

Một transaction có thể cập nhật hàng A rồi chờ ứng dụng xử lý thêm trước khi commit. Transaction khác muốn cập nhật A phải chờ khóa. Nếu transaction thứ hai giữ khóa ở hàng B rồi một transaction thứ ba chờ B, blocking chain có thể lan rộng.

Session idle in transaction không chạy CPU nhưng vẫn có thể là blocker. Khi điều tra, hãy xem `xact_start` hoặc transaction begin time, lock owner, blocker/waiter và câu SQL gần nhất. Truy vấn hiện tại rỗng không có nghĩa session không gây ảnh hưởng.

### 6.2. PostgreSQL: snapshot cũ và vacuum

PostgreSQL dùng MVCC. Transaction có snapshot cũ có thể khiến vacuum không loại bỏ một số phiên bản tuple đã chết vì vẫn có khả năng transaction cũ cần nhìn thấy chúng. Một transaction idle in transaction kéo dài có thể giữ `xmin` cũ, làm dead tuples tích tụ, tăng table/index bloat và tăng lượng I/O cho truy vấn.

Nó cũng có thể giữ row/table lock nếu đã thực hiện thao tác cần khóa. Các trạng thái `idle in transaction` và `idle in transaction (aborted)` trong `pg_stat_activity` là dấu hiệu cần kiểm tra. Một transaction đã lỗi có thể ở trạng thái aborted nhưng vẫn mở cho tới khi rollback hoặc session kết thúc.

### 6.3. MySQL/InnoDB: lock và undo purge

InnoDB dùng MVCC và undo log để phục vụ consistent read và rollback. Transaction cũ có thể giữ read view khiến purge chưa thể dọn một số undo record; history list length có thể tăng, làm tăng dung lượng undo và chi phí đọc phiên bản cũ. Transaction ghi còn có thể giữ row lock, metadata lock hoặc khóa khác cho tới khi kết thúc.

Một connection `Sleep` trong process list vẫn có thể có transaction đang mở. Cần đối chiếu process list với `information_schema.innodb_trx`, không kết luận dựa trên `COMMAND='Sleep'` đơn lẻ. `wait_timeout` có thể đóng session không hoạt động sau một khoảng thời gian; khi session bị ngắt, transaction chưa commit sẽ bị rollback, nhưng chờ timeout không phải cách quản lý transaction đúng và có thể tạo rollback lớn.

### 6.4. SQL Server: open transaction, log và version store

SQL Server có thể hiển thị session `sleeping` nhưng `open_transaction_count` vẫn lớn hơn 0. Transaction mở lâu có thể giữ lock, ngăn transaction log truncation/reuse và làm log file tăng. Với row versioning như snapshot isolation hoặc read committed snapshot, transaction snapshot lâu có thể giữ version cần thiết trong version store lâu hơn.

Hãy xem transaction begin time, session, request đang chạy hay không, lock, log reuse wait và version store. `sleeping` chỉ nói session hiện không có request hoạt động; nó không khẳng định transaction đã kết thúc.

## 7. Vì sao pool cạn và database hết connection?

### 7.1. Pool exhaustion

Pool exhaustion xảy ra khi mọi connection trong pool đang được mượn hoặc pool không thể tạo thêm connection theo giới hạn cấu hình. Request mới phải chờ trong hàng đợi lấy connection. Nếu thời gian chờ vượt `connectionTimeout` hoặc acquisition timeout, ứng dụng báo lỗi trước cả khi gửi SQL.

Nguyên nhân có thể là:

- Leak thực sự: connection không được trả.
- Query chậm: connection được dùng đúng cách nhưng bị giữ lâu.
- Transaction idle: connection được giữ trong transaction mở.
- Pool quá nhỏ so với concurrency hợp lý.
- Database chậm hoặc giới hạn tài nguyên, làm mỗi connection được giữ lâu hơn.
- Connection creation/validation chậm do DNS, TLS, authentication hoặc network.
- Một số request giữ connection khi làm việc ngoài database.

### 7.2. Phân biệt pool nhỏ với leak

Quan sát đồng thời:

| Dấu hiệu | Leak có khả năng | Pool nhỏ hoặc DB chậm có khả năng |
|---|---|---|
| Active connections | Tăng dần và ít giảm sau khi tải hạ | Tăng theo tải rồi giảm khi tải hạ |
| Idle connections | Gần 0 kéo dài | Có thể trở lại khi query hoàn tất |
| Pending borrowers | Tăng và không tự giảm | Tăng theo burst hoặc query latency |
| Connection usage time | Có một số connection bị giữ bất thường lâu | Phần lớn tăng đồng đều theo thời gian query |
| Leak detection warning | Lặp lại cùng call site | Có thể cảnh báo false positive với query hợp lệ dài |
| DB session state | Có thể thấy idle/idle in transaction kéo dài | Có thể thấy active query, lock wait hoặc I/O wait |

Nếu active connection tăng theo thời gian dù request rate không tăng, hãy tìm leak. Nếu query duration và DB waits cùng tăng, pool có thể chỉ đang phản ánh database quá tải. Tăng pool trong trường hợp database đã bão hòa có thể làm contention nặng hơn.

### 7.3. Chọn kích thước pool

Một ước lượng ban đầu cho số connection đang thực hiện công việc trung bình có thể dựa trên định luật Little:

\[
\text{Concurrency trung bình} \approx \text{Throughput} \times \text{Thời gian giữ connection}
\]

Ví dụ, ứng dụng thực hiện 250 thao tác database mỗi giây và mỗi thao tác giữ connection trung bình 40 ms (0,04 giây):

\[
250 \times 0,04 = 10\text{ connection đồng thời trung bình}
\]

Đây chỉ là ước lượng trung bình. Cần cộng headroom hợp lý cho burst và biến thiên, đồng thời kiểm tra CPU, I/O, lock và khả năng xử lý của database. Không lấy số user đăng nhập làm số connection cần có.

Nếu có 8 instance ứng dụng và mỗi instance cho phép tối đa 40 connection, tổng tiềm năng là 320 connection, chưa tính worker nền, migration, monitoring và admin. Hãy tính tổng pool trên toàn bộ deployment so với khả năng database. Một pool lớn hơn không luôn làm throughput cao hơn; nó có thể tăng context switching, lock contention, memory usage và queue ở database.

## 8. Timeout không phải tất cả đều giống nhau

Timeout cần đặt ở đúng tầng và có hành vi cleanup rõ ràng:

| Loại timeout | Giới hạn điều gì? | Khi hết hạn cần lưu ý |
|---|---|---|
| Pool acquisition timeout | Thời gian chờ mượn connection | Chưa chắc SQL đã được gửi; cần báo lỗi/giảm tải ở ứng dụng |
| Connect/login timeout | Thiết lập TCP/TLS/xác thực | Có thể chưa có session; kiểm tra DNS, network và server capacity |
| Socket/network timeout | Thời gian chờ đọc/ghi qua kết nối | Server có thể chưa biết client đã bỏ; transaction outcome có thể không rõ |
| Statement/query timeout | Thời gian một câu SQL được phép chạy | Câu lệnh bị hủy; transaction có thể vẫn mở hoặc ở trạng thái aborted cho tới rollback |
| Lock timeout | Thời gian chờ khóa | Thường hủy thao tác đang chờ; transaction scope vẫn cần được xử lý |
| Transaction timeout | Thời gian tối đa cho transaction theo framework/engine | Cần bảo đảm rollback và trả connection; hỗ trợ tùy nền tảng |
| Idle-in-transaction timeout | Thời gian session được phép nhàn rỗi trong transaction | Engine có thể hủy session/transaction; ứng dụng phải xử lý connection bị đóng |
| Pool leak detection threshold | Ngưỡng cảnh báo connection được mượn lâu | Thường chỉ cảnh báo, không tự động kết thúc query hoặc trả connection |

Đặt timeout theo thứ tự hợp lý: acquisition timeout thường ngắn hơn request deadline; query/transaction deadline phải phù hợp SLO; network timeout phải phối hợp với driver và server; idle transaction timeout là lớp bảo vệ cuối cùng. Nếu statement timeout hủy câu lệnh, ứng dụng vẫn phải rollback transaction trước khi trả connection.

Timeout không thay thế cleanup. Một request timeout ở HTTP layer không tự động bảo đảm JDBC statement đã bị cancel, transaction đã rollback hoặc connection đã về pool. Hãy kiểm tra cách cancellation được truyền qua framework, driver và database.

## 9. Quản lý vòng đời connection pool

### 9.1. Giới hạn pool và thời gian chờ

Pool cần có:

- Maximum pool size phù hợp tổng số instance và năng lực database.
- Minimum idle hợp lý để giảm chi phí tạo kết nối mà không giữ quá nhiều session.
- Connection acquisition timeout để hàng đợi không kéo dài vô hạn.
- Leak detection threshold để phát hiện call site giữ connection lâu.
- Idle timeout và max lifetime để loại connection quá cũ hoặc không cần thiết.
- Validation/keepalive phù hợp với network và database timeout.

Tên cấu hình khác nhau theo pool, ví dụ HikariCP, Apache DBCP hoặc pool của application server. Đừng sao chép con số mẫu mà không đo connection usage duration và concurrency.

### 9.2. Max lifetime và stale connection

Firewall, load balancer, NAT hoặc database có thể đóng connection sau một thời gian. Pool vẫn có thể giữ handle tưởng như hợp lệ nhưng socket đã stale. Cấu hình max lifetime/keepalive nên phối hợp với giới hạn idle của network và server để pool chủ động loại hoặc kiểm tra connection trước khi request cần dùng.

Validation query hoặc `Connection.isValid()` có thể phát hiện một số connection hỏng, nhưng validation quá thường xuyên cũng tạo thêm round trip. Hãy dùng cơ chế pool/driver phù hợp và theo dõi connection creation failure, validation failure, reset và eviction.

TCP keepalive giúp phát hiện peer mất kết nối trong một số tình huống, nhưng thường có chu kỳ riêng và không thay thế query timeout, transaction timeout hoặc kiểm tra connection của pool. Với network partition, client và server có thể phát hiện lỗi ở những thời điểm khác nhau.

### 9.3. Reset session state khi trả connection

Connection pool tái sử dụng session, vì vậy trạng thái do request trước đặt có thể ảnh hưởng request sau nếu không reset. Các trạng thái cần lưu ý:

- `autoCommit`, transaction isolation và read-only mode.
- Schema, catalog, role/user hoặc search path.
- Session variables, timezone, collation hoặc statement timeout.
- Temporary table, cursor và prepared statement theo session.
- Advisory/session lock hoặc application lock.
- Các thiết lập tracing, application name hoặc context nghiệp vụ.

Đừng để request thay đổi session state rồi giả định connection mới sẽ có trạng thái mặc định. Dùng cơ chế reset của pool/driver hoặc khôi phục trạng thái trong phạm vi an toàn. Một số trạng thái như temporary table hoặc session-level lock có thể tồn tại qua lần mượn tiếp theo nếu không được dọn.

## 10. Quan sát pool và database cùng lúc

### 10.1. Metric ở phía ứng dụng

Thu thập ít nhất:

- Total connections, active connections và idle connections.
- Pending borrowers/waiters và acquisition latency p50/p95/p99.
- Connection usage duration từ lúc mượn đến lúc trả.
- Connection creation, validation, eviction và timeout count.
- Leak detection warning theo call site.
- Query duration, transaction duration và request deadline.
- Số connection theo pool name, instance, tenant hoặc service.

Metric pool cho biết ứng dụng đang chờ ở đâu. Nếu pool active đạt max và pending tăng, nhưng database session chủ yếu idle in transaction, cần điều tra transaction bị bỏ quên. Nếu database đang chạy query dài hoặc lock wait, cần xử lý query/blocker thay vì chỉ tăng pool.

### 10.2. Metric ở phía database

Đối chiếu:

- Tổng session/connection theo user, application name, host và database.
- Session active, idle, idle in transaction hoặc sleeping.
- Tuổi transaction và tuổi câu lệnh.
- Lock owner, waiter, blocker và wait duration.
- Transaction mở lâu nhất.
- Deadlock, lock timeout và statement cancellation.
- Vacuum/purge/version store, dead tuple hoặc undo history.
- Transaction log/WAL growth và log reuse/truncation wait.

Nên truyền application name, client identifier hoặc trace ID vào database session khi engine/driver hỗ trợ. Nhờ đó, DBA có thể ánh xạ session tới service và instance cụ thể.

## 11. PostgreSQL: tìm phiên idle in transaction

### 11.1. Xem trạng thái session và tuổi transaction

`pg_stat_activity` cung cấp trạng thái backend, thời điểm bắt đầu transaction, thời điểm đổi state, wait event và câu lệnh gần nhất. Ví dụ:

```sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    now() - state_change AS state_age,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event,
    left(query, 200) AS last_query
FROM pg_stat_activity
WHERE state IN ('idle', 'idle in transaction',
                'idle in transaction (aborted)', 'active')
ORDER BY xact_start NULLS LAST;
```

`xact_start` NULL thường cho biết session không có transaction đang mở. `state_age` giúp biết session đã ở trạng thái hiện tại bao lâu; `transaction_age` cho biết transaction đã tồn tại bao lâu. Cần xét các session hệ thống và quyền xem query text theo role.

### 11.2. Xác định blocker

Có thể dùng `pg_blocking_pids(pid)` để xem session đang chặn một backend:

```sql
SELECT
    pid,
    application_name,
    state,
    now() - xact_start AS transaction_age,
    pg_blocking_pids(pid) AS blocking_pids,
    left(query, 200) AS query
FROM pg_stat_activity
WHERE cardinality(pg_blocking_pids(pid)) > 0;
```

Kết quả giúp tìm quan hệ blocking nhưng vẫn cần kiểm tra `pg_locks`, query text và chủ sở hữu ứng dụng trước khi kết thúc session.

### 11.3. Giới hạn idle transaction

PostgreSQL có `idle_in_transaction_session_timeout` để kết thúc session đã nhàn rỗi quá thời gian cho phép trong một transaction. Đây là hàng rào bảo vệ database khỏi transaction bị bỏ quên. Chọn giá trị theo thời gian xử lý hợp lệ của ứng dụng; nếu quá ngắn, có thể ngắt transaction hợp lệ đang chờ bước tiếp theo.

`statement_timeout` giới hạn thời gian câu lệnh, còn `idle_in_transaction_session_timeout` nhắm tới khoảng thời gian session không gửi lệnh trong khi transaction vẫn mở. Hai tham số giải quyết vấn đề khác nhau. Sau khi server kết thúc session, ứng dụng phải loại bỏ connection đó khỏi pool và xử lý request bị lỗi.

## 12. MySQL/InnoDB: session Sleep vẫn có thể giữ transaction

### 12.1. Xem transaction đang mở

`information_schema.innodb_trx` cung cấp transaction InnoDB đang hoạt động. Ví dụ:

```sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS transaction_age_seconds,
    trx_mysql_thread_id,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

Để ánh xạ thread tới session, xem process list hoặc Performance Schema:

```sql
SELECT
    ID,
    USER,
    HOST,
    DB,
    COMMAND,
    TIME,
    STATE,
    LEFT(INFO, 200) AS current_statement
FROM information_schema.processlist
WHERE COMMAND = 'Sleep' OR COMMAND = 'Query'
ORDER BY TIME DESC;
```

Một thread `Sleep` có thể xuất hiện trong `innodb_trx` nếu transaction vẫn mở. Hãy nối bằng `trx_mysql_thread_id` với `ID`, xem tuổi transaction, lock wait và ứng dụng sở hữu session. Câu lệnh và quyền truy cập thay đổi theo phiên bản; MySQL 8 có thể dùng các view Performance Schema hoặc schema `sys` phù hợp.

### 12.2. wait_timeout không thay thế transaction management

`wait_timeout` điều khiển thời gian session không tương tác trước khi server đóng connection trong các điều kiện áp dụng. Khi connection bị đóng, transaction chưa commit sẽ bị rollback. Tuy nhiên, chờ server timeout để giải phóng transaction gây lãng phí tài nguyên trong toàn bộ khoảng chờ và rollback có thể tạo thêm công việc.

Hãy sửa ứng dụng để commit/rollback rõ ràng, đồng thời đặt timeout server làm lớp bảo vệ. Theo dõi transaction age và InnoDB history list length nếu purge bị giữ bởi transaction cũ.

## 13. SQL Server: sleeping session có open transaction

### 13.1. Tìm session và transaction age

Có thể kết hợp `sys.dm_exec_sessions`, `sys.dm_tran_session_transactions`, `sys.dm_tran_active_transactions` và `sys.dm_exec_requests`:

```sql
SELECT
    s.session_id,
    s.login_name,
    s.host_name,
    s.program_name,
    s.status AS session_status,
    s.open_transaction_count,
    at.transaction_begin_time,
    DATEDIFF(SECOND, at.transaction_begin_time, SYSDATETIME())
        AS transaction_age_seconds,
    r.status AS request_status,
    r.wait_type,
    r.wait_time,
    r.blocking_session_id
FROM sys.dm_exec_sessions AS s
LEFT JOIN sys.dm_tran_session_transactions AS st
    ON st.session_id = s.session_id
LEFT JOIN sys.dm_tran_active_transactions AS at
    ON at.transaction_id = st.transaction_id
LEFT JOIN sys.dm_exec_requests AS r
    ON r.session_id = s.session_id
WHERE s.is_user_process = 1
  AND (s.status = 'sleeping' OR s.open_transaction_count > 0)
ORDER BY at.transaction_begin_time;
```

Một session `sleeping` có `open_transaction_count` lớn hơn 0 cần được điều tra. Có thể không có dòng trong `sys.dm_exec_requests` vì session không chạy request nào ở thời điểm truy vấn. Quyền xem DMV phụ thuộc phiên bản và role, ví dụ `VIEW SERVER STATE` hoặc quyền tương ứng ở phiên bản mới.

### 13.2. Kiểm tra tác động lên transaction log và version store

Transaction mở lâu có thể ngăn log truncation/reuse; xem `log_reuse_wait_desc`, log usage và transaction lâu nhất. Nếu dùng snapshot isolation hoặc read committed snapshot, theo dõi version store và transaction snapshot. Không kết luận chỉ từ log file lớn: cần xác định nguyên nhân log reuse wait và hoạt động ghi hiện tại.

### 13.3. Xử lý session bỏ quên

Xác định `session_id`, ứng dụng, host, transaction begin time, câu SQL gần nhất và blocker. Phối hợp với chủ sở hữu ứng dụng để kết thúc transaction đúng cách. `KILL` một session có thể khởi động rollback dài; theo dõi tiến độ rollback và không giả định tài nguyên được giải phóng tức thì.

## 14. Network failure, stale connection và kết quả COMMIT không rõ

### 14.1. Mất kết nối không đồng nghĩa server đã hủy ngay

Khi client mất mạng, process có thể chưa phát hiện socket hỏng ngay. Server có thể tiếp tục chạy query, giữ transaction hoặc giữ lock cho tới khi phát hiện disconnect, TCP timeout, keepalive hoặc một giới hạn server. Ở chiều ngược lại, client có thể timeout và bỏ request trong khi database vẫn đang xử lý.

Đây là lý do cần phối hợp timeout ở ứng dụng, driver, pool, network và database. TCP keepalive giúp phát hiện peer không phản hồi, nhưng không thay thế statement timeout hoặc transaction cleanup.

### 14.2. Commit response bị mất

Một trường hợp khó là server đã commit và flush log thành công nhưng phản hồi bị mất trên mạng. Ứng dụng nhận timeout và không biết transaction đã commit hay chưa. Nếu retry mù, có thể tạo đơn hàng, thanh toán hoặc bút toán trùng.

Các biện pháp:

- Dùng idempotency key duy nhất cho yêu cầu nghiệp vụ.
- Ghi request ID/operation ID trong cùng transaction với dữ liệu.
- Khi retry, tra cứu trạng thái theo key trước khi tạo lại thay đổi.
- Thiết kế API retry có giới hạn và backoff.
- Không coi rollback từ client sau mất mạng là bằng chứng transaction chưa commit.

### 14.3. Pool phải loại connection lỗi

Connection bị server đóng hoặc socket stale không nên được trả lại pool như một connection khỏe. Dùng validation/eviction phù hợp và xử lý exception loại connection theo hướng dẫn pool/driver. Tránh retry trên cùng connection đã hỏng; lấy connection mới và chỉ retry thao tác nếu semantics nghiệp vụ cho phép.

## 15. Xử lý phiên idle in transaction an toàn

Không kết thúc session chỉ vì nó idle lâu. Một phiên có thể thuộc batch job hợp lệ hoặc quy trình quản trị đang chờ. Trước khi can thiệp:

1. Xác định database, user, application name, host và owner.
2. Xem transaction age, state age, câu SQL gần nhất và request hiện tại.
3. Kiểm tra session có giữ lock hoặc chặn giao dịch khác không.
4. Đánh giá tác động tới vacuum/purge, transaction log, version store và replication.
5. Trao đổi với chủ sở hữu dịch vụ để rollback/commit hoặc dừng job đúng cách.
6. Nếu session thực sự bỏ quên và gây sự cố, kết thúc theo quy trình DBA đã duyệt.
7. Theo dõi rollback và xác nhận lock/tài nguyên được giải phóng.
8. Ghi lại session, thời điểm, nguyên nhân và call site cần sửa.

`pg_terminate_backend`, `KILL` trong MySQL hoặc `KILL <session_id>` trong SQL Server là công cụ xử lý cuối cùng, không phải cách quản lý kết nối thường xuyên. Kết thúc session có thể rollback một transaction lớn, tạo I/O và giữ lock trong thời gian rollback. Cần xác định đúng session và đánh giá tác động trước khi chạy.

## 16. Phòng ngừa ở tầng ứng dụng

### 16.1. Thu hẹp transaction scope

Chỉ mở transaction khi cần bảo đảm atomicity cho các thao tác database liên quan. Không mở transaction trước khi:

- Chờ người dùng nhập dữ liệu hoặc xác nhận.
- Gọi API bên ngoài hoặc chờ message broker.
- Tải file, đọc stream từ object storage hoặc gửi email.
- Đợi một task khác trong thread pool.
- Thực hiện tính toán CPU dài không cần giữ snapshot/lock.

Nếu nghiệp vụ trải qua nhiều hệ thống, dùng workflow/state machine, outbox, saga hoặc cơ chế bù trừ phù hợp thay vì giữ một transaction database mở xuyên suốt thời gian gọi mạng.

### 16.2. Cleanup trong mọi đường đi

Kiểm tra các nhánh:

- Thành công bình thường.
- SQL exception và runtime exception.
- Validation fail sau khi transaction đã bắt đầu.
- Early return hoặc cancellation.
- Request timeout hoặc client disconnect.
- Thread bị interrupt.
- Database restart hoặc network reset.
- Commit timeout với outcome không rõ.

Mỗi đường đi phải có hành vi rõ: commit, rollback, đóng statement/result set, đóng handle connection và xử lý connection lỗi. Không để `catch` chỉ ghi log rồi tiếp tục dùng connection trong transaction ở trạng thái không xác định.

### 16.3. Giới hạn thời gian và số hàng

Đặt giới hạn cho query, transaction, streaming và batch. Truy vấn phân trang hoặc đọc theo keyset có thể giảm thời gian giữ cursor so với stream vô hạn. Nếu cần export lớn, cân nhắc snapshot/export chuyên dụng, batch theo khóa hoặc replica đọc; không giữ transaction OLTP trong nhiều phút chỉ để client tải từng dòng chậm.

### 16.4. Kiểm tra connection leak trong kiểm thử

Trong môi trường kiểm thử, đặt pool nhỏ có chủ đích để leak lộ ra sớm; tạo lỗi giữa các bước; kiểm tra active/idle count sau mỗi test; xác nhận connection trả về pool. Leak detection log nên ghi call site và tuổi mượn connection, nhưng không log dữ liệu nhạy cảm hoặc credentials.

## 17. Ví dụ tình huống: pool cạn sau một lỗi nghiệp vụ

Một API xử lý đơn hàng có pool tối đa 30 connection. Sau khi triển khai phiên bản mới, active connection tăng dần lên 30, idle bằng 0 và request mới timeout khi lấy connection. Database cho thấy nhiều session `idle in transaction` có `application_name` của API.

### 17.1. Giả thuyết ban đầu

Một nhánh xử lý lỗi sau khi cập nhật inventory đã ném exception trước khi commit/rollback. Connection được lấy từ pool nhưng không được trả lại hoặc transaction chưa kết thúc. Một số request khác giữ connection trong khi gọi dịch vụ thanh toán bên ngoài.

### 17.2. Đối chiếu số liệu

| Metric | Trước triển khai | Sau triển khai |
|---|---:|---:|
| Pool active | 8–14 | 30 liên tục |
| Pool idle | 16–22 | 0 |
| Pending borrowers | 0 | 45 |
| Connection usage p95 | 120 ms | 18 s |
| DB idle in transaction | 0–1 | 17 |
| Transaction age lớn nhất | 0,8 s | 95 s |

Các số liệu giả định. Chúng cho thấy connection usage duration tăng cùng transaction age và số session idle in transaction; đây là bằng chứng mạnh để điều tra transaction scope và cleanup.

### 17.3. Khắc phục

1. Xác định call site gây lỗi qua leak warning và trace ID.
2. Sửa code dùng try-with-resources và rollback khi exception.
3. Đưa lời gọi thanh toán ra khỏi transaction; ghi outbox hoặc trạng thái chờ xử lý nếu phù hợp nghiệp vụ.
4. Thêm transaction deadline và idle-in-transaction timeout phù hợp.
5. Dừng các session cũ theo quy trình DBA, theo dõi rollback.
6. Kiểm thử exception, timeout và network disconnect.
7. Đo lại pool active/idle, acquisition latency, transaction age và p99 request.

Tăng pool từ 30 lên 100 có thể làm triệu chứng biến mất tạm thời nhưng không sửa leak; nó còn có thể làm database nhận thêm session idle transaction và tăng contention.

## 18. Quy trình điều tra connection leak và transaction bỏ quên

1. **Xác định triệu chứng:** pool acquisition timeout, connection limit, request latency, lock wait hay log/undo growth.
2. **Đọc metric pool:** active/idle/pending, acquisition latency, usage duration, leak warning và connection creation failure.
3. **Đối chiếu database sessions:** group theo user, application, host và state; tìm idle in transaction hoặc sleeping có open transaction.
4. **Xem tuổi transaction:** tìm transaction tồn tại lâu hơn ngưỡng nghiệp vụ; đối chiếu state age và query age.
5. **Kiểm tra blocker và cleanup:** lock graph, vacuum/purge/version store, log reuse và transaction rollback.
6. **Ánh xạ về code:** dùng application name, trace ID, leak stack trace và log transaction boundary.
7. **Xử lý sự cố:** rollback/đóng session có kiểm soát; không kill hàng loạt theo trạng thái đơn lẻ.
8. **Sửa nguyên nhân:** resource management, transaction scope, cancellation, pool reset, timeout và idempotency.
9. **Kiểm thử lỗi:** exception, timeout, client disconnect, network partition, DB restart và commit response bị mất.
10. **Đo lại:** pool usage, DB session age, lock wait, p95/p99 latency, error rate và tính đúng đắn dữ liệu.

## 19. Những lỗi thường gặp

- **Chỉ đóng connection ở cuối method:** exception hoặc early return có thể bỏ qua cleanup; dùng try-with-resources hoặc `finally`.
- **Cho rằng close luôn đóng socket:** với pool, close thường trả handle về pool; cần hiểu reset và eviction.
- **Nhầm idle connection với idle transaction:** idle bình thường có thể được pool giữ; idle transaction vẫn mở transaction và có thể giữ snapshot/lock.
- **Tăng pool ngay khi acquisition timeout:** nếu database đã bão hòa hoặc có leak, pool lớn hơn có thể làm tình hình nặng hơn.
- **Dùng HTTP timeout thay query/transaction timeout:** client dừng chờ không bảo đảm server đã cancel và rollback.
- **Chỉ đặt statement timeout:** transaction có thể vẫn mở sau khi statement bị hủy; ứng dụng cần rollback.
- **Giữ transaction khi gọi API ngoài:** connection và snapshot bị giữ trong thời gian network không xác định.
- **Trả connection khi stream còn mở:** consumer có thể tiếp tục dùng result set sau khi connection đã về pool.
- **Dùng chung JDBC connection nhiều thread:** gây lỗi trạng thái và thứ tự thao tác khó kiểm soát.
- **Dựa vào server idle timeout để cleanup:** chờ tới khi server ngắt kết nối khiến lock và snapshot tồn tại quá lâu.
- **Kill mọi session Sleep:** có thể ngắt connection pool bình thường và không xử lý đúng session có transaction.
- **Retry commit mù:** phản hồi bị mất không chứng minh transaction chưa commit; có thể tạo dữ liệu nghiệp vụ trùng.
- **Không reset session state:** request sau có thể kế thừa isolation, schema, role, timezone hoặc session lock của request trước.
- **Không theo dõi tuổi transaction:** session không chạy query vẫn có thể giữ tài nguyên và cản cleanup.

## 20. Bài tập tự kiểm tra

**Bài 1.** Pool có 40 connection, active luôn bằng 40, idle bằng 0 và pending borrowers tăng. Database cho thấy 25 session `idle in transaction`. Bạn cần kiểm tra gì trước khi tăng pool?

*Gợi ý:* Tuổi transaction, application/host, lock và blocker, call site mượn connection, nhánh exception/rollback, transaction scope và lời gọi mạng nằm trong transaction.

**Bài 2.** Vì sao session `idle` trong PostgreSQL khác `idle in transaction`?

*Gợi ý:* Session idle thường không có transaction đang mở; idle in transaction đã bắt đầu transaction nhưng không gửi lệnh tiếp theo, có thể giữ snapshot/lock và ngăn vacuum dọn phiên bản cũ.

**Bài 3.** Một JDBC method trả về `Stream<Customer>` để caller xử lý sau. Rủi ro vòng đời tài nguyên là gì?

*Gợi ý:* Stream có thể lazy và giữ ResultSet/Statement/Connection cho tới khi tiêu thụ xong. Cần quy định rõ ai đóng stream và tránh giữ connection trong lúc xử lý ngoài database lâu.

**Bài 4.** Ứng dụng timeout khi gọi `commit()`. Vì sao không thể khẳng định transaction đã rollback?

*Gợi ý:* Server có thể đã commit và flush log nhưng phản hồi bị mất. Cần idempotency key hoặc tra cứu operation ID trước khi retry.

**Bài 5.** MySQL process list cho thấy một thread `Sleep` trong 120 giây. Có đủ căn cứ kết luận nó vô hại không?

*Gợi ý:* Chưa đủ. Đối chiếu `innodb_trx` bằng thread ID, transaction age, lock wait và undo/purge impact; Sleep vẫn có thể giữ transaction mở.

**Bài 6.** SQL Server có session `sleeping` với `open_transaction_count=1`. Bạn cần đối chiếu những thông tin nào?

*Gợi ý:* Transaction begin time, host/program/login, request và wait, lock, log reuse wait, version store nếu dùng row versioning; phối hợp owner trước khi kill.

## 21. Ghi nhớ khi tối ưu

Rò rỉ kết nối là lỗi không trả connection về pool; idle connection là trạng thái bình thường nếu pool chủ động giữ; idle in transaction là session đã bắt đầu transaction nhưng chưa commit/rollback. Ba trạng thái này có biểu hiện khác nhau và cần được chẩn đoán bằng cả metric pool lẫn trạng thái transaction ở database.

Hãy quản lý connection bằng try-with-resources hoặc cơ chế tương đương, đóng statement/result set, kết thúc transaction trên mọi đường đi và giữ transaction scope ngắn. Không gọi dịch vụ ngoài trong transaction nếu không có lý do nghiệp vụ rõ ràng; đặt timeout theo đúng tầng; theo dõi connection usage duration, pending borrowers, transaction age, lock wait và cleanup của MVCC/log. Khi xử lý session bị bỏ quên, xác minh owner và tác động trước khi kết thúc. Sau sửa đổi, kiểm thử cả exception, timeout và mất mạng, rồi xác nhận pool được giải phóng, transaction không còn treo và dữ liệu không bị ghi lặp.
