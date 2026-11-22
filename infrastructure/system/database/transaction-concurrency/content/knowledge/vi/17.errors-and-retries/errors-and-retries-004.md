# Tạo giao dịch mới và đọc lại dữ liệu trước mỗi lần thử

Khi database báo deadlock hoặc serialization failure, một transaction thường không thể tiếp tục như chưa có chuyện gì xảy ra. Transaction có thể đã bị rollback toàn bộ, câu lệnh có thể đã bị rollback riêng, hoặc connection có thể đang ở trạng thái lỗi. Nếu ứng dụng chỉ chạy lại câu SQL cuối cùng bằng dữ liệu đã đọc trước đó, nó có thể tiếp tục dựa trên một snapshot cũ và lặp lại cùng xung đột.

Cách retry an toàn là **kết thúc transaction thất bại, bắt đầu một transaction mới, đọc lại dữ liệu cần thiết, tính lại quyết định nghiệp vụ và thực hiện lại toàn bộ chuỗi thao tác**. Mỗi lần thử phải có một ranh giới transaction rõ ràng. Dữ liệu đầu vào của lần thử mới cần được lấy từ trạng thái database mới nhất mà isolation level cho phép nhìn thấy.

Retry không phải cách chữa mọi lỗi. Chỉ retry những lỗi tạm thời có thể phục hồi, giới hạn số lần thử và bảo đảm các tác dụng phụ ngoài database không bị thực hiện lặp. Bài này tập trung vào ứng dụng Java làm việc với MySQL InnoDB và PostgreSQL.

## 1. Vì sao phải tạo transaction mới?

Một transaction cung cấp ranh giới nhất quán cho các lần đọc và ghi. Tùy isolation level, transaction có thể tiếp tục dùng snapshot đã tạo trước đó. Nếu một thao tác thất bại do xung đột đồng thời, việc chạy lại câu lệnh trong cùng transaction không nhất thiết tạo ra góc nhìn dữ liệu mới.

Ví dụ, hai giao dịch cùng chuyển tiền giữa hai tài khoản:

```text
Ban đầu: account A = 500, account B = 300

Transaction T1 đọc A=500, B=300
Transaction T2 đọc A=500, B=300

T1 tính A=400, B=400
T2 tính A=450, B=350

T1 ghi và COMMIT
T2 gặp deadlock hoặc serialization failure
```

Sau khi T2 thất bại, ứng dụng không nên chỉ gửi lại hai câu `UPDATE` với các giá trị `450` và `350` đã tính từ lần đọc cũ. Nếu làm vậy, T2 có thể ghi đè kết quả T1 và làm mất ý nghĩa của thao tác chuyển tiền.

Lần thử tiếp theo cần bắt đầu transaction mới và đọc lại:

```text
Transaction T3 (lần thử mới)
    |
    v
BEGIN
    |
    v
Đọc lại A và B từ database
    |
    v
Kiểm tra số dư và quy tắc nghiệp vụ
    |
    v
Tính lại số dư mới
    |
    v
UPDATE A và B
    |
    v
COMMIT
```

T3 có thể thấy A=400, B=400 và tính lại kết quả dựa trên trạng thái đó. Nếu điều kiện nghiệp vụ không còn thỏa, chẳng hạn số dư không đủ, ứng dụng trả lỗi nghiệp vụ thay vì cố áp dụng kết quả cũ.

## 2. Retry toàn bộ đơn vị công việc nguyên tử

Một transaction có thể gồm nhiều bước phụ thuộc lẫn nhau:

1. Đọc số dư hoặc trạng thái hiện tại.
2. Kiểm tra điều kiện nghiệp vụ.
3. Tính giá trị mới.
4. Cập nhật một hoặc nhiều hàng.
5. Ghi bản ghi audit hoặc trạng thái nghiệp vụ liên quan.
6. Commit.

Nếu bước 4 gặp deadlock, không thể mặc định rằng chỉ cần chạy lại bước 4. Các bước đọc và tính toán ở lần đầu có thể đã trở nên lỗi thời. Nếu transaction bị rollback, mọi thay đổi trong transaction đó phải được thực hiện lại trong lần thử mới.

```text
Sai: retry một câu lệnh với dữ liệu cũ

BEGIN
  SELECT ... -> dữ liệu X
  tính toán từ X
  UPDATE ... -> deadlock
  retry UPDATE bằng kết quả đã tính từ X

Đúng: retry toàn bộ transaction

Lần thử 1: BEGIN -> SELECT -> tính -> UPDATE -> deadlock -> ROLLBACK
Lần thử 2: BEGIN mới -> SELECT mới -> tính lại -> UPDATE -> COMMIT
```

Transaction mới phải bao trùm toàn bộ thao tác cần tính nguyên tử. Không để một phần cập nhật của lần thử trước được commit rồi chạy lại toàn bộ nghiệp vụ như thể chưa có gì xảy ra.

## 3. Vì sao phải đọc lại dữ liệu trước mỗi lần thử?

### Snapshot cũ có thể không còn phù hợp

Ở `REPEATABLE READ`, một transaction có thể dùng cùng snapshot cho nhiều consistent read. Trong PostgreSQL, `REPEATABLE READ` và `SERIALIZABLE` duy trì snapshot của transaction. Trong MySQL InnoDB, consistent read ở `REPEATABLE READ` thường dùng lại read view được tạo ở lần đọc đầu tiên.

Nếu transaction cũ đã thất bại, dữ liệu mà nó đọc trước đó không phải cơ sở phù hợp để tiếp tục tính toán. Bắt đầu transaction mới cho phép database thiết lập snapshot mới theo isolation level đang dùng.

### Trạng thái có thể đã đổi sau lần đọc

Trong khoảng thời gian giữa lần đọc đầu và lần retry, transaction khác có thể:

- Cập nhật số dư, số lượng tồn kho hoặc trạng thái đơn hàng.
- Xóa hàng mà ứng dụng đang xử lý.
- Thêm hàng mới làm thay đổi điều kiện tổng hợp hoặc phạm vi khóa.
- Thay đổi version của một entity.
- Hoàn tất một thao tác nghiệp vụ khiến yêu cầu ban đầu không còn hợp lệ.

Đọc lại giúp ứng dụng áp dụng quy tắc nghiệp vụ lên trạng thái mới. Nếu không còn đủ điều kiện, lần thử mới cần kết thúc bằng kết quả nghiệp vụ phù hợp.

### Đọc lại cả dữ liệu phụ thuộc

Không chỉ đọc lại hàng cuối cùng được cập nhật. Nếu quyết định phụ thuộc vào nhiều bảng, số dư tổng, giới hạn tín dụng, trạng thái tồn kho hoặc cấu hình, cần đọc lại toàn bộ dữ liệu liên quan trong transaction mới.

Ví dụ, kiểm tra hạn mức tín dụng cần đọc lại cả dư nợ hiện tại và hạn mức áp dụng. Chỉ đọc lại hàng hóa đơn nhưng dùng hạn mức cũ trong bộ nhớ vẫn có thể dẫn đến quyết định sai.

## 4. Phân biệt retry transaction với retry statement

Một số lỗi chỉ rollback câu lệnh hiện tại; một số lỗi khiến toàn transaction bị rollback hoặc đánh dấu không thể tiếp tục. Ứng dụng cần biết trạng thái transaction sau lỗi trước khi quyết định.

| Tình huống | Trạng thái thường gặp | Hành động phù hợp |
|---|---|---|
| MySQL InnoDB deadlock (1213) | InnoDB chọn nạn nhân và rollback transaction | Bắt đầu transaction mới, đọc lại và chạy lại toàn bộ đơn vị công việc |
| MySQL InnoDB lock wait timeout (1205) | Mặc định thường rollback statement; cấu hình có thể rollback cả transaction | Kiểm tra trạng thái transaction; rollback toàn bộ và retry toàn transaction nếu lỗi được phân loại là tạm thời |
| PostgreSQL serialization failure (`40001`) | Transaction bị hủy và ở trạng thái cần rollback | Rollback, bắt đầu transaction mới và chạy lại toàn bộ transaction |
| PostgreSQL deadlock (`40P01`) | Một transaction bị hủy để phá chu trình | Rollback và retry toàn bộ transaction |
| Constraint violation | Vi phạm dữ liệu hoặc quy tắc ràng buộc | Thông thường không retry nguyên trạng; sửa dữ liệu hoặc trả lỗi nghiệp vụ |
| Lỗi cú pháp hoặc thiếu quyền | Lỗi cố định cho đến khi mã/cấu hình thay đổi | Không retry tự động |

Không phải mọi lock timeout đều nên retry vô hạn. Nếu blocker không kết thúc, mỗi lần thử có thể chỉ chờ timeout rồi thất bại tiếp. Cần tìm nguyên nhân blocking và đặt ngân sách retry hữu hạn.

## 5. Mẫu Java JDBC: mỗi lần thử dùng một transaction mới

Ví dụ sau minh họa cấu trúc retry cho một thao tác chuyển tiền. Mỗi vòng lặp lấy connection, bắt đầu transaction, đọc lại hai tài khoản, kiểm tra số dư, ghi thay đổi và commit. Khi có lỗi retryable, transaction được rollback và connection được đóng trước khi chờ lần thử tiếp theo.

```java
public void transfer(
        DataSource dataSource,
        long fromId,
        long toId,
        BigDecimal amount
) throws SQLException, InterruptedException {
    int maxAttempts = 4;

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try {
                Account from = loadAccount(connection, fromId);
                Account to = loadAccount(connection, toId);

                if (from.balance().compareTo(amount) < 0) {
                    throw new InsufficientFundsException();
                }

                updateBalance(connection, fromId, from.balance().subtract(amount));
                updateBalance(connection, toId, to.balance().add(amount));

                connection.commit();
                return;
            } catch (SQLException | RuntimeException failure) {
                rollbackQuietly(connection, failure);

                if (!isRetryable(failure) || attempt == maxAttempts) {
                    throw failure;
                }
            }
        }

        sleepWithBackoff(attempt);
    }
}
```

Đây là khung cấu trúc; các hàm `loadAccount`, `updateBalance`, `rollbackQuietly`, `isRetryable` và `sleepWithBackoff` cần được triển khai theo driver và ứng dụng. Điểm cốt lõi là `loadAccount()` được gọi lại bên trong mỗi vòng thử, sau khi connection/transaction của lần trước đã kết thúc.

### Thứ tự khóa nhất quán

Ví dụ chuyển tiền nên cập nhật tài khoản theo thứ tự id tăng dần để giảm khả năng deadlock khi hai yêu cầu chuyển tiền ngược chiều:

```java
long firstId = Math.min(fromId, toId);
long secondId = Math.max(fromId, toId);

Account first = loadAccount(connection, firstId);
Account second = loadAccount(connection, secondId);

// Tính toán và ghi theo cùng một thứ tự trong mọi luồng.
```

Phần tính toán vẫn phải biết tài khoản nào là nguồn và tài khoản nào là đích. Thứ tự truy cập nhất quán chỉ nhằm giảm vòng chờ; nó không thay thế kiểm tra số dư và tính đúng đắn nghiệp vụ.

### Không giữ connection trong thời gian backoff

Trong ví dụ, khối `try-with-resources` kết thúc trước `sleepWithBackoff()`. Điều này trả connection về pool trong khi chờ. Không nên giữ connection hoặc transaction mở trong thời gian backoff vì có thể làm cạn connection pool và tiếp tục giữ tài nguyên database.

Nếu `commit()` ném lỗi do mất kết nối, kết quả commit có thể không xác định: server có thể đã commit nhưng client chưa nhận được phản hồi. Đây là trường hợp đặc biệt, không nên tự động coi là rollback và chuyển tiền lại. Phần idempotency bên dưới giải thích cách xử lý.

## 6. Phân loại lỗi có thể retry

Không nên viết `catch (Exception e) { retry(); }`. Làm vậy có thể lặp cả lỗi lập trình, lỗi dữ liệu, lỗi xác thực, lỗi cấu hình hoặc lỗi nghiệp vụ.

### MySQL

- Error code `1213`, SQLSTATE `40001`: deadlock. Thường phù hợp để retry toàn bộ transaction sau rollback.
- Error code `1205`: lock wait timeout. Có thể retry có giới hạn sau khi rollback transaction, nhưng cần điều tra blocker nếu lặp lại.
- Lỗi mất kết nối hoặc lỗi giao tiếp ở thời điểm commit: trạng thái commit có thể không xác định. Cần đối soát bằng idempotency key hoặc mã nghiệp vụ.

### PostgreSQL

- SQLSTATE `40001`: serialization failure. Retry toàn bộ transaction.
- SQLSTATE `40P01`: deadlock detected. Retry toàn bộ transaction sau khi transaction thất bại được rollback.
- SQLSTATE `55P03`: lock not available, thường gặp với `NOWAIT`. Có thể retry nếu nghiệp vụ chấp nhận chờ và có giới hạn.
- SQLSTATE `57014`: query canceled, có thể do statement timeout hoặc hủy thủ công. Không tự động retry nếu chưa xác định nguyên nhân.

Ví dụ phân loại theo SQLSTATE và mã vendor trong JDBC:

```java
boolean isRetryable(SQLException exception) {
    for (SQLException current = exception;
         current != null;
         current = current.getNextException()) {

        String state = current.getSQLState();
        int vendorCode = current.getErrorCode();

        if ("40001".equals(state) || "40P01".equals(state)) {
            return true;
        }

        // MySQL lock wait timeout: chỉ retry sau khi rollback transaction.
        if (vendorCode == 1205) {
            return true;
        }
    }
    return false;
}
```

Đây chỉ là ví dụ khởi đầu. SQLSTATE `40001` có thể đại diện cho lỗi serialization trong PostgreSQL và deadlock trong MySQL. Hãy xác nhận mã lỗi của driver đang dùng, phân biệt timeout theo database và bổ sung điều kiện theo loại thao tác. Không đưa lỗi kết nối ở thời điểm commit vào danh sách retry đơn giản nếu chưa có cơ chế xác định kết quả commit.

## 7. Backoff và giới hạn số lần thử

Nếu nhiều client cùng retry ngay lập tức, chúng có thể tạo ra một đợt tải mới và tiếp tục tranh chấp. Backoff làm giãn thời gian giữa các lần thử. Jitter thêm một khoảng ngẫu nhiên để các client không đồng loạt thức dậy cùng lúc.

Một chiến lược exponential backoff có giới hạn:

```text
delay = min(maxDelay, baseDelay * 2^(attempt - 1))
sleep  = random(0, delay)
```

Ví dụ với `baseDelay = 50 ms`, `maxDelay = 800 ms`:

| Lần thử tiếp theo | Khoảng delay tối đa trước jitter |
|---:|---:|
| 2 | 50 ms |
| 3 | 100 ms |
| 4 | 200 ms |
| 5 | 400 ms |
| 6 trở đi | 800 ms |

Số lần thử phải hữu hạn. Một thao tác nghiệp vụ có SLA 2 giây không thể retry 10 lần với mỗi lần chờ khóa 5 giây. Hãy phối hợp `maxAttempts`, timeout câu lệnh, timeout transaction và deadline của request.

Ví dụ hàm delay có jitter:

```java
private void sleepWithBackoff(int attempt) throws InterruptedException {
    long baseMillis = 50L;
    long maxMillis = 800L;
    int exponent = Math.min(attempt - 1, 10);

    long cap = Math.min(maxMillis, baseMillis * (1L << exponent));
    long delay = ThreadLocalRandom.current().nextLong(cap + 1);
    Thread.sleep(delay);
}
```

Trong hệ thống có deadline, delay phải bị giới hạn bởi thời gian còn lại của request. Khi hết ngân sách, trả lỗi phù hợp thay vì tiếp tục retry.

## 8. Retry trong Spring: vòng retry phải nằm ngoài ranh giới transaction

Một lỗi phổ biến trong Spring là đặt vòng retry bên trong một phương thức `@Transactional` duy nhất:

```java
@Transactional
public void updateWithRetry() {
    for (int attempt = 1; attempt <= 3; attempt++) {
        try {
            // đọc và ghi
        } catch (RuntimeException ex) {
            // thử lại trong cùng transaction
        }
    }
}
```

Đây không phải cấu trúc an toàn. Nếu transaction đã bị đánh dấu rollback-only hoặc database đã hủy transaction, việc chạy lại trong cùng phạm vi không tạo transaction mới. Đến lúc commit, Spring có thể ném `UnexpectedRollbackException` hoặc database từ chối câu lệnh tiếp theo.

Đặt coordinator retry ở ngoài transaction và gọi một đơn vị công việc transactional riêng cho mỗi lần thử:

```java
public final class TransferRetryService {
    private final TransferTransactionService transactionService;

    public void transfer(TransferCommand command) {
        for (int attempt = 1; attempt <= 4; attempt++) {
            try {
                transactionService.transferOnce(command);
                return;
            } catch (RuntimeException failure) {
                if (!isRetryable(failure) || attempt == 4) {
                    throw failure;
                }
                backoff(attempt);
            }
        }
    }
}
```

```java
@Service
public class TransferTransactionService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void transferOnce(TransferCommand command) {
        // Đọc lại dữ liệu trong transaction này.
        // Kiểm tra nghiệp vụ và ghi tất cả thay đổi.
    }
}
```

`transferOnce()` phải được gọi qua Spring proxy để `@Transactional` có hiệu lực. Nếu coordinator và phương thức transactional nằm trong cùng object và gọi qua `this.transferOnce()`, self-invocation có thể bỏ qua proxy.

`REQUIRES_NEW` tạo transaction riêng và suspend transaction hiện tại nếu có. Tốt nhất coordinator retry không nằm trong một transaction bao ngoài; nếu có transaction ngoài, nó có thể vẫn giữ khóa hoặc snapshot trong suốt thời gian retry và tiếp tục gây blocking. Với Spring Retry, cũng cần bảo đảm thứ tự interceptor sao cho mỗi lần retry đi qua ranh giới transaction mới, thay vì retry bên trong một transaction đã thất bại.

## 9. Mỗi lần thử phải tính lại quyết định nghiệp vụ

Đọc lại dữ liệu chỉ có ý nghĩa nếu ứng dụng dùng dữ liệu mới để tính lại kết quả. Không nên đọc dữ liệu mới rồi vẫn áp dụng giá trị đã tính từ lần trước.

Ví dụ trừ tồn kho:

```java
@Transactional
public void reserveOnce(long productId, int requestedQuantity) {
    Inventory inventory = repository.findById(productId)
        .orElseThrow(ProductNotFoundException::new);

    if (inventory.getAvailable() < requestedQuantity) {
        throw new InsufficientStockException();
    }

    inventory.setAvailable(
        inventory.getAvailable() - requestedQuantity
    );
}
```

Mỗi lần gọi `reserveOnce()` phải nạp entity trong persistence context của transaction mới. Không truyền entity đã load từ lần thử trước vào phương thức transactional rồi dùng lại. Nếu entity được cache hoặc giữ trong persistence context cũ, nó có thể chứa trạng thái stale.

Với JPA, mỗi transaction mới thường cần một persistence context mới hoặc phải bảo đảm entity được tải lại trong context hiện tại. Không dùng `EntityManager` đã ở trạng thái lỗi để tiếp tục thao tác sau một optimistic lock/serialization failure. Hãy để transaction kết thúc và tạo context phù hợp cho lần thử mới.

## 10. Không lặp tác dụng phụ ngoài database

Một transaction có thể thất bại sau khi ứng dụng đã gửi email, gọi API thanh toán, phát message hoặc ghi file. Rollback database không thể tự thu hồi các tác dụng phụ đã xảy ra bên ngoài.

Ví dụ nguy hiểm:

```text
BEGIN
  UPDATE orders
  gửi email "đơn hàng đã xác nhận"
  INSERT payment_record
  -> deadlock
ROLLBACK

Retry:
  UPDATE orders
  gửi email lần thứ hai
  INSERT payment_record
  COMMIT
```

Khách hàng có thể nhận email xác nhận dù lần đầu transaction đã rollback, rồi nhận thêm email ở lần retry. Với thanh toán hoặc API ngoài, việc gọi lặp có thể tạo giao dịch trùng.

### Ghi ý định gửi cùng transaction

Một cách phổ biến là dùng transactional outbox. Transaction nghiệp vụ ghi thay đổi và một outbox event trong cùng commit:

```sql
BEGIN;

UPDATE orders
SET status = 'CONFIRMED'
WHERE id = :order_id;

INSERT INTO outbox_events(event_id, event_type, aggregate_id, payload)
VALUES (:event_id, 'ORDER_CONFIRMED', :order_id, :payload);

COMMIT;
```

Một worker riêng đọc outbox và gửi sự kiện sau commit. Nếu transaction rollback, cả thay đổi nghiệp vụ và outbox event đều không tồn tại. Nếu worker gửi lại do lỗi mạng, consumer hoặc dịch vụ đích vẫn cần idempotency để xử lý message trùng.

Không gửi email hoặc gọi API ngoài trực tiếp trong mỗi lần thử trước khi commit, trừ khi thao tác đó có cơ chế idempotency và được thiết kế rõ cho retry.

## 11. Idempotency và trường hợp không biết COMMIT đã thành công chưa

Có một tình huống khó hơn deadlock: ứng dụng gửi `COMMIT`, database commit thành công, nhưng kết nối bị đứt trước khi client nhận được phản hồi. Client không biết transaction đã commit hay chưa.

Nếu ứng dụng coi đó là rollback và thực hiện lại thao tác, có thể tạo tác dụng phụ trùng. Đây không phải trường hợp thông thường của deadlock victim; trạng thái commit là **không xác định từ phía client**.

Với API có thể được gọi lại, dùng idempotency key duy nhất cho một yêu cầu nghiệp vụ:

```sql
CREATE TABLE processed_requests (
    request_key VARCHAR(100) PRIMARY KEY,
    result_json JSON,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Trong transaction, ứng dụng ghi nhận `request_key` và kết quả nghiệp vụ. Nếu key đã tồn tại, nó trả lại kết quả đã ghi thay vì thực hiện nghiệp vụ lần nữa. Việc ghi key và thay đổi nghiệp vụ phải nằm trong cùng transaction để tránh trạng thái key đã lưu nhưng thao tác chưa commit hoặc ngược lại.

Idempotency key cần được tạo ổn định ở cấp request, không tạo key mới cho từng lần retry nội bộ. Nếu client gửi lại cùng yêu cầu sau timeout, server nhận ra đó là cùng một thao tác.

## 12. Những trường hợp không nên retry tự động

Không retry nguyên trạng nếu:

- Lỗi cú pháp, lỗi mapping hoặc lỗi lập trình khiến cùng câu lệnh luôn thất bại.
- Vi phạm ràng buộc do dữ liệu không hợp lệ, chẳng hạn duplicate key ngoài luồng idempotency đã thiết kế.
- Người dùng không đủ quyền hoặc đối tượng không tồn tại.
- Quy tắc nghiệp vụ không còn thỏa sau khi đọc lại, ví dụ số dư không đủ hoặc đơn hàng đã chuyển trạng thái.
- Timeout do blocker tồn tại lâu mà chưa có cơ chế giảm tải hoặc giới hạn tổng thời gian chờ.
- Kết quả commit không xác định và hệ thống không có idempotency/đối soát.
- Thao tác có tác dụng phụ ngoài database không thể lặp an toàn.

Một optimistic lock conflict cũng không phải lúc nào cần retry tự động. Nếu hai người cùng sửa biểu mẫu, ứng dụng có thể cần hiển thị thay đổi mới và yêu cầu người dùng hợp nhất thay vì tự ghi lại nội dung cũ.

## 13. Ghi log và quan sát retry

Retry có thể che bớt lỗi đồng thời tạm thời, nhưng nếu không ghi nhận thì đội vận hành khó biết hệ thống đang gặp nhiều deadlock hoặc serialization failure.

Mỗi lần thử nên ghi lại các thông tin không nhạy cảm:

- Mã request hoặc idempotency key.
- Loại nghiệp vụ và định danh đối tượng liên quan.
- Số lần thử hiện tại và tổng số lần tối đa.
- SQLSTATE, vendor error code và loại lỗi.
- Thời gian transaction, thời gian backoff và tổng thời gian request.
- Kết quả cuối cùng: thành công, conflict nghiệp vụ hay hết ngân sách retry.

Không ghi toàn bộ dữ liệu nhạy cảm hoặc nội dung bí mật của câu SQL vào log. Dùng metric để theo dõi tỷ lệ retry, deadlock, serialization failure, lock timeout và số request hết ngân sách. Tỷ lệ retry tăng kéo dài có thể là dấu hiệu cần sửa thứ tự khóa, index hoặc kích thước transaction.

## 14. Quy trình retry chuẩn

```text
Nhận yêu cầu nghiệp vụ
        |
        v
Tạo request/idempotency key ổn định
        |
        v
Mở transaction mới
        |
        v
Đọc lại toàn bộ dữ liệu phụ thuộc
        |
        v
Kiểm tra và tính lại quy tắc nghiệp vụ
        |
        v
Thực hiện tất cả thay đổi database
        |
        v
COMMIT thành công?
     /        \
   Có          Không
   |             |
   v             v
Trả kết quả   Phân loại lỗi
                 |
          Có retry được và còn lượt?
              /          \
            Có            Không
            |               |
            v               v
      ROLLBACK/đóng     Trả lỗi phù hợp
      transaction      và ghi log
            |
            v
      Backoff + jitter
            |
            v
      Transaction mới
```

Các bước đọc và tính toán phải nằm bên trong transaction mới. Backoff diễn ra sau khi transaction cũ đã kết thúc và tài nguyên connection đã được trả lại.

## 15. Checklist khi triển khai retry

1. Xác định lỗi nào có thể retry bằng SQLSTATE/vendor code cụ thể.
2. Xác định transaction đã bị rollback toàn bộ, rollback statement hay đang ở trạng thái aborted.
3. Bảo đảm lần thử mới đi qua ranh giới transaction mới.
4. Đọc lại mọi dữ liệu và version mà quyết định nghiệp vụ phụ thuộc vào.
5. Tính lại điều kiện và giá trị ghi; không tái sử dụng entity hoặc kết quả tính toán stale.
6. Retry toàn bộ đơn vị công việc nguyên tử, không chỉ câu SQL cuối.
7. Đặt số lần thử, backoff, jitter và deadline hữu hạn.
8. Không giữ connection hoặc transaction trong lúc chờ backoff.
9. Đưa email, message và API ngoài ra sau commit hoặc bảo vệ bằng outbox/idempotency.
10. Xử lý trường hợp commit không xác định bằng request key và cơ chế đối soát.
11. Ghi metric/log cho số lần retry, loại lỗi và kết quả cuối cùng.
12. Kiểm thử với hai hoặc nhiều transaction cạnh tranh để xác nhận lần retry đọc dữ liệu mới và không tạo tác dụng phụ trùng.

## 16. Tự kiểm tra

**Vì sao không nên retry câu UPDATE cuối cùng sau deadlock bằng giá trị đã tính từ lần đọc trước?**

Vì transaction khác có thể đã thay đổi dữ liệu. Giá trị cũ có thể ghi đè trạng thái mới hoặc vi phạm quy tắc nghiệp vụ. Cần tạo transaction mới, đọc lại và tính lại.

**PostgreSQL trả SQLSTATE `40001`. Ứng dụng nên làm gì?**

Rollback transaction thất bại, bắt đầu transaction mới, đọc lại dữ liệu và chạy lại toàn bộ đơn vị công việc nếu còn lượt retry.

**Vì sao vòng retry trong cùng một phương thức `@Transactional` có thể không tạo transaction mới?**

Vì các lần lặp có thể vẫn chạy trong cùng transaction đã bị đánh dấu rollback-only hoặc đã bị database hủy. Vòng retry cần nằm ngoài ranh giới transaction, gọi một phương thức transactional riêng qua proxy cho từng lần thử.

**Có nên retry mọi exception không?**

Không. Chỉ retry lỗi tạm thời đã được phân loại. Lỗi dữ liệu, quyền, cú pháp và quy tắc nghiệp vụ cần được xử lý riêng.

**Nếu `COMMIT` bị mất phản hồi do lỗi mạng, có thể coi như transaction đã rollback không?**

Không. Database có thể đã commit nhưng client chưa nhận được phản hồi. Cần idempotency key hoặc đối soát trạng thái trước khi chạy lại nghiệp vụ.

**Tác dụng phụ như gửi email nên diễn ra ở đâu?**

Thường nên thực hiện sau commit, thông qua outbox hoặc cơ chế idempotency để rollback/retry không tạo email hay message trùng.

Retry an toàn dựa trên một nguyên tắc: **mỗi lần thử là một transaction mới với dữ liệu được đọc lại và quyết định được tính lại**. Khi kết hợp phân loại lỗi, rollback rõ ràng, backoff hữu hạn và idempotency cho tác dụng phụ, ứng dụng có thể phục hồi trước xung đột đồng thời mà vẫn giữ đúng ý nghĩa nghiệp vụ.
