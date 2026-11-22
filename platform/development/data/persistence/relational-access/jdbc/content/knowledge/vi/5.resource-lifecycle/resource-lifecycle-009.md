# Hành vi đóng kết nối khi giao dịch chưa kết thúc trong JDBC

## 1. Vì sao `Connection.close()` không phải là lệnh kết thúc giao dịch?

Trong chương **Vòng đời tài nguyên**, cần phân biệt hai thao tác thường xuất hiện cạnh nhau:

- **Kết thúc giao dịch:** xác nhận thay đổi bằng `commit()` hoặc hoàn tác bằng `rollback()`.
- **Kết thúc thời gian sử dụng kết nối:** gọi `close()` để giải phóng tài nguyên hoặc trả kết nối về pool.

**JDBC (Java Database Connectivity)** là API của Java để làm việc với cơ sở dữ liệu quan hệ. Giao diện `java.sql.Connection` chứa cả các phương thức giao dịch lẫn phương thức quản lý tài nguyên, nhưng **đóng kết nối không đồng nghĩa với chủ động commit hay rollback**.

Ví dụ, một ứng dụng chuyển tiền thực hiện hai câu SQL:

~~~sql
UPDATE account SET balance = balance - 100 WHERE id = 1;
UPDATE account SET balance = balance + 100 WHERE id = 2;
~~~

Nếu ứng dụng chỉ thực thi câu lệnh thứ nhất rồi đóng kết nối khi giao dịch chưa kết thúc, số dư cuối cùng sẽ phụ thuộc vào cách driver, cơ sở dữ liệu và lớp quản lý kết nối xử lý giao dịch còn mở. Đây là lỗi có thể làm sai dữ liệu nghiệp vụ, đặc biệt khi thao tác ghi gồm nhiều bước.

**Quy tắc cần nhớ:** với một **giao dịch JDBC cục bộ** do ứng dụng quản lý, hãy quyết định `commit()` hoặc `rollback()` một cách tường minh **trước** khi `close()`.

## 2. Ngữ nghĩa `close()` khi còn giao dịch hoạt động

Theo hợp đồng của `java.sql.Connection.close()`, ứng dụng được khuyến nghị mạnh mẽ thực hiện `commit` hoặc `rollback` trước khi đóng kết nối có giao dịch đang hoạt động. **Nếu gọi `close()` trong khi giao dịch chưa kết thúc, kết quả được xác định bởi cách triển khai** (*implementation-defined*), không có một quy tắc chung “JDBC luôn rollback”.

Điều này có những hệ quả trực tiếp:

| Tình huống | Điều có thể khẳng định theo cách sử dụng JDBC đúng |
| --- | --- |
| `autoCommit=false`, đã thực thi `UPDATE`, chưa `commit/rollback`, gọi `close()` | **Không được dựa vào một kết quả chung**; cần xem hợp đồng driver, DBMS và pool. |
| `autoCommit=false`, gọi `commit()` thành công rồi `close()` | Giao dịch đã được yêu cầu xác nhận xong trước khi giải phóng kết nối. |
| `autoCommit=false`, gọi `rollback()` thành công rồi `close()` | Các thay đổi chưa commit của giao dịch đã được yêu cầu hoàn tác trước khi giải phóng kết nối. |
| `autoCommit=true`, câu lệnh đã hoàn tất và tự commit theo ngữ nghĩa JDBC | Không có giao dịch ghi thủ công còn mở chỉ vì ứng dụng chưa gọi `commit()`. |
| `close()` trên handle của connection pool | Thường trả handle về pool; cách xử lý giao dịch chưa kết thúc phụ thuộc pool/driver. |

Một số hệ thống sẽ rollback giao dịch còn mở khi phiên vật lý bị đóng; một số pool chủ động rollback trước khi trả kết nối cho lượt mượn tiếp theo; một số hoàn cảnh khác có thể gây lỗi hoặc có quy tắc riêng. **Không dùng các hành vi quan sát được ở một môi trường làm bảo đảm cho mọi JDBC driver.**

### `isClosed()` không cho biết giao dịch đã commit hay chưa

Sau khi đóng thành công, `connection.isClosed()` thường trả `true` cho đối tượng kết nối đó. Giá trị này chỉ phản ánh **trạng thái đóng của handle JDBC**; nó không trả lời được số tiền đã được commit, rollback hay giao dịch trước đó có kết quả không xác định.

Tương tự, `isValid(timeout)` dùng để xác minh kết nối hiện có khả năng sử dụng hay không, không phải cách xác nhận giao dịch đã commit.

## 3. Hiểu ranh giới giao dịch qua `autoCommit`

Thông thường, một kết nối JDBC mới có `autoCommit=true`. Ở chế độ này, từng câu lệnh SQL được commit tự động khi **câu lệnh hoàn tất** theo quy tắc JDBC. Với truy vấn trả `ResultSet`, trạng thái hoàn tất có thể liên quan đến việc tiêu thụ hoặc đóng kết quả; không nên đồng nhất “đã gọi `executeQuery()`” với “mọi tài nguyên và giao dịch đã hoàn tất”.

Khi ứng dụng chuyển sang:

~~~java
connection.setAutoCommit(false);
~~~

ứng dụng bắt đầu **tự điều khiển ranh giới giao dịch**: các câu lệnh tiếp theo trên cùng `Connection` thuộc giao dịch hiện tại cho đến khi có `commit()` hoặc `rollback()`. Sau khi một giao dịch kết thúc, câu lệnh tiếp theo trên kết nối đó có thể bắt đầu giao dịch mới.

~~~mermaid
flowchart TD
    A["Lấy Connection đang rảnh"] --> B["setAutoCommit(false)"]
    B --> C["UPDATE A"]
    C --> D["UPDATE B"]
    D --> E{"Toàn bộ nghiệp vụ thành công?"}
    E -->|Có| F["commit()"]
    E -->|Không| G["rollback()"]
    F --> H["Khôi phục trạng thái kết nối nếu cần"]
    G --> H
    H --> I["close() / trả kết nối về pool"]
~~~

Một nhầm lẫn nguy hiểm là nghĩ rằng có thể gọi `connection.setAutoCommit(true)` thay cho rollback. **Khi đổi chế độ auto-commit từ `false` sang `true`, JDBC quy định giao dịch hiện tại được commit.** Vì vậy:

~~~java
connection.setAutoCommit(false);
updateAccount(connection);

// Không làm điều này để "dọn trạng thái" khi chưa quyết định giao dịch:
connection.setAutoCommit(true); // Có thể commit thay đổi đang chờ.
~~~

Nếu muốn hoàn tác, hãy gọi `rollback()` **trước** khi khôi phục `autoCommit=true`.

## 4. Ví dụ sai: để `try-with-resources` tự quyết định hậu quả giao dịch

`try-with-resources` của Java tự gọi `close()` khi rời khối, kể cả khi có ngoại lệ. Nó **không tự chèn lời gọi `rollback()` theo ý nghĩa nghiệp vụ**.

~~~java
// Ví dụ cần tránh: SQL được thực thi nhưng không có commit/rollback rõ ràng.
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (PreparedStatement ps = connection.prepareStatement(
            "UPDATE account SET balance = balance - ? WHERE id = ?")) {
        ps.setBigDecimal(1, new BigDecimal("100.00"));
        ps.setLong(2, 1L);
        ps.executeUpdate();
    }

    // Nếu phương thức kết thúc ở đây, try-with-resources gọi close().
    // Giao dịch vẫn chưa được kết thúc bằng commit()/rollback().
}
~~~

Vấn đề không nằm ở `try-with-resources`: cơ chế này rất hữu ích để bảo đảm đóng tài nguyên. Vấn đề là **thiếu quyết định giao dịch trước khi đóng**. Nếu phần mềm chỉ chạy đúng ở môi trường mà pool tự rollback, lỗi có thể lộ ra khi đổi pool, driver hoặc cấu hình.

Một lỗi khác là nghĩ rằng đóng `PreparedStatement` cũng kết thúc giao dịch. `PreparedStatement.close()` chỉ giải phóng tài nguyên câu lệnh; nó **không thay thế** `Connection.commit()` hoặc `Connection.rollback()`.

## 5. Ví dụ đúng: commit hoặc rollback trước khi đóng kết nối

Giả sử dùng một cơ sở dữ liệu quan hệ hỗ trợ giao dịch cho bảng `account`:

~~~sql
CREATE TABLE account (
    id BIGINT PRIMARY KEY,
    balance DECIMAL(19, 2) NOT NULL,
    CONSTRAINT account_balance_nonnegative CHECK (balance >= 0)
);
~~~

Ví dụ Java sử dụng `DataSource` (được cấu hình từ trước) và một kết nối duy nhất để chuyển tiền. Hai DAO helper dùng **chính `Connection` của service**; chỉ service quyết định thời điểm kết thúc giao dịch.

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class TransferService {
    private final DataSource dataSource;

    public TransferService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void transfer(long fromId, long toId, BigDecimal amount)
            throws SQLException {
        if (amount == null || amount.signum() <= 0 || fromId == toId) {
            throw new IllegalArgumentException("Thông tin chuyển tiền không hợp lệ");
        }

        // Điều kiện của ví dụ: DataSource trả kết nối mới được mượn,
        // không có giao dịch đang hoạt động và autoCommit=true.
        try (Connection connection = dataSource.getConnection()) {
            if (!connection.getAutoCommit()) {
                throw new SQLException("Cần Connection đang bật autoCommit");
            }

            connection.setAutoCommit(false);
            boolean transactionEnded = false;

            try {
                debit(connection, fromId, amount);
                credit(connection, toId, amount);

                connection.commit();
                transactionEnded = true;
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                    transactionEnded = true;
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            } finally {
                // Chỉ khôi phục khi commit/rollback đã kết thúc giao dịch.
                // Nếu rollback thất bại, tránh đổi autoCommit gây commit ngầm.
                if (transactionEnded) {
                    connection.setAutoCommit(true);
                }
            }
        } // close() sau khi giao dịch đã được quyết định rõ ràng.
    }

    private static void debit(Connection connection, long id,
                              BigDecimal amount) throws SQLException {
        String sql = "UPDATE account SET balance = balance - ? "
                   + "WHERE id = ? AND balance >= ?";
        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setBigDecimal(1, amount);
            ps.setLong(2, id);
            ps.setBigDecimal(3, amount);
            if (ps.executeUpdate() != 1) {
                throw new SQLException(
                        "Tài khoản nguồn không tồn tại hoặc không đủ tiền");
            }
        }
    }

    private static void credit(Connection connection, long id,
                               BigDecimal amount) throws SQLException {
        String sql = "UPDATE account SET balance = balance + ? WHERE id = ?";
        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setBigDecimal(1, amount);
            ps.setLong(2, id);
            if (ps.executeUpdate() != 1) {
                throw new SQLException("Tài khoản đích không tồn tại");
            }
        }
    }
}
~~~

### Đọc luồng thành công

1. Service xác minh đầu vào, mượn một `Connection` đang rảnh.
2. Gọi `setAutoCommit(false)` để tự quản lý giao dịch.
3. Trừ tiền và cộng tiền bằng `PreparedStatement` tạo trên **cùng kết nối**.
4. Chỉ khi cả hai câu SQL thành công, gọi `commit()`.
5. Sau khi commit thành công, khôi phục `autoCommit=true` rồi đóng/trả kết nối.

### Đọc luồng thất bại

Giả sử đã trừ tiền khỏi A, nhưng bước cộng B phát hiện tài khoản đích không tồn tại. Phương thức helper ném `SQLException`, service cố gắng gọi `rollback()`; khi rollback thành công, các thay đổi chưa commit của giao dịch được hoàn tác. Sau đó mới khôi phục trạng thái kết nối và để `try-with-resources` gọi `close()`.

Nếu rollback thất bại, **trạng thái giao dịch có thể không xác định**. Trong ví dụ, `transactionEnded` không được đặt thành `true` khi rollback thất bại, nên không bật `autoCommit=true` một cách mù quáng. `close()` vẫn diễn ra để giải phóng handle; với hệ thống thực tế, pool phải có chính sách loại bỏ hoặc xử lý kết nối không an toàn. Vì kết quả của việc đóng kết nối còn giao dịch lỗi là không portable, phải giữ và xử lý lỗi rollback, không tự tuyên bố đã hoàn tác thành công.

**Giới hạn quan trọng:** nếu `commit()` báo lỗi do mất kết nối đúng thời điểm xác nhận, ứng dụng không phải lúc nào cũng biết DBMS đã commit hay chưa. Có thể thử rollback trong nhánh lỗi, nhưng rollback thất bại hoặc thành công về sau cũng không nhất thiết chứng minh giao dịch trước đó chưa từng được commit. Nghiệp vụ tiền tệ thực tế cần cơ chế đối soát, định danh yêu cầu và chống xử lý trùng khi retry.

## 6. Những trường hợp `close()` có thể xuất hiện bất ngờ

### 6.1. `return` hoặc ngoại lệ trong `try-with-resources`

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    executeUpdate(connection);

    if (someCondition) {
        return; // Java vẫn gọi close() trước khi thoát phương thức.
    }

    connection.commit();
}
~~~

Nếu điều kiện đúng, phương thức trả về trước `commit()`; `close()` được gọi khi giao dịch còn mở. Hãy tổ chức mã để **mọi đường đi** (thành công, thất bại, `return` sớm) đều quyết định giao dịch trước khi rời phạm vi sở hữu kết nối.

Tương tự, nếu `executeUpdate()` ném ngoại lệ và ứng dụng chỉ dùng `try-with-resources` nhưng không có nhánh rollback, kết nối sẽ bị đóng trong trạng thái chưa được quyết định rõ ràng.

### 6.2. Ngoại lệ khi đóng tài nguyên

`Connection.close()` có thể ném `SQLException`. Trong `try-with-resources`, nếu thân `try` đã ném một ngoại lệ và thao tác `close()` cũng ném lỗi, Java giữ ngoại lệ ban đầu làm lỗi chính và ghi lỗi đóng trong danh sách `getSuppressed()`:

~~~java
try (Connection connection = dataSource.getConnection()) {
    // Xử lý giao dịch có commit/rollback tường minh.
} catch (SQLException error) {
    System.err.println("Lỗi chính: " + error.getMessage());
    for (Throwable suppressed : error.getSuppressed()) {
        System.err.println("Lỗi bổ sung: " + suppressed.getMessage());
    }
    throw error;
}
~~~

Cần phân biệt **lỗi rollback** do ứng dụng chủ động thêm bằng `addSuppressed()` với **lỗi đóng tài nguyên** được Java tự thêm. Cả hai đều có thể hữu ích khi truy tìm lý do kết nối hoặc giao dịch thất bại.

### 6.3. DAO đóng nhầm kết nối do service quản lý

~~~java
void updateBalance(Connection connection) throws SQLException {
    // Sai khi caller đang sở hữu giao dịch:
    try (Connection ignored = connection) {
        // Chạy UPDATE...
    } // Đóng luôn kết nối của caller.
}
~~~

Khi một service cần gọi nhiều DAO trong cùng giao dịch, **service hoặc transaction manager sở hữu kết nối**. DAO chỉ nên đóng `PreparedStatement`/`ResultSet` do mình tạo. Đóng `Connection` sớm có thể kết thúc phiên trước khi service kịp `commit()` hoặc `rollback()`.

### 6.4. Đóng kết nối có ResultSet hoặc Statement đang mở

Đóng kết nối thường kéo theo việc các tài nguyên gắn với nó không còn dùng được. Tuy nhiên, đóng `ResultSet` hay `Statement` **không phải** lệnh rollback cho giao dịch đang mở. Với truy vấn lớn, giữ cursor/statement mở cũng có thể giữ tài nguyên hoặc ảnh hưởng thời điểm câu lệnh được xem là hoàn tất tùy chế độ JDBC. Hãy đóng tài nguyên con đúng phạm vi, rồi kết thúc giao dịch, sau đó đóng kết nối.

## 7. Connection pool thay đổi ý nghĩa thao tác `close()` như thế nào?

Trong ứng dụng có pool (ví dụ sử dụng `DataSource` của thư viện quản lý kết nối), lời gọi `getConnection()` thường lấy **handle logic** đại diện cho một kết nối vật lý đang được pool quản lý.

~~~mermaid
flowchart LR
    A["Service"] -->|"getConnection()"| B["Connection handle"]
    B -->|"SQL / transaction"| D[("DBMS")]
    A -->|"handle.close()"| C["Connection pool"]
    C -->|"kiểm tra / reset / cấp lại"| B
~~~

`Connection.close()` trên handle logic có thể trả kết nối vật lý về pool thay vì ngắt mạng. Nếu bỏ qua `commit/rollback`, một pool có thể cố gắng rollback hoặc reset trạng thái khi trả kết nối, nhưng **không nên coi hành vi này là cam kết của chuẩn JDBC cho mọi pool**.

Một số điều cần lưu ý:

| Hành vi | Ý nghĩa thực tế |
| --- | --- |
| Đóng handle đã mượn | Kết thúc quyền sử dụng của lượt mượn hiện tại. |
| Pool tiếp tục giữ kết nối vật lý | Tối ưu chi phí tạo kết nối mới; không có nghĩa handle cũ còn dùng được. |
| Pool reset `autoCommit`, isolation, read-only… | Giúp lượt mượn tiếp theo có trạng thái kỳ vọng; cấu hình/cơ chế cụ thể phụ thuộc pool. |
| Pool phát hiện giao dịch hoặc kết nối lỗi | Có thể rollback, đóng vật lý hoặc loại bỏ kết nối; cần theo dõi chính sách và metric pool. |

**Điểm đặc biệt nguy hiểm:** tự gọi `setAutoCommit(true)` để “reset” một kết nối trước khi rollback có thể **commit các thay đổi chưa hoàn tất**. Kể cả pool có chức năng tự reset trạng thái, ứng dụng vẫn phải kết thúc giao dịch chủ động.

Nếu rollback thất bại vì sự cố mạng, một pool tốt cần nhận diện hoặc loại bỏ kết nối lỗi. Chi tiết API để loại bỏ kết nối (evict, invalidate, mark broken) tùy thư viện, nên không thể đưa ra một lời gọi chung cho mọi `DataSource`.

## 8. Khi framework quản lý giao dịch

Trong môi trường có transaction manager (ví dụ Spring `@Transactional`, JTA hoặc container quản lý giao dịch), **chủ sở hữu giao dịch có thể không phải phương thức DAO**. Framework thường chịu trách nhiệm nhận diện ranh giới giao dịch, xác nhận hoặc hoàn tác, rồi dọn các tài nguyên được quản lý.

Ví dụ về **ý nghĩa kiến trúc**:

~~~java
// Mã khái niệm khi dùng transaction manager phù hợp.
@Transactional
public void changeBalances(long fromId, long toId, BigDecimal amount) {
    accountRepository.debit(fromId, amount);
    accountRepository.credit(toId, amount);
}
~~~

Trong kiểu kiến trúc này, repository phải sử dụng cơ chế lấy kết nối **tham gia cùng transaction manager**. Nếu DAO tự tạo kết nối ngoài ngữ cảnh đó hoặc tự đóng/commit một kết nối do framework đang sở hữu, hoạt động có thể thoát khỏi giao dịch dự kiến.

Đừng áp dụng máy móc ví dụ `Connection.commit/rollback` thủ công cho kết nối mà JTA/container đang điều phối: một số thao tác giao dịch cục bộ trên kết nối được quản lý có thể không hợp lệ hoặc tạo xung đột. Hãy tuân theo hợp đồng của framework và API truy cập dữ liệu tương ứng.

## 9. Cách xử lý khi commit hoặc rollback gặp lỗi

Một nguyên tắc quan trọng là **phân biệt kết quả đã xác định và kết quả chưa xác định**:

| Sự kiện | Điều ứng dụng có thể kết luận |
| --- | --- |
| `commit()` trả về bình thường | Driver báo giao dịch đã commit thành công. |
| `rollback()` trả về bình thường trước khi có commit thành công | Driver báo giao dịch hiện tại đã rollback. |
| `rollback()` ném `SQLException` | **Không được kết luận** các thay đổi đã được hoàn tác. |
| `commit()` ném `SQLException` khi mất kết nối | Có thể không biết DBMS đã commit hay chưa; cần đối soát tùy nghiệp vụ. |
| `close()` trả về bình thường sau giao dịch còn mở | Chỉ biết thao tác đóng hoàn tất theo driver/pool; không suy ra giao dịch đã rollback. |

Không nên retry **mù quáng** một giao dịch ghi chỉ vì `commit()` báo lỗi. Ví dụ với thanh toán hoặc chuyển tiền, DBMS có thể đã commit nhưng phản hồi không tới được ứng dụng. Nếu gửi lại yêu cầu thiếu idempotency, hệ thống có thể ghi trùng.

Đối với nhiều tình huống, hành vi xử lý hợp lý là:

1. Ghi log đủ `SQLState`, mã lỗi và chuỗi nguyên nhân, nhưng tránh ghi bí mật hoặc dữ liệu nhạy cảm.
2. Giữ cả lỗi rollback và lỗi đóng kết nối bằng `addSuppressed()`/`getSuppressed()` hoặc cách xử lý ngoại lệ tương đương.
3. Để pool/transaction manager xử lý việc loại bỏ kết nối không còn đáng tin cậy.
4. Chỉ quyết định retry sau khi biết loại lỗi, tính lặp lại an toàn và cách xác minh trạng thái nghiệp vụ.

## 10. Thực hành kiểm chứng với hệ quản trị đang dùng

Ví dụ minh họa dưới đây hữu ích để **quan sát** hành vi, nhưng không dùng làm cơ sở cho một thiết kế phụ thuộc vào rollback tự động:

1. Tạo bảng thử nghiệm và một bản ghi với số dư ban đầu xác định.
2. Lấy `Connection` A, gọi `setAutoCommit(false)` rồi cập nhật bản ghi; chưa `commit()`.
3. Dùng `Connection` B đọc dữ liệu và ghi nhận điều quan sát được (có thể bị chờ khóa, thấy giá trị cũ hoặc khác tùy isolation/DBMS).
4. Thử gọi `A.rollback()` **rồi** `A.close()`. Kiểm tra kết quả sau khi hoàn tác.
5. Làm lại trên dữ liệu thử nghiệm, nhưng lần này gọi `A.commit()` **rồi** `A.close()`. Kiểm tra kết quả đã lưu.
6. Chỉ trong môi trường thử nghiệm cô lập, nếu muốn quan sát cách driver/pool xử lý giao dịch chưa kết thúc khi `close()`, dùng bảng dữ liệu không quan trọng và ghi rõ phiên bản driver, DBMS, pool. Kết quả này **không phải cam kết portable** cho môi trường khác.

Một bài tập lý thuyết:

~~~java
connection.setAutoCommit(false);
updateA(connection);
connection.commit();
updateB(connection);
connection.close();
~~~

**Hỏi:** sau `close()`, có thể chắc chắn `updateB` đã rollback không?

**Trả lời:** Không. `updateA` đã thuộc giao dịch được commit; `updateB` thuộc một giao dịch mới, chưa có `commit/rollback` tường minh. Kết quả của giao dịch đó khi đóng kết nối phụ thuộc triển khai. Muốn hủy `updateB`, phải gọi `rollback()` trước `close()`.

## 11. Checklist trước khi giải phóng `Connection`

- **Tính nguyên tử:** mọi thao tác SQL bắt buộc thành công cùng nhau có dùng cùng một `Connection` hoặc cùng ngữ cảnh transaction manager không?
- **Kết thúc giao dịch:** mọi đường đi thành công đều gọi `commit()` đúng lúc; đường đi thất bại đều cố gắng `rollback()` và không che giấu lỗi?
- **Thứ tự:** khi chuyển `autoCommit=false` về `true`, giao dịch đã được `commit/rollback` thành công chưa?
- **Tài nguyên:** `ResultSet` và `PreparedStatement` do ai tạo, có được đóng đúng phạm vi không?
- **Quyền sở hữu:** lớp đang gọi `close()` có thật sự là chủ sở hữu kết nối, hay kết nối do service/transaction manager khác quản lý?
- **Pool:** có chính sách phát hiện và loại bỏ kết nối hỏng, khôi phục trạng thái, giới hạn thời gian mượn kết nối không?
- **Lỗi bất thường:** nếu `commit/rollback` thất bại, ứng dụng có bảo toàn nguyên nhân, tránh kết luận sai và chống retry trùng không?

**Ghi nhớ:** `Connection.close()` giải phóng quyền sử dụng kết nối, **không phải** một cách portable để quyết định số phận giao dịch JDBC đang mở. Hãy `commit()` khi nghiệp vụ hoàn thành hoặc `rollback()` khi cần hủy, sau đó mới đóng hoặc trả kết nối về pool. `try-with-resources` đảm bảo dọn tài nguyên, còn **ứng dụng hoặc transaction manager** chịu trách nhiệm về ranh giới giao dịch.
