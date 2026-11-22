# Quản lý autocommit, commit, rollback và tài nguyên JDBC trong PostgreSQL

Một nghiệp vụ thường cần nhiều câu SQL thành công **cùng nhau** hoặc thất bại **cùng nhau**. Ví dụ, chuyển 125.00 từ tài khoản A sang B cần trừ số dư A, cộng số dư B và ghi lịch sử giao dịch. Nếu câu trừ tiền thành công nhưng câu cộng tiền thất bại, hệ thống không được giữ trạng thái mất tiền.

Trong Java, JDBC cung cấp `Connection` để kiểm soát giao dịch PostgreSQL, `PreparedStatement` để gửi SQL với tham số, và `ResultSet` để đọc dữ liệu. Ba nhóm phương thức đặc biệt quan trọng là:

~~~java
connection.setAutoCommit(false);
connection.commit();
connection.rollback();
~~~

Và một nguyên tắc vận hành không thể tách rời:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
         connection.prepareStatement(sql)) {
    // Sử dụng statement.
} // Tài nguyên được đóng theo thứ tự ngược.
~~~

**Tuy nhiên, đóng kết nối không phải cách thay thế cho gọi `rollback()` có chủ đích.** Việc quên rollback khi có lỗi, trả connection còn mang trạng thái giao dịch vào pool, hoặc bật autocommit không đúng lúc có thể gây dữ liệu không nguyên tử, lock kéo dài, `idle in transaction` và khó tái hiện lỗi.

~~~text
Ứng dụng Java
   |
   +-- DataSource / connection pool
   |         |
   |         v
   |      Connection (một phiên PostgreSQL đang mượn)
   |         |
   |         +-- setAutoCommit(false)
   |         +-- PreparedStatement 1: trừ tiền
   |         +-- PreparedStatement 2: cộng tiền
   |         +-- PreparedStatement 3: ghi ledger
   |         |
   |         +-- Thành công tất cả? ---- Có ---> commit()
   |         |                         |
   |         |                         Không --> rollback()
   |         |
   |         +-- close() -> trả connection về pool
   |
   +-- Không được dùng cùng Connection đồng thời tùy tiện ở nhiều luồng
~~~

Bài này thuộc chương **Kết nối ứng dụng** của module *Database Engine Relational PostgreSQL*, tập trung vào cách ứng dụng JDBC quản lý **autocommit**, ranh giới `commit/rollback`, trạng thái lỗi PostgreSQL, savepoint, JDBC resources, connection pool, isolation, timeout, lập trình chuyển tiền và kiểm thử thực tế.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Mô tả vai trò của `Connection`, `Statement`/`PreparedStatement`, `ResultSet` và `DataSource`.
2. Giải thích JDBC autocommit mặc định và ranh giới transaction của từng statement.
3. Dùng `setAutoCommit(false)`, `commit()` và `rollback()` đúng cách cho nghiệp vụ nhiều câu SQL.
4. Hiểu `setAutoCommit(true)` có thể commit transaction đang hoạt động khi đổi từ `false`.
5. Phân biệt lỗi SQL làm transaction PostgreSQL rơi vào trạng thái aborted và cách khôi phục.
6. Dùng `try-with-resources` để đóng đúng kết nối, statement và result set.
7. Bảo đảm rollback khi xảy ra `SQLException` hoặc runtime exception trong một đơn vị nghiệp vụ.
8. Biết giới hạn của rollback khi `commit()` báo lỗi do mất kết nối.
9. Áp dụng `Savepoint` cho các bước con có thể hồi phục mà không hủy toàn transaction.
10. Tạo nghiệp vụ chuyển tiền có kiểm tra số hàng ảnh hưởng, khóa, transaction và nhật ký.
11. Hiểu pool trả connection cho người dùng tiếp theo và vì sao không được để rò rỉ transaction state.
12. Điều chỉnh isolation, read-only và timeout đúng phạm vi của connection/transaction.
13. Biết các ảnh hưởng của batch, streaming ResultSet, fetch size và cursor tới thời lượng transaction.
14. Nhận biết khi Spring `@Transactional` quản lý transaction thay cho JDBC thủ công.
15. Quan sát `pg_stat_activity`, `pg_locks` và các SQLSTATE phổ biến khi chẩn đoán sự cố.

## 2. JDBC là lớp giao tiếp nào?

JDBC (*Java Database Connectivity*) là tập API Java cho thao tác với database bằng driver tương ứng. Khi làm việc với PostgreSQL, ứng dụng thường sử dụng PostgreSQL JDBC Driver (**PGJDBC**).

### 2.1. Kiến trúc tổng quát

~~~text
Java service
   |
   +-- JDBC API: java.sql.*, javax.sql.DataSource
   |       |
   |       v
   |   PostgreSQL JDBC Driver
   |       |
   |       v
   |   TCP/TLS connection
   |       |
   |       v
   |   PostgreSQL backend/session
   |       |
   |       +-- transaction
   |       +-- locks
   |       +-- MVCC snapshot
   |       +-- SQL execution
~~~

### 2.2. `DataSource`

`DataSource` là giao diện cấp `Connection`. Trong ứng dụng thực tế, một implementation như connection pool thường cấp **logical connection handle** cho mỗi lượt mượn.

### 2.3. `Connection`

`Connection` đại diện cho ngữ cảnh giao tiếp với database: autocommit, isolation, read-only, transaction và tài nguyên gắn với phiên.

### 2.4. `PreparedStatement`

`PreparedStatement` lưu câu SQL có placeholders và cho phép bind tham số, giúp tách dữ liệu khỏi cú pháp SQL và tránh nối chuỗi đầu vào người dùng.

### 2.5. `ResultSet`

`ResultSet` cho phép duyệt các hàng trả về. Nó thường gắn với `Statement` và `Connection` tạo ra nó; không được trả connection về pool khi vẫn cần đọc ResultSet.

### 2.6. JDBC API không tự quyết định nghiệp vụ

JDBC cung cấp công cụ để tạo một transaction. Bạn vẫn phải xác định:

- Những câu SQL nào phải nguyên tử với nhau?
- Khi nào giao dịch đủ điều kiện commit?
- Khi nào phải rollback?
- Lỗi nào được retry?
- Khi nào khóa/snapshot cần được giữ?

## 3. Khởi tạo kết nối PostgreSQL bằng JDBC

Với PGJDBC có trên classpath, một kết nối đơn giản có thể tạo qua:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.Properties;

public class PgConnectionDemo {
    public static void main(String[] args) throws SQLException {
        String url =
            "jdbc:postgresql://db.example.internal:5432/appdb";

        Properties props = new Properties();
        props.setProperty("user", "app_user");
        props.setProperty("password", System.getenv("DB_PASSWORD"));
        props.setProperty("sslmode", "verify-full");
        props.setProperty(
            "sslrootcert", "/etc/app/certs/pg-ca.crt"
        );

        try (Connection connection =
                 DriverManager.getConnection(url, props)) {
            System.out.println(
                "AutoCommit: " + connection.getAutoCommit()
            );
        }
    }
}
~~~

Địa chỉ, CA, user và database là ví dụ; cần dùng thông tin/secret thật được quản lý đúng. Nếu biến môi trường chứa mật khẩu không có giá trị, ứng dụng nên dừng với lỗi cấu hình rõ ràng.

### 3.1. Không để lộ password

Không hardcode mật khẩu trong source control, log kết nối hoặc URL được ghi ra console. Dùng secret manager hoặc cơ chế cung cấp secret phù hợp.

### 3.2. TLS và xác minh server

`sslmode=verify-full` xác minh CA và hostname PostgreSQL. Nó không thay thế user authentication hay transaction logic.

### 3.3. Connection có chi phí

Mỗi kết nối vật lý tạo backend/session phía PostgreSQL và sử dụng tài nguyên. Trong ứng dụng nhiều requests, sử dụng pool hợp lý thường tốt hơn mở một kết nối TCP mới mỗi câu SQL.

### 3.4. Driver và framework có thể khác nhau

Ví dụ dùng JDBC thuần để làm rõ quy tắc. Spring/JPA có thể quản lý connection/transaction thay ứng dụng; không nên trộn hai mô hình tùy tiện.

## 4. Autocommit là gì?

Trong JDBC, connection mới được tạo thường ở trạng thái:

~~~java
connection.getAutoCommit(); // Thông thường: true
~~~

Khi autocommit bật, **mỗi câu SQL độc lập** được coi là đơn vị transaction của riêng nó theo quy tắc JDBC/driver; transaction được commit khi statement được xem là hoàn thành.

### 4.1. Ví dụ hai statement không nguyên tử

~~~java
try (Connection connection = dataSource.getConnection()) {
    // Giả sử connection.getAutoCommit() == true.

    try (PreparedStatement debit = connection.prepareStatement(
            "UPDATE accounts SET balance = balance - 100 " +
            "WHERE account_id = 1")) {
        debit.executeUpdate();
    }

    // Nếu lỗi ở đây, UPDATE đầu có thể đã commit.

    try (PreparedStatement credit = connection.prepareStatement(
            "UPDATE accounts SET balance = balance + 100 " +
            "WHERE account_id = 2")) {
        credit.executeUpdate();
    }
}
~~~

Nếu UPDATE trừ tiền hoàn thành rồi UPDATE cộng tiền thất bại, hai câu SQL không thuộc cùng transaction do ứng dụng điều khiển.

### 4.2. “Một câu SQL” có thể tự nguyên tử

PostgreSQL bảo đảm transaction atomicity đối với statement riêng lẻ trong phạm vi của nó. Vấn đề ở đây là **nhiều statements phải thành công cùng nhau**, không phải một UPDATE bị ghi nửa hàng.

### 4.3. Completion của SELECT và ResultSet

Theo JDBC, autocommit xảy ra khi statement hoàn thành; đối với statement trả ResultSet, việc hoàn thành liên quan tới việc tiêu thụ/đóng ResultSet theo cơ chế driver. Đừng tưởng rằng chỉ vì `executeQuery()` trả về thì mọi tài nguyên server đã được giải phóng ngay.

### 4.4. Autocommit của JDBC không phải một GUC chung của PostgreSQL

`setAutoCommit(...)` là thao tác trên **JDBC Connection**, không tương đương một tham số `SET autocommit=off` chạy trên PostgreSQL server. Driver quản lý ranh giới transaction và gửi lệnh thích hợp.

### 4.5. Kiểm tra trước khi quyết định

Đừng giả định trạng thái của một connection từ pool dựa trên kinh nghiệm. Pool/framework có thể cấu hình giá trị mặc định; gọi `getAutoCommit()` khi debugging hoặc chủ động đặt trạng thái theo hợp đồng của layer quản lý.

## 5. Tắt autocommit để tạo giao dịch nhiều câu SQL

~~~java
connection.setAutoCommit(false);
~~~

Từ lúc đó, các statement phù hợp được gom vào transaction do ứng dụng chủ động kết thúc bằng:

~~~java
connection.commit();
~~~

hoặc:

~~~java
connection.rollback();
~~~

### 5.1. Luồng chuẩn

~~~text
Lấy Connection
      |
      v
setAutoCommit(false)
      |
      v
Statement A
      |
      v
Statement B
      |
      v
Statement C
      |
      +---- Thành công tất cả ---> commit()
      |
      +---- Một bước lỗi --------> rollback()
      |
      v
Đóng resources / trả connection vào pool
~~~

### 5.2. Đừng trì hoãn commit vô hạn

Khi transaction đang hoạt động, nó có thể giữ locks, snapshots và tài nguyên PostgreSQL. Việc chờ một API bên ngoài hoặc ngủ lâu giữa hai statement có thể gây `idle in transaction` và ảnh hưởng concurrency.

### 5.3. Không commit từng bước của cùng nghiệp vụ

Nếu ba bước phải nguyên tử, gọi `commit()` sau từng bước phá mục tiêu rollback toàn bộ khi bước cuối lỗi.

### 5.4. Tránh kết nối thay đổi giữa các bước

Transaction thuộc **một connection/session cụ thể**. Nếu debit chạy trên connection A còn credit trên connection B, gọi `rollback()` trên A không tự rollback B.

## 6. BEGIN trong SQL và setAutoCommit(false)

Trong `psql`, bạn thường viết:

~~~sql
BEGIN;
UPDATE ...;
UPDATE ...;
COMMIT;
~~~

Trong JDBC, nên dùng API transaction:

~~~java
connection.setAutoCommit(false);
// statements
connection.commit();
~~~

### 6.1. Driver sẽ điều khiển transaction

PGJDBC có thể phát lệnh bắt đầu transaction khi statement đầu tiên cần chạy trong trạng thái autocommit false. Không nhất thiết có transaction server active ngay ở thời điểm Java vừa gọi `setAutoCommit(false)` mà chưa chạy SQL.

### 6.2. Đừng trộn BEGIN/COMMIT thủ công với JDBC API

Tránh:

~~~java
connection.setAutoCommit(false);
statement.execute("BEGIN");
// ...
statement.execute("COMMIT");
connection.rollback();
~~~

Việc tự gửi `BEGIN`/`COMMIT` đồng thời dùng `commit()`/`rollback()` của JDBC làm trạng thái driver và ý đồ của chương trình khó theo dõi, dễ phát sinh cảnh báo hay hành vi bất ngờ.

### 6.3. Mỗi transaction là một ranh giới rõ ràng

Hãy chọn **một chủ thể quản lý**: JDBC thủ công, transaction manager của framework, hoặc một API điều phối rõ ràng; không để nhiều layer tự commit lẫn nhau.

## 7. commit() có ý nghĩa gì?

~~~java
connection.commit();
~~~

Khi autocommit tắt, `commit()` yêu cầu PostgreSQL kết thúc transaction hiện tại bằng commit. Nếu thành công, các thay đổi trở nên có hiệu lực theo ngữ nghĩa giao dịch và có thể được quan sát bởi những transaction khác theo isolation/snapshot của họ.

### 7.1. Commit không đồng nghĩa mọi client nhìn thấy ngay

Một transaction khác đang ở `REPEATABLE READ` có thể tiếp tục nhìn snapshot cũ. Replicas cũng có thể có replication lag. Commit bảo đảm theo semantics PostgreSQL; đừng suy mọi observer đều ngay lập tức thấy thay đổi.

### 7.2. Không gọi commit trong autocommit true

Theo contract JDBC, `commit()` dùng khi autocommit tắt; gọi trong trạng thái autocommit true có thể dẫn đến `SQLException`.

### 7.3. Một commit kết thúc transaction hiện tại

Sau `commit()`, connection vẫn đang ở chế độ autocommit false nếu bạn chưa đổi. Statement tiếp theo có thể bắt đầu transaction mới. `commit()` không có nghĩa tự bật lại autocommit.

### 7.4. Commit là quyết định nghiệp vụ

Chỉ gọi commit sau khi đã kiểm tra:

- Số hàng UPDATE/DELETE đúng dự kiến.
- Không vi phạm ràng buộc.
- Các INSERT ledger/outbox cần thiết đã thành công.
- Không có lỗi validation cần làm transaction thất bại.

## 8. rollback() có ý nghĩa gì?

~~~java
connection.rollback();
~~~

Lệnh rollback hủy hiệu lực những thay đổi trong transaction hiện tại mà chưa commit, theo semantics PostgreSQL.

### 8.1. Ví dụ lỗi ở bước cuối

~~~text
BEGIN transaction
  UPDATE A: trừ 100
  UPDATE B: cộng 100
  INSERT ledger: lỗi
ROLLBACK
~~~

Kết quả: cả việc trừ/cộng tiền và ghi ledger trong transaction ấy đều không được commit.

### 8.2. Rollback không hoàn tác giao dịch đã commit

Nếu code đã commit debit ở transaction trước, rollback transaction sau không thể tự đảo ngược debit cũ. Muốn sửa, cần transaction bù trừ được thiết kế riêng và audit rõ ràng.

### 8.3. Rollback không tua lại sequence

`nextval`/identity sequences trong PostgreSQL không rollback số đã cấp. Một ledger có `transfer_id` nhảy số sau rollback là điều bình thường, không phải bằng chứng tiền bị mất.

### 8.4. Rollback không tự undo side effects ngoài DB

Email, HTTP call, message gửi qua hệ thống khác có thể vẫn xảy ra. Cần transactional outbox, idempotency hoặc cơ chế điều phối phù hợp thay vì gọi service ngoài giữa transaction rồi kỳ vọng DB rollback giải quyết tất cả.

## 9. setAutoCommit(true) có thể commit bất ngờ

Đây là bẫy quan trọng:

~~~java
connection.setAutoCommit(false);

// Thực hiện một số thay đổi...

connection.setAutoCommit(true);
~~~

Theo JDBC, khi thay đổi chế độ autocommit **trong lúc có transaction hoạt động**, transaction hiện tại được commit khi mode được đổi. Việc chuyển từ `false` sang `true` **không phải cách “dọn dẹp trung lập”**.

### 9.1. Ví dụ nguy hiểm

~~~java
connection.setAutoCommit(false);
updateAccount(connection);

// Không có commit()/rollback() rõ ràng:
connection.setAutoCommit(true);
~~~

Lời gọi cuối có thể commit thay đổi đang chờ, dù nghiệp vụ chưa hoàn tất.

### 9.2. Trình tự an toàn

~~~java
connection.setAutoCommit(false);
try {
    doWork(connection);
    connection.commit();
} catch (SQLException | RuntimeException ex) {
    try {
        connection.rollback();
    } catch (SQLException rollbackFailure) {
        ex.addSuppressed(rollbackFailure);
    }
    throw ex;
}
~~~

Chỉ phục hồi autocommit nếu ứng dụng **sở hữu connection thật sự**, biết chính xác transaction đã kết thúc và không bị transaction manager khác quản lý.

### 9.3. Pool thường có cơ chế reset riêng

Khi mượn từ pool, thường nên để pool quản lý việc reset autoCommit/isolation/readOnly theo contract. Tránh viết khối `finally { setAutoCommit(true); }` vô điều kiện khi trạng thái transaction có thể còn lỗi.

### 9.4. Nếu cần reset thủ công

Phải kết thúc giao dịch trước bằng commit/rollback thành công, sau đó mới reset trong logic đã kiểm soát. Nếu rollback thất bại vì connection hỏng, nên loại bỏ connection khỏi sử dụng thay vì cố đổi mode để trả lại pool.

## 10. Đóng resources: try-with-resources

JDBC tài nguyên cần được đóng đúng:

~~~java
String sql =
    "SELECT account_id, balance FROM accounts " +
    "WHERE account_id = ?";

try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(sql)) {

    ps.setLong(1, 1001L);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("account_id");
            java.math.BigDecimal balance =
                rs.getBigDecimal("balance");
            System.out.println(id + ": " + balance);
        }
    }
}
~~~

### 10.1. Đóng theo thứ tự ngược

Trong ví dụ, `ResultSet` được đóng trước, sau đó `PreparedStatement`, cuối cùng `Connection`.

### 10.2. Đóng ResultSet sớm

Kết quả truy vấn có thể giữ cursor, buffer, server resources hoặc tham chiếu statement. Nên đọc/đóng trong một phạm vi nhỏ.

### 10.3. Đóng Statement

`PreparedStatement.close()` giải phóng tài nguyên statement theo driver. Không giữ hàng nghìn statement lâu hơn request/transaction cần thiết.

### 10.4. Đóng Connection

Với connection vật lý, close kết thúc phiên/tài nguyên. Với connection từ pool, `close()` trên handle thường có nghĩa **trả về pool**, không đóng TCP ngay.

### 10.5. Không giữ ResultSet sau khi connection đóng

~~~java
ResultSet rs;
try (Connection conn = dataSource.getConnection()) {
    // ...
}
// Sử dụng rs tại đây là lỗi thiết kế lifecycle.
~~~

Trả về DTO/value object đã đọc hết từ phương thức repository, không trả `ResultSet` ra ngoài phạm vi connection.

## 11. close() không thay cho rollback()

Một pattern không an toàn:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    updateAccount(connection);
    // Lỗi ném ra trước commit.
}
~~~

### 11.1. JDBC và driver/pool có các chi tiết lifecycle

Hành vi đóng connection khi transaction vẫn active có những chi tiết phụ thuộc driver/implementation. Một số pool có thể rollback/reset trước khi trả connection. **Không dùng điều đó làm logic nghiệp vụ**; bạn cần gọi rollback khi giao dịch chưa được commit.

### 11.2. Lý do thực tế

Nếu mã ứng dụng “ngầm tin” vào close:

- Dễ bị lệ thuộc hành vi khác nhau giữa pool và connection thật.
- Khó ghi log transaction failure đúng.
- Khó giữ exception gốc và lỗi cleanup.
- Dễ vô tình thay đổi behavior khi chuyển driver/pool.

### 11.3. Quy tắc

**Mọi transaction được mở do ứng dụng quản lý phải có đường đi rõ ràng tới `commit()` hoặc `rollback()`.** Sau đó đóng tài nguyên.

## 12. Mẫu transaction JDBC an toàn cơ bản

~~~java
import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class TransactionExample {
    private final DataSource dataSource;

    public TransactionExample(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void performBusinessOperation() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try {
                firstStatement(connection);
                secondStatement(connection);
                thirdStatement(connection);

                connection.commit();
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

    private void firstStatement(Connection c)
            throws SQLException {
        // Một câu SQL có kiểm tra kết quả.
    }

    private void secondStatement(Connection c)
            throws SQLException {
        // Bước tiếp theo trên CÙNG connection.
    }

    private void thirdStatement(Connection c)
            throws SQLException {
        // Ghi kết quả nghiệp vụ/ledger trước commit.
    }
}
~~~

### 12.1. Vai trò của hai tầng try

`try-with-resources` ngoài cùng đảm bảo đóng connection. Khối `try/catch` bên trong phân định **commit hay rollback**.

### 12.2. Bắt RuntimeException

Lỗi kiểm tra nghiệp vụ, mapper hoặc logic Java có thể là runtime exception. Nếu bỏ qua nhóm này, transaction có thể rơi vào nhánh đóng connection mà không rollback tường minh.

### 12.3. Giữ exception gốc

Nếu rollback cũng lỗi, `ex.addSuppressed(rollbackFailure)` giúp giữ lỗi ban đầu làm nguyên nhân chính đồng thời không làm mất thông tin cleanup failure.

### 12.4. Không nuốt SQLException

Code:

~~~java
catch (SQLException ex) {
    connection.rollback();
    return; // Che giấu thất bại!
}
~~~

có thể khiến tầng gọi tưởng nghiệp vụ thành công. Nếu chủ ý chuyển lỗi thành kết quả domain, phải mô tả rõ trạng thái thất bại; không âm thầm bỏ qua.

### 12.5. Trường hợp commit lỗi do mất kết nối

`catch` vẫn có thể thử rollback để dọn trạng thái khi connection còn dùng được. Nhưng nếu client không nhận được kết quả commit do mất kết nối, **không thể luôn biết transaction đã commit hay chưa**. Đây là tình huống *ambiguous commit outcome*, cần xử lý riêng ở nghiệp vụ quan trọng.

## 13. Tạo schema thực hành chuyển tiền

Các ví dụ tiếp theo dành cho **database lab**, không chạy trên dữ liệu tài chính thật.

### 13.1. Tạo schema

~~~sql
CREATE SCHEMA jdbc_lab;
~~~

### 13.2. Tạo bảng tài khoản

~~~sql
CREATE TABLE jdbc_lab.accounts (
    account_id bigint PRIMARY KEY,
    owner_name text NOT NULL,
    balance numeric(14,2) NOT NULL
        CHECK (balance >= 0),
    updated_at timestamptz NOT NULL
        DEFAULT clock_timestamp()
);
~~~

### 13.3. Tạo sổ giao dịch

~~~sql
CREATE TABLE jdbc_lab.transfers (
    transfer_id bigint GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    from_account_id bigint NOT NULL
        REFERENCES jdbc_lab.accounts(account_id),
    to_account_id bigint NOT NULL
        REFERENCES jdbc_lab.accounts(account_id),
    amount numeric(14,2) NOT NULL
        CHECK (amount > 0),
    created_at timestamptz NOT NULL
        DEFAULT clock_timestamp(),
    CHECK (from_account_id <> to_account_id)
);
~~~

### 13.4. Chèn hai tài khoản

~~~sql
INSERT INTO jdbc_lab.accounts (
    account_id, owner_name, balance
) VALUES
    (1001, 'Lan',  500.00),
    (1002, 'Minh', 150.00);
~~~

Tổng số dư ban đầu là **650.00**.

### 13.5. Kiểm tra dữ liệu

~~~sql
SELECT account_id, owner_name, balance
FROM jdbc_lab.accounts
ORDER BY account_id;

SELECT sum(balance) AS total_balance
FROM jdbc_lab.accounts;
~~~

Trong lab này, chuyển tiền nội bộ không có phí: nếu thành công, tổng 650.00 phải được bảo toàn.

## 14. Yêu cầu nguyên tử của chuyển tiền

Một transaction chuyển 125.00 từ Lan (1001) sang Minh (1002) cần:

1. Xác nhận số tiền dương và hai account IDs khác nhau.
2. Kiểm tra cả hai tài khoản tồn tại.
3. Chặn tình huống bị trừ khi số dư không đủ.
4. Trừ 125.00 khỏi tài khoản 1001.
5. Cộng 125.00 vào tài khoản 1002.
6. Ghi một dòng `transfers`.
7. **Commit một lần** sau khi tất cả bước thành công.
8. **Rollback tất cả** nếu một bước lỗi.

### 14.1. Điều kiện bất biến

\[
\text{balance}_{1001} + \text{balance}_{1002}
= 650.00
\]

trước và sau một chuyển tiền nội bộ thành công, nếu không có nghiệp vụ khác hoặc giao dịch đồng thời thay đổi số dư.

### 14.2. Trạng thái sau chuyển 125.00

| Account | Trước | Sau |
| --- | ---: | ---: |
| Lan (1001) | 500.00 | 375.00 |
| Minh (1002) | 150.00 | 275.00 |
| Tổng | 650.00 | 650.00 |

### 14.3. SQL cập nhật có điều kiện

~~~sql
UPDATE jdbc_lab.accounts
SET balance = balance - 125.00,
    updated_at = clock_timestamp()
WHERE account_id = 1001
  AND balance >= 125.00;
~~~

Nếu UPDATE ảnh hưởng **0 hàng**, có thể do tài khoản không tồn tại hoặc thiếu số dư. Không coi statement chạy không exception là đã trừ tiền thành công.

## 15. Mã Java chuyển tiền dùng đúng một Connection

Đoạn mã dưới đây minh họa một phương thức chuyển tiền nguyên tử bằng JDBC thuần.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class TransferRepository {
    private final DataSource dataSource;

    public TransferRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public long transfer(
            long fromAccountId,
            long toAccountId,
            BigDecimal amount
    ) throws SQLException {
        if (fromAccountId == toAccountId) {
            throw new IllegalArgumentException(
                "Source and destination must differ"
            );
        }
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException(
                "Amount must be positive"
            );
        }
        BigDecimal normalizedAmount =
            amount.setScale(2, RoundingMode.UNNECESSARY);

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try {
                lockBothAccounts(
                    connection, fromAccountId, toAccountId
                );
                debit(connection, fromAccountId, normalizedAmount);
                credit(connection, toAccountId, normalizedAmount);
                long transferId = insertTransfer(
                    connection,
                    fromAccountId,
                    toAccountId,
                    normalizedAmount
                );

                connection.commit();
                return transferId;
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

    private static void lockBothAccounts(
            Connection connection,
            long fromId,
            long toId
    ) throws SQLException {
        String sql =
            "SELECT account_id " +
            "FROM jdbc_lab.accounts " +
            "WHERE account_id IN (?, ?) " +
            "ORDER BY account_id FOR UPDATE";

        try (PreparedStatement ps =
                 connection.prepareStatement(sql)) {
            ps.setLong(1, fromId);
            ps.setLong(2, toId);

            int count = 0;
            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    count++;
                }
            }
            if (count != 2) {
                throw new IllegalArgumentException(
                    "One or both accounts do not exist"
                );
            }
        }
    }

    private static void debit(
            Connection connection,
            long fromId,
            BigDecimal amount
    ) throws SQLException {
        String sql =
            "UPDATE jdbc_lab.accounts " +
            "SET balance = balance - ?, " +
            "    updated_at = clock_timestamp() " +
            "WHERE account_id = ? AND balance >= ?";

        try (PreparedStatement ps =
                 connection.prepareStatement(sql)) {
            ps.setBigDecimal(1, amount);
            ps.setLong(2, fromId);
            ps.setBigDecimal(3, amount);

            if (ps.executeUpdate() != 1) {
                throw new IllegalArgumentException(
                    "Insufficient funds"
                );
            }
        }
    }

    private static void credit(
            Connection connection,
            long toId,
            BigDecimal amount
    ) throws SQLException {
        String sql =
            "UPDATE jdbc_lab.accounts " +
            "SET balance = balance + ?, " +
            "    updated_at = clock_timestamp() " +
            "WHERE account_id = ?";

        try (PreparedStatement ps =
                 connection.prepareStatement(sql)) {
            ps.setBigDecimal(1, amount);
            ps.setLong(2, toId);

            if (ps.executeUpdate() != 1) {
                throw new IllegalStateException(
                    "Destination account disappeared"
                );
            }
        }
    }

    private static long insertTransfer(
            Connection connection,
            long fromId,
            long toId,
            BigDecimal amount
    ) throws SQLException {
        String sql =
            "INSERT INTO jdbc_lab.transfers " +
            "(from_account_id, to_account_id, amount) " +
            "VALUES (?, ?, ?) RETURNING transfer_id";

        try (PreparedStatement ps =
                 connection.prepareStatement(sql)) {
            ps.setLong(1, fromId);
            ps.setLong(2, toId);
            ps.setBigDecimal(3, amount);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException(
                        "No transfer_id was returned"
                    );
                }
                return rs.getLong(1);
            }
        }
    }
}
~~~

### 15.1. Đây là ví dụ JDBC cho PostgreSQL

`RETURNING transfer_id` là cú pháp PostgreSQL tiện để nhận ID sau INSERT. Nếu cần tương thích nhiều RDBMS, có thể cân nhắc `getGeneratedKeys()` với behavior driver được xác nhận.

### 15.2. Một connection cho toàn bộ nghiệp vụ

Tất cả helper nhận cùng `Connection connection`; không helper nào tự gọi `dataSource.getConnection()`. Nếu mỗi helper mượn một connection khác, giao dịch không còn nguyên tử.

### 15.3. Khóa tài khoản

`SELECT ... FOR UPDATE` đặt row-level locks thích hợp để những giao dịch đồng thời không tùy tiện sửa cùng tài khoản. `ORDER BY account_id` cung cấp thứ tự khóa có chủ đích trong ví dụ; một thiết kế production nên giữ thứ tự khóa nhất quán ở **mọi đường cập nhật** để giảm deadlocks.

### 15.4. Kiểm tra số dòng thay đổi

`executeUpdate()` trả số hàng bị ảnh hưởng. Nếu debit/credit không cập nhật đúng một hàng, ném lỗi để transaction rollback.

### 15.5. Dùng BigDecimal cho tiền

`numeric(14,2)` tương ứng với `BigDecimal`, tránh sai số biểu diễn nhị phân của `double`. `RoundingMode.UNNECESSARY` ở ví dụ từ chối số tiền có nhiều hơn 2 chữ số thập phân cần làm tròn.

### 15.6. Biểu thức UPDATE tránh lost update đơn giản

`balance = balance - ?`/`+ ?` cập nhật dựa trên giá trị ở database dưới cơ chế khóa, tốt hơn việc đọc balance ra Java, tự tính rồi ghi tuyệt đối bằng giá trị stale trong một ứng dụng đồng thời.

### 15.7. Ví dụ chưa phải hệ thống thanh toán production

Hệ thống tài chính thật còn cần idempotency key, ledger bất biến, mô hình double-entry, hạn mức, xác thực chủ thể, audit, chống retry trùng và quy trình xử lý commit không rõ kết quả. Lab chỉ minh họa **transaction boundaries/resource management**.

## 16. Chạy chuyển tiền và quan sát kết quả

Ví dụ sử dụng:

~~~java
TransferRepository repository =
    new TransferRepository(dataSource);

long id = repository.transfer(
    1001L,
    1002L,
    new BigDecimal("125.00")
);

System.out.println("Transfer ID: " + id);
~~~

### 16.1. Kiểm tra số dư

~~~sql
SELECT account_id, balance
FROM jdbc_lab.accounts
ORDER BY account_id;
~~~

Nếu chưa có transaction khác:

~~~text
1001  375.00
1002  275.00
~~~

### 16.2. Kiểm tra ledger

~~~sql
SELECT
    transfer_id,
    from_account_id,
    to_account_id,
    amount,
    created_at
FROM jdbc_lab.transfers
ORDER BY transfer_id DESC;
~~~

### 16.3. Kiểm tra tổng

~~~sql
SELECT sum(balance) AS total_balance
FROM jdbc_lab.accounts;
~~~

Kỳ vọng 650.00 sau chuyển nội bộ thành công.

### 16.4. Chạy lại ví dụ có tác động thật

Mỗi lần gọi `transfer(...)` sẽ thực hiện **một chuyển tiền mới** nếu không có idempotency. Không chạy lặp lại rồi kỳ vọng số dư vẫn giống bảng kết quả lần đầu.

## 17. Kiểm thử rollback khi thiếu số dư

Giả sử tài khoản nguồn có 375.00, thử chuyển 900.00.

~~~java
try {
    repository.transfer(
        1001L, 1002L, new BigDecimal("900.00")
    );
} catch (IllegalArgumentException ex) {
    System.out.println("Rejected: " + ex.getMessage());
}
~~~

### 17.1. Điều kiện debit không thỏa

~~~sql
WHERE account_id = ? AND balance >= ?
~~~

không khớp hàng, `executeUpdate()` trả 0, Java ném exception.

### 17.2. Rollback

Khối catch chạy `connection.rollback()`. Nếu chưa có thay đổi ghi nào thì rollback vẫn kết thúc transaction tương ứng.

### 17.3. Không có transfer ledger

Lệnh INSERT vào `transfers` chưa chạy, nên không có bản ghi mới. Trong các lỗi xảy ra sau debit/credit, rollback cũng loại bỏ các thay đổi chưa commit từ transaction.

### 17.4. Lỗi nghiệp vụ không nhất thiết là SQLException

Ở ví dụ, lỗi thiếu tiền là `IllegalArgumentException`. Đây là lý do pattern bắt cả `RuntimeException` để rollback, thay vì chỉ bắt `SQLException`.

## 18. Kiểm thử lỗi sau khi đã debit

Một bài test quan trọng là giả lập lỗi **sau khi cập nhật tài khoản nguồn**, trước khi commit.

### 18.1. Luồng minh họa

~~~text
setAutoCommit(false)
  -> UPDATE source balance -= 50
  -> UPDATE destination balance += 50
  -> INSERT ledger báo lỗi
  -> rollback()
  -> cả source và destination trở về giá trị trước giao dịch
~~~

### 18.2. Không cố gây lỗi bằng cách xóa bảng thật

Trong test tự động, dùng transaction/test seam hoặc một dữ liệu gây constraint violation trong database **lab**. Không thay schema production để ép lỗi cho thử nghiệm.

### 18.3. Assertion cần kiểm tra cả hai bên

Một test rollback không chỉ kiểm tra `transfers` không có hàng mới; phải kiểm tra nguồn và đích đều không đổi.

### 18.4. Số ID có thể vẫn nhảy

Nếu INSERT ledger cấp identity rồi thất bại/rollback, ID có thể bỏ trống. Test không nên đòi sequence liên tục.

## 19. PostgreSQL transaction aborted và SQLSTATE 25P02

Trong PostgreSQL, khi một statement gây lỗi trong transaction thông thường, transaction có thể chuyển sang trạng thái **aborted**.

### 19.1. Ví dụ từ JDBC autocommit false

~~~sql
BEGIN;

INSERT INTO jdbc_lab.accounts (
    account_id, owner_name, balance
) VALUES (
    1001, 'Duplicate ID', 1.00
);

SELECT * FROM jdbc_lab.accounts;
~~~

INSERT vi phạm primary key (nếu ID 1001 đã tồn tại). Câu SELECT sau đó trong cùng transaction bị lỗi dạng:

~~~text
current transaction is aborted,
commands ignored until end of transaction block
~~~

SQLSTATE liên quan là `25P02`.

### 19.2. Không tiếp tục chạy statement rồi kỳ vọng tự hồi phục

JDBC code bắt SQLException rồi tiếp tục gửi UPDATE khác trên cùng connection mà không rollback có thể chỉ nhận thêm `25P02`.

### 19.3. Đường khôi phục cơ bản

~~~java
try {
    executeWork(connection);
    connection.commit();
} catch (SQLException ex) {
    connection.rollback();
    throw ex;
}
~~~

### 19.4. Savepoint là lựa chọn có kiểm soát

Nếu lỗi thuộc một bước **được phép bỏ qua**, `rollback(savepoint)` có thể đưa transaction trở về trạng thái dùng được mà không rollback toàn bộ. Không dùng nó để lờ đi lỗi làm nghiệp vụ tổng thể không còn hợp lệ.

### 19.5. Trong psql

Sau khi transaction aborted, cần `ROLLBACK` (hoặc rollback về savepoint đã tạo trước lỗi) thay vì cố tiếp tục SELECT như chưa có chuyện gì.

## 20. Savepoint là gì?

`Savepoint` đánh dấu một điểm trong transaction, cho phép rollback một phần công việc kể từ điểm đó.

~~~java
connection.setAutoCommit(false);

Savepoint savepoint = connection.setSavepoint("optional_step");
// ...
connection.rollback(savepoint);
~~~

### 20.1. Không thay commit

Rollback về savepoint không commit transaction. Giao dịch vẫn cần `commit()` hoặc `rollback()` tổng thể.

### 20.2. Không dùng trong autocommit true

Savepoint thuộc transaction do ứng dụng quản lý; hãy tắt autocommit trước.

### 20.3. Mục tiêu đúng

Một luồng:

~~~text
Tạo order
  |
  +-- Ghi order chính       (bắt buộc)
  |
  +-- SAVEPOINT extras
          |
          +-- Ghi tag phụ  (tùy chọn)
          +-- Lỗi?
                |
                +-- ROLLBACK TO extras
  |
  +-- COMMIT order chính
~~~

chỉ hợp lý nếu yêu cầu nghiệp vụ cho phép thiếu tag phụ.

## 21. Ví dụ JDBC Savepoint

~~~java
import java.sql.Connection;
import java.sql.Savepoint;
import java.sql.SQLException;
import javax.sql.DataSource;

public void createOrderWithOptionalTag(DataSource ds)
        throws SQLException {
    try (Connection connection = ds.getConnection()) {
        connection.setAutoCommit(false);

        try {
            insertRequiredOrder(connection);

            Savepoint sp =
                connection.setSavepoint("before_optional_tag");

            try {
                insertOptionalTag(connection);
            } catch (SQLException optionalError) {
                connection.rollback(sp);
                // Ghi log lỗi tùy chọn một cách an toàn.
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
~~~

Hai helper là những phương thức nghiệp vụ cần triển khai, nhận **cùng Connection**; đoạn mã minh họa khung xử lý transaction/savepoint.

### 21.1. Vì sao rollback tới savepoint quan trọng?

Trong PostgreSQL, sau một statement lỗi, transaction thông thường bị aborted. `rollback(sp)` có thể loại bỏ hậu quả bước con và cho phép transaction tiếp tục.

### 21.2. Nếu rollback(sp) cũng lỗi

Exception từ `rollback(sp)` sẽ đi tới catch ngoài, nơi ứng dụng thử rollback toàn transaction. Không nên nuốt lỗi này vì connection có thể không còn đáng tin.

### 21.3. Release savepoint

JDBC có `releaseSavepoint(sp)` để giải phóng savepoint khi không cần nữa. Sau rollback về savepoint, có thể release theo semantics driver; cần kiểm tra lifecycle trong đoạn code thực tế, không giữ hàng nghìn savepoints không cần thiết.

### 21.4. Savepoint có chi phí

Tạo savepoint và xử lý subtransactions không miễn phí. Không tạo savepoint cho từng hàng của batch hàng triệu rows chỉ để tránh thiết kế validation tốt hơn.

### 21.5. Lỗi bắt buộc không được bỏ qua

Nếu ghi order chính thất bại, không được rollback riêng bước này rồi commit các phần khác. Quy tắc nghiệp vụ phải quyết định bước nào optional.

## 22. Phân biệt rollback toàn bộ và rollback(savepoint)

| Thao tác | Phạm vi | Transaction sau thao tác |
| --- | --- | --- |
| `rollback()` | Toàn bộ transaction chưa commit | Kết thúc, có thể bắt đầu transaction mới |
| `rollback(savepoint)` | Những thay đổi sau savepoint | Transaction tiếp tục từ điểm đã đánh dấu |
| `commit()` | Commit toàn transaction | Kết thúc thành công |
| `releaseSavepoint(sp)` | Bỏ mốc savepoint | Không commit/rollback giao dịch |

### 22.1. Không rollback(savepoint) sau commit

Sau khi commit, savepoint của transaction đã kết thúc không còn dùng như trước.

### 22.2. Savepoint và exception SQLSTATE

Một lỗi `23505` hoặc `23503` trong transaction PostgreSQL thường làm transaction aborted; rollback về savepoint được tạo **trước lỗi** là cách để phục hồi có kiểm soát.

### 22.3. Không dùng savepoint để giả vờ partial success

Nếu một transfer phải trừ/cộng và ghi ledger nguyên tử, lỗi ledger không phải optional. Không rollback riêng INSERT ledger rồi commit debit/credit.

## 23. SQLSTATE trong ứng dụng JDBC

`SQLException` cung cấp mã:

~~~java
String sqlState = exception.getSQLState();
~~~

Một số mã thường gặp ở PostgreSQL:

| SQLSTATE | Ý nghĩa thường gặp | Hướng phản ứng |
| --- | --- | --- |
| `23505` | Unique violation | Xem constraint/idempotency, không retry mù |
| `23503` | Foreign key violation | Sửa dữ liệu hoặc thứ tự thao tác |
| `23514` | Check constraint violation | Sửa input/business rule |
| `25P02` | Transaction đang aborted | Rollback toàn bộ hoặc về savepoint |
| `40001` | Serialization failure | Retry toàn transaction nếu hợp lệ |
| `40P01` | Deadlock detected | Rollback, có thể retry toàn nghiệp vụ |
| `55P03` | Lock not available | Xử lý lock timeout/NOWAIT |
| `57014` | Query canceled | Xem timeout/cancellation, xử lý transaction |
| `08006` | Connection failure | Connection có thể hỏng; kết quả commit có thể không chắc |

### 23.1. Không dựa vào text message

Thông báo lỗi có thể khác ngôn ngữ/phiên bản. SQLSTATE và metadata exception thường ổn định hơn khi phân loại.

### 23.2. Constraint names giúp chẩn đoán

Với PGJDBC, một số lỗi cung cấp metadata PostgreSQL chi tiết qua API driver; nếu cần xác định constraint vi phạm, sử dụng thông tin cấu trúc khi có, không parse chuỗi message bằng regex.

### 23.3. Đừng retry mọi SQLException

Một `23514` do số tiền âm sẽ tiếp tục thất bại dù retry 100 lần. Retry phải dành cho các lỗi tạm thời có chiến lược phù hợp, như serialization/deadlock, và cần giới hạn số lần.

## 24. Retry transaction an toàn

PostgreSQL có thể ném `40001` khi `SERIALIZABLE` phát hiện conflict hoặc `40P01` khi deadlock.

### 24.1. Retry **toàn bộ** transaction

~~~text
Lần 1:
   BEGIN -> SELECT -> UPDATE -> lỗi 40001 -> ROLLBACK

Lần 2:
   BEGIN mới -> SELECT lại -> UPDATE lại -> COMMIT
~~~

Không chỉ retry câu UPDATE cuối trên transaction đã aborted.

### 24.2. Mỗi attempt dùng transaction sạch

Có thể mượn connection mới hoặc bảo đảm connection cũ đã rollback thành công và được phép reuse. Không tiếp tục từ state lỗi không rõ.

### 24.3. Backoff và giới hạn

Ví dụ tối đa 3 attempts với jitter/backoff có kiểm soát; nếu vẫn thất bại, trả lỗi rõ ràng. Tránh tạo *retry storm* khi database đã quá tải.

### 24.4. Retry và side effects

Nếu transaction gọi hệ thống ngoài, retry có thể gửi request nhiều lần. Dùng idempotency key, outbox hoặc thiết kế phân tách side effects.

### 24.5. Transaction thành công nhưng phản hồi commit mất

Khi mất kết nối đúng lúc commit, client không thể luôn biết server đã commit chưa. Retry “chuyển tiền” với ID mới có thể chuyển hai lần. Cần business request ID duy nhất và khả năng kiểm tra trạng thái giao dịch trước khi quyết định retry.

## 25. Ambiguous commit và idempotency

Giả sử:

~~~text
Client gửi COMMIT
    |
    +-- PostgreSQL đã commit
    |
    +-- Đường mạng bị ngắt trước khi client nhận OK
~~~

Ứng dụng nhận lỗi kết nối nhưng **kết quả ở server có thể đã được commit**.

### 25.1. rollback() không “phủ định” commit đã xảy ra

Nếu commit đã hoàn tất, rollback trên connection cũ hoặc connection mới không thể hủy giao dịch vừa commit.

### 25.2. Idempotency key

Một transfer production nên có `business_request_id` do hệ thống cấp và UNIQUE constraint:

~~~sql
-- Minh họa thiết kế mở rộng trong schema lab:
-- ALTER TABLE jdbc_lab.transfers
-- ADD COLUMN business_request_id uuid UNIQUE;
~~~

Logic retry phải tìm lại transaction bằng request ID ổn định và so sánh thông số nghiệp vụ, không tạo một ID mới mỗi lần retry.

### 25.3. Không coi unique violation lúc retry là lỗi nghiệp vụ ngay

Nếu request ID đã tồn tại và dữ liệu trùng khớp, có thể đó là lần thực hiện trước đã commit. Cần truy vấn trạng thái/cân nhắc contract để trả kết quả nhất quán.

### 25.4. Chỉ đặt idempotency key là chưa đủ

Ứng dụng phải xử lý races giữa hai requests cùng key, transaction boundaries và mapping kết quả. Tạo UNIQUE constraint là một thành phần, không phải toàn bộ giải pháp.

## 26. Transaction isolation và JDBC

JDBC cung cấp:

~~~java
connection.setTransactionIsolation(
    Connection.TRANSACTION_READ_COMMITTED
);
~~~

Các mức thường gặp:

| JDBC constant | PostgreSQL tương ứng/ghi chú |
| --- | --- |
| `TRANSACTION_READ_UNCOMMITTED` | PostgreSQL thực thi theo semantics READ COMMITTED |
| `TRANSACTION_READ_COMMITTED` | Mặc định phổ biến của PostgreSQL |
| `TRANSACTION_REPEATABLE_READ` | Snapshot ổn định trong transaction, có quy tắc lỗi riêng |
| `TRANSACTION_SERIALIZABLE` | Isolation mạnh nhất, có thể phát sinh `40001` và cần retry |

### 26.1. READ COMMITTED

Mỗi statement có thể nhìn snapshot mới của những transaction đã commit trước statement đó. Hai SELECT cùng transaction có thể nhìn kết quả khác nhau nếu có commits đồng thời.

### 26.2. REPEATABLE READ

Giúp các lần đọc thông thường trong transaction dùng snapshot ổn định, nhưng có thể phát sinh lỗi nếu update xung đột theo semantics PostgreSQL.

### 26.3. SERIALIZABLE

Có thể ngăn một số bất thường concurrency mà khóa đơn giản khó bao phủ, nhưng ứng dụng phải biết **retry toàn transaction** khi server báo serialization failure.

### 26.4. Thiết lập isolation trước khi transaction thực sự hoạt động

JDBC yêu cầu thay isolation trong transaction active có thể có behavior phụ thuộc implementation. Với PGJDBC, nên chọn isolation **trước statement đầu tiên của transaction**, hoặc theo API transaction manager đang dùng.

### 26.5. Isolation không thay transaction logic

Dùng `SERIALIZABLE` không sửa được việc debit chạy trong một connection còn credit chạy connection khác/transaction khác.

## 27. Ví dụ đặt isolation

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setTransactionIsolation(
        Connection.TRANSACTION_SERIALIZABLE
    );
    connection.setAutoCommit(false);

    try {
        performOperation(connection);
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

### 27.1. Cẩn thận với pooled connection

Nếu ứng dụng đổi isolation trên connection mượn từ pool, cần bảo đảm trạng thái được reset đúng theo pool/framework. Nếu không, một request có thể vô tình thừa hưởng `SERIALIZABLE` và chịu lỗi/chi phí không mong muốn.

### 27.2. Đọc trạng thái

~~~java
int isolation = connection.getTransactionIsolation();
~~~

### 27.3. Không gọi setTransactionIsolation trong repository tùy ý

Khi một transaction đã được Spring quản lý, repository cấp dưới đổi isolation có thể xung đột với transaction manager và hoạt động đang diễn ra.

## 28. Read-only transaction

JDBC có:

~~~java
connection.setReadOnly(true);
~~~

### 28.1. Ý định

Đánh dấu connection/transaction dự kiến chỉ đọc. Driver/database có thể tận dụng hint hoặc áp policy read-only phù hợp.

### 28.2. Không phải ranh giới quyền bảo mật

`setReadOnly(true)` không thay PostgreSQL role privileges. Một role được cấp quyền ghi vẫn phải được quản trị bằng `GRANT`/RLS/chính sách DB thích hợp.

### 28.3. Thiết lập trước khi bắt đầu transaction

PGJDBC có các cấu hình chi tiết về cách áp read-only theo connection/transaction. Đặt nó trước các statement trong transaction và không đổi giữa một transaction đang chạy nếu không có contract framework hỗ trợ.

### 28.4. Không quên reset khi trả pool

Read-only flag có thể ảnh hưởng request sau nếu pool không reset. Ưu tiên quản lý ở transaction manager/connection pool thay vì tự thay ngầm bên trong một hàm SQL.

## 29. Statement timeout và transaction timeout

Một query chờ khóa hoặc quét nhiều hàng có thể khiến request treo dài.

### 29.1. JDBC Statement.setQueryTimeout

~~~java
try (PreparedStatement ps =
         connection.prepareStatement(
             "SELECT count(*) FROM jdbc_lab.transfers"
         )) {
    ps.setQueryTimeout(5); // Đơn vị giây.
    try (ResultSet rs = ps.executeQuery()) {
        rs.next();
        long count = rs.getLong(1);
    }
}
~~~

### 29.2. PostgreSQL statement_timeout

Có thể đặt transaction-local setting trong transaction:

~~~sql
SET LOCAL statement_timeout = '5s';
~~~

`SET LOCAL` có hiệu lực trong transaction hiện tại; sau khi transaction kết thúc sẽ không tiếp tục giữ giá trị đó theo cùng phạm vi.

### 29.3. lock_timeout

~~~sql
SET LOCAL lock_timeout = '2s';
~~~

giới hạn thời gian chờ lock theo chính sách PostgreSQL. Nó không phải giới hạn toàn bộ thời gian tính toán của query.

### 29.4. idle_in_transaction_session_timeout

~~~sql
SET LOCAL idle_in_transaction_session_timeout = '30s';
~~~

có thể kết thúc session nếu nó ở trạng thái idle in transaction quá lâu. Đây là một guardrail, không thay việc ứng dụng commit/rollback đúng.

### 29.5. Timeout có thể làm transaction aborted

Khi một statement trong transaction bị hủy vì timeout/cancel, transaction PostgreSQL có thể cần rollback trước khi tiếp tục. Không chỉ catch exception rồi gửi statement khác.

### 29.6. Phân biệt các timeout

| Timeout | Bảo vệ |
| --- | --- |
| Connection acquisition timeout (pool) | Chờ có connection rảnh |
| TCP connect timeout | Thiết lập kết nối mạng |
| Socket read timeout | Đọc phản hồi từ server |
| JDBC query timeout | Thời gian thực thi statement theo driver |
| PostgreSQL statement_timeout | Thời gian câu SQL trên server |
| lock_timeout | Thời gian chờ lấy lock |
| idle_in_transaction_session_timeout | Session bỏ không trong transaction |

Không có một timeout duy nhất giải quyết tất cả các pha.

## 30. Cấu hình SET LOCAL bằng JDBC

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        try (PreparedStatement ps =
                 connection.prepareStatement(
                     "SET LOCAL statement_timeout = '5s'"
                 )) {
            ps.execute();
        }

        runBusinessSql(connection);
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

### 30.1. SET LOCAL trong transaction

Phải dùng khi transaction đã được quản lý, để setting có phạm vi transaction và không rò rỉ qua connection pool.

### 30.2. Không làm SET LOCAL bằng SQL injection

Những giá trị cấu hình cố định do ứng dụng kiểm soát có thể dùng literal rõ ràng. Nếu dynamic, validate và sử dụng phương pháp thiết lập phù hợp; không nối chuỗi từ input không tin cậy.

### 30.3. setQueryTimeout và statement_timeout có thể cùng tồn tại

Đây là các cơ chế khác tầng. Khi hai bên cùng giới hạn, cần hiểu cái nào có thể hủy statement trước và cách kết nối/transaction phản ứng.

## 31. Connection pool: mượn và trả

Trong ứng dụng server:

~~~text
Pool chứa các kết nối vật lý PostgreSQL
   |
Request A --- getConnection() ---> Logical Connection A
   |                                 |
   +---- transaction / SQL ----------+
   |
   +---- close() --------------> trả pool

Request B --- getConnection() ---> Logical Connection B
~~~

### 31.1. close() thường trả pool

`Connection.close()` trên pooled handle có thể là thao tác hoàn trả connection cho pool; socket/backend chưa chắc bị đóng.

### 31.2. Không lưu Connection trong singleton

Tránh để một `Connection` dùng chung lâu dài trong object singleton/bean hay chia sẻ giữa requests. Mỗi đơn vị công việc nên mượn một connection theo scope rõ ràng.

### 31.3. Không mượn connection rồi quên close

Nếu mỗi request lấy một connection nhưng không trả, pool sẽ cạn và các requests sau phải chờ hoặc timeout.

### 31.4. Không giữ connection khi gọi mạng bên ngoài

Giữ connection và transaction trong lúc chờ HTTP call vài giây có thể chiếm pool, giữ locks và giảm throughput.

### 31.5. Pool size không càng lớn càng tốt

Mỗi connection dùng tài nguyên PostgreSQL. Số connection quá nhiều có thể tăng context switching, lock contention và bộ nhớ; phải đo workload, CPU, PostgreSQL limits và pool wait time.

## 32. Ví dụ lifecycle với DataSource

~~~java
public BigDecimal readBalance(
        DataSource dataSource,
        long accountId
) throws SQLException {
    String sql =
        "SELECT balance FROM jdbc_lab.accounts " +
        "WHERE account_id = ?";

    try (Connection connection = dataSource.getConnection();
         PreparedStatement ps =
             connection.prepareStatement(sql)) {
        ps.setLong(1, accountId);

        try (ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) {
                return null;
            }
            return rs.getBigDecimal(1);
        }
    }
}
~~~

### 32.1. Một SELECT đơn giản có thể để autocommit mặc định

Không phải mọi truy vấn cần tắt autocommit. Nếu một SELECT độc lập không cần giữ snapshot/lock qua các statement, connection mặc định có thể phù hợp.

### 32.2. Không tự reset mode nếu không đổi nó

Ví dụ chỉ đọc không thay autoCommit/isolation. Với pool, ít thay đổi trạng thái hơn thường dễ bảo trì hơn.

### 32.3. Một repository gọi repository khác có thể sai ranh giới

Nếu mỗi repository method tự mượn/close connection, gọi hai method từ service không tự tạo một transaction chung. Cần truyền connection/transaction context hoặc dùng framework transaction manager.

## 33. Rủi ro trạng thái connection bị rò trong pool

Các thuộc tính session/connection có thể ảnh hưởng người mượn kế tiếp:

- Autocommit.
- Isolation level.
- Read-only.
- Schema/search_path.
- Các session-level `SET`.
- Prepared statements, temporary tables hoặc advisory locks theo scope.
- Transaction chưa được kết thúc.

### 33.1. Pool reset phần nào?

Connection pool thường có cơ chế reset một số trạng thái JDBC được theo dõi. Nhưng **không được mặc nhiên tin mọi biến session SQL tùy ý đã được khôi phục** nếu ứng dụng gọi `SET search_path`/`SET ROLE` hay tạo temp objects.

### 33.2. Prefer transaction-local changes

Với settings phù hợp, dùng `SET LOCAL` thay vì `SET` toàn session giúp giới hạn tác động trong transaction.

### 33.3. Chú ý session advisory locks

Session-level advisory locks có thể tồn tại qua transaction và gắn với physical connection. Nếu quên release rồi trả pool, người mượn kế tiếp có thể chịu ảnh hưởng.

### 33.4. Cấu hình pool phải rõ

Pool nên có baseline về autocommit, isolation, read-only và giới hạn connection lifetime/acquisition. Không sửa những giá trị ấy tùy tiện ở từng repository method.

## 34. JDBC batch trong một transaction

Batch giảm số lần gọi JDBC/network khi chèn nhiều dòng:

~~~java
String sql =
    "INSERT INTO jdbc_lab.accounts " +
    "(account_id, owner_name, balance) VALUES (?, ?, ?)";

try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        try (PreparedStatement ps =
                 connection.prepareStatement(sql)) {
            for (int i = 0; i < 100; i++) {
                ps.setLong(1, 2000L + i);
                ps.setString(2, "Lab-" + i);
                ps.setBigDecimal(3, new BigDecimal("10.00"));
                ps.addBatch();
            }
            ps.executeBatch();
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
~~~

### 34.1. Batch không tự quyết định transaction boundary

`executeBatch()` không thay `commit()`. Nếu autocommit được bật, behavior atomicity giữa các batch elements có thể không đáp ứng yêu cầu nghiệp vụ toàn batch.

### 34.2. BatchUpdateException

Khi một phần batch lỗi, JDBC có thể ném `BatchUpdateException`, cung cấp update counts cho những phần liên quan. Nhưng nếu yêu cầu **all-or-nothing**, hãy rollback transaction thay vì tự kết luận “những phần trước thành công thì giữ lại”.

### 34.3. Ràng buộc của PostgreSQL transaction

Trong transaction đã có SQL error, nó có thể bị aborted; phải rollback hoặc về savepoint phù hợp trước khi gửi SQL tiếp.

### 34.4. Batch quá lớn

Batch hàng triệu dòng có thể tăng memory, WAL, thời gian lock và transaction duration. Chia batch hợp lý tùy yêu cầu atomicity, data volume và giới hạn hệ thống.

### 34.5. Nếu chia thành nhiều transactions

Bạn mất tính nguyên tử của toàn dữ liệu nhập. Cần checkpoint/restart, idempotency và trạng thái “đã nhập một phần” được mô tả rõ.

## 35. Streaming ResultSet và fetchSize

Khi đọc hàng triệu rows, nếu driver tải toàn bộ ResultSet vào memory, ứng dụng có thể hết heap.

PGJDBC hỗ trợ mô hình cursor-based fetching trong những điều kiện nhất định, thường gồm autocommit tắt và ResultSet phù hợp.

~~~java
String sql =
    "SELECT transfer_id, amount " +
    "FROM jdbc_lab.transfers ORDER BY transfer_id";

try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        try (PreparedStatement ps =
                 connection.prepareStatement(
                     sql,
                     ResultSet.TYPE_FORWARD_ONLY,
                     ResultSet.CONCUR_READ_ONLY
                 )) {
            ps.setFetchSize(500);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    long id = rs.getLong(1);
                    BigDecimal amount = rs.getBigDecimal(2);
                    processRow(id, amount);
                }
            }
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
~~~

`processRow(...)` là phương thức ứng dụng giả định, không phải API JDBC.

### 35.1. Vì sao autocommit phải tắt?

Với nhiều cơ chế cursor của PostgreSQL/PGJDBC, một cursor gắn với transaction; nếu transaction kết thúc sau mỗi statement, cursor phục vụ nhiều lượt fetch không thể tiếp tục như mong muốn.

### 35.2. Đọc hết rồi mới commit

Khi còn đang sử dụng ResultSet/cursor, không commit/close connection sớm. Kết thúc đọc và đóng ResultSet trước, rồi commit/rollback.

### 35.3. Streaming không có nghĩa giữ transaction vô hạn

Một vòng lặp `while (rs.next())` mất 30 phút có thể giữ transaction/snapshot lâu, tăng áp lực vacuum và chiếm connection. Với xử lý chậm, nên cân nhắc phân trang keyset hoặc tách query khỏi xử lý bên ngoài.

### 35.4. fetchSize không phải LIMIT

`setFetchSize(500)` là gợi ý cách fetch/stream dữ liệu; không giới hạn kết quả tổng cộng ở 500 hàng. Query vẫn có thể trả hàng triệu rows.

### 35.5. Không đưa network calls vào vòng lặp lâu dài

Nếu `processRow(...)` gửi HTTP từng hàng, transaction có thể idle/chậm rất lâu. Cân nhắc queue/batch xử lý tách biệt.

## 36. Dùng cursor hay keyset pagination?

Hai cách xử lý tập dữ liệu lớn:

| Cách | Ưu điểm | Đánh đổi |
| --- | --- | --- |
| Cursor/fetchSize | API duyệt tuần tự, có thể giữ tính nhất quán snapshot | Giữ connection/transaction khi duyệt dài |
| Keyset pagination | Mỗi trang một transaction ngắn, dễ retry/checkpoint | Cần khóa sắp xếp ổn định và xử lý thay đổi đồng thời |

### 36.1. Keyset minh họa

~~~sql
SELECT transfer_id, amount
FROM jdbc_lab.transfers
WHERE transfer_id > :last_seen_id
ORDER BY transfer_id
LIMIT 500;
~~~

`:last_seen_id` là placeholder minh họa trong một layer hỗ trợ named parameters; JDBC thuần dùng `?`.

### 36.2. Không hứa snapshot toàn bộ khi phân trang nhiều transaction

Nếu mỗi trang dùng một transaction mới, dữ liệu nguồn có thể thay đổi giữa các trang. Cần xác định yêu cầu consistency.

### 36.3. Thiết kế theo mục đích

Export một ảnh chụp dữ liệu nhất quán có thể thích cursor trong transaction có kiểm soát; job nhập/xử lý hàng triệu đơn theo checkpoint có thể thích phân trang và cơ chế idempotent.

## 37. Connection và thread-safety

Không nên chia sẻ một `Connection` đang thực hiện giao dịch giữa nhiều thread mà không có thiết kế synchronization chặt chẽ và contract driver hỗ trợ rõ.

### 37.1. Vì sao nguy hiểm?

Hai threads dùng cùng connection có thể:

- Trộn câu SQL vào **cùng transaction**.
- Một thread commit/rollback công việc của thread kia.
- Gây cạnh tranh trên Statement/ResultSet.
- Tạo trạng thái khó dự đoán với session variables.

### 37.2. Mỗi đơn vị nghiệp vụ một transaction context

Trong mô hình request-response, thường một transaction chỉ phục vụ một request/operation tại một thời điểm. Framework có thể bind connection với thread hoặc async context theo cơ chế riêng.

### 37.3. Không truyền Connection sang async callback vô thời hạn

Một callback chạy sau khi scope resource đóng không thể dùng handle đã trả pool. Nếu cần background job, cho job tự tạo transaction/scope riêng theo kế hoạch.

## 38. Spring @Transactional và JDBC thủ công

Trong ứng dụng Spring, transaction manager thường quản lý connection và transaction thông qua proxy/context.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.jdbc.core.JdbcTemplate;

@Service
public class TransferService {
    private final JdbcTemplate jdbc;

    public TransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(long fromId, long toId, BigDecimal amount) {
        int debited = jdbc.update(
            "UPDATE jdbc_lab.accounts " +
            "SET balance = balance - ? " +
            "WHERE account_id = ? AND balance >= ?",
            amount, fromId, amount
        );
        if (debited != 1) {
            throw new IllegalArgumentException("Insufficient funds");
        }

        int credited = jdbc.update(
            "UPDATE jdbc_lab.accounts SET balance = balance + ? " +
            "WHERE account_id = ?",
            amount, toId
        );
        if (credited != 1) {
            throw new IllegalStateException("Unknown destination");
        }

        jdbc.update(
            "INSERT INTO jdbc_lab.transfers " +
            "(from_account_id, to_account_id, amount) " +
            "VALUES (?, ?, ?)",
            fromId, toId, amount
        );
    }
}
~~~

Đây là mẫu minh họa ngắn để so sánh **ai sở hữu transaction boundary**; nó chưa bao gồm validate đầu vào, khóa theo thứ tự, idempotency và retry như ví dụ JDBC lab đầy đủ.

### 38.1. Spring quản lý commit/rollback

Với `@Transactional` đang hoạt động qua proxy và transaction manager phù hợp, Spring quyết định commit khi method kết thúc thành công hoặc rollback theo các quy tắc exception.

### 38.2. Không tự gọi Connection.commit()

Nếu lấy connection tham gia transaction Spring rồi gọi `commit()` thủ công, bạn phá contract framework và có thể làm transaction kết thúc sớm.

### 38.3. Không tự lấy connection khác bằng DataSource ở nơi không tham gia transaction

Nếu một repository dùng `DriverManager.getConnection()` độc lập, nó có thể không cùng transaction Spring với `JdbcTemplate`. Hãy dùng resource APIs được transaction manager nhận biết.

### 38.4. Spring rollback rules

Mặc định Spring thường rollback với `RuntimeException` và `Error`, nhưng không tự rollback với mọi checked exception trừ khi cấu hình tương ứng (ví dụ `rollbackFor=Exception.class`). Phải hiểu policy của transaction manager/version thực tế.

### 38.5. Self-invocation

Trong cấu hình proxy-based phổ biến, một method của bean tự gọi một method `@Transactional` khác trên chính `this` có thể không đi qua proxy, khiến transaction boundary không kích hoạt như mong đợi.

### 38.6. Propagation

`REQUIRED` và `REQUIRES_NEW` có semantics khác nhau về transaction tham gia/tạo mới. `REQUIRES_NEW` có thể cần thêm connection và làm tăng áp lực pool nếu dùng lồng không kiểm soát.

## 39. Khi nào nên dùng TransactionTemplate?

Nếu muốn ranh giới transaction tường minh trong Spring mà không tự điều khiển `Connection`:

~~~java
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.jdbc.core.JdbcTemplate;

public class TransferServiceExplicit {
    private final TransactionTemplate tx;
    private final JdbcTemplate jdbc;

    public TransferServiceExplicit(
            TransactionTemplate tx,
            JdbcTemplate jdbc
    ) {
        this.tx = tx;
        this.jdbc = jdbc;
    }

    public void doWork() {
        tx.executeWithoutResult(status -> {
            jdbc.update(
                "UPDATE jdbc_lab.accounts " +
                "SET updated_at = clock_timestamp() " +
                "WHERE account_id = ?",
                1001L
            );
        });
    }
}
~~~

### 39.1. TransactionTemplate không yêu cầu tự commit()

Nó dùng transaction manager; callback chạy trong transaction scope được quản lý và framework xử lý commit/rollback phù hợp.

### 39.2. Không trộn chủ sở hữu

Đừng vừa dùng `TransactionTemplate` vừa gọi `connection.setAutoCommit(false)`/`commit()` trên một connection được framework quản lý nếu không có lý do được thiết kế riêng.

### 39.3. Logic nghiệp vụ cần giữ transaction ngắn

Dù Spring giúp dọn resource, một method `@Transactional` vẫn có thể giữ lock/snapshot lâu nếu gọi HTTP, sleep hoặc xử lý CPU nặng bên trong.

## 40. Quan sát transaction từ PostgreSQL

Các vấn đề JDBC như quên commit/rollback có thể xuất hiện phía PostgreSQL qua `pg_stat_activity`.

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event,
    left(query, 160) AS query_prefix
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST, pid;
~~~

### 40.1. state = idle in transaction

Một session ở trạng thái `idle in transaction` đã bắt đầu transaction và đang chờ client gửi lệnh tiếp theo. Nó có thể giữ locks/snapshot và làm vacuum bị ảnh hưởng.

### 40.2. xact_start

Cho biết thời điểm transaction hiện tại bắt đầu, giúp tìm transaction mở quá lâu. Không nhầm với thời điểm request HTTP bắt đầu.

### 40.3. application_name

Nên đặt application name từ connection parameters để phân biệt Java service/worker trong monitoring, chẳng hạn PGJDBC property `ApplicationName` khi driver hỗ trợ.

### 40.4. Query text có thể chứa dữ liệu nhạy cảm

Giới hạn quyền xem monitoring và xử lý log cẩn thận. Không xuất `pg_stat_activity.query` nguyên vẹn ra dashboard công khai.

### 40.5. Không kill backend tùy tiện

`pg_terminate_backend(pid)` có thể làm application errors/rollback transaction; chỉ dùng theo quy trình vận hành và khi hiểu ảnh hưởng.

## 41. Theo dõi locks

~~~sql
SELECT
    l.pid,
    a.application_name,
    a.state,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation_name
FROM pg_locks AS l
LEFT JOIN pg_stat_activity AS a
  ON a.pid = l.pid
WHERE a.datname = current_database()
ORDER BY l.pid, l.granted, l.mode;
~~~

### 41.1. Cần hiểu locktype

Một transaction có thể giữ relation locks, transactionid locks hoặc các loại khác. Không phải mọi lock chờ đều là “table lock” làm tắc tất cả bảng.

### 41.2. Chặn và bị chặn

Có thể dùng `pg_blocking_pids(pid)` để tìm process IDs đang chặn một backend:

~~~sql
SELECT
    pid,
    pg_blocking_pids(pid) AS blocking_pids,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE datname = current_database();
~~~

### 41.3. Root cause có thể nằm ở Java

Một connection dùng `setAutoCommit(false)` rồi chờ callback HTTP không commit/rollback có thể giữ locks lâu hơn dự kiến. Sửa luồng ứng dụng quan trọng hơn việc chỉ tăng `lock_timeout`.

## 42. Giám sát tỷ lệ commit và rollback

`pg_stat_database` có counters:

~~~sql
SELECT
    datname,
    xact_commit,
    xact_rollback,
    stats_reset
FROM pg_stat_database
WHERE datname = current_database();
~~~

### 42.1. Đây là số cộng dồn

Các counters không tự cho biết “trong 1 phút vừa qua” nếu không lấy hai mẫu theo thời gian. Chúng có thể bị reset nên cần xử lý metadata reset khi tính rate.

### 42.2. Không suy một rollback = một bug

Rollback có thể do user cancel, validation failure, deadlock retry hoặc nghiệp vụ có chủ đích. Tỷ lệ rollback tăng là tín hiệu cần phân loại, không phải bằng chứng trực tiếp về corruption.

### 42.3. Kết hợp application metrics

Nên đo:

- Transaction duration p50/p95/p99.
- Số transaction commits, rollbacks theo nghiệp vụ.
- Pool active/idle/waiting connections.
- SQLSTATE breakdown.
- Deadlocks và lock waits.
- `idle in transaction` sessions quá ngưỡng.

## 43. Testing transaction boundaries

Một bài test tốt không chỉ xem phương thức Java có ném exception hay không.

### 43.1. Happy path

Chuyển 125.00: cả hai balances đúng, ledger có một dòng, tổng không đổi.

### 43.2. Insufficient funds

Chuyển nhiều hơn số dư: debit không cập nhật, cả hai balances không đổi, không có ledger.

### 43.3. Destination missing

Chuyển tới account không tồn tại: giao dịch thất bại, nguồn không mất tiền.

### 43.4. Ledger failure

Chèn ledger bị constraint violation: debit/credit rollback.

### 43.5. Concurrent transfers

Hai threads/transactions chuyển từ cùng tài khoản với tổng số tiền vượt số dư: không được để balance âm hoặc tạo tiền. Kiểm tra locks, update counts và retry logic.

### 43.6. Deadlock/serialization

Tạo workload cạnh tranh có kiểm soát để xem ứng dụng có rollback và retry **toàn transaction** đúng không.

### 43.7. Commit outcome unknown

Mô phỏng mất kết nối quanh commit và xác minh idempotency/reconciliation. Không khẳng định một test đơn giản có thể luôn tái hiện chính xác thời điểm commit trên network.

### 43.8. Resource leakage

Mô phỏng request ném exception; số active pool connections phải trở lại mức bình thường sau khi scope kết thúc, không tăng mãi.

## 44. Unit test và integration test

### 44.1. Unit test

Có thể mock repository/DataSource để xác minh gọi đúng logic, nhưng mock không mô phỏng đầy đủ PostgreSQL transaction semantics, locks, SQLSTATE hay driver behavior.

### 44.2. Integration test

Một môi trường PostgreSQL thật (ví dụ container test) giúp kiểm tra:

- SQL syntax và constraints.
- Commit/rollback.
- Transaction aborted (`25P02`).
- Savepoint.
- Locks và isolation.
- PGJDBC behavior.

### 44.3. Không dựa hoàn toàn vào @Transactional test

Một integration test được framework tự rollback sau mỗi test có thể che lỗi production do code không commit rõ, hoặc khác với ngữ cảnh transaction thực. Cần test cả behavior lúc transaction thực sự commit.

### 44.4. Không chia sẻ dữ liệu test giữa các parallel workers tùy tiện

Test đồng thời có thể khiến các assert về tổng số dư không ổn định. Dùng fixture riêng hoặc transaction/test schema được cô lập.

## 45. Anti-patterns thường gặp

### Lỗi 1. Mặc định autocommit true nhưng gọi nhiều SQL và mong atomicity

Mỗi statement có thể commit riêng. Cần tắt autocommit hoặc transaction manager.

### Lỗi 2. Quên commit()

Thay đổi chưa commit không tự có hiệu lực bền vững chỉ vì Java method return.

### Lỗi 3. Quên rollback() khi có exception

Transaction có thể tiếp tục active/aborted cho đến khi connection được dọn; không lệ thuộc pool cleanup.

### Lỗi 4. setAutoCommit(true) trong finally vô điều kiện

Có thể commit transaction active không mong muốn, kể cả khi nghiệp vụ có lỗi.

### Lỗi 5. close() là commit/rollback nghiệp vụ

Close giải phóng/hoàn trả resource; chương trình phải quyết định transaction outcome trước.

### Lỗi 6. Mỗi helper tự mở Connection

Debit và credit có thể ở hai transaction khác nhau.

### Lỗi 7. Không kiểm tra executeUpdate()

UPDATE 0 hàng vẫn là statement có thể hoàn thành không exception. Không suy tiền đã trừ chỉ vì không có SQLException.

### Lỗi 8. Dùng double để biểu diễn tiền

`double` có thể gây sai số nhị phân. Dùng `BigDecimal` và `numeric` với quy tắc rounding rõ.

### Lỗi 9. Nối chuỗi input thành SQL

Rủi ro SQL injection. Dùng `PreparedStatement` với placeholders.

### Lỗi 10. Bắt SQLException rồi tiếp tục trên transaction aborted

PostgreSQL có thể trả `25P02` cho những statement sau; phải rollback hoặc rollback tới savepoint.

### Lỗi 11. Savepoint thay thế commit

Savepoint chỉ cho phép rollback một phần, không commit nghiệp vụ.

### Lỗi 12. Catch optional error rồi không rollback(savepoint)

Transaction có thể vẫn aborted trong PostgreSQL, dù Java đã bắt exception.

### Lỗi 13. Commit sau khi xử lý sai bắt buộc

Ví dụ ledger fail nhưng vẫn commit balances, phá invariant.

### Lỗi 14. Commit trong framework @Transactional

Framework chưa kết thúc unit-of-work nhưng code bên dưới đã commit sớm.

### Lỗi 15. Dùng DriverManager độc lập trong transaction Spring

Connection mới không tự tham gia transaction context đang có.

### Lỗi 16. Đổi isolation/readOnly khi transaction đã active

Behavior có thể phụ thuộc driver và phá hợp đồng transaction.

### Lỗi 17. Quên reset trạng thái pooled connection

Request sau có thể gặp autocommit/readOnly/isolation/search_path khác baseline.

### Lỗi 18. Trả ResultSet ra ngoài phạm vi Connection

Resource đã đóng và không thể duyệt an toàn sau khi method trả về.

### Lỗi 19. Không đóng PreparedStatement

Giữ tài nguyên JDBC và có thể góp phần leak memory/server state.

### Lỗi 20. Giữ Connection chờ HTTP

Chiếm pool và kéo dài transaction/locks.

### Lỗi 21. Dùng shared Connection giữa threads

Transactions và statements của nhiều requests có thể trộn, gây commit/rollback công việc của nhau.

### Lỗi 22. Đặt timeout nhưng không rollback sau cancellation

Transaction có thể aborted sau `57014`; không tiếp tục như không có lỗi.

### Lỗi 23. setFetchSize(500) rồi tưởng chỉ có 500 kết quả

Fetch size là cách truyền dữ liệu theo lô, không phải `LIMIT`.

### Lỗi 24. Streaming hàng triệu rows trong transaction kéo dài

Giữ snapshot/connection lâu, ảnh hưởng pool/vacuum/locks.

### Lỗi 25. Retry đúng một statement sau 40001

Phải rollback và retry toàn transaction cùng toàn bộ quyết định nghiệp vụ.

### Lỗi 26. Retry chuyển tiền khi không biết commit thành công chưa

Có thể chuyển hai lần. Cần idempotency/reconciliation.

### Lỗi 27. Dựa vào sequence liên tục để khẳng định giao dịch đúng

Sequence không rollback, có thể có khoảng trống dù không mất dữ liệu.

### Lỗi 28. Nghĩ SERIALIZABLE thay sự phối hợp Connection

Isolation không sửa việc dùng sai transaction boundary.

### Lỗi 29. Bật readOnly làm đủ quyền bảo mật

`setReadOnly(true)` không thay `GRANT`/RLS.

### Lỗi 30. Pool size rất lớn để che connection leak

Chỉ trì hoãn cạn pool và có thể tăng gánh nặng PostgreSQL. Phải sửa lifecycle.

## 46. Bài tập thực hành

Các bài dựa trên schema `jdbc_lab` hoặc đoạn code mẫu của bài. Những bài chuyển tiền có tác động ghi dữ liệu phải chạy trên database **lab**, không chạy với tài khoản thật.

### Bài 1. JDBC resources

Liệt kê vai trò của `DataSource`, `Connection`, `PreparedStatement` và `ResultSet`.

### Bài 2. Autocommit mặc định

Nếu `getAutoCommit()` là true, hai UPDATE nối tiếp có tự trở thành một transaction nguyên tử không?

### Bài 3. Tắt autocommit

Viết Java code để tắt autocommit trên một `Connection`.

### Bài 4. Commit

Lệnh JDBC nào commit transaction? Sau commit, trạng thái autocommit false có tự chuyển thành true không?

### Bài 5. Rollback

Viết đoạn catch giữ exception gốc và ghi rollback failure thành suppressed exception.

### Bài 6. Chuyển autoCommit

Vì sao `setAutoCommit(true)` trong `finally` có thể nguy hiểm?

### Bài 7. One connection

Vì sao debit/credit/ledger trong một transaction phải dùng cùng `Connection`?

### Bài 8. PreparedStatement

Viết câu UPDATE balance của account dùng placeholders thay vì nối chuỗi ID/số tiền.

### Bài 9. executeUpdate

Nếu UPDATE có `WHERE balance >= ?` trả 0 hàng, chương trình nên hiểu gì?

### Bài 10. Money type

Vì sao dùng `BigDecimal` và PostgreSQL `numeric` cho tiền thay vì `double`?

### Bài 11. Lab SQL

Viết SQL tính tổng balances và liệt kê các transfer gần nhất.

### Bài 12. Thành công

Từ số dư (500,150), sau chuyển 125 từ 1001 tới 1002, kết quả mong đợi là gì?

### Bài 13. Không đủ tiền

Chuyển 900 từ account 1001 khi có 375. Code `debit` xử lý thế nào?

### Bài 14. Lỗi ledger

Nếu INSERT ledger lỗi sau debit/credit, trạng thái nguồn/đích sau rollback là gì?

### Bài 15. try-with-resources

Viết code mở Connection, PreparedStatement và ResultSet, đóng đúng phạm vi.

### Bài 16. ResultSet scope

Tại sao repository không nên trả `ResultSet` ra ngoài sau khi connection đã close?

### Bài 17. Pool close

`connection.close()` trên pooled handle thường có nghĩa gì?

### Bài 18. Pool leak

Nếu 100 requests lấy connection nhưng không close, triệu chứng có thể là gì?

### Bài 19. PostgreSQL 25P02

Transaction báo unique violation và SELECT tiếp theo báo `25P02`. Lệnh phục hồi cơ bản là gì?

### Bài 20. Savepoint

Viết Java code đặt savepoint rồi rollback riêng bước con.

### Bài 21. Optional step

Khi nào có thể rollback(savepoint) rồi commit toàn transaction?

### Bài 22. SERIALIZABLE

Vì sao một transaction `SERIALIZABLE` có thể cần retry khi gặp `40001`?

### Bài 23. READ UNCOMMITTED

PostgreSQL thực thi `READ UNCOMMITTED` theo semantics isolation nào?

### Bài 24. SQLSTATE

Phân biệt `23505`, `40P01`, `40001` và `25P02`.

### Bài 25. Retry

Vì sao không thể retry riêng UPDATE cuối cùng sau transaction bị serialization failure?

### Bài 26. Ambiguous commit

Client mất mạng sau khi gửi COMMIT. Có thể khẳng định chắc chắn server chưa commit không?

### Bài 27. Idempotency

Vì sao `business_request_id UNIQUE` có ích khi phải retry chuyển tiền?

### Bài 28. Timeout

Nêu khác nhau giữa `setQueryTimeout`, `lock_timeout` và pool acquisition timeout.

### Bài 29. SET LOCAL

Viết SQL đặt `statement_timeout=5s` chỉ cho transaction hiện tại.

### Bài 30. Streaming

Vì sao PGJDBC streaming cursor thường dùng `setAutoCommit(false)` và `setFetchSize(500)`?

### Bài 31. FetchSize

`setFetchSize(500)` có đồng nghĩa query trả tối đa 500 rows không?

### Bài 32. Thread safety

Vì sao không nên dùng chung một `Connection` đang chạy transaction giữa hai requests?

### Bài 33. Spring @Transactional

Trong method Spring đang `@Transactional`, có nên tự gọi `connection.commit()` không?

### Bài 34. Spring self-invocation

Vì sao lời gọi `this.innerTransactionalMethod()` có thể không tạo transaction mới trong proxy-based Spring?

### Bài 35. Monitoring

Viết SQL tìm các session `idle in transaction` và thời điểm bắt đầu transaction.

### Bài 36. Lock wait

Viết SQL liệt kê `pid` và `pg_blocking_pids(pid)` để điều tra lock wait.

### Bài 37. pg_stat_database

Hai counter nào cho biết số commits và rollbacks tích lũy ở database?

### Bài 38. Batch

`executeBatch()` có thay thế nhu cầu `commit()` khi autocommit false không?

### Bài 39. Read-only

`setReadOnly(true)` có thay `GRANT` và RLS không?

### Bài 40. Thiết kế

Nêu ít nhất tám mục trong checklist quản lý transaction và JDBC resources an toàn cho một service production.

## 47. Lời giải tham khảo

### Bài 1–2. Resources và autocommit

`DataSource` cấp Connection, `Connection` quản lý session/transaction, `PreparedStatement` bind SQL parameters, `ResultSet` đọc rows. Với autocommit true, hai UPDATE thường có thể commit riêng; không bảo đảm nguyên tử cho cả hai.

### Bài 3–4. Tắt autocommit và commit

~~~java
connection.setAutoCommit(false);
// Thực hiện các statements của một đơn vị nghiệp vụ.
connection.commit();
~~~

Sau commit, connection vẫn ở trạng thái autocommit false cho đến khi mode được đổi hoặc pool/framework reset theo contract.

### Bài 5. Rollback giữ lỗi

~~~java
catch (SQLException | RuntimeException ex) {
    try {
        connection.rollback();
    } catch (SQLException rollbackError) {
        ex.addSuppressed(rollbackError);
    }
    throw ex;
}
~~~

### Bài 6. setAutoCommit(true)

Đổi mode từ false sang true trong lúc có transaction active có thể commit transaction ấy. Không dùng nó như cleanup vô điều kiện khi transaction chưa được kết thúc.

### Bài 7. Một connection

PostgreSQL transaction gắn với một connection/backend. Rollback trên connection A không tự rollback câu SQL đã commit trên connection B.

### Bài 8. UPDATE parameterized

~~~java
String sql =
    "UPDATE jdbc_lab.accounts " +
    "SET balance = balance - ? " +
    "WHERE account_id = ? AND balance >= ?";

try (PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setBigDecimal(1, amount);
    ps.setLong(2, accountId);
    ps.setBigDecimal(3, amount);
    int updated = ps.executeUpdate();
}
~~~

### Bài 9–10. Update counts và tiền

0 hàng nghĩa điều kiện `WHERE` không thỏa hoặc row không tồn tại, cần xử lý nghiệp vụ thay vì commit mặc định. `BigDecimal` tránh sai số nhị phân của `double` và khớp với kiểu `numeric`.

### Bài 11. Lab queries

~~~sql
SELECT sum(balance) AS total_balance
FROM jdbc_lab.accounts;

SELECT transfer_id, from_account_id,
       to_account_id, amount
FROM jdbc_lab.transfers
ORDER BY transfer_id DESC;
~~~

### Bài 12–14. Giao dịch

Chuyển 125 thành công: nguồn 375.00, đích 275.00, tổng 650.00 và một ledger. Nếu thiếu số dư, debit UPDATE 0 hàng rồi throw; nếu ledger lỗi, rollback hoàn tác cả debit/credit chưa commit.

### Bài 15. Đóng resources

~~~java
try (Connection conn = ds.getConnection();
     PreparedStatement ps = conn.prepareStatement(
         "SELECT balance FROM jdbc_lab.accounts " +
         "WHERE account_id = ?"
     )) {
    ps.setLong(1, 1001L);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            BigDecimal balance = rs.getBigDecimal(1);
        }
    }
}
~~~

### Bài 16–18. Pool lifecycle

ResultSet cần Statement/Connection còn hợp lệ. `close()` trên pooled handle thường trả connection về pool. Quên close làm pool thiếu connection rảnh, requests chờ và có thể timeout.

### Bài 19. Transaction aborted

~~~java
connection.rollback();
~~~

Hoặc rollback về savepoint tạo trước lỗi nếu quy trình nghiệp vụ cho phép. Không tiếp tục SQL trên transaction aborted.

### Bài 20–21. Savepoint

~~~java
Savepoint sp = connection.setSavepoint();
try {
    insertOptionalRecord(connection);
} catch (SQLException ex) {
    connection.rollback(sp);
}
~~~

Sau đó có thể commit transaction chính **chỉ khi** bước tùy chọn được phép thất bại mà không làm mất tính đúng của nghiệp vụ.

### Bài 22–23. Isolation

`SERIALIZABLE` có thể phát hiện conflict và báo `40001`, yêu cầu rollback/retry toàn transaction. PostgreSQL xử lý `READ UNCOMMITTED` theo semantics `READ COMMITTED`.

### Bài 24. SQLSTATE

`23505`: unique violation; `40P01`: deadlock; `40001`: serialization failure; `25P02`: transaction đã aborted.

### Bài 25–27. Retry và idempotency

Sau `40001`, transaction cũ không thể commit nên phải bắt đầu lại và tính lại những quyết định dựa trên dữ liệu đọc. Khi commit response bị mất, kết quả server có thể đã thành công; request ID ổn định kèm UNIQUE constraint giúp kiểm tra/reconcile, giảm nguy cơ làm hai lần.

### Bài 28. Timeouts

`setQueryTimeout` giới hạn statement theo driver; `lock_timeout` giới hạn chờ lock ở PostgreSQL; pool acquisition timeout giới hạn chờ mượn một connection.

### Bài 29. SET LOCAL

~~~sql
SET LOCAL statement_timeout = '5s';
~~~

Chạy trong transaction, không dùng như một session setting vĩnh viễn cho người mượn connection tiếp theo.

### Bài 30–31. Streaming

Cursor-based fetching của PGJDBC thường cần transaction giữ cursor và `fetchSize` dương để lấy theo lô. `fetchSize(500)` không phải `LIMIT 500`; nó không giới hạn tổng rows.

### Bài 32. Connection threads

Hai requests dùng cùng connection có thể chung transaction, một request commit/rollback công việc của request kia và tranh chấp Statement/ResultSet.

### Bài 33–34. Spring

Không tự `commit()` trong transaction do Spring quản lý. Với proxy-based Spring, self-invocation `this.method()` có thể không đi qua proxy nên annotation của method được gọi không kích hoạt transaction interceptor.

### Bài 35. idle in transaction

~~~sql
SELECT pid, application_name, xact_start,
       state, wait_event_type, wait_event
FROM pg_stat_activity
WHERE state = 'idle in transaction'
ORDER BY xact_start;
~~~

### Bài 36. Blocking PIDs

~~~sql
SELECT
    pid,
    pg_blocking_pids(pid) AS blockers
FROM pg_stat_activity
WHERE datname = current_database();
~~~

### Bài 37. Commit/rollback counters

~~~sql
SELECT xact_commit, xact_rollback
FROM pg_stat_database
WHERE datname = current_database();
~~~

### Bài 38. Batch

Không. Với autocommit false, sau `executeBatch()` vẫn cần `commit()` hoặc `rollback()` theo nghiệp vụ.

### Bài 39. Read-only

Không. `setReadOnly(true)` là trạng thái/hint JDBC và có thể được PostgreSQL/driver áp theo ngữ cảnh, không thay security grants/RLS.

### Bài 40. Checklist

Một lựa chọn: (1) ranh giới nghiệp vụ; (2) một Connection; (3) đặt autocommit rõ; (4) commit một lần; (5) rollback khi lỗi; (6) kiểm tra update count; (7) PreparedStatement; (8) try-with-resources; (9) pool reset; (10) timeout; (11) isolation/locks; (12) idempotency; (13) SQLSTATE/retry; (14) monitoring `idle in transaction`; (15) integration tests.

## 48. Bảng tra cứu nhanh

| Nhu cầu | JDBC/SQL |
| --- | --- |
| Xem autocommit | `connection.getAutoCommit()` |
| Gom nhiều statements vào transaction | `connection.setAutoCommit(false)` |
| Commit transaction | `connection.commit()` |
| Rollback toàn transaction | `connection.rollback()` |
| Tạo savepoint | `connection.setSavepoint()` |
| Rollback phần sau savepoint | `connection.rollback(savepoint)` |
| Giải phóng savepoint | `connection.releaseSavepoint(savepoint)` |
| Đọc isolation | `connection.getTransactionIsolation()` |
| Đặt isolation | `connection.setTransactionIsolation(...)` |
| Đánh dấu read-only | `connection.setReadOnly(true)` |
| Đóng resource an toàn | `try (...) { ... }` |
| SQL bind parameter | `PreparedStatement` + `setLong`/`setBigDecimal` |
| Số hàng DML đã tác động | `executeUpdate()` |
| Đọc SQLSTATE | `SQLException.getSQLState()` |
| Mở kết quả PostgreSQL từ INSERT | `INSERT ... RETURNING` + `executeQuery()` |
| Lock một row | `SELECT ... FOR UPDATE` |
| Giới hạn thời gian query JDBC | `Statement.setQueryTimeout(seconds)` |
| Giới hạn query server theo transaction | `SET LOCAL statement_timeout` |
| Giới hạn chờ lock | `SET LOCAL lock_timeout` |
| Tránh idle in transaction quá lâu | `idle_in_transaction_session_timeout` |
| Batch | `addBatch()`/`executeBatch()` |
| Streaming/fetch theo lô | `setFetchSize(n)` + autocommit off theo PGJDBC |
| Transaction manager Spring | `@Transactional` / `TransactionTemplate` |
| Xem session/transaction | `pg_stat_activity` |
| Xem lock | `pg_locks` / `pg_blocking_pids()` |
| Xem commits/rollbacks tổng | `pg_stat_database` |
| Retry serialization | SQLSTATE `40001`, retry toàn transaction |
| Retry deadlock | SQLSTATE `40P01`, rollback và retry có giới hạn |
| Transaction đã aborted | SQLSTATE `25P02` |

## 49. Checklist triển khai JDBC transaction trong production

1. **Một đơn vị nghiệp vụ gồm những statements nào?** Có cần atomicity toàn bộ?
2. Các statements đó có chạy trên **cùng Connection** không?
3. Có bật/tắt autocommit đúng chủ sở hữu transaction?
4. Có đường `commit()` duy nhất khi tất cả steps thành công?
5. Có đường `rollback()` cho `SQLException` và runtime business failures?
6. Có xử lý rollback exception mà không làm mất lỗi gốc?
7. Có tránh `setAutoCommit(true)` vô điều kiện khi transaction active?
8. Có dùng `try-with-resources` cho Connection/Statement/ResultSet?
9. Có tránh trả ResultSet hoặc Connection ra ngoài lifecycle được quản lý?
10. Có kiểm tra `executeUpdate()` và số rows expected?
11. Có dùng parameterized SQL thay string concatenation?
12. Có dùng `BigDecimal` và validate scale/range khi xử lý tiền?
13. Có ràng buộc CHECK/FK/UNIQUE ở DB để hỗ trợ invariant?
14. Có thứ tự lock nhất quán giữa các transaction cạnh tranh?
15. Isolation level có đúng yêu cầu, và có retry với `40001`?
16. Có xử lý SQLSTATE `25P02` sau SQL error?
17. Savepoint chỉ dùng cho bước thực sự optional?
18. Có idempotency cho thao tác không được thực hiện hai lần?
19. Có xử lý commit response không rõ do mất kết nối?
20. Pool có giới hạn hợp lý và đo active/idle/waiting/leaks?
21. Pool/framework có reset autoCommit/isolation/readOnly/session state?
22. Có tránh network/CPU-heavy work khi giữ transaction mở?
23. Có timeout ở các tầng pool/network/query/lock?
24. Streaming ResultSet có transaction duration/fetch size hợp lý?
25. Có tránh chia sẻ Connection giữa nhiều threads?
26. Nếu dùng Spring, ai sở hữu transaction: framework hay JDBC thủ công?
27. Có test self-invocation/exception rollback/propagation của Spring?
28. Có `application_name` và observability cho session JDBC?
29. Có alert `idle in transaction` và transactions quá lâu?
30. Có integration tests cho commit, rollback, deadlock và resource cleanup?

## 50. Tổng kết

Quản lý giao dịch qua JDBC không chỉ là gọi ba phương thức `setAutoCommit(false)`, `commit()` và `rollback()`. Cần xác định đúng **ranh giới nghiệp vụ**, giữ tất cả statements trong **một Connection**, xử lý lỗi khiến PostgreSQL transaction bị aborted và đóng các resources đúng thời điểm.

Những nguyên tắc cốt lõi:

1. **Autocommit true** phù hợp nhiều statements độc lập, nhưng không bảo đảm nguyên tử cho một nghiệp vụ gồm nhiều statements.
2. **Autocommit false** cho phép ứng dụng quyết định commit hoặc rollback cả nhóm SQL. Mọi đường kết thúc phải rõ ràng; không xem `Connection.close()` hoặc `setAutoCommit(true)` là thay thế cho quyết định giao dịch.
3. **Rollback khi lỗi** cần áp dụng cả lỗi SQL và runtime lỗi nghiệp vụ; sau lỗi SQL trong PostgreSQL, transaction có thể ở trạng thái `25P02` cho đến khi rollback hoặc rollback về savepoint.
4. **Try-with-resources** bảo vệ lifecycle `ResultSet`, `PreparedStatement` và `Connection`, đặc biệt quan trọng khi dùng connection pool. Resource cleanup và transaction outcome là **hai trách nhiệm khác nhau**.
5. **Concurrency và retries** vẫn cần được thiết kế: row locking, isolation, deadlock/serialization errors, idempotency và ambiguous commit outcome không tự giải quyết nhờ JDBC API.
6. **Framework transaction managers** như Spring cần là chủ sở hữu commit/rollback khi được dùng; không trộn chúng tùy tiện với JDBC thủ công.

Khi đánh giá một đoạn code database, hãy hỏi: **“Những thay đổi nào cần thành công cùng nhau?”, “Ai sở hữu Connection và transaction này?”, “Mọi đường lỗi có rollback trước khi trả Connection không?”, và “Nếu mất kết nối ngay lúc COMMIT, nghiệp vụ có thể kiểm tra/retry mà không làm hai lần không?”**. Trả lời rõ bốn câu ấy là nền tảng để viết ứng dụng Java–PostgreSQL đúng dữ liệu, dễ vận hành và chịu được lỗi thực tế.
