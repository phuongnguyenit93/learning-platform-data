# Autocommit phía công cụ/JDBC và nguy cơ chia nhỏ giao dịch trong Oracle

Một nghiệp vụ thường gồm nhiều câu SQL nhưng cần được xem như **một đơn vị công việc nguyên tử**. Ví dụ chuyển tiền phải trừ tiền ở tài khoản nguồn và cộng tiền vào tài khoản đích; tạo đơn hàng có thể phải ghi đơn, chi tiết đơn và trừ tồn kho; phê duyệt hồ sơ có thể phải cập nhật trạng thái và ghi lịch sử. Nếu mỗi câu SQL tự commit ngay sau khi chạy, một lỗi ở giữa có thể để lại dữ liệu chỉ được cập nhật một nửa.

Đây là rủi ro chính của **autocommit** khi dùng SQL client hoặc JDBC. Trong Oracle, ranh giới transaction do database quản lý, nhưng công cụ và ứng dụng quyết định lúc nào gửi `COMMIT`/`ROLLBACK`, có bật chế độ tự commit hay không, và các câu lệnh có thực sự chạy trên cùng một connection/session hay không.

Bài học tập trung vào:

- Autocommit trong SQL client và JDBC có ý nghĩa gì.
- Vì sao một nghiệp vụ nhiều câu SQL có thể bị chia thành nhiều transaction.
- Cách quản lý transaction bằng `setAutoCommit(false)`, `commit()` và `rollback()`.
- `SAVEPOINT`, implicit commit của DDL và ảnh hưởng của connection pool.
- Các tình huống lỗi, retry, batch, framework transaction và cách kiểm thử ranh giới commit.

## 1. Transaction là gì và vì sao cần ranh giới rõ ràng?

Một **transaction** là một đơn vị công việc database gồm một hoặc nhiều câu lệnh được xử lý như một chỉnh thể. Transaction thường được mô tả bằng bốn thuộc tính ACID:

| Thuộc tính | Ý nghĩa trong thực tế |
|---|---|
| Atomicity | Tất cả thay đổi của transaction được commit, hoặc các thay đổi chưa commit được rollback |
| Consistency | Transaction phải giữ các ràng buộc và quy tắc dữ liệu của hệ thống |
| Isolation | Các transaction đồng thời không được nhìn thấy trạng thái trung gian theo cách vi phạm mức cô lập đã chọn |
| Durability | Sau khi commit thành công, thay đổi được database bảo đảm lưu bền vững theo cấu hình/đảm bảo của hệ thống |

Ví dụ chuyển 100 đơn vị tiền từ tài khoản A sang B gồm hai câu lệnh:

```sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 2;
```

Hai câu lệnh này phải thuộc **cùng một transaction**. Nếu câu trừ tiền thành công nhưng câu cộng tiền thất bại, ứng dụng phải có thể rollback cả hai thay đổi. Nếu câu trừ tiền đã commit riêng, `ROLLBACK` sau đó không thể lấy lại thay đổi đã commit.

```text
Một nghiệp vụ chuyển tiền
          |
          v
    Trừ tài khoản A
          |
          v
    Cộng tài khoản B
          |
          v
   Cả hai thành công?
       /       \
     Có         Không
     |             |
     v             v
   COMMIT       ROLLBACK
```

**Autocommit có thể làm thay đổi ranh giới transaction**: mỗi câu lệnh hoàn tất được commit riêng, khiến hai bước trên không còn nguyên tử như nghiệp vụ yêu cầu.

## 2. Transaction trong Oracle được bắt đầu và kết thúc thế nào?

Oracle quản lý transaction trong một database session. Một transaction có thể gồm nhiều câu lệnh DML như `INSERT`, `UPDATE`, `DELETE` và `MERGE`. Các thay đổi chưa commit chỉ thuộc transaction hiện tại.

Các lệnh điều khiển thường gặp:

```sql
COMMIT;
ROLLBACK;
SAVEPOINT before_optional_step;
ROLLBACK TO before_optional_step;
```

- `COMMIT`: kết thúc transaction hiện tại và xác nhận các thay đổi.
- `ROLLBACK`: hủy các thay đổi chưa commit của transaction hiện tại.
- `SAVEPOINT name`: đánh dấu một vị trí trong transaction.
- `ROLLBACK TO name`: hủy phần thay đổi sau savepoint, nhưng giữ transaction mở để có thể tiếp tục.

Oracle không cần câu `BEGIN TRANSACTION` theo cách viết của một số hệ quản trị khác. Transaction được database quản lý trong session; DML bắt đầu hoặc tham gia transaction hiện tại. Từ `BEGIN` trong `BEGIN ... END;` là cú pháp khối PL/SQL, **không tự tạo một transaction độc lập** và cũng không tự commit khi kết thúc khối.

### 2.1. Thay đổi chưa commit được nhìn thấy thế nào?

Trong một session, người dùng nhìn thấy thay đổi do chính transaction của mình thực hiện. Session khác thường nhìn thấy phiên bản đã commit theo cơ chế read consistency của Oracle, không nhìn thấy thay đổi DML chưa commit của session đầu.

Ví dụ kiểm tra bằng hai session:

**Session A:**

```sql
UPDATE lab_accounts
SET balance = balance - 100
WHERE account_id = 1;
-- Chưa COMMIT.
```

**Session B:**

```sql
SELECT account_id, balance
FROM lab_accounts
WHERE account_id = 1;
```

Session B đọc dữ liệu đã commit trước đó, trong khi session A thấy số dư sau cập nhật của chính mình. Khi session A chạy `COMMIT`, các truy vấn tiếp theo của session B có thể nhìn thấy giá trị mới.

Điều này cũng có nghĩa nếu SQL client tự commit sau câu `UPDATE`, session B sẽ thấy dữ liệu mới ngay sau khi câu lệnh hoàn tất. Người dùng có thể tưởng rằng chỉ đang “thử một câu lệnh”, nhưng thay đổi đã được xác nhận.

### 2.2. Rollback chỉ tác động phần chưa commit

```sql
UPDATE lab_accounts
SET balance = balance - 100
WHERE account_id = 1;

COMMIT;

UPDATE lab_accounts
SET balance = balance + 100
WHERE account_id = 2;

ROLLBACK;
```

Sau đoạn trên, câu cập nhật đầu tiên vẫn được giữ vì đã commit. Câu cập nhật thứ hai bị hủy vì còn trong transaction chưa commit. `ROLLBACK` không thể hoàn tác một transaction đã kết thúc bằng `COMMIT`.

### 2.3. Statement atomicity không giống transaction atomicity

Oracle bảo đảm tính nguyên tử ở cấp **một câu lệnh**: nếu một câu `UPDATE` thất bại giữa quá trình thực hiện, database hoàn tác tác động của chính câu lệnh đó. Nhưng điều này không có nghĩa toàn bộ các câu lệnh trước đó trong transaction cũng tự rollback.

Ví dụ:

```sql
UPDATE lab_accounts
SET balance = balance - 100
WHERE account_id = 1;

-- Giả sử câu lệnh sau lỗi do vi phạm constraint.
INSERT INTO lab_transfer_log (transfer_id, note)
VALUES (NULL, 'missing required id');
```

Nếu câu `INSERT` lỗi, tác động của câu `INSERT` bị hủy. Câu `UPDATE` trước đó vẫn còn trong transaction và có thể được commit sau đó nếu ứng dụng không chủ động rollback. Vì thế, xử lý exception phải quyết định rõ có rollback **toàn bộ nghiệp vụ** hay không.

## 3. Autocommit là gì?

**Autocommit** là chế độ trong đó công cụ/driver tự commit sau khi câu lệnh hoàn tất theo quy tắc của nó, thay vì chờ ứng dụng hoặc người dùng gọi `COMMIT` tường minh.

Về mặt nghiệp vụ, cần phân biệt:

- **Autocommit bật:** mỗi câu lệnh hoàn tất là một ranh giới commit riêng trong chế độ áp dụng.
- **Autocommit tắt:** các câu lệnh có thể tham gia cùng transaction cho tới khi gọi `COMMIT` hoặc `ROLLBACK` (hoặc một sự kiện khác kết thúc transaction, chẳng hạn DDL trong Oracle).

Autocommit là thuộc tính của **công cụ/connection**, không phải một constraint của bảng. Cùng một database, hai session có thể đang dùng chế độ commit khác nhau.

### 3.1. Vì sao autocommit tiện?

Autocommit phù hợp với các thao tác độc lập, chẳng hạn:

- Chạy một câu `INSERT` đơn giản để nạp một dòng thử nghiệm.
- Chạy một câu `UPDATE` độc lập mà kết quả đã được xác định.
- Thực hiện truy vấn chỉ đọc; SELECT không tạo thay đổi DML cần commit.
- Thực thi câu lệnh quản trị mà công cụ/database có quy tắc transaction riêng.

Người dùng không cần nhớ bấm `COMMIT` sau từng thao tác độc lập. Tuy nhiên, nếu nhiều câu lệnh cùng phục vụ một nghiệp vụ, autocommit có thể chia nhỏ transaction ngoài ý muốn.

### 3.2. Autocommit không có nghĩa là “mọi thứ trong script là một transaction”

Một script có thể chứa nhiều câu SQL:

```sql
UPDATE orders SET status = 'APPROVED' WHERE order_id = 1001;
INSERT INTO order_audit (order_id, action_name)
VALUES (1001, 'APPROVED');
UPDATE inventory SET reserved_qty = reserved_qty + 1 WHERE product_id = 501;
```

Nếu công cụ đang autocommit theo từng statement, ba câu lệnh có thể trở thành ba transaction riêng. Nếu câu thứ ba thất bại, hai thay đổi trước có thể đã được commit. Việc bấm “Run Script” hoặc “Execute” không tự bảo đảm tất cả câu lệnh thuộc cùng một transaction; cần biết công cụ gửi statement và xử lý commit như thế nào.

## 4. Autocommit phía SQL client/công cụ

SQL client là chương trình kết nối Oracle để chạy SQL/PLSQL. Các công cụ có thể cung cấp tùy chọn như Auto Commit, Commit after each statement, Manual Commit, hoặc nút Commit/Rollback. Tên tùy chọn, giá trị mặc định và cách áp dụng có thể khác theo phiên bản công cụ, chế độ chạy worksheet/script và loại kết nối.

Không nên khẳng định mọi SQL client đều mặc định bật hoặc tắt autocommit. Trước khi chạy script có DML, hãy kiểm tra cấu hình hiện tại và quan sát trạng thái transaction của chính session.

### 4.1. Khi bật autocommit

Ví dụ người dùng chạy:

```sql
UPDATE lab_accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE lab_accounts
SET balance = balance + 100
WHERE account_id = 2;
```

Nếu công cụ commit từng câu sau khi thực thi:

1. Câu trừ tiền hoàn tất và được commit.
2. Câu cộng tiền chạy sau đó.
3. Nếu câu thứ hai lỗi, câu thứ nhất vẫn đã commit.

Người dùng không thể khôi phục tính nguyên tử bằng cách bấm Rollback sau đó, vì transaction đầu tiên đã kết thúc.

### 4.2. Khi tắt autocommit

Nếu công cụ giữ transaction mở:

```sql
UPDATE lab_accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE lab_accounts
SET balance = balance + 100
WHERE account_id = 2;

-- Chỉ xác nhận sau khi cả hai bước thành công.
COMMIT;
```

Nếu một câu lỗi và nghiệp vụ không thể tiếp tục:

```sql
ROLLBACK;
```

Các thay đổi DML chưa commit của transaction sẽ bị hủy. Nhưng autocommit tắt không tự động bảo đảm script an toàn: script vẫn có thể chứa `COMMIT`, DDL gây implicit commit, gọi procedure tự commit hoặc chuyển sang session khác.

### 4.3. Script nhiều câu lệnh và thao tác chạy từng statement

Một số công cụ cho phép chạy:

- Một statement đang được chọn.
- Toàn bộ nội dung worksheet.
- Một script thông qua script runner.
- Một khối PL/SQL.

Các chế độ này có thể gửi SQL đến database theo cách khác nhau. Hãy xác định công cụ có bật autocommit cho connection không, có chèn commit tự động sau script không, và script có lệnh `COMMIT`/`ROLLBACK` riêng hay không. Đừng dựa vào việc một lần bấm nút tương ứng với một transaction.

### 4.4. Kiểm tra bằng hai session

Một cách kiểm chứng thực tế là mở hai session độc lập tới cùng schema:

1. Session A thực hiện một `UPDATE` nhưng chưa commit.
2. Session B đọc hàng đó.
3. Quan sát session B vẫn thấy dữ liệu đã commit trước đó.
4. Session A commit.
5. Session B đọc lại và thấy thay đổi mới.

Nếu session B nhìn thấy giá trị mới ngay sau khi câu lệnh A chạy xong, hãy kiểm tra autocommit hoặc một commit được thực hiện ở nơi khác. Thử nghiệm trên bảng lab, không dùng một bảng nghiệp vụ thật để “thử xem rollback có hoạt động không”.

## 5. Autocommit trong JDBC

JDBC quản lý transaction thông qua `java.sql.Connection`. **Một `Connection` mới được tạo thường ở chế độ auto-commit bật (`true`) theo JDBC contract.** Khi auto-commit bật, câu lệnh được commit khi hoàn tất theo quy tắc của driver/JDBC. Nếu một nghiệp vụ gồm nhiều statement, ứng dụng cần tắt auto-commit để gom các statement vào cùng transaction.

Các API chính:

```java
connection.getAutoCommit();
connection.setAutoCommit(false);
connection.commit();
connection.rollback();
connection.setSavepoint();
connection.rollback(savepoint);
```

### 5.1. Auto-commit mặc định

Ví dụ:

```java
try (Connection connection = dataSource.getConnection()) {
    System.out.println(connection.getAutoCommit());

    try (PreparedStatement ps = connection.prepareStatement(
            "UPDATE lab_accounts SET balance = balance - ? WHERE account_id = ?")) {
        ps.setBigDecimal(1, new BigDecimal("100.00"));
        ps.setLong(2, 1L);
        ps.executeUpdate();
    }
}
```

Nếu `getAutoCommit()` trả `true`, câu `UPDATE` độc lập được commit tự động khi hoàn tất. Nếu ứng dụng tiếp tục chạy một câu `UPDATE` khác trên cùng connection, câu thứ hai không tự nhập lại transaction đã commit của câu thứ nhất.

### 5.2. Tắt autocommit và commit tường minh

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (PreparedStatement ps = connection.prepareStatement(
            "UPDATE lab_accounts SET balance = balance - ? WHERE account_id = ?")) {
        ps.setBigDecimal(1, new BigDecimal("100.00"));
        ps.setLong(2, 1L);
        ps.executeUpdate();
    }

    try (PreparedStatement ps = connection.prepareStatement(
            "UPDATE lab_accounts SET balance = balance + ? WHERE account_id = ?")) {
        ps.setBigDecimal(1, new BigDecimal("100.00"));
        ps.setLong(2, 2L);
        ps.executeUpdate();
    }

    connection.commit();
}
```

Hai câu `UPDATE` được thực hiện trong cùng transaction của connection và chỉ commit sau khi cả hai hoàn tất. Tuy nhiên, ví dụ trên vẫn cần xử lý lỗi bằng rollback; chỉ gọi `setAutoCommit(false)` rồi để connection đóng không phải cách xử lý lỗi đầy đủ.

### 5.3. Rollback khi có lỗi

Mẫu quản lý transaction cơ bản:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        // Thực hiện tất cả statement thuộc cùng nghiệp vụ.
        updateAccountA(connection);
        updateAccountB(connection);
        insertTransferAudit(connection);

        // Chỉ commit sau khi toàn bộ bước thành công.
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

Mẫu này thể hiện các nguyên tắc:

- Tất cả statement của nghiệp vụ dùng cùng một `Connection`.
- Không commit giữa các bước.
- Khi lỗi, rollback phần chưa commit.
- Nếu rollback cũng lỗi, giữ lỗi rollback dưới dạng suppressed exception để không che mất nguyên nhân ban đầu.
- Chỉ đóng connection sau khi transaction đã được commit hoặc rollback rõ ràng.

Trong ứng dụng thực tế, nên tách logic SQL thành các method nhận connection hiện tại, hoặc để framework transaction quản lý connection. Tránh để mỗi method tự mở một connection mới nếu chúng phải cùng transaction.

### 5.4. Kiểm tra số hàng bị tác động

Một câu `UPDATE` không lỗi cú pháp nhưng có thể cập nhật **0 hàng** do sai ID hoặc dữ liệu không tồn tại. Điều đó không tự phát sinh exception. Với nghiệp vụ chuyển tiền, cần kiểm tra số hàng:

```java
int updated = statement.executeUpdate();
if (updated != 1) {
    throw new SQLException("Expected exactly one account row, updated=" + updated);
}
```

Nếu số hàng không đúng, ném lỗi để luồng transaction rollback. Đừng coi “không có SQLException” đồng nghĩa nghiệp vụ đã thành công.

### 5.5. Thay đổi autoCommit có thể commit transaction hiện tại

Theo JDBC contract, nếu gọi `setAutoCommit(...)` trong khi transaction đang diễn ra và giá trị auto-commit thực sự thay đổi, transaction hiện tại sẽ được commit. Vì vậy, đoạn sau nguy hiểm:

```java
connection.setAutoCommit(false);
updateAccountA(connection);

// Nguy hiểm: đổi chế độ có thể commit transaction hiện tại.
connection.setAutoCommit(true);

updateAccountB(connection);
```

Thay đổi `false` sang `true` có thể commit thay đổi của `updateAccountA` trước khi `updateAccountB` chạy. Không dùng `setAutoCommit(true)` như một cách “dọn trạng thái” giữa nghiệp vụ. Hãy hoàn tất bằng `commit()` hoặc `rollback()` theo ý định, rồi để pool/framework khôi phục trạng thái connection theo contract của nó.

## 6. Ví dụ đầy đủ: chuyển tiền an toàn và lỗi chia nhỏ transaction

### 6.1. Tạo bảng lab

Chỉ chạy DDL sau trong schema **DEV/TEST** được cấp quyền và xác nhận đúng database/service:

```sql
CREATE TABLE lab_accounts (
    account_id NUMBER PRIMARY KEY,
    owner_name VARCHAR2(80 CHAR) NOT NULL,
    balance    NUMBER(14, 2) NOT NULL,
    CONSTRAINT ck_lab_accounts_balance CHECK (balance >= 0)
);

INSERT INTO lab_accounts VALUES (1, 'Account A', 1000.00);
INSERT INTO lab_accounts VALUES (2, 'Account B', 500.00);
COMMIT;
```

Constraint `CHECK (balance >= 0)` giúp database từ chối số dư âm. Nó không thay thế việc kiểm tra số tiền và số hàng được cập nhật trong ứng dụng.

### 6.2. Cách sai: autocommit bật cho từng bước

Giả sử ứng dụng chạy hai câu lệnh trên một connection có `autoCommit = true`:

```java
connection.setAutoCommit(true);

try (PreparedStatement debit = connection.prepareStatement(
        "UPDATE lab_accounts " +
        "SET balance = balance - ? " +
        "WHERE account_id = ? AND balance >= ?")) {
    debit.setBigDecimal(1, new BigDecimal("100.00"));
    debit.setLong(2, 1L);
    debit.setBigDecimal(3, new BigDecimal("100.00"));
    debit.executeUpdate(); // Câu này có thể đã được commit.
}

try (PreparedStatement credit = connection.prepareStatement(
        "UPDATE lab_accounts SET balance = balance + ? WHERE account_id = ?")) {
    credit.setBigDecimal(1, new BigDecimal("100.00"));
    credit.setLong(2, 999L); // Tài khoản đích không tồn tại.
    int rows = credit.executeUpdate(); // Không lỗi SQL, nhưng cập nhật 0 hàng.
}
```

Hậu quả:

1. Tài khoản A bị trừ 100 và câu lệnh đầu được commit.
2. Câu thứ hai cập nhật 0 hàng vì ID 999 không tồn tại.
3. Không có exception bắt buộc chỉ vì số hàng cập nhật bằng 0.
4. Tiền đã rời tài khoản A nhưng không được cộng vào tài khoản B.

Ngay cả khi ứng dụng phát hiện `rows == 0` và gọi `rollback()`, rollback không thể hoàn tác câu trừ tiền đã commit trước đó.

### 6.3. Cách đúng: một transaction cho toàn bộ chuyển tiền

```java
public void transfer(
        DataSource dataSource,
        long fromAccountId,
        long toAccountId,
        BigDecimal amount
) throws SQLException {
    if (amount == null || amount.signum() <= 0) {
        throw new IllegalArgumentException("amount must be positive");
    }
    if (fromAccountId == toAccountId) {
        throw new IllegalArgumentException("source and destination must differ");
    }

    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);

        try {
            int debited;
            try (PreparedStatement debit = connection.prepareStatement(
                    "UPDATE lab_accounts " +
                    "SET balance = balance - ? " +
                    "WHERE account_id = ? AND balance >= ?")) {
                debit.setBigDecimal(1, amount);
                debit.setLong(2, fromAccountId);
                debit.setBigDecimal(3, amount);
                debited = debit.executeUpdate();
            }

            if (debited != 1) {
                throw new SQLException("Source account missing or insufficient funds");
            }

            int credited;
            try (PreparedStatement credit = connection.prepareStatement(
                    "UPDATE lab_accounts " +
                    "SET balance = balance + ? " +
                    "WHERE account_id = ?")) {
                credit.setBigDecimal(1, amount);
                credit.setLong(2, toAccountId);
                credited = credit.executeUpdate();
            }

            if (credited != 1) {
                throw new SQLException("Destination account does not exist");
            }

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
}
```

Ở đây cả hai cập nhật cùng connection, auto-commit tắt, kiểm tra số hàng và commit một lần sau cùng. Nếu tài khoản đích không tồn tại, exception kích hoạt rollback và số dư tài khoản nguồn được khôi phục.

### 6.4. Còn phải xử lý các trường hợp cạnh tranh

Transaction bảo đảm các câu lệnh cùng commit/rollback, nhưng logic nghiệp vụ vẫn cần xử lý đồng thời:

- Hai request cùng chuyển tiền từ một tài khoản có thể cạnh tranh cập nhật số dư.
- Điều kiện `balance >= amount` trong `UPDATE` giúp kiểm tra số dư tại thời điểm cập nhật và giảm nguy cơ trừ quá số tiền hiện có.
- Constraint `CHECK (balance >= 0)` là lớp bảo vệ cuối ở database.
- Cần xác định thứ tự khóa khi hai transaction chuyển tiền ngược chiều để giảm nguy cơ deadlock.
- Với request có thể retry, nên có mã giao dịch/idempotency key để tránh chuyển tiền hai lần khi client không nhận được phản hồi.

Autocommit tắt là điều kiện cần cho atomicity của hai câu lệnh, nhưng không tự giải quyết mọi vấn đề đồng thời hoặc retry.

## 7. SAVEPOINT: rollback một phần mà không chia transaction

`SAVEPOINT` cho phép đánh dấu một điểm trong transaction. Có thể rollback một phần công việc sau điểm đó mà vẫn giữ các thay đổi trước savepoint trong cùng transaction.

```sql
UPDATE lab_accounts
SET balance = balance - 50
WHERE account_id = 1;

SAVEPOINT after_debit;

UPDATE lab_accounts
SET balance = balance + 50
WHERE account_id = 2;

-- Nếu bước cộng tiền phụ thất bại, có thể rollback tới savepoint.
ROLLBACK TO after_debit;

-- Sau khi xử lý lại logic, quyết định COMMIT hoặc ROLLBACK toàn transaction.
```

Trong ví dụ trên, `ROLLBACK TO after_debit` chỉ hủy thay đổi sau savepoint; câu trừ tiền trước savepoint vẫn còn trong transaction. Nếu mục tiêu là chuyển tiền nguyên tử, không nên commit phần trừ tiền sau đó. Savepoint không thay thế quyết định cuối cùng commit/rollback của nghiệp vụ.

### 7.1. Savepoint trong JDBC

```java
connection.setAutoCommit(false);

try {
    updateRequiredData(connection);

    Savepoint optionalStep = connection.setSavepoint("OPTIONAL_STEP");
    try {
        updateOptionalData(connection);
    } catch (SQLException optionalError) {
        connection.rollback(optionalStep);
        recordOptionalFailureInMemory(optionalError);
    }

    connection.commit();
} catch (SQLException | RuntimeException ex) {
    connection.rollback();
    throw ex;
}
```

Mẫu này phù hợp khi một bước phụ có thể được bỏ qua mà các bước bắt buộc vẫn hợp lệ. Không dùng savepoint để che lỗi của một bước bắt buộc; quyết định rollback một phần phải xuất phát từ quy tắc nghiệp vụ rõ ràng.

## 8. DDL trong Oracle có implicit commit

Một bẫy quan trọng khác: **DDL trong Oracle có thể tự kết thúc transaction**, bất kể JDBC `autoCommit` đang là `true` hay `false`.

Các câu DDL thường gặp:

```sql
CREATE TABLE ...;
ALTER TABLE ...;
DROP TABLE ...;
TRUNCATE TABLE ...;
CREATE INDEX ...;
```

Oracle thực hiện implicit commit trước DDL hợp lệ và sau DDL thành công theo quy tắc transaction của database. Vì vậy:

```sql
UPDATE lab_accounts
SET balance = balance - 10
WHERE account_id = 1;

CREATE TABLE lab_temp_note (note_id NUMBER);

ROLLBACK;
```

Không thể kỳ vọng `ROLLBACK` cuối cùng hoàn tác câu `UPDATE` đầu tiên; transaction DML đã bị commit trước khi DDL chạy. DDL thành công còn có commit sau nó. Đây là quy tắc Oracle, không phụ thuộc việc người dùng đã tắt autocommit trong JDBC.

### 8.1. DDL không thể rollback như DML thông thường

Sau khi chạy:

```sql
CREATE TABLE lab_temp_note (note_id NUMBER);
```

không thể dùng `ROLLBACK` để xóa bảng vừa tạo. Muốn xóa, phải chạy DDL khác:

```sql
DROP TABLE lab_temp_note PURGE;
```

Đây là thao tác DDL mới, có transaction semantics riêng. Không đặt DDL giữa các bước DML cần atomicity, trừ khi đã thiết kế rõ ranh giới commit.

### 8.2. Migration schema và transaction dữ liệu

Không nên gom thay đổi schema và cập nhật dữ liệu nghiệp vụ vào một transaction với kỳ vọng có thể rollback tất cả. Một migration thường cần quy trình riêng:

1. Chuẩn bị và kiểm tra thay đổi schema.
2. Thực hiện DDL, hiểu rõ implicit commit.
3. Chạy backfill/transform dữ liệu theo batch có checkpoint phù hợp.
4. Kiểm tra kết quả và khả năng tương thích ứng dụng.
5. Có kế hoạch rollback/forward-fix cho schema và dữ liệu.

DDL của Oracle không được hoàn tác bằng rollback thông thường như một câu `UPDATE` chưa commit. Với thay đổi lớn, cần version hóa migration và thiết kế thao tác bù/forward migration.

## 9. JDBC, connection pool và ranh giới transaction

Trong ứng dụng server, `DataSource` thường cấp connection từ connection pool. Connection mà ứng dụng nhận có thể là logical handle trỏ tới một physical database session được tái sử dụng.

### 9.1. Một transaction phải dùng cùng connection

Ví dụ sai về mặt transaction boundary:

```java
updateAccountA(dataSource); // Method mở connection A, commit/close.
updateAccountB(dataSource); // Method mở connection B, commit/close.
```

Hai method có thể dùng hai session khác nhau. Ngay cả khi cùng kết nối tới một database và cùng schema, chúng không tự động thuộc một transaction chung.

Mẫu tốt hơn là truyền connection hiện tại:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    try {
        updateAccountA(connection);
        updateAccountB(connection);
        connection.commit();
    } catch (SQLException | RuntimeException ex) {
        connection.rollback();
        throw ex;
    }
}
```

Các helper `updateAccountA` và `updateAccountB` chỉ thực thi statement trên connection được truyền vào; chúng không tự mở connection, commit hay close connection của caller.

### 9.2. Trả connection về pool khi transaction chưa kết thúc

Không nên dựa vào việc `Connection.close()` sẽ tự rollback theo một cách giống nhau ở mọi driver/pool. JDBC khuyến nghị ứng dụng kết thúc transaction bằng `commit()` hoặc `rollback()` trước khi đóng connection; kết quả khi đóng connection đang có transaction hoạt động có thể phụ thuộc implementation.

Với connection pool, `close()` thường trả logical connection về pool thay vì đóng physical session. Pool có thể rollback/reset trạng thái khi tái sử dụng, nhưng ứng dụng vẫn phải quản lý transaction rõ ràng. Đừng để một request trả connection về pool khi chưa biết transaction đã commit hay rollback.

### 9.3. Trạng thái connection có thể rò sang request sau

Ngoài autocommit, connection còn có các trạng thái như isolation level, schema, read-only, client info, NLS/session setting và savepoint. Pool/framework thường có cơ chế reset một số trạng thái, nhưng không nên giả định mọi thay đổi tùy chỉnh đều tự được khôi phục.

Một request tắt autocommit rồi trả connection về pool sai cách có thể khiến request sau nhận trạng thái ngoài mong muốn. Hãy:

- Để transaction manager/pool quản lý trạng thái khi có framework.
- Luôn commit/rollback rõ ràng.
- Không tự thay đổi autocommit trong một connection do framework quản lý nếu không được hướng dẫn.
- Kiểm tra cấu hình reset/validation của pool khi điều tra lỗi trạng thái session.

## 10. Spring và framework transaction

Trong ứng dụng Java dùng Spring, thường nên để **transaction manager** điều khiển connection và transaction thay vì mỗi method tự gọi `setAutoCommit`, `commit`, `rollback`.

Ví dụ khái niệm:

```java
@Service
public class TransferService {
    private final AccountRepository accountRepository;
    private final TransferAuditRepository auditRepository;

    public TransferService(
            AccountRepository accountRepository,
            TransferAuditRepository auditRepository) {
        this.accountRepository = accountRepository;
        this.auditRepository = auditRepository;
    }

    @Transactional
    public void transfer(long fromId, long toId, BigDecimal amount) {
        accountRepository.debit(fromId, amount);
        accountRepository.credit(toId, amount);
        auditRepository.insert(fromId, toId, amount);
    }
}
```

Với cấu hình transaction manager phù hợp, các repository tham gia cùng transaction được quản lý cho method. Khi method hoàn tất bình thường, transaction manager commit; khi exception thuộc quy tắc rollback, transaction manager rollback.

### 10.1. Những điều cần chú ý với @Transactional

- Các repository phải tham gia cùng transaction manager/resource; tự mở một connection độc lập có thể thoát khỏi transaction hiện tại.
- `@Transactional` thường được áp dụng qua proxy; gọi method transactional từ một method khác trong cùng object (self-invocation) có thể không đi qua proxy như mong đợi.
- Mặc định Spring thường rollback với `RuntimeException` và `Error`; checked exception không nhất thiết tự rollback nếu không cấu hình `rollbackFor` phù hợp.
- Không gọi `connection.commit()` trực tiếp trên connection do framework quản lý; có thể phá vỡ transaction boundary.
- Không đặt `setAutoCommit(true)` giữa method transactional.
- DDL Oracle vẫn có implicit commit; annotation không thể làm DDL trở thành rollbackable DML.

Ví dụ quy định rollback cho checked exception:

```java
@Transactional(rollbackFor = Exception.class)
public void createOrder(CreateOrderCommand command) throws Exception {
    orderRepository.insert(command);
    inventoryRepository.reserve(command.items());
    auditRepository.insert(command);
}
```

Đây là ví dụ minh họa. Cần kiểm tra transaction manager, datasource và quy tắc exception thực tế của dự án trước khi áp dụng.

## 11. Batch JDBC và nguy cơ một phần thành công

JDBC hỗ trợ batch để gửi nhiều lần thực thi cùng một prepared statement:

```java
String sql = "INSERT INTO lab_import_rows (row_id, value_text) VALUES (?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (ImportRow row : rows) {
        ps.setLong(1, row.id());
        ps.setString(2, row.value());
        ps.addBatch();
    }
    int[] counts = ps.executeBatch();
}
```

Batch giảm round-trip và có thể tăng throughput, nhưng **batch không tự xác định ranh giới nghiệp vụ**. Nếu cần toàn bộ batch thành công hoặc không có hàng nào được giữ, hãy quản lý transaction tường minh:

```java
connection.setAutoCommit(false);
try {
    try (PreparedStatement ps = connection.prepareStatement(
            "INSERT INTO lab_import_rows (row_id, value_text) VALUES (?, ?)")) {
        for (ImportRow row : rows) {
            ps.setLong(1, row.id());
            ps.setString(2, row.value());
            ps.addBatch();
        }
        ps.executeBatch();
    }
    connection.commit();
} catch (SQLException | RuntimeException ex) {
    connection.rollback();
    throw ex;
}
```

Khi `executeBatch()` thất bại, driver có thể cung cấp `BatchUpdateException` với update counts cho các lệnh đã chạy/được xử lý. Cách driver xử lý phần còn lại của batch có thể khác nhau; đọc tài liệu driver và không suy luận rằng “batch ném exception thì mọi thứ tự rollback”. Với auto-commit tắt, ứng dụng có thể rollback transaction chưa commit để đưa các DML thuộc batch về trạng thái trước transaction.

Nếu batch quá lớn, có thể chia thành nhiều transaction theo chunk để giới hạn undo/redo, thời gian khóa và khả năng phục hồi. Nhưng khi đó phải chấp nhận rằng mỗi chunk là một **đơn vị commit riêng**; thiết kế checkpoint, restart và idempotency cho import.

## 12. Chia nhỏ transaction: các rủi ro nghiệp vụ

Chia một nghiệp vụ thành nhiều transaction có thể cần thiết cho batch dài, nhưng nếu chia không chủ đích sẽ tạo ra trạng thái dở dang.

### 12.1. Dữ liệu liên quan không còn đồng bộ

Ví dụ tạo đơn hàng:

1. Insert `ORDERS` và commit.
2. Insert `ORDER_ITEMS` và commit.
3. Trừ tồn kho và commit.
4. Ghi thanh toán thất bại.

Database có thể còn đơn hàng và chi tiết nhưng tồn kho đã giảm, thanh toán chưa có. Nếu nghiệp vụ coi các bước đó phải cùng nguyên tử, đây là trạng thái không hợp lệ.

### 12.2. Ràng buộc tổng thể bị phá vỡ

Một transaction có thể phải giữ các invariant như:

- Tổng tiền ghi nợ bằng tổng tiền ghi có.
- Số lượng tồn kho không âm.
- Đơn đã xác nhận phải có ít nhất một dòng chi tiết.
- Trạng thái thanh toán và trạng thái đơn hàng phải tương thích.
- Một mã idempotency chỉ được xử lý một lần.

Nếu commit giữa các bước, các invariant chỉ được kiểm tra ở trạng thái trung gian có thể bị phá vỡ hoặc bị hệ thống khác đọc thấy.

### 12.3. Rollback không thể vượt qua commit trước đó

Khi bước 3 thất bại, `ROLLBACK` chỉ hoàn tác transaction hiện tại. Các bước 1 và 2 đã commit vẫn tồn tại. Muốn sửa, ứng dụng phải thực hiện **compensating action** (thao tác bù) hoặc một quy trình sửa dữ liệu có kiểm soát.

### 12.4. Retry có thể thực hiện trùng nghiệp vụ

Giả sử ứng dụng gửi lệnh chuyển tiền, database commit thành công nhưng mạng đứt trước khi client nhận phản hồi. Client không biết commit đã thành công hay chưa và gửi lại request. Nếu không có idempotency key, có thể chuyển tiền hai lần.

Một thiết kế thường dùng là lưu `REQUEST_ID`/idempotency key với unique constraint trong cùng transaction với nghiệp vụ. Request lặp lại có thể tra kết quả đã xử lý thay vì thực hiện lần nữa. Cần xác định rõ hành vi khi request đang xử lý hoặc kết quả commit chưa được client nhận.

### 12.5. Transaction quá dài cũng có rủi ro

Không phải cứ gom tất cả vào một transaction thật dài là tốt. Transaction kéo dài có thể:

- Giữ row lock lâu và làm session khác phải chờ.
- Tăng lượng undo cần giữ để phục vụ rollback/read consistency.
- Tăng khả năng tranh chấp, deadlock hoặc timeout.
- Làm rollback sau lỗi tốn thời gian.
- Giữ connection pool slot lâu, làm giảm khả năng phục vụ request khác.

Giải pháp là xác định đúng **đơn vị nguyên tử của nghiệp vụ**, không commit tùy tiện từng statement và cũng không giữ transaction mở trong khi chờ người dùng, gọi API bên ngoài hoặc xử lý tác vụ lâu không cần thiết.

## 13. Khi nào chia transaction theo batch là hợp lý?

Một số công việc lớn không nên giữ một transaction duy nhất trong nhiều giờ. Ví dụ import hàng triệu bản ghi, backfill dữ liệu hoặc đồng bộ định kỳ. Có thể chia thành chunk, nhưng phải thiết kế quy tắc phục hồi.

Một quy trình import theo chunk có thể gồm:

1. Đọc một lô dữ liệu có khóa/offset rõ.
2. Ghi dữ liệu lô và trạng thái checkpoint trong cùng transaction.
3. Commit lô.
4. Chuyển sang lô tiếp theo.
5. Khi lỗi, chỉ chạy lại từ checkpoint đã commit; thao tác phải idempotent.

Ví dụ bảng checkpoint giả định:

```sql
CREATE TABLE import_checkpoint (
    job_id          VARCHAR2(80 CHAR) PRIMARY KEY,
    last_row_id     NUMBER NOT NULL,
    updated_at      TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);
```

Trong mỗi chunk, cập nhật dữ liệu và checkpoint cùng transaction:

```sql
-- DML dữ liệu của chunk.
INSERT INTO target_rows (row_id, value_text)
SELECT row_id, value_text
FROM staging_rows
WHERE row_id > :last_row_id
  AND row_id <= :next_row_id;

-- DML checkpoint trong cùng transaction.
UPDATE import_checkpoint
SET last_row_id = :next_row_id,
    updated_at = SYSTIMESTAMP
WHERE job_id = :job_id;

COMMIT;
```

Nếu insert dữ liệu và cập nhật checkpoint không cùng transaction, có thể xảy ra:

- Dữ liệu đã commit nhưng checkpoint chưa cập nhật: chạy lại có thể duplicate.
- Checkpoint đã commit nhưng dữ liệu chưa commit: job bỏ qua dữ liệu chưa được ghi.

Nếu `TARGET_ROWS` có unique key phù hợp, `MERGE`/upsert hoặc cơ chế idempotent có thể giúp chạy lại an toàn hơn. Phải xác định checkpoint và dữ liệu được commit cùng nhau.

## 14. DDL, procedure và transaction control bên trong database

Autocommit phía client không phải nguồn duy nhất có thể kết thúc transaction. Câu lệnh hoặc code chạy bên trong database cũng có thể thay đổi ranh giới.

### 14.1. Procedure có COMMIT

Ví dụ procedure:

```sql
CREATE OR REPLACE PROCEDURE approve_order(p_order_id NUMBER) AS
BEGIN
    UPDATE orders
    SET status = 'APPROVED'
    WHERE order_id = p_order_id;

    INSERT INTO order_audit(order_id, action_name)
    VALUES (p_order_id, 'APPROVED');

    COMMIT;
END;
/
```

Procedure này tự commit. Nếu ứng dụng gọi nó giữa một transaction lớn, lệnh `COMMIT` bên trong procedure có thể commit cả các thay đổi trước đó trong **cùng session/transaction**, không chỉ hai câu lệnh của procedure. Caller không còn khả năng rollback toàn bộ nghiệp vụ như dự định.

Trong thiết kế có transaction do caller quản lý, thường nên để procedure thực hiện DML nhưng **không tự commit**, trừ khi contract quy định rõ procedure sở hữu transaction. Ranh giới commit nên được quản lý nhất quán ở một tầng.

### 14.2. Autonomous transaction là transaction riêng

PL/SQL có `PRAGMA AUTONOMOUS_TRANSACTION` để tạo transaction độc lập với transaction gọi nó. Nó thường được dùng cho logging/audit đặc biệt cần tồn tại ngay cả khi transaction chính rollback.

Ví dụ khái niệm:

```sql
CREATE OR REPLACE PROCEDURE write_error_log(p_message VARCHAR2) AS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO error_log(message, logged_at)
    VALUES (p_message, SYSTIMESTAMP);
    COMMIT;
END;
/
```

Log được commit độc lập; rollback của transaction gọi không xóa log đó. Điều này có thể hữu ích, nhưng cũng có thể tạo audit record cho một hành động nghiệp vụ cuối cùng không được commit. Không dùng autonomous transaction để “né” rollback cho các bước nghiệp vụ phải nguyên tử.

### 14.3. Trigger và transaction

Trigger thông thường chạy trong transaction kích hoạt nó; DML của trigger tham gia transaction đó. Nếu trigger phát sinh lỗi, câu lệnh kích hoạt có thể thất bại và tác động của câu lệnh được hoàn tác. Không dùng trigger để âm thầm commit một phần nghiệp vụ; các transaction độc lập trong trigger cần cơ chế đặc biệt và phải có thiết kế rõ ràng.

## 15. Giao dịch qua nhiều database hoặc dịch vụ bên ngoài

Một JDBC `Connection` quản lý transaction trong một database resource. Nếu một nghiệp vụ ghi Oracle rồi gọi một REST API, gửi email hoặc ghi sang một database khác, `commit()` của Oracle **không tự rollback** được hành động đã xảy ra ở hệ thống ngoài.

Các lựa chọn thiết kế gồm:

- **Outbox pattern:** ghi dữ liệu nghiệp vụ và một sự kiện outbox trong cùng transaction Oracle; worker gửi sự kiện sau commit.
- **Saga/compensation:** chia quy trình dài thành các bước có thao tác bù khi bước sau thất bại.
- **Distributed/XA transaction:** dùng khi các resource hỗ trợ và hệ thống thật sự cần một giao dịch phân tán; cần đánh giá chi phí, vận hành và khả năng phục hồi.

Ví dụ outbox đơn giản:

```sql
INSERT INTO orders(order_id, status, total_amount)
VALUES (:order_id, 'CREATED', :total_amount);

INSERT INTO outbox_events(event_id, aggregate_id, event_type, payload, status)
VALUES (:event_id, :order_id, 'ORDER_CREATED', :payload, 'PENDING');

COMMIT;
```

Worker chỉ đọc sự kiện đã commit và gửi sang hệ thống khác. Nếu gửi thành công nhưng worker chết trước khi đánh dấu đã gửi, sự kiện có thể được gửi lại; consumer cần idempotency. Outbox bảo đảm dữ liệu đơn hàng và sự kiện được ghi cùng nhau trong Oracle, chứ không biến REST call thành một phần của transaction Oracle.

## 16. Cách kiểm tra và chẩn đoán autocommit

Khi phát hiện dữ liệu bị cập nhật một phần, cần tìm đúng ranh giới transaction thay vì chỉ xem từng câu SQL.

### 16.1. Kiểm tra phía JDBC

Ghi nhận:

```java
boolean autoCommit = connection.getAutoCommit();
DatabaseMetaData metadata = connection.getMetaData();

System.out.println("autoCommit=" + autoCommit);
System.out.println("driver=" + metadata.getDriverName());
System.out.println("driverVersion=" + metadata.getDriverVersion());
System.out.println("database=" + metadata.getDatabaseProductName());
```

Đừng chỉ kiểm tra một connection ở lúc khởi tạo rồi suy ra mọi request đều dùng cùng trạng thái. Connection pool, framework và code khác có thể thay đổi trạng thái connection. Hãy log transaction boundary ở tầng service hoặc dùng tracing phù hợp, tránh ghi thông tin nhạy cảm.

### 16.2. Kiểm tra session Oracle

DBA hoặc người có quyền phù hợp có thể quan sát session, transaction đang hoạt động và lock qua các view như `V$SESSION`, `V$TRANSACTION`, `V$LOCK` hoặc các view `GV$` trong môi trường RAC. Quyền truy cập các view này thường bị giới hạn; ứng dụng thông thường không nên được cấp quyền DBA chỉ để kiểm tra transaction.

Ví dụ khái niệm dành cho người có quyền:

```sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.status,
       s.module,
       s.action,
       t.start_time,
       t.used_ublk,
       t.used_urec
FROM v$session s
LEFT JOIN v$transaction t
       ON t.addr = s.taddr
WHERE s.username = USER;
```

View và cột cụ thể cần đối chiếu với phiên bản/quyền của database. Không chạy query quản trị này bằng tài khoản ứng dụng không có quyền.

### 16.3. Ghi nhận transaction boundary trong log ứng dụng

Log hữu ích nên có:

- Correlation ID hoặc idempotency key của nghiệp vụ.
- Tên service/method và transaction manager.
- Các bước DML thành công/thất bại ở mức không lộ dữ liệu nhạy cảm.
- Thời điểm bắt đầu và kết thúc transaction.
- Kết quả commit/rollback và exception gốc.
- Database service, module/action nếu được cấu hình.

Không log mật khẩu, token, dữ liệu tài khoản đầy đủ hoặc SQL chứa thông tin nhạy cảm. Khi lỗi xảy ra sau khi gửi COMMIT nhưng trước khi nhận phản hồi, trạng thái commit có thể không xác định từ phía client; cần tra cứu bằng mã nghiệp vụ/idempotency key.

## 17. Checklist thiết kế transaction an toàn

Trước khi bật autocommit hoặc chia một luồng nghiệp vụ thành nhiều transaction, hãy trả lời:

1. Một nghiệp vụ gồm những statement nào?
2. Những thay đổi nào bắt buộc cùng commit hoặc cùng rollback?
3. Tất cả statement có chạy trên cùng một JDBC connection/session không?
4. Autocommit hiện tại là `true` hay `false`? Ai là người sở hữu cấu hình này: ứng dụng, framework hay pool?
5. Có `COMMIT`, `ROLLBACK`, DDL hoặc procedure tự commit ở giữa luồng không?
6. Khi một statement cập nhật 0 hàng hoặc vi phạm constraint, code có rollback toàn nghiệp vụ không?
7. Batch có thể thành công một phần không? Có checkpoint/idempotency khi chia chunk không?
8. Connection có được commit/rollback trước khi trả về pool không?
9. Retry sau timeout hoặc mất kết nối có thể thực hiện nghiệp vụ hai lần không?
10. Có gọi hệ thống ngoài trong lúc transaction database đang mở quá lâu không?

## 18. Thực hành Oracle SQL và JDBC

Các bài thực hành dùng bảng giả `LAB_ACCOUNTS`. Chỉ chạy trên schema **DEV/TEST** được cấp quyền và đúng PDB/service. Không dùng tài khoản thật, không thử rollback trên dữ liệu production.

### Bài 1 — Quan sát transaction chưa commit

Mở hai session A và B tới cùng schema. Trong session A:

```sql
UPDATE lab_accounts
SET balance = balance - 10
WHERE account_id = 1;
```

Chưa commit. Trong session B:

```sql
SELECT balance
FROM lab_accounts
WHERE account_id = 1;
```

Ghi nhận session B thấy số dư đã commit trước đó. Quay lại A chạy `COMMIT`, rồi đọc lại ở B.

### Bài 2 — Rollback toàn transaction

Trong session A:

```sql
UPDATE lab_accounts
SET balance = balance - 10
WHERE account_id = 1;

UPDATE lab_accounts
SET balance = balance + 10
WHERE account_id = 2;

ROLLBACK;
```

Kiểm tra số dư hai tài khoản. Cả hai thay đổi chưa commit phải được hủy.

### Bài 3 — Minh họa chia nhỏ transaction

Chỉ trong lab, bật autocommit ở công cụ đang dùng hoặc chạy hai câu riêng với commit giữa các bước:

```sql
UPDATE lab_accounts
SET balance = balance - 10
WHERE account_id = 1;
COMMIT;

UPDATE lab_accounts
SET balance = balance + 10
WHERE account_id = 999;
COMMIT;
```

Xác nhận câu thứ hai cập nhật 0 hàng nhưng câu đầu đã commit. Sau đó khôi phục dữ liệu lab bằng thao tác bù có kiểm soát hoặc reset bảng lab; không dùng ví dụ này trên tài khoản thật.

### Bài 4 — SAVEPOINT

```sql
UPDATE lab_accounts
SET balance = balance - 10
WHERE account_id = 1;

SAVEPOINT after_first_change;

UPDATE lab_accounts
SET balance = balance + 10
WHERE account_id = 2;

ROLLBACK TO after_first_change;

ROLLBACK;
```

Quan sát `ROLLBACK TO` hủy bước sau savepoint; `ROLLBACK` cuối cùng hủy phần còn lại của transaction.

### Bài 5 — DDL gây implicit commit

Trong schema lab riêng, chạy:

```sql
UPDATE lab_accounts
SET balance = balance - 5
WHERE account_id = 1;

CREATE TABLE lab_ddl_marker (marker_id NUMBER);

ROLLBACK;
```

Kiểm tra thay đổi `LAB_ACCOUNTS`: DML trước DDL đã bị commit trước khi DDL chạy, nên rollback cuối không hoàn tác nó. Dọn bảng marker bằng DDL riêng sau khi hoàn tất.

### Bài 6 — JDBC autoCommit

Viết một chương trình Java nhỏ:

1. Lấy connection từ `DataSource`.
2. In `getAutoCommit()`.
3. Thực hiện hai câu update trên cùng connection.
4. Thử chạy với `true`, rồi `false`.
5. Với `false`, gọi `commit()` sau cả hai bước; thử làm bước thứ hai thất bại và gọi `rollback()`.
6. So sánh số dư sau mỗi lần chạy.

Đảm bảo reset dữ liệu lab giữa các lần thử và không thay đổi cấu hình pool dùng chung của ứng dụng thật.

### Bài 7 — Connection khác nhau

Mở hai connection trong Java. Chạy một DML trên connection A và một DML liên quan trên connection B, tắt autocommit cả hai. Thử commit A rồi rollback B. Giải thích vì sao rollback B không thể hủy thay đổi đã commit trên A và hai connection không tạo thành một transaction nguyên tử.

### Thu dọn dữ liệu lab

Chỉ khi xác nhận đúng bảng do mình tạo trong DEV/TEST và không có người khác sử dụng:

```sql
DROP TABLE lab_accounts PURGE;
DROP TABLE lab_ddl_marker PURGE;
```

`DROP TABLE ... PURGE` xóa bảng và dữ liệu, không đưa vào recycle bin; đây là DDL có implicit commit. Không chạy trên production hoặc bất kỳ bảng nào ngoài phạm vi bài thực hành.

## 19. Câu hỏi ôn tập

**Câu 1.** Autocommit bật có ý nghĩa gì với một connection JDBC?

**Đáp án:** Mỗi statement được commit tự động khi hoàn tất theo JDBC/driver; nhiều statement liên tiếp không mặc nhiên là một transaction nghiệp vụ chung.

**Câu 2.** JDBC connection mới mặc định có `autoCommit` là gì?

**Đáp án:** `true` theo JDBC contract, trừ khi framework/pool hoặc code thay đổi cấu hình trước khi ứng dụng sử dụng.

**Câu 3.** Muốn hai câu UPDATE cùng commit hoặc rollback, cần làm gì?

**Đáp án:** Dùng cùng một connection, tắt autocommit, thực hiện cả hai câu, kiểm tra kết quả rồi gọi `commit()` hoặc `rollback()`.

**Câu 4.** Nếu câu UPDATE đầu đã autocommit, câu thứ hai lỗi thì ROLLBACK có hủy được câu đầu không?

**Đáp án:** Không. Transaction đầu đã kết thúc bằng commit.

**Câu 5.** Oracle có cho rollback DDL như UPDATE chưa commit không?

**Đáp án:** Không. DDL có implicit commit theo quy tắc Oracle; không thể dùng rollback thông thường để hoàn tác DDL hoặc DML đã được commit trước đó.

**Câu 6.** SAVEPOINT khác COMMIT thế nào?

**Đáp án:** SAVEPOINT chỉ đánh dấu vị trí trong transaction; ROLLBACK TO hủy phần sau điểm đó nhưng transaction vẫn mở. COMMIT kết thúc transaction và xác nhận thay đổi.

**Câu 7.** Tại sao các method repository phải dùng cùng connection trong một transaction?

**Đáp án:** Mỗi connection/session có transaction riêng. Connection khác không tự tham gia transaction của connection hiện tại.

**Câu 8.** Nếu một câu INSERT lỗi trong transaction có nhiều statement, Oracle có tự rollback mọi statement trước đó không?

**Đáp án:** Không. Oracle hoàn tác tác động của statement lỗi; các statement trước chưa commit vẫn còn trong transaction và ứng dụng phải quyết định rollback toàn bộ khi nghiệp vụ thất bại.

**Câu 9.** Vì sao không nên gọi `setAutoCommit(true)` giữa transaction?

**Đáp án:** Thay đổi chế độ auto-commit trong transaction có thể commit transaction hiện tại theo JDBC contract.

**Câu 10.** Một request mất kết nối sau khi gửi COMMIT nhưng không nhận được phản hồi. Có thể kết luận transaction rollback không?

**Đáp án:** Không. Commit có thể đã thành công nhưng phản hồi bị mất. Cần tra cứu trạng thái bằng mã nghiệp vụ/idempotency key trước khi retry.

**Câu 11.** Chia import thành nhiều chunk có luôn sai không?

**Đáp án:** Không. Có thể cần thiết cho batch lớn, nhưng mỗi chunk là một transaction riêng; phải có checkpoint, idempotency và quy trình phục hồi.

**Câu 12.** `@Transactional` có tự biến DDL Oracle thành rollbackable không?

**Đáp án:** Không. DDL vẫn tuân theo implicit commit của Oracle.

## Kết luận

**Autocommit bật có thể biến từng câu SQL thành một transaction riêng.** Điều đó tiện cho thao tác độc lập, nhưng nguy hiểm khi một nghiệp vụ cần nhiều câu lệnh cùng thành công hoặc cùng thất bại. Với JDBC, connection mới mặc định bật auto-commit; để gom nhiều statement, hãy tắt bằng `setAutoCommit(false)`, dùng cùng connection, kiểm tra số hàng bị tác động, rồi commit một lần hoặc rollback toàn bộ khi có lỗi.

Ranh giới transaction còn có thể bị thay đổi bởi DDL implicit commit của Oracle, procedure tự commit, connection khác, framework/pool hoặc thao tác retry sau khi mất phản hồi. `SAVEPOINT` hỗ trợ rollback một phần trong cùng transaction; chia batch thành nhiều transaction chỉ nên thực hiện khi đã có checkpoint và cơ chế chạy lại an toàn. Hãy xác định rõ đơn vị nguyên tử của nghiệp vụ, quản lý connection và commit/rollback tại một tầng nhất quán, đồng thời kiểm thử các tình huống lỗi giữa chừng trước khi đưa luồng dữ liệu vào production.

## Tài liệu tham khảo

- [Oracle Database 19c — Transactions](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/transactions.html): transaction, commit, rollback, savepoint và read consistency.
- [Oracle Database 19c — COMMIT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/COMMIT.html): kết thúc transaction và xác nhận thay đổi.
- [Oracle Database 19c — ROLLBACK](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ROLLBACK.html): rollback toàn transaction hoặc tới savepoint.
- [Oracle Database 19c — SAVEPOINT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SAVEPOINT.html): tạo savepoint trong transaction.
- [Oracle Database 19c — DDL Statements](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Types-of-SQL-Statements.html): phân loại DDL/DML và transaction implications.
- [Java JDBC API — Connection](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Connection.html): `getAutoCommit`, `setAutoCommit`, `commit`, `rollback`, savepoint và quản lý connection.
