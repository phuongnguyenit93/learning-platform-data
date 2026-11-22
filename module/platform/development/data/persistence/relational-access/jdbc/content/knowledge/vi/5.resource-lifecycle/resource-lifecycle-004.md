# Phân biệt tài nguyên do phương thức tạo và tài nguyên được truyền vào trong JDBC

Khi viết chương trình Java truy cập cơ sở dữ liệu quan hệ qua **JDBC (Java Database Connectivity)**, mỗi thao tác thường liên quan đến nhiều tài nguyên: kết nối (**Connection**), câu lệnh (**Statement** hoặc **PreparedStatement**) và tập kết quả (**ResultSet**). Những tài nguyên này có vòng đời riêng và cần được đóng đúng lúc để tránh rò rỉ kết nối, cursor, bộ nhớ và các tài nguyên ở phía cơ sở dữ liệu.

Một câu hỏi quan trọng hơn việc “có gọi close() hay không” là **ai có trách nhiệm gọi close()?** Để trả lời, cần phân biệt rõ:

- **Tài nguyên do phương thức tạo hoặc lấy ra để tự sử dụng:** Phương thức thông thường chịu trách nhiệm đóng trước khi kết thúc, trừ khi cố ý chuyển quyền sở hữu cho bên gọi.
- **Tài nguyên được truyền vào từ bên ngoài:** Phương thức thông thường chỉ **mượn** để làm việc rồi trả quyền sử dụng lại cho bên gọi; nó không tự đóng tài nguyên đó.

Đây là **quy ước thiết kế về quyền sở hữu tài nguyên (resource ownership)**, không phải quy tắc JVM có thể tự suy ra từ chữ ký Java. Nếu một API có hợp đồng sở hữu khác, cần tuân thủ hợp đồng được công bố.

## 1. Vì sao nguồn gốc tài nguyên quyết định cách đóng?

Xét hai phương thức cùng thực hiện truy vấn:

~~~java
// A: Tự xin kết nối từ DataSource.
public String findName(DataSource dataSource, long id) throws SQLException {
    try (Connection connection = dataSource.getConnection()) {
        // Truy vấn với connection; phương thức sở hữu lượt sử dụng này.
        return queryName(connection, id);
    }
}

// B: Nhận một kết nối mà bên gọi đang quản lý.
public String queryName(Connection connection, long id) throws SQLException {
    // Phương thức này chỉ mượn connection.
    // Các PreparedStatement và ResultSet do nó tạo vẫn phải được đóng.
    // Phần triển khai cụ thể được minh họa ở mục 4.
    return "...";
}
~~~

Ở ví dụ A, phương thức đã **lấy** Connection từ DataSource nên phải đóng lượt sử dụng kết nối khi xong. Ở ví dụ B, Connection do bên gọi **truyền vào**; phương thức có thể đang tham gia vào một transaction gồm nhiều thao tác. Nếu B tự đóng Connection, các thao tác tiếp theo của bên gọi có thể thất bại, hoặc transaction bị kết thúc không đúng chỗ.

Điểm mấu chốt là **ranh giới sở hữu**, không đơn thuần là tên phương thức hay việc gọi getConnection() trong nội bộ thư viện. Với connection pool, gọi **Connection.close()** trên kết nối lấy từ pool thường **trả kết nối về pool**, thay vì đóng vĩnh viễn kết nối vật lý. Tuy nhiên, bên đã lấy kết nối vẫn cần gọi close() để giải phóng lượt mượn.

## 2. Bảng xác định ai đóng tài nguyên

| Tài nguyên | Xuất hiện từ đâu? | Ai thường có trách nhiệm đóng? | Lưu ý |
| --- | --- | --- | --- |
| **DataSource** | Được truyền qua constructor hoặc tham số | Bộ phận cấu hình/vòng đời ứng dụng | DataSource dùng chung không nên bị repository tự ý dừng; một số pool có API shutdown riêng. |
| **Connection** | Phương thức gọi DataSource.getConnection() | Phương thức lấy kết nối | Đóng khi hoàn thành công việc, kể cả khi lỗi. |
| **Connection** | Được truyền vào qua tham số | Bên gọi đã truyền kết nối | Phương thức nhận chỉ sử dụng, không tự đóng nếu không có thỏa thuận chuyển quyền. |
| **PreparedStatement** | Phương thức gọi connection.prepareStatement(sql) | Phương thức tạo statement | Thường dùng try-with-resources. |
| **Statement** | Phương thức gọi connection.createStatement() | Phương thức tạo statement | Đóng sau khi hoàn thành. |
| **ResultSet** | Phương thức gọi statement.executeQuery() | Phương thức nhận và xử lý ResultSet | Đóng trước hoặc cùng lúc đóng statement; không giữ ResultSet sau khi statement đóng. |
| **ResultSet** | Phương thức gọi statement.getGeneratedKeys() | Phương thức yêu cầu khóa được tạo | Cũng là tài nguyên cần được giải phóng. |
| **PreparedStatement trả về cho bên gọi** | Phương thức tạo nhưng **trả object còn mở** | Bên nhận, nếu hợp đồng xác định chuyển quyền sở hữu | Bên nhận phải đóng; kết nối nền phải còn sống khi dùng. |

**Nguồn gốc và quyền sở hữu có thể khác nhau** nếu API cố ý chuyển quyền. Ví dụ, phương thức tạo PreparedStatement rồi trả về cho bên gọi để sử dụng thì không thể đóng statement ngay trong phương thức tạo. Khi đó, tài liệu API phải ghi rõ: **bên gọi chịu trách nhiệm đóng statement**.

## 3. Tài nguyên được tạo trong phương thức: sử dụng và đóng tại chỗ

Ví dụ dưới đây minh họa repository nhận DataSource do ứng dụng cấu hình. Mỗi lần gọi, phương thức tự lấy Connection, tạo PreparedStatement, nhận ResultSet rồi đóng cả ba theo đúng thứ tự.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import javax.sql.DataSource;

public final class CustomerLookup {
    private final DataSource dataSource;

    public CustomerLookup(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Optional<String> findEmail(long customerId) throws SQLException {
        String sql = "SELECT email FROM customers WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {

            statement.setLong(1, customerId);

            try (ResultSet resultSet = statement.executeQuery()) {
                if (!resultSet.next()) {
                    return Optional.empty();
                }
                return Optional.ofNullable(resultSet.getString("email"));
            }
        }
    }
}
~~~

Trong ví dụ:

1. **DataSource** là thành phần dùng chung, được cung cấp từ bên ngoài: repository không đóng nó.
2. **Connection** do phương thức findEmail() lấy ra: phương thức có trách nhiệm đóng.
3. **PreparedStatement** do phương thức tạo: phương thức có trách nhiệm đóng.
4. **ResultSet** do executeQuery() trả về: được đọc và đóng ngay trong phạm vi sử dụng.
5. **Optional<String>** là dữ liệu Java thông thường: có thể trả về an toàn sau khi tài nguyên JDBC đã đóng.

Từ khóa **try-with-resources** giúp tự động gọi close() cả khi có return trong khối try hoặc khi xảy ra lỗi. Tài nguyên được đóng theo **thứ tự ngược với thứ tự khai báo**, nên statement được đóng trước connection; ResultSet trong khối try lồng nhau được đóng trước cả hai.

Nếu không có try-with-resources, lập trình viên phải tự viết finally và xử lý ngoại lệ của close(), dễ gây thiếu sót hơn.

## 4. Tài nguyên được truyền vào: chỉ mượn để sử dụng

Một repository đôi khi cần tham gia transaction do tầng service quản lý. Khi đó, tầng service truyền Connection vào phương thức repository.

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public final class ProductRepository {
    // Connection do tầng gọi sở hữu; không đóng tại đây.
    public int updatePrice(
            Connection connection, long productId, BigDecimal newPrice)
            throws SQLException {

        String sql = "UPDATE products SET price = ? WHERE id = ?";

        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setBigDecimal(1, newPrice);
            statement.setLong(2, productId);
            return statement.executeUpdate();
        }
    }
}
~~~

Phương thức **updatePrice()** đóng PreparedStatement vì nó tự tạo statement. Phương thức không đóng Connection vì connection được nhận từ tham số.

Bên gọi quyết định kết nối được sử dụng trong bao lâu:

~~~java
ProductRepository repository = new ProductRepository();

try (Connection connection = dataSource.getConnection()) {
    int count = repository.updatePrice(
            connection, 101L, new BigDecimal("125000.00"));
    System.out.println("Số hàng được cập nhật: " + count);
}
// Connection do bên gọi lấy nên được đóng tại đây.
~~~

Điều gì xảy ra nếu repository tự gọi connection.close() ở cuối updatePrice()? Bên gọi có thể tiếp tục định chạy câu lệnh khác trên chính connection đó nhưng gặp **SQLException** vì connection đã bị đóng, hoặc kết nối đã bị trả về pool. Trong một transaction nhiều bước, hành vi này còn có thể phá vỡ ranh giới commit/rollback đã được thiết kế.

Ngược lại, việc “truyền vào” không có nghĩa phương thức được phép bỏ qua **mọi** thao tác đóng. Nó vẫn sở hữu PreparedStatement và ResultSet **do chính nó tạo ra** trong phạm vi gọi.

## 5. Ví dụ transaction: quyền quản lý Connection thuộc tầng service

Giả sử việc chuyển điểm giữa hai tài khoản yêu cầu hai thao tác cập nhật cùng thành công hoặc cùng rollback. Tầng service lấy Connection và điều phối transaction; các phương thức repository chỉ nhận Connection để thực hiện SQL.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class PointTransferService {
    private final DataSource dataSource;

    public PointTransferService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void transfer(long fromId, long toId, int points)
            throws SQLException {
        if (fromId == toId || points <= 0) {
            throw new IllegalArgumentException("Yêu cầu chuyển điểm không hợp lệ");
        }

        try (Connection connection = dataSource.getConnection()) {
            boolean oldAutoCommit = connection.getAutoCommit();
            try {
                connection.setAutoCommit(false);
                int debitCount = debit(connection, fromId, points);
                int creditCount = credit(connection, toId, points);
                if (debitCount != 1 || creditCount != 1) {
                    throw new SQLException("Thiếu tài khoản hoặc số điểm không đủ");
                }
                connection.commit();
            } catch (SQLException | RuntimeException error) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            } finally {
                // Pool/ứng dụng nên bảo đảm trạng thái connection được khôi phục.
                connection.setAutoCommit(oldAutoCommit);
            }
        }
    }

    private static int debit(Connection connection, long id, int points)
            throws SQLException {
        String sql = "UPDATE point_accounts SET points = points - ? " +
                     "WHERE id = ? AND points >= ?";
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setInt(1, points);
            statement.setLong(2, id);
            statement.setInt(3, points);
            return statement.executeUpdate();
        }
    }

    private static int credit(Connection connection, long id, int points)
            throws SQLException {
        String sql = "UPDATE point_accounts SET points = points + ? WHERE id = ?";
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setInt(1, points);
            statement.setLong(2, id);
            return statement.executeUpdate();
        }
    }
}
~~~

Ở đây, **transfer()** tạo/lấy Connection nên là nơi đặt transaction và đóng kết nối. **debit()** và **credit()** mượn Connection; mỗi phương thức chỉ đóng PreparedStatement do mình tạo. Nếu debit() tự đóng Connection thì credit() không thể sử dụng kết nối đó để hoàn thành transaction.

Đây là ví dụ về ranh giới tài nguyên, không thay thế một thiết kế nghiệp vụ chuyển điểm hoàn chỉnh (ví dụ, kiểm soát tranh chấp đồng thời, ghi lịch sử, quy tắc khóa). Việc rollback phụ thuộc khả năng transaction của hệ quản trị cơ sở dữ liệu và bảng dữ liệu. Trong ứng dụng thực tế, cần xử lý cả lỗi khi **khôi phục autoCommit** để không làm mất thông tin về lỗi ban đầu; thư viện giao dịch hoặc connection pool có thể cung cấp cơ chế quản lý trạng thái kết nối phù hợp.

## 6. Không trả về ResultSet nếu statement hoặc connection sắp đóng

Một lỗi vòng đời thường thấy là trả thẳng ResultSet từ phương thức tự tạo và đóng statement:

~~~java
// SAI: ResultSet phụ thuộc vào statement, nhưng statement đã đóng
// trước khi bên gọi sử dụng kết quả.
public ResultSet findCustomers(Connection connection) throws SQLException {
    try (PreparedStatement statement = connection.prepareStatement(
            "SELECT id, name FROM customers")) {
        return statement.executeQuery();
    }
}
~~~

Khi PreparedStatement bị đóng ở cuối khối try, ResultSet gắn với nó cũng không còn dùng được. Bên gọi có thể gặp SQLException nếu cố đọc next() hoặc getString().

Giải pháp thường dễ quản lý nhất là **chuyển dữ liệu từ ResultSet sang kiểu Java rồi mới trả về**:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

public List<String> findCustomerNames(Connection connection)
        throws SQLException {
    String sql = "SELECT name FROM customers";
    List<String> names = new ArrayList<>();

    try (PreparedStatement statement = connection.prepareStatement(sql);
         ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            names.add(resultSet.getString("name"));
        }
    }
    return names; // List không phụ thuộc tài nguyên JDBC đã đóng.
}
~~~

Với kết quả quá lớn để đưa hết vào List, có thể xử lý theo **callback trong khi ResultSet còn mở**, sử dụng phân trang hoặc thiết kế API stream có hợp đồng đóng tài nguyên rõ ràng. Không nên trả một luồng đọc dữ liệu phụ thuộc ResultSet mà không xác định ai đóng ResultSet, Statement và Connection.

## 7. Trường hợp ngoại lệ: phương thức tạo rồi chuyển quyền sở hữu

Nguồn gốc tài nguyên không phải lúc nào cũng quyết định người đóng cuối cùng. Một phương thức có thể **tạo PreparedStatement và trả nó cho bên gọi**:

~~~java
// Hợp đồng: caller sở hữu và phải đóng PreparedStatement trả về.
public PreparedStatement prepareFindById(Connection connection)
        throws SQLException {
    return connection.prepareStatement(
            "SELECT id, email FROM customers WHERE id = ?");
}
~~~

Bên gọi chịu trách nhiệm đóng statement:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = prepareFindById(connection)) {

    statement.setLong(1, customerId);
    try (ResultSet resultSet = statement.executeQuery()) {
        if (resultSet.next()) {
            System.out.println(resultSet.getString("email"));
        }
    }
}
~~~

Đây là **chuyển quyền sở hữu statement**: phương thức tạo không đóng statement vì bên gọi cần dùng nó sau khi phương thức trả về. Connection vẫn do bên gọi đang sở hữu, và phải còn mở trong toàn bộ thời gian sử dụng statement. Hợp đồng có thể viết trong Javadoc: “Caller must close the returned PreparedStatement.”

Một nguyên tắc tương tự áp dụng cho các API trả về **InputStream**, **Reader**, stream dữ liệu hoặc wrapper giữ tài nguyên JDBC. Nếu một phương thức truyền quyền sở hữu ra ngoài thì bên gọi cần biết và quản lý vòng đời của tất cả tài nguyên phụ thuộc.

## 8. Những trường hợp dễ nhầm trong JDBC

### Lấy tham chiếu khác không làm phát sinh quyền sở hữu mới

Nếu có một ResultSet, lệnh **resultSet.getStatement()** chỉ lấy tham chiếu đến Statement đã tạo kết quả. Tương tự, **statement.getConnection()** trả về Connection đã liên kết với statement. Các phương thức này không đồng nghĩa phương thức nhận tham chiếu vừa “tạo ra” Statement hoặc Connection mới.

Vì vậy, không gọi close() trên một Connection nhận từ statement.getConnection() chỉ vì đang ở trong phương thức xử lý ResultSet. Người sở hữu Connection ban đầu vẫn quản lý nó.

### Đóng tài nguyên phụ thuộc đúng phạm vi

JDBC quy định đóng Statement cũng đóng ResultSet hiện hành mà nó tạo ra. Dù vậy, vẫn nên **đóng ResultSet rõ ràng** bằng try-with-resources và đóng nó trước Statement, để vòng đời dễ hiểu và dễ duy trì.

Nếu tái sử dụng cùng Statement cho truy vấn tiếp theo, ResultSet trước đó thường không còn hợp lệ theo quy tắc đóng kết quả hiện hành; hãy đọc/đóng kết quả trước khi thực thi câu khác trên cùng Statement.

### Không đưa Connection được mượn vào try-with-resources

Đoạn sau **đóng cả Connection**, dù Connection là tham số do bên gọi sở hữu:

~~~java
public void updateSomething(Connection connection) throws SQLException {
    try (connection) {  // Java 9+: sẽ gọi connection.close()!
        // ...
    }
}
~~~

Đoạn mã tương tự trong Java 8 dùng try-with-resources với biến bí danh cũng có thể vô tình đóng Connection được mượn. Cách đúng là chỉ đưa **Statement/ResultSet do phương thức tạo** vào try-with-resources khi phương thức không sở hữu Connection.

### Connection pool không thay đổi trách nhiệm giải phóng

Khi dùng pool, DataSource thường tồn tại lâu dài, còn mỗi lời gọi getConnection() cấp một lượt sử dụng Connection. Phương thức lấy Connection cần close() để trả nó về pool. Không close() có thể làm **cạn pool**, khiến yêu cầu khác phải chờ hoặc timeout, dù kết nối vật lý vẫn hoạt động.

### Kiểm tra ai quản lý transaction trước khi đóng Connection

Connection đang nằm trong transaction do tầng ngoài quản lý thì repository bên trong không được tự commit(), rollback() hoặc close() nếu không được trao quyền. Hành động này có thể gây commit sớm, rollback ngoài dự kiến hoặc làm hỏng chuỗi thao tác nghiệp vụ.

### Truyền stream vào JDBC cũng cần hợp đồng rõ ràng

Ví dụ một phương thức nhận InputStream từ bên gọi và chuyển nó vào setBinaryStream(...). JDBC driver có thể đọc stream trong quá trình thực thi. Không nên tự đóng stream do bên gọi truyền vào trừ khi API nêu rõ. Nếu phương thức tự mở FileInputStream, nó thường tự đóng sau khi statement đã hoàn tất việc tiêu thụ dữ liệu, với lưu ý về đặc tính của driver.

## 9. Cách thiết kế API dễ kiểm soát vòng đời

Một API JDBC dễ dùng nên thể hiện rõ ranh giới sở hữu. Có thể lựa chọn một trong ba kiểu:

| Kiểu API | Minh họa | Quyền sở hữu |
| --- | --- | --- |
| Repository tự lấy kết nối | findById(long id) | Repository quản lý Connection, Statement và ResultSet. |
| Repository mượn kết nối | findById(Connection connection, long id) | Bên gọi quản lý Connection; repository quản lý Statement và ResultSet. |
| API tạo và trả tài nguyên | prepareFindById(Connection connection) | Bên nhận đóng Statement trả về; bên sở hữu Connection đóng Connection. |

Khi thiết kế:

1. **Quy định người sở hữu ngay từ chữ ký hoặc tài liệu API.** Đặt tên và Javadoc rõ ràng nếu phương thức trả về một tài nguyên còn mở.
2. **Giữ thời gian sống càng ngắn càng tốt.** Đọc hết ResultSet trong phạm vi xử lý và đóng sớm.
3. **Dùng try-with-resources cho tài nguyên mình sở hữu.** Đóng được cả trên đường đi thành công và khi có ngoại lệ.
4. **Không tự đóng đối tượng được truyền vào** khi không có hợp đồng chuyển quyền.
5. **Quản lý transaction ở tầng sở hữu Connection.** Một transaction nhiều bước cần cùng Connection cho đến commit/rollback.
6. **Trả dữ liệu tách khỏi tài nguyên khi phù hợp.** DTO, List hoặc Optional thường thuận tiện hơn trả ResultSet đang mở.

### Quy tắc ghi nhớ: ai mở, ai đóng?

“**Ai mở thì người đó đóng**” là quy tắc khởi đầu hữu ích, nhưng cần hiểu chính xác: **ai nhận trách nhiệm sở hữu tài nguyên thì người đó phải đóng**, kể cả khi một phương thức khác đã tạo ra tài nguyên rồi cố ý chuyển quyền cho bên gọi.

~~~mermaid
flowchart TD
    A[Phương thức cần dùng tài nguyên JDBC] --> B{Tài nguyên thuộc ai?}
    B -->|Tự tạo hoặc lấy để dùng| C[Tự quản lý vòng đời]
    C --> D{Có chuyển quyền sở hữu cho caller?}
    D -->|Không| E[Đóng bằng try-with-resources]
    D -->|Có| F[Ghi rõ hợp đồng và trả tài nguyên còn mở]
    B -->|Caller truyền vào để mượn| G[Dùng trong phạm vi cho phép]
    G --> H[Không đóng hoặc kết thúc transaction của caller]
    H --> I[Đóng tài nguyên con do mình tạo]
~~~

## 10. Câu hỏi tự kiểm tra

1. Một repository nhận DataSource qua constructor và gọi getConnection() trong mỗi truy vấn. Ai đóng DataSource, Connection, PreparedStatement và ResultSet?
2. Phương thức nhận Connection để thực hiện một bước trong transaction có được đặt Connection vào try-with-resources không? Vì sao?
3. Tại sao trả ResultSet từ khối try-with-resources đang quản lý PreparedStatement thường là lỗi?
4. Nếu một helper trả PreparedStatement còn mở, ai có trách nhiệm đóng và cần ghi gì trong tài liệu API?
5. Trong ứng dụng dùng connection pool, không gọi Connection.close() có thể gây hậu quả gì?
6. Việc gọi Statement.getConnection() có chuyển quyền đóng Connection sang phương thức vừa nhận tham chiếu không?

**Ghi nhớ:** Trong JDBC, hãy xác định **quyền sở hữu của từng tài nguyên** trước khi quyết định nơi gọi close(). Phương thức thường đóng Connection, Statement và ResultSet mà chính nó lấy hoặc tạo để sử dụng; với Connection do bên ngoài truyền vào, phương thức chỉ mượn và tự đóng những Statement/ResultSet nó tạo. Khi cố ý chuyển quyền sở hữu cho bên gọi, phải mô tả rõ hợp đồng và giữ các tài nguyên phụ thuộc còn sống đủ lâu.
