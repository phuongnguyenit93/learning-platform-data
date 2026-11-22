# Kiểm thử khóa, deadlock và lost update bằng nhiều kết nối

## Mục tiêu

Các lỗi đồng thời trong MySQL thường chỉ xuất hiện khi nhiều transaction cùng đọc hoặc sửa một tập dữ liệu. Một câu `UPDATE` chạy đúng khi thử riêng lẻ vẫn có thể chờ khóa, tạo deadlock hoặc ghi đè thay đổi của transaction khác khi chạy đồng thời. Để kiểm chứng hành vi, cần mở nhiều kết nối độc lập, điều khiển thứ tự câu lệnh và quan sát trạng thái khóa trong lúc các transaction còn hoạt động.

Bài học thuộc module **DATABASE_MYSQL**, tập trung vào thiết kế bảng, kiểu dữ liệu, khóa, SQL, index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn và vận hành cơ sở dữ liệu quan hệ. Bài này hướng dẫn dựng lab nhiều session để tái hiện row lock, lock wait, deadlock và lost update; sau đó áp dụng pessimistic locking, atomic update và optimistic locking để bảo vệ dữ liệu.

Sau bài học, bạn có thể:

- Tạo hai hoặc nhiều kết nối MySQL độc lập để tái hiện tranh chấp dữ liệu.
- Phân biệt blocking, lock wait timeout, deadlock và lost update.
- Giải thích ảnh hưởng của index, isolation level và thời gian giữ transaction tới phạm vi khóa.
- Dùng `SELECT ... FOR UPDATE`, câu lệnh cập nhật nguyên tử và version column để tránh lost update.
- Quan sát transaction và lock bằng Performance Schema, `sys.innodb_lock_waits` và InnoDB status.
- Viết kiểm thử đồng thời có thể lặp lại và xác minh kết quả dữ liệu sau commit/rollback.

## 1. Chuẩn bị môi trường thử nghiệm

Dùng MySQL với storage engine InnoDB. Tạo bảng nhỏ để các session cùng thao tác trên một vài hàng:

```sql
CREATE DATABASE IF NOT EXISTS concurrency_lab;
USE concurrency_lab;

CREATE TABLE accounts (
  account_id BIGINT PRIMARY KEY,
  balance DECIMAL(12,2) NOT NULL
) ENGINE = InnoDB;

INSERT INTO accounts (account_id, balance) VALUES
  (1, 100.00),
  (2, 100.00)
ON DUPLICATE KEY UPDATE balance = 100.00;
```

Các ví dụ giả định bạn mở hai cửa sổ terminal hoặc hai tab SQL, mỗi tab dùng một kết nối độc lập tới cùng instance và schema. Gọi chúng là **Session A** và **Session B**. Không dùng chung một connection object cho cả hai luồng vì khi đó không tái hiện được tranh chấp giữa hai transaction độc lập.

Xác nhận mỗi session có connection ID riêng:

```sql
SELECT CONNECTION_ID() AS connection_id,
       @@transaction_isolation AS transaction_isolation,
       @@autocommit AS autocommit;
```

Với MySQL 8.0, biến `transaction_isolation` cho biết isolation level của session. InnoDB thường dùng `REPEATABLE READ` mặc định, nhưng hãy đọc giá trị thực tế thay vì giả định. Các ví dụ cần transaction tường minh, vì vậy dùng `START TRANSACTION` trước thao tác cần giữ khóa.

Đặt lại dữ liệu giữa các bài thực hành:

```sql
UPDATE accounts SET balance = 100.00 WHERE account_id IN (1, 2);
```

Chỉ chạy các bài tập gây tranh chấp trên môi trường thử nghiệm. Không dùng session quản trị hoặc dữ liệu production để cố ý tạo deadlock hay giữ khóa lâu.

## 2. Phân biệt các hiện tượng đồng thời

| Hiện tượng | Điều xảy ra | Dấu hiệu thường thấy |
|---|---|---|
| Blocking / lock wait | Transaction cần một khóa đang do transaction khác giữ | Câu lệnh chờ cho đến khi khóa được nhả hoặc hết timeout |
| Lock wait timeout | Thời gian chờ khóa vượt `innodb_lock_wait_timeout` | Lỗi MySQL `1205` |
| Deadlock | Các transaction tạo chu trình chờ khóa lẫn nhau | InnoDB chọn một transaction làm nạn nhân; thường nhận lỗi `1213` |
| Lost update | Hai transaction cùng dựa trên một giá trị cũ rồi ghi giá trị tuyệt đối; lần ghi sau làm mất thay đổi trước | Không nhất thiết có lỗi SQL; kết quả cuối sai nghiệp vụ |

Blocking không đồng nghĩa deadlock. Một transaction có thể chờ hợp lệ cho đến khi transaction đang giữ khóa commit. Deadlock là chu trình phụ thuộc không thể tự tiến triển, nên InnoDB phải hủy một transaction để giải phóng chu trình.

Lost update còn nguy hiểm hơn vì câu lệnh có thể hoàn tất thành công. Ứng dụng chỉ phát hiện được nếu kiểm tra invariant nghiệp vụ, dùng khóa hoặc version, hay đối chiếu kết quả mong đợi.

## 3. Kiểm thử row lock với `SELECT ... FOR UPDATE`

`SELECT ... FOR UPDATE` là locking read. Trong một transaction InnoDB, câu lệnh đọc các hàng phù hợp và lấy khóa độc quyền cần thiết để transaction có thể cập nhật chúng. Khóa được giữ đến khi transaction commit hoặc rollback.

**Session A**:

```sql
START TRANSACTION;

SELECT account_id, balance
FROM accounts
WHERE account_id = 1
FOR UPDATE;
```

Session A giữ khóa hàng `account_id = 1`. Chưa commit hoặc rollback.

**Session B**:

```sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 10.00
WHERE account_id = 1;
```

Câu `UPDATE` ở Session B sẽ phải chờ khóa của Session A. Trong lúc B đang chờ, quay lại A:

```sql
UPDATE accounts
SET balance = balance - 5.00
WHERE account_id = 1;

COMMIT;
```

Sau khi A commit, câu lệnh của B có thể tiếp tục. Kết thúc B:

```sql
COMMIT;
```

Kiểm tra:

```sql
SELECT * FROM accounts WHERE account_id = 1;
```

Giá trị cuối phải phản ánh cả hai lần trừ, tức `85.00`. Nếu B bị timeout trước khi A nhả khóa, hãy xử lý transaction của B theo phần lock wait timeout bên dưới.

`SELECT ... FOR UPDATE` chỉ có tác dụng giữ khóa khi nằm trong transaction còn mở. Nếu bật autocommit và chạy locking read như một statement độc lập, transaction có thể kết thúc ngay sau statement và khóa được nhả trước thao tác tiếp theo.

## 4. Kiểm thử lock wait timeout

Đặt timeout ngắn cho Session B để lab không phải chờ lâu. Ví dụ:

```sql
SET SESSION innodb_lock_wait_timeout = 5;
```

**Session A** giữ khóa:

```sql
START TRANSACTION;
SELECT balance FROM accounts WHERE account_id = 1 FOR UPDATE;
```

**Session B** bắt đầu transaction và thử cập nhật cùng hàng:

```sql
START TRANSACTION;
UPDATE accounts
SET balance = balance + 1
WHERE account_id = 1;
```

Nếu A giữ khóa lâu hơn 5 giây, B nhận lỗi `1205: Lock wait timeout exceeded`. Trong cấu hình mặc định, lock wait timeout thường rollback statement bị timeout, không nhất thiết rollback toàn transaction. Biến `innodb_rollback_on_timeout` có thể thay đổi hành vi này.

Ứng dụng nên xử lý rõ ràng: rollback toàn bộ transaction B, đóng hoặc trả connection về pool ở trạng thái sạch, rồi chỉ retry toàn bộ nghiệp vụ nếu lỗi được xem là tạm thời và thao tác có thể retry an toàn.

```sql
ROLLBACK;
```

Trên A, giải phóng khóa:

```sql
COMMIT;
```

Không tiếp tục dùng transaction B như thể chưa có lỗi. Sau timeout, transaction có thể vẫn còn hoạt động và giữ những khóa đã lấy trước đó. Chủ động rollback giúp giải phóng trạng thái và tránh giữ lock ngoài ý muốn.

## 5. Tái hiện deadlock bằng hai session

Deadlock xuất hiện khi hai transaction giữ khóa mà transaction kia cần. Tạo thứ tự truy cập khác nhau để tái hiện:

Đặt lại dữ liệu:

```sql
UPDATE accounts SET balance = 100.00 WHERE account_id IN (1, 2);
```

**Bước 1 — Session A** khóa hàng 1:

```sql
START TRANSACTION;
UPDATE accounts SET balance = balance - 10 WHERE account_id = 1;
```

**Bước 2 — Session B** khóa hàng 2:

```sql
START TRANSACTION;
UPDATE accounts SET balance = balance - 20 WHERE account_id = 2;
```

**Bước 3 — Session A** thử khóa hàng 2 và bị chờ:

```sql
UPDATE accounts SET balance = balance + 10 WHERE account_id = 2;
```

Để câu lệnh A tiếp tục chờ, chưa kết thúc transaction A.

**Bước 4 — Session B** thử khóa hàng 1:

```sql
UPDATE accounts SET balance = balance + 20 WHERE account_id = 1;
```

Lúc này A đang chờ khóa do B giữ, còn B đang chờ khóa do A giữ. InnoDB phát hiện chu trình deadlock và chọn một transaction làm nạn nhân. Session được chọn thường nhận lỗi `1213: Deadlock found when trying to get lock`; transaction nạn nhân bị rollback. Transaction còn lại có thể tiếp tục sau khi khóa được giải phóng.

Không giả định Session A hoặc B luôn là nạn nhân. InnoDB chọn nạn nhân dựa trên chi phí rollback và trạng thái giao dịch. Sau khi thấy lỗi, kiểm tra trạng thái cả hai session; nếu transaction còn lại hoàn tất thì commit nó theo đúng mục đích bài lab. Đặt lại dữ liệu trước lần chạy tiếp theo.

Ứng dụng phải retry **toàn bộ transaction** bị deadlock, không chỉ câu SQL cuối. Các lần đọc và quyết định nghiệp vụ trước đó có thể đã dựa trên snapshot hoặc trạng thái khóa cũ.

## 6. Quan sát lock và transaction đang chờ

Trong lúc Session B đang chờ, mở Session C hoặc một tab giám sát:

```sql
SELECT *
FROM sys.innodb_lock_waits;
```

View `sys.innodb_lock_waits` tóm tắt transaction đang chờ và transaction đang chặn. Nó cần schema `sys` được cài đặt và quyền đọc phù hợp. Tùy phiên bản hoặc quyền, bạn có thể truy vấn trực tiếp Performance Schema.

Xem các transaction InnoDB đang hoạt động:

```sql
SELECT trx_id, trx_state, trx_started,
       trx_wait_started, trx_mysql_thread_id,
       trx_query
FROM information_schema.innodb_trx;
```

Xem lock được Performance Schema ghi nhận:

```sql
SELECT OBJECT_SCHEMA, OBJECT_NAME, INDEX_NAME,
       LOCK_TYPE, LOCK_MODE, LOCK_STATUS, LOCK_DATA
FROM performance_schema.data_locks;
```

Xem các quan hệ lock đang chờ:

```sql
SELECT REQUESTING_ENGINE_TRANSACTION_ID,
       BLOCKING_ENGINE_TRANSACTION_ID,
       REQUESTING_ENGINE_LOCK_ID,
       BLOCKING_ENGINE_LOCK_ID
FROM performance_schema.data_lock_waits;
```

Các bảng Performance Schema cần được bật và có thể yêu cầu quyền giám sát. `SHOW ENGINE INNODB STATUS\G` cung cấp phần trạng thái InnoDB, bao gồm thông tin deadlock gần nhất được ghi nhận:

```sql
SHOW ENGINE INNODB STATUS\G
```

Phần `LATEST DETECTED DEADLOCK` thường cho biết transaction tham gia, câu lệnh, lock đang giữ và lock đang chờ. Đây là bằng chứng hữu ích để tìm thứ tự truy cập tài nguyên gây deadlock. Nếu có nhiều deadlock liên tiếp, log error hoặc hệ thống giám sát có thể cần lưu thêm dữ liệu vì status chỉ hiển thị deadlock gần nhất.

## 7. Index quyết định phạm vi khóa

InnoDB khóa các index record mà thao tác truy cập, không đơn giản chỉ khóa “một hàng logic” theo cách người viết SQL hình dung. Phạm vi khóa phụ thuộc index được chọn, điều kiện tìm kiếm, isolation level và loại truy vấn.

Ví dụ, truy vấn theo primary key:

```sql
SELECT balance
FROM accounts
WHERE account_id = 1
FOR UPDATE;
```

Vì `account_id` là primary key, InnoDB có thể định vị trực tiếp record tương ứng. Nếu truy vấn theo cột không có index, engine có thể phải quét nhiều record và khóa nhiều index record hơn dự kiến.

Kiểm tra kế hoạch thực thi:

```sql
EXPLAIN
SELECT balance
FROM accounts
WHERE account_id = 1
FOR UPDATE;
```

Trong InnoDB với isolation mặc định `REPEATABLE READ`, locking range scan có thể sử dụng next-key lock (record lock kết hợp gap lock) để ngăn insert vào khoảng khóa liên quan. Truy vấn dùng unique index với điều kiện bằng một giá trị duy nhất đã tồn tại thường chỉ cần khóa record tương ứng; các trường hợp range, record không tồn tại hoặc index không unique có thể khóa phạm vi rộng hơn.

Ở `READ COMMITTED`, nhiều gap lock được giảm hoặc không dùng cho locking read thông thường, nhưng vẫn có ngoại lệ như kiểm tra khóa ngoại và duplicate key. Không đổi isolation level chỉ để né lock mà chưa kiểm tra tác động tới tính nhất quán và workload.

## 8. Tái hiện lost update

Lost update xảy ra khi hai transaction cùng đọc một giá trị cũ, tính giá trị mới ở ứng dụng rồi ghi một giá trị tuyệt đối. Transaction ghi sau có thể ghi đè kết quả của transaction trước.

Đặt lại số dư tài khoản 1 về `100.00`.

**Session A**:

```sql
START TRANSACTION;
SELECT balance FROM accounts WHERE account_id = 1;
-- Ứng dụng đọc 100.00 và tính 90.00
```

**Session B**:

```sql
START TRANSACTION;
SELECT balance FROM accounts WHERE account_id = 1;
-- Ứng dụng cũng đọc 100.00 và tính 80.00
```

**Session A** ghi giá trị đã tính:

```sql
UPDATE accounts SET balance = 90.00 WHERE account_id = 1;
COMMIT;
```

**Session B** sau đó ghi giá trị đã tính từ dữ liệu cũ:

```sql
UPDATE accounts SET balance = 80.00 WHERE account_id = 1;
COMMIT;
```

Giá trị cuối là `80.00`, trong khi nếu cả hai lần trừ 10 và 20 đều được áp dụng thì số dư phải là `70.00`. Cả hai transaction đều có thể commit thành công; database không tự biết rằng giá trị 80 được tính từ một lần đọc đã cũ.

Đây là lý do kiểm thử đồng thời phải kiểm tra invariant nghiệp vụ và kết quả cuối, không chỉ kiểm tra rằng câu lệnh không báo lỗi.

## 9. Ngăn lost update bằng pessimistic locking

Với nghiệp vụ cần đọc giá trị hiện tại rồi quyết định cập nhật, có thể khóa hàng trước khi đọc bằng `SELECT ... FOR UPDATE`.

**Session A**:

```sql
START TRANSACTION;

SELECT balance
FROM accounts
WHERE account_id = 1
FOR UPDATE;

-- Tính giá trị mới dựa trên số dư vừa đọc
UPDATE accounts
SET balance = balance - 10.00
WHERE account_id = 1;

COMMIT;
```

**Session B** phải thực hiện cùng quy tắc: bắt đầu transaction, `SELECT ... FOR UPDATE`, đọc giá trị sau khi lấy được khóa rồi tính và cập nhật. Nếu A đang giữ khóa, B sẽ chờ. Khi A commit, locking read của B đọc phiên bản hiện hành và B tính trên số dư mới.

Đây là pessimistic locking: khóa trước khi thay đổi. Phù hợp khi xung đột thường xuyên hoặc nghiệp vụ cần bảo vệ một chuỗi đọc-sửa-ghi. Giữ transaction ngắn và truy vấn bằng index chọn lọc để hạn chế thời gian blocking.

## 10. Ngăn lost update bằng atomic update

Nếu nghiệp vụ chỉ cần cộng/trừ một lượng xác định, hãy để MySQL thực hiện phép tính trong một câu lệnh thay vì đọc giá trị về ứng dụng rồi ghi lại:

```sql
UPDATE accounts
SET balance = balance - 10.00
WHERE account_id = 1
  AND balance >= 10.00;

SELECT ROW_COUNT() AS affected_rows;
```

Phép trừ được thực hiện nguyên tử trên giá trị hiện hành của hàng. Điều kiện `balance >= 10.00` giúp ngăn số dư âm. Nếu `affected_rows = 0`, có thể tài khoản không tồn tại hoặc số dư không đủ; ứng dụng cần phân biệt theo nghiệp vụ.

Ví dụ tồn kho:

```sql
UPDATE inventory
SET quantity = quantity - ?
WHERE sku = ?
  AND quantity >= ?;
```

Bind cùng số lượng vào hai placeholder và kiểm tra số hàng bị ảnh hưởng. Đây thường là cách đơn giản, hiệu quả cho phép tăng/giảm có điều kiện. Với logic phức tạp phụ thuộc nhiều giá trị vừa đọc, cân nhắc pessimistic lock hoặc optimistic version.

## 11. Ngăn lost update bằng optimistic locking

Optimistic locking phù hợp khi xung đột không thường xuyên. Thêm cột `version` vào bảng:

```sql
CREATE TABLE versioned_accounts (
  account_id BIGINT PRIMARY KEY,
  balance DECIMAL(12,2) NOT NULL,
  version BIGINT NOT NULL DEFAULT 0
) ENGINE = InnoDB;

INSERT INTO versioned_accounts (account_id, balance, version)
VALUES (1, 100.00, 0);
```

Ứng dụng đọc `balance` và `version`, tính giá trị mới rồi cập nhật có điều kiện:

```sql
UPDATE versioned_accounts
SET balance = 90.00,
    version = version + 1
WHERE account_id = 1
  AND version = 0;
```

Nếu `ROW_COUNT() = 1`, cập nhật thành công. Nếu bằng 0, version đã thay đổi hoặc hàng không tồn tại; ứng dụng cần đọc lại, kiểm tra nghiệp vụ và thử lại có giới hạn hoặc báo xung đột.

Trong JPA, có thể dùng `@Version` để Hibernate tự thêm điều kiện version vào câu UPDATE và ném `OptimisticLockException` khi phát hiện xung đột:

```java
@Entity
public class VersionedAccount {
    @Id
    private Long accountId;

    private BigDecimal balance;

    @Version
    private Long version;
}
```

Optimistic locking không khóa hàng trong suốt thời gian ứng dụng xử lý sau lần đọc. Nó phát hiện xung đột ở lúc ghi, nên cần thiết kế retry hoặc phản hồi xung đột phù hợp.

## 12. Giảm deadlock bằng thiết kế truy cập

Không phải mọi deadlock đều là lỗi cấu hình. InnoDB phát hiện và xử lý deadlock để duy trì tính nhất quán. Mục tiêu của thiết kế là giảm tần suất và bảo đảm ứng dụng phục hồi đúng.

Các thực hành hữu ích:

- **Khóa theo thứ tự nhất quán:** nếu nhiều transaction cần các hàng A và B, luôn truy cập A trước B, chẳng hạn sắp xếp ID trước khi cập nhật.
- **Giữ transaction ngắn:** không gọi HTTP, chờ người dùng hoặc xử lý file khi đang giữ khóa.
- **Dùng index phù hợp:** tránh full scan trong `UPDATE`, `DELETE` và locking read nếu chỉ cần vài hàng.
- **Cập nhật tập dữ liệu nhỏ:** chia batch lớn thành các batch có ranh giới nghiệp vụ rõ ràng.
- **Tránh truy cập cùng tài nguyên theo thứ tự ngược:** rà soát code path khác nhau cùng cập nhật các bảng/hàng.
- **Retry toàn bộ transaction khi deadlock:** dùng giới hạn lần thử và backoff có jitter.
- **Kiểm tra constraint và trigger:** một câu lệnh có thể khóa thêm hàng hoặc index do foreign key, unique check và trigger.

Không tìm cách loại bỏ mọi deadlock bằng cách tắt deadlock detection hoặc tăng timeout. Deadlock là tín hiệu về thứ tự khóa và cạnh tranh tài nguyên; hãy xem thông tin InnoDB để sửa nguyên nhân.

## 13. Isolation level và locking read

MySQL InnoDB hỗ trợ các isolation level phổ biến: `READ UNCOMMITTED`, `READ COMMITTED`, `REPEATABLE READ` và `SERIALIZABLE`. Mức isolation ảnh hưởng consistent read, gap locking và khả năng quan sát thay đổi giữa các câu lệnh.

Trong `REPEATABLE READ`, các consistent read thông thường trong transaction dùng snapshot theo quy tắc của InnoDB. Locking read như `SELECT ... FOR UPDATE` là current read, đọc trạng thái mới nhất có thể khóa được thay vì chỉ đọc snapshot cũ.

Để quan sát isolation của session:

```sql
SELECT @@SESSION.transaction_isolation;
```

Đổi isolation chỉ cho transaction kế tiếp trong session:

```sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;
-- Thực hiện bài thử
COMMIT;
```

Không thay đổi global isolation trên production chỉ để làm một bài test qua được. Hãy xác định yêu cầu nhất quán của ứng dụng, kiểm thử lại truy vấn và khóa, rồi thay đổi ở phạm vi nhỏ nhất có thể.

## 14. Kiểm thử bằng Java/JDBC với nhiều kết nối

Trong integration test, mở hai `Connection` riêng từ `DataSource`, tắt auto-commit và dùng latch/barrier để điều khiển thứ tự. Không dùng một connection chia sẻ giữa hai thread.

Ví dụ khung kiểm thử:

```java
try (Connection connectionA = dataSource.getConnection();
     Connection connectionB = dataSource.getConnection()) {
    connectionA.setAutoCommit(false);
    connectionB.setAutoCommit(false);

    // A khóa hàng trước.
    try (PreparedStatement lockA = connectionA.prepareStatement(
            "SELECT balance FROM accounts WHERE account_id = ? FOR UPDATE")) {
        lockA.setLong(1, 1L);
        try (ResultSet resultSet = lockA.executeQuery()) {
            if (resultSet.next()) {
                resultSet.getBigDecimal("balance");
            }
        }
    }

    // Dùng CountDownLatch để cho B thử cập nhật khi A còn giữ khóa.
    // Assert B chờ hoặc nhận lock timeout theo cấu hình test.

    connectionA.commit();
    connectionB.rollback();
}
```

Đây là khung minh họa cho một phần bài test; trong test thực tế, thực hiện thao tác B trên thread riêng và đồng bộ bằng `CountDownLatch`, `CyclicBarrier` hoặc `Future`. Đặt timeout cho test để tránh treo vô hạn, và rollback cả hai connection trong `finally` nếu test thất bại.

Test deadlock cần điều khiển đúng thứ tự khóa: A khóa hàng 1, B khóa hàng 2, A yêu cầu hàng 2, sau đó B yêu cầu hàng 1. Bắt lỗi SQL state/error code và xác minh một transaction bị rollback. Không khẳng định trước session nào sẽ là nạn nhân.

## 15. Ma trận kiểm thử đồng thời

| Bài kiểm thử | Sắp xếp session | Kết quả mong đợi |
|---|---|---|
| Row lock | A `FOR UPDATE`; B update cùng hàng; A commit | B chờ rồi tiếp tục |
| Lock timeout | A giữ khóa lâu; B đặt timeout ngắn và update | B nhận `1205`; ứng dụng rollback transaction B |
| Deadlock | A khóa hàng 1; B khóa hàng 2; mỗi bên yêu cầu hàng còn lại | InnoDB chọn một nạn nhân; nhận `1213` ở transaction bị hủy |
| Lost update | A và B cùng đọc giá trị cũ; lần lượt ghi giá trị tuyệt đối | Tái hiện việc một thay đổi bị ghi đè |
| Pessimistic prevention | Cả hai session đọc `FOR UPDATE` trước khi tính | Session thứ hai đọc giá trị mới sau khi lấy khóa |
| Atomic update | Hai session cùng chạy phép cộng/trừ trên cột trong SQL | Cả hai phép toán được áp dụng trên giá trị hiện hành |
| Optimistic locking | A và B đọc cùng version; A update trước; B update version cũ | B cập nhật 0 hàng hoặc nhận optimistic lock exception |

Với mỗi bài, lưu lại SQL đã chạy, connection ID, thời gian chờ, lỗi, trạng thái transaction và dữ liệu cuối. Kết quả test cần kiểm tra invariant như tổng số dư không đổi trong chuyển tiền, tồn kho không âm và mỗi request chỉ được áp dụng một lần.

## 16. Lỗi thường gặp và cách xử lý

- **Dùng chung một connection cho nhiều thread:** các câu lệnh có thể xen kẽ trên cùng session và không tái hiện hai transaction độc lập. Lấy connection riêng cho mỗi luồng.
- **Quên `START TRANSACTION`:** khóa được nhả ngay sau statement khi autocommit bật. Mở transaction trước locking read.
- **Giữ transaction quá lâu:** session khác bị chặn và undo history tăng. Thu hẹp transaction boundary.
- **Nhầm timeout với deadlock:** `1205` là hết thời gian chờ; `1213` là deadlock. Xử lý transaction và retry theo đúng loại lỗi.
- **Chỉ retry câu lệnh gây deadlock:** các quyết định đọc trước đó có thể không còn đúng. Retry toàn bộ transaction.
- **Bắt lỗi timeout nhưng tiếp tục transaction:** transaction có thể vẫn hoạt động và giữ lock. Chủ động rollback toàn bộ.
- **Không có index cho điều kiện khóa:** engine có thể quét và khóa nhiều record hơn cần thiết. Dùng `EXPLAIN`, tạo index phù hợp và kiểm tra lại phạm vi khóa.
- **Dùng `SELECT` thường để bảo vệ read-modify-write:** consistent read không giữ khóa độc quyền. Dùng `FOR UPDATE`, atomic update hoặc version.
- **Tắt autocommit nhưng không commit/rollback:** connection trả về pool có trạng thái transaction không sạch. Kết thúc transaction rõ ràng.
- **Chỉ kiểm tra lỗi SQL, không kiểm tra kết quả:** lost update có thể xảy ra mà không có exception. Assert dữ liệu cuối và invariant nghiệp vụ.

## 17. Bài tập thực hành

Trên một MySQL instance thử nghiệm, hoàn thành các bước:

1. Tạo schema `concurrency_lab` và bảng `accounts` như phần chuẩn bị; mở Session A, B và một session giám sát.
2. Tái hiện row lock bằng `SELECT ... FOR UPDATE`, xác nhận Session B chờ và tiếp tục sau khi A commit.
3. Đặt `innodb_lock_wait_timeout` ngắn ở B, giữ khóa ở A và xác nhận B nhận lỗi `1205`; rollback B.
4. Tái hiện deadlock bằng cách khóa hai hàng theo thứ tự ngược; ghi lại transaction nạn nhân và phần `LATEST DETECTED DEADLOCK`.
5. Tái hiện lost update bằng hai lần đọc giá trị 100 rồi ghi lần lượt 90 và 80; xác nhận kết quả cuối sai nghiệp vụ.
6. Sửa bài lost update bằng `FOR UPDATE`, chạy lại và xác nhận cả hai thay đổi được áp dụng.
7. Thử atomic update có điều kiện số dư/tồn kho và kiểm tra số hàng bị ảnh hưởng.
8. Thêm cột `version`, thử optimistic locking với hai session cùng version và xác nhận một lần ghi bị từ chối.
9. Dùng `EXPLAIN` và lock monitoring để so sánh truy vấn có index với truy vấn không có index.

**Tiêu chí hoàn thành:** bạn có thể chủ động tạo và giải thích blocking, timeout, deadlock và lost update; chọn được cách bảo vệ phù hợp; đọc được thông tin lock; và chứng minh dữ liệu cuối thỏa invariant sau khi chạy đồng thời.

## Kết luận

Kiểm thử đồng thời cần nhiều kết nối độc lập và thứ tự thao tác được kiểm soát. InnoDB dùng row/index lock để bảo vệ cập nhật, phát hiện deadlock và chọn transaction cần rollback; nhưng lost update vẫn có thể xảy ra nếu ứng dụng đọc rồi ghi giá trị cũ mà không khóa hoặc kiểm tra version. Kết hợp `SELECT ... FOR UPDATE`, atomic update, optimistic locking, index phù hợp và retry toàn transaction sẽ giúp ứng dụng duy trì tính đúng đắn khi nhiều request cùng truy cập dữ liệu.
