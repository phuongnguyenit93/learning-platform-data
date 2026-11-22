# Thực thi lại một câu lệnh trong giao dịch đã lỗi

Khi một câu lệnh SQL thất bại trong transaction, việc gửi lại đúng câu lệnh đó chưa chắc khôi phục được nghiệp vụ. Transaction có thể đã bị database đánh dấu không thể tiếp tục, snapshot đọc có thể đã cũ, các thao tác trước đó có thể vẫn còn hiệu lực trong transaction, hoặc hệ quản trị đã rollback toàn bộ transaction. Nếu chỉ retry câu lệnh cuối, ứng dụng có thể tiếp tục từ một trạng thái không còn hợp lệ và tạo ra kết quả sai.

Cần phân biệt **retry câu lệnh** với **retry transaction**:

- Retry câu lệnh là chạy lại một statement trong transaction hiện tại.
- Retry transaction là rollback hoặc kết thúc transaction cũ, bắt đầu transaction mới, đọc lại dữ liệu và chạy lại toàn bộ đơn vị nghiệp vụ.

Với deadlock và serialization failure, cách phục hồi an toàn thường là retry toàn bộ transaction. Retry riêng statement chỉ phù hợp khi lỗi được xác định là lỗi cục bộ, transaction vẫn hợp lệ, các bước trước đó vẫn đúng và nghiệp vụ cho phép tiếp tục từ savepoint hoặc trạng thái hiện tại.

## 1. Transaction là một đơn vị nghiệp vụ, không chỉ là tập câu SQL

Giả sử thao tác chuyển tiền gồm ba bước:

1. Đọc số dư tài khoản nguồn và kiểm tra đủ tiền.
2. Trừ tiền tài khoản nguồn.
3. Cộng tiền tài khoản đích và ghi lịch sử chuyển tiền.

~~~sql
BEGIN;

SELECT balance
FROM account
WHERE account_id = 10;

UPDATE account
SET balance = balance - 100
WHERE account_id = 10;

UPDATE account
SET balance = balance + 100
WHERE account_id = 20;

INSERT INTO transfer_log (from_account, to_account, amount)
VALUES (10, 20, 100);

COMMIT;
~~~

Giả sử câu UPDATE tài khoản đích gặp deadlock. Nếu hệ quản trị rollback toàn transaction, câu UPDATE tài khoản nguồn cũng đã bị hoàn tác. Chỉ chạy lại câu UPDATE tài khoản đích sẽ cộng tiền mà không có khoản trừ tương ứng nếu ứng dụng tiếp tục sai cách.

Ở một hệ quản trị chỉ rollback statement lỗi, câu UPDATE tài khoản nguồn có thể vẫn còn trong transaction. Nếu chạy lại riêng câu UPDATE tài khoản đích và sau đó commit, giao dịch có thể hoàn tất. Nhưng điều này chỉ đúng khi transaction vẫn hợp lệ, khoản trừ trước đó vẫn nằm trong cùng transaction, các điều kiện đã đọc vẫn còn phù hợp và không có lỗi nào làm hỏng tính nhất quán của toàn nghiệp vụ.

Một lỗi đồng thời có thể làm thay đổi những giả định đó. Vì thế, quyết định retry phải dựa trên **loại lỗi, trạng thái transaction và ranh giới nghiệp vụ**, không chỉ dựa trên câu SQL vừa thất bại.

## 2. Vì sao retry riêng statement thường sai?

Có bốn nguyên nhân chính.

### 2.1. Transaction có thể đã bị hủy hoặc đánh dấu không thể tiếp tục

Một số hệ quản trị đánh dấu toàn transaction là failed sau một lỗi. Mọi câu SQL tiếp theo sẽ bị từ chối cho đến khi rollback. Trong trường hợp đó, retry statement ngay trên cùng transaction không thể thành công.

Ví dụ PostgreSQL trả SQLSTATE **25P02** với thông báo transaction hiện tại đã bị aborted. Đây thường là hậu quả của một lỗi trước đó; nó không phải nguyên nhân gốc cần retry.

### 2.2. Các bước trước đó có thể đã dựa trên dữ liệu cũ

Giả sử transaction đọc hạn mức còn lại là 500, sau đó thực hiện một số thao tác, rồi câu UPDATE cuối bị serialization failure. Trong lúc đó transaction khác đã thay đổi dữ liệu liên quan.

Nếu chỉ chạy lại UPDATE cuối, ứng dụng có thể tiếp tục dùng quyết định “còn 500” đã tính từ snapshot cũ. Transaction mới phải đọc lại các dữ liệu đầu vào và tính lại điều kiện nghiệp vụ.

### 2.3. Một phần thay đổi trước đó có thể vẫn còn trong transaction

Một số hệ quản trị rollback statement lỗi nhưng giữ các thay đổi của những statement trước. Nếu ứng dụng retry cả đoạn code hoặc chạy lại các statement trước mà không rollback, có thể trừ tiền, tăng bộ đếm hoặc tạo bản ghi hai lần trong cùng transaction.

Ngược lại, nếu hệ quản trị đã rollback toàn bộ transaction nhưng ứng dụng giả định các bước trước vẫn còn, retry riêng statement cuối có thể tạo dữ liệu thiếu hoặc sai.

### 2.4. Lỗi có thể không còn là lỗi tạm thời

Nếu câu lệnh thất bại vì constraint, dữ liệu đầu vào sai hoặc quyền truy cập không đủ, gửi lại cùng statement thường chỉ lặp lại cùng lỗi. Retry vô hạn làm tăng tải và che giấu nguyên nhân thực sự.

## 3. Phân biệt lỗi statement với lỗi transaction

Cần đọc tài liệu hệ quản trị và mã lỗi cụ thể để biết lỗi ảnh hưởng tới phạm vi nào.

| Loại lỗi | Phạm vi có thể bị ảnh hưởng | Hướng xử lý thường gặp |
|---|---|---|
| Lỗi dữ liệu/constraint của một statement | Statement thất bại; transaction có thể vẫn hoạt động tùy engine | Sửa dữ liệu hoặc rollback về savepoint nếu nghiệp vụ cho phép |
| Deadlock victim | Thường transaction bị chọn làm nạn nhân bị rollback; chi tiết theo engine | Kết thúc transaction và retry toàn bộ đơn vị nghiệp vụ |
| Serialization failure | Transaction không thể tiếp tục với lịch/snapshot hiện tại | Transaction mới, đọc lại và chạy lại toàn bộ nghiệp vụ |
| Lock wait timeout | Có thể rollback statement hoặc transaction tùy engine/cấu hình | Xác định trạng thái transaction; retry có giới hạn nếu còn phù hợp |
| Mất kết nối khi COMMIT | Kết quả commit có thể chưa rõ với client | Tra cứu bằng idempotency key hoặc business reference trước khi thực hiện lại |

Một câu lệnh báo lỗi không tự động có nghĩa toàn transaction đã rollback. Ngược lại, việc database cho phép gửi tiếp một câu SQL cũng không chứng minh nghiệp vụ còn an toàn để tiếp tục.

## 4. Hành vi theo hệ quản trị

### 4.1. PostgreSQL: lỗi thường làm transaction vào trạng thái aborted

Trong PostgreSQL, một lỗi SQL xảy ra trong transaction thường đánh dấu transaction hiện tại là aborted. Các câu lệnh tiếp theo bị từ chối với SQLSTATE **25P02** cho đến khi transaction được rollback hoặc rollback về savepoint được tạo trước lỗi.

Ví dụ:

~~~sql
BEGIN;

UPDATE account
SET balance = balance - 100
WHERE account_id = 10;

-- Giả sử câu lệnh này phát sinh lỗi.
UPDATE account
SET balance = balance + 100
WHERE account_id = 20;

-- Chạy lại statement lỗi ngay trong transaction này
-- sẽ không phục hồi transaction.
UPDATE account
SET balance = balance + 100
WHERE account_id = 20;

COMMIT;
~~~

Sau lỗi đầu tiên, transaction đã bị đánh dấu failed. Cách xử lý thông thường:

~~~sql
ROLLBACK;
~~~

Sau đó bắt đầu transaction mới và chạy lại từ bước đọc dữ liệu đầu tiên.

Hai mã đồng thời cần nhận diện riêng:

- **40P01:** deadlock detected.
- **40001:** serialization failure.

Với **40001**, PostgreSQL yêu cầu ứng dụng retry toàn bộ transaction. Không chạy lại riêng statement cuối vì quyết định trước đó có thể dựa trên snapshot không còn hợp lệ.

Savepoint là ngoại lệ có chủ đích: nếu tạo savepoint trước một thao tác có thể thất bại, ứng dụng có thể ROLLBACK TO SAVEPOINT để phục hồi transaction về điểm đó. Tuy nhiên, savepoint không biến serialization failure thành một transaction mới và không làm mới snapshot. Không dùng nó để né yêu cầu retry toàn bộ transaction khi lỗi là serialization failure.

### 4.2. MySQL InnoDB: deadlock và lock timeout có phạm vi rollback khác nhau

InnoDB tự động phát hiện deadlock và chọn một transaction làm nạn nhân. Transaction nạn nhân thường bị rollback toàn bộ. Lỗi thường có mã **1213** và SQLSTATE **40001**. Khi gặp lỗi này, ứng dụng nên bỏ transaction hiện tại và retry toàn bộ đơn vị nghiệp vụ trong transaction mới.

Lock wait timeout khác deadlock. Mặc định, InnoDB thường rollback statement bị timeout; nếu **innodb_rollback_on_timeout** được bật, timeout có thể làm rollback toàn transaction. Vì vậy cần biết cấu hình thực tế trước khi quyết định trạng thái transaction.

Ví dụ kiểm tra cấu hình:

~~~sql
SELECT
    @@transaction_isolation,
    @@innodb_rollback_on_timeout,
    @@autocommit;
~~~

Mã **1205** thường là lock wait timeout. Nếu cấu hình chỉ rollback statement, các thay đổi trước đó có thể vẫn đang nằm trong transaction. Việc retry riêng statement chỉ có thể cân nhắc khi ứng dụng đã xác nhận transaction còn hợp lệ và các bước trước đó vẫn đúng. Với nghiệp vụ gồm nhiều bước phụ thuộc nhau, rollback và chạy lại toàn bộ transaction thường dễ đảm bảo hơn.

Không nên coi **1213** và **1205** là cùng một loại lỗi chỉ vì cả hai đều liên quan đến khóa.

### 4.3. SQL Server: kiểm tra trạng thái transaction sau lỗi

SQL Server có nhiều kiểu lỗi và hành vi transaction khác nhau. Một số lỗi chỉ làm statement thất bại; một số làm transaction không thể commit; deadlock victim thường bị rollback.

Có thể kiểm tra trạng thái bằng **XACT_STATE()**:

| Giá trị | Ý nghĩa |
|---:|---|
| **1** | Có transaction đang hoạt động và có thể commit; vẫn cần quyết định nghiệp vụ xem có nên tiếp tục không |
| **-1** | Transaction đang hoạt động nhưng không thể commit; chỉ có thể đọc hoặc rollback toàn bộ transaction |
| **0** | Không có transaction đang hoạt động |

Ví dụ:

~~~sql
BEGIN TRY
    BEGIN TRANSACTION;

    UPDATE dbo.Account
    SET Balance = Balance - 100
    WHERE AccountId = 10;

    UPDATE dbo.Account
    SET Balance = Balance + 100
    WHERE AccountId = 20;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    SELECT
        ERROR_NUMBER() AS error_number,
        ERROR_MESSAGE() AS error_message,
        XACT_STATE() AS transaction_state;

    IF XACT_STATE() <> 0
        ROLLBACK TRANSACTION;

    THROW;
END CATCH;
~~~

**SET XACT_ABORT ON** làm nhiều lỗi runtime khiến transaction bị hủy thay vì chỉ rollback statement. Cách xử lý vẫn phải xem **XACT_STATE()** trong khối CATCH. Deadlock victim thường nhận error number **1205**; transaction bị chọn làm nạn nhân đã được SQL Server rollback.

Nếu **XACT_STATE() = -1**, không thể rollback về savepoint để tiếp tục phần còn lại. Phải rollback transaction. Nếu **XACT_STATE() = 1**, transaction vẫn có thể commit về mặt kỹ thuật, nhưng ứng dụng chỉ nên tiếp tục khi biết rõ statement nào đã rollback và các điều kiện nghiệp vụ trước đó vẫn hợp lệ.

### 4.4. Oracle: statement rollback không đồng nghĩa transaction rollback

Oracle bảo đảm tính nguyên tử ở cấp statement: nếu một statement thất bại, các thay đổi của chính statement đó được hoàn tác. Những statement thành công trước đó trong transaction thường vẫn còn và transaction có thể tiếp tục.

Ví dụ, nếu câu UPDATE thứ hai gặp lỗi, Oracle có thể rollback câu UPDATE thứ hai mà vẫn giữ câu UPDATE đầu tiên chưa commit. Đây là hành vi khác với trạng thái aborted mặc định của PostgreSQL.

Với deadlock **ORA-00060**, Oracle thường rollback statement phát hiện deadlock để phá chu trình; transaction không nhất thiết tự động rollback toàn bộ. Các khóa do statement trước đó lấy có thể vẫn được giữ.

Tuy nhiên, điều này không có nghĩa cứ retry riêng statement là an toàn. Nếu statement trước đó đã đọc dữ liệu và đưa ra quyết định dựa trên trạng thái cũ, hoặc toàn bộ nghiệp vụ cần tính nguyên tử, ứng dụng vẫn nên rollback và chạy lại toàn transaction.

**ORA-08177** là lỗi không thể tuần tự hóa truy cập trong transaction SERIALIZABLE. Hãy coi đây là xung đột cần bắt đầu transaction mới và đọc lại dữ liệu theo toàn bộ đơn vị nghiệp vụ.

## 5. Một ví dụ về quyết định cũ làm cho retry statement sai

Giả sử một khách hàng không được có quá 10 đơn đang mở. Transaction thực hiện:

~~~sql
BEGIN;

SELECT COUNT(*) AS open_count
FROM orders
WHERE customer_id = 77
  AND status = 'OPEN';

-- Ứng dụng thấy open_count = 9 và cho phép tạo đơn.

INSERT INTO orders (customer_id, status)
VALUES (77, 'OPEN');

UPDATE customer_summary
SET open_order_count = open_order_count + 1
WHERE customer_id = 77;

COMMIT;
~~~

Giữa lúc kiểm tra và ghi, transaction khác có thể tạo đơn thứ 10. Một lỗi ở câu UPDATE cuối hoặc một xung đột đồng thời khiến transaction hiện tại phải xử lý lại.

Nếu chỉ retry câu UPDATE summary, ứng dụng có thể hoàn tất thao tác dựa trên quyết định cũ rằng số đơn trước đó là 9. Nếu transaction mới đọc lại, nó có thể thấy đã có 10 đơn và từ chối tạo đơn tiếp theo.

Đây là lý do retry phải bắt đầu ở điểm mà quyết định nghiệp vụ được đưa ra. Khi quyết định phụ thuộc vào dữ liệu có thể thay đổi, điểm đó thường là đầu transaction.

## 6. Mẫu sai: bắt lỗi rồi chạy lại statement trong cùng transaction

Một anti-pattern phổ biến trong code:

~~~java
connection.setAutoCommit(false);

try {
    debitSourceAccount(connection, sourceId, amount);

    try {
        creditDestinationAccount(connection, destinationId, amount);
    } catch (SQLException error) {
        if (isDeadlock(error)) {
            // Sai: transaction có thể đã bị rollback hoặc ở trạng thái lỗi.
            creditDestinationAccount(connection, destinationId, amount);
        } else {
            throw error;
        }
    }

    insertTransferLog(connection, sourceId, destinationId, amount);
    connection.commit();
} catch (SQLException error) {
    connection.rollback();
    throw error;
}
~~~

Đoạn code này giả định rằng:

- Transaction vẫn hoạt động sau lỗi.
- Chỉ statement cộng tiền bị ảnh hưởng.
- Statement trừ tiền trước đó vẫn tồn tại.
- Dữ liệu mà quyết định chuyển tiền dựa vào vẫn còn đúng.
- Retry statement không tạo tác động lặp.

Các giả định đó không đúng cho mọi database hoặc mọi loại lỗi. Với deadlock victim của InnoDB hay SQL Server, transaction có thể đã bị rollback. Với PostgreSQL, transaction đã aborted. Với Oracle, statement rollback có thể để các bước trước tồn tại, nhưng vẫn cần đánh giá lại logic nghiệp vụ.

## 7. Mẫu đúng: retry toàn bộ transaction trong transaction mới

Với deadlock hoặc serialization failure, hãy đặt vòng retry bên ngoài ranh giới transaction.

Luồng:

~~~mermaid
flowchart TD
    A["Bắt đầu lần thử"] --> B["Mở transaction mới"]
    B --> C["Đọc dữ liệu và kiểm tra nghiệp vụ"]
    C --> D["Thực hiện tất cả thao tác ghi"]
    D --> E{"COMMIT thành công?"}
    E -->|Có| F["Trả kết quả"]
    E -->|Không, lỗi retryable| G["Rollback/kết thúc transaction"]
    G --> H{"Còn lượt thử?"}
    H -->|Có| I["Backoff có jitter"]
    I --> B
    H -->|Không| J["Trả lỗi cho caller"]
    E -->|Lỗi không retryable| K["Rollback và trả lỗi"]
~~~

Ví dụ Java với JDBC:

~~~java
static <T> T executeWithRetry(
        DataSource dataSource,
        int maxAttempts,
        SqlWork<T> work) throws SQLException {

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try {
                T result = work.execute(connection);
                connection.commit();
                return result;
            } catch (SQLException | RuntimeException error) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            }
        } catch (SQLException error) {
            if (!isRetryableConcurrencyError(error)
                    || attempt == maxAttempts) {
                throw error;
            }

            pauseWithBackoffAndJitter(attempt);
        }
    }

    throw new IllegalStateException("Không thể tới nhánh này");
}
~~~

**SqlWork** là interface nhận connection và thực hiện toàn bộ nghiệp vụ:

~~~java
@FunctionalInterface
interface SqlWork<T> {
    T execute(Connection connection) throws SQLException;
}
~~~

Mỗi lần lặp lấy một connection mới từ pool và bắt đầu transaction mới. Trong một số pool, connection vật lý có thể được tái sử dụng; điều quan trọng là transaction cũ đã được kết thúc và connection đã được reset đúng trạng thái trước khi dùng lại.

Hàm **work.execute()** phải chứa cả bước đọc, kiểm tra và ghi. Không truyền vào một số dư, số lượng tồn kho hoặc quyết định đã tính ở lần thử trước để tái sử dụng.

Hàm **isRetryableConcurrencyError()** cần phân loại theo database vendor, SQLSTATE và vendor code. Ví dụ:

- PostgreSQL: **40P01** deadlock; **40001** serialization failure.
- MySQL InnoDB: **1213** deadlock; **1205** lock wait timeout cần xử lý theo cấu hình và chính sách.
- SQL Server: **1205** deadlock victim; **3960** snapshot update conflict.
- Oracle: **60** cho ORA-00060; **8177** cho ORA-08177.

Không retry mọi **SQLException**. Lỗi constraint, cú pháp, quyền truy cập hoặc dữ liệu đầu vào sai thường cần được xử lý như lỗi cuối cùng.

## 8. Retry với Spring: vòng lặp phải nằm ngoài transaction boundary

Khi dùng Spring, một lỗi thường gặp là bắt exception bên trong cùng một phương thức **@Transactional** rồi gọi lại logic nghiệp vụ. Transaction có thể đã bị đánh dấu rollback-only; lần gọi sau vẫn chạy trong transaction cũ hoặc kết thúc bằng **UnexpectedRollbackException**.

Dùng **TransactionTemplate** để mỗi lần thử tạo transaction mới:

~~~java
public OrderResult createOrderWithRetry(CreateOrderRequest request) {
    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        try {
            return transactionTemplate.execute(status ->
                createOrderInsideTransaction(request)
            );
        } catch (RuntimeException error) {
            if (!isRetryableConcurrencyError(error)
                    || attempt == maxAttempts) {
                throw error;
            }

            pauseWithBackoffAndJitter(attempt);
        }
    }

    throw new IllegalStateException("Không thể tới nhánh này");
}
~~~

Ở đây vòng lặp retry nằm bên ngoài **transactionTemplate.execute()**. Mỗi lần execute kết thúc với commit hoặc rollback trước khi lần thử tiếp theo bắt đầu.

Nếu dùng **@Retryable** cùng **@Transactional**, hãy xác nhận thứ tự interceptor để mỗi lần retry tạo transaction mới. Ngoài ra, lời gọi nội bộ trong cùng object có thể bỏ qua Spring proxy; không nên giả định một self-invocation sẽ kích hoạt transaction boundary mới.

## 9. Khi nào retry riêng statement là hợp lý?

Retry statement có thể đúng trong một số trường hợp có kiểm soát:

- Lỗi chỉ ảnh hưởng statement hiện tại.
- Transaction vẫn ở trạng thái có thể tiếp tục.
- Các thay đổi trước đó vẫn hợp lệ và chưa bị rollback.
- Dữ liệu đầu vào và các quyết định trước đó không cần đọc lại.
- Nghiệp vụ cho phép tiếp tục từ điểm hiện tại.
- Ứng dụng có một savepoint rõ ràng nếu cần hoàn tác phần công việc cục bộ.

Ví dụ một import có một dòng tùy chọn bị trùng và nghiệp vụ cho phép bỏ qua dòng đó. Ứng dụng có thể tạo savepoint trước khi chèn dòng tùy chọn, rollback về savepoint nếu gặp duplicate key, rồi tiếp tục phần còn lại. Đây là xử lý lỗi cục bộ có chủ đích, không phải retry deadlock hoặc serialization failure.

Một nguyên tắc hữu ích: nếu lỗi xảy ra vì dữ liệu cạnh tranh đã thay đổi, hãy nghiêng về transaction mới. Nếu lỗi là một điều kiện cục bộ đã được dự kiến và transaction còn hợp lệ, savepoint có thể phù hợp.

## 10. Savepoint không phải transaction mới

Savepoint đánh dấu một điểm trong transaction hiện tại. Rollback về savepoint chỉ hoàn tác phần thay đổi sau điểm đó, trong khi vẫn giữ transaction và các thay đổi trước đó.

~~~sql
BEGIN;

UPDATE import_job
SET status = 'RUNNING'
WHERE job_id = 55;

SAVEPOINT optional_step;

INSERT INTO optional_metadata (job_id, metadata_key, metadata_value)
VALUES (55, 'source', 'partner');

-- Nếu chỉ thao tác tùy chọn bị duplicate:
ROLLBACK TO SAVEPOINT optional_step;

-- Transaction vẫn có thể tiếp tục với các thao tác hợp lệ.
UPDATE import_job
SET status = 'COMPLETED'
WHERE job_id = 55;

COMMIT;
~~~

Cần chú ý:

- Savepoint không tạo snapshot mới.
- Savepoint không xóa các quyết định đã dựa trên snapshot cũ.
- Không phải mọi lỗi transaction đều cho phép rollback về savepoint.
- SQL Server không cho rollback về savepoint khi transaction ở trạng thái uncommittable (**XACT_STATE() = -1**).
- PostgreSQL có thể phục hồi transaction về savepoint sau lỗi statement, nhưng serialization failure vẫn cần retry toàn transaction.
- Savepoint không làm một deadlock victim đã bị rollback trở lại trạng thái đang hoạt động.

Dùng savepoint để xử lý phần việc tùy chọn hoặc lỗi cục bộ đã dự kiến, không dùng nó như một cơ chế tổng quát để retry transaction đã lỗi.

## 11. Batch và nhiều statement: xác định lại ranh giới retry

Một batch có thể chứa nhiều statement. Khi batch thất bại, **BatchUpdateException** có thể cung cấp update counts, nhưng số lệnh đã thực thi và cách driver dừng batch phụ thuộc driver.

Nếu cả chunk là một đơn vị nguyên tử:

1. Bắt lỗi batch.
2. Rollback toàn transaction của chunk.
3. Không đánh dấu checkpoint chunk hoàn tất.
4. Nếu lỗi có thể retry, bắt đầu transaction mới và chạy lại toàn chunk.
5. Dùng unique key hoặc idempotency để bảo vệ việc chạy lại.

Không nên chỉ chạy lại những statement được cho là thất bại nếu các statement trước có quan hệ phụ thuộc hoặc batch đã bị rollback ở phạm vi rộng hơn.

Nếu mỗi dòng độc lập và chấp nhận thành công một phần, hãy lưu kết quả từng dòng và định nghĩa rõ cách tiếp tục. Không suy ra commit thành công từ update count; chỉ commit mới xác nhận transaction hoàn tất theo durability policy.

## 12. Không retry mù quáng khi COMMIT trả lỗi kết nối

Một trường hợp khó là client gửi COMMIT nhưng kết nối bị mất trước khi nhận phản hồi. Client không biết transaction đã commit hay chưa.

Nếu chạy lại toàn bộ transaction bằng một key mới, ứng dụng có thể tạo đơn hoặc thanh toán trùng. Nếu không retry, client có thể không nhận được kết quả dù nghiệp vụ đã thành công.

Cách xử lý:

- Mỗi yêu cầu nghiệp vụ quan trọng có idempotency key hoặc business reference duy nhất.
- Lưu key và kết quả nghiệp vụ trong cùng transaction.
- Khi kết nối mất ở thời điểm commit, mở kết nối mới và tra cứu key.
- Nếu đã có kết quả hoàn tất, phát lại kết quả đó.
- Nếu chắc chắn chưa có transaction commit, mới thực hiện lại theo chính sách.
- Nếu trạng thái chưa rõ, tiếp tục đối soát; không tạo một yêu cầu logic mới chỉ để vượt qua timeout.

Idempotency giải quyết sự không chắc chắn giữa việc database commit và việc client nhận response. Nó bổ sung cho transaction retry, không thay thế việc xác định transaction nào đã thành công.

## 13. Side effect bên ngoài phải nằm ngoài vòng retry hoặc có idempotency

Giả sử transaction tạo đơn hàng, gửi email và sau đó gặp deadlock. Nếu ứng dụng retry toàn bộ method, email có thể được gửi hai lần dù transaction database đầu tiên đã rollback.

Không gọi dịch vụ ngoài trong transaction retry nếu không có cơ chế chống lặp. Có thể:

- Ghi sự kiện vào bảng outbox trong cùng transaction với đơn hàng.
- Commit transaction.
- Worker gửi email hoặc message sau commit.
- Dùng event ID/idempotency key để consumer xử lý trùng an toàn.

Retry transaction chỉ nên lặp lại các thay đổi có thể rollback trong database. Tác động bên ngoài cần có ranh giới và cơ chế phục hồi riêng.

## 14. Backoff và giới hạn số lần retry

Nếu nhiều transaction cùng bị deadlock rồi retry ngay lập tức, chúng có thể va chạm lại theo cùng một lịch. Backoff có jitter làm lệch thời điểm thử lại và giảm khả năng lặp lại xung đột.

Chính sách thường gồm:

- Giới hạn số lần thử nhỏ và cấu hình được.
- Tăng thời gian chờ theo exponential backoff.
- Thêm random jitter.
- Giới hạn tổng thời gian retry theo deadline của request.
- Tôn trọng interrupt/cancellation.
- Ghi log số lần thử và mã lỗi gốc.

Không retry lỗi dữ liệu, constraint hoặc lỗi lập trình. Lock timeout có thể được retry theo chính sách riêng; nếu timeout phản ánh hệ thống đang quá tải, retry dày đặc có thể làm tình hình tệ hơn.

## 15. Bảng quyết định: retry statement hay transaction?

| Tình huống | Có nên retry riêng statement? | Hướng xử lý |
|---|---|---|
| PostgreSQL **25P02** | Không | Rollback transaction; tìm lỗi gốc trước đó |
| PostgreSQL deadlock **40P01** | Không | Transaction mới, chạy lại toàn bộ nghiệp vụ |
| PostgreSQL serialization **40001** | Không | Transaction mới, đọc lại và chạy lại toàn bộ nghiệp vụ |
| MySQL InnoDB deadlock **1213** | Không | Transaction mới và retry toàn bộ |
| MySQL lock timeout **1205** | Chỉ khi đã xác nhận transaction còn hợp lệ và nghiệp vụ cho phép | Kiểm tra **innodb_rollback_on_timeout**; rollback toàn bộ thường đơn giản và an toàn hơn |
| SQL Server deadlock victim **1205** | Không | Transaction đã rollback; transaction mới |
| SQL Server **XACT_STATE() = -1** | Không | Chỉ rollback toàn bộ transaction |
| Oracle **ORA-00060** | Có thể về mặt phạm vi statement, nhưng không tự động an toàn về nghiệp vụ | Đánh giá trạng thái trước đó; thường retry toàn bộ đơn vị nghiệp vụ |
| Oracle **ORA-08177** | Không nên | Rollback và chạy lại transaction từ đầu |
| Duplicate key của một bước tùy chọn có savepoint | Có thể | Rollback về savepoint và tiếp tục nếu nghiệp vụ cho phép |
| Lỗi cú pháp hoặc quyền | Không | Sửa nguyên nhân, không retry |

Bảng này là hướng dẫn phục hồi, không thay thế việc kiểm tra trạng thái transaction thực tế và tài liệu đúng phiên bản.

## 16. Checklist xử lý khi một statement thất bại

- [ ] Đã ghi lại SQLSTATE và vendor error code gốc?
- [ ] Đã phân biệt deadlock, serialization failure, lock timeout và lỗi dữ liệu?
- [ ] Đã xác định hệ quản trị rollback statement hay toàn transaction?
- [ ] Transaction hiện tại còn hoạt động, aborted hay uncommittable?
- [ ] Các statement trước có thay đổi dữ liệu hoặc giữ khóa không?
- [ ] Các quyết định trước đó có dựa trên snapshot hoặc predicate có thể đã cũ?
- [ ] Nếu retry, có bắt đầu transaction mới khi cần không?
- [ ] Toàn bộ bước đọc, kiểm tra và ghi có được chạy lại không?
- [ ] Retry có giới hạn, backoff và jitter không?
- [ ] Side effect bên ngoài có idempotent hoặc dùng outbox không?
- [ ] Kết quả COMMIT không rõ có được tra cứu bằng idempotency key không?
- [ ] Savepoint chỉ được dùng cho lỗi cục bộ mà transaction vẫn hợp lệ?

Khi một statement lỗi, đừng mặc định có thể chạy lại chính statement đó trong transaction hiện tại. Hệ quản trị có thể đã rollback toàn transaction, đánh dấu transaction không thể commit hoặc giữ lại các thay đổi trước đó nhưng làm cho quyết định nghiệp vụ trở nên cũ. Với deadlock và serialization failure, hãy kết thúc transaction hiện tại, bắt đầu transaction mới, đọc lại dữ liệu và thực hiện lại toàn bộ nghiệp vụ. Chỉ retry riêng statement khi đã xác nhận transaction còn hợp lệ, phạm vi rollback rõ ràng và các bước trước đó vẫn đúng; savepoint có thể hỗ trợ trường hợp cục bộ, nhưng không thay thế transaction mới.

