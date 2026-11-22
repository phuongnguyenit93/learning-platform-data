# READ COMMITTED và phạm vi nhất quán của từng lần đọc

`READ COMMITTED` là mức cô lập phổ biến trong các hệ quản trị quan hệ. Tên gọi của nó nói lên một bảo đảm quan trọng: một thao tác đọc thông thường chỉ quan sát dữ liệu đã commit trước thời điểm đọc theo quy tắc snapshot của database. Tuy nhiên, điều đó **không có nghĩa toàn bộ transaction nhìn một trạng thái dữ liệu cố định**.

Trong PostgreSQL, `READ COMMITTED` lấy một snapshot mới cho **mỗi câu lệnh**. Vì vậy, hai câu `SELECT` trong cùng một transaction có thể nhìn thấy hai trạng thái đã commit khác nhau nếu một transaction khác commit ở giữa. Đây là điểm phải hiểu rõ khi viết báo cáo, đọc nhiều bảng, kiểm tra điều kiện rồi cập nhật, hoặc tổng hợp dữ liệu qua nhiều câu truy vấn.

Bài học trình bày phạm vi nhất quán của từng lần đọc ở `READ COMMITTED`, lịch thực thi có thể quan sát được, cách tương tác với câu lệnh ghi và khóa, ví dụ trên PostgreSQL, JDBC và Spring, cùng những trường hợp cần mức cô lập hoặc cơ chế bảo vệ mạnh hơn.

## 1. `READ COMMITTED` bảo đảm điều gì?

Một transaction ở mức `READ COMMITTED` không được phép đọc thay đổi chưa commit của transaction khác theo hành vi thông thường. Khi một câu lệnh đọc bắt đầu, database xác định những phiên bản dữ liệu mà câu lệnh được phép nhìn thấy. Các thay đổi đã commit trước snapshot đó có thể được nhìn thấy; các thay đổi commit sau đó thường chỉ xuất hiện trong snapshot của câu lệnh tiếp theo.

Ví dụ, bảng tài khoản có số dư:

| Tài khoản | Số dư ban đầu |
|---|---:|
| A | 600 |
| B | 400 |

Transaction T1 chuyển 100 từ A sang B:

```sql
BEGIN;

UPDATE account
SET balance = balance - 100
WHERE account_id = 'A';

UPDATE account
SET balance = balance + 100
WHERE account_id = 'B';

COMMIT;
```

Transaction T2 đọc dữ liệu ở `READ COMMITTED`:

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT balance
FROM account
WHERE account_id = 'A';

SELECT balance
FROM account
WHERE account_id = 'B';

COMMIT;
```

Nếu T1 commit giữa hai câu SELECT của T2, PostgreSQL có thể trả về:

```text
SELECT A -> 600   (trước commit của T1)
SELECT B -> 500   (sau commit của T1)
```

Mỗi câu SELECT chỉ đọc dữ liệu đã commit, nhưng tổng 600 + 500 = 1.100 không phản ánh một trạng thái đã commit nhất quán của hai tài khoản. Đây là ví dụ về **read skew** (đọc lệch).

### Phạm vi nhất quán là một câu lệnh

Trong PostgreSQL, cách hình dung phù hợp là:

```text
Transaction T2 (READ COMMITTED)
  |
  +-- SELECT A  -> Snapshot S1
  |
  +-- SELECT B  -> Snapshot S2
  |
  +-- SELECT C  -> Snapshot S3

S1, S2, S3 có thể khác nhau nếu transaction khác commit giữa các câu lệnh.
```

Mỗi câu lệnh đọc có một cái nhìn nhất quán riêng đối với các transaction khác. Toàn bộ chuỗi câu lệnh của T2 không được bảo đảm cùng nhìn một snapshot.

**Không nên hiểu `READ COMMITTED` là “mọi lần đọc trong transaction đều nhất quán với nhau”.** Nó là bảo đảm nhất quán ở phạm vi câu lệnh theo cách PostgreSQL triển khai.

## 2. Snapshot theo câu lệnh trong PostgreSQL

PostgreSQL sử dụng MVCC (*Multi-Version Concurrency Control*) để quản lý nhiều phiên bản logic của hàng. Thay vì buộc mọi lần đọc phải chặn mọi lần ghi, hệ quản trị có thể cho truy vấn đọc phiên bản phù hợp với snapshot của nó.

Ở `READ COMMITTED`, snapshot của một câu lệnh thông thường được thiết lập khi câu lệnh bắt đầu thực thi. Nó xác định transaction nào đã commit tại thời điểm đó và phiên bản nào được phép hiển thị.

Minh họa:

```text
Thời gian       T1: cập nhật A và B        T2: báo cáo READ COMMITTED
    |
    |                                      BEGIN
    |                                      SELECT A
    |                                      Snapshot S1 -> A = 600
    |
    |           UPDATE A = 500
    |           UPDATE B = 500
    |           COMMIT
    |
    |                                      SELECT B
    |                                      Snapshot S2 -> B = 500
    |                                      COMMIT
    v
```

Snapshot S1 được xác lập trước khi T1 commit, trong khi S2 được xác lập sau khi T1 commit. T2 vì vậy thấy hai phiên bản khác nhau ở hai câu lệnh.

### Snapshot không phải bản sao vật lý toàn database

Snapshot là quy tắc xác định phiên bản nào được nhìn thấy, không có nghĩa database sao chép toàn bộ database mỗi khi chạy SELECT. MVCC tổ chức metadata và các phiên bản hàng để truy vấn thực hiện quy tắc visibility. Chi tiết lưu trữ, dọn phiên bản cũ và quản lý transaction ID thuộc triển khai của PostgreSQL.

Một snapshot đọc thường có các thuộc tính:

- Các thay đổi của transaction khác chưa commit tại thời điểm snapshot không được hiển thị.
- Các transaction đã commit trước snapshot có thể hiển thị.
- Các transaction commit sau snapshot không được đưa vào cái nhìn của câu lệnh đang chạy.
- Transaction nhìn thấy các thay đổi của chính nó theo quy tắc visibility của hệ quản trị, kể cả thay đổi vừa tạo ra trong transaction đó.

Điểm cuối rất quan trọng: một snapshot ổn định đối với transaction khác không có nghĩa transaction không thể đọc thấy các lệnh ghi của chính nó.

## 3. Thí nghiệm hai kết nối: mỗi SELECT có thể thấy commit mới

Ta dùng PostgreSQL để quan sát trực tiếp. Mở hai kết nối độc lập, đặt tên là A và B.

Chuẩn bị bảng và dữ liệu:

```sql
CREATE TABLE account (
    account_id TEXT PRIMARY KEY,
    balance NUMERIC(14, 2) NOT NULL CHECK (balance >= 0)
);

INSERT INTO account (account_id, balance)
VALUES ('A', 600.00), ('B', 400.00);
```

**Kết nối B — bắt đầu transaction đọc:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT balance
FROM account
WHERE account_id = 'A';
-- Kết quả: 600.00
```

Giữ transaction B mở. **Kết nối A — chuyển tiền và commit:**

```sql
BEGIN;

UPDATE account
SET balance = balance - 100
WHERE account_id = 'A';

UPDATE account
SET balance = balance + 100
WHERE account_id = 'B';

COMMIT;
```

Quay lại **kết nối B** và chạy câu truy vấn tiếp theo:

```sql
SELECT balance
FROM account
WHERE account_id = 'B';
-- Kết quả: 500.00

COMMIT;
```

B đọc A = 600 trước khi T1 commit và B = 500 sau khi T1 commit. Mỗi câu SELECT đều đọc dữ liệu đã commit theo snapshot tương ứng, nhưng kết hợp hai giá trị lại tạo ra một tổng không nhất quán.

Nếu cần tổng số dư ở một snapshot của một câu lệnh, hãy chạy:

```sql
SELECT SUM(balance) AS total_balance
FROM account;
-- 1000.00
```

Một câu SELECT thông thường ở PostgreSQL `READ COMMITTED` dùng cùng snapshot cho các hàng mà nó đọc trong câu lệnh đó. Do đó phép SUM quan sát trạng thái trước hoặc sau transaction chuyển tiền tùy thời điểm bắt đầu snapshot, không lấy nửa cũ nửa mới của transaction chuyển tiền đã commit nguyên tử.

## 4. Dirty read bị ngăn, nhưng non-repeatable read vẫn có thể xảy ra

`READ COMMITTED` loại trừ dirty read theo hành vi PostgreSQL: transaction không đọc thay đổi chưa commit của transaction khác. Tuy nhiên, nó không ngăn mọi lần đọc lại nhìn thấy dữ liệu mới.

### Dirty read: dữ liệu chưa commit không được thấy

```text
Giá trị A ban đầu: 600

T1: BEGIN
T1: UPDATE A = 500         (chưa commit)
T2: BEGIN
T2: SELECT A               -> vẫn thấy 600 trong PostgreSQL
T1: ROLLBACK
T2: COMMIT
```

T2 không thấy 500 vì thay đổi đó chưa commit. Khi T1 rollback, không có transaction khác nào đã quan sát giá trị tạm thời 500 theo một dirty read thông thường.

### Non-repeatable read: cùng hàng trả về giá trị khác nhau

```text
T2: BEGIN READ COMMITTED
T2: SELECT A -> 600

T1: UPDATE A = 500
T1: COMMIT

T2: SELECT A -> 500
T2: COMMIT
```

Hai lần đọc cùng hàng A trong T2 có thể trả về hai giá trị. Lần thứ hai dùng snapshot mới, thấy commit của T1. Đây là **non-repeatable read**.

### Phantom read: tập hàng thỏa điều kiện có thể thay đổi

```text
T2: BEGIN READ COMMITTED
T2: SELECT COUNT(*) FROM booking WHERE status = 'ACTIVE';
    -> 3

T1: INSERT booking mới với status = 'ACTIVE'
T1: COMMIT

T2: SELECT COUNT(*) FROM booking WHERE status = 'ACTIVE';
    -> 4

T2: COMMIT
```

Lần truy vấn thứ hai của T2 có thể nhìn thấy một hàng mới được commit. Đây là phantom read trong lịch thực thi.

| Hiện tượng | `READ COMMITTED` PostgreSQL |
|---|---|
| Dirty read | Bị ngăn |
| Non-repeatable read | Có thể xảy ra |
| Phantom read | Có thể xảy ra giữa các câu truy vấn |
| Read skew qua nhiều câu SELECT | Có thể xảy ra |
| Write skew trên nhiều hàng | Có thể xảy ra |

Các hiện tượng này liên hệ nhưng không đồng nghĩa. Một câu SELECT đơn lẻ có snapshot riêng; lần SELECT kế tiếp có snapshot mới. Sự thay đổi giữa các snapshot là nguồn gốc của các kết quả đọc khác nhau.

## 5. Cùng một câu SELECT có nhất quán không?

Ở PostgreSQL `READ COMMITTED`, các phần của cùng một câu lệnh đọc thông thường cùng sử dụng snapshot của câu lệnh. Điều này quan trọng với phép JOIN, aggregate và subquery: nhiều bảng được đọc trong cùng câu SELECT có thể nhìn một trạng thái commit nhất quán tại snapshot đó.

Ví dụ:

```sql
SELECT
    a.account_id,
    a.balance,
    g.group_name
FROM account a
JOIN account_group g
    ON g.group_id = a.group_id
WHERE a.account_id IN ('A', 'B');
```

Nếu transaction khác cập nhật account và group rồi commit trong khi câu SELECT đang chạy, câu SELECT thông thường vẫn đọc theo snapshot của nó thay vì đổi snapshot giữa từng hàng được quét.

Tương tự, một phép tổng hợp:

```sql
SELECT
    COUNT(*) AS active_count,
    SUM(amount) AS active_amount
FROM payment
WHERE status = 'SETTLED';
```

Các hàng và giá trị được tính trong cùng câu SELECT dựa trên snapshot câu lệnh. Điều đó giúp tránh việc một nửa phép tính đến từ snapshot trước và nửa còn lại từ snapshot sau.

### Nhưng một câu lệnh không sửa được logic truy vấn sai

Ví dụ JOIN hai bảng một-nhiều có thể nhân bản hàng và làm tổng bị đếm lặp. Snapshot nhất quán không tự sửa lỗi fan-out.

```sql
SELECT
    c.customer_id,
    SUM(p.amount) AS payment_total,
    SUM(r.amount) AS refund_total
FROM customer c
LEFT JOIN payment p ON p.customer_id = c.customer_id
LEFT JOIN refund r ON r.customer_id = c.customer_id
GROUP BY c.customer_id;
```

Nếu một khách hàng có nhiều payment và nhiều refund, phép JOIN có thể tạo tích các hàng payment/refund, khiến hai tổng bị nhân lên. Phải thiết kế phép tổng hợp (ví dụ tổng hợp mỗi bảng trước rồi JOIN kết quả) để bảo đảm công thức đúng.

Snapshot trả lời câu hỏi **các phiên bản dữ liệu nào được nhìn thấy**. Nó không bảo đảm câu SQL biểu diễn đúng phép tính nghiệp vụ.

## 6. Khi nào nhiều câu lệnh cần cùng một snapshot?

Nhiều ứng dụng cố ý dùng nhiều truy vấn riêng để đọc dữ liệu:

- Báo cáo tổng tài khoản theo từng nhóm.
- Đọc thông tin khách hàng, rồi đọc số dư và giao dịch liên quan.
- Lập dashboard từ các chỉ số được truy vấn riêng.
- Kiểm tra điều kiện trước khi cập nhật dữ liệu.
- Đối chiếu số lượng đơn với tổng tiền thanh toán và hoàn tiền.

Nếu các câu truy vấn đó phải cùng mô tả một thời điểm, `READ COMMITTED` trong PostgreSQL không đủ để đảm bảo. Có thể cân nhắc các lựa chọn sau.

### Lựa chọn 1: gộp dữ liệu vào một câu lệnh

Nếu tất cả dữ liệu cần thiết có thể truy vấn bằng một SQL statement, một snapshot câu lệnh có thể đáp ứng yêu cầu.

```sql
SELECT
    account_group.group_id,
    SUM(account.balance) AS total_balance
FROM account
JOIN account_group
    ON account.group_id = account_group.group_id
GROUP BY account_group.group_id;
```

Ưu điểm là không cần giữ transaction đọc dài. Nhưng truy vấn có thể khó bảo trì và cần tối ưu; không phải báo cáo nào cũng nên ép thành một câu SQL lớn.

### Lựa chọn 2: dùng REPEATABLE READ

Nếu cần nhiều câu SELECT ở cùng một snapshot trong PostgreSQL, dùng `REPEATABLE READ`:

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT balance
FROM account
WHERE account_id = 'A';

SELECT balance
FROM account
WHERE account_id = 'B';

SELECT SUM(balance)
FROM account;

COMMIT;
```

Snapshot cấp transaction được xác lập ở truy vấn đầu tiên cần snapshot. Các truy vấn đọc sau đó tiếp tục sử dụng snapshot ấy đối với thay đổi từ các transaction khác. Điều này giúp báo cáo nhìn nhất quán giữa nhiều câu lệnh.

### Lựa chọn 3: dùng SERIALIZABLE khi kết quả đọc dẫn tới ghi

Nếu các câu truy vấn không chỉ để báo cáo mà còn dùng để quyết định ghi dữ liệu, snapshot ổn định có thể chưa đủ. Ví dụ hai transaction cùng đọc tổng số bác sĩ trực rồi cập nhật hai hàng khác nhau, làm vi phạm quy tắc luôn còn ít nhất một bác sĩ trực. Đây là write skew.

`SERIALIZABLE` cung cấp bảo đảm mạnh hơn: các transaction commit thành công có hiệu ứng tương đương một thứ tự thực thi tuần tự. Database có thể hủy một transaction khi phát hiện sự xen kẽ không thể tuần tự hóa; ứng dụng cần retry toàn bộ transaction khi thích hợp.

### Bảng lựa chọn

| Nhu cầu | Hướng tiếp cận |
|---|---|
| Một phép đọc/aggregate cần một snapshot | Một câu SELECT |
| Nhiều câu SELECT cần cùng trạng thái dữ liệu | REPEATABLE READ (PostgreSQL) |
| Đọc rồi ghi theo một bất biến nhiều hàng | Serializable, constraint hoặc giao thức khóa phù hợp |
| Cập nhật một hàng dựa trên điều kiện đơn giản | UPDATE nguyên tử với điều kiện trong WHERE |
| Báo cáo phân tán từ nhiều database/service | Watermark, snapshot/version phối hợp hoặc xác định rõ eventual consistency |

## 7. UPDATE ở READ COMMITTED: điều kiện được đánh giá lại ra sao?

`READ COMMITTED` không chỉ tác động tới SELECT. Trong PostgreSQL, khi một lệnh UPDATE gặp một hàng đã bị transaction khác cập nhật và commit, nó có thể phải chờ. Sau khi transaction kia kết thúc, PostgreSQL có thể áp dụng thao tác trên phiên bản hàng mới và đánh giá lại điều kiện WHERE để xác định hàng còn phù hợp hay không.

Ví dụ, hai người cùng mua chiếc vé cuối cùng:

```sql
UPDATE inventory
SET quantity = quantity - 1
WHERE sku = 'TICKET-01'
  AND quantity > 0
RETURNING quantity;
```

Giả sử quantity ban đầu bằng 1. Hai transaction đồng thời chạy cùng câu lệnh:

1. T1 lấy khóa hàng và cập nhật quantity xuống 0.
2. T2 muốn cập nhật cùng hàng nên phải chờ.
3. T1 commit.
4. T2 tiếp tục và PostgreSQL đánh giá lại điều kiện trên phiên bản hàng đã cập nhật.
5. Điều kiện `quantity > 0` không còn đúng, nên T2 không cập nhật hàng.

Câu UPDATE nguyên tử này bảo vệ điều kiện số lượng không âm tốt hơn mẫu đọc về ứng dụng rồi ghi lại giá trị cũ. Ứng dụng cần kiểm tra số hàng được cập nhật: không có hàng trả về có nghĩa là không có vé phù hợp hoặc vé đã hết.

Tuy nhiên, hành vi này cần hiểu đúng:

- Ví dụ trên là semantics cụ thể của PostgreSQL `READ COMMITTED`.
- Nó bảo vệ việc cập nhật cùng hàng và điều kiện WHERE gắn với hàng đó.
- Nó không tự bảo vệ bất biến trải qua nhiều hàng hoặc toàn bộ tập kết quả của một predicate.
- Việc dùng câu UPDATE nguyên tử không thay thế việc phân tích transaction nghiệp vụ tổng thể.

## 8. SELECT FOR UPDATE và phạm vi của khóa

Một cách bảo vệ thao tác đọc rồi cập nhật là khóa hàng trước khi quyết định:

```sql
BEGIN;

SELECT balance
FROM account
WHERE account_id = 'A'
FOR UPDATE;

-- Kiểm tra và thực hiện nghiệp vụ dựa trên hàng đã khóa.

UPDATE account
SET balance = balance - 100
WHERE account_id = 'A';

COMMIT;
```

Trong PostgreSQL, `SELECT ... FOR UPDATE` khóa các hàng được chọn để transaction khác không thể đồng thời cập nhật hoặc khóa xung đột chúng cho đến khi transaction kết thúc. Transaction khác muốn cập nhật cùng hàng có thể phải đợi.

Nhưng phạm vi khóa cần được hiểu chính xác:

- Khóa hàng được chọn bảo vệ hàng đó khỏi thao tác ghi cạnh tranh phù hợp.
- Nó không mặc định khóa mọi hàng chưa tồn tại có thể thỏa một điều kiện trong tương lai.
- Khóa A và B theo hai câu truy vấn riêng không đảm bảo báo cáo nhất quán nếu transaction đã đọc A trước khi lấy được khóa B và trạng thái thay đổi giữa hai lần.
- Khóa nhiều hàng theo thứ tự nhất quán giúp giảm nguy cơ deadlock.
- Câu lệnh locking read có quy tắc riêng khi gặp hàng đang được cập nhật; cần xem tài liệu PostgreSQL và mục tiêu nghiệp vụ cụ thể.

Nếu mục tiêu là đọc báo cáo không cần ghi, snapshot cấp transaction thường là lựa chọn tự nhiên hơn việc khóa hàng. Nếu mục tiêu là bảo vệ một quyết định ghi, khóa cần nằm trong cùng transaction với phép kiểm tra và cập nhật.

## 9. JDBC: mỗi câu SELECT trong cùng transaction

JDBC thường bắt đầu ở chế độ autocommit. Khi `autoCommit=true`, mỗi câu SQL độc lập được thực thi như transaction riêng theo cách sử dụng thông thường. Để một chuỗi truy vấn thuộc cùng transaction, hãy tắt autocommit.

Ví dụ sau cố ý sử dụng `READ COMMITTED` để minh họa phạm vi snapshot của từng câu SELECT trên PostgreSQL:

```java
public AccountSummary readSummary(
        DataSource dataSource,
        String accountA,
        String accountB) throws SQLException {

    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);
        connection.setTransactionIsolation(
                Connection.TRANSACTION_READ_COMMITTED);

        try {
            BigDecimal balanceA = readBalance(connection, accountA);
            BigDecimal balanceB = readBalance(connection, accountB);

            AccountSummary summary = new AccountSummary(
                    balanceA,
                    balanceB,
                    balanceA.add(balanceB)
            );

            connection.commit();
            return summary;
        } catch (SQLException | RuntimeException ex) {
            try {
                connection.rollback();
            } catch (SQLException rollbackFailure) {
                ex.addSuppressed(rollbackFailure);
            }
            throw ex;
        }
    }
}

private BigDecimal readBalance(Connection connection, String accountId)
        throws SQLException {

    String sql = """
        SELECT balance
        FROM account
        WHERE account_id = ?
        """;

    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setString(1, accountId);

        try (ResultSet result = statement.executeQuery()) {
            if (!result.next()) {
                throw new SQLException("Account not found");
            }
            return result.getBigDecimal("balance");
        }
    }
}
```

Trong PostgreSQL, hai lần gọi `readBalance` là hai câu SELECT riêng. Nếu transaction khác commit giữa chúng, phương thức có thể tạo một AccountSummary lấy balanceA và balanceB ở hai snapshot khác nhau.

Nếu muốn hai câu đọc cùng snapshot, đặt isolation thành:

```java
connection.setTransactionIsolation(
        Connection.TRANSACTION_REPEATABLE_READ);
```

Với thao tác chỉ đọc hai giá trị để tính tổng, cũng có thể thực hiện một câu SELECT duy nhất với điều kiện phù hợp để cả hai giá trị được đọc trong cùng snapshot câu lệnh.

### Một lưu ý về JDBC

`Connection.TRANSACTION_READ_COMMITTED` là hằng số JDBC yêu cầu driver/database sử dụng mức tương ứng. Mỗi hệ quản trị có thể có semantics triển khai khác nhau trong giới hạn hỗ trợ. Hãy kiểm tra driver và database thật sự đang dùng; không suy luận hành vi PostgreSQL từ tên hằng số JDBC cho mọi engine.

## 10. Spring @Transactional và READ COMMITTED

Spring cho phép khai báo isolation cho một ranh giới transaction:

```java
@Service
public class AccountSummaryService {

    private final AccountRepository repository;

    public AccountSummaryService(AccountRepository repository) {
        this.repository = repository;
    }

    @Transactional(
        readOnly = true,
        isolation = Isolation.READ_COMMITTED
    )
    public AccountSummary load(String accountA, String accountB) {
        BigDecimal balanceA = repository.findBalance(accountA)
            .orElseThrow();

        BigDecimal balanceB = repository.findBalance(accountB)
            .orElseThrow();

        return new AccountSummary(
            balanceA,
            balanceB,
            balanceA.add(balanceB)
        );
    }
}
```

Trong PostgreSQL, hai truy vấn repository chạy trong cùng transaction nhưng từng câu lệnh đọc thông thường vẫn có snapshot riêng. Vì vậy, `@Transactional` không tự động biến READ COMMITTED thành snapshot cấp transaction.

Các điểm phải nhớ:

- `readOnly = true` mô tả ý định chỉ đọc và có thể giúp framework/driver tối ưu. Nó không tự thay thế isolation level.
- `isolation = Isolation.READ_COMMITTED` thiết lập mức cô lập của transaction vật lý mới do transaction manager quản lý.
- Nếu phương thức tham gia một transaction đã tồn tại, transaction bên ngoài có thể quyết định isolation thực tế.
- Nếu muốn snapshot ổn định qua nhiều câu lệnh trong PostgreSQL, cân nhắc `Isolation.REPEATABLE_READ` ở đúng ranh giới transaction mới.
- Nếu đọc rồi cập nhật một bất biến xuyên nhiều hàng, cân nhắc Serializable hoặc một giao thức khóa/ràng buộc phù hợp.

Một annotation trên phương thức không phải bằng chứng duy nhất rằng database đã thực thi đúng mức cô lập mong muốn; cần hiểu propagation, transaction manager, connection pool và database.

## 11. READ COMMITTED và báo cáo nhiều bảng

Một báo cáo thường kết hợp nhiều nguồn:

```text
Câu 1: số đơn hàng đã thanh toán
Câu 2: tổng tiền đã thu
Câu 3: tổng tiền hoàn lại
Câu 4: số đơn đã hoàn tất
Câu 5: tính doanh thu thuần
```

Nếu từng câu SELECT chạy ở PostgreSQL READ COMMITTED, mỗi câu có thể sử dụng snapshot riêng. Một transaction khác có thể hoàn tất đơn hàng hoặc ghi nhận refund giữa các câu truy vấn. Báo cáo sẽ ghép chỉ số của các thời điểm khác nhau.

Ví dụ:

| Thời điểm | Sự kiện | Đơn đã thanh toán | Refund |
|---|---|---:|---:|
| t1 | Báo cáo đọc số đơn | 10 | Chưa đọc |
| t2 | Transaction khác hoàn tất đơn và ghi refund | 11 | 100 |
| t3 | Báo cáo đọc refund | 11? / giá trị mới | 100 |

Các chỉ số tĩnh của báo cáo có thể không cùng mốc dữ liệu. Điều này không nhất thiết là lỗi nếu dashboard chấp nhận tính mới gần đúng. Nhưng với báo cáo đối soát, tài chính hoặc kiểm toán, phải xác định rõ một thời điểm snapshot.

Các lựa chọn:

1. Một câu SELECT tổng hợp nếu mô hình dữ liệu và truy vấn cho phép.
2. Một transaction REPEATABLE READ để nhiều truy vấn dùng cùng snapshot.
3. Một snapshot báo cáo đã chốt hoặc bảng tổng hợp theo phiên bản/thời điểm nếu báo cáo cần tái lập về sau.
4. Nếu kết quả còn được dùng để quyết định cập nhật, đánh giá thêm các ràng buộc và xung đột ghi; snapshot đọc chưa chắc đủ.

## 12. READ COMMITTED không chỉ có nghĩa là “dữ liệu mới nhất”

Câu “READ COMMITTED luôn trả dữ liệu mới nhất” dễ gây hiểu sai.

Một câu SELECT chỉ thấy các transaction đã commit trước snapshot của câu lệnh. Nếu một transaction khác commit ngay sau khi snapshot được xác lập, câu SELECT đang chạy không nhất thiết đổi kết quả giữa chừng để lấy commit đó. Do vậy, nó là dữ liệu đã commit tại một điểm nhìn cụ thể của câu lệnh, không phải một luồng giá trị thay đổi liên tục theo từng hàng.

Ví dụ:

```text
10:00:00.000  T2 bắt đầu SELECT, snapshot S được xác lập
10:00:00.010  T1 commit balance = 500
10:00:00.020  T2 tiếp tục quét các hàng còn lại
10:00:00.100  T2 hoàn tất SELECT
```

Kết quả của T2 tuân theo snapshot S, không nhất thiết phản ánh commit tại 10:00:00.010. Câu SELECT kế tiếp của T2 có thể nhận snapshot mới và nhìn thấy balance = 500.

Đây là một sự đánh đổi hợp lý: database không buộc một câu lệnh đang quét phải thay đổi góc nhìn giữa quá trình thực thi, nhưng các câu lệnh sau vẫn có thể thấy dữ liệu cập nhật.

## 13. Thời lượng transaction và tác động vận hành

Một transaction READ COMMITTED không cần giữ cùng snapshot qua toàn bộ thời gian transaction, vì mỗi câu lệnh đọc có thể dùng snapshot mới. Điều đó không có nghĩa giữ transaction lâu là miễn phí.

Transaction dài vẫn có thể:

- Giữ các khóa do những câu lệnh ghi/locking read đã lấy.
- Giữ connection từ pool và chiếm một slot kết nối.
- Tăng thời gian chờ của transaction khác.
- Gây khó khăn cho việc quản lý trạng thái session và timeout.
- Làm logic ứng dụng khó hiểu vì nhiều câu lệnh vẫn thuộc cùng một ranh giới transaction dù snapshot đọc thay đổi.

Ở PostgreSQL, transaction đang idle-in-transaction vẫn có thể giữ khóa đã lấy và các tài nguyên liên quan. Nên giữ transaction ngắn, không chờ người dùng hoặc gọi API ngoài trong khi transaction đang mở.

Đối với transaction READ COMMITTED chỉ đọc thông thường, snapshot câu lệnh kết thúc khi câu lệnh hoàn tất; điều đó giúp hạn chế việc giữ snapshot cũ quá lâu so với một transaction giữ snapshot cấp transaction. Nhưng transaction và connection vẫn cần được kết thúc đúng cách.

## 14. Những hiểu lầm thường gặp

**“READ COMMITTED nghĩa là các truy vấn trong một transaction thấy cùng dữ liệu.”** Không đúng với PostgreSQL. Mỗi câu lệnh đọc thông thường có snapshot riêng.

**“READ COMMITTED ngăn mọi kiểu đọc bất thường.”** Nó ngăn dirty read nhưng non-repeatable read, phantom read và read skew giữa các câu lệnh vẫn có thể xảy ra.

**“Nếu không có dirty read thì tổng hợp nhiều hàng chắc chắn đúng.”** Không đúng. Một báo cáo có thể ghép hai giá trị đã commit nhưng đến từ hai trạng thái khác nhau.

**“@Transactional đồng nghĩa snapshot cố định.”** Không đúng. Isolation level mới quyết định semantics; Spring chỉ quản lý ranh giới và yêu cầu mức cô lập.

**“Một câu SELECT lớn luôn cho báo cáo đúng.”** Snapshot có thể nhất quán, nhưng JOIN hoặc công thức tổng hợp vẫn có thể sai vì đếm trùng, thiếu điều kiện hoặc sai mô hình quan hệ.

**“REPEATABLE READ giải quyết mọi bất thường đồng thời.”** Không đúng. PostgreSQL REPEATABLE READ cung cấp snapshot ổn định, nhưng write skew trên nhiều hàng vẫn có thể xảy ra. Khi cần bảo vệ bất biến xuyên nhiều hàng, cần phân tích Serializable/constraint/locking.

**“Khóa một hàng là bảo vệ được mọi điều kiện truy vấn.”** Không đúng. Một predicate có thể bao phủ hàng chưa tồn tại; khóa một số hàng hiện có chưa chắc ngăn hàng mới thỏa điều kiện được chèn.

## 15. Cách chọn mức cô lập theo nhu cầu

Khi quyết định sử dụng READ COMMITTED, hãy trả lời các câu hỏi sau:

### Đây chỉ là một lần đọc hay nhiều lần đọc liên quan?

- Một câu SELECT/aggregate đơn lẻ thường có thể dùng snapshot câu lệnh.
- Nhiều câu truy vấn phải cùng mô tả một thời điểm nên cân nhắc snapshot transaction.

### Kết quả đọc có dùng để ghi dữ liệu không?

- Nếu chỉ hiển thị thông tin có thể chấp nhận thay đổi giữa các truy vấn, READ COMMITTED thường phù hợp.
- Nếu quyết định ghi dựa trên tổng nhiều hàng hoặc một điều kiện phức tạp, phải bảo vệ bất biến bằng constraint, khóa phù hợp hoặc Serializable.

### Độ mới quan trọng tới đâu?

- Dashboard có thể chấp nhận snapshot câu lệnh mới nhất ở từng chỉ số, nhưng cần minh bạch rằng các con số có thể không cùng mốc.
- Báo cáo đối soát có thể cần snapshot nhất quán.
- Báo cáo lịch sử cần lưu thời điểm chốt hoặc phiên bản dữ liệu.

### Chi phí xung đột và retry có chấp nhận được không?

Serializable có thể hủy transaction trong tình huống xung đột, do đó cần code retry toàn transaction. Khóa có thể làm tăng thời gian chờ và deadlock. Snapshot transaction dài có thể làm tăng áp lực tài nguyên. Không có lựa chọn nào miễn phí; cơ chế phải phục vụ bất biến nghiệp vụ cụ thể.

## 16. Bài tập tự suy luận

### Bài 1: Hai câu SELECT trong cùng transaction

T1 đọc A = 300. T2 cập nhật A = 250 và commit. T1 đọc lại A.

- Ở PostgreSQL READ COMMITTED, T1 nhận giá trị nào ở lần đọc thứ hai?
- T1 có dirty read không?
- Hiện tượng này được gọi là gì?
- Nếu đổi sang REPEATABLE READ thì kết quả thay đổi thế nào?

### Bài 2: Tổng số dư bị lệch

Hai tài khoản A = 600 và B = 400. T1 chuyển 100 từ A sang B trong cùng transaction. T2 chạy hai câu SELECT riêng và đọc A trước commit, B sau commit.

- T2 nhìn thấy giá trị nào?
- Tổng kết quả có phải một trạng thái đã commit không?
- Một câu SELECT SUM(balance) ở PostgreSQL READ COMMITTED có thể tránh tình huống này bằng cách nào?

### Bài 3: Báo cáo nhiều nguồn

Dashboard chạy ba truy vấn riêng: số đơn đã thanh toán, tổng refund và số đơn hoàn tất. T1 cập nhật trạng thái và ghi refund trong cùng transaction giữa các truy vấn.

- Vì sao READ COMMITTED có thể tạo dashboard không nhất quán?
- REPEATABLE READ giúp gì?
- Có trường hợp nào phải dùng snapshot/reporting dataset được chốt thay vì chỉ mở transaction không?

### Bài 4: Đọc rồi ghi tổng hạn mức

T1 và T2 cùng đọc tổng hạn mức 9.000. Mỗi transaction tăng một hàng khác nhau thêm 700. Cả hai dùng PostgreSQL REPEATABLE READ.

- Snapshot nhất quán có ngăn write skew không?
- Nêu một cách dùng hàng điều phối với SELECT FOR UPDATE.
- Vì sao Serializable có thể hủy một transaction và ứng dụng cần làm gì sau lỗi 40001?

### Bài 5: Một câu JOIN có snapshot nhất quán

Một câu SELECT JOIN account và account_group chạy trong khi T1 cập nhật cả hai bảng rồi commit.

- Theo snapshot của câu SELECT ở PostgreSQL READ COMMITTED, nó có thể nhìn một nửa trước commit và một nửa sau commit không?
- Snapshot nhất quán có đảm bảo phép JOIN tổng hợp không đếm trùng không?
- Phân biệt hai loại vấn đề này.

## Kết luận

`READ COMMITTED` trong PostgreSQL bảo đảm mỗi câu lệnh đọc thông thường làm việc trên một snapshot nhất quán của dữ liệu đã commit. Nhưng **phạm vi nhất quán dừng ở từng câu lệnh**: một transaction chạy nhiều câu SELECT có thể thấy những commit mới giữa các câu và ghép dữ liệu từ nhiều thời điểm khác nhau.

Mức này phù hợp với nhiều thao tác CRUD và truy vấn cần dữ liệu đã commit mới tại mỗi câu lệnh. Khi cần nhiều truy vấn cùng nhìn một trạng thái, hãy cân nhắc REPEATABLE READ hoặc gộp các phép đọc vào một câu SELECT. Khi kết quả đọc được dùng để bảo vệ bất biến ghi xuyên nhiều hàng, cần thêm constraint, khóa hoặc SERIALIZABLE. Hiểu đúng **snapshot của từng câu lệnh**, **snapshot của cả transaction** và **phạm vi của bất biến nghiệp vụ** giúp lựa chọn mức cô lập phù hợp mà không tạo giả định sai về dữ liệu đồng thời.
