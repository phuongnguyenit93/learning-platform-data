# Đóng kết nối, câu lệnh và tập kết quả bằng try-with-resources

Một ứng dụng Java gọi database để đọc thông tin khách hàng. Mỗi yêu cầu có thể tạo ra một `Connection`, một `PreparedStatement` và một `ResultSet`. Nếu những đối tượng này không được đóng đúng lúc, ứng dụng có thể giữ phiên kết nối, cursor phía database và tài nguyên của connection pool, kể cả khi mã xử lý nghiệp vụ đã kết thúc. Hệ quả dễ thấy là phản hồi chậm, nhiều yêu cầu chờ kết nối và lỗi hết connection pool.

Bài học thuộc chương **Kết nối và tài nguyên** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Người học sẽ thiết kế vòng đời tài nguyên JDBC trong Java bằng **try-with-resources**, xác định ai có trách nhiệm đóng từng tài nguyên, phân biệt `close()` với commit/rollback và biết cách xử lý cả đường thành công lẫn ngoại lệ. Đây là nền tảng của persistence ổn định trong ứng dụng có truy vấn, giao dịch, kiểm soát đồng thời và xử lý lỗi kết nối.

## 1. Ba tài nguyên JDBC quan trọng

| Tài nguyên | Tác dụng | Thường được tạo bằng | Điều có thể xảy ra nếu không đóng |
| --- | --- | --- | --- |
| **`Connection`** | Phiên kết nối, ngữ cảnh thực thi SQL và giao dịch | `dataSource.getConnection()` | Chiếm suất trong pool, giữ tài nguyên phiên và có thể để giao dịch mở |
| **`Statement` / `PreparedStatement`** | Gửi lệnh SQL, lưu trạng thái lệnh và tham số | `connection.prepareStatement(sql)` | Giữ statement, cursor hoặc tài nguyên driver/server |
| **`ResultSet`** | Duyệt các hàng và cột trả về | `statement.executeQuery()` | Giữ bộ đệm hoặc cursor và kéo dài thời gian giữ kết nối |

`PreparedStatement` là một loại `Statement`, thường được ưu tiên vì hỗ trợ truyền tham số đúng kiểu và giảm rủi ro SQL injection. Các loại trên hỗ trợ `AutoCloseable` theo API JDBC, nên có thể được khai báo trong `try-with-resources`.

Theo JDBC, đóng `Statement` cũng đóng `ResultSet` hiện tại mà statement đó sinh ra; đóng `Connection` có thể làm những tài nguyên phụ thuộc không còn khả dụng. Tuy nhiên, **khai báo và đóng rõ từng tài nguyên** giúp giải phóng sớm và cho người đọc biết phạm vi sở hữu. Không nên trông chờ thao tác đóng dây chuyền làm cơ chế quản lý duy nhất.

~~~mermaid
flowchart TD
    A[DataSource] -->|getConnection| B[Connection]
    B -->|prepareStatement| C[PreparedStatement]
    C -->|executeQuery| D[ResultSet]
    D --> E[Đóng ResultSet]
    E --> F[Đóng PreparedStatement]
    F --> G[Đóng Connection / trả về pool]
~~~

Một connection có thể thực hiện nhiều statement nối tiếp trong cùng giao dịch. Sơ đồ thể hiện thứ tự giải phóng khi một truy vấn đã kết thúc.

## 2. Vì sao không thể dựa vào garbage collector?

Garbage collector xử lý bộ nhớ Java, nhưng không cho ứng dụng một thời điểm xác định để giải phóng phiên JDBC và trả kết nối cho pool. Một số driver có cơ chế dọn dẹp tài nguyên không còn tham chiếu; đó không phải hợp đồng để ứng dụng dựa vào.

Ví dụ phương thức dưới đây dễ gây rò rỉ:

~~~java
public String findNameBad(DataSource dataSource, long id)
        throws SQLException {
    Connection connection = dataSource.getConnection();
    PreparedStatement statement = connection.prepareStatement(
            "SELECT name FROM customers WHERE id = ?");
    statement.setLong(1, id);
    ResultSet result = statement.executeQuery();

    if (result.next()) {
        return result.getString("name"); // Không đóng tài nguyên.
    }
    return null;                         // Không đóng tài nguyên.
}
~~~

Ngay cả khi thêm ba lời gọi `close()` ở cuối phương thức, trường hợp `return` sớm hoặc `prepareStatement()`, `executeQuery()`, `result.next()` ném lỗi vẫn có thể bỏ qua việc dọn dẹp. Dùng `finally` thủ công có thể khắc phục, nhưng nhiều tầng tài nguyên và ngoại lệ khi đóng khiến mã dài, khó đúng.

Nếu pool có 10 kết nối và 10 yêu cầu quên trả connection, yêu cầu thứ 11 có thể phải chờ hoặc timeout dù database chưa quá tải. Quản lý tài nguyên là một phần của **độ tin cậy và hiệu năng** chứ không chỉ là vấn đề bộ nhớ.

## 3. Try-with-resources hoạt động như thế nào?

Từ Java 7, một khối `try` có thể khai báo các đối tượng triển khai `AutoCloseable`:

~~~java
try (ResourceA a = openA();
     ResourceB b = openB(a);
     ResourceC c = openC(b)) {
    use(c);
}
~~~

Java sẽ tự gọi `close()` khi rời khối, kể cả khi khối chạy đến cuối, `return` sớm hoặc ném ngoại lệ. Nếu tạo tài nguyên `c` thất bại, Java vẫn đóng `b` và `a` đã được tạo thành công.

**Tài nguyên đóng theo thứ tự ngược thứ tự khởi tạo:** `c` rồi `b` rồi `a`. Điều này rất hợp với JDBC: đóng `ResultSet` trước, tiếp đến `PreparedStatement` và sau cùng `Connection`.

Trong Java 9 trở lên, một biến đã khai báo trước có thể xuất hiện trong phần resource nếu là `final` hoặc *effectively final*:

~~~java
Connection connection = dataSource.getConnection();
try (connection) {
    // Sử dụng connection.
}
// connection đã được đóng, không tiếp tục dùng.
~~~

Tuy cú pháp trên hợp lệ, với JDBC đơn giản nên khai báo ngay trong `try` để không có đoạn mã giữa lúc lấy kết nối và lúc bắt đầu bảo vệ vòng đời:

~~~java
try (Connection connection = dataSource.getConnection()) {
    // Sử dụng connection.
}
~~~

## 4. Ví dụ hoàn chỉnh: đọc dữ liệu với ba tài nguyên

Phương thức sau nhận một `DataSource` và trả về dữ liệu Java độc lập với JDBC:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import javax.sql.DataSource;

public final class CustomerRepository {
    private final DataSource dataSource;

    public CustomerRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Optional<String> findNameById(long id) throws SQLException {
        String sql = "SELECT name FROM customers WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, id);

            try (ResultSet result = statement.executeQuery()) {
                if (result.next()) {
                    return Optional.ofNullable(result.getString("name"));
                }
                return Optional.empty();
            }
        }
    }
}
~~~

Những điều cần quan sát:

1. `Connection` được cấp bởi `DataSource` và được khai báo trong khối ngoài.
2. `PreparedStatement` được tạo từ đúng connection đó; `id` truyền qua `setLong()` thay vì ghép chuỗi vào SQL.
3. Khối trong mở `ResultSet` **sau khi** đã đặt tham số trên statement.
4. `return` bên trong khối không khiến mã bỏ qua dọn dẹp: Java đóng result set, statement và connection khi rời phạm vi.
5. Nếu gọi SQL, đọc cột hoặc đóng tài nguyên gặp lỗi, những tài nguyên đã tạo sẽ được xử lý theo quy tắc của `try-with-resources`.

Có thể viết gọn cả ba tài nguyên trong một khối khi không cần cấu hình statement trước khi chạy:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
             "SELECT id, name FROM customers");
     ResultSet result = statement.executeQuery()) {
    while (result.next()) {
        // Đọc từng hàng.
    }
}
~~~

Hai cách đều hợp lệ. Cách lồng khối dễ đọc hơn với truy vấn có tham số hoặc thao tác cấu hình statement như `setFetchSize()`.

## 5. Phạm vi sống của ResultSet và dữ liệu trả về

`ResultSet` phụ thuộc vào statement, connection và trạng thái thực thi truy vấn. Trả một `ResultSet` ra khỏi phương thức rồi đóng statement/connection là một lỗi về **quyền sở hữu**:

~~~java
public ResultSet findCustomersBad(DataSource ds) throws SQLException {
    try (Connection connection = ds.getConnection();
         PreparedStatement statement = connection.prepareStatement(
                 "SELECT id, name FROM customers")) {
        return statement.executeQuery(); // Hết phạm vi là statement đóng.
    }
}
~~~

Khi caller bắt đầu gọi `result.next()`, statement và connection có thể đã đóng. Cách an toàn hơn là **đọc và ánh xạ dữ liệu trong cùng phạm vi try**:

~~~java
public record CustomerRow(long id, String name) {}

public List<CustomerRow> listCustomers(DataSource ds) throws SQLException {
    List<CustomerRow> rows = new ArrayList<>();
    try (Connection connection = ds.getConnection();
         PreparedStatement statement = connection.prepareStatement(
                 "SELECT id, name FROM customers ORDER BY id");
         ResultSet result = statement.executeQuery()) {
        while (result.next()) {
            rows.add(new CustomerRow(
                    result.getLong("id"),
                    result.getString("name")));
        }
    }
    return rows;
}
~~~

Đoạn mã minh họa giả định có các import `java.util.List` và `java.util.ArrayList`; `record` có từ Java 16. Với bản Java cũ, dùng DTO class thông thường.

Nếu dữ liệu lớn, không nên bắt buộc gom toàn bộ hàng vào `List`. Có thể xử lý từng hàng khi `ResultSet` còn sống, dùng phân trang hoặc thiết kế một đối tượng streaming **có hợp đồng đóng tài nguyên rõ ràng**. Một `Stream` lười được trả ra mà connection đã đóng cũng gặp vấn đề tương tự `ResultSet`.

### Đọc tuần tự và fetch size

~~~java
try (Connection c = dataSource.getConnection();
     PreparedStatement ps = c.prepareStatement(
             "SELECT id, balance FROM accounts WHERE active = ?")) {
    ps.setBoolean(1, true);
    ps.setFetchSize(200);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long accountId = rs.getLong("id");
            java.math.BigDecimal balance = rs.getBigDecimal("balance");
            processAccount(accountId, balance);
        }
    }
}
~~~

`setFetchSize(200)` là một **gợi ý cho driver**, không bảo đảm chỉ dùng bộ nhớ cho đúng 200 hàng hoặc luôn kích hoạt streaming. Một số driver có yêu cầu về transaction, auto-commit hoặc cursor để fetch từng lô. Nên kiểm tra tài liệu driver và quan sát hành vi thật.

Không nên giữ cursor mở rồi gọi HTTP hoặc chạy tính toán rất lâu trong mỗi vòng lặp. Kết nối vẫn đang được giữ; trong một số cấu hình còn giữ snapshot, transaction hoặc tài nguyên server.

## 6. Ghi dữ liệu: không có ResultSet vẫn phải close

Lệnh `INSERT`, `UPDATE` và `DELETE` thường dùng `executeUpdate()`. Dù không gọi `executeQuery()`, statement và connection vẫn cần được giải phóng:

~~~java
public int changeEmail(DataSource ds, long id, String email)
        throws SQLException {
    try (Connection c = ds.getConnection();
         PreparedStatement ps = c.prepareStatement(
                 "UPDATE customers SET email = ? WHERE id = ?")) {
        ps.setString(1, email);
        ps.setLong(2, id);
        return ps.executeUpdate();
    }
}
~~~

Lưu ý số dòng bị ảnh hưởng: `0` có thể nghĩa là không tìm thấy bản ghi, `1` là cập nhật đúng một khách hàng theo khóa chính. Với ứng dụng có transaction, việc các lệnh ghi được commit cùng nhau phụ thuộc ranh giới giao dịch chứ không phụ thuộc việc statement có được đóng hay chưa.

### ResultSet của generated keys cũng phải đóng

Một lệnh `INSERT` lấy ID do database sinh có thể trả về kết quả qua `getGeneratedKeys()`:

~~~java
try (Connection c = dataSource.getConnection();
     PreparedStatement ps = c.prepareStatement(
             "INSERT INTO customers(name) VALUES (?)",
             java.sql.Statement.RETURN_GENERATED_KEYS)) {
    ps.setString(1, "An");
    if (ps.executeUpdate() != 1) {
        throw new SQLException("Không tạo được khách hàng");
    }
    try (ResultSet keys = ps.getGeneratedKeys()) {
        if (!keys.next()) {
            throw new SQLException("Database không trả khóa mới");
        }
        long newCustomerId = keys.getLong(1);
        // Sử dụng ID trước khi keys hết phạm vi.
    }
}
~~~

Khả năng cung cấp khóa sinh tự động và nội dung result set phụ thuộc driver/DB. Dù kết quả đến từ `executeQuery()` hay `getGeneratedKeys()`, nguyên tắc vòng đời vẫn như nhau.

## 7. Connection pool: close thường là trả kết nối

Với `DataSource` có connection pool, lời gọi `getConnection()` thường **mượn một connection logic**. Khi gọi `close()` trên connection được mượn, pool thường nhận lại và tái sử dụng kết nối vật lý nếu nó vẫn hợp lệ; không nhất thiết đóng TCP socket đến DB.

~~~mermaid
sequenceDiagram
    participant R as Request Java
    participant P as Connection pool
    participant D as Database
    R->>P: getConnection()
    P-->>R: Connection được mượn
    R->>D: Thực thi SQL
    D-->>R: Kết quả
    R->>P: close()
    Note over P: Trả về pool hoặc loại bỏ nếu không hợp lệ
~~~

Ba khoảng thời gian cần phân biệt:

| Khoảng thời gian | Mốc đo | Vì sao cần theo dõi |
| --- | --- | --- |
| **Query duration** | Từ lúc thực thi truy vấn đến khi hoàn thành | SQL chậm, chờ khóa, chờ I/O |
| **Connection hold time** | Từ lúc mượn connection đến lúc trả pool | Cạn pool dù SQL chạy nhanh |
| **Transaction duration** | Từ lúc bắt đầu transaction đến commit/rollback | Khóa, snapshot hoặc trạng thái giao dịch bị giữ |

Ví dụ pool có 20 kết nối. Nếu 20 request mở connection rồi mỗi request chờ API ngoài DB trong 5 giây, request thứ 21 có thể chờ pool dù database gần như rảnh. **Try-with-resources ngăn quên đóng, nhưng phải đặt phạm vi try hợp lý** để không giữ kết nối trong những công việc không cần DB.

Việc tăng kích thước pool chỉ có ích nếu có bằng chứng database có thể chịu thêm tải; nó không thay thế việc sửa rò rỉ hoặc thu hẹp phạm vi mượn kết nối.

## 8. Close không tự commit hay rollback

`Connection.close()` kết thúc việc sử dụng kết nối; nó **không đồng nghĩa** với `commit()` hoặc `rollback()`. Khi tắt auto-commit và để giao dịch còn mở lúc đóng connection, hành vi có thể phụ thuộc driver, pool và DB. Không nên dựa vào một kết quả ngầm định.

Ví dụ thiếu quyết định giao dịch:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    // UPDATE ...
    // Quên cả commit lẫn rollback.
}
~~~

Thiết kế đúng là **commit khi tất cả bước thành công**, hoặc **rollback khi xảy ra lỗi**, rồi mới kết thúc phạm vi mượn connection.

### Ví dụ JDBC: chuyển tiền trong một transaction

Đoạn mã sau tập trung vào tài nguyên và transaction, giả định hai tài khoản thuộc cùng database hỗ trợ giao dịch và `balance` dùng số thập phân chính xác:

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
            throw new IllegalArgumentException("Chuyển tiền không hợp lệ");
        }

        try (Connection c = dataSource.getConnection()) {
            c.setAutoCommit(false);
            try {
                // Đóng statement trước khi commit.
                try (PreparedStatement debit = c.prepareStatement(
                             "UPDATE accounts SET balance = balance - ? " +
                             "WHERE id = ? AND balance >= ?");
                     PreparedStatement credit = c.prepareStatement(
                             "UPDATE accounts SET balance = balance + ? " +
                             "WHERE id = ?")) {
                    debit.setBigDecimal(1, amount);
                    debit.setLong(2, fromId);
                    debit.setBigDecimal(3, amount);
                    if (debit.executeUpdate() != 1) {
                        throw new IllegalStateException("Không đủ số dư");
                    }

                    credit.setBigDecimal(1, amount);
                    credit.setLong(2, toId);
                    if (credit.executeUpdate() != 1) {
                        throw new IllegalStateException(
                                "Tài khoản đích không tồn tại");
                    }
                }
                c.commit();
            } catch (SQLException | RuntimeException failure) {
                try {
                    c.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }
}
~~~

Ở đây hai statement cùng dùng một connection và một transaction. Nếu ghi có thất bại, phần ghi nợ phải rollback. Các statement được đóng trước lúc commit; nếu việc đóng statement ném lỗi, nhánh catch cũng có cơ hội rollback.

Các giới hạn cần hiểu:

- `setAutoCommit(false)` thay đổi cách commit; với pool, cần dùng cấu hình chuẩn để connection được trả về trạng thái dùng lại đúng cách.
- Nếu mất kết nối trong lúc `commit()`, kết quả transaction **có thể không xác định**. Gọi rollback sau đó là nỗ lực xử lý trạng thái, không chứng minh giao dịch chưa commit. Nghiệp vụ quan trọng cần mã yêu cầu duy nhất và đối soát trước khi retry.
- Mã minh họa chưa có sổ cái, chống trùng lặp chuyển tiền và các quy tắc bảo mật của hệ thống tài chính thực tế.
- Đóng connection không khôi phục tác dụng đã phát sinh ở hệ thống ngoài DB như email hoặc thanh toán.

## 9. Ngoại lệ khi close và suppressed exceptions

Việc đóng statement, result set hay connection cũng có thể ném `SQLException`. Giả sử câu SQL chính thất bại, sau đó `close()` của statement cũng thất bại. Nếu viết `finally` thủ công không cẩn thận, lỗi khi đóng có thể che mất lỗi chính.

`Try-with-resources` xử lý bằng quy tắc **suppressed exception**:

1. Lỗi xảy ra trong khối try được giữ làm ngoại lệ chính.
2. Các lỗi ném ra lúc tự động đóng tài nguyên được gắn vào `getSuppressed()` của ngoại lệ chính.
3. Nếu thân try không lỗi nhưng close lỗi, lỗi đóng đầu tiên là ngoại lệ chính; các lỗi đóng sau có thể bị suppressed.

Ví dụ truy vết:

~~~java
try (Connection c = dataSource.getConnection();
     PreparedStatement ps = c.prepareStatement(
             "SELECT id FROM products");
     ResultSet rs = ps.executeQuery()) {
    while (rs.next()) {
        // Xử lý hàng.
    }
} catch (SQLException failure) {
    System.err.println("Lỗi chính: " + failure.getMessage());
    for (Throwable secondary : failure.getSuppressed()) {
        System.err.println("Lỗi phụ khi đóng: " + secondary.getMessage());
    }
    throw failure;
}
~~~

Trong ứng dụng thật nên dùng logger, request ID và thông tin truy vết phù hợp, tránh ghi dữ liệu nhạy cảm vào log. Không được bỏ qua lỗi đóng một cách vô điều kiện vì nó có thể phản ánh lỗi kết nối hoặc driver.

Nếu `prepareStatement()` thất bại trong lúc khởi tạo tài nguyên thứ hai, Java vẫn đóng connection đã tạo trước đó. Đây là lợi ích khó bảo đảm đầy đủ khi chỉ gọi close ở cuối phương thức.

Không nên dùng `return` trong `finally` vì có thể làm mất kết quả hoặc che ngoại lệ xảy ra trước đó.

## 10. Ai là chủ sở hữu tài nguyên?

Quy tắc thực tế: **thành phần tạo hoặc được giao quyền sở hữu tài nguyên có trách nhiệm đóng nó**. Với JDBC trong framework, connection có thể thuộc quyền quản lý của transaction manager chứ không thuộc một repository nhỏ.

| Cách dùng | Thành phần quản lý vòng đời | Cách xử lý |
| --- | --- | --- |
| Repository tự gọi `dataSource.getConnection()` | Repository mượn connection | Dùng `try-with-resources` cho connection, statement, result set |
| Service mở connection, truyền xuống repository | Service/caller | Repository đóng statement/result set do nó tạo, **không đóng** connection được truyền vào |
| Spring `JdbcTemplate` | Framework/transaction manager | Để framework quản lý tài nguyên JDBC theo hợp đồng |
| JPA `EntityManager` do container quản lý | Container/framework | Không tự đóng entity manager/connection của transaction đang được quản lý |
| API streaming chuyển giao quyền sở hữu | Caller nếu API quy định rõ | Caller phải đóng đối tượng `AutoCloseable` được trả về |

### Repository nhận connection từ service

~~~java
public int debit(Connection connection, long id, BigDecimal amount)
        throws SQLException {
    try (PreparedStatement ps = connection.prepareStatement(
            "UPDATE accounts SET balance = balance - ? " +
            "WHERE id = ? AND balance >= ?")) {
        ps.setBigDecimal(1, amount);
        ps.setLong(2, id);
        ps.setBigDecimal(3, amount);
        return ps.executeUpdate();
    }
    // Không đóng connection: service/caller sở hữu transaction.
}
~~~

Nếu repository đóng connection này, service không thể tiếp tục ghi phần giao dịch còn lại. Một lỗi thiết kế thường gặp là trộn lẫn hai kiểu phương thức: kiểu **tự cấp và tự đóng connection** với kiểu **nhận connection đang thuộc transaction của caller**.

### Khi ứng dụng dùng Spring

`JdbcTemplate` và các API tiện ích transaction-aware của Spring biết cách tham gia transaction theo cấu hình transaction manager. Nếu tự gọi `dataSource.getConnection()` và `close()` khi đang ở một transaction do Spring quản lý mà không sử dụng cơ chế tương thích, truy vấn có thể không tham gia transaction mong đợi hoặc làm sai vòng đời kết nối.

Với Spring, ưu tiên dùng API được framework quản lý; khi phải truy cập JDBC trực tiếp trong transaction Spring, tuân theo hợp đồng của `DataSourceUtils`/transaction manager tương ứng. Không mặc định rằng mọi `Connection` lấy được là do repository sở hữu để tự đóng.

## 11. Xử lý bất đồng bộ và ResultSet dạng streaming

Giữ một `ResultSet` sống qua nhiều thread hoặc sau khi phương thức repository trả về thường làm quyền sở hữu khó kiểm soát.

- Đừng trả `Stream<T>` lười từ một phương thức đã đóng connection.
- Đừng bắt đầu task async đọc `ResultSet` rồi rời khỏi khối try trước khi task đọc xong.
- Đừng dùng cùng connection đồng thời trên nhiều thread nếu driver/hợp đồng không bảo đảm.
- Đừng giữ cursor mở trong thời gian chờ HTTP, người dùng hoặc tác vụ tính toán quá dài.

Nếu một API thực sự cần streaming, phải có **hợp đồng đóng** rõ ràng: ai mượn connection, ai đóng khi người dùng dừng giữa chừng, cách hủy truy vấn, cách xử lý lỗi và thời gian tối đa giữ cursor. Với luồng xử lý phổ biến, phân trang theo khóa ổn định và đọc từng lô thường đơn giản hơn.

## 12. Giám sát rò rỉ và giữ kết nối lâu

Rò rỉ tài nguyên không phải lúc nào tạo ra lỗi ở chính request gây rò rỉ. Nó có thể xuất hiện dưới dạng thời gian chờ tăng dần sau nhiều giờ:

| Dấu hiệu | Khả năng liên quan | Hướng kiểm tra |
| --- | --- | --- |
| Pool luôn có nhiều connection active | Không trả connection hoặc giữ quá lâu | Theo dõi thời gian mượn, request/trace và đường cấp connection |
| `getConnection()` timeout | Cạn pool hoặc database quá tải | Đo pending/idle/active, acquisition latency |
| Nhiều phiên `idle in transaction` | Transaction mở nhưng không làm việc | Tìm code path thiếu commit/rollback hoặc giữ transaction qua tác vụ dài |
| Số cursor/statement phía database tăng | ResultSet/Statement còn mở | Kiểm tra resource scope, streaming và driver |
| Lỗi “Connection is closed” | Tài nguyên bị đóng trước lúc sử dụng | Kiểm tra quyền sở hữu và đường async |
| Query nhanh nhưng API chậm | Giữ connection cho xử lý ngoài DB hoặc chờ pool | So sánh query duration, connection hold time và request latency |

Một số connection pool có **leak detection threshold**: nó cảnh báo khi một connection bị giữ lâu hơn ngưỡng. Cảnh báo này không nhất thiết chứng minh leak, vì truy vấn hay transaction hợp lệ nhưng dài cũng có thể kích hoạt. Cần điều tra nguyên nhân và kiểm tra tài nguyên có được trả sau khi yêu cầu kết thúc hay không.

Các metric hữu ích gồm số kết nối active/idle/pending, thời gian chờ lấy connection, thời gian giữ connection, thời gian transaction, lock wait và số timeout. Nên gắn correlation ID để nối số liệu với đường xử lý cụ thể.

## 13. Kiểm thử thành công, lỗi SQL và lỗi đóng

Để xác minh vòng đời tài nguyên, kiểm thử cả trường hợp thường và ngoại lệ:

| Kịch bản | Điều cần kiểm tra |
| --- | --- |
| Có kết quả và `return` sớm | ResultSet, statement và connection đều được đóng |
| Không có hàng | Trả kết quả rỗng và tài nguyên vẫn được giải phóng |
| Lỗi lúc `prepareStatement()` | Connection đã cấp vẫn được đóng |
| Lỗi lúc `executeQuery()` hoặc `result.next()` | Mọi tài nguyên đã mở được đóng |
| Lỗi khi ánh xạ hàng sang DTO | Không bỏ qua việc đóng hoặc để cursor mồ côi |
| Lỗi xử lý đồng thời với lỗi `close()` | Ngoại lệ chính vẫn có, lỗi đóng nằm trong `getSuppressed()` |
| Transaction lỗi ở câu SQL thứ hai | Rollback và trả connection cho pool |
| Nhiều request liên tiếp vào pool | Connection active trở lại mức bình thường sau mỗi lượt |

Có thể dùng một fake `AutoCloseable` để hiểu thứ tự đóng mà không cần database:

~~~java
final class DemoResource implements AutoCloseable {
    private final String name;

    DemoResource(String name) {
        this.name = name;
        System.out.println("open " + name);
    }

    @Override
    public void close() {
        System.out.println("close " + name);
    }
}

try (DemoResource a = new DemoResource("Connection");
     DemoResource b = new DemoResource("Statement");
     DemoResource c = new DemoResource("ResultSet")) {
    System.out.println("use");
}
~~~

Kết quả:

~~~text
open Connection
open Statement
open ResultSet
use
close ResultSet
close Statement
close Connection
~~~

Ví dụ chỉ minh họa cú pháp Java. Để kiểm tra JDBC thật, nên dùng integration test trên database và pool gần môi trường triển khai; mock không chứng minh được transaction, cursor hoặc hành vi của driver.

## 14. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| `return` trước khi gọi `close()` thủ công | Rò rỉ trên đường thoát sớm | Đặt tài nguyên trong try-with-resources |
| Chỉ đóng connection ở cuối request | Giữ statement/result set quá lâu | Thu hẹp phạm vi của từng tài nguyên |
| Trả `ResultSet` ra ngoài repository đã đóng connection | Người gọi dùng tài nguyên hết hạn | Chuyển sang DTO hoặc hợp đồng streaming sở hữu rõ |
| Đóng connection được caller truyền vào | Phá transaction của caller | Chỉ đóng statement/result set do phương thức tạo |
| Dựa vào garbage collector | Cạn pool khó đoán | Đóng có chủ đích, không chờ GC |
| Coi `close()` là commit | Trạng thái transaction không rõ | Commit/rollback tường minh |
| Nuốt ngoại lệ từ close | Mất dấu vết lỗi tài nguyên | Giữ ngoại lệ chính, xem suppressed và log đúng |
| Chờ HTTP khi đang mượn connection | Chờ pool và tăng độ trễ | Rút ngắn phạm vi dùng connection |
| Cho hai thread dùng chung connection tùy tiện | Race, lỗi cursor và driver | Chia rõ connection/transaction theo tác vụ |
| Repository tự mượn connection khác trong một use case cần atomicity | Nhiều câu SQL không cùng transaction | Dùng transaction boundary do service/framework quản lý |

## 15. Bài tập: sửa phương thức bị rò rỉ

Xét mã:

~~~java
public List<String> loadNames(DataSource ds) throws SQLException {
    Connection c = ds.getConnection();
    PreparedStatement ps = c.prepareStatement(
            "SELECT name FROM customers WHERE active = ?");
    ps.setBoolean(1, true);
    ResultSet rs = ps.executeQuery();

    List<String> names = new ArrayList<>();
    while (rs.next()) {
        names.add(rs.getString("name"));
    }
    rs.close();
    ps.close();
    c.close();
    return names;
}
~~~

Hãy xác định đường rò rỉ khi `prepareStatement()`, `executeQuery()` hoặc `rs.getString()` ném lỗi. Sau đó viết lại bằng `try-with-resources`, bảo đảm kết quả cuối là `List<String>` độc lập với JDBC.

Một cách sửa:

~~~java
public List<String> loadNames(DataSource ds) throws SQLException {
    List<String> names = new ArrayList<>();
    try (Connection c = ds.getConnection();
         PreparedStatement ps = c.prepareStatement(
                 "SELECT name FROM customers WHERE active = ?")) {
        ps.setBoolean(1, true);
        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                names.add(rs.getString("name"));
            }
        }
    }
    return names;
}
~~~

Giả định các import Java/JDBC phù hợp. Phương thức sửa xong đóng tài nguyên trên cả đường thành công và lỗi, kể cả lỗi xảy ra khi tạo statement hoặc trong lúc đọc từng hàng.

## 16. Những điều cần nhớ

- **Đóng cả Connection, Statement và ResultSet** bằng `try-with-resources` khi tự quản lý JDBC; `close()` được thực hiện ngược thứ tự khởi tạo.
- **ResultSet sống trong phạm vi của statement/connection.** Trả về dữ liệu Java đã ánh xạ hoặc định nghĩa hợp đồng streaming rõ ràng.
- **Connection pool cần nhận lại connection** qua `close()` đúng lúc; thu hẹp phạm vi mượn để giảm chờ pool và tranh chấp.
- **Close không thay commit/rollback.** Khi `autoCommit=false`, transaction phải kết thúc có chủ đích.
- **Xác định chủ sở hữu tài nguyên.** Repository không tự đóng connection do service hoặc framework quản lý.
- **Ngoại lệ khi close cũng đáng quan sát.** `try-with-resources` giữ ngoại lệ chính và gắn các lỗi đóng thành suppressed exceptions.
- **Kiểm thử cả đường lỗi.** Chỉ chạy truy vấn thành công một lần chưa chứng minh vòng đời tài nguyên đúng.

Quản lý vòng đời JDBC chính xác giúp ứng dụng Java sử dụng connection pool ổn định, giải phóng cursor và statement đúng lúc, đồng thời giữ các giao dịch trong phạm vi cần thiết. Try-with-resources giải quyết phần đóng tài nguyên ở cấp ngôn ngữ; thiết kế persistence còn cần phân định quyền sở hữu, ranh giới giao dịch và chiến lược xử lý lỗi rõ ràng.
