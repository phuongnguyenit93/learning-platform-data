# Hoàn tác dữ liệu bằng `rollback` trong JDBC

Trong ứng dụng Java dùng JDBC, một thao tác nghiệp vụ thường cần nhiều câu SQL cùng thành công. Ví dụ, chuyển 150.000 đồng từ tài khoản A sang tài khoản B phải **trừ tiền ở A và cộng tiền ở B**. Nếu câu SQL thứ hai thất bại mà câu thứ nhất đã được lưu vĩnh viễn, tổng số tiền bị sai. **Transaction (giao dịch)** gom những thay đổi có liên quan thành một đơn vị; `rollback` là thao tác **hủy các thay đổi chưa được commit trong giao dịch đó**.

Bài này thuộc chương *Giao dịch cơ bản* của JDBC. Ta sẽ dùng `Connection.setAutoCommit(false)`, `commit()`, `rollback()`, `PreparedStatement`, `Savepoint` và cơ chế xử lý `SQLException` để hoàn tác đúng phạm vi, an toàn khi gặp lỗi, đồng thời hiểu rõ những gì `rollback` **không thể** hoàn tác.

## 1. `rollback` hoạt động ở phạm vi nào?

Một transaction có hai cách kết thúc phổ biến:

- **`commit()`:** xác nhận các thay đổi của transaction hiện tại, để chúng được lưu theo cam kết của DBMS.
- **`rollback()`:** hủy các thay đổi chưa commit của transaction hiện tại, đưa dữ liệu chịu sự quản lý của giao dịch về trạng thái như trước các thay đổi đó.

Sơ đồ tư duy:

```text
Bắt đầu transaction trên một Connection
              |
     UPDATE / INSERT / DELETE
              |
      +-------+-------+
      |               |
  Tất cả đúng      Có lỗi / hủy
      |               |
   commit()        rollback()
      |               |
  Xác nhận          Hủy thay đổi
```

Điều quan trọng là **phạm vi rollback gắn với transaction của đúng `Connection` đang thực thi SQL**:

- `connection.rollback()` tác động đến những thay đổi chưa commit trên connection đó, không tự hoàn tác transaction đã commit hay các transaction trên connection khác.
- Nếu transaction sửa nhiều bảng, rollback có thể hủy các thay đổi thuộc toàn bộ transaction, miễn là các đối tượng và thao tác được DBMS hỗ trợ giao dịch.
- Rollback không có nghĩa là mọi side effect của chương trình được đảo ngược. Gửi email, gọi API thanh toán, ghi file hoặc phát sự kiện ra hệ thống bên ngoài cần cơ chế bù trừ/điều phối riêng.
- Rollback về một **savepoint** chỉ hủy phần việc sau savepoint, thay vì hủy toàn bộ transaction; nội dung này sẽ được minh họa ở phần sau.

Tính **atomicity** của ACID chính là yêu cầu “tất cả hoặc không có gì” đối với những thay đổi thuộc transaction. Các thuộc tính ACID khác như isolation, consistency, durability vẫn ảnh hưởng tính đúng đắn, nhưng `rollback` chủ yếu phục vụ việc đạt tính nguyên tử khi giao dịch thất bại.

## 2. Điều kiện bắt buộc: kiểm soát `autoCommit`

Một connection JDBC mới thường ở chế độ `autoCommit = true`. Khi đó, mỗi câu lệnh SQL hoàn tất thường được commit theo quy tắc của JDBC và DBMS. Nếu chạy hai câu `UPDATE` riêng rẽ, câu đầu có thể đã commit trước khi câu sau báo lỗi; **rollback lúc đó không thể quay ngược câu đầu**.

Để chủ động gộp nhiều câu SQL thành một transaction:

```java
Connection connection = dataSource.getConnection();
connection.setAutoCommit(false);

// Thực hiện các câu SQL thuộc cùng một transaction...
connection.commit();     // Khi tất cả thành công
// Hoặc:
// connection.rollback(); // Khi muốn hủy các thay đổi chưa commit
```

Đoạn trên chỉ mô tả các lời gọi chính; code ứng dụng cần đóng connection bằng `try-with-resources` và xử lý lỗi như các ví dụ đầy đủ phía dưới.

Khi `autoCommit=false`:

1. Transaction được thực hiện theo cơ chế bắt đầu giao dịch của DBMS/JDBC khi có SQL phù hợp.
2. Nhiều `INSERT`, `UPDATE`, `DELETE` trên **cùng một connection** có thể nằm trong một transaction.
3. `commit()` hoặc `rollback()` kết thúc transaction hiện tại; các SQL tiếp theo có thể bắt đầu transaction mới trong chế độ này.
4. Đổi chế độ `setAutoCommit(true)` khi một transaction đang hoạt động **có thể khiến transaction đó được commit theo quy định JDBC**. Vì thế không dùng thay đổi chế độ auto-commit làm cách dọn dẹp sau lỗi.

| Trạng thái | Hai câu `UPDATE` liên tiếp | `rollback()` có cứu được câu đầu không? |
|---|---|---|
| `autoCommit=true` | Mỗi câu có thể được commit riêng khi hoàn tất | **Không**, nếu câu đầu đã commit |
| `autoCommit=false`, chưa `commit()` | Hai câu thuộc cùng transaction trên connection | **Có**, nếu DB/table và thao tác hỗ trợ transaction |
| Đã gọi `commit()` thành công | Thay đổi đã được xác nhận | **Không**; cần transaction bù trừ mới nếu nghiệp vụ cho phép |

Thông thường `rollback()` khi connection đang `autoCommit=true` là không hợp lệ theo JDBC và có thể ném `SQLException`. Muốn dùng rollback rõ ràng, hãy tắt auto-commit **trước** các lệnh cần tính nguyên tử.

## 3. Ví dụ nhỏ: cập nhật rồi hoàn tác

Giả sử có bảng tài khoản:

```sql
CREATE TABLE accounts (
    id       BIGINT PRIMARY KEY,
    owner    VARCHAR(100) NOT NULL,
    balance  DECIMAL(18, 2) NOT NULL
);

INSERT INTO accounts (id, owner, balance)
VALUES (1, 'An', 500000.00),
       (2, 'Binh', 300000.00);
```

Dùng connection lấy từ `DataSource`. Ví dụ dưới đây cố ý thực hiện cập nhật rồi **rollback để minh họa**, vì vậy số dư sau transaction phải trở lại giá trị ban đầu:

```java
import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public final class RollbackDemo {
    private RollbackDemo() {}

    public static void run(DataSource dataSource) throws SQLException {
        String sql = "UPDATE accounts SET balance = balance - ? " +
                     "WHERE id = ?";

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try (PreparedStatement ps =
                         connection.prepareStatement(sql)) {
                ps.setBigDecimal(1, new BigDecimal("50000.00"));
                ps.setLong(2, 1L);

                int rows = ps.executeUpdate();
                if (rows != 1) {
                    throw new SQLException(
                            "Tài khoản nguồn không tồn tại");
                }

                // Hủy thay đổi vừa thực hiện để minh họa rollback.
                connection.rollback();

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
}
```

Sau khi gọi `RollbackDemo.run(...)` thành công:

```sql
SELECT id, balance FROM accounts ORDER BY id;
-- 1 | 500000.00
-- 2 | 300000.00
```

Điểm cần quan sát: `executeUpdate()` có thể trả về 1 dù thay đổi **chưa được commit**. Connection thực hiện thao tác thường có thể đọc thấy thay đổi chưa commit của chính nó; connection khác có thể chưa thấy thay đổi đó, tùy mức cô lập. `rollback()` kết thúc transaction và loại bỏ tác động của câu `UPDATE`. Lệnh `SELECT` kiểm tra sau đó nên được chạy sau khi phương thức đã kết thúc, hoặc trên connection đã hoàn tất rollback.

Khi viết thao tác nghiệp vụ thực sự, không đặt `rollback()` cố định sau mọi câu SQL; cần `commit()` ở nhánh thành công và `rollback()` ở nhánh thất bại.

## 4. Mẫu JDBC hoàn chỉnh: chuyển tiền với `commit` hoặc `rollback`

Giả sử người dùng muốn chuyển tiền giữa hai tài khoản trong cùng cơ sở dữ liệu. Các bước nghiệp vụ:

1. Kiểm tra số tiền chuyển dương và hai tài khoản khác nhau.
2. Trừ tiền tài khoản nguồn **chỉ nếu số dư đủ**.
3. Cộng tiền tài khoản đích.
4. Nếu cả hai câu lệnh cập nhật đúng một hàng, `commit()`; nếu một bước thất bại, `rollback()`.

Dùng `BigDecimal` cho giá trị tiền và `PreparedStatement` để tham số hóa SQL:

```java
import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public final class TransferRepository {
    private TransferRepository() {}

    public static void transfer(
            DataSource dataSource,
            long fromAccount,
            long toAccount,
            BigDecimal amount) throws SQLException {

        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException(
                    "Số tiền chuyển phải lớn hơn 0");
        }
        if (fromAccount == toAccount) {
            throw new IllegalArgumentException(
                    "Hai tài khoản phải khác nhau");
        }

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try {
                int debited = debit(connection, fromAccount, amount);
                if (debited != 1) {
                    throw new SQLException(
                            "Không tồn tại tài khoản nguồn hoặc thiếu tiền");
                }

                int credited = credit(connection, toAccount, amount);
                if (credited != 1) {
                    throw new SQLException(
                            "Không tìm thấy tài khoản nhận");
                }

                // Chỉ xác nhận khi toàn bộ các bước đều thành công.
                connection.commit();

            } catch (SQLException | RuntimeException error) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    // Giữ lỗi gốc và ghi nhận lỗi rollback để điều tra.
                    error.addSuppressed(rollbackError);
                }
                throw error;
            }
        }
    }

    private static int debit(
            Connection connection, long accountId, BigDecimal amount)
            throws SQLException {

        String sql = "UPDATE accounts " +
                "SET balance = balance - ? " +
                "WHERE id = ? AND balance >= ?";

        try (PreparedStatement ps =
                     connection.prepareStatement(sql)) {
            ps.setBigDecimal(1, amount);
            ps.setLong(2, accountId);
            ps.setBigDecimal(3, amount);
            return ps.executeUpdate();
        }
    }

    private static int credit(
            Connection connection, long accountId, BigDecimal amount)
            throws SQLException {

        String sql = "UPDATE accounts " +
                "SET balance = balance + ? " +
                "WHERE id = ?";

        try (PreparedStatement ps =
                     connection.prepareStatement(sql)) {
            ps.setBigDecimal(1, amount);
            ps.setLong(2, accountId);
            return ps.executeUpdate();
        }
    }
}
```

Ví dụ gọi:

```java
TransferRepository.transfer(
        dataSource,
        1L,
        2L,
        new BigDecimal("150000.00"));
```

Nếu hai lệnh SQL thành công, từ số dư `500000.00` và `300000.00` ban đầu, kết quả là `350000.00` và `450000.00`. Nếu tài khoản nhận không tồn tại, lệnh cộng tiền không cập nhật hàng nào; phương thức ném `SQLException`, gọi `rollback()` và số dư tài khoản nguồn trở lại như trước giao dịch.

### Vì sao thiết kế này an toàn hơn việc chỉ “kiểm tra trước”?

Điều kiện `balance >= ?` nằm ngay trong lệnh `UPDATE` trừ tiền, vì vậy không dựa vào một kết quả `SELECT` số dư đã cũ trước khi cập nhật. Việc câu lệnh trả về đúng 1 hàng là một phần của điều kiện nghiệp vụ. Tuy nhiên, ứng dụng thực tế vẫn cần thiết kế **isolation/locking**, chính sách xử lý deadlock, quy định độ chính xác số tiền và ràng buộc dữ liệu phù hợp DBMS.

Đặc biệt, hai `UPDATE` phải dùng **cùng `Connection`**. Nếu mỗi hàm `debit`/`credit` tự mở một connection mới, có thể tạo ra hai transaction khác nhau; gọi `rollback()` trên connection ngoài không hoàn tác những gì connection kia đã commit.

### Phân biệt kết quả nghiệp vụ và kết quả commit

Nếu lỗi xảy ra **trước khi gọi commit**, rollback thành công có thể hủy những thay đổi chưa xác nhận. Nhưng nếu `connection.commit()` ném `SQLException` do mất kết nối hoặc lỗi mạng, ứng dụng có thể **không biết chắc** DBMS đã commit hay chưa. Lệnh rollback trong `catch` là nỗ lực xử lý, không chứng minh giao dịch chưa từng được commit. Với chuyển tiền, cần mã giao dịch duy nhất, cơ chế chống xử lý trùng và đối soát trạng thái trước khi tự động thử lại.

## 5. Xử lý lỗi để không làm mất nguyên nhân thất bại

Một lệnh JDBC có thể ném `SQLException` do ràng buộc khóa ngoại, khóa duy nhất, timeout, deadlock, mất kết nối hoặc lỗi driver. Một số bước xử lý dữ liệu cũng có thể ném `RuntimeException`. Nguyên tắc là:

- Khi giao dịch đang có thay đổi chưa commit và một bước thất bại, **cố gắng rollback ngay trên connection đó**.
- Nếu rollback cũng thất bại, giữ nguyên ngoại lệ ban đầu và đính kèm lỗi rollback để không đánh mất nguyên nhân gốc.
- Không tiếp tục dùng connection cho truy vấn nghiệp vụ mới trong transaction bị lỗi. Với một số DBMS (đặc biệt PostgreSQL), sau lỗi SQL trong transaction, các lệnh tiếp theo có thể bị từ chối cho đến khi rollback.
- Luôn đóng `ResultSet`, `PreparedStatement` và `Connection` bằng `try-with-resources`. Việc đóng connection chỉ giải phóng/trả tài nguyên; **không nên dựa vào `close()` như một lời hứa thay thế `rollback()`** vì hành vi khi còn transaction chưa kết thúc phụ thuộc driver, DBMS và pool.

Mẫu cốt lõi:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        // Toàn bộ thao tác JDBC của cùng transaction.
        // ...
        connection.commit();

    } catch (SQLException | RuntimeException original) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            original.addSuppressed(rollbackFailure);
        }
        throw original;
    }
}
```

Có trường hợp muốn log và trả lỗi nghiệp vụ khác thay vì ném lại `SQLException`, nhưng phải giữ thông tin `SQLState`, mã lỗi và lỗi rollback để điều tra. Không được **nuốt ngoại lệ**, trả thành công hoặc âm thầm bỏ qua lỗi sau một rollback thất bại.

### Vì sao không đặt `setAutoCommit(true)` bừa bãi trong `finally`?

Theo hợp đồng JDBC, thay đổi trạng thái auto-commit của connection trong lúc transaction đang hoạt động có thể khiến transaction hiện tại được commit. Nếu nhánh lỗi chưa rollback được, thao tác “dọn dẹp” bằng `setAutoCommit(true)` có thể gây hậu quả khó đoán.

Với `DataSource` có pool, hãy cấu hình pool khôi phục trạng thái connection khi trả lại và kiểm tra hành vi đó. Nếu hệ thống tự quản lý/giữ connection lâu dài, chỉ khôi phục chế độ ban đầu **sau khi đã xác nhận transaction kết thúc an toàn**, và xử lý riêng lỗi khôi phục trạng thái. Không chuyển đổi auto-commit giữa các câu SQL đang thuộc một transaction.

## 6. Rollback toàn phần và rollback một phần với `Savepoint`

Có lúc một transaction đã thực hiện một phần bắt buộc và bước tiếp theo chỉ là thao tác **tạm thời**, có thể bỏ đi mà vẫn giữ phần trước. JDBC hỗ trợ `Savepoint` để đánh dấu một vị trí trong transaction.

| Lệnh JDBC | Tác dụng |
|---|---|
| `connection.setSavepoint()` | Tạo mốc trong transaction |
| `connection.setSavepoint("name")` | Tạo mốc có tên nếu driver hỗ trợ |
| `connection.rollback(savepoint)` | Hoàn tác các thay đổi sau mốc đó |
| `connection.rollback()` | Hủy toàn bộ thay đổi chưa commit trong transaction |
| `connection.releaseSavepoint(savepoint)` | Giải phóng mốc; không tương đương `commit()` |

Ví dụ: tạo đơn hàng, thử thêm một ghi chú nháp, sau đó quyết định **không lưu ghi chú nháp** nhưng vẫn lưu đơn hàng:

```sql
CREATE TABLE orders (
    id      BIGINT PRIMARY KEY,
    status  VARCHAR(30) NOT NULL
);

CREATE TABLE order_notes (
    order_id BIGINT NOT NULL,
    note     VARCHAR(200) NOT NULL
);
```

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Savepoint;

public final class SavepointDemo {
    private SavepointDemo() {}

    public static void createWithoutDraftNote(
            DataSource dataSource, long orderId) throws SQLException {

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try {
                try (PreparedStatement ps = connection.prepareStatement(
                        "INSERT INTO orders(id, status) VALUES (?, ?)")) {
                    ps.setLong(1, orderId);
                    ps.setString(2, "CREATED");
                    ps.executeUpdate();
                }

                Savepoint beforeDraft = connection.setSavepoint();

                try (PreparedStatement ps = connection.prepareStatement(
                        "INSERT INTO order_notes(order_id, note) " +
                        "VALUES (?, ?)")) {
                    ps.setLong(1, orderId);
                    ps.setString(2, "Ghi chú nháp");
                    ps.executeUpdate();
                }

                // Chỉ loại bỏ ghi chú được thêm SAU savepoint.
                connection.rollback(beforeDraft);

                // Đơn hàng được thêm TRƯỚC savepoint vẫn được commit.
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
}
```

Sau khi chạy thành công, hàng trong `orders` vẫn tồn tại nhưng hàng nháp trong `order_notes` không tồn tại. Đó là **rollback một phần**, không phải transaction lồng nhau. Nếu không gọi `commit()` sau `rollback(savepoint)`, phần trước savepoint vẫn chưa được xác nhận.

Một số điều kiện cần nhớ:

- Savepoint phải thuộc **cùng connection/transaction**, và chỉ dùng khi `autoCommit=false`.
- Hệ quản trị và driver có thể không hỗ trợ savepoint hoặc có giới hạn. Có thể xem `connection.getMetaData().supportsSavepoints()` trước khi dùng.
- `rollback(savepoint)` không đảm bảo hoàn tác side effect nằm ngoài hệ giao dịch.
- Khi SQL ở bước tùy chọn thất bại, chỉ nên bỏ lỗi và trở về savepoint nếu **loại lỗi đó được nghiệp vụ cho phép bỏ qua**. Không xem mọi `SQLException` (mất kết nối, deadlock, lỗi hạ tầng) là lỗi tùy chọn có thể tiếp tục.

## 7. Rollback trong JDBC batch và CRUD nhiều bảng

`PreparedStatement.addBatch()`/`executeBatch()` giúp gửi nhiều thao tác hiệu quả, nhưng **batch không tự tạo ra một transaction an toàn**. Nếu muốn tất cả hàng được ghi hoặc không hàng nào được ghi, cần đặt batch trong transaction có `autoCommit=false`.

```java
import java.sql.BatchUpdateException;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.List;

public static void insertAccounts(
        Connection connection, List<Long> ids) throws SQLException {

    // Phương thức nhận connection đã được chủ động quản lý từ bên ngoài.
    // Người gọi bắt đầu transaction bằng setAutoCommit(false).
    String sql = "INSERT INTO accounts(id, owner, balance) " +
                 "VALUES (?, ?, ?)";

    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        for (Long id : ids) {
            ps.setLong(1, id);
            ps.setString(2, "New account " + id);
            ps.setBigDecimal(3, new java.math.BigDecimal("0.00"));
            ps.addBatch();
        }
        ps.executeBatch();
    }
}
```

Phương thức `insertAccounts` chỉ thực hiện các câu SQL; **chủ transaction** phải đảm bảo gọi `commit()` hoặc `rollback()`. Đối với lỗi `BatchUpdateException`, driver có thể đã thực hiện một phần batch trước khi báo lỗi và có thể cung cấp `getUpdateCounts()`; không suy ra dữ liệu “tự trở lại nguyên vẹn” chỉ vì batch ném lỗi. Để đạt tính nguyên tử, thực hiện rollback toàn transaction nếu batch thất bại.

Mẫu gọi ở tầng service:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        insertAccounts(connection, List.of(3L, 4L, 5L));
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
```

Các đoạn minh họa từ hai khối trên có thể đặt cùng phương thức/lớp sau khi thêm các import và tham số `dataSource` cần thiết. `List.of(...)` yêu cầu Java 9+. Quy tắc chính là **không để từng helper CRUD tự commit khi nó là một bước của transaction lớn hơn**.

## 8. Những gì `rollback` không thể hứa

Rollback có sức mạnh rõ ràng trong phạm vi giao dịch nhưng không phải thao tác “hoàn tác toàn hệ thống”.

### 8.1. Không đảo ngược một commit đã thành công

Sau khi `commit()` thành công, không thể gọi `rollback()` để xóa lần commit đó. Nếu nghiệp vụ cần sửa lỗi (chẳng hạn hoàn tiền sau thanh toán), hãy tạo **nghiệp vụ bù trừ** trong một transaction mới, ghi nhận lịch sử và bảo đảm tính nhất quán.

### 8.2. Không hoàn tác hoạt động bên ngoài database

Giả sử một transaction JDBC đã gửi email “đã đặt hàng thành công”, rồi thất bại và rollback đơn hàng. Email đã gửi sẽ không biến mất. Với hệ thống có queue, email hoặc API bên ngoài, nên xem xét **transactional outbox**, saga hoặc cơ chế điều phối tương đương theo yêu cầu, thay vì coi rollback DB là rollback mọi side effect.

### 8.3. Không bảo đảm mọi kiểu SQL và đối tượng DB đều có thể rollback

Hành vi phụ thuộc DBMS và storage engine. Một số câu DDL có thể implicit commit; sequence/identity có thể đã cấp số rồi vẫn tăng dù transaction rollback; các bảng/engine không hỗ trợ transaction có thể không hoàn tác dữ liệu. Chẳng hạn, không nên kiểm thử rollback bằng cách `CREATE TABLE` rồi giả định mọi RDBMS đều sẽ bỏ bảng khi rollback. Hãy thực nghiệm bằng **DML trên bảng giao dịch** của DBMS đang dùng.

### 8.4. Không giải quyết tự động deadlock, timeout hay kết nối đã hỏng

Deadlock hoặc timeout có thể khiến DBMS hủy một statement hoặc cả transaction, tùy sản phẩm và loại lỗi. Sau ngoại lệ, việc gọi rollback thường là bước dọn trạng thái thích hợp nhưng có thể thất bại vì connection đã mất. Khi triển khai retry:

- Xác định lỗi nào có thể thử lại dựa trên SQLState/mã lỗi và chính sách DBMS.
- Bắt đầu **transaction mới** và thực hiện lại **toàn bộ đơn vị nghiệp vụ**, không chỉ lệnh SQL cuối đã hỏng.
- Bảo đảm thao tác idempotent hoặc có khóa nghiệp vụ/mã yêu cầu duy nhất để tránh thực hiện hai lần khi trạng thái commit không rõ.

### 8.5. Không thay thế yêu cầu isolation

Hai transaction riêng vẫn có thể cạnh tranh dữ liệu. `rollback()` của transaction A không kiểm soát transaction B; cơ chế khóa, mức cô lập và ràng buộc dữ liệu thuộc trách nhiệm thiết kế riêng. Trong ví dụ chuyển tiền, điều kiện `balance >= ?` bảo vệ phép trừ tiền ngay tại câu SQL; ứng dụng thực tế vẫn cần tính đến truy cập đồng thời và deadlock.

## 9. Những lỗi thường gặp khi dùng `rollback`

| Cách làm sai | Hậu quả | Cách sửa |
|---|---|---|
| Quên `setAutoCommit(false)` trước loạt SQL cần tính nguyên tử | Lệnh thành công trước đó có thể đã commit | Tắt auto-commit trên connection trước loạt thao tác |
| Chỉ `rollback()` khi bắt `SQLException`, nhưng code còn có `RuntimeException` | Nhánh lỗi nghiệp vụ có thể để transaction chưa kết thúc | Xử lý cả lỗi runtime phù hợp, luôn kết thúc transaction rõ ràng |
| Dùng nhiều connection cho các bước rồi rollback một connection | Chỉ hoàn tác được transaction của connection đó | Truyền cùng `Connection` cho các helper tham gia transaction |
| Có `commit()` trong hàm DAO con khi service còn bước tiếp theo | Transaction bị xác nhận quá sớm | Đặt quyền `commit/rollback` tại tầng sở hữu toàn nghiệp vụ |
| Gọi `setAutoCommit(true)` để “reset” trước khi rollback | Có thể commit transaction đang hoạt động | Rollback/commit trước khi khôi phục trạng thái |
| Chỉ dựa vào `Connection.close()` | Hành vi với transaction chưa hoàn tất có thể khác giữa driver/pool | Gọi `rollback()` hoặc `commit()` tường minh |
| Bỏ qua lỗi của `rollback()` | Mất thông tin và có thể hiểu sai trạng thái giao dịch | Đính kèm lỗi rollback bằng `addSuppressed`/log |
| Sau lỗi `commit()` tự động chạy lại giao dịch ngay | Giao dịch trước có thể thực sự đã commit | Đối soát kết quả và dùng cơ chế chống trùng |
| Cho rằng `rollback(savepoint)` cũng hủy phần trước mốc | Lưu lại dữ liệu ngoài ý muốn khi commit tiếp | Phân biệt rollback toàn phần và về savepoint |
| Kiểm thử rollback bằng DDL hoặc bảng không hỗ trợ transaction | Kết luận sai về tính nguyên tử | Kiểm thử DML trên engine/cấu hình thực tế |

## 10. Thực hành tự kiểm tra trên JDBC

Dùng bảng `accounts` ở phần 3, giả định số dư ban đầu là `500000.00` và `300000.00`.

**Tình huống A — thành công:** chạy `transfer(dataSource, 1L, 2L, 150000.00)`. Kiểm tra sau commit: A còn `350000.00`, B có `450000.00`.

**Tình huống B — tài khoản đích không tồn tại:** dùng `toAccount=999`. Phép trừ A có thể thành công tạm thời nhưng phép cộng cập nhật 0 hàng; mã gọi rollback. Kiểm tra A không bị trừ tiền sau khi transaction kết thúc.

**Tình huống C — thiếu tiền:** thử chuyển nhiều hơn số dư A. Lệnh trừ với điều kiện `balance >= ?` cập nhật 0 hàng; chương trình rollback và không cộng tiền B.

**Tình huống D — savepoint:** tạo một order, thêm note, rollback về savepoint trước note và commit. Kiểm tra chỉ còn order.

**Tình huống E — lỗi giữa batch:** thêm các hàng có khóa chính trùng để một bước batch lỗi. Xác minh các hàng chèn trước đó trong cùng transaction không còn sau rollback, miễn là DB/engine hỗ trợ transaction.

Một phép kiểm thử tích hợp có thể kiểm tra giá trị trước và sau transaction:

```java
// Mã giả hướng dẫn kiểm thử, không phải hàm Java độc lập:
BigDecimal beforeA = queryBalance(1L);
BigDecimal beforeB = queryBalance(2L);

assertThrows(SQLException.class, () ->
        TransferRepository.transfer(
                dataSource, 1L, 999L,
                new BigDecimal("150000.00")));

assertEquals(beforeA, queryBalance(1L));
assertEquals(beforeB, queryBalance(2L));
```

`queryBalance` và `assertThrows`/`assertEquals` là các helper của bộ kiểm thử (ví dụ JUnit) do người viết test cung cấp. Nên đọc số dư **trên connection mới sau khi phương thức kết thúc**, để xác minh kết quả thực sự được hoặc không được commit. Đồng thời kiểm tra không có connection bị giữ mở hoặc transaction bị bỏ dở khi ngoại lệ xuất hiện.

## 11. Checklist trước khi áp dụng trong dự án

1. Đã xác định toàn bộ các câu SQL thuộc **cùng một transaction nghiệp vụ** chưa?
2. Đã dùng đúng **một `Connection`**, tắt auto-commit trước các thao tác cần tính nguyên tử chưa?
3. Có kiểm tra hàng bị ảnh hưởng, ràng buộc dữ liệu và mọi điều kiện thành công trước khi gọi `commit()` không?
4. Có rollback khi gặp lỗi, giữ lỗi gốc khi rollback lại thất bại và đóng tài nguyên JDBC đúng cách không?
5. Có phân biệt “rollback không thành công” với “không biết chắc transaction đã commit hay chưa” không?
6. Có nhận diện DDL, sequence, side effect bên ngoài DB và các ranh giới mà rollback không kiểm soát không?
7. Nếu dùng savepoint, đã xác định phần nào được hoàn tác và phần nào vẫn phải commit chưa?
8. Đã kiểm thử ít nhất một đường **commit**, một đường **rollback** và một trường hợp **lỗi giữa các bước** trên DBMS/driver thực tế chưa?

## Ghi nhớ

- **`rollback()`** hoàn tác những thay đổi **chưa commit** của transaction trên **chính `Connection`** đó.
- **`setAutoCommit(false)`** là bước thường dùng để gom các câu SQL JDBC thành một transaction, và **`commit()`** chỉ được gọi khi toàn bộ điều kiện nghiệp vụ đã đạt.
- **`rollback(savepoint)`** hoàn tác một phần transaction; phần trước savepoint vẫn chưa được commit và cần được xử lý tiếp.
- **Rollback không đảo ngược commit đã thành công**, thao tác bên ngoài DB, hoặc mọi loại DDL/sequence/engine.
- **Xử lý lỗi đúng** phải giữ ngoại lệ gốc, ghi nhận lỗi rollback và không phỏng đoán trạng thái sau lỗi commit/mất kết nối.

Dùng `rollback` đúng phạm vi giúp thao tác CRUD nhiều bước, JDBC batch và các nghiệp vụ quan trọng giữ được dữ liệu nhất quán ngay cả khi một lệnh SQL thất bại.
