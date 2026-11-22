# Tiêm lỗi mất kết nối quanh thời điểm COMMIT

Một transaction có thể thực hiện tất cả câu `INSERT`, `UPDATE` và `DELETE` mà không báo lỗi, nhưng ứng dụng vẫn không biết kết quả cuối cùng nếu kết nối bị mất đúng lúc gọi `COMMIT`. Database có thể đã commit và chỉ mất phản hồi xác nhận trên đường về. Cũng có thể lệnh commit chưa đến server hoặc transaction chưa hoàn tất và cuối cùng bị rollback.

Đây là một trường hợp quan trọng cần kiểm thử trong hệ thống giao dịch. Chỉ kiểm thử câu lệnh SQL thành công hoặc cố ý ném exception trước commit không mô phỏng được tình huống client mất ACK sau khi database đã commit. Muốn kiểm tra đúng, cần điều khiển thời điểm lỗi ở cả hai chiều kết nối, quan sát trạng thái bền vững từ một connection độc lập và xác nhận retry không thực hiện nghiệp vụ lần thứ hai.

Bài học này trình bày các điểm có thể tiêm lỗi quanh commit, cách dựng môi trường kiểm thử có thể điều khiển, những kịch bản cần chạy, cách viết kiểm thử Java/JDBC và các nguyên tắc phục hồi bằng idempotency key.

## 1. Vì sao cần tiêm lỗi quanh COMMIT?

Trong một transaction thông thường, ứng dụng gửi các câu lệnh ghi rồi gửi `COMMIT`. Nếu database xác nhận commit và client nhận được phản hồi, ứng dụng có thể trả kết quả thành công. Nhưng commit đi qua mạng nên có hai sự kiện riêng:

1. Database hoàn tất commit.
2. Client nhận được phản hồi xác nhận commit.

Hai sự kiện này không xảy ra nguyên tử ở phía client. Kết nối có thể đứt giữa chúng.

Ví dụ chuyển 100.000 đồng:

```text
Application                         Database
    |                                  |
    | BEGIN                            |
    |--------------------------------->|
    | UPDATE account                   |
    |--------------------------------->|
    | COMMIT                           |
    |--------------------------------->|
    |                           Commit hoàn tất
    |                           Gửi phản hồi thành công
    X Kết nối bị reset trước khi nhận ACK
```

Database có thể đã trừ tiền và ghi nhận giao dịch thành công. Client lại nhận `SQLException` hoặc lỗi kết nối. Nếu ứng dụng hiểu lỗi đó là “chắc chắn rollback” rồi tạo một yêu cầu chuyển tiền mới, số tiền có thể bị trừ hai lần.

Kiểm thử fault injection nhằm trả lời các câu hỏi thực tế:

- Nếu connection đứt trước khi server nhận `COMMIT`, transaction có được rollback không?
- Nếu lệnh `COMMIT` đã được gửi nhưng phản hồi bị mất, ứng dụng có nhận biết kết quả chưa xác định không?
- Nếu database đã commit nhưng client không nhận ACK, retry cùng yêu cầu có trả lại kết quả cũ không?
- Nếu database process dừng trong lúc commit, dữ liệu có phục hồi theo durability configuration không?
- Nếu HTTP response bị mất sau khi transaction đã commit, request retry từ người dùng có tạo tác dụng lần thứ hai không?

## 2. Phân biệt các điểm lỗi quanh commit

Không phải mọi lỗi kết nối quanh commit đều tương đương. Cần xác định chính xác lỗi được tiêm ở đâu.

| Điểm tiêm lỗi | Điều gì đã xảy ra? | Kết quả phía client |
| --- | --- | --- |
| Trước khi gửi `COMMIT` | Các câu lệnh có thể đã chạy trong transaction nhưng commit chưa được gửi | Nếu session đóng và server rollback, transaction không commit; cần xác nhận bằng trạng thái bền vững |
| Khi gửi `COMMIT`, chưa biết server nhận hay chưa | Một phần hoặc toàn bộ lệnh có thể đã đến server | Kết quả chưa xác định |
| Server đã nhận `COMMIT`, chưa biết commit hoàn tất hay chưa | Database đang xử lý quyết định commit | Kết quả chưa xác định nếu kết nối mất trước phản hồi rõ ràng |
| Database đã commit, ACK bị chặn hoặc mất | Thay đổi đã bền vững theo cấu hình database | Client vẫn có thể nhận timeout/reset và không biết commit thành công |
| ACK đã đến client, HTTP response bị mất | Transaction đã commit và ứng dụng có thể đã nhận kết quả | Người gọi API không biết kết quả; cần idempotency ở tầng API |
| Database process/crash xảy ra trong lúc commit | Phục hồi phụ thuộc log, engine và durability configuration | Cần kiểm tra sau recovery; không suy luận từ exception của client |

Trong kiểm thử, hãy ghi rõ kịch bản đang mô phỏng điểm nào. Một test chỉ ngắt kết nối trước khi gọi `commit()` không chứng minh hệ thống xử lý được trường hợp database đã commit nhưng ACK bị mất.

## 3. Hai hướng dữ liệu qua mạng phải được kiểm soát riêng

Kết nối JDBC là một luồng trao đổi hai chiều:

- **Client → database:** request SQL, tham số, lệnh `COMMIT` và các thông điệp giao thức khác.
- **Database → client:** kết quả câu lệnh, lỗi SQL, thông báo hoàn tất commit và trạng thái session.

Để mô phỏng đúng lỗi quanh commit, cần phân biệt:

1. Chặn request `COMMIT` trước khi nó tới database.
2. Cho request `COMMIT` tới database nhưng chặn phản hồi đi về client.
3. Đóng hoặc reset cả hai hướng, khiến client và server phát hiện connection mất ở những thời điểm khác nhau.

Một TCP proxy nằm giữa ứng dụng và database giúp điều khiển hai hướng này. Proxy có thể chuyển tiếp dữ liệu bình thường, tạm dừng một chiều, loại bỏ dữ liệu, đóng socket hoặc reset connection theo tín hiệu từ test.

Sơ đồ môi trường:

```text
Java test / JDBC client
          |
          v
Controllable TCP proxy
    |             ^
    | app -> DB   | DB -> app
    v             |
     Database server
          ^
          |
Independent observer connection
```

Connection observer đi thẳng đến database, không qua proxy bị lỗi. Nó dùng để kiểm tra một operation record đã commit hay chưa. Nếu observer cũng đi qua proxy đang bị chặn, test sẽ không thể phân biệt trạng thái database với trạng thái mạng.

## 4. Chọn công cụ fault injection

Có thể tiêm lỗi ở nhiều lớp. Mỗi lớp kiểm tra một điều khác nhau.

### Wrapper ở tầng ứng dụng hoặc JDBC

Một wrapper quanh `Connection` có thể ném exception ngay trước khi gọi delegate `commit()`. Cách này hữu ích để kiểm thử nhánh xử lý lỗi trong code, nhưng không mô phỏng mất kết nối thật. Server chưa nhận lệnh commit vì wrapper không chuyển tiếp nó.

Wrapper cũng có thể gọi `delegate.commit()` thành công rồi ném exception giả lập cho caller. Điều này mô phỏng logic “database đã commit nhưng ứng dụng không nhận ACK”, nhưng không kiểm tra TCP, driver, socket hay connection pool.

### TCP proxy có thể điều khiển

Một proxy như Toxiproxy hoặc một proxy kiểm thử tự viết có thể thêm latency, đóng kết nối, reset peer hoặc chặn dữ liệu theo hướng. Proxy phù hợp để kiểm thử driver và ứng dụng với lỗi mạng thực tế.

Đối với kịch bản mất ACK sau commit, proxy cần:

1. Cho phép request `COMMIT` đi từ client đến database.
2. Chặn phản hồi từ database về client.
3. Cho một observer độc lập xác nhận operation record đã nhìn thấy trên primary.
4. Sau khi observer xác nhận commit, reset hoặc đóng kết nối phía client.

Không nên chỉ ngủ một khoảng thời gian cố định rồi ngắt socket. Thời gian commit thay đổi theo tải, filesystem và trạng thái database. Dùng barrier hoặc observer để đồng bộ test sẽ đáng tin cậy hơn.

### Dừng database process hoặc container

Dừng database process trong lúc transaction commit kiểm tra khả năng recovery của engine và storage. Đây là thử nghiệm crash recovery, khác với chỉ mất ACK ở mạng. Nó cần môi trường test cô lập, dữ liệu có thể tạo lại và quy trình khởi động database sau sự cố.

### Network emulation

Các công cụ như `tc netem` có thể tạo latency, packet loss hoặc gián đoạn mạng trên môi trường Linux. Chúng hữu ích cho thử nghiệm chaos nhưng thời điểm lỗi thường ít chính xác hơn proxy có barrier. Cần bảo đảm chỉ tác động vào network namespace hoặc container dành cho test.

Không dùng fault injection trên database production hoặc trên connection chứa dữ liệu người dùng thật. Một test reset socket có thể làm hỏng nhiều request đang dùng chung proxy hoặc pool nếu phạm vi cấu hình sai.

## 5. Chuẩn bị dữ liệu để xác định kết quả commit

Không thể xác định transaction đã commit hay chưa chỉ bằng exception ở client. Test cần một dấu vết bền vững được ghi trong **cùng transaction** với thay đổi nghiệp vụ.

Ví dụ bảng operation:

```sql
CREATE TABLE transfer_operation (
    request_id       VARCHAR(80) PRIMARY KEY,
    payload_hash     VARCHAR(128) NOT NULL,
    from_account_id  BIGINT NOT NULL,
    to_account_id    BIGINT NOT NULL,
    amount           DECIMAL(18, 2) NOT NULL,
    status           VARCHAR(20) NOT NULL,
    transfer_id      BIGINT,
    created_at       TIMESTAMP NOT NULL,
    CONSTRAINT ck_transfer_operation_amount CHECK (amount > 0),
    CONSTRAINT ck_transfer_operation_status
        CHECK (status IN ('PROCESSING', 'COMPLETED', 'REJECTED'))
);
```

`request_id` là khóa duy nhất đại diện cho một ý định nghiệp vụ. Nếu operation record và thay đổi tài khoản cùng nằm trong một transaction:

- Nếu transaction commit, operation record và thay đổi tài khoản cùng tồn tại.
- Nếu transaction rollback, cả operation record và thay đổi tài khoản đều không tồn tại.

Observer có thể tìm `request_id` trên primary bằng connection mới. Đây là cách kiểm tra kết quả bền vững thay vì đoán từ loại exception.

Không commit riêng một hàng `PROCESSING` trước khi làm nghiệp vụ nếu chưa thiết kế lease, timeout và recovery cho trạng thái đó. Nếu operation record được commit trong transaction riêng, việc record tồn tại không còn chứng minh transaction nghiệp vụ đã hoàn tất.

## 6. Thiết kế transaction có idempotency key

Một transaction chuyển tiền có thể ghi operation record, cập nhật hai tài khoản và lưu kết quả trong cùng transaction:

```sql
BEGIN;

INSERT INTO transfer_operation (
    request_id, payload_hash,
    from_account_id, to_account_id, amount,
    status, created_at
)
VALUES (
    :request_id, :payload_hash,
    :from_id, :to_id, :amount,
    'PROCESSING', CURRENT_TIMESTAMP
);

UPDATE account
SET balance = balance - :amount
WHERE account_id = :from_id
  AND balance >= :amount;
-- Phải kiểm tra đúng một hàng được cập nhật.

UPDATE account
SET balance = balance + :amount
WHERE account_id = :to_id;
-- Phải kiểm tra đúng một hàng được cập nhật.

INSERT INTO transfer_ledger(request_id, from_account_id, to_account_id, amount)
VALUES (:request_id, :from_id, :to_id, :amount);

UPDATE transfer_operation
SET status = 'COMPLETED',
    transfer_id = :transfer_id
WHERE request_id = :request_id;

COMMIT;
```

Đây là SQL khái quát; trong ứng dụng thực tế cần xác nhận tài khoản tồn tại, kiểm tra tài khoản nguồn và đích khác nhau nếu nghiệp vụ yêu cầu, khóa tài khoản theo thứ tự nhất quán và xử lý mọi lỗi bằng rollback. Operation record chỉ được chèn sau khi đã xác định request hợp lệ, hoặc có thể lưu kết quả từ chối theo một transaction/contract riêng.

Khi client retry cùng `request_id`:

1. Server thử ghi nhận request ID duy nhất.
2. Nếu INSERT thành công, transaction mới có quyền xử lý request đó.
3. Nếu gặp unique violation vì request đã commit, server đọc operation record bằng connection mới và trả lại kết quả đã lưu.
4. Nếu transaction đầu tiên vẫn đang xử lý, unique check có thể phải chờ transaction đó commit hoặc rollback.
5. Nếu transaction đầu tiên rollback, request retry có thể chèn cùng key và thực hiện nghiệp vụ.

Payload hash hoặc các trường nghiệp vụ được lưu phải được so sánh. Dùng cùng key nhưng đổi tài khoản hoặc số tiền phải bị từ chối; server không được trả kết quả của một request khác.

## 7. Kịch bản A: mất kết nối trước khi gửi COMMIT

Mục tiêu là xác nhận một transaction chưa gửi commit không tạo ra thay đổi đã commit.

Trình tự kiểm thử:

1. Tạo một `request_id` mới và ghi nhận số dư ban đầu.
2. Mở transaction qua proxy.
3. Thực hiện các câu UPDATE và INSERT operation record.
4. Dừng test ngay trước lời gọi `connection.commit()`.
5. Reset connection phía client mà không chuyển tiếp lệnh COMMIT.
6. Chờ database phát hiện session đã đóng và hoàn tất rollback.
7. Dùng observer connection trực tiếp đọc operation record và số dư.
8. Retry cùng `request_id` bằng một connection mới.
9. Xác nhận thao tác mới có thể commit đúng một lần.

Kết quả mong đợi:

- Operation record của transaction đầu tiên không tồn tại sau khi server đã xử lý disconnect/rollback.
- Số dư không phản ánh một lần chuyển tiền chưa commit.
- Retry cùng key tạo đúng một transfer record và cập nhật số dư một lần.

Không kiểm tra operation record ngay lập tức rồi kết luận rollback nếu server chưa kịp phát hiện connection mất. Hãy đợi trạng thái session được giải quyết hoặc dùng retry cùng key để unique constraint phối hợp với transaction cũ. Việc “không tìm thấy record tại một thời điểm” không phải lúc nào cũng là bằng chứng đầy đủ rằng request cũ không còn đang xử lý.

## 8. Kịch bản B: mất kết nối khi COMMIT đang được gửi

Mục tiêu là mô phỏng tình huống client không biết lệnh commit có đến server hay không.

Trình tự:

1. Bắt đầu transaction và thực hiện các thay đổi nghiệp vụ.
2. Cho test gọi `commit()`.
3. Proxy chuyển tiếp một phần hoặc toàn bộ dữ liệu client → database, sau đó reset connection ở một thời điểm được điều khiển.
4. Không giả định server đã nhận hoặc chưa nhận commit.
5. Ghi nhận exception phía client và đánh dấu operation là `UNKNOWN` ở tầng xử lý request nếu cần.
6. Mở observer connection trực tiếp đến primary để tra cứu operation record.
7. Nếu chưa thể xác định vì transaction cũ còn đang được giải quyết, chờ hoặc retry cùng idempotency key.
8. Xác nhận cuối cùng chỉ có một tác dụng nghiệp vụ.

Đây là kịch bản cần chấp nhận cả hai kết quả hợp lệ: transaction đầu tiên commit hoặc transaction đầu tiên rollback. Điều bắt buộc là ứng dụng không tạo tác dụng kép khi kết quả ban đầu chưa rõ.

Không viết assertion rằng mọi lần reset tại điểm này phải rollback. Kết quả phụ thuộc thời điểm byte commit được server nhận và thời điểm server hoàn tất transaction.

## 9. Kịch bản C: database đã COMMIT nhưng ACK bị mất

Đây là kịch bản quan trọng nhất để kiểm tra idempotency. Test phải chứng minh database commit xong trước khi cắt kết nối phía client.

Trình tự có thể điều khiển bằng proxy và observer:

1. Client gửi transaction qua proxy, dùng `request_id` cố định.
2. Client gọi `COMMIT`.
3. Proxy chuyển tiếp dữ liệu client → database.
4. Proxy tạm chặn chiều database → client để phản hồi commit không đến được JDBC client.
5. Observer connection độc lập liên tục truy vấn primary theo `request_id`.
6. Khi observer nhìn thấy operation record đã commit, test đã có bằng chứng database hoàn tất transaction.
7. Proxy reset connection phía client trước khi mở luồng phản hồi bị chặn.
8. JDBC client nhận lỗi kết nối hoặc timeout dù database đã commit.
9. Client retry cùng `request_id` qua connection mới.
10. Server nhận ra key đã tồn tại, đọc kết quả cũ và trả cùng transfer ID.
11. Test xác nhận số dư và ledger chỉ phản ánh một lần chuyển tiền.

Sơ đồ:

```text
JDBC client          Proxy             Database        Observer
    |                  |                   |                |
    |--- COMMIT ------>|                   |                |
    |                  |--- COMMIT ------->|                |
    |                  |                   | commit xong    |
    |                  |<-- ACK (giữ lại) -|                |
    |                  |                   |<-- SELECT -----|
    |                  |                   |--- operation ->|
    |                  |<------------------------------ thấy committed
    |<-- RESET --------|                   |                |
    | SQLException     |                   |                |
    |                  |                   |                |
    |--- retry same request_id ----------->|                |
    |<-- kết quả đã lưu -------------------|                |
```

Nếu observer chỉ thấy operation record sau khi transaction commit, test có thể khẳng định ACK đã bị mất sau commit. Để tránh race, proxy phải tiếp tục giữ phản hồi cho đến khi observer xác nhận rồi mới reset phía client.

Kết quả mong đợi:

- Client ban đầu có thể nhận exception; đây không phải lỗi test.
- Operation record tồn tại trên primary.
- Retry cùng key không tạo transfer record mới.
- Response retry trả cùng `transfer_id` hoặc kết quả đã lưu.
- Tổng số lần thay đổi số dư đúng bằng một lần nghiệp vụ.

## 10. Kịch bản D: database process dừng trong lúc COMMIT

Mất kết nối mạng và database crash là hai fault model khác nhau. Khi database process dừng, transaction có thể đang ở nhiều giai đoạn: chưa ghi commit record, đã ghi commit record nhưng chưa flush bền vững theo cấu hình, hoặc đã hoàn tất commit.

Kiểm thử crash recovery cần:

1. Chạy database trong container hoặc VM dành riêng cho test.
2. Tạo dữ liệu ban đầu và operation ID duy nhất.
3. Dùng hook/observer để dừng database ở các điểm có thể kiểm soát quanh commit nếu engine hỗ trợ; nếu không, lặp lại thử nghiệm chaos có ghi nhận giới hạn về độ xác định thời điểm.
4. Khởi động lại database và chờ recovery hoàn tất.
5. Kết nối mới đến primary và kiểm tra operation record, ledger và số dư.
6. Retry cùng request ID và xác nhận không tạo tác dụng kép.

Kết quả phụ thuộc database engine, filesystem, storage và `synchronous`/durability settings. Không nên tuyên bố mọi database đều phải giữ mọi commit đã xác nhận trong mọi kiểu power loss nếu cấu hình durability đã cho phép trade-off. Test phải ghi lại cấu hình được dùng.

Không dùng lệnh kill hoặc xóa volume tùy tiện trên môi trường chứa dữ liệu cần giữ. Mục tiêu là kiểm thử recovery, nên dữ liệu và storage phải hoàn toàn disposable.

## 11. Kịch bản E: database commit thành công nhưng HTTP response bị mất

Có một cửa sổ lỗi nằm sau JDBC commit:

```text
Application -> Database: COMMIT
Database -> Application: ACK thành công
Application: đã commit, chuẩn bị HTTP 200
Network: mất HTTP response
Client: timeout và gửi lại request
```

Trong kịch bản này, ứng dụng có thể biết transaction đã commit, nhưng client cuối cùng không biết. Tầng API cũng phải dùng idempotency key ổn định. Nếu chỉ database service có idempotency mà gateway tạo request ID mới cho mỗi lần nhận request HTTP, duplicate vẫn có thể xảy ra.

Test nên gửi cùng một API request hai lần với cùng idempotency key, chủ động drop response lần đầu sau khi service commit, rồi xác nhận lần hai trả kết quả cũ và không tạo đơn hàng/thanh toán thứ hai.

## 12. Dựng test Java/JDBC với hai connection

Một test cần ít nhất hai connection độc lập:

- **Connection nghiệp vụ:** đi qua proxy có thể reset/chặn kết nối.
- **Connection observer:** kết nối trực tiếp đến primary để kiểm tra operation record.

Ví dụ phần nghiệp vụ JDBC:

```java
void executeTransfer(
        Connection connection,
        String requestId,
        long fromId,
        long toId,
        BigDecimal amount) throws SQLException {

    connection.setAutoCommit(false);

    try {
        insertOperation(connection, requestId, fromId, toId, amount);
        debit(connection, fromId, amount);
        credit(connection, toId, amount);
        insertLedger(connection, requestId, fromId, toId, amount);

        connection.commit();
    } catch (SQLException | RuntimeException ex) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            ex.addSuppressed(rollbackError);
        }
        throw ex;
    }
}
```

Đây là khung minh họa. Trong trường hợp lỗi mạng xảy ra bên trong `commit()`, lệnh `rollback()` tiếp theo có thể cũng thất bại và không thể chứng minh transaction đã rollback. Connection đó phải được xem là hỏng và loại khỏi pool; trạng thái nghiệp vụ cần được tra cứu bằng connection mới.

Phần observer:

```java
Optional<TransferResult> findCommittedOperation(
        DataSource observerDataSource,
        String requestId) throws SQLException {

    try (Connection connection = observerDataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(
             "SELECT transfer_id, status " +
             "FROM transfer_operation WHERE request_id = ?")) {

        statement.setString(1, requestId);

        try (ResultSet result = statement.executeQuery()) {
            if (!result.next()) {
                return Optional.empty();
            }

            return Optional.of(new TransferResult(
                result.getLong("transfer_id"),
                result.getString("status")
            ));
        }
    }
}
```

Observer phải đọc primary hoặc một nguồn có consistency đủ mạnh. Nếu đọc replica bất đồng bộ, replica có thể chưa nhận commit mới và trả kết quả rỗng dù primary đã commit.

## 13. Pseudocode cho test mất ACK sau commit

API của proxy và test framework khác nhau, vì vậy đoạn dưới mô tả thứ tự phối hợp chứ không giả định một thư viện cụ thể:

```java
@Test
void retryAfterCommitAckWasDroppedDoesNotDuplicateTransfer() {
    String requestId = "test-transfer-ack-lost-001";

    proxy.forwardClientToDatabase();
    proxy.blockDatabaseToClientResponses();

    Future<?> firstAttempt = executor.submit(() -> {
        try (Connection connection = proxiedDataSource.getConnection()) {
            executeTransfer(connection, requestId, 100, 200,
                            new BigDecimal("50000"));
        } catch (SQLException expectedNetworkFailure) {
            // Test mong đợi connection bị reset sau khi database commit.
        }
    });

    observer.awaitCommittedOperation(requestId, timeout);
    proxy.resetClientSideConnection();
    await(firstAttempt);

    TransferResult retryResult = service.retry(
        requestId, 100, 200, new BigDecimal("50000"));

    assertEquals(observer.transferId(requestId), retryResult.transferId());
    assertEquals(1, observer.countOperations(requestId));
    assertBalancesReflectExactlyOneTransfer(100, 200);
    assertEquals(1, observer.countLedgerEntries(requestId));
}
```

`proxy`, `observer` và `service.retry()` ở đây là các thành phần test/application do dự án xây dựng, không phải API có sẵn của JUnit. Điểm quan trọng là test đợi observer xác nhận commit trước khi reset connection và chỉ sau đó mới retry cùng key.

Trong triển khai thực tế, không nên bắt mọi `SQLException` rồi coi là kết quả mong đợi. Hãy xác nhận lỗi thực sự thuộc loại connection reset/timeout do fault injector tạo ra; lỗi constraint, authentication hoặc SQL syntax phải làm test thất bại.

## 14. Kiểm thử retry cùng key khi transaction cũ chưa được giải quyết

Một test khác cần cho thấy retry không gây tác dụng kép ngay cả khi transaction cũ vẫn đang được server xử lý.

1. T1 chèn operation record với `request_id = K` và thực hiện thay đổi nghiệp vụ.
2. Proxy làm client T1 mất kết nối sau khi server nhận COMMIT nhưng trước khi client biết kết quả.
3. Trước khi server hoàn tất hoặc rollback T1, T2 gửi lại cùng key K.
4. Unique constraint trên `request_id` khiến T2 phải phối hợp với transaction đang giữ key hoặc nhận kết quả duplicate sau khi T1 kết thúc.
5. Nếu T1 commit, T2 đọc kết quả đã lưu.
6. Nếu T1 rollback, T2 có thể trở thành transaction xử lý request K.
7. Xác nhận chỉ một operation cuối cùng được commit.

Kịch bản này kiểm tra tính đúng đắn của unique key và transaction boundary. Nó cũng phát hiện thiết kế sai trong đó operation record được commit riêng trước thay đổi nghiệp vụ hoặc request key không được ràng buộc duy nhất.

## 15. Timeout, FIN, RST và packet drop không giống nhau

Fault injector có thể tạo ra nhiều dạng gián đoạn mạng:

| Kiểu lỗi | Hành vi mạng | Điều test nên quan sát |
| --- | --- | --- |
| FIN / orderly close | Một phía đóng socket theo quy trình TCP | Driver có thể đọc EOF hoặc lỗi khi tiếp tục trao đổi; dữ liệu đã gửi trước đó có thể vẫn được xử lý |
| RST / connection reset | Kết nối bị hủy đột ngột | Client thường nhận reset nhanh; server có thể phát hiện session mất khi đọc/ghi tiếp |
| Drop packet / blackhole | Gói tin bị bỏ, không có phản hồi ngay | Client có thể chờ đến socket/read timeout hoặc TCP timeout |
| High latency | Phản hồi đến rất muộn | Có thể kích hoạt timeout ở client dù server vẫn hoàn tất transaction |
| Database process termination | Server process dừng | Kiểm tra crash recovery và trạng thái sau khi khởi động lại |

Các lỗi này có thể làm driver báo những exception khác nhau. Không viết test phụ thuộc duy nhất vào chuỗi thông báo exception vì thông điệp thay đổi theo JDBC driver và hệ điều hành. Hãy kiểm tra SQLState, vendor error code, exception cause và trạng thái connection khi cần phân loại.

Timeout ở client không tự hủy transaction ở server ngay lập tức. Server có thể tiếp tục xử lý cho đến khi phát hiện connection đóng hoặc transaction timeout riêng được áp dụng. Vì vậy, observer/retry phải tính đến thời gian transaction cũ được giải quyết.

## 16. Connection pool phải loại bỏ connection hỏng

Sau lỗi mạng trong hoặc quanh commit, connection JDBC có thể không còn đồng bộ với protocol state của database. Không trả connection đó về pool như một connection bình thường.

Các nguyên tắc:

- Đánh dấu/đóng connection khi driver báo lỗi kết nối nghiêm trọng.
- Để pool loại bỏ connection hỏng và tạo connection mới cho lần thử tiếp theo.
- Không tái sử dụng connection cũ chỉ vì `isClosed()` trả về false; socket có thể còn mở ở phía client nhưng server đã đóng session.
- Không coi `rollback()` thành công trên một connection khác là bằng chứng transaction trước đã rollback.
- Không retry trên cùng transaction hoặc cùng session sau lỗi protocol không xác định.
- Dùng connection mới và request ID cũ để tra cứu hoặc thực hiện retry idempotent.

Các pool như HikariCP có cơ chế xử lý connection lỗi, nhưng ứng dụng vẫn cần phân biệt lỗi SQL nghiệp vụ với lỗi connection và cấu hình validation/eviction phù hợp. Hãy kiểm thử qua đúng pool đang dùng trong production, không chỉ test với `DriverManager` trực tiếp.

## 17. Không retry COMMIT hoặc statement cuối một cách mù quáng

Khi `commit()` ném exception do mất kết nối, gửi lại riêng `COMMIT` trên connection mới không có nghĩa là commit transaction cũ. Transaction gắn với session/database transaction ID cũ; connection mới không thể tự tiếp tục transaction đó.

Tương tự, không chỉ gửi lại câu `UPDATE` hoặc `INSERT` cuối cùng. Các câu trước có thể đã commit cùng transaction, hoặc quyết định nghiệp vụ có thể dựa trên snapshot cũ.

Quy trình phục hồi nên là:

1. Đánh dấu kết quả request là unknown khi không có xác nhận commit rõ ràng.
2. Loại bỏ connection hỏng.
3. Kết nối lại đến primary hoặc nguồn đọc nhất quán.
4. Tra cứu operation record theo idempotency key.
5. Nếu đã có kết quả cuối, trả lại kết quả đó.
6. Nếu chưa có kết quả và transaction cũ đã được giải quyết, retry toàn bộ nghiệp vụ với cùng key.
7. Nếu vẫn chưa thể xác định, giữ trạng thái pending/unknown và thử tra cứu lại theo chính sách có giới hạn.

Retry toàn bộ transaction phải có idempotency ở cấp nghiệp vụ. Nếu thao tác tạo một đơn hàng mới, dùng cùng order request ID và unique constraint; nếu chuyển tiền, lưu transfer operation/ledger theo request ID; nếu gửi sự kiện, dùng outbox và event ID duy nhất.

## 18. Tác dụng phụ bên ngoài database

Transaction database có thể commit thành công nhưng ứng dụng mất kết nối trước khi gửi email, gọi payment provider hoặc phát message. Ngược lại, ứng dụng có thể gửi message trước commit rồi transaction rollback.

Không đặt các tác dụng phụ không thể rollback vào giữa transaction với giả định chúng sẽ cùng commit. Với sự kiện cần phát sau commit, dùng Transactional Outbox:

```sql
BEGIN;

UPDATE orders
SET status = 'PAID'
WHERE order_id = :order_id;

INSERT INTO outbox_event(event_id, event_type, aggregate_id, payload)
VALUES (:event_id, 'OrderPaid', :order_id, :payload);

COMMIT;
```

Worker đọc outbox và gửi event sau đó. Nếu process dừng sau commit nhưng trước khi gửi, event vẫn còn trong outbox. Nếu worker gửi thành công nhưng mất ACK trước khi đánh dấu sent, event có thể được gửi lại; consumer cần deduplicate theo `event_id` và xử lý idempotent.

Đối với payment provider, hãy dùng idempotency key do provider hỗ trợ nếu có. Nếu provider không có idempotency hoặc API tra cứu, cần quy trình reconciliation; không thể tự tạo bảo đảm exactly-once qua mạng chỉ bằng retry.

## 19. Ma trận test tối thiểu

Một bộ kiểm thử nên bao phủ các điểm sau:

| Test case | Điểm tiêm lỗi | Kiểm tra chính |
| --- | --- | --- |
| A. Disconnect trước COMMIT | Client không gửi lệnh commit | Transaction cũ rollback; retry cùng key thực hiện đúng một lần |
| B. Disconnect khi COMMIT đang truyền | Proxy reset quanh thời điểm request đến server | Client đánh dấu unknown; cả commit và rollback đều được xử lý an toàn |
| C. Drop ACK sau commit | Forward COMMIT, chặn response, observer xác nhận operation đã commit rồi reset client | Retry trả kết quả cũ; không duplicate nghiệp vụ |
| D. Database crash quanh commit | Dừng server process trong môi trường disposable | Recovery phù hợp durability config; trạng thái operation nhất quán |
| E. HTTP response bị mất | Database commit và app nhận ACK, nhưng client không nhận response | Retry cùng API key trả kết quả cũ |
| F. Hai request cùng key đồng thời | Hai client gửi cùng idempotency key | Chỉ một operation được commit; request còn lại đọc kết quả đó |
| G. Cùng key, payload khác | Retry dùng lại key với nội dung khác | Server từ chối key reuse không hợp lệ |
| H. Connection pool tái sử dụng lỗi | Reset connection rồi request tiếp theo dùng pool | Connection hỏng bị loại; request mới dùng session sạch |
| I. Replica lag | Primary commit, replica chưa cập nhật | Không kết luận sai từ kết quả đọc stale; luồng xác nhận dùng primary/consistency phù hợp |
| J. Outbox worker mất ACK | Event đã gửi nhưng worker chưa đánh dấu hoàn tất | Retry event không tạo tác dụng kép ở consumer |

Mỗi test cần xác nhận cả trạng thái database và phản hồi API. Chỉ kiểm tra exception hoặc status code là chưa đủ.

## 20. Những assertion quan trọng

Sau mỗi kịch bản, nên kiểm tra các bất biến sau bằng observer connection:

- Số operation record cho một request ID bằng 0 hoặc 1, không bao giờ lớn hơn 1.
- Nếu operation record có trạng thái `COMPLETED`, ledger và thay đổi số dư phải cùng phản ánh đúng một transfer.
- Tổng tiền trước và sau chuyển khoản được bảo toàn nếu đó là quy tắc nghiệp vụ.
- Retry cùng key trả cùng operation/transfer ID.
- Cùng key nhưng payload khác bị từ chối.
- Không có connection hỏng được tái sử dụng sau reset.
- Nếu database đã commit, lỗi cache/message/email sau đó không khiến ứng dụng thực hiện lại nghiệp vụ database.
- Nếu transaction rollback, không có operation record hoặc outbox event đã commit từ transaction đó.
- Nếu kết quả chưa xác định, API không khẳng định thành công hoặc thất bại khi chưa có bằng chứng.

Hãy dùng truy vấn kiểm tra từ primary và transaction mới. Truy vấn trong connection cũ hoặc snapshot cũ có thể không phản ánh trạng thái vừa commit.

## 21. Logging và quan sát khi fault injection

Để hiểu điều gì xảy ra, test cần liên kết được log ứng dụng, proxy và database bằng cùng một request ID/correlation ID.

Thông tin hữu ích:

- `request_id` / idempotency key.
- Thời điểm bắt đầu transaction, gửi từng statement, gọi commit và nhận exception.
- Proxy action: forward, pause, drop, FIN hoặc RST; hướng dữ liệu bị tác động.
- Database backend/session ID nếu engine cung cấp.
- Operation record và transfer ID sau khi reconnect.
- SQLState, vendor error code và exception cause.
- Thời điểm observer thấy operation record đã commit.
- Số lần retry và kết quả cuối.

Không ghi mật khẩu, token xác thực hoặc dữ liệu thanh toán nhạy cảm vào log. Môi trường test có thể dùng account và số tiền giả, nhưng vẫn nên áp dụng cách log an toàn như production.

Một timeline có timestamp đồng bộ giúp phân biệt:

```text
10:00:00.100 client gửi COMMIT
10:00:00.110 proxy forward COMMIT
10:00:00.125 database commit operation K
10:00:00.130 observer đọc thấy operation K
10:00:00.135 proxy reset connection phía client
10:00:00.140 JDBC ném connection reset
10:00:00.200 client retry cùng key K
10:00:00.220 server trả kết quả transfer cũ
```

Timeline này chứng minh lỗi xảy ra sau commit chứ không phải trước commit.

## 22. Những lỗi trong thiết kế test thường gặp

### Chỉ ném exception trước khi gọi commit

Điều này kiểm tra nhánh rollback trước commit, không kiểm tra mất ACK sau commit. Cần proxy hoặc wrapper gọi commit thật rồi mới làm mất phản hồi.

### Chỉ dùng sleep để đoán thời điểm commit

Thời gian commit phụ thuộc tải và storage. Một sleep 100 ms không chứng minh server đã commit. Dùng observer hoặc barrier có tín hiệu xác nhận.

### Observer đi qua cùng proxy bị lỗi

Khi proxy chặn kết nối, observer cũng không thể xác định trạng thái database. Dùng connection riêng đến primary.

### Đọc từ replica bất đồng bộ

Replica có thể chưa nhận transaction đã commit. Kết quả rỗng không chứng minh transaction rollback. Dùng primary hoặc consistency token/replication position phù hợp.

### Tạo idempotency key mới khi retry

Key mới biểu thị một yêu cầu nghiệp vụ mới. Nó không bảo vệ request ban đầu khỏi bị thực hiện hai lần.

### Lưu idempotency record trong transaction khác

Nếu record commit riêng, nó có thể tồn tại trong khi thay đổi nghiệp vụ rollback hoặc ngược lại. Record dùng để chứng minh kết quả phải cùng transaction với thay đổi được bảo vệ.

### Chỉ kiểm tra số dư cuối mà không kiểm tra ledger

Hai lỗi đối nghịch có thể vô tình bù trừ số dư. Kiểm tra operation count, ledger count, transfer ID và số dư để phát hiện duplicate chính xác hơn.

### Bắt mọi SQLException và coi là lỗi mạng mong đợi

Constraint violation, deadlock, authentication failure hoặc SQL syntax error phải làm test thất bại nếu test đang mô phỏng mất ACK. Hãy phân loại exception và xác nhận hành động của fault injector.

### Dùng chung proxy/database giữa các test song song

Một test reset connection có thể làm hỏng test khác. Dùng proxy endpoint, database/schema hoặc container riêng; tắt song song cho nhóm test cần điều khiển cùng một luồng mạng.

## 23. Quy trình xây dựng bộ kiểm thử từng bước

1. Tạo database test cô lập với schema operation/idempotency và dữ liệu tài khoản giả.
2. Tạo request ID cố định cho mỗi test và lưu số dư ban đầu.
3. Đưa JDBC traffic qua TCP proxy có thể điều khiển từng chiều.
4. Tạo observer datasource kết nối trực tiếp đến primary.
5. Bắt đầu với test đơn giản: ngắt connection trước khi gửi commit và xác nhận rollback.
6. Thêm barrier để proxy forward COMMIT nhưng giữ phản hồi database → client.
7. Dùng observer chờ operation record commit, sau đó reset connection phía client.
8. Retry cùng key và xác nhận kết quả cũ được trả về.
9. Thêm test hai request đồng thời cùng key và test payload mismatch.
10. Chạy cùng bộ test qua connection pool thực tế.
11. Thêm test crash recovery riêng nếu yêu cầu durability cần xác minh.
12. Ghi lại engine version, JDBC driver version, pool configuration, isolation level, `synchronous`/durability settings và proxy behavior.

Hãy giữ các test fault injection có thời gian chạy và tài nguyên riêng. Chúng thường chậm và phụ thuộc timing hơn unit test thông thường; có thể chạy trong integration-test hoặc nightly suite, còn test idempotency logic thuần ứng dụng nên chạy thường xuyên hơn.

## 24. Những điểm cần ghi nhớ

- Mất kết nối khi gọi `COMMIT` có thể khiến client không biết transaction đã commit hay rollback; exception không tự xác định kết quả.
- Cần tách rõ lỗi trước khi gửi commit, lỗi khi commit đang truyền và trường hợp database đã commit nhưng ACK bị mất.
- TCP proxy cho phép điều khiển riêng hướng client → database và database → client; observer connection phải đi trực tiếp đến primary.
- Để chứng minh ACK bị mất sau commit, giữ phản hồi ở proxy, đợi observer thấy operation record đã commit rồi mới reset connection client.
- Ghi idempotency key, thay đổi nghiệp vụ, ledger và kết quả trong cùng transaction để có thể tra cứu kết quả sau reconnect.
- Retry phải dùng cùng key và payload; key đã tồn tại trả kết quả cũ, còn cùng key với payload khác phải bị từ chối.
- Nếu transaction cũ chưa được giải quyết, unique constraint trên request ID giúp các lần retry phối hợp với transaction đó thay vì tạo tác dụng thứ hai.
- Không retry riêng câu COMMIT hoặc statement cuối trên connection mới; hãy tra cứu rồi retry toàn bộ nghiệp vụ theo cơ chế idempotent.
- Connection gặp lỗi protocol/mạng nghiêm trọng phải bị loại khỏi pool; không tái sử dụng session không đáng tin cậy.
- Database crash test khác network disconnect test; kết quả recovery phụ thuộc engine, storage và durability configuration.
- HTTP response có thể mất sau khi database commit, vì vậy idempotency cần được áp dụng xuyên suốt tầng API.
- Tác dụng phụ ngoài database nên dùng outbox và consumer idempotent; không thể bảo đảm exactly-once qua mạng chỉ bằng retry.
- Test phải xác nhận operation count, ledger, số dư và kết quả trả về, không chỉ kiểm tra exception.
