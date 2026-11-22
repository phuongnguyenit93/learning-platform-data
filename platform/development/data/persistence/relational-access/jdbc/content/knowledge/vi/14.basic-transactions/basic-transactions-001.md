# Ranh giới giao dịch và vai trò của cùng một `Connection` trong JDBC

## 1. Vì sao cần hiểu ranh giới giao dịch?

**JDBC (Java Database Connectivity)** là API giúp ứng dụng Java kết nối và thực thi SQL trên cơ sở dữ liệu quan hệ. Khi một nghiệp vụ cần nhiều câu lệnh SQL cùng thành công hoặc cùng thất bại, chỉ thực thi chúng lần lượt là chưa đủ: ứng dụng phải xác định **giao dịch (transaction)** nào bao trùm các câu lệnh đó.

Ví dụ: chuyển 500.000 đồng từ tài khoản A sang tài khoản B cần tối thiểu hai thao tác:

1. Trừ 500.000 đồng ở tài khoản A.
2. Cộng 500.000 đồng ở tài khoản B.

Nếu thao tác 1 đã được lưu vĩnh viễn nhưng thao tác 2 lỗi, tổng số tiền trong hệ thống bị sai. Giao dịch giúp thực hiện cả hai thay đổi như một đơn vị: **`commit()` khi tất cả đạt yêu cầu; `rollback()` nếu có lỗi**.

Sau bài này, bạn có thể xác định điểm bắt đầu/kết thúc giao dịch JDBC, giải thích vì sao các DAO phải dùng cùng một `Connection`, và viết mã xử lý thành công, thất bại, dọn tài nguyên đúng cách.

## 2. Ranh giới giao dịch nằm ở đâu?

Với **giao dịch JDBC cục bộ (local transaction)**, ranh giới giao dịch được điều khiển trên **một đối tượng `java.sql.Connection` cụ thể**. Những lệnh SQL gửi qua `Statement` hoặc `PreparedStatement` tạo từ kết nối đó thuộc giao dịch hiện tại của kết nối, tùy trạng thái `autoCommit`.

| Thao tác JDBC | Ý nghĩa |
| --- | --- |
| `connection.getAutoCommit()` | Kiểm tra chế độ tự động commit hiện tại. |
| `connection.setAutoCommit(false)` | Chuyển sang quản lý giao dịch thủ công; các thao tác kế tiếp trên kết nối sẽ chờ `commit` hoặc `rollback`. |
| `connection.commit()` | Xác nhận các thay đổi trong giao dịch hiện tại trên kết nối. |
| `connection.rollback()` | Hủy những thay đổi chưa commit trong giao dịch hiện tại trên kết nối. |
| `connection.setAutoCommit(true)` | Trở lại tự động commit; **nếu đang có giao dịch còn mở, thao tác đổi chế độ này sẽ commit giao dịch đó**. |
| `connection.close()` | Đóng hoặc trả kết nối về pool; **không dùng thay cho quyết định commit/rollback rõ ràng**. |

Theo JDBC, `autoCommit` mặc định của kết nối mới thường là `true`. Khi bật, mỗi câu lệnh SQL được commit tự động khi hoàn tất theo quy tắc JDBC (ví dụ `ResultSet` có thể cần được tiêu thụ/đóng để câu lệnh được xem là hoàn tất). Hai lệnh `UPDATE` được thực thi nối tiếp trong chế độ này **không mặc nhiên** tạo thành một giao dịch chung.

Khi tắt `autoCommit`, giao dịch phát sinh khi kết nối thực thi câu lệnh đầu tiên; sau mỗi `commit()` hoặc `rollback()`, câu lệnh tiếp theo trên cùng kết nối thuộc một giao dịch mới. Không cần phát lệnh SQL `BEGIN TRANSACTION` nếu đã dùng API JDBC để quản lý giao dịch thủ công.

~~~mermaid
flowchart TD
    A["Lấy một Connection"] --> B["setAutoCommit(false)"]
    B --> C["UPDATE tài khoản A"]
    C --> D["UPDATE tài khoản B"]
    D --> E{"Tất cả thành công?"}
    E -->|Có| F["commit()"]
    E -->|Không| G["rollback()"]
    F --> H["Khôi phục trạng thái và đóng/trả Connection"]
    G --> H
~~~

**Điểm quan trọng:** lời gọi `commit()` không có nghĩa “commit mọi thay đổi của ứng dụng”. Nó chỉ tác động đến **giao dịch hiện tại gắn với kết nối được gọi**.

## 3. Vì sao phải là cùng một `Connection`?

Giả sử hai phương thức truy cập dữ liệu được viết như sau:

~~~java
void truTien(long taiKhoanA, BigDecimal soTien) throws SQLException {
    try (Connection c1 = dataSource.getConnection()) {
        // Thực thi UPDATE trừ tiền bằng c1.
    }
}

void congTien(long taiKhoanB, BigDecimal soTien) throws SQLException {
    try (Connection c2 = dataSource.getConnection()) {
        // Thực thi UPDATE cộng tiền bằng c2.
    }
}
~~~

Dù `c1` và `c2` được lấy từ **cùng `DataSource`**, dùng **cùng tài khoản đăng nhập** và thao tác trên **cùng cơ sở dữ liệu**, chúng vẫn là hai kết nối JDBC riêng biệt. Gọi `c1.rollback()` không thể hoàn tác thay đổi đã commit qua `c2` và ngược lại. Nếu `autoCommit=true`, mỗi `UPDATE` còn có thể được commit độc lập ngay khi hoàn tất.

| Cách tổ chức | Kết quả |
| --- | --- |
| DAO A và DAO B nhận **cùng `Connection`**, `autoCommit=false` | Có thể cùng nằm trong một giao dịch JDBC cục bộ; một lần `commit/rollback` quyết định cả hai. |
| Mỗi DAO tự gọi `dataSource.getConnection()` | Thường nhận các kết nối khác nhau; không được giả định chung một giao dịch. |
| Hai `Statement` tạo từ cùng `Connection` | Chúng sử dụng trạng thái giao dịch của cùng kết nối. |
| Cùng một `Connection` nhưng gọi `commit()` ở giữa hai SQL | SQL trước đã kết thúc giao dịch; SQL sau nằm ở giao dịch kế tiếp. |
| Chia sẻ một `Connection` cho nhiều luồng đồng thời | Dễ gây lẫn câu lệnh, `commit` và `rollback`; nên giới hạn quyền sử dụng kết nối trong một luồng/luồng nghiệp vụ tại một thời điểm. |

Vì vậy, **tầng điều phối nghiệp vụ** nên lấy và quản lý một `Connection`, sau đó **truyền chính kết nối đó** vào mọi phương thức DAO tham gia cùng giao dịch.

## 4. Ví dụ đầy đủ: chuyển tiền an toàn trong một giao dịch

Giả sử có bảng quan hệ:

~~~sql
CREATE TABLE bank_account (
    id BIGINT PRIMARY KEY,
    balance DECIMAL(19, 2) NOT NULL
);
~~~

Ví dụ Java dưới đây sử dụng `javax.sql.DataSource`, `java.sql.Connection`, `java.sql.PreparedStatement`, `java.sql.SQLException` và `java.math.BigDecimal`. Ta giả định `DataSource` cung cấp một kết nối **đang rảnh, không có giao dịch dang dở**, và DB hỗ trợ giao dịch cho bảng này.

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

        // Chỉ lấy Connection MỘT LẦN cho toàn bộ nghiệp vụ.
        try (Connection connection = dataSource.getConnection()) {
            boolean originalAutoCommit = connection.getAutoCommit();
            connection.setAutoCommit(false);
            boolean transactionFinished = false;

            try {
                debit(connection, fromId, amount);
                credit(connection, toId, amount);

                connection.commit();
                transactionFinished = true;
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                    transactionFinished = true;
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            } finally {
                // Chỉ khôi phục autoCommit khi đã commit/rollback thành công.
                if (transactionFinished) {
                    connection.setAutoCommit(originalAutoCommit);
                }
            }
        }
    }

    private static void debit(Connection connection, long accountId,
                              BigDecimal amount) throws SQLException {
        String sql = "UPDATE bank_account SET balance = balance - ? "
                   + "WHERE id = ? AND balance >= ?";
        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setBigDecimal(1, amount);
            ps.setLong(2, accountId);
            ps.setBigDecimal(3, amount);
            if (ps.executeUpdate() != 1) {
                throw new SQLException("Tài khoản nguồn không tồn tại hoặc không đủ tiền");
            }
        }
    }

    private static void credit(Connection connection, long accountId,
                               BigDecimal amount) throws SQLException {
        String sql = "UPDATE bank_account SET balance = balance + ? "
                   + "WHERE id = ?";
        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setBigDecimal(1, amount);
            ps.setLong(2, accountId);
            if (ps.executeUpdate() != 1) {
                throw new SQLException("Tài khoản đích không tồn tại");
            }
        }
    }
}
~~~

Ví dụ thể hiện rõ **ai sở hữu giao dịch**: `transfer()` quyết định `setAutoCommit(false)`, `commit()`, `rollback()`; `debit()` và `credit()` chỉ chạy SQL trên `Connection` được nhận. Các DAO **không** tự `commit`, `rollback`, đóng kết nối hoặc gọi `getConnection()`.

`executeUpdate()` trả về số dòng bị tác động. Nếu không trừ được tiền (ví dụ không đủ số dư) hoặc không tìm thấy tài khoản đích, phương thức ném `SQLException`; nhánh `catch` rollback cả hai thay đổi chưa commit. Điều kiện `balance >= ?` nằm ngay trong lệnh `UPDATE` giúp tránh trường hợp hai luồng đều dựa vào cùng một kết quả kiểm tra số dư cũ trước khi trừ tiền.

Khối `try-with-resources` đảm bảo đóng `PreparedStatement` và `Connection`. Với kết nối lấy từ pool, `close()` thường là **trả về pool**, nên cần khôi phục trạng thái kết nối sau giao dịch đã kết thúc. Nếu `rollback()` thất bại, trạng thái giao dịch có thể chưa xác định: ví dụ cố ý **không** bật `autoCommit` lại trong trường hợp đó, đồng thời giữ lỗi rollback ở `suppressed exceptions` để tầng kết nối/pool xử lý kết nối hỏng. Ứng dụng thực tế cần cấu hình pool để phát hiện, hủy hoặc reset kết nối không an toàn.

**Lưu ý:** `commit()` có thể trả lỗi khi kết quả đã trở nên không chắc chắn do mất kết nối, và chương trình không nên tự động thực hiện lại giao dịch chuyển tiền nếu chưa có cơ chế chống thực hiện trùng (như khóa idempotency). Ví dụ này tập trung vào ranh giới giao dịch trên một kết nối, không thay thế toàn bộ thiết kế hệ thống thanh toán.

## 5. Phân biệt giao dịch nghiệp vụ và giao dịch JDBC

Một yêu cầu HTTP “đặt hàng” có thể gọi các bước: tạo đơn, trừ tồn kho, ghi thanh toán, gửi email. **Giao dịch JDBC cục bộ** chỉ quản lý các thao tác SQL được thực hiện qua **cùng kết nối** và trong **cùng một khoảng giữa `setAutoCommit(false)` với `commit/rollback`**.

Không nên suy ra rằng các hành động bên ngoài cơ sở dữ liệu (gọi API, gửi email, ghi file, đẩy message) cũng được hoàn tác bởi `connection.rollback()`. Với nhiều nguồn dữ liệu/kết nối cần giao dịch phân tán, có thể cần JTA/XA hoặc một thiết kế phối hợp như outbox/saga, tùy yêu cầu hệ thống. Một `Connection` JDBC thông thường không tự cấp cơ chế commit nguyên tử cho hai cơ sở dữ liệu độc lập.

Trong Spring, `@Transactional` có thể giúp framework gắn một kết nối với ngữ cảnh giao dịch và quản lý `commit/rollback`, **khi** transaction manager và tầng truy cập dữ liệu được cấu hình đúng. Một DAO tự lấy kết nối JDBC ngoài ngữ cảnh quản lý giao dịch vẫn có nguy cơ thoát khỏi giao dịch mong muốn.

## 6. Những điểm dễ gây nhầm lẫn

### 6.1. `autoCommit=false` không có nghĩa mọi SQL sau đó thuộc mãi một giao dịch

Mỗi lần `commit()` hoặc `rollback()` kết thúc giao dịch hiện tại. Nếu tiếp tục gọi SQL khi `autoCommit=false`, kết nối bắt đầu một giao dịch mới. Do đó:

~~~java
connection.setAutoCommit(false);
updateA(connection);
connection.commit(); // Giao dịch thứ nhất kết thúc.
updateB(connection);
connection.rollback(); // Chỉ hoàn tác giao dịch thứ hai.
~~~

Không thể dùng `rollback()` ở cuối để đảo ngược `updateA()` đã commit.

### 6.2. `rollback()` không xóa dữ liệu đã commit bởi kết nối khác

~~~java
Connection a = dataSource.getConnection();
Connection b = dataSource.getConnection();
// Nếu b đã commit thay đổi, gọi a.rollback() không thể hủy thay đổi đó.
~~~

Hai biến có cùng URL JDBC, user/password, schema, thậm chí được lấy cùng một pool không bảo đảm chung giao dịch.

### 6.3. Đọc dữ liệu trong giao dịch không có nghĩa kết nối khác nhìn thấy ngay

Ví dụ, kết nối A đặt `autoCommit=false`, cập nhật số dư nhưng chưa commit. Kết nối B thực hiện `SELECT`. Kết quả B nhận được phụ thuộc mức cô lập (`READ_COMMITTED`, `REPEATABLE_READ`, `SERIALIZABLE`...), DBMS, cơ chế khóa và thời điểm đọc. B có thể thấy giá trị đã commit trước đó hoặc bị chờ khóa; không nên mặc định B thấy thay đổi chưa commit.

Giao dịch đem lại tính **nguyên tử** trong phạm vi nói trên; tính nhất quán khi nhiều kết nối truy cập đồng thời còn phụ thuộc **isolation**, ràng buộc dữ liệu và cách viết SQL. Có thể đọc/thiết lập `connection.getTransactionIsolation()` và `connection.setTransactionIsolation(...)`, nhưng lựa chọn mức cô lập cần phù hợp DBMS và tình huống nghiệp vụ.

### 6.4. Lỗi SQL không đồng nghĩa JDBC tự rollback toàn bộ giao dịch

Sau `SQLException`, không được mặc định mọi câu lệnh trước đó đã hoàn tác. Cơ sở dữ liệu có thể đánh dấu giao dịch lỗi hoặc chỉ hủy câu lệnh lỗi, tùy hệ quản trị và loại lỗi. Hãy cố gắng `rollback()`, lưu cả lỗi rollback nếu có, và tránh tái sử dụng kết nối khi trạng thái không xác định.

### 6.5. `close()` và DDL không phải là công cụ xác định commit

Không dựa vào việc đóng kết nối để tự động rollback: nếu đóng khi còn giao dịch đang mở, kết quả có thể phụ thuộc driver/pool. Ngoài ra, một số DBMS thực hiện commit ngầm cho câu lệnh DDL như `CREATE TABLE`, `ALTER TABLE`. Khi cần tính nguyên tử, hãy xác minh quy tắc DDL/transaction của DBMS đang dùng.

### 6.6. Savepoint vẫn thuộc giao dịch của chính kết nối

Nếu muốn hoàn tác một phần công việc, có thể dùng `Savepoint point = connection.setSavepoint()` rồi `connection.rollback(point)`. Savepoint không tạo một giao dịch độc lập và không thể chuyển sang `Connection` khác. Khả năng hỗ trợ savepoint phụ thuộc driver/DBMS; `commit()` cuối cùng vẫn quyết định toàn giao dịch còn lại.

## 7. Tự kiểm tra bằng một kịch bản nhỏ

Giả sử bảng có A = 1.000.000 và B = 200.000. Lần lượt thử:

1. Dùng **một kết nối**, tắt `autoCommit`, trừ A 500.000 và cộng B 500.000 rồi `commit()`. Sau commit, A = 500.000 và B = 700.000.
2. Khôi phục dữ liệu ban đầu, dùng **một kết nối**, tắt `autoCommit`, trừ A rồi cố tình phát sinh lỗi trước khi cộng B; `rollback()`. Sau rollback, A = 1.000.000 và B = 200.000.
3. Khôi phục dữ liệu ban đầu, dùng **hai kết nối** bật `autoCommit`: trừ A qua kết nối 1, sau đó cho thao tác cộng B qua kết nối 2 thất bại. Bạn sẽ quan sát A đã giảm: một minh chứng vì sao ranh giới giao dịch bị tách sai.

Trong lúc giao dịch còn mở, có thể thử đọc từ kết nối thứ hai để quan sát quy tắc cô lập của DBMS. Đừng dựa vào một kết quả quan sát cụ thể để kết luận rằng mọi cơ sở dữ liệu đều hoạt động giống nhau.

## 8. Checklist khi viết giao dịch JDBC

- Xác định **một nghiệp vụ cần nguyên tử** gồm những SQL nào, và giao cho tầng điều phối sở hữu ranh giới `commit/rollback`.
- Lấy **một `Connection` đang rảnh** và truyền nó cho mọi DAO của nghiệp vụ; tắt `autoCommit` trước khi thực thi các SQL liên quan.
- Dùng `PreparedStatement`; kiểm tra số dòng bị ảnh hưởng và các điều kiện nghiệp vụ trước khi commit.
- Chỉ `commit()` sau khi tất cả bước bắt buộc thành công; khi lỗi, gọi `rollback()` và giữ nguyên thông tin lỗi.
- Đóng `Statement`, `ResultSet`, `Connection` và khôi phục trạng thái kết nối đã kết thúc giao dịch nếu cần trả về pool.
- Xem xét khóa, isolation, deadlock, timeout, khả năng retry an toàn và các tác động bên ngoài DB nếu nghiệp vụ có nhiều người dùng đồng thời.

**Ghi nhớ:** giao dịch JDBC cục bộ được xác định bởi **cùng `Connection` + cùng khoảng thời gian trước `commit/rollback`**. Nhiều câu lệnh SQL chỉ thực sự chia sẻ một quyết định thành công hay thất bại khi chúng nằm trong cùng ranh giới đó.
