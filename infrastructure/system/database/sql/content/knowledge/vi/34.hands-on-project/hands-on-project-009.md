# Thực hiện chuyển tiền hoặc đặt hàng trong một giao dịch

Chuyển tiền và đặt hàng là hai ví dụ điển hình cho thao tác database gồm nhiều bước nhưng phải được xem như **một công việc thống nhất**. Một giao dịch chuyển tiền có thể cần trừ tiền tài khoản nguồn, cộng tiền tài khoản đích và ghi sổ giao dịch. Một đơn hàng có thể cần tạo đơn, giữ hoặc trừ tồn kho, ghi chi tiết từng sản phẩm và tạo trạng thái thanh toán ban đầu.

Nếu chỉ một bước thành công còn bước khác thất bại, dữ liệu có thể rơi vào trạng thái không thể chấp nhận: tiền đã bị trừ nhưng người nhận chưa được cộng; đơn hàng tồn tại nhưng tồn kho không được giữ; tồn kho đã giảm nhưng không có đơn; hoặc hệ thống gửi thông báo thành công dù transaction đã rollback.

**Database transaction** gom các thay đổi liên quan thành một đơn vị: tất cả được commit cùng nhau hoặc các thay đổi trong transaction được rollback. Tuy nhiên, transaction không tự giải quyết mọi vấn đề. Ta vẫn cần kiểm tra điều kiện nghiệp vụ, khóa dữ liệu phù hợp, xử lý cạnh tranh đồng thời, chống request lặp, và phối hợp với hệ thống bên ngoài như cổng thanh toán.

Bài học thuộc chương **Thực hành tổng hợp** của **Database SQL**. Ta thực hiện hai luồng: chuyển tiền giữa hai tài khoản và tạo đơn hàng có nhiều dòng sản phẩm. Qua đó, bài học kết nối BEGIN/COMMIT/ROLLBACK, constraint, row lock, isolation level, idempotency, retry, outbox và kiểm thử transaction.

> **Nguyên tắc:** đặt mọi thay đổi database cần cùng đúng hoặc cùng thất bại vào một transaction; kiểm tra số hàng bị ảnh hưởng và invariant nghiệp vụ trước khi commit; chỉ thông báo thành công sau khi commit được xác nhận.

## 1. Vì sao cần transaction?

Giả sử tài khoản A có 1.000.000 đồng và chuyển 200.000 đồng cho tài khoản B.

Một thao tác gồm:

1. Kiểm tra hai tài khoản tồn tại và đang hoạt động.
2. Kiểm tra cùng loại tiền và số tiền hợp lệ.
3. Kiểm tra A có đủ số dư.
4. Trừ 200.000 khỏi A.
5. Cộng 200.000 vào B.
6. Ghi nhận giao dịch chuyển tiền.
7. Commit.

Nếu bước 4 thành công nhưng bước 5 lỗi, không được để tài khoản A mất tiền mà B không nhận được. Nếu bước 5 thành công nhưng bước 6 lỗi, số dư đã đổi nhưng không có dấu vết nghiệp vụ tương ứng.

Transaction giúp các thao tác ghi database ở các bước 4–6 có tính nguyên tử:

~~~text
BEGIN
  debit account A
  credit account B
  insert transfer record
COMMIT

Nếu một bước thất bại:
ROLLBACK
~~~

Đặt hàng cũng có vấn đề tương tự:

~~~text
BEGIN
  create order
  reserve/decrease inventory for item 1
  reserve/decrease inventory for item 2
  create order items
  create initial payment state
COMMIT
~~~

Nếu sản phẩm thứ hai hết hàng sau khi sản phẩm thứ nhất đã được giữ, transaction rollback để không tạo trạng thái đơn nửa vời.

## 2. ACID trong thao tác nghiệp vụ

Transaction thường được giải thích bằng bốn thuộc tính ACID.

| Thuộc tính | Ý nghĩa | Ví dụ chuyển tiền/đặt hàng |
|---|---|---|
| Atomicity | Tất cả hoặc không có thay đổi nào của transaction | Trừ tiền, cộng tiền và ghi sổ cùng commit |
| Consistency | Transaction giữ các invariant/constraint hợp lệ | Số dư không âm, số lượng tồn kho không âm, khóa ngoại hợp lệ |
| Isolation | Transaction đồng thời không tạo kết quả trái với mức cô lập được chọn | Hai request không cùng tiêu một số dư hoặc một lượng hàng |
| Durability | Sau commit thành công, thay đổi được lưu bền vững theo bảo đảm DBMS | Giao dịch đã commit không biến mất khi ứng dụng kết thúc bình thường |

ACID không có nghĩa ứng dụng tự động đúng nghiệp vụ. Database chỉ bảo vệ những invariant được biểu diễn trong schema, constraint, transaction và logic. Nếu chương trình tính sai số tiền hoặc bỏ quên một dòng hàng, transaction vẫn có thể commit một kết quả sai nhưng nhất quán về mặt kỹ thuật.

## 3. Ranh giới transaction phải bao trùm thay đổi liên quan

Một transaction cần bao gồm tất cả thay đổi database phải cùng thành công hoặc cùng thất bại.

### 3.1. Chuyển tiền

Trong một transaction:

- Trừ số dư tài khoản nguồn.
- Cộng số dư tài khoản đích.
- Ghi transfer record.
- Ghi ledger entries nếu hệ thống dùng sổ kép.
- Ghi idempotency result hoặc event outbox nếu các bản ghi này thuộc cùng luồng.

### 3.2. Đặt hàng

Trong một transaction:

- Tạo đơn hàng ở trạng thái phù hợp.
- Giữ hoặc trừ tồn kho theo chính sách.
- Tạo các dòng đơn hàng.
- Ghi reservation/stock movement.
- Ghi payment intent hoặc outbox event nội bộ.

### 3.3. Không kéo dài transaction qua thao tác chậm bên ngoài

Không nên mở transaction database rồi gọi cổng thanh toán, gửi email hoặc gọi dịch vụ vận chuyển trong khi vẫn giữ row lock. Các thao tác mạng có thể chậm, timeout hoặc không xác định kết quả, làm transaction giữ lock lâu và tăng deadlock.

Thay vào đó, commit trạng thái nội bộ như PENDING/RESERVED và một outbox event; worker xử lý giao tiếp bên ngoài sau commit. Phần này được trình bày chi tiết ở mục 13.

## 4. Thiết kế schema cho ví dụ chuyển tiền

Ta dùng PostgreSQL làm hệ quản trị minh họa.

### 4.1. Bảng tài khoản

~~~sql
CREATE TABLE bank_accounts_lab (
    account_id BIGINT PRIMARY KEY,
    owner_id BIGINT NOT NULL,
    currency CHAR(3) NOT NULL,
    balance NUMERIC(18, 2) NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    CONSTRAINT ck_bank_accounts_balance
        CHECK (balance >= 0),
    CONSTRAINT ck_bank_accounts_status
        CHECK (status IN ('ACTIVE', 'FROZEN', 'CLOSED'))
);
~~~

Số tiền dùng NUMERIC/DECIMAL, không dùng FLOAT/REAL để lưu tiền vì số dấu phẩy động có thể có sai số biểu diễn. Số chữ số thập phân cần theo đơn vị tiền và quy tắc nghiệp vụ.

### 4.2. Bảng giao dịch chuyển tiền

~~~sql
CREATE TABLE transfers_lab (
    transfer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id UUID NOT NULL UNIQUE,
    from_account_id BIGINT NOT NULL
        REFERENCES bank_accounts_lab(account_id),
    to_account_id BIGINT NOT NULL
        REFERENCES bank_accounts_lab(account_id),
    amount NUMERIC(18, 2) NOT NULL,
    currency CHAR(3) NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_transfer_positive_amount
        CHECK (amount > 0),
    CONSTRAINT ck_transfer_different_accounts
        CHECK (from_account_id <> to_account_id),
    CONSTRAINT ck_transfer_status
        CHECK (status IN ('COMPLETED', 'REVERSED'))
);
~~~

request_id là idempotency key do ứng dụng tạo cho một yêu cầu chuyển tiền logic. UNIQUE ngăn cùng một request ID được ghi thành nhiều transfer.

### 4.3. Sổ cái giao dịch

Trong hệ thống tài chính, chỉ lưu số dư hiện tại thường chưa đủ để kiểm toán. Một ledger ghi các bút toán:

~~~sql
CREATE TABLE account_ledger_lab (
    ledger_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    transfer_id BIGINT NOT NULL
        REFERENCES transfers_lab(transfer_id),
    account_id BIGINT NOT NULL
        REFERENCES bank_accounts_lab(account_id),
    direction TEXT NOT NULL
        CHECK (direction IN ('DEBIT', 'CREDIT')),
    amount NUMERIC(18, 2) NOT NULL
        CHECK (amount > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Một transfer hoàn tất tạo hai bút toán cùng số tiền: một DEBIT ở tài khoản nguồn và một CREDIT ở tài khoản đích. Trong ví dụ đơn giản, mỗi transfer có đúng hai ledger rows. Hệ thống thực tế có thể cần tài khoản phí, tài khoản trung gian, nhiều loại tiền, tỷ giá, trạng thái pending và bút toán đảo.

## 5. Nạp dữ liệu mẫu

~~~sql
INSERT INTO bank_accounts_lab
    (account_id, owner_id, currency, balance, status)
VALUES
    (1001, 501, 'VND', 1000000.00, 'ACTIVE'),
    (1002, 502, 'VND',  300000.00, 'ACTIVE'),
    (1003, 503, 'USD',     500.00, 'ACTIVE'),
    (1004, 504, 'VND',       0.00, 'FROZEN');
~~~

Trạng thái ban đầu:

| Tài khoản | Tiền tệ | Số dư | Trạng thái |
|---:|---|---:|---|
| 1001 | VND | 1.000.000,00 | ACTIVE |
| 1002 | VND | 300.000,00 | ACTIVE |
| 1003 | USD | 500,00 | ACTIVE |
| 1004 | VND | 0,00 | FROZEN |

Ví dụ chuyển 200.000 VND từ 1001 sang 1002 sẽ tạo số dư mới lần lượt 800.000 và 500.000.

## 6. Xác định invariant trước khi viết SQL

Invariant là điều kiện phải đúng trước và sau mỗi transaction hợp lệ.

Với chuyển tiền:

1. Hai tài khoản phải tồn tại.
2. Tài khoản nguồn và đích phải khác nhau.
3. Cả hai tài khoản phải được phép giao dịch.
4. Currency phải tương thích theo quy tắc chuyển tiền.
5. Amount phải lớn hơn 0.
6. Tài khoản nguồn phải đủ số dư.
7. Số dư sau chuyển không được âm.
8. Tổng thay đổi số dư giữa hai tài khoản cùng loại tiền phải bằng 0 trong ví dụ không có phí.
9. Transfer record và ledger entries phải khớp với thay đổi số dư.
10. Một request logic chỉ được áp dụng một lần.

Với đặt hàng:

1. Khách hàng và địa chỉ giao hàng phải hợp lệ.
2. Giỏ hàng có ít nhất một dòng.
3. Mỗi sản phẩm phải bán được và có số lượng dương.
4. Tổng tiền được tính từ giá đáng tin cậy phía server.
5. Tồn kho không được âm.
6. Mỗi dòng đơn phải tham chiếu đúng đơn và sản phẩm.
7. Tổng tiền đơn phải bằng tổng các dòng và phí/thuế/giảm giá theo quy tắc.
8. Trạng thái đơn và thanh toán phải chuyển theo state machine.
9. Request lặp không tạo đơn hoặc giữ hàng hai lần.

Constraint database nên bảo vệ các invariant đơn giản có thể diễn đạt bằng CHECK, NOT NULL, UNIQUE và FOREIGN KEY. Logic liên quan nhiều hàng cần transaction, khóa và kiểm tra số hàng.

## 7. Thực hiện chuyển tiền trong PostgreSQL transaction

Ví dụ sau minh họa thứ tự thao tác. Ứng dụng cần kiểm tra kết quả từng câu lệnh và rollback nếu bất kỳ bước bắt buộc nào không đạt.

### 7.1. Bắt đầu transaction và khóa hai tài khoản

~~~sql
BEGIN;

SELECT account_id, currency, balance, status
FROM bank_accounts_lab
WHERE account_id IN (1001, 1002)
ORDER BY account_id
FOR UPDATE;
~~~

FOR UPDATE khóa các hàng được chọn cho đến khi transaction kết thúc. Hai transaction cùng chuyển tiền qua một tài khoản sẽ phải phối hợp qua lock thay vì cùng đọc rồi ghi đè số dư.

ORDER BY account_id tạo thứ tự lấy lock nhất quán. Nếu một luồng chuyển 1001 → 1002 và luồng khác chuyển 1002 → 1001, cả hai vẫn cố khóa account 1001 trước rồi mới đến 1002, giảm nguy cơ deadlock do thứ tự khóa ngược nhau.

Ứng dụng phải xác minh truy vấn trả đúng hai tài khoản, cả hai ACTIVE, cùng currency và account ID khác nhau. Nếu thiếu một hàng hoặc trạng thái không hợp lệ, rollback.

### 7.2. Trừ tiền có điều kiện

~~~sql
UPDATE bank_accounts_lab
SET balance = balance - 200000.00
WHERE account_id = 1001
  AND status = 'ACTIVE'
  AND currency = 'VND'
  AND balance >= 200000.00;
~~~

Kiểm tra số hàng bị ảnh hưởng:

- 1 hàng: bước debit thành công.
- 0 hàng: tài khoản không tồn tại, không hoạt động, sai currency hoặc không đủ số dư.
- Hơn 1 hàng: schema/điều kiện có vấn đề vì account_id là primary key.

Không tiếp tục credit nếu debit không cập nhật đúng một hàng.

### 7.3. Cộng tiền tài khoản đích

~~~sql
UPDATE bank_accounts_lab
SET balance = balance + 200000.00
WHERE account_id = 1002
  AND status = 'ACTIVE'
  AND currency = 'VND';
~~~

Phải xác nhận đúng một hàng được cập nhật. Nếu tài khoản đích không hợp lệ, rollback cả debit.

### 7.4. Ghi transfer và hai ledger entries

~~~sql
INSERT INTO transfers_lab (
    request_id,
    from_account_id,
    to_account_id,
    amount,
    currency,
    status
)
VALUES (
    '11111111-1111-4111-8111-111111111111',
    1001,
    1002,
    200000.00,
    'VND',
    'COMPLETED'
)
RETURNING transfer_id;
~~~

Lấy transfer_id được trả về, sau đó:

~~~sql
INSERT INTO account_ledger_lab
    (transfer_id, account_id, direction, amount)
VALUES
    (:transfer_id, 1001, 'DEBIT', 200000.00),
    (:transfer_id, 1002, 'CREDIT', 200000.00);
~~~

Placeholder :transfer_id trong ví dụ là ký hiệu thay thế cho giá trị mà ứng dụng vừa nhận từ RETURNING; cú pháp bind thực tế phụ thuộc driver.

### 7.5. Commit

~~~sql
COMMIT;
~~~

Chỉ sau khi COMMIT được xác nhận thành công, ứng dụng mới trả kết quả chuyển tiền hoàn tất. Nếu bất kỳ bước bắt buộc nào lỗi, chạy ROLLBACK.

### 7.6. Số dư sau chuyển

~~~sql
SELECT account_id, balance
FROM bank_accounts_lab
WHERE account_id IN (1001, 1002)
ORDER BY account_id;
~~~

Kết quả:

| account_id | balance |
|---:|---:|
| 1001 | 800000.00 |
| 1002 | 500000.00 |

Ledger phải có đúng một DEBIT 200.000 ở account 1001 và một CREDIT 200.000 ở account 1002 cho transfer đó.

## 8. Chuyển tiền bằng code ứng dụng: kiểm tra row count

SQL transaction phải được điều khiển bởi code ứng dụng hoặc stored procedure. Ví dụ Java JDBC dưới đây cho thấy cách kiểm tra từng bước.

~~~java
public TransferResult transfer(
        long fromId,
        long toId,
        BigDecimal amount,
        String currency,
        UUID requestId) throws SQLException {

    if (fromId == toId) {
        throw new IllegalArgumentException("Accounts must differ");
    }
    if (amount == null || amount.signum() <= 0) {
        throw new IllegalArgumentException("Amount must be positive");
    }

    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);

        try {
            // Khóa theo thứ tự account_id để các luồng lấy lock nhất quán.
            try (PreparedStatement ps = connection.prepareStatement("""
                    SELECT account_id, currency, balance, status
                    FROM bank_accounts_lab
                    WHERE account_id IN (?, ?)
                    ORDER BY account_id
                    FOR UPDATE
                    """)) {
                ps.setLong(1, fromId);
                ps.setLong(2, toId);

                try (ResultSet rs = ps.executeQuery()) {
                    int found = 0;
                    while (rs.next()) {
                        found++;
                        if (!"ACTIVE".equals(rs.getString("status"))) {
                            throw new IllegalStateException("Account inactive");
                        }
                        if (!currency.equals(rs.getString("currency"))) {
                            throw new IllegalArgumentException("Currency mismatch");
                        }
                    }
                    if (found != 2) {
                        throw new IllegalArgumentException("Account not found");
                    }
                }
            }

            int debited;
            try (PreparedStatement ps = connection.prepareStatement("""
                    UPDATE bank_accounts_lab
                    SET balance = balance - ?
                    WHERE account_id = ?
                      AND status = 'ACTIVE'
                      AND currency = ?
                      AND balance >= ?
                    """)) {
                ps.setBigDecimal(1, amount);
                ps.setLong(2, fromId);
                ps.setString(3, currency);
                ps.setBigDecimal(4, amount);
                debited = ps.executeUpdate();
            }
            if (debited != 1) {
                throw new IllegalStateException("Insufficient funds or invalid source");
            }

            int credited;
            try (PreparedStatement ps = connection.prepareStatement("""
                    UPDATE bank_accounts_lab
                    SET balance = balance + ?
                    WHERE account_id = ?
                      AND status = 'ACTIVE'
                      AND currency = ?
                    """)) {
                ps.setBigDecimal(1, amount);
                ps.setLong(2, toId);
                ps.setString(3, currency);
                credited = ps.executeUpdate();
            }
            if (credited != 1) {
                throw new IllegalStateException("Invalid destination");
            }

            long transferId;
            try (PreparedStatement ps = connection.prepareStatement("""
                    INSERT INTO transfers_lab
                        (request_id, from_account_id, to_account_id,
                         amount, currency, status)
                    VALUES (?, ?, ?, ?, ?, 'COMPLETED')
                    RETURNING transfer_id
                    """)) {
                ps.setObject(1, requestId);
                ps.setLong(2, fromId);
                ps.setLong(3, toId);
                ps.setBigDecimal(4, amount);
                ps.setString(5, currency);

                try (ResultSet rs = ps.executeQuery()) {
                    if (!rs.next()) {
                        throw new SQLException("Transfer id was not returned");
                    }
                    transferId = rs.getLong(1);
                }
            }

            try (PreparedStatement ps = connection.prepareStatement("""
                    INSERT INTO account_ledger_lab
                        (transfer_id, account_id, direction, amount)
                    VALUES (?, ?, ?, ?), (?, ?, ?, ?)
                    """)) {
                ps.setLong(1, transferId);
                ps.setLong(2, fromId);
                ps.setString(3, "DEBIT");
                ps.setBigDecimal(4, amount);
                ps.setLong(5, transferId);
                ps.setLong(6, toId);
                ps.setString(7, "CREDIT");
                ps.setBigDecimal(8, amount);
                if (ps.executeUpdate() != 2) {
                    throw new SQLException("Expected two ledger entries");
                }
            }

            connection.commit();
            return new TransferResult(transferId, "COMPLETED");
        } catch (SQLException | RuntimeException ex) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                ex.addSuppressed(rollbackError);
            }
            throw ex;
        }
    }
}
~~~

Đây là ví dụ minh họa cần điều chỉnh kiểu exception và transaction management theo framework. Trong ứng dụng dùng connection pool, bảo đảm pool reset trạng thái connection khi close; nếu rollback thất bại hoặc trạng thái connection không rõ, không tái sử dụng connection đó. Trong ứng dụng dùng Spring/Jakarta transaction manager, thường để framework quản lý commit/rollback thay vì tự điều khiển Connection ở mọi repository method.

Điểm cần giữ:

- Validate dữ liệu trước khi mở transaction khi có thể.
- Lock hai tài khoản theo thứ tự xác định.
- Kiểm tra đúng số hàng ở mỗi UPDATE/INSERT.
- Dùng BigDecimal cho tiền.
- Không trả thành công trước commit.
- Nếu bất kỳ bước nào thất bại, rollback cả transaction.

## 9. Chống request chuyển tiền lặp bằng idempotency

Một tình huống thực tế: client gửi yêu cầu chuyển tiền, server commit thành công nhưng response bị mất trên mạng. Client không biết giao dịch đã thành công nên gửi lại. Nếu không có idempotency, tiền có thể bị trừ hai lần.

### 9.1. Unique request_id

Bảng transfers_lab đã có:

~~~sql
request_id UUID NOT NULL UNIQUE
~~~

Ứng dụng tạo một UUID cho một thao tác logic và dùng lại UUID đó khi retry cùng request.

### 9.2. Luồng xử lý

1. Nhận request ID.
2. Tìm transfer đã có theo request ID.
3. Nếu đã có, trả lại kết quả đã lưu và không thực hiện debit/credit lần nữa.
4. Nếu chưa có, thực hiện transaction.
5. Insert transfer với request ID trong cùng transaction với debit, credit và ledger.
6. Nếu hai request cùng request ID chạy đồng thời, UNIQUE constraint chỉ cho phép một transaction tạo bản ghi.
7. Transaction thua conflict phải rollback; sau đó đọc kết quả đã commit theo request ID và trả lại cho caller.

### 9.3. Không chỉ SELECT trước rồi tin là chưa có

Hai transaction có thể đồng thời:

~~~text
T1: SELECT request_id -> chưa có
T2: SELECT request_id -> chưa có
T1: thực hiện debit/credit
T2: thực hiện debit/credit
~~~

Một lần SELECT trước không ngăn race. UNIQUE constraint và transaction mới là bảo vệ cuối cùng. Logic ứng dụng phải xử lý unique conflict và đọc kết quả đã được commit.

### 9.4. Idempotency key phải gắn với payload

Nếu client dùng lại cùng request ID nhưng gửi amount hoặc tài khoản khác, không được trả lại kết quả cũ mà không phát hiện sự khác biệt.

Có thể lưu hash hoặc các trường request quan trọng:

- from_account_id
- to_account_id
- amount
- currency
- client/request scope

Khi request ID đã tồn tại, so sánh payload. Nếu khác, trả conflict vì cùng idempotency key đang được dùng cho một yêu cầu khác.

### 9.5. Lưu cả kết quả nghiệp vụ

Để trả lại cùng kết quả sau retry, bảng request/transfer có thể lưu transfer_id, trạng thái và response fields cần thiết. Đảm bảo bản ghi idempotency và thay đổi số dư commit trong cùng transaction.

## 10. Xử lý cạnh tranh khi hai giao dịch cùng tiêu một số dư

Giả sử account 1001 có 300.000 đồng. Hai request đồng thời, mỗi request chuyển 200.000.

Nếu cả hai cùng đọc số dư trước khi khóa:

~~~text
T1 đọc 300.000
T2 đọc 300.000
T1 thấy đủ tiền
T2 thấy đủ tiền
T1 trừ 200.000
T2 trừ 200.000
~~~

Nếu code ghi số dư mới dựa trên giá trị cũ, có thể xảy ra lost update hoặc số dư âm tùy cách viết.

### 10.1. Atomic conditional UPDATE

Một cách bảo vệ quan trọng:

~~~sql
UPDATE bank_accounts_lab
SET balance = balance - 200000.00
WHERE account_id = 1001
  AND balance >= 200000.00;
~~~

Database thực hiện điều kiện và cập nhật như một statement. Khi hai request cạnh tranh, statement thứ hai phải xét trên trạng thái đã được khóa/đồng bộ; nó không thể trừ nếu số dư hiện tại không còn đủ. Kiểm tra row count bằng 1 là bắt buộc.

### 10.2. SELECT FOR UPDATE

~~~sql
BEGIN;

SELECT account_id, balance
FROM bank_accounts_lab
WHERE account_id = 1001
FOR UPDATE;

-- Kiểm tra số dư sau khi đã lấy lock.
-- Debit, credit, ledger...

COMMIT;
~~~

SELECT FOR UPDATE giữ row lock đến khi transaction kết thúc. Request khác muốn cập nhật cùng hàng phải đợi.

### 10.3. Kết hợp cả lock và conditional UPDATE

Đối với luồng chuyển tiền quan trọng, có thể dùng cả:

- SELECT FOR UPDATE để đọc trạng thái nhất quán và kiểm tra nhiều điều kiện.
- UPDATE ... WHERE balance >= amount để invariant số dư không âm được bảo vệ ngay trong câu lệnh.
- CHECK(balance >= 0) để database từ chối trạng thái âm nếu có đường ghi khác bỏ qua logic.

Nhiều lớp bảo vệ này giúp giảm phụ thuộc vào một giả định duy nhất.

### 10.4. Thử nghiệm hai giao dịch đồng thời

Trong hai session PostgreSQL:

Session A:

~~~sql
BEGIN;
SELECT balance
FROM bank_accounts_lab
WHERE account_id = 1001
FOR UPDATE;
-- Tạm dừng để quan sát lock.
~~~

Session B:

~~~sql
BEGIN;
UPDATE bank_accounts_lab
SET balance = balance - 200000
WHERE account_id = 1001
  AND balance >= 200000;
~~~

Session B sẽ chờ lock từ A. Khi A commit hoặc rollback, B tiếp tục và điều kiện UPDATE được đánh giá theo trạng thái phù hợp. Sau đó kiểm tra row count của B.

Chỉ chạy thí nghiệm trên database lab; kết thúc cả hai session bằng COMMIT/ROLLBACK.

## 11. Isolation level và lựa chọn khóa

Isolation level xác định cách transaction nhìn thấy thay đổi của transaction khác và loại anomaly nào có thể xảy ra.

### 11.1. Read Committed

PostgreSQL mặc định thường dùng READ COMMITTED. Mỗi statement có snapshot riêng. UPDATE cạnh tranh sẽ chờ row lock và đánh giá điều kiện trên phiên bản hàng mới theo quy tắc PostgreSQL.

READ COMMITTED phù hợp với nhiều thao tác có conditional UPDATE hoặc SELECT FOR UPDATE, nhưng không tự bảo vệ mọi quy tắc nhiều hàng phức tạp.

### 11.2. Repeatable Read

Repeatable Read giữ snapshot ổn định hơn trong transaction. Trong PostgreSQL, xung đột ghi có thể dẫn đến serialization-style error khi transaction cố cập nhật hàng đã thay đổi sau snapshot.

Ứng dụng phải chuẩn bị rollback và retry toàn transaction trong các trường hợp phù hợp.

### 11.3. Serializable

SERIALIZABLE cố gắng đảm bảo kết quả tương đương một thứ tự chạy tuần tự. DBMS có thể từ chối một transaction để tránh anomaly, vì vậy ứng dụng cần xử lý serialization failure và retry.

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

-- Đọc, kiểm tra invariant và ghi dữ liệu.

COMMIT;
~~~

SERIALIZABLE không phải lựa chọn mặc định cho mọi endpoint. Nó có thể tăng xung đột và retry. Chọn dựa trên invariant cần bảo vệ, workload và khả năng retry của ứng dụng.

### 11.4. Pessimistic và optimistic concurrency

**Pessimistic locking**: khóa hàng trước khi thực hiện thay đổi, ví dụ SELECT FOR UPDATE. Phù hợp khi xung đột có khả năng cao hoặc cần giữ trạng thái trong lúc xử lý ngắn.

**Optimistic concurrency**: đọc version, sau đó UPDATE chỉ khi version chưa đổi:

~~~sql
UPDATE bank_accounts_lab
SET balance = balance - 100,
    version = version + 1
WHERE account_id = 1001
  AND version = 7
  AND balance >= 100;
~~~

Nếu row count bằng 0, dữ liệu đã thay đổi hoặc điều kiện không còn đúng. Cách này cần cột version và logic xử lý conflict. Ví dụ bảng bank_accounts_lab ở trên chưa có cột version; cần thêm cột nếu muốn chạy câu lệnh này.

## 12. Deadlock và thứ tự lấy lock

Deadlock có thể xảy ra khi:

~~~text
T1 khóa account A, chờ account B
T2 khóa account B, chờ account A
~~~

Không transaction nào tiếp tục được. DBMS phát hiện chu trình và hủy một transaction.

### 12.1. Quy tắc thứ tự ổn định

Nếu cần khóa nhiều tài khoản:

~~~sql
SELECT account_id
FROM bank_accounts_lab
WHERE account_id IN (:id1, :id2)
ORDER BY account_id
FOR UPDATE;
~~~

Mọi luồng chuyển tiền phải khóa theo cùng thứ tự account_id tăng dần. Với nhiều loại đối tượng, định nghĩa thứ tự toàn hệ thống, ví dụ account trước transfer metadata, hoặc inventory theo product_id tăng dần.

### 12.2. Giữ transaction ngắn

Không:

- Gọi API bên ngoài khi đang giữ lock.
- Chờ người dùng xác nhận.
- Thực hiện xử lý file hoặc tính toán dài không cần thiết.
- Giữ transaction mở qua nhiều request HTTP.

Hãy chuẩn bị input và tính toán không phụ thuộc dữ liệu khóa trước khi BEGIN; sau đó thực hiện phần đọc/ghi ngắn nhất có thể.

### 12.3. Retry deadlock

Khi deadlock:

1. DBMS hủy transaction nạn nhân.
2. Ứng dụng rollback/đóng transaction đó.
3. Đợi backoff có jitter.
4. Bắt đầu transaction mới.
5. Chạy lại toàn bộ logic đọc, kiểm tra và ghi.
6. Giới hạn số lần retry.

Không retry vô hạn và không chạy lại riêng statement cuối.

## 13. Đặt hàng và giữ tồn kho trong một transaction

Chuyển tiền bảo vệ hai số dư; đặt hàng cần phối hợp đơn hàng, các dòng hàng và tồn kho.

### 13.1. Thiết kế bảng sản phẩm và tồn kho

~~~sql
CREATE TABLE products_lab (
    product_id BIGINT PRIMARY KEY,
    product_name TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE inventory_lab (
    product_id BIGINT PRIMARY KEY
        REFERENCES products_lab(product_id),
    available_quantity INTEGER NOT NULL
        CHECK (available_quantity >= 0),
    reserved_quantity INTEGER NOT NULL DEFAULT 0
        CHECK (reserved_quantity >= 0)
);

CREATE TABLE orders_lab (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id UUID NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL,
    currency CHAR(3) NOT NULL,
    total_amount NUMERIC(18, 2) NOT NULL
        CHECK (total_amount >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (status IN (
        'PENDING_PAYMENT',
        'CONFIRMED',
        'CANCELLED',
        'PAYMENT_FAILED'
    ))
);

CREATE TABLE order_items_lab (
    order_item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders_lab(order_id),
    product_id BIGINT NOT NULL REFERENCES products_lab(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(18, 2) NOT NULL CHECK (unit_price >= 0),
    line_total NUMERIC(18, 2) NOT NULL CHECK (line_total >= 0)
);
~~~

Ở đây inventory có hai cột:

- available_quantity: số lượng còn có thể bán/đặt giữ.
- reserved_quantity: số lượng đã giữ cho đơn chưa hoàn tất.

Một hệ thống khác có thể dùng on_hand, allocated, available hoặc stock movements. Điều quan trọng là định nghĩa rõ ý nghĩa và invariant.

### 13.2. Nạp sản phẩm mẫu

~~~sql
INSERT INTO products_lab(product_id, product_name)
VALUES
    (9001, 'Keyboard'),
    (9002, 'Mouse'),
    (9003, 'Monitor');

INSERT INTO inventory_lab(product_id, available_quantity, reserved_quantity)
VALUES
    (9001, 10, 0),
    (9002, 20, 0),
    (9003, 2, 0);
~~~

### 13.3. Dữ liệu request mẫu

Khách hàng 700 muốn đặt:

| Sản phẩm | Số lượng | Đơn giá phía server |
|---|---:|---:|
| Keyboard | 1 | 800.000 |
| Mouse | 2 | 250.000 |

Tổng trước phí/thuế là 1.300.000. Không tin giá do client gửi; server phải lấy giá hợp lệ từ catalog hoặc snapshot giá đã xác nhận.

### 13.4. Transaction tạo đơn và giữ kho

Luồng:

1. Validate giỏ hàng không rỗng, quantity dương, không có product trùng chưa gộp.
2. Tính tổng từ giá server-side.
3. Bắt đầu transaction.
4. Khóa các hàng inventory theo product_id tăng dần.
5. Kiểm tra đủ hàng và sản phẩm còn active.
6. Tạo order ở trạng thái PENDING_PAYMENT.
7. Với mỗi SKU, chuyển số lượng từ available sang reserved bằng UPDATE có điều kiện.
8. Kiểm tra mỗi UPDATE tác động đúng một hàng.
9. Tạo order_items với unit_price snapshot và line_total.
10. Ghi outbox event để yêu cầu thanh toán sau commit.
11. Commit.

Ví dụ phần SQL cốt lõi:

~~~sql
BEGIN;

-- Khóa inventory theo thứ tự product_id để giảm deadlock.
SELECT product_id, available_quantity
FROM inventory_lab
WHERE product_id IN (9001, 9002)
ORDER BY product_id
FOR UPDATE;

-- Ứng dụng xác minh đủ hai sản phẩm và số lượng:
-- product 9001 cần 1, product 9002 cần 2.

INSERT INTO orders_lab (
    request_id, customer_id, status, currency, total_amount
)
VALUES (
    '22222222-2222-4222-8222-222222222222',
    700,
    'PENDING_PAYMENT',
    'VND',
    1300000.00
)
RETURNING order_id;

-- Giả sử ứng dụng nhận order_id = 501.
UPDATE inventory_lab
SET available_quantity = available_quantity - 1,
    reserved_quantity = reserved_quantity + 1
WHERE product_id = 9001
  AND available_quantity >= 1;

UPDATE inventory_lab
SET available_quantity = available_quantity - 2,
    reserved_quantity = reserved_quantity + 2
WHERE product_id = 9002
  AND available_quantity >= 2;

INSERT INTO order_items_lab
    (order_id, product_id, quantity, unit_price, line_total)
VALUES
    (501, 9001, 1, 800000.00, 800000.00),
    (501, 9002, 2, 250000.00, 500000.00);

COMMIT;
~~~

Đây là ví dụ trình bày thứ tự SQL; trong ứng dụng thực tế phải kiểm tra row count của từng UPDATE. Nếu sản phẩm thứ hai không đủ hàng, rollback để đơn, dòng hàng và lần giữ sản phẩm thứ nhất đều không còn.

### 13.5. Vì sao khóa inventory theo thứ tự?

Hai đơn có thể chứa cùng hai sản phẩm nhưng thứ tự dòng giỏ hàng khác nhau. Nếu một transaction khóa product 9001 trước 9002, còn transaction kia khóa 9002 trước 9001, chúng có thể deadlock. Chuẩn hóa thứ tự product_id giúp các luồng lấy lock nhất quán.

### 13.6. Gộp SKU trùng trước khi cập nhật

Nếu giỏ hàng có:

| Dòng | Product | Quantity |
|---|---:|---:|
| 1 | 9002 | 1 |
| 2 | 9002 | 2 |

Hãy gộp thành product 9002 quantity 3 trước khi khóa/cập nhật kho, hoặc có logic tổng hợp tương đương. Nếu xử lý từng dòng không kiểm soát, dễ kiểm tra tồn kho không nhất quán hoặc tạo nhiều lần cập nhật khó hiểu.

### 13.7. Tồn kho và giá phải được xác nhận phía server

Không tin:

- product_id có trong giỏ là sản phẩm đang bán.
- unit_price từ client là giá đúng.
- total_amount từ client là tổng đúng.
- available_quantity mà client đọc trước đó vẫn còn đúng.

Database phải kiểm tra tồn kho tại thời điểm ghi. Giá cần được lấy từ nguồn đáng tin cậy và snapshot vào order_items để lịch sử đơn không đổi khi giá catalog thay đổi.

## 14. Thanh toán bên ngoài: transaction database không bao trùm cổng thanh toán

Một transaction PostgreSQL không thể tự rollback một khoản tiền đã được cổng thanh toán bên ngoài thu thành công. Đây là ranh giới quan trọng.

### 14.1. Không gọi payment gateway bên trong transaction đang giữ lock

Luồng không tốt:

~~~text
BEGIN
  lock inventory
  create order
  call payment gateway over network
  wait 20 seconds
  gateway timeout
ROLLBACK
~~~

Gateway có thể đã thu tiền nhưng response bị timeout. Database rollback không hoàn lại tiền bên gateway. Transaction còn giữ lock lâu trong khi chờ mạng.

### 14.2. Mô hình trạng thái

Một luồng phổ biến:

~~~text
NEW REQUEST
    |
    v
DB TRANSACTION
  create order PENDING_PAYMENT
  reserve inventory
  create payment intent record
  insert outbox event
COMMIT
    |
    v
OUTBOX WORKER
  call payment provider with idempotency key
    |
    +---- success ----> mark payment PAID, order CONFIRMED
    |
    +---- failure ----> mark payment FAILED, release inventory
    |
    +---- unknown ----> reconcile/query provider before retry
~~~

Mỗi bước cập nhật database riêng cũng phải nằm trong transaction. Ví dụ khi thanh toán thành công, update payment state, order state và outbox/notification record nội bộ trong cùng transaction.

### 14.3. Transactional outbox

Outbox ghi sự kiện cần gửi vào cùng transaction tạo đơn:

~~~sql
CREATE TABLE outbox_events_lab (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    aggregate_type TEXT NOT NULL,
    aggregate_id BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ
);
~~~

Trong transaction tạo order:

~~~sql
INSERT INTO outbox_events_lab (
    aggregate_type, aggregate_id, event_type, payload
)
VALUES (
    'ORDER',
    501,
    'PAYMENT_REQUESTED',
    '{"orderId":501,"amount":"1300000.00","currency":"VND"}'::jsonb
);
~~~

Nếu transaction rollback, outbox event cũng rollback. Nếu commit, worker có thể đọc và gửi event. Worker đánh dấu published sau khi gửi thành công theo cơ chế an toàn.

Outbox thường cho delivery ít nhất một lần, không đảm bảo worker chỉ gửi đúng một lần. Consumer cần idempotency/deduplication theo event_id hoặc business key.

### 14.4. Saga và bù trừ

Nếu quy trình trải qua nhiều hệ thống độc lập, không có một transaction ACID duy nhất bao trùm tất cả. Có thể dùng Saga:

- Bước giữ tồn kho.
- Bước tạo payment intent/thu tiền.
- Bước xác nhận đơn.
- Nếu bước sau thất bại, chạy hành động bù như giải phóng tồn kho hoặc hoàn tiền theo quy trình.

Hành động bù không phải rollback vật lý của transaction cũ. Nó là một thao tác nghiệp vụ mới, có thể thất bại và cần retry/đối soát riêng.

## 15. Đặt hàng idempotent

Client có thể gửi lại request tạo đơn khi timeout. Nếu mỗi lần retry tạo order mới, khách hàng có thể bị giữ tồn kho hoặc thanh toán nhiều lần.

### 15.1. Unique request_id

Bảng orders_lab có:

~~~sql
request_id UUID NOT NULL UNIQUE
~~~

Một request logic phải giữ nguyên request_id qua các lần retry.

### 15.2. Payload hash

Lưu hash hoặc snapshot các trường quan trọng của request. Nếu cùng request_id nhưng customer, SKU, quantity hoặc currency khác, từ chối thay vì trả nhầm order cũ.

### 15.3. Xử lý đồng thời

Hai worker cùng xử lý request_id chưa tồn tại có thể cùng bắt đầu. UNIQUE constraint bảo vệ điểm ghi cuối. Transaction thua cần rollback toàn bộ việc giữ kho rồi đọc order đã được tạo bởi transaction thắng.

### 15.4. Idempotency ở payment provider

Nếu worker gọi provider và timeout, trước khi gọi lại phải dùng cùng idempotency key hoặc tra cứu trạng thái payment intent. Không tạo một payment intent mới mỗi lần retry mà không kiểm tra kết quả lần trước.

## 16. ROLLBACK và lỗi giữa chừng

Một transaction phải xử lý đúng nếu lỗi xảy ra ở bất kỳ bước nào.

### 16.1. Chuyển tiền: lỗi sau debit

Giả sử:

1. Debit tài khoản nguồn thành công.
2. Credit tài khoản đích lỗi vì tài khoản bị đóng hoặc có lỗi dữ liệu.
3. Transaction rollback.

Kết quả mong muốn:

- Số dư nguồn trở về trước transaction.
- Số dư đích không thay đổi.
- Không có transfer record.
- Không có ledger entries.

Không tự tạo một giao dịch “cộng bù” bên ngoài transaction để sửa. Nếu transaction chưa commit, rollback là cách đúng để hủy toàn bộ thay đổi chưa commit.

### 16.2. Đặt hàng: sản phẩm sau hết hàng

Giả sử:

- Product A còn 5, khách đặt 2.
- Product B còn 1, khách đặt 3.

Nếu A đã được reserve trước khi phát hiện B thiếu hàng, rollback phải trả A về số lượng ban đầu và không để order ở trạng thái nửa chừng.

### 16.3. COMMIT có thể thất bại hoặc mất phản hồi

Nếu server đã commit nhưng kết nối bị mất trước khi client nhận phản hồi, ứng dụng không biết chắc kết quả. Đây là lúc idempotency key cần thiết:

1. Giữ request ID.
2. Kết nối lại.
3. Tra cứu transfer/order theo request ID.
4. Nếu đã tồn tại ở trạng thái hoàn tất/đang xử lý, trả kết quả đó.
5. Chỉ chạy lại nếu xác định request chưa được commit và quy trình cho phép.

Không coi mọi lỗi khi gọi commit là bằng chứng transaction đã rollback.

## 17. SAVEPOINT khi chỉ một phần công việc có thể bỏ qua

Savepoint đánh dấu một vị trí trong transaction để rollback một phần thay đổi.

Ví dụ:

~~~sql
BEGIN;

INSERT INTO orders_lab (
    request_id, customer_id, status, currency, total_amount
)
VALUES (
    '33333333-3333-4333-8333-333333333333',
    700, 'PENDING_PAYMENT', 'VND', 100000.00
);

SAVEPOINT optional_discount;

-- Một bước áp dụng ưu đãi có thể thất bại.
-- Nếu thất bại, rollback về savepoint:
ROLLBACK TO SAVEPOINT optional_discount;

-- Tiếp tục phần bắt buộc theo nghiệp vụ.
COMMIT;
~~~

Savepoint không thay thế transaction chính. Chỉ dùng khi nghiệp vụ xác định phần nào thực sự tùy chọn. Không rollback một phần rồi commit nếu invariant bắt buộc đã bị phá vỡ.

## 18. Transaction trong Java JDBC

JDBC thường mặc định auto-commit. Nếu cần nhiều statement cùng transaction, tắt auto-commit.

### 18.1. Mẫu cơ bản

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        debit(connection, fromId, amount);
        credit(connection, toId, amount);
        insertTransfer(connection, requestId, fromId, toId, amount);

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
~~~

### 18.2. Vì sao không dùng connection khác cho mỗi statement?

Transaction thuộc về một database session/connection. Nếu debit chạy trên connection A còn credit chạy trên connection B, chúng không nằm trong cùng transaction. Commit/rollback ở A không điều khiển thay đổi của B.

Giữ cùng Connection cho toàn bộ thao tác.

### 18.3. Auto-commit và connection pool

Với connection pool:

- Connection được tái sử dụng giữa request.
- Phải đảm bảo transaction được commit hoặc rollback.
- Không để connection có auto-commit/isolation/read-only state khác mong đợi khi trả về pool.
- Framework/pool thường có cơ chế reset state; không tự ý thay đổi ngoài hợp đồng.

Nếu tự quản lý JDBC, khôi phục state an toàn hoặc loại bỏ connection khi không thể xác định trạng thái.

### 18.4. Spring transaction

Trong ứng dụng Spring, có thể dùng transaction manager:

~~~java
@Transactional
public TransferResult transfer(TransferCommand command) {
    accountRepository.debit(
        command.fromId(),
        command.amount()
    );
    accountRepository.credit(
        command.toId(),
        command.amount()
    );
    return transferRepository.insert(command);
}
~~~

Transaction manager bao các thao tác repository tham gia cùng transaction. Cần chú ý:

- Các repository phải dùng cùng transaction manager/DataSource.
- Mặc định rollback thường áp dụng cho unchecked exception; cấu hình rollbackFor nếu cần rollback cho checked exception.
- Không nuốt exception rồi trả thành công.
- Gọi method trong cùng object có thể không đi qua proxy transaction tùy cấu hình.
- Không gọi remote service chậm trong transaction.

Đọc tài liệu framework và cấu hình thực tế; annotation không tự làm các kết nối database khác nhau trở thành một transaction phân tán.

## 19. Transaction trong Python DB-API

DB-API driver thường có chế độ transaction và commit/rollback trên connection. Cú pháp context manager phụ thuộc driver.

Ví dụ dạng tổng quát:

~~~python
connection.autocommit = False

try:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE bank_accounts_lab
            SET balance = balance - %s
            WHERE account_id = %s
              AND balance >= %s
            """,
            (amount, from_id, amount),
        )
        if cursor.rowcount != 1:
            raise ValueError("Insufficient funds or invalid source")

        cursor.execute(
            """
            UPDATE bank_accounts_lab
            SET balance = balance + %s
            WHERE account_id = %s
            """,
            (amount, to_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("Invalid destination")

    connection.commit()
except Exception:
    connection.rollback()
    raise
~~~

Đây là ví dụ kiểu psycopg placeholder %s; không copy dấu placeholder này sang sqlite3, nơi thường dùng ?. Kiểm tra API autocommit, context manager và rowcount theo driver.

## 20. Stored procedure và transaction ownership

Transaction có thể được điều khiển ở application layer hoặc trong stored procedure, nhưng phải xác định rõ ai sở hữu ranh giới transaction.

### 20.1. Application-owned transaction

Ứng dụng mở transaction, gọi các procedure/statement tham gia transaction và commit/rollback ở cuối. Đây là cách phổ biến trong service/repository.

### 20.2. Procedure-owned transaction

Một số DBMS cho phép procedure điều khiển transaction trong những giới hạn cụ thể. Cách này có thể hữu ích khi toàn bộ nghiệp vụ nằm trong database, nhưng semantics khác nhau theo DBMS.

Không viết procedure vừa tự commit/rollback vừa được gọi trong một transaction do application quản lý mà không hiểu rõ quy tắc DBMS. PostgreSQL function và procedure cũng có quy tắc transaction control khác nhau; transaction control không được phép ở mọi context gọi.

### 20.3. Không trộn ranh giới mơ hồ

Chọn một nơi rõ ràng chịu trách nhiệm:

- Application transaction manager; hoặc
- Stored procedure được thiết kế để quản lý transaction theo DBMS.

Document hợp đồng cho caller: procedure có tự commit không, có thể gọi bên trong transaction không, lỗi nào được ném lại và trạng thái dữ liệu khi lỗi.

## 21. Kiểm thử transaction chuyển tiền

Kiểm thử cần xác minh cả kết quả cuối và tính nguyên tử.

### 21.1. Test thành công

Fixture:

- Account A: 1.000.000 VND.
- Account B: 300.000 VND.
- Chuyển 200.000 VND.

Assert:

- A còn 800.000.
- B có 500.000.
- Có một transfer record.
- Có hai ledger entries.
- Tổng debit bằng tổng credit.
- Request ID chỉ xuất hiện một lần.

### 21.2. Test không đủ tiền

Chuyển 2.000.000 từ A có 1.000.000:

- Debit row count = 0.
- Transaction rollback.
- Số dư A/B không đổi.
- Không có transfer record.
- Không có ledger entries.

### 21.3. Test tài khoản đích không hợp lệ

Debit có thể chạy trước, nhưng credit không tìm thấy tài khoản đích:

- Rollback.
- Số dư nguồn trở lại giá trị ban đầu.
- Không có transfer/ledger.

### 21.4. Test cùng tài khoản

Chuyển từ account 1001 sang chính 1001 phải bị từ chối trước khi ghi. Constraint from_account_id <> to_account_id là lớp bảo vệ database bổ sung.

### 21.5. Test khác currency

Không cho chuyển trực tiếp giữa VND và USD nếu không có luồng FX được định nghĩa. Không chỉ cộng/trừ hai con số khác currency rồi coi như cân bằng.

### 21.6. Test request lặp

Gửi cùng request_id hai lần:

- Chỉ một transfer được tạo.
- Chỉ một lần debit/credit được áp dụng.
- Lần thứ hai trả lại kết quả cũ hoặc conflict theo hợp đồng.
- Nếu payload khác, từ chối tái sử dụng key.

### 21.7. Test đồng thời

Account có 300.000; chạy đồng thời hai transfer 200.000:

- Chỉ một giao dịch được thành công.
- Giao dịch còn lại bị từ chối do không đủ số dư hoặc retry/đọc lại rồi bị từ chối.
- Số dư cuối không âm.
- Ledger và transfer record khớp với đúng một lần chuyển.

## 22. Kiểm thử transaction đặt hàng

### 22.1. Test đủ tồn kho

Đặt Keyboard ×1 và Mouse ×2:

- Order được tạo.
- Hai order_items được tạo.
- available của Keyboard giảm 1.
- reserved của Keyboard tăng 1.
- available của Mouse giảm 2.
- reserved của Mouse tăng 2.
- Tổng tiền order bằng tổng line_total.
- Có một outbox event PAYMENT_REQUESTED.

### 22.2. Test thiếu hàng ở dòng sau

Keyboard còn 10; Monitor còn 2; request cần Keyboard ×1 và Monitor ×3:

- Không có order được commit.
- Không có order_items.
- Keyboard vẫn còn 10.
- Monitor vẫn còn 2.
- Không có outbox event.

Đây là test quan trọng để chứng minh rollback toàn bộ.

### 22.3. Test request rỗng và quantity không hợp lệ

- Giỏ rỗng: từ chối trước transaction hoặc rollback.
- Quantity 0/âm: validation/constraint từ chối.
- Product không tồn tại: FK hoặc validation từ chối.
- Product inactive: không giữ hàng.
- SKU trùng: gộp hoặc xử lý theo quy tắc rõ ràng.

### 22.4. Test hai đơn cùng mua SKU cuối

Inventory còn 1. Hai request cùng đặt 1:

- Chỉ một request reserve thành công.
- Request còn lại không tạo đơn hoàn tất giữ hàng.
- available không âm.
- reserved tăng đúng 1.

### 22.5. Test lỗi sau commit trước khi gửi event

Nếu ứng dụng crash sau khi commit order nhưng trước khi gửi event tới payment worker, outbox event vẫn nằm trong database. Worker có thể gửi lại sau khi ứng dụng hoạt động. Đây là lý do ghi outbox trong cùng transaction với order.

## 23. Kiểm thử bằng transaction rollback để cô lập fixture

Một số integration test có thể chạy trong transaction và rollback sau test:

~~~text
BEGIN test transaction
  insert fixtures
  execute business operation
  assert database state
ROLLBACK
~~~

Cách này giữ database sạch, nhưng cần lưu ý:

- Test dùng nhiều connection có thể không nhìn thấy fixture chưa commit.
- Worker bất đồng bộ không thể xử lý outbox chưa commit.
- Test concurrency cần nhiều transaction/connection thực sự, không chỉ một transaction bao ngoài.
- Một số framework tự mở transaction cho test; thao tác commit trong code có thể tương tác với transaction test theo cách đặc biệt.

Với test outbox/worker hoặc concurrency, có thể cần database/schema riêng và fixture cleanup thay vì một transaction test đơn lẻ.

## 24. Các invariant nên được xác minh sau transaction

### 24.1. Chuyển tiền không phí

Với hai tài khoản cùng currency:

~~~text
source_balance_before + destination_balance_before
=
source_balance_after + destination_balance_after
~~~

Nếu có phí, phải đưa tài khoản phí vào phương trình.

Ledger:

~~~text
SUM(DEBIT amount) = SUM(CREDIT amount)
~~~

cho từng transfer theo mô hình đơn giản hai bút toán.

### 24.2. Đặt hàng

~~~text
order.total_amount
= SUM(order_items.line_total)
  + shipping_fee
  + tax
  - discount
~~~

Tùy mô hình tồn kho:

~~~text
available_quantity >= 0
reserved_quantity >= 0
~~~

Khi reserve thành công:

~~~text
available_before - available_after
= quantity_reserved

reserved_after - reserved_before
= quantity_reserved
~~~

Khi xác nhận/hoàn tất đơn, quy tắc chuyển reserved sang sold phải nhất quán. Khi hủy, giải phóng reservation đúng một lần.

## 25. State machine cho order và payment

Transaction giúp lưu các chuyển trạng thái hợp lệ, nhưng state machine xác định **trạng thái nào được phép chuyển sang trạng thái nào**.

Ví dụ order:

~~~text
PENDING_PAYMENT
   | payment success
   v
CONFIRMED

PENDING_PAYMENT
   | payment failure/expiry
   v
PAYMENT_FAILED or CANCELLED
~~~

Không cho phép một order đã CANCELLED tự chuyển thành CONFIRMED chỉ vì worker nhận event cũ. Dùng điều kiện trạng thái khi update:

~~~sql
UPDATE orders_lab
SET status = 'CONFIRMED'
WHERE order_id = 501
  AND status = 'PENDING_PAYMENT';
~~~

Kiểm tra row count:

- 1: chuyển trạng thái thành công.
- 0: trạng thái đã đổi hoặc order không tồn tại; đọc lại và xử lý idempotent.

Khi hủy đơn và release stock, cũng phải đảm bảo chỉ release reservation một lần. Có thể dùng transition có điều kiện và stock movement record unique theo order/item/action.

## 26. Những lỗi thường gặp

### Lỗi 1 — Mỗi statement dùng một connection riêng

Debit và credit chạy trên hai connection không thuộc cùng transaction. Giữ một connection/transaction manager xuyên suốt các thay đổi liên quan.

### Lỗi 2 — Quên tắt auto-commit

Trong JDBC, auto-commit có thể làm từng statement commit riêng. Tắt auto-commit hoặc dùng transaction manager.

### Lỗi 3 — Commit trước khi ghi đủ ledger/order items

Commit quá sớm khiến dữ liệu nửa vời. Xác định ranh giới transaction trước khi code.

### Lỗi 4 — Không kiểm tra row count

UPDATE 0 hàng có thể là không đủ tiền, tài khoản không tồn tại hoặc trạng thái đã đổi. Không tiếp tục các bước phụ thuộc.

### Lỗi 5 — Chỉ đọc số dư rồi UPDATE theo giá trị cũ

Hai request đồng thời có thể cùng tiêu số dư. Dùng row lock hoặc conditional atomic UPDATE và constraint.

### Lỗi 6 — Không khóa theo thứ tự nhất quán

Hai transaction lấy lock ngược thứ tự có thể deadlock. Sắp thứ tự khóa theo khóa ổn định.

### Lỗi 7 — Nghĩ CHECK constraint thay transaction

CHECK(balance >= 0) ngăn số dư âm, nhưng không đảm bảo debit, credit và ledger cùng được ghi. Vẫn cần transaction.

### Lỗi 8 — Dùng FLOAT cho tiền

Sai số dấu phẩy động có thể làm tổng không khớp. Dùng NUMERIC/DECIMAL và BigDecimal/Decimal ở ứng dụng.

### Lỗi 9 — Tin giá và tổng tiền từ client

Client có thể sửa request. Tính giá phía server và lưu snapshot giá trong order item.

### Lỗi 10 — Giữ transaction khi gọi payment gateway

Network call lâu giữ lock và không thể rollback side effect ngoài database. Dùng outbox/state machine.

### Lỗi 11 — Nghĩ rollback database hoàn lại tiền đã thu

Rollback chỉ tác động transaction của database đó. Hoàn tiền qua provider là thao tác bù riêng.

### Lỗi 12 — Retry mọi lỗi

Syntax error, invalid input, permission denied và constraint violation thường không tự hết. Retry vô hạn tăng tải.

### Lỗi 13 — Retry riêng statement cuối sau deadlock

Transaction nạn nhân đã rollback. Bắt đầu transaction mới và chạy lại toàn bộ logic.

### Lỗi 14 — Không có idempotency key

Client retry sau timeout có thể tạo hai transfer/order. Dùng request ID có UNIQUE constraint và lưu kết quả trong cùng transaction.

### Lỗi 15 — Chỉ SELECT kiểm tra request ID

Hai transaction có thể cùng không thấy key. UNIQUE constraint mới xử lý race; code phải bắt conflict và đọc kết quả đã commit.

### Lỗi 16 — Cùng idempotency key nhưng payload khác

Có thể trả nhầm kết quả cũ hoặc che request bị sửa. Lưu và so sánh payload hash/fields.

### Lỗi 17 — Cập nhật tồn kho từng dòng mà không gộp SKU

SKU trùng trong giỏ có thể gây kiểm tra và cập nhật lặp. Gộp quantity theo product trước khi giữ kho.

### Lỗi 18 — Hai bảng con JOIN trực tiếp rồi cộng tổng

Quan hệ 1:N ở hai phía có thể nhân số hàng. Tổng hợp mỗi phía trước khi JOIN.

### Lỗi 19 — Gửi email trước commit

Transaction có thể rollback sau khi email đã gửi. Ghi outbox cùng transaction và gửi sau commit.

### Lỗi 20 — Nuốt exception

Catch rồi không ném lại có thể khiến transaction manager hiểu thao tác thành công. Chỉ xử lý lỗi có chủ đích; lỗi khác phải propagate.

### Lỗi 21 — Không xử lý lỗi rollback

Rollback cũng có thể lỗi nếu connection đã mất. Gắn rollback error làm suppressed/cause và loại connection không rõ trạng thái khỏi pool.

### Lỗi 22 — Nghĩ COMMIT timeout chắc chắn rollback

Kết quả commit có thể không rõ nếu response mất. Tra cứu bằng idempotency key trước khi chạy lại.

### Lỗi 23 — Transaction quá dài

Giữ lock trong lúc xử lý mạng/tính toán dài làm tăng contention và deadlock. Giữ phần transaction ngắn.

### Lỗi 24 — Không test hai request đồng thời

Test tuần tự không phát hiện race. Tạo integration test với nhiều connection và đồng bộ thời điểm.

### Lỗi 25 — Hủy đơn giải phóng kho hai lần

Hai worker xử lý cancel có thể cùng tăng available_quantity. Dùng state transition có điều kiện và reservation/stock movement unique.

## 27. Quy trình triển khai một transaction nghiệp vụ

Trước khi code:

1. Viết rõ invariant nghiệp vụ.
2. Xác định tất cả bảng cần thay đổi.
3. Xác định bước nào phải atomic.
4. Chọn constraint có thể bảo vệ invariant ở database.
5. Xác định row cần khóa và thứ tự khóa.
6. Chọn isolation level theo anomaly cần ngăn.
7. Thiết kế idempotency key và retry behavior.
8. Xác định side effect ngoài database và outbox/compensation.

Khi chạy:

1. Validate input không cần database.
2. Bắt đầu transaction.
3. Đọc/khóa dữ liệu cần thiết.
4. Kiểm tra điều kiện nghiệp vụ.
5. Ghi từng thay đổi và kiểm tra row count.
6. Ghi ledger/outbox/idempotency trong cùng transaction nếu cần.
7. Commit.
8. Chỉ trả success sau khi commit được xác nhận.
9. Nếu lỗi, rollback; phân loại lỗi và retry chỉ khi an toàn.

Sau khi chạy:

- Ghi log correlation/request ID, operation và trạng thái commit.
- Không log credential hoặc dữ liệu nhạy cảm không cần thiết.
- Theo dõi deadlock, lock wait, retry rate, transaction duration và outbox lag.
- Đối soát ledger/số dư hoặc order/reservation theo định kỳ.

## 28. Bài tập thực hành có đáp án

### Bài 1 — Xác định ranh giới transaction

Chuyển tiền gồm debit, credit và insert transfer. Có nên commit sau debit không?

**Đáp án:** Không. Cả ba thay đổi phải cùng transaction.

### Bài 2 — Số dư âm

Constraint nào ngăn balance âm?

~~~sql
CHECK (balance >= 0)
~~~

**Đáp án:** CHECK constraint trên cột balance. Nó bổ sung bảo vệ; vẫn cần logic debit đúng.

### Bài 3 — Số tiền hợp lệ

Amount bằng 0 hoặc âm có được chuyển không?

**Đáp án:** Không trong mô hình này; validate ở ứng dụng và CHECK(amount > 0).

### Bài 4 — Tiền tệ

Có thể cộng 100.000 VND vào tài khoản USD mà không có FX?

**Đáp án:** Không. Phải cùng currency hoặc có quy trình tỷ giá/định giá rõ ràng.

### Bài 5 — Debit row count bằng 0

Ứng dụng nên làm gì?

**Đáp án:** Không credit; rollback và trả lỗi nghiệp vụ phù hợp như không đủ số dư hoặc tài khoản không hợp lệ.

### Bài 6 — Credit thất bại sau debit

Kết quả mong muốn?

**Đáp án:** Rollback toàn transaction để số dư nguồn trở về ban đầu, không transfer/ledger nào được lưu.

### Bài 7 — Vì sao dùng NUMERIC?

**Đáp án:** NUMERIC/DECIMAL biểu diễn số thập phân chính xác theo precision/scale; FLOAT có sai số biểu diễn.

### Bài 8 — FOR UPDATE

Mục đích của SELECT ... FOR UPDATE?

**Đáp án:** Khóa các hàng được chọn để transaction khác không thể cập nhật chúng đồng thời cho tới khi transaction kết thúc.

### Bài 9 — Thứ tự lock

Hai giao dịch chuyển tiền ngược chiều nên khóa theo thứ tự nào?

**Đáp án:** Cùng thứ tự ổn định, ví dụ account_id tăng dần.

### Bài 10 — Conditional UPDATE

Vì sao thêm WHERE balance >= amount?

**Đáp án:** Kiểm tra điều kiện và trừ tiền trong cùng statement, tránh tiêu số dư đã bị transaction khác thay đổi.

### Bài 11 — Idempotency

Client timeout sau khi server commit rồi retry cùng request. Điều gì ngăn chuyển tiền hai lần?

**Đáp án:** request_id có UNIQUE constraint, lưu trong cùng transaction và đọc lại kết quả đã commit.

### Bài 12 — Cùng key, payload khác

Client dùng lại request_id nhưng đổi amount. Xử lý thế nào?

**Đáp án:** So sánh payload đã lưu và từ chối conflict; không áp dụng request mới dưới key cũ.

### Bài 13 — Deadlock

Sau deadlock, chỉ chạy lại UPDATE cuối có đúng không?

**Đáp án:** Không. Rollback và chạy lại toàn transaction.

### Bài 14 — Serializable

Serializable có thể phát sinh serialization failure không?

**Đáp án:** Có. Ứng dụng phải rollback và retry toàn transaction có giới hạn.

### Bài 15 — Đặt hàng thiếu sản phẩm thứ hai

Sản phẩm đầu đã reserve, sản phẩm thứ hai hết hàng. Trạng thái sau rollback?

**Đáp án:** Không có order/order_items đã commit; reservation sản phẩm đầu được hoàn lại.

### Bài 16 — Giỏ có SKU trùng

Hai dòng cùng product có quantity 1 và 2. Nên làm gì?

**Đáp án:** Gộp thành quantity 3 hoặc có logic tương đương trước khi kiểm tra/giữ kho.

### Bài 17 — Giá từ client

Có nên tin unit_price client gửi?

**Đáp án:** Không. Lấy giá phía server và snapshot vào order_items.

### Bài 18 — Payment gateway timeout

Database rollback có chứng minh gateway chưa thu tiền không?

**Đáp án:** Không. Kết quả bên ngoài có thể không rõ; tra cứu payment intent hoặc dùng idempotency key của provider.

### Bài 19 — Outbox

Vì sao ghi outbox cùng transaction tạo order?

**Đáp án:** Nếu order commit thì event cùng tồn tại; nếu rollback thì event cũng rollback, tránh mất event giữa DB commit và publish.

### Bài 20 — Outbox gửi lặp

Worker có thể gửi cùng event hai lần không?

**Đáp án:** Có trong mô hình at-least-once. Consumer cần deduplicate/idempotency.

### Bài 21 — Savepoint

Savepoint dùng để làm gì?

**Đáp án:** Rollback một phần thay đổi về điểm đã đánh dấu trong transaction, khi nghiệp vụ cho phép tiếp tục.

### Bài 22 — JDBC connection

Debit ở connection A và credit ở connection B có cùng transaction không?

**Đáp án:** Không. Transaction gắn với session/connection; dùng cùng connection hoặc transaction manager.

### Bài 23 — Auto-commit

Vì sao phải tắt auto-commit trong JDBC transaction nhiều statement?

**Đáp án:** Để các statement không tự commit riêng lẻ trước khi toàn bộ công việc hoàn tất.

### Bài 24 — Test đồng thời

Account có 300.000; hai request cùng chuyển 200.000. Kết quả đúng?

**Đáp án:** Tối đa một transfer thành công; số dư không âm và ledger chỉ ghi đúng giao dịch thành công.

### Bài 25 — Release inventory hai lần

Hai worker cùng hủy một order. Cách ngăn cộng kho hai lần?

**Đáp án:** Conditional state transition từ trạng thái có thể hủy, kết hợp unique stock movement/reservation action.

### Bài 26 — Commit response bị mất

Có nên gửi lại thao tác tạo đơn bằng request ID mới?

**Đáp án:** Không. Tra cứu theo cùng idempotency key trước; key mới có thể tạo đơn thứ hai.

### Bài 27 — Transaction duration

Có nên chờ người dùng xác nhận trong lúc giữ FOR UPDATE?

**Đáp án:** Không. Transaction cần ngắn; không giữ lock qua tương tác người dùng hoặc network call.

### Bài 28 — Tổng ledger

Trong transfer đơn giản không phí, tổng debit và credit phải thế nào?

**Đáp án:** Bằng nhau theo cùng currency và transfer.

### Bài 29 — Isolation level

Serializable có nghĩa ứng dụng không cần xử lý lỗi concurrency không?

**Đáp án:** Không. DBMS có thể từ chối transaction để duy trì serializability; ứng dụng cần retry đúng cách.

### Bài 30 — Kiểm thử rollback

Nêu ba điều cần assert khi lỗi xảy ra sau khi debit thành công.

**Đáp án:** Số dư nguồn/đích không đổi so với trước transaction; không có transfer record; không có ledger entries.

## 29. Bảng ghi nhớ nhanh

| Thành phần | Vai trò |
|---|---|
| BEGIN | Bắt đầu transaction |
| COMMIT | Xác nhận tất cả thay đổi trong transaction |
| ROLLBACK | Hủy các thay đổi chưa commit |
| SAVEPOINT | Đánh dấu vị trí rollback một phần |
| SELECT FOR UPDATE | Khóa hàng để phối hợp ghi đồng thời |
| Conditional UPDATE | Kiểm tra điều kiện và cập nhật trong cùng statement |
| CHECK | Bảo vệ invariant trên hàng |
| UNIQUE | Chặn duplicate theo khóa |
| FOREIGN KEY | Bảo vệ quan hệ tham chiếu |
| Row count | Xác minh số hàng thực sự bị tác động |
| Idempotency key | Ngăn cùng request logic áp dụng nhiều lần |
| Deadlock retry | Rollback rồi chạy lại toàn transaction có giới hạn |
| Outbox | Ghi event cùng transaction, publish sau commit |
| Saga | Điều phối nhiều transaction/hệ thống bằng bước bù trừ |
| Decimal/NUMERIC | Lưu số tiền chính xác theo precision/scale |
| Stable lock order | Giảm deadlock khi khóa nhiều hàng |

## Kết luận

**Chuyển tiền và đặt hàng là các thao tác nhiều bước phải được bảo vệ bằng một ranh giới transaction rõ ràng.** Transaction đảm bảo các thay đổi database liên quan cùng commit hoặc cùng rollback, nhưng ứng dụng vẫn phải xác minh invariant, số hàng bị ảnh hưởng, quyền giao dịch và trạng thái cuối.

Khi triển khai:

- **Chuyển tiền:** debit, credit, transfer record và ledger entries cùng transaction; dùng NUMERIC/DECIMAL, kiểm tra số dư và khóa tài khoản theo thứ tự ổn định.
- **Đặt hàng:** tạo order, giữ kho, tạo order items và ghi outbox trong cùng transaction; kiểm tra từng SKU và gộp số lượng trùng.
- **Đồng thời:** dùng conditional UPDATE, row lock, constraint và isolation level phù hợp; retry toàn transaction khi gặp lỗi tạm thời được xác định.
- **Request lặp:** dùng idempotency key có UNIQUE constraint, kiểm tra payload và lưu kết quả cùng transaction.
- **Hệ thống bên ngoài:** không giả định rollback database có thể hoàn tác thanh toán/email; dùng outbox, state machine, idempotency và hành động bù trừ.
- **Kiểm thử:** xác minh cả đường thành công, lỗi giữa chừng, rollback, request lặp và hai giao dịch đồng thời.

Một transaction tốt không chỉ là vài câu lệnh nằm giữa BEGIN và COMMIT. Nó là một quy trình có invariant rõ ràng, thứ tự khóa hợp lý, điều kiện cập nhật được kiểm tra, khả năng phục hồi khi lỗi và kết quả có thể xác minh sau commit.
