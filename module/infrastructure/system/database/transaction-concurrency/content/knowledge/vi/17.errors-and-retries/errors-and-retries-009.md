# Hủy yêu cầu, hủy câu lệnh và xác minh giao dịch đã kết thúc

Khi người dùng bấm Cancel, client đóng kết nối hoặc ứng dụng hết thời gian chờ, điều đó chưa chắc có nghĩa transaction trong cơ sở dữ liệu đã dừng. Yêu cầu có thể chỉ bị hủy ở tầng HTTP, trong khi câu SQL vẫn chạy ở server. Ngay cả khi câu lệnh đã bị hủy, transaction có thể vẫn còn mở và giữ khóa. Nếu ứng dụng trả connection về pool khi trạng thái transaction chưa rõ, request tiếp theo có thể nhận một connection còn mang transaction cũ.

Muốn hủy an toàn, cần phân biệt ba việc: hủy yêu cầu ở tầng ứng dụng, hủy câu lệnh đang thực thi và kết thúc transaction bằng `COMMIT` hoặc `ROLLBACK`. Sau đó phải xác nhận kết quả ở đúng tầng. Hủy là một yêu cầu điều khiển; rollback hoặc commit mới xác định kết quả dữ liệu.

## 1. Ba tầng hủy thường bị nhầm lẫn

| Tầng | Ví dụ | Điều được yêu cầu dừng | Điều chưa được bảo đảm |
|---|---|---|---|
| Yêu cầu ứng dụng | Người dùng bấm Cancel, HTTP request bị ngắt, cancellation token được kích hoạt. | Công việc xử lý request hoặc tác vụ ứng dụng. | SQL đang chạy ở database có thể vẫn tiếp tục nếu ứng dụng không truyền tín hiệu hủy đến driver. |
| Câu lệnh database | JDBC `Statement.cancel()`, query timeout, lệnh cancel/kill của hệ quản trị. | Câu SQL hoặc batch đang chạy. | Transaction bao quanh câu lệnh có thể vẫn mở; các câu lệnh trước đó có thể đã thực hiện. |
| Transaction | `ROLLBACK`, rollback toàn bộ transaction hoặc đóng session theo hành vi của hệ quản trị. | Các thay đổi chưa commit trong transaction. | Nếu commit đã hoàn tất nhưng phản hồi bị mất, rollback sau đó không thể đảo ngược commit. |

Một thao tác hủy ở tầng trên cần được truyền xuống tầng dưới theo cách phù hợp. Ví dụ, hủy HTTP request không tự động gọi `Statement.cancel()` trong mọi framework. Ngược lại, hủy một câu `UPDATE` không có nghĩa toàn bộ transaction đã rollback.

## 2. Phân biệt trạng thái của yêu cầu và trạng thái của transaction

Một hệ thống nên theo dõi trạng thái riêng cho công việc ứng dụng và transaction database. Một mô hình đơn giản:

```text
REQUEST_RECEIVED
       |
       v
RUNNING ----------------------+
   |                          |
   | Cancel requested         | Work completed
   v                          v
CANCEL_REQUESTED           COMMITTING
   |                          |
   v                          +----> COMMITTED
STATEMENT_CANCELING          |
   |                          +----> COMMIT_FAILED
   v                          |
STATEMENT_CANCELED            +----> OUTCOME_UNKNOWN
   |                          |
   v                          |
ROLLING_BACK <----------------+
   |
   +----> ROLLED_BACK
   |
   +----> ROLLBACK_FAILED / CONNECTION_DISCARDED
```

Đây là mô hình trạng thái khái niệm. Hệ quản trị có thể dùng trạng thái nội bộ khác, và ứng dụng cần phân biệt ít nhất:

- Đã nhận yêu cầu hủy.
- Đã gửi tín hiệu hủy đến driver hoặc database.
- Câu lệnh đã kết thúc hoặc server xác nhận đã hủy.
- Transaction đã commit, rollback hoặc chưa xác định được kết quả.
- Connection còn an toàn để tái sử dụng hay phải loại khỏi pool.

Không nên đổi trạng thái công việc thành `CANCELLED` ngay khi người dùng bấm nút nếu database vẫn đang xử lý. Có thể ghi nhận `CANCEL_REQUESTED` trước, rồi chỉ đánh dấu `CANCELLED` sau khi transaction đã rollback và hệ thống xác nhận không có kết quả nghiệp vụ được commit.

## 3. Hủy yêu cầu ở tầng ứng dụng

Ở tầng HTTP hoặc job runner, ứng dụng thường nhận được một cancellation signal khi client ngắt kết nối, deadline hết hạn hoặc người dùng yêu cầu dừng. Signal này cần được truyền đến phần code đang thực hiện truy vấn.

Pseudocode:

```text
handleRequest(request, cancellationToken):
    cancellationToken.throwIfCancellationRequested()

    result = repository.performWork(cancellationToken)

    cancellationToken.throwIfCancellationRequested()
    return result
```

Kiểm tra cancellation giữa các bước giúp ứng dụng không bắt đầu thêm công việc khi yêu cầu đã bị hủy. Tuy nhiên, nếu `repository.performWork()` đang chờ một câu SQL chạy lâu, chỉ kiểm tra token trước và sau hàm là chưa đủ. Repository hoặc database driver cần có cơ chế hủy câu lệnh đang chạy.

Không nên giả định client disconnect đồng nghĩa với server đã dừng công việc. Một số server tiếp tục xử lý sau khi socket của client đóng; một số framework chỉ ngừng gửi response. Nếu công việc phải dừng để giải phóng tài nguyên, ứng dụng cần quản lý cancellation token và liên kết nó với thao tác database.

## 4. Hủy câu lệnh đang chạy

### 4.1. JDBC `Statement.cancel()`

JDBC cung cấp `Statement.cancel()` để yêu cầu hủy câu lệnh đang thực thi nếu driver và DBMS hỗ trợ. API này thường được gọi từ một luồng khác trong lúc luồng thực thi đang chờ kết quả.

Ví dụ minh họa:

```java
Connection connection = dataSource.getConnection();
connection.setAutoCommit(false);

Statement statement = connection.createStatement();
try {
    // Một luồng khác có thể gọi statement.cancel()
    // khi người dùng yêu cầu dừng.
    statement.execute("UPDATE large_table SET ... WHERE ...");

    connection.commit();
} catch (SQLException error) {
    // Xử lý rollback và trạng thái connection ở phần quản lý transaction.
    throw error;
} finally {
    statement.close();
    connection.close();
}
```

Đây chỉ là ví dụ về vị trí API. Trong ứng dụng thật, cần đồng bộ vòng đời của `Statement` và luồng yêu cầu hủy; không được đóng hoặc tái sử dụng statement tùy tiện trong khi luồng khác đang thực thi. Việc driver hỗ trợ cancel và cách nó gửi tín hiệu đến server phụ thuộc sản phẩm.

`Statement.cancel()` là yêu cầu hủy câu lệnh. Nó không tự gọi `Connection.rollback()` và không chứng minh transaction đã kết thúc. Sau khi câu lệnh dừng, ứng dụng vẫn phải xác định transaction còn hợp lệ, đã bị đánh dấu lỗi hay cần rollback.

### 4.2. Query timeout

JDBC cho phép đặt thời gian chờ thực thi câu lệnh:

```java
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setQueryTimeout(15);
    statement.executeUpdate();
}
```

Khi quá thời hạn, driver sẽ cố gắng hủy câu lệnh và báo lỗi phù hợp. Độ chính xác của timeout, cách gửi cancel và thời gian server thực sự dừng có thể khác nhau giữa driver và DBMS. Timeout không phải cam kết rằng toàn transaction đã rollback.

### 4.3. Lệnh cancel/kill của hệ quản trị

Một số hệ quản trị cho phép gửi tín hiệu hủy câu lệnh theo session hoặc request ID. Cần phân biệt lệnh hủy câu lệnh với lệnh kết thúc session:

- Cancel query thường cố dừng câu lệnh hiện tại nhưng giữ session.
- Kill/terminate session có thể đóng session và làm rollback transaction chưa commit, nhưng có thể gây chi phí cleanup lớn và ảnh hưởng các câu lệnh khác trên cùng session.

Không dùng thao tác terminate session như một cách hủy thông thường nếu driver đã có cơ chế cancel. Cần xác định đúng session/request của công việc cần dừng để không hủy nhầm kết nối đang phục vụ request khác.

## 5. Hủy câu lệnh không đồng nghĩa rollback toàn transaction

Giả sử transaction có ba câu lệnh:

```sql
BEGIN;

UPDATE account
SET balance = balance - 100
WHERE account_id = 1;

UPDATE account
SET balance = balance + 100
WHERE account_id = 2;

INSERT INTO transfer_audit (...);

COMMIT;
```

Nếu câu `INSERT` bị hủy, hai câu `UPDATE` trước đó có thể đã thực hiện trong transaction nhưng chưa commit. Ứng dụng phải rollback transaction nếu nghiệp vụ yêu cầu toàn bộ chuyển tiền và audit thành công cùng nhau.

Hành vi sau khi một câu lệnh bị hủy phụ thuộc DBMS:

- Có hệ quản trị đánh dấu transaction hiện tại ở trạng thái lỗi; các câu lệnh tiếp theo bị từ chối cho đến khi rollback.
- Có hệ quản trị chỉ rollback câu lệnh bị hủy và cho phép transaction tiếp tục, trong khi các thay đổi trước đó vẫn còn chờ commit.
- Một số loại lỗi hoặc cancel có thể khiến connection không còn dùng được.

Vì vậy, không nên viết code dùng chung với giả định rằng mọi database đều tự rollback toàn transaction khi một câu lệnh bị cancel. Sau lỗi, cần thực hiện rollback tường minh nếu transaction còn hoạt động và xác định được trạng thái; nếu không thể xác nhận, hãy loại connection khỏi pool và xử lý kết quả theo quy tắc của driver/DBMS.

## 6. Kết thúc transaction bằng COMMIT hoặc ROLLBACK

Một transaction chỉ có kết quả dữ liệu rõ ràng khi hệ thống xác nhận commit hoặc rollback thành công, hoặc có bằng chứng đáng tin cậy rằng server đã kết thúc transaction theo một kết quả cụ thể.

| Kết quả | Ý nghĩa | Hành động của ứng dụng |
|---|---|---|
| `COMMIT` được xác nhận thành công | Các thay đổi đã commit. | Đánh dấu công việc hoàn tất; không thể coi thao tác đã bị hủy chỉ vì client sau đó đóng kết nối. |
| `ROLLBACK` được xác nhận thành công | Các thay đổi chưa commit trong transaction đã bị hủy. | Đánh dấu công việc đã rollback/cancel; giải phóng hoặc trả connection về pool nếu trạng thái đã sạch. |
| Câu lệnh bị hủy nhưng transaction còn mở | Chỉ câu lệnh hiện tại đã dừng; transaction có thể còn giữ khóa và thay đổi trước đó. | Thực hiện rollback hoặc xử lý tiếp theo đúng quy tắc nghiệp vụ; không trả connection về pool như thể đã xong. |
| Rollback thất bại hoặc mất kết nối | Không xác nhận được trạng thái session/transaction. | Đánh dấu connection không an toàn, loại khỏi pool; xác minh kết quả qua cơ chế độc lập nếu cần. |
| Mất kết nối trong lúc commit | Client không biết server đã commit hay chưa. | Đánh dấu kết quả chưa xác định và đối soát; không retry mù một thao tác không idempotent. |

### Mẫu quản lý transaction

Pseudocode dưới đây nhấn mạnh việc phân biệt commit, rollback và trạng thái không xác định:

```text
connection = pool.borrow()
outcome = NOT_COMMITTED
connectionReusable = true

try:
    beginTransaction(connection)

    executeWork(connection)
    checkCancellation()

    outcome = COMMITTING
    commit(connection)
    outcome = COMMITTED

catch error:
    if outcome == COMMITTING and connectionLostOrCommitResultUnknown(error):
        outcome = UNKNOWN
        connectionReusable = false
    else:
        try:
            rollback(connection)
            outcome = ROLLED_BACK
        catch rollbackError:
            outcome = UNKNOWN
            connectionReusable = false
            recordSuppressed(error, rollbackError)

    raise error

finally:
    if connectionReusable and outcome in [COMMITTED, ROLLED_BACK]:
        returnCleanConnectionToPool(connection)
    else:
        discardPhysicalConnection(connection)
```

Đây là pseudocode, không phải API cụ thể của một pool. Thực tế cần phân loại lỗi theo driver và DBMS. Một lỗi serialization hoặc deadlock có thể là kết quả từ chối rõ ràng, trong khi lỗi mạng đúng lúc `commit()` có thể khiến kết quả chưa xác định.

## 7. Cửa sổ nguy hiểm: client mất phản hồi khi COMMIT

Tình huống khó nhất xảy ra khi ứng dụng gửi `COMMIT`, database đã commit thành công, nhưng kết nối bị đứt trước khi client nhận được phản hồi.

```text
Ứng dụng                 Database
   |                         |
   |------ COMMIT ---------->|
   |                         | Commit transaction
   |                         | Ghi nhận thành công
   |<--- response lost ------X
   |
   +-- Client thấy timeout/mất kết nối
```

Client không thể suy ra từ timeout rằng commit thất bại. Cũng không thể gọi rollback trên một connection đã mất rồi cho rằng dữ liệu được hoàn tác. Transaction có thể đã commit, hoặc server có thể chưa nhận được yêu cầu; kết quả chưa xác định từ góc nhìn client.

Nếu ứng dụng tự động gửi lại thao tác chuyển tiền, tạo đơn hàng hoặc trừ tồn kho, dữ liệu có thể bị ghi hai lần. Cần một định danh nghiệp vụ/idempotency key được lưu trong cùng transaction với thay đổi chính.

Ví dụ:

```sql
CREATE TABLE processed_request (
    request_id VARCHAR(100) PRIMARY KEY,
    result_payload TEXT,
    completed_at TIMESTAMP NOT NULL
);
```

Trong cùng transaction, ứng dụng ghi `request_id` duy nhất và dữ liệu nghiệp vụ. Khi client không biết kết quả commit, nó có thể dùng một connection mới truy vấn `request_id`:

- Nếu đã tồn tại, transaction trước đã ghi nhận yêu cầu; trả lại kết quả đã lưu.
- Nếu chưa tồn tại, cần áp dụng quy trình retry có kiểm soát, vẫn dùng cùng idempotency key để hai lần gửi không tạo hai hiệu ứng.

Việc đối soát cần dựa trên dữ liệu bền vững đã commit, không dựa trên trạng thái trong bộ nhớ của request cũ.

## 8. Xác minh câu lệnh đã dừng

Sau khi gửi cancel, ứng dụng cần biết câu lệnh có thực sự kết thúc hay chưa. Có thể dùng các tín hiệu sau, tùy driver và hệ quản trị:

1. Luồng thực thi nhận được kết quả hoặc exception từ driver, cho biết lời gọi câu lệnh đã kết thúc ở phía client.
2. Driver xác nhận thao tác cancel hoặc trả về trạng thái lỗi cụ thể; đây là tín hiệu cần diễn giải theo tài liệu driver.
3. Công cụ giám sát database cho thấy session/request không còn chạy câu lệnh đó.
4. Một thao tác kiểm tra qua connection độc lập xác nhận dữ liệu hoặc trạng thái công việc phù hợp với kết quả mong đợi.

Không phải mọi driver đều cung cấp một callback “server đã dừng” riêng. Việc `Statement.cancel()` trả về bình thường chỉ cho biết yêu cầu cancel đã được gửi/xử lý theo hợp đồng driver; không nên suy rộng thành bằng chứng transaction đã rollback.

Một câu `SELECT 1` thành công trên connection chỉ chứng minh connection có thể thực thi truy vấn mới. Nó không chứng minh câu lệnh trước đã rollback, transaction cũ đã kết thúc hoặc dữ liệu chưa được commit. Muốn xác nhận kết quả dữ liệu, phải dựa trên kết quả commit/rollback hoặc đối soát nghiệp vụ bền vững.

## 9. Xác minh transaction và connection đã sạch

Trước khi tái sử dụng connection, ứng dụng hoặc connection pool cần biết:

- Không còn câu lệnh đang chạy trên session.
- Transaction trước đã commit hoặc rollback.
- Không còn transaction mở giữ khóa hoặc snapshot.
- Các thuộc tính session đã được reset về trạng thái pool mong đợi, như auto-commit, isolation level, schema, role và session variables.
- Connection vẫn còn hợp lệ và driver không đánh dấu nó là broken.

Không nên chỉ gọi `Connection.getAutoCommit()` rồi kết luận transaction đã kết thúc. Phương thức này trả về chế độ auto-commit, không phải bằng chứng transaction hiện tại không còn hoạt động. Tương tự, `Connection.close()` trong môi trường pool thường trả logical connection về pool; nó không nhất thiết đóng physical session ngay lập tức.

Một pool tốt thường có cơ chế rollback transaction chưa hoàn tất và reset trạng thái session khi connection được trả về. Tuy vậy, nếu rollback thất bại, connection mất kết nối hoặc trạng thái protocol không còn tin cậy, connection cần bị loại bỏ thay vì phát lại cho request khác.

### Quan sát từ database

Khi cần xác minh ở server, dùng công cụ giám sát phù hợp với DBMS để kiểm tra session, query đang chạy, trạng thái transaction và wait event. Ví dụ, PostgreSQL có `pg_stat_activity`; SQL Server có các DMV về session/request và transaction; các sản phẩm khác có view tương ứng.

Các view này có thể cập nhật trễ hoặc chỉ cho thấy trạng thái tại thời điểm lấy mẫu. Chúng hữu ích để điều tra session còn chạy hoặc đang chờ khóa, nhưng kết quả cuối cùng của một thao tác commit vẫn nên được đối soát bằng khóa nghiệp vụ hoặc dữ liệu đã commit.

## 10. Khác biệt giữa các hệ quản trị

Hủy câu lệnh và trạng thái transaction sau lỗi không đồng nhất giữa các DBMS. Một số đặc điểm thường gặp:

| Hệ quản trị | Điểm cần lưu ý |
|---|---|
| PostgreSQL | Cancel query thường dừng câu lệnh hiện tại. Trong transaction block, lỗi câu lệnh thường khiến transaction ở trạng thái aborted cho đến khi `ROLLBACK` hoặc rollback to savepoint phù hợp. Cần kiểm tra session và xử lý transaction lỗi trước khi dùng lại connection. |
| MySQL InnoDB | `KILL QUERY` hủy câu lệnh hiện tại; transaction có thể vẫn tồn tại và các thay đổi từ câu lệnh trước có thể còn chờ commit. `KILL CONNECTION` kết thúc session và rollback transaction chưa commit theo cleanup của engine. |
| SQL Server | Client cancel/attention có thể dừng batch hoặc câu lệnh; trạng thái transaction phụ thuộc lỗi và cấu hình. Cần kiểm tra `XACT_STATE()`/`@@TRANCOUNT` trong ngữ cảnh còn kết nối và rollback khi cần. |
| Oracle Database | Cancel câu SQL thường kết thúc câu lệnh hiện tại; transaction chưa commit có thể vẫn còn và các thay đổi trước đó vẫn tồn tại. Cần rollback tường minh nếu muốn hủy toàn bộ transaction. |

Bảng chỉ nêu hành vi cần lưu ý ở mức khái quát. Driver, phiên bản, loại lỗi, savepoint, distributed transaction và cấu hình có thể làm chi tiết khác đi. Trước khi triển khai cancellation, hãy kiểm tra tài liệu chính thức của đúng DBMS và driver.

## 11. Hủy khi đang ở giữa nhiều câu lệnh

Một transaction có thể có nhiều giai đoạn:

```text
BEGIN
  SELECT dữ liệu
  UPDATE hàng A
  UPDATE hàng B
  INSERT audit
COMMIT
```

Nếu cancellation đến sau `UPDATE A` nhưng trước `UPDATE B`, ứng dụng cần quyết định:

- Nếu các bước phải nguyên tử, rollback toàn transaction.
- Nếu đã có một ranh giới commit trước đó, không thể rollback phần đã commit; cần ghi nhận trạng thái một phần và tiếp tục/compensate theo nghiệp vụ.
- Nếu câu lệnh hiện tại chỉ là một bước tùy chọn, có thể rollback về savepoint nếu DBMS và thiết kế transaction hỗ trợ, rồi tiếp tục theo một nhánh được định nghĩa trước.

Savepoint không tương đương transaction mới. Rollback về savepoint chỉ hủy các thay đổi sau savepoint; các thay đổi trước đó vẫn nằm trong transaction và vẫn cần commit hoặc rollback cuối cùng.

Ví dụ:

```sql
BEGIN;

UPDATE orders
SET status = 'PROCESSING'
WHERE order_id = :order_id;

SAVEPOINT optional_step;

-- Một bước phụ có thể bị hủy.
UPDATE order_summary
SET recalculated = TRUE
WHERE order_id = :order_id;

-- Nếu chỉ bước phụ bị lỗi và nghiệp vụ cho phép:
ROLLBACK TO SAVEPOINT optional_step;

-- Transaction vẫn mở; cần quyết định commit hay rollback.
COMMIT;
```

Không nên dùng savepoint để che giấu một lỗi làm mất invariant cốt lõi. Chỉ tiếp tục commit nếu trạng thái còn lại được nghiệp vụ cho phép.

## 12. Cancellation token và timeout phải có giới hạn

Một request có thể có nhiều deadline: HTTP timeout, application deadline, pool acquisition timeout, query timeout và transaction timeout. Các giới hạn này cần phối hợp để ứng dụng có đủ thời gian hủy câu lệnh, rollback và giải phóng connection trước khi request bị đóng hoàn toàn.

Ví dụ, nếu HTTP deadline là 10 giây nhưng query timeout là 30 giây, client có thể ngắt kết nối trước khi database nhận cancel. Nếu query timeout là 10 giây nhưng rollback cleanup cần thêm thời gian, request có thể hết hạn trước khi connection được làm sạch.

Thiết kế nên dành một khoảng thời gian cho cleanup:

```text
Request deadline:       20 s
  Work/query budget:    16 s
  Cancel + rollback:     3 s
  Response/cleanup:      1 s
```

Các con số chỉ minh họa. Hãy chọn dựa trên latency thực tế và SLA. Khi deadline hết, cancellation handler nên có thời gian giới hạn để gửi cancel và rollback; nếu cleanup không hoàn tất, đánh dấu connection để discard và để hệ quản trị hoàn tất việc thu hồi session.

## 13. Không để cancellation gây ra thao tác phụ trùng lặp

Cancellation có thể xảy ra sau khi database đã commit nhưng trước khi ứng dụng gửi response. Người dùng có thể bấm lại hoặc client tự retry vì tưởng request thất bại. Vì vậy, thao tác có tác dụng phụ cần idempotency key hoặc một mã nghiệp vụ duy nhất.

Một quy trình an toàn thường gồm:

1. Client gửi một operation ID ổn định cho lần yêu cầu logic.
2. Transaction ghi operation ID và thay đổi dữ liệu nghiệp vụ trong cùng commit.
3. Nếu client mất kết nối, lần gửi lại dùng cùng operation ID.
4. Server kiểm tra operation ID đã được xử lý chưa và trả lại kết quả đã lưu nếu có.
5. Tác dụng phụ bên ngoài được phát qua outbox hoặc cơ chế idempotent tương đương.

Nếu thao tác đã commit, cancellation của response không đảo ngược dữ liệu. API cần thể hiện trạng thái kết quả có thể đã hoàn tất và cho phép client truy vấn theo operation ID.

## 14. Quy trình xử lý một yêu cầu hủy an toàn

Một quy trình tổng quát có thể đi theo các bước:

1. Ghi nhận `CANCEL_REQUESTED` cho đúng operation ID.
2. Ngăn ứng dụng bắt đầu thêm câu lệnh hoặc bước xử lý mới.
3. Nếu có câu lệnh đang chạy, gọi cơ chế cancel của driver/DBMS và chờ lời gọi thực thi kết thúc trong thời hạn cleanup.
4. Phân loại lỗi trả về: query canceled, deadlock, serialization failure, timeout, connection loss hay lỗi nghiệp vụ.
5. Nếu transaction chưa commit và còn điều khiển được connection, thực hiện `ROLLBACK` hoặc rollback về savepoint theo quy tắc nghiệp vụ.
6. Xác nhận rollback thành công; nếu không xác nhận được, đánh dấu kết quả chưa xác định và loại connection khỏi pool.
7. Nếu lỗi xảy ra trong lúc commit hoặc mất phản hồi commit, đối soát operation ID bằng connection mới trước khi retry.
8. Chỉ đánh dấu công việc `CANCELLED` sau khi biết không có kết quả commit cần giữ; nếu commit đã thành công, trả trạng thái hoàn tất thay vì báo hủy thành công.
9. Ghi log thời điểm gửi cancel, thời điểm câu lệnh dừng, kết quả rollback/commit, session ID và lý do discard connection.

## 15. Checklist trước khi triển khai hủy transaction

- [ ] Đã phân biệt hủy HTTP/request, hủy câu lệnh và rollback transaction.
- [ ] Cancellation token được truyền đến lớp database đang thực thi truy vấn.
- [ ] Driver và DBMS hỗ trợ cơ chế cancel đã chọn.
- [ ] Query timeout, request deadline và thời gian cleanup được phối hợp.
- [ ] Sau khi câu lệnh bị hủy, ứng dụng xác định transaction còn hoạt động hay đã ở trạng thái lỗi.
- [ ] Rollback được thực hiện tường minh khi cần và có kiểm tra lỗi rollback.
- [ ] Connection có trạng thái không chắc chắn được loại khỏi pool.
- [ ] Không dùng `getAutoCommit()` hoặc `SELECT 1` làm bằng chứng transaction đã kết thúc.
- [ ] Mất kết nối trong lúc commit được xem là kết quả có thể chưa xác định.
- [ ] Thao tác có tác dụng phụ có idempotency key hoặc cơ chế đối soát.
- [ ] Có giám sát session/query đang chạy, lock wait và transaction còn mở.
- [ ] Đã kiểm thử cancel trước khi chạy, giữa câu lệnh, giữa hai câu lệnh, trong lúc rollback và trong lúc commit.

Hủy một yêu cầu chỉ là bước đầu. Ứng dụng phải dừng câu lệnh đang chạy, kết thúc transaction theo đúng ngữ nghĩa của hệ quản trị và xác định connection có an toàn để tái sử dụng hay không. Đặc biệt, khi mất phản hồi trong lúc commit, kết quả có thể chưa xác định từ phía client; hãy đối soát bằng operation ID và thiết kế idempotent thay vì đoán rằng transaction đã rollback.
