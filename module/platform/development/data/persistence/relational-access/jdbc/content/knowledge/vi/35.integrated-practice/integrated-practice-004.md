# Chuyển tiền giữa hai tài khoản trong cùng giao dịch bằng JDBC

Trong một ứng dụng Java sử dụng **JDBC**, thao tác “chuyển 125,50 đơn vị tiền từ tài khoản A sang tài khoản B” nghe có vẻ chỉ gồm hai câu `UPDATE`: trừ số dư của A, rồi cộng số dư của B. Nhưng nếu lệnh thứ nhất thành công còn lệnh thứ hai thất bại, hệ thống có thể làm **biến mất tiền**. Nếu hai yêu cầu cùng chuyển từ A, cả hai có thể đọc số dư cũ và làm sai số dư. Nếu server đã `COMMIT` nhưng kết nối bị ngắt trước khi ứng dụng nhận xác nhận, gửi lại yêu cầu có thể **chuyển tiền hai lần**.

Bài **“Chuyển tiền giữa hai tài khoản trong cùng giao dịch”** thuộc chương **Thực hành tổng hợp** của module **JDBC**. Ta sẽ kết hợp `DataSource`, `Connection`, `PreparedStatement`, `ResultSet`, SQL tham số hóa, kiểm tra số hàng bị tác động, `BigDecimal`, transaction, khóa, ngoại lệ, connection pool và kiểm thử tích hợp để xây dựng một ví dụ chuyển tiền có tính nguyên tử.

Bài học không nhằm xây dựng hệ thống ngân hàng production hoàn chỉnh. Một hệ thống tài chính thực tế thường cần **sổ cái kép bất biến**, phân quyền, xác thực lệnh, đối soát, idempotency, kiểm toán và kiểm soát vận hành chặt chẽ hơn. Ví dụ ở đây tập trung vào bất biến cốt lõi: **hai thay đổi số dư và bản ghi chuyển tiền phải cùng được commit hoặc cùng bị rollback**.

**Kết quả mong đợi:** bạn có thể giải thích vì sao hai câu SQL cần cùng `Connection` và transaction, triển khai đường thành công và đường thất bại, kiểm tra cạnh tranh giữa các transaction, và nhận diện rủi ro khi mất kết nối lúc commit.

## 1. Đề bài nghiệp vụ và các bất biến phải giữ

Giả sử có hai tài khoản cùng đồng tiền:

```text
Trước chuyển tiền
  A: 1 000,00 USD
  B:   300,00 USD
  Tổng: 1 300,00 USD

Chuyển A → B: 125,50 USD

Sau chuyển tiền thành công
  A:   874,50 USD
  B:   425,50 USD
  Tổng: 1 300,00 USD
```

Một yêu cầu hợp lệ cần giữ những bất biến sau:

| Bất biến | Mô tả | Cách bảo vệ |
| --- | --- | --- |
| **Nguyên tử** | Không được chỉ trừ A mà không cộng B | Hai `UPDATE` và bản ghi chuyển tiền trong **một transaction** |
| **Không âm số dư** | A chỉ được trừ khi số dư đủ | `UPDATE ... WHERE balance >= ?`, `CHECK` ở DB, kiểm tra số hàng |
| **Bảo toàn tổng** | Nếu không có phí và không đổi tiền, `A + B` không đổi | Trừ và cộng **chính xác cùng một `BigDecimal`** |
| **Đồng tiền phù hợp** | Không cộng USD vào tài khoản VND | Kiểm tra currency của cả hai tài khoản; không ngầm chuyển đổi |
| **Hai tài khoản tồn tại và khác nhau** | Không gửi tiền tới tài khoản thiếu hoặc chuyển cho chính mình | Validation và kiểm tra hàng khóa |
| **Mỗi yêu cầu logic không bị thực hiện hai lần** | Request bị gửi lại không chuyển tiền trùng | Mã idempotency riêng với ràng buộc `UNIQUE`/khóa chính |
| **Dữ liệu đúng khi đồng thời** | Hai yêu cầu không tiêu cùng số dư cũ | Khóa hàng và điều kiện `WHERE` nguyên tử; test hai connection |
| **Có thể kiểm toán** | Biết một lần chuyển thành công gồm những gì | Bản ghi chuyển tiền trong chính transaction, không tự ghi sau commit |

**Không nhầm “một transaction” với “một câu SQL”.** JDBC cho phép nhiều câu SQL chạy trong cùng một transaction trên một `Connection`. Việc ghi cùng transaction không yêu cầu phải ghép mọi thao tác thành một chuỗi SQL dài hoặc gọi stored procedure.

Để tránh mơ hồ, ví dụ chỉ xử lý **chuyển tiền cùng đồng tiền, không có phí và không chuyển đổi ngoại tệ**, với số tiền có hai chữ số thập phân. Hệ thống hỗ trợ VND (thường không có hai số thập phân theo cách biểu diễn nghiệp vụ) hoặc nhiều loại tiền cần định nghĩa precision/scale và quy tắc làm tròn **theo từng đồng tiền**, không sao chép cứng hợp đồng của ví dụ này.

## 2. Thiết kế schema tối thiểu và dữ liệu khởi tạo

Ta cần bảng tài khoản và bảng ghi nhận lệnh đã được thực hiện. Một schema minh họa:

```sql
CREATE TABLE accounts (
    id          BIGINT PRIMARY KEY,
    currency    CHAR(3) NOT NULL,
    balance     DECIMAL(19, 2) NOT NULL,
    version     BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT chk_account_balance_nonnegative
        CHECK (balance >= 0)
);

CREATE TABLE transfer_log (
    request_key         VARCHAR(64) PRIMARY KEY,
    source_account_id   BIGINT NOT NULL,
    target_account_id   BIGINT NOT NULL,
    currency            CHAR(3) NOT NULL,
    amount              DECIMAL(19, 2) NOT NULL,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_transfer_source
        FOREIGN KEY (source_account_id) REFERENCES accounts(id),
    CONSTRAINT fk_transfer_target
        FOREIGN KEY (target_account_id) REFERENCES accounts(id),
    CONSTRAINT chk_transfer_positive CHECK (amount > 0),
    CONSTRAINT chk_transfer_distinct
        CHECK (source_account_id <> target_account_id)
);
```

**Lưu ý tính khả chuyển:** đây là DDL minh họa gần với SQL phổ biến. Cú pháp `CHECK`, `DEFAULT`, kiểu thời gian, đặc tính transaction và constraint có thể khác giữa các DBMS hoặc storage engine. Cần dùng migration được kiểm thử với database đang triển khai. Ở một số môi trường, `CHAR(3)` có quy tắc đệm khoảng trắng hoặc collation riêng; test mapping currency phải xác nhận rõ.

Dữ liệu thử nghiệm:

```sql
INSERT INTO accounts (id, currency, balance, version)
VALUES (101, 'USD', 1000.00, 0);

INSERT INTO accounts (id, currency, balance, version)
VALUES (202, 'USD', 300.00, 0);
```

Sử dụng **database thử nghiệm riêng** để chạy ví dụ và thay đổi dữ liệu. Không chạy trực tiếp trên tài khoản thực hoặc hệ thống production.

### Vì sao cần hai bảng?

- `accounts` chứa **trạng thái số dư hiện tại** để truy vấn và kiểm tra còn đủ tiền.
- `transfer_log` lưu **một lần chuyển tiền đã commit**, cùng `request_key` duy nhất, giúp đối soát hoặc phát hiện yêu cầu lặp.
- Bản ghi `transfer_log` được tạo **trong cùng transaction** với hai cập nhật số dư; nếu rollback, cả ba thay đổi biến mất.
- `version` tăng khi thay đổi số dư để các hệ thống khác có cơ sở thực hiện optimistic locking nếu cần; nó không thay thế khóa hoặc transaction của ví dụ.
- Khóa chính `request_key` chặn **hai bản ghi transfer cùng một mã yêu cầu** ở mức database. Tuy nhiên, cách xử lý khi trùng khóa và khi commit chưa rõ vẫn cần thiết kế riêng; một constraint không tự tạo ra API idempotent hoàn chỉnh.

### Những giả định không được bỏ qua

Ví dụ đòi hỏi bảng dùng **cơ chế transaction thật**. Nếu storage engine không hỗ trợ commit/rollback cho những bảng này, `connection.rollback()` không bảo đảm nguyên tử. Mọi tài khoản tham gia đều phải nằm trong cùng database/resource được quản lý bởi một JDBC local transaction; nếu A và B ở hai database khác nhau, một `Connection` đơn lẻ không thể tự đảm bảo atomicity cho cả hai.

## 3. Trường hợp sai: mỗi UPDATE tự commit độc lập

Một cách viết hấp dẫn nhưng nguy hiểm:

```java
// MẪU SAI: mỗi DAO tự mượn connection và auto-commit.
try (Connection c = dataSource.getConnection();
     PreparedStatement s = c.prepareStatement(
             "UPDATE accounts SET balance = balance - ? WHERE id = ?")) {
    s.setBigDecimal(1, amount);
    s.setLong(2, fromId);
    s.executeUpdate(); // Có thể đã commit ngay!
}

// Nếu câu lệnh thứ hai lỗi, câu đầu có thể đã được commit.
try (Connection c = dataSource.getConnection();
     PreparedStatement s = c.prepareStatement(
             "UPDATE accounts SET balance = balance + ? WHERE id = ?")) {
    s.setBigDecimal(1, amount);
    s.setLong(2, toId);
    s.executeUpdate();
}
```

Ở chế độ `autoCommit=true` thông thường, mỗi câu lệnh được commit độc lập khi hoàn tất theo ngữ nghĩa của JDBC/driver. Nếu câu thứ hai không tìm thấy tài khoản nhận, bị từ chối vì constraint hoặc kết nối đứt, số dư A có thể đã giảm nhưng B không tăng.

Ngay cả khi hai đoạn dùng **cùng `Connection`**, để `autoCommit=true` vẫn không tạo một transaction bao trùm cả hai câu SQL. Cần chủ động đặt `autoCommit=false` trước khi thực hiện các bước, rồi `commit()` **một lần sau tất cả thành công** hoặc `rollback()` khi thất bại.

### Vì sao không nên “cứ cộng lại tiền nếu câu hai lỗi”?

Một chiến lược sửa sai bằng lệnh `UPDATE accounts SET balance = balance + ?` sau khi lỗi là một **giao dịch bù** (*compensating transaction*), không tương đương nguyên tử:

- Lệnh bù cũng có thể thất bại do mạng, khóa hoặc lỗi server.
- Có thể có request khác nhìn thấy số dư đã trừ trong khoảng giữa.
- Nếu lỗi xuất hiện sau khi câu cộng B thực sự chạy nhưng ứng dụng mất phản hồi, thực hiện bù không kiểm soát có thể khiến tổng tiền sai.
- Ghi nhật ký, trigger và hệ thống ngoài có thể đã nhận tác động mà phép bù không đảo ngược.

Với hai hàng trong cùng một database transactional, **local transaction trên một connection** đơn giản và an toàn hơn mô hình bù thủ công.

## 4. Transaction boundary và vòng đời Connection

Luồng đúng từ góc nhìn service:

```text
DataSource.getConnection()
          │
          ▼
  Kiểm tra trạng thái Connection
          │
          ▼
    setAutoCommit(false)
          │
          ├─ Khóa tài khoản theo thứ tự cố định
          ├─ Kiểm tra số dư/currency
          ├─ INSERT transfer_log (giữ request_key)
          ├─ UPDATE trừ tiền ở A
          ├─ UPDATE cộng tiền ở B
          │
          ├─ Nếu mọi bước PASS ──► commit()
          │
          └─ Nếu bước nào FAIL ─► rollback()
          │
          ▼
  Phục hồi trạng thái phù hợp
          │
          ▼
    Connection.close()
          │
          └─ Pooled DataSource: thường trả quyền sử dụng về pool
```

**Vai trò:** service sở hữu ranh giới transaction. Các hàm truy cập dữ liệu cấp thấp chỉ nhận `Connection` được truyền vào; chúng **không tự gọi `getConnection()`**, `commit()`, `rollback()` hay `close()` kết nối đó.

Một số điểm quan trọng:

- `DataSource` có thể là connection pool, nhưng `Connection` ứng dụng nhận vẫn phải dùng đúng hợp đồng JDBC.
- `Connection.close()` từ pooled datasource thường trả một **kết nối logic** về pool, không chắc đóng socket vật lý.
- Khi `autoCommit=false`, các câu SQL trên cùng connection tham gia transaction cho đến khi commit/rollback (theo DBMS).
- Chỉ phục hồi `autoCommit` **sau khi transaction đã kết thúc**. Nếu `rollback()` thất bại, không tự gọi `setAutoCommit(true)` vì có thể làm commit một transaction chưa rõ trạng thái.
- Nếu `commit()` báo lỗi mạng, trạng thái thực tại server có thể **không xác định**; rollback sau đó là nỗ lực cleanup, không chứng minh chưa có commit.
- Không giữ connection trong lúc chờ HTTP, gọi cổng thanh toán hoặc tương tác dài với người dùng; điều đó kéo dài thời gian giữ khóa và chiếm pool.

## 5. Chọn kiểu tiền: `BigDecimal` thay vì `double`

Không dùng `double` cho số dư hoặc số tiền cần chính xác theo đơn vị nhỏ nhất của đồng tiền:

```java
// Sai về mô hình tiền chính xác:
double amount = 0.1 + 0.2;
// Có thể thành 0.30000000000000004 trong binary floating point.
```

Sử dụng:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal amount = new BigDecimal("125.50");
BigDecimal normalized = amount.setScale(
        2, RoundingMode.UNNECESSARY);

if (normalized.signum() <= 0) {
    throw new IllegalArgumentException(
            "Transfer amount must be positive");
}
```

- Tạo `BigDecimal` từ **chuỗi decimal** hoặc số nguyên đơn vị nhỏ nhất, không từ literal `double` nếu muốn giữ chính xác giá trị nhập.
- `RoundingMode.UNNECESSARY` từ chối số có **hơn hai chữ số thập phân mang thông tin** thay vì tự làm tròn tiền. Ví dụ `"1.005"` phải bị từ chối khi hợp đồng chỉ nhận cent.
- `DECIMAL(19,2)` ở database phải phù hợp với Java; giới hạn precision/range cần được kiểm tra.
- `BigDecimal.compareTo()` dùng cho so sánh **giá trị số**. `BigDecimal.equals()` còn so cả `scale` nên `1.0` và `1.00` có thể không `equals`.
- Nếu ứng dụng hỗ trợ nhiều currency, phải có **mô hình tiền rõ ràng** gồm currency và scale, không chỉ một `BigDecimal` vô danh.
- Không tự đổi tiền giữa hai currency. Chuyển đổi ngoại tệ cần tỷ giá, phí, làm tròn, sổ cái và nghiệp vụ khác.

Trong ví dụ, hai tài khoản và lệnh đều dùng `USD` để giữ quy tắc hai chữ số thập phân rõ ràng.

## 6. Khóa hai tài khoản theo thứ tự cố định

Nếu hai request diễn ra đồng thời:

```text
Request R1: chuyển 101 → 202
Request R2: chuyển 202 → 101
```

Một triển khai khóa tài khoản **theo thứ tự người gửi trước, người nhận sau** có thể tạo deadlock:

```text
R1 khóa account 101 ─────────┐
                             ├─ R1 cần khóa 202 (R2 giữ)
R2 khóa account 202 ─────────┘
                             └─ R2 cần khóa 101 (R1 giữ)
```

Để giảm nguy cơ này, mọi transfer trong ví dụ chọn **thứ tự khóa cố định theo ID tăng dần**:

```text
firstId  = min(fromId, toId)
secondId = max(fromId, toId)

SELECT ... WHERE id = firstId  FOR UPDATE
SELECT ... WHERE id = secondId FOR UPDATE

Sau đó mới:
  UPDATE source balance - amount
  UPDATE target balance + amount
```

`SELECT ... FOR UPDATE` là cú pháp được nhiều DBMS hỗ trợ với những khác biệt (ví dụ PostgreSQL, MySQL/InnoDB, Oracle); **không phải cú pháp DML giống nhau trên mọi database**, và SQL Server thường dùng cách khóa/hint khác. Cần triển khai và kiểm thử đúng dialect.

**Thứ tự khóa thống nhất giúp giảm một dạng deadlock, không bảo đảm loại bỏ mọi deadlock.** Trigger, index, foreign key, transaction khác hoặc thứ tự truy cập bảng ở nơi khác vẫn có thể gây vòng chờ. Phải có chính sách xử lý lỗi rollback và retry có điều kiện ở tầng gọi.

### Tại sao vẫn dùng `WHERE balance >= ?` nếu đã khóa hàng?

Khóa giúp các transaction hợp tác không cùng đọc/sửa hàng một cách không kiểm soát. Điều kiện `UPDATE accounts SET balance = balance - ? WHERE id = ? AND balance >= ?` còn diễn đạt **bất biến ngay trong thao tác ghi** và trả row count để phát hiện thay đổi không mong muốn.

Khi một chương trình khác không tuân thủ đúng chiến lược khóa, điều kiện cập nhật này vẫn là lớp bảo vệ hữu ích. Đồng thời ràng buộc `CHECK (balance >= 0)` ở DB là lớp bảo vệ bổ sung, không thay thế việc kiểm tra business error ở service.

## 7. Mã Java hoàn chỉnh: `TransferService` quản lý một transaction

Ví dụ dưới đây dùng **Java 8+**, JDBC chuẩn và một `DataSource` đã cấu hình. SQL khóa hàng minh họa theo các DB hỗ trợ `FOR UPDATE`. Mỗi lần gọi `transfer(...)` sẽ:

1. Xác thực dữ liệu đầu vào.
2. Mượn **một** `Connection`.
3. Bắt đầu transaction bằng `setAutoCommit(false)`.
4. Khóa và xác minh hai tài khoản theo thứ tự ID tăng.
5. Ghi `request_key` vào `transfer_log` trong transaction.
6. Trừ tài khoản nguồn, cộng tài khoản đích bằng SQL tham số hóa.
7. `commit()` nếu toàn bộ thao tác thành công; cố `rollback()` nếu có lỗi.
8. Chỉ phục hồi trạng thái kết nối khi transaction đã kết thúc.

```java
import javax.sql.DataSource;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;

public final class TransferService {
    private final DataSource dataSource;

    public TransferService(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(
                dataSource, "dataSource");
    }

    public void transfer(TransferCommand command)
            throws SQLException {

        Objects.requireNonNull(command, "command");
        validate(command);

        // Giá trị được dùng cho cả phép trừ và phép cộng.
        BigDecimal amount =
                command.amount.setScale(2, RoundingMode.UNNECESSARY);

        try (Connection connection = dataSource.getConnection()) {
            boolean originalAutoCommit = connection.getAutoCommit();

            // Ví dụ này sở hữu local transaction; không chạy trong
            // transaction khác do framework/DAO quản lý.
            if (!originalAutoCommit) {
                throw new SQLException(
                        "Expected an unused auto-commit connection");
            }

            connection.setAutoCommit(false);
            boolean transactionEnded = false;
            Throwable primaryFailure = null;

            try {
                // Giữ cùng thứ tự khóa, dù chuyển A->B hay B->A.
                long firstId = Math.min(
                        command.fromAccountId, command.toAccountId);
                long secondId = Math.max(
                        command.fromAccountId, command.toAccountId);

                AccountSnapshot first = loadForUpdate(connection, firstId);
                AccountSnapshot second = loadForUpdate(connection, secondId);

                AccountSnapshot source =
                        first.id == command.fromAccountId ? first : second;
                AccountSnapshot target =
                        first.id == command.toAccountId ? first : second;

                if (!source.currency.equals(command.currency)
                        || !target.currency.equals(command.currency)) {
                    throw new TransferRejectedException(
                            "Source and target currency must match");
                }

                if (source.balance.compareTo(amount) < 0) {
                    throw new TransferRejectedException(
                            "Insufficient funds");
                }

                // Kiểm tra khóa duy nhất trước khi thay đổi số dư;
                // tạo log sau khi đã khóa account theo thứ tự cố định.
                insertTransferLog(connection, command, amount);

                int debited = debit(connection,
                        command.fromAccountId, amount);
                if (debited != 1) {
                    throw new SQLException(
                            "Debit did not update exactly one account");
                }

                int credited = credit(connection,
                        command.toAccountId, amount);
                if (credited != 1) {
                    throw new SQLException(
                            "Credit did not update exactly one account");
                }

                connection.commit();
                transactionEnded = true;

            } catch (SQLException | RuntimeException | Error failure) {
                primaryFailure = failure;

                if (!transactionEnded) {
                    try {
                        connection.rollback();
                        transactionEnded = true;
                    } catch (SQLException rollbackFailure) {
                        failure.addSuppressed(rollbackFailure);
                    }
                }
                throw failure;

            } finally {
                // Chỉ khôi phục sau commit/rollback thành công.
                // Nếu rollback thất bại, connection phải được xử lý
                // như tài nguyên có trạng thái không xác định.
                if (transactionEnded) {
                    try {
                        connection.setAutoCommit(originalAutoCommit);
                    } catch (SQLException resetFailure) {
                        if (primaryFailure != null) {
                            primaryFailure.addSuppressed(resetFailure);
                        } else {
                            throw resetFailure;
                        }
                    }
                }
            }
        }
    }

    private static void validate(TransferCommand c) {
        if (c.fromAccountId == c.toAccountId) {
            throw new IllegalArgumentException(
                    "Source and target must differ");
        }

        if (c.requestKey == null
                || c.requestKey.trim().isEmpty()
                || c.requestKey.length() > 64) {
            throw new IllegalArgumentException(
                    "Invalid request key");
        }

        if (c.currency == null
                || !c.currency.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException(
                    "Invalid currency code");
        }

        if (c.amount == null || c.amount.signum() <= 0) {
            throw new IllegalArgumentException(
                    "Amount must be positive");
        }

        // Từ chối phần thập phân không biểu diễn được
        // bằng DECIMAL(19,2), không tự làm tròn tiền.
        BigDecimal normalized = c.amount.setScale(
                2, RoundingMode.UNNECESSARY);

        if (normalized.precision() > 19) {
            throw new IllegalArgumentException(
                    "Amount exceeds DECIMAL(19,2)");
        }
    }

    private static void insertTransferLog(
            Connection connection,
            TransferCommand c,
            BigDecimal amount) throws SQLException {

        String sql =
                "INSERT INTO transfer_log " +
                "(request_key, source_account_id, target_account_id, " +
                "currency, amount) VALUES (?, ?, ?, ?, ?)";

        try (PreparedStatement statement =
                     connection.prepareStatement(sql)) {
            statement.setString(1, c.requestKey);
            statement.setLong(2, c.fromAccountId);
            statement.setLong(3, c.toAccountId);
            statement.setString(4, c.currency);
            statement.setBigDecimal(5, amount);

            if (statement.executeUpdate() != 1) {
                throw new SQLException(
                        "Expected one transfer log row");
            }
        }
    }

    private static AccountSnapshot loadForUpdate(
            Connection connection, long accountId) throws SQLException {

        String sql =
                "SELECT id, currency, balance " +
                "FROM accounts WHERE id = ? FOR UPDATE";

        try (PreparedStatement statement =
                     connection.prepareStatement(sql)) {

            statement.setLong(1, accountId);

            try (ResultSet rs = statement.executeQuery()) {
                if (!rs.next()) {
                    throw new TransferRejectedException(
                            "Account was not found");
                }

                AccountSnapshot account = new AccountSnapshot(
                        rs.getLong("id"),
                        rs.getString("currency"),
                        rs.getBigDecimal("balance"));

                if (rs.next()) {
                    throw new SQLException(
                            "Primary key unexpectedly returned many rows");
                }
                return account;
            }
        }
    }

    private static int debit(
            Connection connection, long accountId,
            BigDecimal amount) throws SQLException {

        String sql =
                "UPDATE accounts " +
                "SET balance = balance - ?, version = version + 1 " +
                "WHERE id = ? AND balance >= ?";

        try (PreparedStatement statement =
                     connection.prepareStatement(sql)) {
            statement.setBigDecimal(1, amount);
            statement.setLong(2, accountId);
            statement.setBigDecimal(3, amount);
            return statement.executeUpdate();
        }
    }

    private static int credit(
            Connection connection, long accountId,
            BigDecimal amount) throws SQLException {

        String sql =
                "UPDATE accounts " +
                "SET balance = balance + ?, version = version + 1 " +
                "WHERE id = ?";

        try (PreparedStatement statement =
                     connection.prepareStatement(sql)) {
            statement.setBigDecimal(1, amount);
            statement.setLong(2, accountId);
            return statement.executeUpdate();
        }
    }

    public static final class TransferCommand {
        public final String requestKey;
        public final long fromAccountId;
        public final long toAccountId;
        public final String currency;
        public final BigDecimal amount;

        public TransferCommand(
                String requestKey, long fromAccountId,
                long toAccountId, String currency,
                BigDecimal amount) {
            this.requestKey = requestKey;
            this.fromAccountId = fromAccountId;
            this.toAccountId = toAccountId;
            this.currency = currency;
            this.amount = amount;
        }
    }

    private static final class AccountSnapshot {
        private final long id;
        private final String currency;
        private final BigDecimal balance;

        private AccountSnapshot(
                long id, String currency, BigDecimal balance) {
            this.id = id;
            this.currency = currency;
            this.balance = balance;
        }
    }

    public static final class TransferRejectedException
            extends RuntimeException {

        public TransferRejectedException(String message) {
            super(message);
        }
    }
}
```

**Tại sao trả `void` thay vì báo thành công khi gặp mọi ngoại lệ?** Ví dụ chỉ trả bình thường sau `commit()` thành công **và thao tác dọn trạng thái connection không báo lỗi**. Nếu phương thức ném `SQLException` lúc `commit()`, caller **không được mặc định** rằng giao dịch thất bại ở server. Một API production nên biểu diễn rõ `COMMITTED`, `REJECTED` và `UNKNOWN / RECONCILIATION_REQUIRED` khi có đủ cơ chế xác minh.

### Các điều kiện để đoạn mã có ý nghĩa

- `Connection` được lấy từ một `DataSource` có thể thao tác transaction trên database thật; service **tự sở hữu local transaction**. Không dùng nguyên phương thức này bên trong `@Transactional` của Spring nếu Spring đang sở hữu kết nối/giao dịch.
- `SELECT ... FOR UPDATE` phải được database/driver hỗ trợ. Với SQL Server hoặc database khác, dùng chiến lược khóa tương đương đã được xác minh.
- `loadForUpdate()` lấy **khóa trên cả hai hàng** theo thứ tự số ID tăng, trước khi chạy hai lệnh `UPDATE`.
- Hai lệnh `UPDATE` sử dụng **cùng `BigDecimal`** đã chuẩn hóa; không có phép cộng/trừ bằng `double` trong Java.
- Bảng `transfer_log` có khóa chính `request_key`, đủ để ngăn hai transfer với cùng key cùng commit thành công khi database cưỡng chế unique đúng trong transaction. **Việc xử lý lệnh trùng để trả kết quả idempotent vẫn cần một nhánh riêng** (phần 10).
- `TransferRejectedException` thuộc loại unchecked; nhánh `catch` cố rollback trước khi ném lại. Có thể thay bằng kiểu kết quả nghiệp vụ khác, miễn không vô tình commit thay đổi một phần.
- `RoundingMode.UNNECESSARY` có thể ném `ArithmeticException` ở bước validate; nó được thực hiện **trước khi mượn connection**, nên không làm bẩn transaction.
- `requestKey` cần được caller giữ ổn định qua retry **của cùng yêu cầu nghiệp vụ**; không tạo UUID mới mỗi lần timeout.
- Các công việc side effect ngoài DB như email, phát message hoặc gọi dịch vụ thanh toán **không nằm trong transaction JDBC** chỉ vì phương thức Java bao quanh chúng.

### Một điều kiện quan trọng về lỗi cleanup

Nếu `commit()` đã thành công nhưng `setAutoCommit(originalAutoCommit)` hoặc `close()` ném lỗi, caller vẫn có thể nhận `SQLException`. Do đó **“phương thức ném lỗi” không có nghĩa “tiền chưa chuyển”**. Cơ chế reconciliation dựa trên `request_key` quan trọng ngay cả khi mã Java có `try-with-resources` đúng.

Nếu rollback thất bại, ví dụ tránh reset auto-commit nhưng vẫn để `try-with-resources` gọi `close()`. Pool production phải có chính sách **invalidate/evict kết nối nghi vấn** theo implementation; không thể chỉ dựa vào `close()` để chứng minh socket đã bị loại bỏ.

## 8. Chạy ví dụ và kiểm tra kết quả

Một đoạn gọi:

```java
import java.math.BigDecimal;

TransferService service = new TransferService(dataSource);

TransferService.TransferCommand command =
        new TransferService.TransferCommand(
                "transfer-demo-001", 101L, 202L,
                "USD", new BigDecimal("125.50"));

service.transfer(command);
```

`dataSource` do ứng dụng khởi tạo bằng cấu hình DB và pool đã được phép. Sau khi `transfer(...)` trả về bình thường, dùng SQL đọc lại:

```sql
SELECT id, currency, balance, version
FROM accounts
WHERE id IN (101, 202)
ORDER BY id;

SELECT request_key, source_account_id,
       target_account_id, currency, amount
FROM transfer_log
WHERE request_key = 'transfer-demo-001';
```

Kết quả mong đợi:

| Tài khoản | Currency | Balance sau transfer | Version sau transfer |
| --- | --- | ---: | ---: |
| 101 | USD | 874.50 | 1 |
| 202 | USD | 425.50 | 1 |

`transfer_log` có đúng **một hàng** với mã `transfer-demo-001`, nguồn `101`, đích `202`, `amount=125.50`.

Tổng số dư vẫn bằng `1 300.00`. Thực hiện đọc kiểm chứng bằng một connection mới sau transaction để chắc chắn chỉ quan sát dữ liệu **đã commit**, không phải dữ liệu chưa commit trên connection cũ.

**Quan trọng với việc chạy lại bài học:** `request_key` là duy nhất. Gọi lại đúng mã `transfer-demo-001` không được thực hiện thêm một lần chuyển; trong implementation hiện tại, thao tác sẽ gặp lỗi vi phạm unique key và rollback. Để chạy lại kịch bản thành công, hãy reset fixture trên DB thử nghiệm hoặc dùng một request key mới **cho một lần chuyển mới có chủ đích**. Không tự đổi key khi thử lại một request thật đã gửi.

## 9. Bốn tình huống rollback quan trọng

### 9.1. Tài khoản nguồn không đủ tiền

Tài khoản A có `100.00` nhưng yêu cầu chuyển `125.50`:

1. Service khóa A/B theo thứ tự cố định rồi kiểm tra `source.balance < amount`.
2. `TransferRejectedException` được ném trước khi chèn log hoặc cập nhật số dư.
3. Service gọi `rollback()` để giải phóng khóa và dọn transaction.
4. **Số dư hai tài khoản và `transfer_log` phải giữ nguyên**.

Việc ứng dụng thông báo “insufficient funds” chỉ đáng tin khi transaction đã dọn sạch những thay đổi tạm thời hoặc đã xác nhận kết quả rollback. Nếu rollback thất bại, cần ghi lỗi dọn dẹp và xử lý connection theo chính sách vận hành.

### 9.2. Tài khoản nhận không tồn tại

Nếu `targetAccountId` không có hàng:

- `loadForUpdate()` của tài khoản đích phát hiện thiếu hàng trước khi ghi transfer log.
- Service rollback.
- Không được trừ A hay commit bản ghi transfer.

Việc bảng transfer có foreign key tới cả hai account là **lớp phòng vệ của database**, không thay thế thông báo nghiệp vụ dễ hiểu. Khi có ứng dụng khác đồng thời xóa hoặc sửa tài khoản, ràng buộc và khóa của database vẫn phải bảo vệ tính toàn vẹn; không phụ thuộc chỉ vào lần kiểm tra tồn tại trong Java.

### 9.3. Một câu UPDATE giữa transaction thất bại

Giả sử debit A đã chạy và cập nhật số dư trong transaction, nhưng câu credit B thất bại do một constraint/trigger DB hoặc lỗi SQL có chủ đích trong môi trường test:

```text
BEGIN
  INSERT transfer_log                (chưa commit)
  UPDATE A balance = balance - 125.50
  UPDATE B ...                       → SQLException
ROLLBACK
```

Sau rollback:

- A quay lại số dư ban đầu.
- B không nhận tiền.
- `transfer_log` không có bản ghi đã commit cho request đó.

Đây là **bài thử xác nhận tính nguyên tử** quan trọng nhất. Không được giả lập lỗi bằng cách chỉ đặt một câu `if` **trước khi debit**, vì khi đó test không chứng minh rollback có thể hoàn tác một thay đổi đã thực thi.

Có thể tạo **test-only failure point sau debit** trong một biến thể của service, hoặc cấu hình trigger/constraint trên DB thử nghiệm để từ chối credit. Không thêm logic “cố tình ném lỗi” vào đường chuyển tiền sản phẩm.

### 9.4. Lỗi ngay sau `commit()` hoặc mất kết nối

Trình tự có thể là:

```text
Java application                     DB server
----------------                     ---------
UPDATE A/B thành công    ─────────► Thay đổi trong transaction
COMMIT                   ─────────► Commit hoàn tất
                         ◄── X ─── Mạng bị ngắt trước khi phản hồi
Java nhận SQLException
```

Tại thời điểm này, ứng dụng **không biết chắc** server đã commit hay chưa. Kể cả nếu `rollback()` sau đó thành công trên client, nó không chứng minh transaction trước đó chưa commit. Vì thế:

- Không tạo `request_key` mới rồi gọi lại `transfer(...)` ngay.
- Tra cứu trạng thái đã commit qua một connection mới với `request_key` ổn định.
- Nếu thấy bản ghi tương ứng **và dữ liệu/transaction contract cho phép kết luận nó được ghi nguyên tử**, có thể xác nhận đã áp dụng.
- Nếu không thấy, vẫn cần chú ý đọc từ **primary/nguồn có tính nhất quán phù hợp**, không đọc replica đang chậm đồng bộ rồi tuyên bố chưa chuyển.
- Nếu chưa thể xác định, báo trạng thái **đang đối soát/không rõ kết quả**, không trả thành công hay thất bại giả.

## 10. Idempotency: khóa chính chưa phải toàn bộ giải pháp

Trong API thực tế, client có thể gửi cùng yêu cầu nhiều lần vì mất phản hồi, retry hoặc double-click. Nếu mỗi lần đều trừ/cộng tiền, transaction vẫn **nguyên tử trong từng lần**, nhưng nghiệp vụ chuyển tiền có thể bị thực hiện **hai lần**.

### Mã yêu cầu phải có phạm vi và ngữ nghĩa ổn định

Ví dụ:

```text
request_key = "transfer-8c51..."  (do caller tạo một lần)
from        = 101
to          = 202
currency    = USD
amount      = 125.50

Retry: dùng lại CHÍNH request_key và CHÍNH nội dung nghiệp vụ.
```

`request_key` cần duy nhất theo phạm vi đã định. Nếu hệ thống có nhiều tenant hoặc client, có thể thiết kế khóa chính tổng hợp `(tenant_id, request_key)`, đồng thời kiểm tra principal có quyền thao tác với tài khoản nguồn. Ví dụ đơn giản dùng một `request_key` duy nhất trên toàn bảng.

### Tại sao chèn transfer_log trước khi thay đổi số dư?

Bảng `transfer_log` lưu cùng request key trong transaction. Trong ví dụ, service **khóa hai tài khoản theo thứ tự ID trước**, rồi chèn transfer log **trước hai lệnh cập nhật số dư**. Thứ tự này cũng tránh cho các kiểm tra foreign key của lệnh INSERT lấy khóa tham chiếu trước các khóa hàng có thứ tự mà service chủ động thiết lập; hành vi khóa ngoại cụ thể vẫn phụ thuộc DBMS. Nếu hai transaction cùng dùng key:

1. Chỉ một transaction được phép **commit** bản ghi `request_key` đó theo ràng buộc unique.
2. Transaction khác có thể phải chờ khóa/constraint, nhận duplicate key error hoặc bị rollback do xung đột.
3. Không có chuyện cả hai transaction cùng commit thành công với cùng khóa chính **nếu ràng buộc được database cưỡng chế đúng**.

Tuy nhiên, `SQLException` duplicate key xảy ra **không phải một response idempotent có kiểm chứng**. Bạn cần đọc record đã commit sau khi rollback giao dịch lỗi, rồi so sánh đầy đủ:

| Dữ liệu | Phải khớp với lệnh đang retry? |
| --- | --- |
| `request_key` | Có |
| `source_account_id` | Có |
| `target_account_id` | Có |
| `currency` | Có |
| `amount` theo giá trị decimal đã chuẩn hóa | Có |
| Tenant/principal/ủy quyền | Phải tiếp tục được kiểm tra theo bảo mật ứng dụng |

Nếu key đã tồn tại nhưng nội dung khác, phải trả **idempotency conflict**, không tự coi là một lần chuyển hợp lệ đã được thực hiện.

### Quy trình xác minh khi duplicate hoặc commit unknown

```text
Lệnh transfer(request_key, from, to, amount)
             │
             ▼
     Thử transaction ghi
         /           \
      Commit       Duplicate/timeout/lỗi
        │                 │
        ▼                 ▼
  Xác nhận OK      Rollback/cleanup nếu cần
                          │
                          ▼
               Đọc transfer_log trên nguồn
               có tính nhất quán phù hợp
                    /          \
             Có bản ghi       Chưa thấy
                │               │
          So sánh payload    Đánh giá tình trạng
            /      \         commit/replication
         Trùng     Khác          │
          │         │            ▼
    ALREADY_APPLIED CONFLICT  RETRY có điều kiện
                              hoặc NEED_RECONCILIATION
```

**Cảnh báo:** Không bắt duplicate key rồi chạy `SELECT` ngay trên cùng transaction đã lỗi mà mặc định nó vẫn dùng được. Ví dụ PostgreSQL có thể đặt transaction vào trạng thái **aborted** sau lỗi; cần rollback trước rồi mới bắt đầu đường đọc xác minh. Các quy tắc và mã duplicate-key khác nhau giữa driver/database.

Một bảng `transfer_log` ghi mỗi chuyển tiền đã hoàn tất cho phép kiểm chứng lại trạng thái nếu nó là **nguồn có thẩm quyền**, nhưng production cần cân nhắc crash giữa các dịch vụ, replication lag, tính bất biến của log, retention và quyền sửa/xóa. Không tự tuyên bố “exactly once toàn hệ thống” chỉ vì có một unique key.

## 11. Hai yêu cầu đồng thời và khóa giao dịch

### Ví dụ 1 — Hai request cùng trừ một tài khoản

Giả sử A có `100.00`. Hai giao dịch độc lập cùng muốn chuyển `80.00` từ A tới hai người nhận khác nhau:

```text
Tx1: A → B, amount 80.00
Tx2: A → C, amount 80.00
```

Nếu chỉ dùng `SELECT balance` bình thường rồi tính `newBalance` trong Java, cả hai có thể cùng thấy `100.00` và cùng ghi lại một số dư không đúng (lost update hoặc double spending tùy triển khai). Trong bài, hai cơ chế phối hợp:

- `SELECT ... FOR UPDATE` khóa hàng nguồn theo cách database hỗ trợ, nên transaction thứ hai có thể phải chờ.
- `UPDATE ... WHERE balance >= ?` kiểm tra điều kiện tại thời điểm ghi, không tự dựa vào giá trị balance đã đọc từ trước.

Trên database hỗ trợ row locking đúng như mong đợi, chỉ một giao dịch có thể trừ `80.00` thành công; giao dịch còn lại sẽ thấy thiếu tiền hoặc gặp lỗi transaction có thể phân loại. **Không được yêu cầu cả hai đều thành công nếu tổng tiền nguồn không đủ.**

### Ví dụ 2 — Hai request chuyển ngược chiều

Tx1 chuyển A → B và Tx2 chuyển B → A. Cả hai khóa **ID nhỏ trước rồi ID lớn**, không khóa người gửi trước. Việc dùng cùng thứ tự giúp giảm vòng chờ đơn giản giữa hai account.

Tuy nhiên, nếu một DAO khác cập nhật thêm bảng hoặc sử dụng thứ tự khóa ngược, vẫn có thể deadlock. Khi phát sinh deadlock/serialization failure:

1. Xác định transaction đã bị rollback theo hợp đồng DB và driver.
2. Không retry riêng câu `UPDATE` cuối trong transaction đã bị lỗi.
3. Nếu nghiệp vụ an toàn để retry, bắt đầu **transaction mới**, dùng **cùng request key**, đọc lại số dư và kiểm tra điều kiện.
4. Giới hạn số lần thử, thêm backoff/jitter và tôn trọng request deadline.
5. Không tự retry khi `commit()` có kết quả không rõ.

### Isolation có cần `SERIALIZABLE` không?

Không nhất thiết. Với một chuyển tiền hai hàng, khóa hàng có thứ tự và câu `UPDATE` có điều kiện thường đã bảo vệ những bất biến đã nêu khi database thực thi đúng contract. Các mức cô lập khác nhau có thể thay đổi kiểu blocking, snapshot và ngoại lệ; **không nâng isolation lên mức cao nhất theo phản xạ** vì có thể tăng contention và rollback.

Nếu nghiệp vụ thêm ràng buộc nhiều hàng như “tổng số dư trong một nhóm phải vượt ngưỡng”, chỉ khóa hai account chưa chắc đủ; cần xem xét thêm phạm vi khóa/isolation và test write skew. Quyết định phải dựa trên **bất biến cần bảo vệ**, không chỉ tên mức isolation.

## 12. Bảng các lỗi và hành động đúng

| Lỗi hoặc kết quả | Phản ứng tại transaction | Phản ứng tại API/nghiệp vụ |
| --- | --- | --- |
| Không đủ tiền | Rollback phần đã thực hiện | Từ chối hợp lệ, không retry tự động |
| Tài khoản không tồn tại | Rollback | Thông báo account không hợp lệ, không lộ dữ liệu tenant khác |
| Hai account khác currency | Rollback | Từ chối; không âm thầm chuyển đổi ngoại tệ |
| `debit.executeUpdate() == 0` | Rollback | Kiểm tra không đủ tiền/xung đột; không báo success |
| `credit.executeUpdate() != 1` | Rollback | Báo lỗi, đối chiếu account và schema |
| Duplicate `request_key` | Rollback transaction lỗi | Đọc log đã commit và so payload; trả already-applied hoặc conflict |
| Deadlock/serialization rollback | Rollback/cleanup theo DB | Retry **toàn transaction** nếu an toàn và còn deadline |
| Query timeout giữa thao tác ghi | Cố rollback nếu sở hữu transaction | Không mặc định server chưa ghi; xác minh transaction |
| Pool borrow timeout **trước SQL** | Chưa mở transaction nghiệp vụ | Có thể retry có giới hạn nếu còn deadline |
| Lỗi trong `commit()` | Cố cleanup nhưng trạng thái có thể unknown | Đối soát, không retry mù quáng |
| Rollback thất bại | Connection nghi vấn | Ghi lỗi phụ, invalidate/evict theo pool, không reset auto-commit mù quáng |
| `close()` hoặc reset trạng thái lỗi sau commit | Ghi rõ transaction đã commit nếu biết | Không chuyển lại tiền chỉ vì lỗi cleanup |

Không nên phân loại chỉ dựa vào chuỗi thông điệp `SQLException.getMessage()`. Ưu tiên `getSQLState()`, `getErrorCode()`, lớp exception, `getNextException()` và ngữ cảnh **đang ở bước nào**. Vendor code cho duplicate key, deadlock, lock wait hoặc serialization khác nhau theo hệ quản trị.

**Đường ngoại lệ không thay thế hợp đồng return.** Một service sản phẩm nên phân biệt business rejection, conflict, lỗi tạm thời và kết quả chưa rõ, để tầng API không vô tình phản hồi `500` rồi client thay key và gửi giao dịch mới.

## 13. Kiểm thử tích hợp: phải quan sát được rollback thật

Unit test với mock `PreparedStatement` có thể kiểm tra số lần gọi setter và method, nhưng **không chứng minh** database đã rollback hai câu `UPDATE` hoặc khóa đúng khi chạy đồng thời.

Bộ kiểm thử quan trọng nhất phải chạy trên **database thật của môi trường test** với transaction engine, constraint và isolation tương ứng. Các test có thể dùng JUnit 5, test database/schema riêng và fixture reset trước mỗi kịch bản.

### Ma trận kiểm thử tối thiểu

| Test case | Fixture | Hành vi mong đợi |
| --- | --- | --- |
| Happy path | A=1000.00, B=300.00 | A=874.50, B=425.50, một `transfer_log` |
| Không đủ tiền | A=100.00, B=300.00, amount=125.50 | Hai số dư giữ nguyên, không có transfer log |
| Không có người nhận | A tồn tại, B thiếu | Không debit A, không có log commit |
| Nguồn và đích giống nhau | `fromId == toId` | Bị từ chối trước khi mượn connection |
| Currency khác nhau | A=USD, B=EUR | Rollback, không thay đổi số dư |
| Amount bằng 0 hoặc âm | `0.00`, `-1.00` | Bị từ chối trước SQL |
| Amount có phần cent lẻ ngoài hợp đồng | `1.005` | Bị từ chối, không làm tròn âm thầm |
| Lỗi **sau debit** | Inject SQL exception lúc credit trên DB test | Rollback cả debit, không có log |
| Duplicate request key cùng payload | Chạy lệnh đã commit rồi gọi lại | Không chuyển tiền lần hai; API xử lý idempotency |
| Duplicate key khác payload | Trùng key, khác amount/to | Trả conflict, không sửa số dư |
| Hai request cùng trừ A | A chỉ đủ một giao dịch | Không vượt quá số dư hoặc double-spend |
| Hai request chuyển ngược | A→B và B→A chạy đồng thời | Bảo toàn tổng, xử lý lock/deadlock nếu có |
| Serialization/deadlock | Hai connection tạo xung đột | Transaction lỗi được dọn đúng; retry có giới hạn |
| Lỗi commit không rõ | Fault injection trên môi trường riêng | Không replay tiền, có đối soát |
| Connection pool trả lại | Borrow/close nhiều lần | Không rò connection, trạng thái transaction được phục hồi |

Một số kịch bản (đặc biệt commit unknown) yêu cầu **fault injection** hoặc proxy DB được phép điều khiển; không gây mất kết nối cố ý trên production.

### Ví dụ JUnit 5 cho happy path

Giả định test fixture đã khởi tạo A=1000.00, B=300.00 và chưa có `request_key` đang thử. Test dùng `DataSource` thật, và helper `readBalance(...)` để kiểm tra sau commit.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;

public final class TransferServiceIT {
    // Khởi tạo bằng test framework/config của dự án.
    private DataSource dataSource;

    @Test
    void transfersAtomically() throws SQLException {
        TransferService service = new TransferService(dataSource);

        service.transfer(new TransferService.TransferCommand(
                "it-transfer-001", 101L, 202L,
                "USD", new BigDecimal("125.50")));

        assertEquals(
                0,
                readBalance(101L).compareTo(
                        new BigDecimal("874.50")));
        assertEquals(
                0,
                readBalance(202L).compareTo(
                        new BigDecimal("425.50")));
    }

    private BigDecimal readBalance(long id) throws SQLException {
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(
                     "SELECT balance FROM accounts WHERE id = ?")) {

            statement.setLong(1, id);

            try (ResultSet rs = statement.executeQuery()) {
                if (!rs.next()) {
                    throw new AssertionError("Account is missing");
                }
                BigDecimal balance = rs.getBigDecimal(1);
                if (rs.next()) {
                    throw new AssertionError("Duplicate account");
                }
                return balance;
            }
        }
    }
}
```

**Đây là khung kiểm thử**, không phải class chạy độc lập nếu `dataSource` chưa được inject/khởi tạo hoặc fixture chưa được reset. Trong dự án thật, dùng `@BeforeEach`, extension/test container hoặc một test fixture được kiểm soát để tạo trạng thái ban đầu và dọn dữ liệu. Nên kiểm tra thêm `transfer_log` bằng `SELECT COUNT(*)` và tổng số dư.

Nếu test được bọc trong một transaction tự động rollback của test framework, phép kiểm tra có thể đọc **dữ liệu chưa commit cùng scope** và che lỗi. Để xác minh `TransferService` tự commit đúng ranh giới, thực hiện đọc hậu điều kiện từ một connection riêng **sau khi service kết thúc**.

## 14. Kiểm thử lỗi sau debit: xác minh tính nguyên tử, không chỉ xử lý exception

Để chứng minh rollback, cần một lỗi xảy ra **sau khi câu debit đã thực thi**, trước khi transaction commit. Cách dạy học an toàn là dùng database test và một helper test-specific có kiểm soát.

Luồng test:

```text
1. Seed accounts: A=1000.00, B=300.00
2. BEGIN TRANSACTION trên Connection C
3. UPDATE A SET balance = balance - 125.50
4. Xác nhận debit ảnh hưởng đúng một hàng
5. Cố ý gây SQLException (fault injection sau debit)
6. ROLLBACK trên chính Connection C
7. Lấy Connection D khác, SELECT lại A và B
8. Assert A=1000.00, B=300.00
```

Đoạn mã minh họa phần lõi, **chỉ dùng trong test**:

```java
// Test helper, không phải đường chuyển tiền sản phẩm.
Connection c = dataSource.getConnection();
try {
    c.setAutoCommit(false);

    try (PreparedStatement debit = c.prepareStatement(
            "UPDATE accounts SET balance = balance - ? WHERE id = ?")) {
        debit.setBigDecimal(1, new BigDecimal("125.50"));
        debit.setLong(2, 101L);
        if (debit.executeUpdate() != 1) {
            throw new AssertionError("Debit test setup failed");
        }
    }

    // Chủ động mô phỏng lỗi sau debit nhưng trước credit.
    throw new SQLException("Injected failure after debit");

} catch (SQLException failure) {
    c.rollback();
    // Test sau đó đọc lại A/B trên connection mới.
} finally {
    c.close();
}
```

Đây là phép thử rút gọn về **rollback của JDBC**. Test thực tế phải quản lý rollback failure và trạng thái auto-commit một cách chặt chẽ, dùng `try-with-resources` phù hợp và không bỏ qua lỗi setup hay lỗi cleanup. Để kiểm tra **chính `TransferService`**, nên thay vì tự tái hiện SQL, dùng fault-injection tại lớp repository/test database khiến bước **credit** thất bại sau debit; sau đó so sánh số dư và log từ connection mới.

Nếu chỉ kiểm tra `assertThrows(SQLException.class, ...)` mà không truy vấn lại số dư, bạn chưa chứng minh được tính nguyên tử.

## 15. Kiểm thử đồng thời bằng hai connection

Các tình huống cạnh tranh cần **hai connection vật lý/logical độc lập đang dùng đồng thời**, mỗi thread sở hữu riêng. Không chia sẻ một `Connection` giữa hai thread như thể JDBC chuẩn đảm bảo mọi thao tác an toàn luồng.

Ví dụ điều phối:

```text
Worker T1                         Worker T2
---------                         ---------
DataSource.getConnection()        DataSource.getConnection()
setAutoCommit(false)              setAutoCommit(false)

SELECT account 101 FOR UPDATE     SELECT account 101 FOR UPDATE
   giữ khóa / chờ                   chờ hoặc bị từ chối theo DB

UPDATE ...                        UPDATE ... sau khi được phép
COMMIT hoặc ROLLBACK              COMMIT hoặc ROLLBACK
```

Dùng `CountDownLatch` hoặc `CyclicBarrier` để đưa hai transaction tới những thời điểm rõ ràng, và đặt timeout cho test để tránh treo CI vô hạn. Cần kiểm tra:

- **Không có số dư âm** sau hai yêu cầu cạnh tranh.
- Tổng số dư trong nhóm hai/ba tài khoản không đổi nếu không có phí.
- Không có hai bản ghi transfer cùng `request_key`.
- Nếu một giao dịch là nạn nhân deadlock, các thay đổi của nó không được commit một phần.
- Sau khi các transaction kết thúc, pool trả lại đủ connection và không còn khóa bị giữ.
- SQLState/vendor code và hành vi blocking phù hợp **driver/database thực tế**.

**Không khóa cứng “transaction T1 phải thắng”**. Database có thể chọn nạn nhân deadlock khác nhau, hoặc điều phối theo thứ tự khác, nhưng các bất biến nghiệp vụ vẫn phải giữ.

Một transaction `SERIALIZABLE` có thể ném serialization failure chứ không trả kết quả “thiếu tiền” theo cùng cách `READ_COMMITTED`; test phải xác minh **tính đúng**, sau đó phân loại các kết quả lỗi hợp lệ theo môi trường.

## 16. Truy vấn đối soát và phát hiện bất thường

Không nên chỉ xem thông báo “transfer succeeded” trên API mà bỏ qua hậu điều kiện dữ liệu. Với dữ liệu thử:

```sql
SELECT
    SUM(balance) AS total_balance
FROM accounts
WHERE id IN (101, 202);

SELECT COUNT(*) AS transfer_count
FROM transfer_log
WHERE request_key = ?;
```

Câu thứ hai phải dùng `PreparedStatement` và bind `request_key` khi chạy trong ứng dụng; placeholder ở đây nhấn mạnh yêu cầu SQL tham số hóa.

Sau chuyển thành công, giá trị mong đợi:

```text
total_balance = 1300.00
transfer_count = 1
```

**Cảnh báo về đối soát tổng:** tổng của hai tài khoản chỉ là một bất biến cục bộ trong ví dụ không có phí, lãi, ngoại tệ hay thao tác từ bên ngoài. Với dữ liệu production có nhiều chuyển tiền đồng thời, đọc tổng ở hai thời điểm không có cùng snapshot có thể tạo kết quả khó diễn giải. Nên đối soát bằng snapshot nhất quán, sổ cái và nguồn sự kiện có thẩm quyền, không chỉ so tổng thô của vài hàng trong hệ thống đang hoạt động.

### Vì sao hệ thống tài chính thường dùng sổ cái kép?

Một bảng `balance` cho biết trạng thái hiện tại nhưng không tự chứng minh mọi thay đổi có nguồn gốc hợp lệ. Mô hình **double-entry ledger** ghi mỗi giao dịch qua hai bút toán cân bằng (debit và credit) với mã giao dịch chung, bất biến và khả năng đối soát lịch sử.

Trong sản phẩm thật, có thể coi `accounts.balance` là số dư tính sẵn hoặc materialized state, còn sổ cái là nguồn có thẩm quyền. Mọi ghi sổ cái và cập nhật số dư liên quan vẫn cần transaction, ràng buộc và cơ chế đối soát thích hợp. Bài này sử dụng `transfer_log` để giới thiệu việc lưu một event trong transaction, **không tuyên bố nó là sổ cái kế toán đầy đủ**.

## 17. Khi tích hợp Spring hoặc một transaction manager

Ví dụ `TransferService` ở phần 7 tự gọi `setAutoCommit(false)`, `commit()` và `rollback()`. Nó phù hợp khi **service thực sự sở hữu `Connection` và local JDBC transaction**. Nếu ứng dụng dùng Spring `@Transactional`, thiết kế khác:

```java
// Ví dụ ý tưởng cho Spring JdbcTemplate:
@Transactional
public void transfer(TransferCommand command) {
    // repository.insertTransferLog(...)
    // repository.lockAccountsInFixedOrder(...)
    // repository.debit(...)
    // repository.credit(...)
    // Không tự gọi Connection.commit()/rollback() tại đây.
}
```

Khi dùng Spring, phải chắc chắn mọi repository tham gia **cùng transaction manager và cùng target `DataSource`**, thường qua `JdbcTemplate` hoặc `DataSourceUtils`. Tự gọi `dataSource.getConnection()` trên raw pool trong một DAO có thể tạo **connection ngoài transaction Spring**; kết quả là debit/credit có thể commit độc lập dù service mang `@Transactional`.

Lưu ý các đặc điểm của Spring:

- Phương thức transactional phải được gọi qua transaction proxy/cơ chế tương ứng; self-invocation thông thường có thể bỏ qua interceptor.
- `DataAccessException` là unchecked và thường kích hoạt rollback mặc định; checked `SQLException` cần quy tắc `rollbackFor` nếu thoát ra khỏi phương thức.
- `REQUIRES_NEW` có thể tạo transaction độc lập; nó **không phù hợp** cho riêng bước credit nếu mục tiêu là debit/credit cùng nguyên tử.
- Transaction local trên một `DataSource` không bao phủ hai database khác nhau hoặc HTTP/email bên ngoài.

**Chọn một bên sở hữu transaction**, không vừa để Spring điều phối vừa tự commit/close connection đang được Spring gắn với transaction.

## 18. Hiệu năng và vận hành

Một chuyển tiền thành công có nhiều thao tác SQL. Tối ưu hiệu năng **không được đánh đổi tính nguyên tử**:

| Chỉ số | Mục đích |
| --- | --- |
| `jdbc.acquire.duration` | Biết thời gian chờ mượn connection từ pool |
| `transfer.transaction.duration` | Đo thời gian giữ transaction và khóa |
| `jdbc.statement.duration` theo operation | Biết lock, debit, credit, insert log nào chậm |
| Pool `active/idle/pending` | Phát hiện connection pool bão hòa |
| Deadlock/serialization failure rate | Theo dõi tranh chấp và chiến lược retry |
| `commit()/rollback()` failures | Phát hiện transaction outcome không rõ |
| Duplicate request key rate | Đo yêu cầu lặp; phân biệt retry hợp lệ với xung đột |
| Balance invariant/reconciliation alerts | Phát hiện chênh lệch cần điều tra |

Nên giữ transaction **ngắn**, không gọi dịch vụ ngoài DB khi đang giữ hai hàng khóa. Các truy vấn `WHERE id = ?` phải tận dụng khóa chính; không quét toàn bảng để khóa hàng. Tăng kích thước pool không giải quyết được deadlock hoặc SQL chậm gây giữ connection lâu.

**Timeout có nhiều tầng:** pool borrow timeout, connect/login timeout, query timeout, network timeout và request deadline. Chúng không cùng phạm vi. `Statement.setQueryTimeout(seconds)` không bảo đảm toàn bộ transfer kết thúc đúng deadline và `cancel()` không chứng minh rollback. Nếu request có deadline, chia ngân sách trước mỗi bước và vẫn thực hiện cleanup transaction khi hết hạn.

### Không log bí mật hoặc dữ liệu tài chính nhạy cảm

Nên log tên operation cố định, phase (`acquire`, `lock`, `debit`, `credit`, `commit`, `rollback`), trace ID, SQLState/vendor code và kết quả xử lý. Không log mật khẩu, JDBC URL chứa secret, raw SQL parameters, thông tin người sở hữu tài khoản hay số dư chi tiết vào hệ thống không được phân quyền.

Mã `request_key` có thể dùng để đối soát nhưng không nên làm **metric label** vì cardinality cao; chỉ đưa nó vào log nội bộ được phép và có chính sách bảo vệ.

## 19. Checklist trước khi hoàn thành bài thực hành

- [ ] Tài khoản nguồn và đích khác nhau, tồn tại và cùng đồng tiền.
- [ ] Số tiền dùng `BigDecimal` với scale/precision hợp lệ, không dùng `double`.
- [ ] Cả hai `UPDATE` và `transfer_log` dùng **cùng `Connection`, cùng transaction**.
- [ ] `setAutoCommit(false)` trước khi chạy bất kỳ SQL ghi nào của transaction.
- [ ] Khóa hai hàng theo thứ tự nhất quán và kiểm tra kết quả trên DB/driver thật.
- [ ] Lệnh debit có điều kiện `balance >= amount` và kiểm tra update count bằng `1`.
- [ ] Lệnh credit kiểm tra update count bằng `1`, không báo thành công khi thiếu tài khoản.
- [ ] `commit()` chỉ xảy ra sau khi mọi bước thành công.
- [ ] Có `rollback()` khi lỗi; không reset auto-commit nếu rollback thất bại.
- [ ] Có cơ chế xử lý connection nghi vấn và commit outcome unknown.
- [ ] `request_key` được dùng ổn định qua retry, có constraint unique và quy trình đọc log đối soát.
- [ ] Dữ liệu đầu vào được xác thực/ủy quyền, tất cả SQL dùng `PreparedStatement`.
- [ ] Unit test và integration test phủ happy path, insufficient funds, lỗi giữa debit/credit, duplicate key và concurrency.
- [ ] Đọc kết quả từ connection riêng sau transaction để xác nhận **dữ liệu commit**.
- [ ] Không chạy test phá khóa/network trên database production.

## 20. Bài tập mở rộng

### Bài 1 — Chuyển tiền có phí

Thêm một tài khoản thu phí và phí cố định. Khi chuyển `125.50` với phí `1.00`, xác định rõ **người gửi bị trừ tổng 126.50 hay người nhận chỉ được nhận 124.50**, sau đó viết ba cập nhật cân bằng theo chính sách chọn. Tất cả ghi phải trong **một transaction**. Kiểm tra tổng ở phạm vi gồm **cả tài khoản phí**, không chỉ A+B.

### Bài 2 — Tầng API idempotent

Thiết kế API nhận `request_key` do client tạo và áp dụng constraint unique theo tenant. Khi duplicate:

1. Rollback transaction lỗi.
2. Đọc transfer đã commit từ nguồn có tính nhất quán phù hợp.
3. So sánh source, target, currency, amount và tenant.
4. Trả trạng thái already-applied khi giống hệt; trả conflict nếu key bị dùng cho payload khác.
5. Với lỗi commit chưa rõ và dữ liệu chưa xác minh được, trả trạng thái cần đối soát.

Không tạo request key mới chỉ vì có lỗi `SQLException`.

### Bài 3 — Chuyển tiền đồng thời

Tạo hai worker transfer 101→202 và 202→101 bằng hai connection độc lập. So sánh trước/sau khi áp chiến lược khóa theo ID tăng. Ghi thời gian lock wait, lỗi deadlock/serialization, tổng số dư và number of committed transfer log rows.

### Bài 4 — Sổ cái kép

Thiết kế bảng `ledger_entries` có mã transfer, account, signed amount hoặc debit/credit side, currency và thời điểm. Định nghĩa điều kiện tổng signed amount trong một currency bằng `0` cho mỗi transfer. Viết bút toán trong **cùng transaction** với update account; thiết kế truy vấn đối soát theo request key.

### Bài 5 — Timeout và kết quả commit không rõ

Trong môi trường fault injection riêng, ngắt phản hồi khi `commit()` đang diễn ra. Thử đọc `transfer_log` trên primary sau sự cố; giải thích vì sao **không thể** dùng exception của client để xác nhận transaction chưa commit. Viết chính sách retry có idempotency và giới hạn ngân sách thời gian.

### Câu hỏi tự kiểm tra

- Hai `UPDATE` cùng chạy qua một `DataSource` có đủ để đảm bảo nguyên tử không? Vì sao cần cùng `Connection` và `autoCommit=false`?
- Nếu `debit.executeUpdate() == 1` nhưng `credit.executeUpdate() == 0`, điều gì phải xảy ra trước khi service báo lỗi?
- Tại sao dùng `BigDecimal("125.50")` thích hợp hơn dùng `double 125.50`?
- Vì sao khóa người gửi trước, người nhận sau có thể tạo deadlock khi có chuyển tiền hai chiều?
- `UPDATE ... WHERE balance >= ?` bảo vệ điều kiện gì ngoài việc `SELECT ... FOR UPDATE`?
- Khi duplicate `request_key`, vì sao không thể tự trả `SUCCESS` mà không đối chiếu payload?
- Nếu `commit()` mất kết nối, việc gọi `rollback()` sau đó có chứng minh giao dịch chưa commit không?
- Vì sao hai transaction cùng chuyển mỗi lần `80.00` từ tài khoản có `100.00` không được cùng thành công?
- `Connection.close()` với pooled `DataSource` có nhất thiết đóng kết nối vật lý không?
- Khi dùng Spring `@Transactional`, vì sao một DAO tự mở raw `Connection` có thể phá tính nguyên tử?
- Vì sao test chỉ kiểm tra có exception là chưa đủ để chứng minh rollback?
- Hệ thống tài chính production cần gì thêm ngoài bảng `accounts` và `transfer_log` của ví dụ?

## 21. Tổng kết

1. **Một lệnh chuyển tiền gồm nhiều thay đổi phải cùng một transaction**: debit, credit và ghi nhận transfer được commit/rollback như một đơn vị.
2. **Một bên sở hữu `Connection` và transaction boundary.** Dùng `DataSource` để mượn, `PreparedStatement` cho SQL tham số hóa, kiểm tra update counts, rồi commit hoặc rollback đúng lúc.
3. **Giữ bất biến ngay ở SQL và schema**: đủ số dư, cột DECIMAL chính xác, tài khoản/currency hợp lệ và ràng buộc database.
4. **Khóa tài khoản nhất quán, kiểm thử đồng thời**: thứ tự khóa giúp giảm deadlock, còn điều kiện debit và database transaction bảo vệ dữ liệu khi tranh chấp.
5. **Idempotency và commit unknown là vấn đề tách biệt với atomicity**: một transaction có thể nguyên tử nhưng request bị gửi lại vẫn chuyển tiền hai lần nếu key và đối soát sai.
6. **Rollback/cleanup phải được kiểm chứng**: rollback thất bại hoặc lỗi lúc commit khiến kết nối/trạng thái nghiệp vụ cần xử lý cẩn trọng.
7. **Kiểm thử trên DB thật**: happy path, insufficient funds, lỗi sau debit, duplicate key và concurrency đều cần xác nhận dữ liệu sau transaction, không chỉ dựa vào mock.

**Kết luận:** Chuyển tiền giữa hai tài khoản là bài thực hành tổng hợp thể hiện rõ nhất vai trò của **JDBC transaction**: cả hai số dư và bản ghi chuyển tiền chỉ được xem là hoàn tất khi cùng commit thành công. Kết hợp `BigDecimal`, câu SQL có điều kiện, khóa theo thứ tự, ràng buộc database, rollback, idempotency và kiểm thử tích hợp giúp xây dựng nền tảng đúng đắn; một hệ thống tài chính thực tế còn cần sổ cái kép, đối soát và các kiểm soát bảo mật/vận hành đầy đủ.
