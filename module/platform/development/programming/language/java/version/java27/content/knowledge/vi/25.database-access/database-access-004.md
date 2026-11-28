# Transaction, commit, rollback và savepoint trong Java 27

Một thao tác cơ sở dữ liệu đôi khi gồm **nhiều câu SQL nhưng chỉ được phép thành công hoặc thất bại như một đơn vị nghiệp vụ**. Ví dụ chuyển 100.000 đồng từ tài khoản A sang B phải thực hiện ít nhất hai thay đổi: trừ A và cộng B. Nếu chỉ câu đầu thành công, hệ thống sẽ mất tiền. Nếu chỉ câu sau thành công, hệ thống sẽ tạo thêm tiền.

**Transaction** (*giao dịch*) là công cụ để nhóm các thao tác cần tính nhất quán. Trong **Java 27**, API chuẩn JDBC thuộc gói `java.sql` cung cấp các phương thức trên `Connection`:

- `setAutoCommit(false)` — bắt đầu quản lý ranh giới giao dịch một cách tường minh.
- `commit()` — xác nhận toàn bộ thay đổi của giao dịch hiện tại.
- `rollback()` — yêu cầu hủy thay đổi của giao dịch hiện tại.
- `setSavepoint(...)` và `rollback(savepoint)` — đánh dấu và quay về một điểm trong giao dịch, khi database/driver hỗ trợ.

Bài thuộc chương **Truy cập cơ sở dữ liệu** trong module **Java 27 và các kiến thức liên quan**. Các ví dụ sử dụng JDBC chuẩn hiện hành, `PreparedStatement` và `try-with-resources`; không dùng API quản lý giao dịch đã lỗi thời. Những khác biệt giữa PostgreSQL, MySQL, SQL Server và các cơ sở dữ liệu khác được nêu như **quy tắc phụ thuộc sản phẩm**, không giả định mọi hệ quản trị có cùng hành vi.

## 1. Một transaction giải quyết vấn đề gì?

Giả sử một lệnh chuyển tiền được triển khai bằng hai cập nhật:

```sql
UPDATE accounts
SET balance_cents = balance_cents - 10000
WHERE id = 1;

UPDATE accounts
SET balance_cents = balance_cents + 10000
WHERE id = 2;
```

Nếu mỗi lệnh tự commit và lệnh thứ hai thất bại, lệnh đầu đã được xác nhận nên hệ thống có thể mất tính nhất quán. Đúng hơn, cả hai lệnh nằm trong một transaction:

```text
                    ┌────────── TRANSACTION ──────────┐
                    │ Trừ tiền A                       │
Bắt đầu giao dịch ──┤ Cộng tiền B                      ├──► COMMIT
                    │ Kiểm tra điều kiện nghiệp vụ     │    nếu tất cả thành công
                    └───────────────┬─────────────────┘
                                    └─────────────────► ROLLBACK
                                                         nếu có lỗi cần hủy
```

Kết quả mong muốn:

- **Thành công:** cả số dư A và B được cập nhật và commit.
- **Thất bại:** không để lại trạng thái chỉ trừ hoặc chỉ cộng một bên.

**Transaction không tự kiểm tra mọi quy tắc nghiệp vụ.** Ứng dụng vẫn phải kiểm tra số dư, số hàng bị cập nhật, ràng buộc khóa chính, unique, foreign key, giới hạn số tiền, quyền truy cập và hành vi đồng thời.

## 2. ACID: bốn thuộc tính thường gắn với transaction

| Thuộc tính | Ý nghĩa | Trong ví dụ chuyển tiền |
| --- | --- | --- |
| **Atomicity** — nguyên tử | Những thay đổi thuộc giao dịch được xác nhận hoặc hủy theo một đơn vị | Không chỉ trừ A mà quên cộng B |
| **Consistency** — nhất quán | Giao dịch chuyển database giữa các trạng thái hợp lệ theo ràng buộc và quy tắc được thiết kế | Số dư không âm, khóa tài khoản hợp lệ |
| **Isolation** — cô lập | Điều chỉnh cách các giao dịch đồng thời quan sát/ảnh hưởng lẫn nhau | Hai lệnh rút tiền không cùng tiêu một số dư |
| **Durability** — bền vững | Sau khi commit thành công, dữ liệu được duy trì theo bảo đảm của DBMS và cấu hình lưu trữ | Không mất giao dịch đã xác nhận theo hợp đồng độ bền |

ACID là mục tiêu và hợp đồng của **hệ thống quản lý giao dịch**, không phải bốn flag bật tắt bằng một lệnh JDBC. Đặc biệt:

- Một giao dịch vẫn có thể commit dữ liệu **sai nghiệp vụ** nếu ứng dụng không kiểm tra điều kiện và database không có ràng buộc thích hợp.
- Isolation level ảnh hưởng đến hiện tượng khi giao dịch chạy đồng thời; **không phải mức cao hơn luôn miễn phí**.
- Durability phụ thuộc cơ chế và cấu hình lưu trữ của DBMS, không phải do `Connection.commit()` tự làm cho mọi hệ thống ngoài database trở nên bền vững.

## 3. Ranh giới giao dịch nằm trên Connection

Trong JDBC, một `Connection` đại diện một phiên kết nối với database. Các câu SQL được thực thi trên **cùng Connection** sẽ tham gia vào ranh giới giao dịch của Connection đó khi auto-commit đã tắt.

```java
import java.sql.Connection;

Connection connection = dataSource.getConnection();
connection.setAutoCommit(false);

// Các PreparedStatement tạo từ connection này
// tham gia giao dịch đang được quản lý bởi connection.
```

Đoạn trên là minh họa trong ngữ cảnh ứng dụng có `dataSource` phù hợp; phần sau có chương trình chạy riêng với `DriverManager`.

**Không thể nhóm hai câu lệnh vào cùng một transaction chỉ vì chúng chạy trong cùng phương thức Java.** Nếu một câu dùng Connection A, câu kia dùng Connection B, chúng thường là **hai phiên/giao dịch khác nhau**. Dùng `DataSource.getConnection()` hai lần không đảm bảo hai lời gọi trả cùng một phiên.

### 3.1. JDBC connection không phải đối tượng chia sẻ tự do giữa nhiều task

Đối với transaction cục bộ (*local transaction*), nên giữ Connection trong **một phạm vi công việc được sở hữu rõ ràng**, không đồng thời sử dụng một Connection từ nhiều virtual threads hoặc tasks khác nhau.

Một connection pool có thể cấp Connection cho nhiều request, nhưng mỗi request/transaction cần mượn connection theo quy tắc của pool và **trả lại khi hoàn thành**. Pool không biến một Connection đang giao dịch thành một tài nguyên có thể dùng chung không kiểm soát.

## 4. Auto-commit: vì sao mặc định nguy hiểm cho nghiệp vụ nhiều bước?

Theo hợp đồng JDBC, Connection mới **mặc định bật auto-commit**. Khi đó mỗi câu SQL thông thường được thực hiện và commit như một giao dịch riêng sau khi statement hoàn thành.

```java
try (Connection connection = dataSource.getConnection()) {
    System.out.println(connection.getAutoCommit());
    // Với một Connection JDBC mới theo contract mặc định: true.
}
```

**Thời điểm statement được coi là hoàn thành** không giống nhau cho mọi câu SQL:

- Với DML như `INSERT`, `UPDATE`, `DELETE`, statement thường hoàn thành khi việc thực thi xong.
- Với `SELECT` trả `ResultSet`, statement có thể chưa hoàn thành theo hợp đồng auto-commit cho tới khi `ResultSet` liên quan được đóng.
- Với stored procedure hoặc nhiều result sets, còn phải xử lý các kết quả và update counts theo contract.

Vì vậy không nên suy luận đơn giản “auto-commit luôn commit ngay sau dòng `executeQuery()`” nếu result set vẫn đang mở.

### 4.1. Tắt auto-commit trước khi thực hiện nhiều thay đổi

```java
connection.setAutoCommit(false);

try {
    updateFirstRecord(connection);
    updateSecondRecord(connection);
    connection.commit();
} catch (SQLException error) {
    connection.rollback();
    throw error;
}
```

Đây là **khung minh họa**, các hàm `updateFirstRecord`/`updateSecondRecord` cần được cài đặt, và code thực tế còn phải bảo toàn lỗi rollback, đóng connection và xử lý RuntimeException.

Cần phân biệt:

- `setAutoCommit(false)` **không phải** một lệnh SQL `BEGIN` bất biến trên mọi DBMS; JDBC driver quản lý việc bắt đầu giao dịch theo contract khi có hoạt động phù hợp.
- Khi auto-commit tắt, `commit()` và `rollback()` mới là các điểm kết thúc giao dịch.
- Sau `commit()` hoặc `rollback()`, Connection vẫn có thể dùng tiếp cho giao dịch mới; nó **không bị đóng** bởi các lệnh này.

### 4.2. Đổi auto-commit giữa giao dịch có thể tự commit!

Một quy tắc rất dễ gây lỗi:

> Nếu gọi `setAutoCommit(...)` **và trạng thái auto-commit thực sự thay đổi khi đang có transaction**, transaction hiện tại được commit theo hợp đồng `Connection.setAutoCommit`.

```java
connection.setAutoCommit(false);
updateAccount(connection);

// KHÔNG làm như một cách "hủy" hay "dọn":
connection.setAutoCommit(true); // Có thể COMMIT transaction đang mở!
```

Muốn hủy, **gọi `rollback()` trước**. Muốn xác nhận, **gọi `commit()` trước**.

Nếu gọi `setAutoCommit` với giá trị không làm thay đổi mode hiện tại thì đó là no-op theo hợp đồng JDBC. Nhưng không nên xây logic transaction dựa trên việc đổi mode ở giữa nghiệp vụ.

### 4.3. Không đặt cấu hình Connection bằng SQL khi JDBC đã có API

Khi JDBC cung cấp `setAutoCommit` hoặc `setTransactionIsolation`, nên dùng API JDBC thay vì tự gửi những câu SQL thay đổi cấu hình Connection rồi kỳ vọng JDBC driver biết trạng thái mới. Điều này đặc biệt quan trọng với connection pool, nơi pool theo dõi và phục hồi session state.

## 5. Commit: xác nhận transaction

`Connection.commit()` xác nhận mọi thay đổi được thực hiện trong giao dịch hiện tại theo quy tắc của DBMS và giải phóng các khóa liên quan do transaction giữ theo contract.

```java
connection.setAutoCommit(false);

try (PreparedStatement statement = connection.prepareStatement(
        "UPDATE accounts SET balance_cents = balance_cents + ? WHERE id = ?")) {

    statement.setLong(1, 5000L);
    statement.setLong(2, 2L);

    int affected = statement.executeUpdate();
    if (affected != 1) {
        throw new SQLException("Không tìm thấy đúng một tài khoản");
    }

    connection.commit();
}
```

Đây là fragment mô tả nguyên tắc, không phải phương thức hoàn chỉnh xử lý mọi lỗi. Điểm quan trọng là `executeUpdate()` cho biết số hàng chịu tác động; không nên commit chỉ vì câu SQL **không ném exception** nếu nghiệp vụ còn đòi hỏi đúng một hàng được sửa.

### 5.1. Commit thất bại có thể có trạng thái không chắc chắn

Nếu `commit()` ném `SQLException` vì mạng bị ngắt hoặc kết nối tới database mất đúng thời điểm xác nhận, ứng dụng có thể **không biết chắc transaction đã commit trên server hay chưa**. Ném exception không tự động chứng minh database đã rollback.

Cách xử lý ở cấp hệ thống:

1. Ghi nhận sự kiện và nguyên nhân lỗi bằng cơ chế logging an toàn.
2. Xem Connection đang gặp lỗi là **không đáng tin cậy** nếu không xác nhận lại được trạng thái.
3. Dùng **idempotency key**, mã giao dịch duy nhất, sổ cái hoặc cơ chế đối soát để tránh ghi trùng khi retry.
4. Không tự động retry thao tác chuyển tiền chỉ vì nhận lỗi kết nối trong hoặc ngay sau `commit()`.

Đây là lý do giao dịch tài chính cần thiết kế idempotency và reconciliation, không chỉ dựa vào một khối `try/catch`.

## 6. Rollback: hủy toàn bộ những thay đổi chưa commit

`Connection.rollback()` yêu cầu DBMS hủy các thay đổi trong **transaction hiện tại**, quay về trạng thái trước transaction đó.

```java
connection.setAutoCommit(false);

try {
    updateOrder(connection);
    updateInventory(connection);
    connection.commit();
} catch (SQLException | RuntimeException failure) {
    try {
        connection.rollback();
    } catch (SQLException rollbackError) {
        failure.addSuppressed(rollbackError);
    }
    throw failure;
}
```

Ở đây các hàm update chỉ là minh họa; chưa bao gồm quản lý Connection bằng `try-with-resources`.

Cách xử lý rollback lỗi có chủ đích:

- Giữ lại **lỗi ban đầu** để người điều tra biết vì sao nghiệp vụ thất bại.
- Nếu `rollback()` cũng thất bại, gắn lỗi rollback vào `failure` bằng `addSuppressed(...)` thay vì thay mất nguyên nhân.
- Không coi rollback thành công là bằng chứng mọi tác dụng phụ **ngoài database** cũng được đảo ngược.

### 6.1. Rollback không hoàn tác các hiệu ứng ngoài giao dịch

Các hành động sau **không tự rollback** cùng một transaction JDBC:

- Email đã gửi hoặc notification đã push.
- Một HTTP request đã được hệ thống khác xử lý.
- File đã được ghi lên hệ thống file.
- Message đã được publish tới message broker mà không có cùng cơ chế giao dịch phối hợp.
- Các thao tác ghi vào **database khác trên Connection khác**.

Nếu cần tính nhất quán giữa database và hệ thống ngoài, cân nhắc các mẫu được hỗ trợ hiện nay như **transactional outbox**, thiết kế idempotency, hoặc saga/compensation theo ranh giới hệ thống. Một transaction JDBC cục bộ chỉ bao phủ tài nguyên mà connection quản lý, không biến mọi dịch vụ thành một giao dịch phân tán.

## 7. Commit, rollback và close là ba thao tác khác nhau

| Lệnh | Tác dụng chính | Có đóng Connection không? | Có xác nhận thay đổi không? |
| --- | --- | --- | --- |
| `commit()` | Kết thúc transaction bằng xác nhận | Không | Có |
| `rollback()` | Kết thúc transaction bằng hủy | Không | Không |
| `close()` | Giải phóng Connection/tài nguyên JDBC | Có, theo contract | **Không được dùng như cách quyết định commit/rollback** |
| `setAutoCommit(true)` | Đổi mode quản lý transaction | Không | Có thể **commit transaction hiện tại** nếu mode thay đổi |

Javadoc của `Connection.close()` cảnh báo: nếu đóng một connection khi vẫn còn transaction đang hoạt động, **kết quả là implementation-defined**. Vì vậy ứng dụng phải commit hoặc rollback **tường minh trước khi close**.

### 7.1. Tại sao try-with-resources chưa đủ?

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    executeBusinessStatements(connection);
}
// KHÔNG đảm bảo tự rollback theo contract JDBC.
```

`try-with-resources` bảo đảm lời gọi `close()`, nhưng **không thay** một nhánh `commit()`/`rollback()` chủ động.

Trong thực tế, `Connection.close()` ở một pool thường trả wrapper về pool thay vì đóng socket vật lý ngay, nhưng đó là **contract của pool**, không phải lý do để bỏ giao dịch chưa hoàn tất. Cần hiểu pool reset state và xử lý connection lỗi thế nào.

## 8. Ví dụ đầy đủ: chuyển tiền dùng một JDBC transaction

Chương trình dưới đây dùng API Java SE 27 và SQL PostgreSQL cho một bài thực hành. PostgreSQL JDBC driver là **dependency bên ngoài JDK**; phải đưa driver tương ứng vào runtime. Các API `Connection`, `PreparedStatement` và `DriverManager` vẫn là JDBC chuẩn.

### 8.1. Chuẩn bị database thử nghiệm

Tạo database thử nghiệm `jdbc_lab` theo cách quản trị PostgreSQL của môi trường, rồi thực hiện:

```sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    balance_cents BIGINT NOT NULL CHECK (balance_cents >= 0)
);

INSERT INTO accounts (id, balance_cents) VALUES
    (1, 200000),
    (2, 50000);
```

Dùng số nguyên **đơn vị tiền nhỏ nhất** trong demo để tránh lỗi làm tròn từ `double`. Với tiền tệ/đơn vị phức tạp hơn, có thể dùng `DECIMAL/NUMERIC` và `BigDecimal` theo chính sách precision/scale của sản phẩm.

Đặt biến môi trường cho ứng dụng:

```text
JDBC_URL=jdbc:postgresql://localhost:5432/jdbc_lab
JDBC_USER=lab_user
JDBC_PASSWORD=<mật khẩu được cấp>
```

Đây là **tên biến môi trường mẫu**, không phải chuỗi cấu hình được commit vào source control. Tài khoản DB cần quyền phù hợp và được tạo riêng cho môi trường thử nghiệm.

### 8.2. Mã Java hoàn chỉnh

Tạo file `JdbcTransactionDemo.java`:

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.Objects;

public final class JdbcTransactionDemo {

    private JdbcTransactionDemo() {}

    public static void main(String[] args) throws SQLException {
        String url = Objects.requireNonNull(
                System.getenv("JDBC_URL"), "Thiếu JDBC_URL");
        String user = Objects.requireNonNull(
                System.getenv("JDBC_USER"), "Thiếu JDBC_USER");
        String password = Objects.requireNonNull(
                System.getenv("JDBC_PASSWORD"), "Thiếu JDBC_PASSWORD");

        transfer(url, user, password, 1L, 2L, 10_000L);
        System.out.println("Đã chuyển 10000 đơn vị tiền nhỏ nhất.");
    }

    static void transfer(
            String url, String user, String password,
            long sourceId, long targetId, long amountCents)
            throws SQLException {

        if (sourceId == targetId || amountCents <= 0) {
            throw new IllegalArgumentException(
                    "Hai tài khoản phải khác nhau và số tiền phải dương");
        }

        try (Connection connection =
                     DriverManager.getConnection(url, user, password)) {

            // Cơ sở JDBC: hai câu UPDATE sẽ cùng một transaction.
            connection.setAutoCommit(false);

            try {
                int debitCount;
                try (PreparedStatement debit =
                             connection.prepareStatement(
                                     "UPDATE accounts "
                                   + "SET balance_cents = balance_cents - ? "
                                   + "WHERE id = ? AND balance_cents >= ?")) {

                    debit.setLong(1, amountCents);
                    debit.setLong(2, sourceId);
                    debit.setLong(3, amountCents);
                    debitCount = debit.executeUpdate();
                }

                if (debitCount != 1) {
                    throw new SQLException(
                            "Tài khoản nguồn không tồn tại hoặc không đủ số dư");
                }

                int creditCount;
                try (PreparedStatement credit =
                             connection.prepareStatement(
                                     "UPDATE accounts "
                                   + "SET balance_cents = balance_cents + ? "
                                   + "WHERE id = ?")) {

                    credit.setLong(1, amountCents);
                    credit.setLong(2, targetId);
                    creditCount = credit.executeUpdate();
                }

                if (creditCount != 1) {
                    throw new SQLException("Tài khoản đích không tồn tại");
                }

                connection.commit();
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    failure.addSuppressed(rollbackError);
                }
                throw failure;
            }
        }
    }
}
```

Để chạy trên JDK 27, cần đặt **JDBC driver PostgreSQL** tương thích trên classpath/module path phù hợp với cách triển khai, rồi biên dịch và chạy lớp. JDK chỉ cung cấp JDBC API, **không tích hợp sẵn driver PostgreSQL**.

Với dữ liệu ban đầu như ở trên, một lần chạy thành công sẽ để lại:

| Tài khoản | Trước khi chuyển | Sau khi chuyển |
| --- | ---: | ---: |
| `id = 1` | 200000 | 190000 |
| `id = 2` | 50000 | 60000 |
| **Tổng** | **250000** | **250000** |

Các con số tính theo đơn vị nhỏ nhất. Nếu chạy chương trình nhiều lần mà không reset database, số dư sẽ tiếp tục thay đổi; không nên hiểu bảng này là kết quả bất biến sau mọi lần chạy.

### 8.3. Vì sao mã được tổ chức như vậy?

1. **Một Connection:** cả hai `UPDATE` dùng cùng một kết nối, nên tham gia một transaction.
2. **Auto-commit tắt:** không câu `UPDATE` nào tự xác nhận đơn lẻ.
3. **`PreparedStatement`:** dữ liệu được bind bằng tham số `?`, không ghép chuỗi đầu vào vào SQL.
4. **Điều kiện `balance_cents >= ?`:** kiểm tra đủ tiền **ngay trong câu `UPDATE`**, giảm nguy cơ lỗi do đọc số dư rồi ghi sau.
5. **Kiểm tra số hàng:** nếu tài khoản không tồn tại hoặc điều kiện không thỏa, ném exception trước commit.
6. **`commit()` duy nhất:** chỉ xác nhận khi cả ghi nợ và ghi có hoàn tất.
7. **`rollback()` khi lỗi:** yêu cầu hủy giao dịch và giữ cả lỗi rollback nếu phát sinh.
8. **`try-with-resources`:** đóng `PreparedStatement` và `Connection` ngay cả khi có exception.

Ví dụ dùng `DriverManager` để tự chứa về phần Java và dễ thấy ranh giới Connection. Trong ứng dụng production, ưu tiên lấy kết nối từ `DataSource` và connection pool được cấu hình phù hợp; **không chia sẻ Connection đang có transaction giữa các request**.

### 8.4. Giới hạn của demo chuyển tiền

Đây là **ví dụ transaction**, chưa phải hệ thống thanh toán production. Cần bổ sung:

- Idempotency key và bảng giao dịch/sổ cái để tránh thực hiện trùng khi client retry.
- Quy tắc chống overflow ở cột nhận tiền và xác thực đơn vị tiền.
- Cơ chế phân quyền và xác thực chủ tài khoản.
- Chính sách xử lý deadlock, serialization failure và lỗi commit không rõ kết quả.
- Transaction timeout, giám sát và hạn mức kết nối.
- Quy định khi hai lệnh chuyển tiền đồng thời giữa cùng hai tài khoản.
- Audit trail thích hợp, bảo đảm không có side effect bên ngoài transaction một cách vô tình.

Câu `UPDATE ... WHERE balance_cents >= ?` tránh một dạng **check-then-act race** phổ biến; nó không thay thế toàn bộ thiết kế đồng thời và sổ cái.

## 9. Savepoint: điểm quay lui bên trong cùng một transaction

Một **savepoint** đánh dấu vị trí trong transaction. Gọi `rollback(savepoint)` hủy các thay đổi **sau điểm đánh dấu** nhưng giữ các thay đổi **trước điểm đó** trong trạng thái **chưa commit**.

```text
Transaction mở (autoCommit=false)
  │
  ├─ A: cập nhật đơn hàng       ──► thay đổi A chưa commit
  │
  ├─ SAVEPOINT S
  │
  ├─ B: ghi metadata tùy chọn   ──► thay đổi B chưa commit
  │
  ├─ ROLLBACK TO S             ──► hủy B, vẫn giữ A chưa commit
  │
  ├─ C: cập nhật thống kê hợp lệ
  │
  └─ COMMIT                    ──► xác nhận A và C
```

Điểm mấu chốt:

- `rollback(savepoint)` **không kết thúc transaction** và không tương đương `commit()`.
- Nếu sau đó gọi `rollback()` **không tham số**, cả A và C chưa commit đều bị hủy.
- Nếu sau đó `commit()`, những thay đổi còn lại sẽ được xác nhận.
- Savepoint **không phải nested transaction độc lập**. Nó không có commit riêng, không biến một lệnh bên trong thành giao dịch phân tán.

### 9.1. Tạo savepoint có tên hoặc không tên

```java
import java.sql.Savepoint;

connection.setAutoCommit(false);

Savepoint checkpoint = connection.setSavepoint();
Savepoint named = connection.setSavepoint("before_optional_note");
```

Lưu ý:

- `setSavepoint()` trả về một `Savepoint` không tên do driver quản lý ID.
- `setSavepoint("name")` trả về savepoint có tên.
- `Savepoint.getSavepointId()` chỉ phù hợp với savepoint **không tên**.
- `Savepoint.getSavepointName()` chỉ phù hợp với savepoint **có tên**.
- Gọi getter không phù hợp có thể ném `SQLException`; không nên dùng cả hai getter như thể lúc nào cũng có dữ liệu.

### 9.2. Không dùng savepoint ở auto-commit mode

`Connection.setSavepoint(...)` yêu cầu Connection **không ở auto-commit mode**. Driver có thể ném `SQLException` nếu auto-commit vẫn bật hoặc nếu đang tham gia phân tán transaction không hỗ trợ lệnh đó.

```java
// Sai về bối cảnh:
// connection.setAutoCommit(true);
// Savepoint point = connection.setSavepoint(); // SQLException
```

Tạo savepoint không tự bật/tắt auto-commit; cần tổ chức transaction đúng từ đầu.

## 10. Ví dụ rollback một phần mà vẫn commit phần chính

Giả sử một giao dịch ghi đơn hàng bắt buộc thành công, trong khi thông tin *ghi chú nội bộ* là tùy chọn. Sau khi ghi đơn hàng, có thể đánh dấu điểm quay lui trước khi ghi ghi chú.

Đoạn minh họa nằm **bên trong một transaction đã tắt auto-commit** và giả định có hai bảng `orders`, `order_notes` cùng các khóa phù hợp:

```java
// Đã tắt auto-commit và kiểm tra driver hỗ trợ savepoint.
insertOrder(connection, orderId);

Savepoint beforeOptionalNote =
        connection.setSavepoint("before_optional_note");

try {
    insertOptionalNote(connection, orderId, note);
    connection.releaseSavepoint(beforeOptionalNote);
} catch (SQLException noteError) {
    // Chỉ được bỏ qua nếu lỗi này THỰC SỰ là lỗi cho phép
    // không có ghi chú, theo chính sách nghiệp vụ.
    if (!isAllowedOptionalNoteFailure(noteError)) {
        throw noteError;
    }

    connection.rollback(beforeOptionalNote);
    connection.releaseSavepoint(beforeOptionalNote);
}

// Giao dịch chính vẫn đang mở.
connection.commit();
```

Đây là **fragment kiến trúc**, các hàm `insertOrder`, `insertOptionalNote`, `isAllowedOptionalNoteFailure` cần được cài đặt theo database và chính sách nghiệp vụ. Bao quanh nó vẫn phải có xử lý rollback **toàn transaction** cho mọi lỗi không được phép bỏ qua.

**Không bắt mọi `SQLException` rồi bỏ qua sau `rollback(savepoint)`.** Lỗi mất kết nối, deadlock, thiếu bảng hoặc hỏng transaction không tương đương một lỗi metadata tùy chọn. Chỉ coi một lỗi là có thể bỏ qua khi nó được phân loại và kiểm chứng chính xác theo nghiệp vụ, ví dụ một ràng buộc cụ thể đã được dự kiến.

Một lưu ý thực tế: với PostgreSQL, khi câu SQL trong transaction phát sinh lỗi, các lệnh tiếp theo có thể bị từ chối cho đến khi transaction được rollback hoặc rollback về savepoint thích hợp. Đây là một lý do cần đặt savepoint **trước** câu lệnh có thể lỗi. Nhưng quy tắc xử lý lỗi cụ thể phải được xác nhận theo DBMS/driver.

### 10.1. Release savepoint khác commit

`connection.releaseSavepoint(point)` giải phóng **điểm đánh dấu**, không commit transaction. Theo contract JDBC, việc release một savepoint còn có thể vô hiệu hóa các savepoint được đặt **sau nó**. Không nên giữ đối tượng `Savepoint` rồi sử dụng lại sau khi nó đã được release hoặc transaction đã kết thúc.

`rollback(savepoint)` cũng làm mất hiệu lực những savepoint được tạo sau điểm quay về. Với nhiều lớp savepoint, cần tổ chức thứ tự tạo/rollback/release theo stack logic thay vì giữ tham chiếu tùy ý.

## 11. Kiểm tra database và driver có hỗ trợ savepoint không

Không phải mọi database/driver đều hỗ trợ mọi tính năng JDBC. Hãy kiểm tra:

```java
import java.sql.DatabaseMetaData;
import java.sql.SQLFeatureNotSupportedException;

DatabaseMetaData metadata = connection.getMetaData();

if (!metadata.supportsSavepoints()) {
    throw new SQLFeatureNotSupportedException(
            "Database/driver không hỗ trợ savepoint");
}
```

Tùy theo driver, khi gọi `setSavepoint`, `rollback(Savepoint)` hoặc `releaseSavepoint` vẫn có thể gặp `SQLFeatureNotSupportedException`/`SQLException`.

**Đừng dùng savepoint như tính năng tất yếu của tất cả database**. Nếu nghiệp vụ yêu cầu rollback một phần, có thể:

- Chọn database/driver được kiểm chứng hỗ trợ savepoint.
- Thiết kế lại một đơn vị công việc để không cần tiếp tục sau lỗi.
- Đưa thao tác tùy chọn thành công việc độc lập **sau commit** khi điều đó phù hợp, với cơ chế idempotency/outbox nếu cần.

Với ứng dụng phục vụ nhiều DBMS, phải kiểm thử tình huống rollback và retry trên đúng từng engine. Chỉ kiểm tra `supportsSavepoints()` là bước đầu, không thay thế integration test.

## 12. Transaction isolation: khi nhiều transaction chạy đồng thời

Một transaction có thể đúng khi chạy một mình nhưng sai khi hai client cùng đọc/ghi. JDBC cung cấp những hằng số isolation level trên `Connection`:

| Isolation level | Dirty read | Non-repeatable read | Phantom read |
| --- | --- | --- | --- |
| `TRANSACTION_READ_UNCOMMITTED` | Có thể | Có thể | Có thể |
| `TRANSACTION_READ_COMMITTED` | Ngăn theo định nghĩa JDBC | Có thể | Có thể |
| `TRANSACTION_REPEATABLE_READ` | Ngăn | Ngăn | Có thể |
| `TRANSACTION_SERIALIZABLE` | Ngăn | Ngăn | Ngăn |

Bảng trên trình bày **bảo đảm tối thiểu theo JDBC** cho ba hiện tượng chuẩn:

- **Dirty read:** đọc dữ liệu chưa commit của transaction khác.
- **Non-repeatable read:** hai lần đọc cùng hàng trong một transaction có thể nhận giá trị khác sau commit của transaction khác.
- **Phantom read:** cùng một điều kiện truy vấn nhận tập hàng khác nhau do transaction khác thay đổi các hàng phù hợp.

Cách triển khai thực tế theo **MVCC, khóa hoặc snapshot** khác nhau giữa các DBMS. Một mức isolation có thể ngăn thêm hiện tượng khác, hoặc engine có quy tắc riêng đối với serialization failures, write skew và row locks.

### 12.1. Đọc và thay đổi isolation level

```java
int previousIsolation = connection.getTransactionIsolation();

boolean supported = connection.getMetaData()
        .supportsTransactionIsolationLevel(
                Connection.TRANSACTION_SERIALIZABLE);

if (!supported) {
    throw new SQLFeatureNotSupportedException(
            "SERIALIZABLE không được hỗ trợ");
}

connection.setTransactionIsolation(
        Connection.TRANSACTION_SERIALIZABLE);
```

Trong code ví dụ này, cần import `java.sql.Connection` và `java.sql.SQLFeatureNotSupportedException`; nó là **fragment cấu hình**, không phải một transaction hoàn chỉnh.

Nên đặt isolation **trước khi transaction bắt đầu**, không đổi giữa một transaction đang hoạt động. Javadoc nêu kết quả thay đổi isolation giữa transaction **phụ thuộc implementation**. Nếu dùng connection pool, việc restore isolation sau transaction cũng cần được thực hiện theo policy của pool khi connection đang ở trạng thái an toàn.

### 12.2. Isolation không thay thế concurrency control

Ngay cả khi dùng isolation level hợp lý, một mô hình “đọc giá trị → tính toán trong Java → ghi đè giá trị” có thể gây **lost update** nếu không có chiến lược bảo vệ.

Ví dụ anti-pattern:

```java
// Hai giao dịch có thể cùng đọc version/số dư cũ.
// long amount = readBalance(connection, id);
// updateBalance(connection, id, amount - 1000);
```

Những cách hiện đại để bảo vệ gồm:

- Một câu `UPDATE` có điều kiện và phép cộng/trừ **trong database**.
- **Optimistic locking** bằng cột `version`, cập nhật `WHERE id = ? AND version = ?` rồi kiểm tra số hàng.
- Khóa hàng có chủ đích, ví dụ `SELECT ... FOR UPDATE` nếu DBMS hỗ trợ và policy cho phép.
- Mức isolation cao hơn và xử lý retry cho serialization failure.

Chọn chiến lược theo mô hình dữ liệu, contention, isolation semantics và DBMS thực tế; không có một cách đơn giản đúng cho mọi hệ thống.

## 13. Optimistic locking và kiểm tra số hàng cập nhật

Một mô hình dùng cột version:

```sql
CREATE TABLE documents (
    id BIGINT PRIMARY KEY,
    version BIGINT NOT NULL,
    content TEXT NOT NULL
);
```

Khi cập nhật, ứng dụng biết phiên bản đã đọc trước đó, ví dụ `version = 5`:

```sql
UPDATE documents
SET content = ?, version = version + 1
WHERE id = ? AND version = ?;
```

Trong Java:

```java
try (PreparedStatement update = connection.prepareStatement(
        "UPDATE documents "
      + "SET content = ?, version = version + 1 "
      + "WHERE id = ? AND version = ?")) {

    update.setString(1, newContent);
    update.setLong(2, documentId);
    update.setLong(3, expectedVersion);

    int changed = update.executeUpdate();
    if (changed != 1) {
        throw new SQLException(
                "Dữ liệu đã bị thay đổi hoặc không còn tồn tại");
    }
}
```

Đoạn là fragment có các biến đã được cung cấp từ ngữ cảnh. Nếu một request khác đã tăng version, điều kiện `version = ?` không còn đúng và số hàng cập nhật bằng 0. Điều này cho phép code phát hiện **xung đột** thay vì vô tình ghi đè dữ liệu mới.

Với nhiều bảng trong một giao dịch, vẫn cần `commit()` sau khi tất cả điều kiện thành công; optimistic locking **không phải cách thay thế transaction**.

## 14. Deadlock, serialization failure và chính sách retry

Khi hai transaction cập nhật các tài nguyên theo thứ tự đối nghịch, DBMS có thể phát hiện **deadlock** rồi hủy một transaction. Ở isolation cao, transaction cũng có thể thất bại do **serialization conflict**.

Ví dụ về thứ tự cập nhật:

```text
Transaction A: khóa tài khoản 1 ──► muốn khóa tài khoản 2
Transaction B: khóa tài khoản 2 ──► muốn khóa tài khoản 1
```

Cả hai có thể chờ nhau. Một số biện pháp giảm khả năng:

1. **Truy cập các hàng theo thứ tự khóa nhất quán** trong mọi giao dịch.
2. Giữ transaction **ngắn**, không gọi HTTP hay chờ tương tác người dùng khi đang giữ lock.
3. Chỉ mở transaction khi chuẩn bị thao tác DB.
4. Cấu hình lock timeout, statement timeout và giới hạn kết nối phù hợp với DBMS.
5. Đọc SQLState/exception theo driver để phân loại deadlock, serialization failure, vi phạm ràng buộc hay lỗi kết nối.

### 14.1. Nếu retry, phải retry toàn bộ đơn vị công việc

Khi database báo một lỗi được phân loại **có thể retry**, không thể tùy tiện chỉ chạy lại câu SQL cuối cùng vì trạng thái/khóa của transaction cũ có thể không còn hợp lệ. Quy trình thường là:

```text
Bắt đầu transaction
  ├── Thực hiện toàn bộ các bước DB
  ├── Commit
  ├── Thành công ─► kết thúc
  └── Lỗi được phân loại retryable
         ├── Rollback / hủy connection lỗi
         ├── Chờ ngắn có jitter, giới hạn số lần
         └── Bắt đầu lại từ transaction mới
```

Không retry vô hạn. Với lỗi **kết quả commit không chắc chắn**, phải tra cứu bằng idempotency key hoặc đối soát trước khi thực hiện lại tác dụng nghiệp vụ.

Mã lỗi SQLState có các nhóm và quy ước riêng; không giả định một bảng mapping là giống nhau trên mọi database/driver. Các subclass như `SQLTransactionRollbackException` và `SQLTransientException` cung cấp thêm tín hiệu, nhưng không thay thế chính sách retry đã được kiểm chứng cho driver cụ thể.

## 15. SQLException và bảo toàn nguyên nhân khi cleanup

Phần thân transaction có thể thất bại, sau đó `rollback()` cũng có thể ném lỗi do kết nối mất. Một lỗi cleanup **không nên vô tình che lấp lỗi ban đầu**.

Mẫu:

```java
try {
    performChanges(connection);
    connection.commit();
} catch (SQLException | RuntimeException failure) {
    try {
        connection.rollback();
    } catch (SQLException rollbackFailure) {
        failure.addSuppressed(rollbackFailure);
    }
    throw failure;
}
```

Nên kết hợp với `try-with-resources` bên ngoài để giải phóng connection và statements. Bản thân try-with-resources cũng hỗ trợ **suppressed exceptions** khi `close()` thất bại trong lúc đã có ngoại lệ chính.

Một số thông tin để log ở backend:

- `SQLException.getSQLState()` — mã SQLState theo driver/DBMS.
- `SQLException.getErrorCode()` — mã vendor-specific.
- `SQLException.getNextException()` — các lỗi SQL liên kết nếu driver cung cấp.
- Tên thao tác nghiệp vụ, correlation ID, connection/transaction ID an toàn và elapsed time.

**Không log mật khẩu, chuỗi kết nối có credentials hoặc dữ liệu cá nhân nhạy cảm**. Với hệ thống chịu tải lớn, cần tránh log toàn bộ tham số SQL của người dùng mà không có chính sách bảo vệ dữ liệu.

## 16. Cấu hình isolation, auto-commit và connection pool

Trong ứng dụng thật, thường dùng `javax.sql.DataSource` để lấy connection. Nhiều `DataSource` được triển khai bởi connection pool, nhưng JDBC không bắt buộc mọi DataSource đều là pool.

```java
import javax.sql.DataSource;
import java.sql.Connection;

static void performUnitOfWork(DataSource dataSource) throws Exception {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);

        try {
            // Các câu SQL của cùng giao dịch.
            performBusinessSql(connection);
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

Đây là ví dụ khung, `performBusinessSql` phải được cài đặt. Quy trình dùng Connection theo scope và **đóng sau khi đã commit/rollback**, nhưng code production cần thêm chính sách xử lý Connection trạng thái không chắc chắn nếu commit/rollback lỗi.

### 16.1. Tại sao phải hiểu pool reset state?

Một Connection được pool cho mượn có thể có state như:

- `autoCommit`.
- Transaction isolation.
- `readOnly`.
- Catalog/schema.
- Holdability và session settings khác.
- Một transaction đã mở hoặc bị lỗi.

Pool tốt thường có logic reset/rollback khi trả Connection, nhưng bạn phải đọc **contract của pool đang sử dụng**. Không nên giả định các cờ được tự phục hồi theo một cơ chế chung do Java SE quy định.

Đặc biệt tránh hai lỗi:

1. Gọi `setAutoCommit(true)` trong `finally` **trước khi transaction được commit/rollback rõ ràng**: có thể vô tình commit.
2. Đưa Connection lỗi không rõ trạng thái về pool rồi tiếp tục dùng như thể sạch. Khi Connection không còn đáng tin, cần theo chính sách loại bỏ/evict của pool.

Nếu thư viện/framework đang **quản lý transaction** (ví dụ một transaction manager của ứng dụng), không tự ý gọi `commit`, `rollback` hoặc đóng Connection của framework nếu contract không trao quyền đó cho code hiện tại.

## 17. Savepoint không giải quyết mọi vấn đề

Savepoint chỉ hỗ trợ **rollback một phần trong transaction cục bộ** khi driver/DBMS cho phép. Nó không giúp:

- Commit độc lập một phần rồi rollback phần còn lại như nested transactions thực sự.
- Chia sẻ transaction an toàn giữa nhiều connection/database.
- Hủy email/HTTP/queue message đã gửi ra ngoài.
- Tự động giải quyết deadlock hoặc serialization failure.
- Bỏ qua mọi lỗi SQL mà database vẫn giữ session ở trạng thái an toàn.
- Tự động cải thiện hiệu năng: thêm savepoint và giữ transaction lâu hơn cũng có chi phí.

Một quy tắc thiết kế hữu ích: nếu thao tác B **phải** thành công cùng A, đừng dùng savepoint để bỏ lỗi B và vẫn commit A. Nếu B **thật sự tùy chọn**, có thể dùng savepoint hoặc tách B thành công việc sau commit, nhưng phải diễn tả rõ trạng thái và hệ quả nghiệp vụ.

## 18. Test giao dịch: xác minh cả đường thành công lẫn thất bại

Bài kiểm thử integration cần chạy với **database và driver gần với môi trường production**, đặc biệt cho isolation, savepoint và SQLState. Những trường hợp quan trọng:

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Cả hai UPDATE thành công | Commit đúng cả hai, tổng số dư bảo toàn |
| Tài khoản nguồn không đủ tiền | Debited row count bằng 0, rollback, số dư không đổi |
| Tài khoản đích không tồn tại | Đã trừ tạm nhưng rollback trả lại số dư nguồn |
| Vi phạm CHECK/unique/foreign key | Không có dữ liệu giao dịch dở dang |
| Lỗi tại câu SQL thứ hai | Lỗi được ném; transaction không được commit một phần |
| Lỗi rollback | Lỗi ban đầu còn nguyên, rollback error được gắn suppressed |
| Savepoint với thao tác tùy chọn lỗi hợp lệ | Phần trước savepoint còn, phần sau bị hủy, commit chỉ khi đúng chính sách |
| Database không hỗ trợ savepoint | Feature được phát hiện và xử lý rõ ràng |
| Hai giao dịch rút tiền đồng thời | Không rút vượt số dư; concurrency strategy hoạt động |
| Deadlock/serialization conflict | Được phát hiện và retry có giới hạn nếu phù hợp |
| Connection mất khi commit | Không retry mù; dựa vào idempotency/reconciliation |
| Đóng Connection sau transaction | Không còn transaction treo, lock và connection được giải phóng |

Không chỉ unit-test method gọi `commit()` bằng một mock rồi coi là đã kiểm thử atomicity. Tính đúng đắn phụ thuộc **database engine thật, driver, câu SQL và isolation**.

## 19. Bảng lỗi thường gặp

| Cách làm | Vấn đề | Cách khắc phục |
| --- | --- | --- |
| Chạy hai UPDATE với auto-commit mặc định | Mỗi câu có thể được commit riêng | Tắt auto-commit trước transaction nhiều bước |
| Nghĩ cùng một method Java nghĩa là cùng transaction | Có thể đang dùng hai Connection | Giữ một connection/transaction owner rõ ràng |
| Gọi `commit()` trong auto-commit mode | JDBC ném `SQLException` | Chỉ commit tường minh khi auto-commit tắt |
| Đóng connection có transaction mở và mong auto-rollback | Kết quả implementation-defined | Commit/rollback tường minh trước close |
| Gọi `setAutoCommit(true)` để “reset” sau lỗi | Có thể tự commit các thay đổi chưa xác nhận | Rollback trước; chỉ restore khi state an toàn |
| Không kiểm tra `executeUpdate()` | Có thể commit khi không có hàng nào được sửa | Kiểm tra số hàng theo business invariant |
| Bắt `SQLException` rồi quên rollback | Transaction còn mở/giữ lock | Nhánh rollback có bảo toàn lỗi |
| Rollback lỗi làm mất exception chính | Khó chẩn đoán gốc | `addSuppressed(...)` |
| Dùng `setSavepoint` khi auto-commit bật | Ném `SQLException` | Tắt auto-commit và kiểm tra hỗ trợ |
| Nghĩ `rollback(savepoint)` đã kết thúc transaction | Vẫn còn thay đổi chưa commit | Commit/rollback toàn bộ sau khi xử lý |
| Nghĩ `releaseSavepoint` commit dữ liệu | Chỉ bỏ điểm đánh dấu | Gọi `commit()` khi mọi việc hoàn tất |
| Bỏ qua mọi lỗi trong bước tùy chọn | Có thể che lỗi hạ tầng nghiêm trọng | Chỉ bỏ qua lỗi đã phân loại theo hợp đồng |
| Đổi isolation giữa transaction | Hành vi không thống nhất giữa DBMS | Cấu hình trước transaction, kiểm tra hỗ trợ |
| Đọc rồi ghi lại số dư trong Java không có guard | Lost update/check-then-act race | UPDATE có điều kiện, versioning hoặc locking |
| Giữ transaction mở trong lúc gọi HTTP | Lock lâu, tăng deadlock/timeout | Transaction ngắn, outbox khi cần phối hợp |
| Retry sau lỗi commit mạng không biết kết quả | Có thể thực hiện trùng | Idempotency key, đối soát |
| Gửi cùng Connection cho nhiều virtual threads | Transaction và session state bị chia sẻ nguy hiểm | Một connection cho mỗi transaction/task theo pool |
| Dùng `double` cho số tiền chính xác | Có thể gây lỗi biểu diễn và làm tròn | `BigDecimal` hoặc integer minor units |
| Nghĩ savepoint là nested transaction độc lập | Không có commit riêng | Dùng đúng partial rollback; xét kiến trúc khác nếu cần |

## 20. Quy trình quyết định giao dịch trong Java 27

Trước khi viết logic database nhiều bước, hãy tự trả lời:

1. **Đơn vị nghiệp vụ nào phải nguyên tử?** Xác định rõ tập thao tác cần cùng commit/rollback.
2. **Các câu SQL có dùng cùng Connection không?** Nếu không, transaction cục bộ chưa bao trùm tất cả.
3. **Auto-commit đang ở trạng thái nào?** Chỉ tắt trước khi bắt đầu đơn vị công việc.
4. **Ai sở hữu Connection?** Code tự mượn và đóng hay framework transaction manager quản lý?
5. **Điều kiện thành công có cụ thể không?** Kiểm tra số hàng cập nhật, version, constraint, business validation.
6. **Nếu có exception, rollback có được gọi không?** Giữ nguyên nhân ban đầu và suppressed failures.
7. **Có bước tùy chọn nào cho phép hủy riêng không?** Savepoint chỉ khi driver hỗ trợ và nghiệp vụ cho phép.
8. **Kết thúc transaction bằng lệnh nào?** Commit khi đủ điều kiện; rollback nếu lỗi; **không để close tự quyết**.
9. **Có nhiều giao dịch đồng thời không?** Chọn isolation/concurrency control thích hợp.
10. **Có retry không?** Chỉ retry đúng lỗi có thể retry, giới hạn số lần và đảm bảo idempotency.
11. **Có gọi dịch vụ ngoài transaction không?** Tách rõ side effect và cân nhắc outbox/saga.
12. **Đã test trên DB thật chưa?** Kiểm tra success, rollback, savepoint, deadlock, network failure và pool cleanup.

**Ghi nhớ:** Trong JDBC Java 27, **transaction gắn với Connection**, `setAutoCommit(false)` trao quyền quyết định commit/rollback cho ứng dụng, `commit()` xác nhận cả đơn vị công việc, `rollback()` hủy transaction và `rollback(savepoint)` chỉ quay lui **một phần**. Điều khó nhất không phải cú pháp JDBC mà là **đặt đúng ranh giới nghiệp vụ, quản lý lỗi và đồng thời**.

## 21. Tài liệu tham khảo chính thức Java SE 27

- [`java.sql.Connection` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/Connection.html): auto-commit, commit, rollback, close, transaction isolation, savepoint và các quy tắc với transaction đang mở.
- [`java.sql.Savepoint` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/Savepoint.html): savepoint có tên/không tên và phương thức lấy tên/ID.
- [`java.sql.DatabaseMetaData` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/DatabaseMetaData.html): `supportsSavepoints`, `supportsTransactions`, `supportsTransactionIsolationLevel` và capabilities của DBMS/driver.
- [`java.sql.PreparedStatement` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/PreparedStatement.html): bind tham số `?`, thực thi SQL và kiểm tra số hàng thay đổi.
- [`java.sql.SQLException` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/SQLException.html): SQLState, vendor error code, chained exceptions.
- [`java.sql.SQLTransactionRollbackException` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/SQLTransactionRollbackException.html): nhóm lỗi rollback transaction theo phân loại JDBC.
- [`javax.sql.DataSource` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/javax/sql/DataSource.html): lấy Connection từ nhà cung cấp nguồn dữ liệu.
- [Oracle JDBC Tutorial — Using Transactions](https://docs.oracle.com/javase/tutorial/jdbc/basics/transactions.html): các khái niệm transaction và savepoint; dùng Javadoc Java 27 làm nguồn chuẩn cho hợp đồng API hiện tại.
