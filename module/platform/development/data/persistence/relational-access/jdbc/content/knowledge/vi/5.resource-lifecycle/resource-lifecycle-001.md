# Chuỗi phụ thuộc giữa kết nối, câu lệnh và tập kết quả

Trong **JDBC (Java Database Connectivity)**, ba đối tượng thường xuất hiện cùng nhau là **`Connection`**, **`Statement`** (hoặc `PreparedStatement`) và **`ResultSet`**. Chúng có quan hệ phụ thuộc về vòng đời: câu lệnh được tạo từ kết nối; tập kết quả được tạo từ việc thực thi câu lệnh. Hiểu quan hệ này giúp đọc dữ liệu đúng cách, tránh rò rỉ tài nguyên và xử lý lỗi nhất quán.

Sau bài này, bạn có thể xác định tài nguyên nào tạo ra tài nguyên nào, lúc nào kết quả còn hợp lệ, thứ tự đóng an toàn và cách dùng `try-with-resources` để bảo đảm tài nguyên luôn được giải phóng.

## 1. Mô hình phụ thuộc ba tầng

~~~text
DataSource / DriverManager
          |
          v
      Connection                   ← phiên làm việc JDBC, ngữ cảnh giao dịch
          |
          +----> Statement         ← đối tượng thực thi SQL
          |          |
          |          +----> ResultSet (nếu truy vấn trả về hàng)
          |
          +----> PreparedStatement ← câu lệnh SQL có tham số
                     |
                     +----> ResultSet (nếu truy vấn trả về hàng)
~~~

- **`Connection`** đại diện cho kết nối logic đến cơ sở dữ liệu. Nó cung cấp phương thức tạo câu lệnh, quản lý `autoCommit`, `commit()`, `rollback()` và các tùy chọn của phiên/giao dịch. Đối tượng `Connection` có thể đến từ `DriverManager` hoặc `DataSource`.
- **`Statement`** được tạo bởi `Connection.createStatement()`; **`PreparedStatement`** được tạo bởi `Connection.prepareStatement(sql)`. Chúng giữ ngữ cảnh thực thi SQL, tham số (với `PreparedStatement`) và có thể giữ tài nguyên phía driver/cơ sở dữ liệu.
- **`ResultSet`** là con trỏ đọc kết quả được trả về từ `executeQuery()` (hoặc các API kết quả khác như `getGeneratedKeys()`). Nó gắn với câu lệnh đã sinh ra nó và thường chỉ được duyệt khi các tài nguyên cha còn mở.

Quan hệ này có **hai chiều cần phân biệt**: đối tượng con cần đối tượng cha để hoạt động; nhưng đóng một đối tượng con **không đồng nghĩa** với đóng đối tượng cha. Ví dụ, `resultSet.close()` không tự đóng `statement` hay `connection`.

| Tài nguyên | Được tạo từ | Vai trò | Phạm vi sử dụng hợp lý |
| --- | --- | --- | --- |
| `Connection` | `DataSource.getConnection()` hoặc `DriverManager.getConnection()` | Gắn các câu lệnh với phiên/giao dịch | Một thao tác nghiệp vụ hoặc một giao dịch |
| `Statement` / `PreparedStatement` | `Connection` | Chuẩn bị và thực thi SQL | Trong thao tác cần thực thi câu lệnh đó |
| `ResultSet` | `Statement` / `PreparedStatement` | Duyệt từng hàng kết quả | Trong lúc câu lệnh và kết nối còn hợp lệ |

Đây là **vòng đời tài nguyên**, không phải cây đối tượng mà bạn có thể tùy ý tách ra rồi tiếp tục sử dụng. `ResultSet` không phải một `List` chứa sẵn mọi hàng; tùy driver và chế độ đọc, nó có thể phụ thuộc vào cursor, bộ đệm, phiên và tài nguyên mạng.

## 2. Thứ tự mở, sử dụng và đóng

Trình tự thông dụng của một truy vấn là:

1. Lấy `Connection`.
2. Tạo `PreparedStatement` từ `Connection`.
3. Gán tham số SQL và gọi `executeQuery()` để nhận `ResultSet`.
4. Gọi `resultSet.next()`, đọc các cột và chuyển dữ liệu sang đối tượng Java.
5. Đóng `ResultSet`, rồi `PreparedStatement`, cuối cùng là `Connection`.

~~~text
Thời gian ──────────────────────────────────────────────────────────────>

Connection     [============================== đóng ]
Statement          [==================== đóng ]
ResultSet                   [========== đóng ]

Tạo:       Connection → Statement → ResultSet
Giải phóng: ResultSet → Statement → Connection
~~~

**Quy tắc thực hành:** tài nguyên được mở sau thì nên được đóng trước. Đây là mô hình *last in, first out* (LIFO). `try-with-resources` của Java thực hiện việc đóng tự động theo thứ tự ngược với khai báo, kể cả khi khối lệnh phát sinh ngoại lệ.

### Nếu đóng một đối tượng trước đối tượng khác thì sao?

| Hành động | Ảnh hưởng chính | Điều không nên giả định |
| --- | --- | --- |
| `resultSet.close()` | Giải phóng tập kết quả/cursor liên quan | Không đóng câu lệnh hay kết nối |
| `statement.close()` | Giải phóng câu lệnh; đóng các `ResultSet` còn mở do nó tạo ra | Không đóng `Connection` |
| `connection.close()` | Giải phóng kết nối logic và làm các tài nguyên con không còn dùng được | Không coi đây là thao tác `commit()` hoặc `rollback()` thay thế |

Đặc biệt, **thực thi lại một `Statement` thường đóng `ResultSet` hiện tại của chính câu lệnh đó** theo quy tắc JDBC; khi xử lý chuỗi nhiều kết quả, việc chuyển sang kết quả tiếp theo cũng có quy tắc đóng liên quan. Vì vậy, không giữ một `ResultSet` để đọc tiếp rồi gọi `executeQuery()` khác trên *cùng* `Statement`. Hãy đọc xong kết quả cũ, hoặc tạo câu lệnh khác khi thực sự cần.

## 3. Ví dụ đầy đủ với `try-with-resources`

Giả sử có bảng minh họa `orders(id, customer_id, status)`. Phương thức sau trả về danh sách chuỗi Java, không trả về cursor JDBC:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

public final class OrderQueries {

    public static List<String> findOrders(
            DataSource dataSource, long customerId) throws SQLException {

        String sql = """
                SELECT id, status
                FROM orders
                WHERE customer_id = ?
                ORDER BY id
                """;

        List<String> orders = new ArrayList<>();

        // Mở Connection trước, PreparedStatement sau.
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(sql)) {

            statement.setLong(1, customerId);

            // executeQuery() chạy sau khi đã gán tham số.
            try (ResultSet rows = statement.executeQuery()) {
                while (rows.next()) {
                    long id = rows.getLong("id");
                    String status = rows.getString("status");
                    orders.add(id + ": " + status);
                }
            } // Đóng ResultSet.
        }     // Đóng PreparedStatement, rồi Connection.

        return orders; // Chỉ còn dữ liệu Java, không phụ thuộc JDBC.
    }
}
~~~

*Ví dụ sử dụng text block SQL (Java 15 trở lên). Với Java cũ hơn, thay text block bằng chuỗi SQL nối thông thường.*

Có bốn điểm quyết định tính đúng đắn:

- `statement` nằm trong phạm vi mà `connection` còn mở; `rows` nằm trong phạm vi mà cả hai tài nguyên cha còn mở.
- Tham số `?` được gán bằng `setLong(1, customerId)` trước `executeQuery()`; đây cũng là cách tránh ghép trực tiếp dữ liệu người dùng vào SQL.
- Dữ liệu được sao chép sang `List<String>` **trong lúc** `ResultSet` còn mở. Sau khi thoát khối `try`, dữ liệu trong `List` vẫn dùng được.
- Nếu `next()`, `getString()` hoặc bất kỳ dòng nào bên trong ném ngoại lệ, Java vẫn thử đóng các tài nguyên đã mở.

Bạn có thể khai báo các tài nguyên ở các khối `try` lồng nhau như trên vì `executeQuery()` phải chạy sau khi gán tham số. Nếu không có tham số cần gán, nhiều trường hợp có thể khai báo `ResultSet` cùng danh sách tài nguyên trong một khối `try`; thứ tự đóng vẫn đảo ngược thứ tự khai báo.

## 4. Vì sao không được trả `ResultSet` ra khỏi phạm vi kết nối?

Xét đoạn code **sai về vòng đời**:

~~~java
public static ResultSet findIdsWrong(DataSource dataSource)
        throws SQLException {
    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement =
                 connection.prepareStatement("SELECT id FROM orders")) {

        return statement.executeQuery(); // Trả về ResultSet...
    } // ...nhưng Statement và Connection đã bị đóng tại đây.
}
~~~

Giá trị trả về trông giống một `ResultSet` bình thường, nhưng khi caller gọi `next()`, tài nguyên cha đã bị đóng; thao tác đọc có thể thất bại với `SQLException` (chẳng hạn “ResultSet closed”). Việc bỏ `try-with-resources` để giữ `ResultSet` sống lâu hơn lại chuyển gánh nặng đóng đủ cả ba tài nguyên sang caller, rất dễ gây rò rỉ.

**Cách sửa thông dụng:** ánh xạ dữ liệu sang DTO, `List` hoặc giá trị Java ngay trong phạm vi `try`. Nếu thiết kế API đọc luồng cho dữ liệu lớn, phải quy định rõ ai sở hữu `Connection`/`Statement`/`ResultSet`, thời điểm đóng và xử lý khi người dùng dừng đọc sớm. Không trả một `Stream` phụ thuộc cursor từ phương thức đã đóng kết nối.

## 5. Một kết nối có thể tạo nhiều câu lệnh

Một `Connection` có thể tạo nhiều `Statement`/`PreparedStatement` để phục vụ một thao tác hoặc giao dịch. Chúng cùng dùng ngữ cảnh của kết nối đó, nhưng mỗi câu lệnh cần được đóng riêng.

~~~java
try (Connection connection = dataSource.getConnection()) {
    try (PreparedStatement check = connection.prepareStatement(
            "SELECT status FROM orders WHERE id = ?")) {
        check.setLong(1, orderId);

        try (ResultSet rows = check.executeQuery()) {
            if (rows.next()) {
                System.out.println(rows.getString("status"));
            }
        }
    }

    try (PreparedStatement update = connection.prepareStatement(
            "UPDATE orders SET status = ? WHERE id = ?")) {
        update.setString(1, "PROCESSED");
        update.setLong(2, orderId);
        update.executeUpdate();
    }
} // Hai Statement được đóng trước khi đóng Connection.
~~~

Đoạn mã giả định `dataSource` và `orderId` đã được khai báo ở phạm vi bên ngoài. `executeUpdate()` trả về số hàng bị tác động, **không sinh `ResultSet` để duyệt** như `executeQuery()`. Tuy nhiên, nếu câu lệnh yêu cầu đọc khóa vừa tạo, `statement.getGeneratedKeys()` có thể trả về một `ResultSet` khác, và bạn cũng phải quản lý vòng đời của nó:

~~~java
try (PreparedStatement insert = connection.prepareStatement(
        "INSERT INTO orders(customer_id, status) VALUES (?, ?)",
        java.sql.Statement.RETURN_GENERATED_KEYS)) {

    insert.setLong(1, customerId);
    insert.setString(2, "NEW");
    insert.executeUpdate();

    try (ResultSet keys = insert.getGeneratedKeys()) {
        if (keys.next()) {
            long newId = keys.getLong(1);
            System.out.println("ID: " + newId);
        }
    }
}
~~~

Ở ví dụ này `connection` và `customerId` phải được tạo từ trước; cú pháp sinh khóa và mức hỗ trợ của driver/cơ sở dữ liệu có thể khác nhau. Điểm cốt lõi: **dù `ResultSet` đến từ `executeQuery()` hay `getGeneratedKeys()`, nó vẫn gắn với câu lệnh tạo ra nó**.

## 6. Phụ thuộc tài nguyên trong một giao dịch

`Connection` không chỉ là “ống dẫn SQL”; nó còn giữ trạng thái giao dịch. Nếu đặt `autoCommit=false`, các câu lệnh trên cùng kết nối tham gia cùng giao dịch cho đến khi `commit()` hoặc `rollback()`.

Ví dụ minh họa việc kiểm tra và cập nhật trạng thái đơn hàng trên **một kết nối**:

~~~java
public static void approveOrder(DataSource dataSource, long orderId)
        throws SQLException {

    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);

        try {
            try (PreparedStatement check = connection.prepareStatement(
                    "SELECT status FROM orders WHERE id = ?")) {
                check.setLong(1, orderId);

                try (ResultSet rows = check.executeQuery()) {
                    if (!rows.next()) {
                        throw new SQLException("Order not found: " + orderId);
                    }
                    if (!"PENDING".equals(rows.getString("status"))) {
                        throw new SQLException("Order is not pending");
                    }
                }
            }

            try (PreparedStatement update = connection.prepareStatement(
                    "UPDATE orders SET status = 'APPROVED' " +
                    "WHERE id = ? AND status = 'PENDING'")) {
                update.setLong(1, orderId);
                if (update.executeUpdate() != 1) {
                    throw new SQLException("Order changed concurrently");
                }
            }

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
~~~

Ở đây, `check`, `rows` và `update` đều được đóng trước khi `Connection` kết thúc. Việc kiểm tra số hàng cập nhật làm rõ rằng thao tác có thể thất bại nếu trạng thái đã thay đổi giữa lần đọc và lần ghi; khi cần ngăn chặn truy cập đồng thời nghiêm ngặt, phải chọn chiến lược khóa/mức cô lập phù hợp với cơ sở dữ liệu.

**Không dựa vào `connection.close()` để thay cho `commit()` hoặc `rollback()`.** JDBC không bảo đảm hành vi nhất quán khi đóng kết nối còn giao dịch chưa kết thúc; hãy kết thúc giao dịch tường minh. Trong ứng dụng có connection pool hoặc framework quản lý giao dịch, tuân thủ quy ước khôi phục `autoCommit`, isolation và các thuộc tính phiên trước khi kết nối được tái sử dụng; nếu dùng Spring transaction chẳng hạn, để bộ quản lý giao dịch sở hữu thao tác `commit`/`rollback`.

## 7. Điều gì xảy ra khi có lỗi?

Với `try-with-resources`, Java chỉ đóng những tài nguyên **đã khởi tạo thành công** và thực hiện theo thứ tự ngược:

- `dataSource.getConnection()` thất bại: chưa có `Connection` để đóng.
- `prepareStatement()` thất bại: `Connection` đã mở sẽ được đóng.
- `executeQuery()` hoặc `rows.next()` thất bại: các tài nguyên đã mở được đóng theo phạm vi tương ứng.
- Lỗi xảy ra **cả trong xử lý chính và khi đóng**: lỗi chính được ném ra; lỗi khi đóng thường được ghi trong `Throwable.getSuppressed()` để không làm mất nguyên nhân ban đầu.

Ví dụ chẩn đoán lỗi bổ sung:

~~~java
try {
    // Gọi phương thức truy vấn JDBC có try-with-resources.
    findOrders(dataSource, 42L);
} catch (SQLException error) {
    System.err.println("Lỗi JDBC: " + error.getMessage());

    for (Throwable suppressed : error.getSuppressed()) {
        System.err.println("Lỗi khi đóng/rollback: " + suppressed);
    }
}
~~~

Nếu tự đóng tài nguyên bằng `finally`, phải xử lý ngoại lệ khi đóng từng tài nguyên để không bỏ qua các bước đóng còn lại; vì thế, `try-with-resources` là lựa chọn mặc định cho các đối tượng JDBC triển khai `AutoCloseable`.

## 8. Lưu ý với connection pool và kết quả lớn

Trong ứng dụng thực tế, `DataSource` thường lấy `Connection` từ **connection pool**. Lệnh `connection.close()` trên kết nối được pool cấp thường trả kết nối logic về pool để tái sử dụng; nó vẫn là thao tác **bắt buộc** tại ranh giới sở hữu tài nguyên của bạn. Đừng giữ `Connection` dùng chung toàn ứng dụng hoặc chia sẻ cùng một `Statement`/`ResultSet` giữa các luồng mà không có thiết kế đồng bộ rõ ràng.

Với truy vấn nhiều hàng, giữ `ResultSet` mở quá lâu có thể duy trì cursor, bộ nhớ, kết nối hoặc khóa, tùy driver/cơ sở dữ liệu và cấu hình giao dịch. Có thể cân nhắc phân trang, xử lý lần lượt, `setFetchSize(...)` (chỉ là gợi ý cho driver) và giới hạn thời gian truy vấn. Dù dùng chiến lược nào, vòng đời **Connection → Statement → ResultSet → đóng ngược lại** vẫn phải được quản lý.

## 9. Các lỗi thường gặp và cách sửa

| Tình huống | Hậu quả có thể gặp | Cách xử lý |
| --- | --- | --- |
| Chỉ đóng `Connection`, bỏ quên đóng câu lệnh/kết quả | Phụ thuộc vào driver để dọn tài nguyên; khó xác định nguồn rò rỉ | Dùng `try-with-resources` cho cả ba tầng |
| Trả `ResultSet` từ hàm đã đóng `Statement` | Caller không thể đọc kết quả hợp lệ | Ánh xạ dữ liệu ngay trong khối `try` |
| Thực thi SQL mới trên cùng `Statement` khi còn dùng `ResultSet` cũ | Kết quả cũ bị đóng/mất hiệu lực | Đọc xong và đóng kết quả cũ; hoặc tạo câu lệnh riêng |
| Dùng `ResultSet` sau khi đóng `Connection` | Thao tác đọc không còn hợp lệ | Giữ mọi thao tác đọc trong phạm vi kết nối đang mở |
| Bỏ qua `rollback()` khi thao tác giao dịch thất bại | Giao dịch có thể còn dở dang hoặc phụ thuộc driver/pool | Kết thúc giao dịch tường minh; xử lý lỗi rollback |
| Giữ `ResultSet` mở khi xử lý dữ liệu bên ngoài rất lâu | Chiếm dụng kết nối và tài nguyên không cần thiết | Đọc/ánh xạ hoặc xử lý theo lô trong phạm vi ngắn |

## 10. Tự kiểm tra

**Câu 1.** Đã gọi `resultSet.close()`. Có thể tiếp tục dùng `PreparedStatement` trên cùng `Connection` không?

Có, nếu câu lệnh và kết nối vẫn mở và logic ứng dụng cho phép. Đóng tập kết quả không tự đóng hai tài nguyên cha.

**Câu 2.** Nếu `statement.close()` chạy trước `resultSet.next()`, điều gì xảy ra?

`ResultSet` do câu lệnh đó tạo ra không còn hợp lệ; không được tiếp tục đọc.

**Câu 3.** Tại sao phải xử lý dữ liệu trước khi kết thúc khối `try`?

Vì ra khỏi khối `try-with-resources` thì `ResultSet`, `Statement` và `Connection` sẽ được đóng. Dữ liệu đã chuyển sang đối tượng Java độc lập vẫn sử dụng bình thường.

**Câu 4.** Có cần `ResultSet` khi dùng `executeUpdate()` không?

Không, vì `executeUpdate()` trả về số hàng tác động. Chỉ khi cần dữ liệu bổ sung, ví dụ các khóa sinh tự động thông qua `getGeneratedKeys()`, mới có thêm `ResultSet` cần đóng.

**Điểm cần nhớ:** Hãy thiết kế phạm vi sống của `ResultSet` nằm **bên trong** phạm vi sống của `Statement`, và phạm vi sống của `Statement` nằm **bên trong** phạm vi sống của `Connection`. Dùng `try-with-resources` để Java đóng chúng theo thứ tự ngược lúc mở, đồng thời kết thúc giao dịch một cách tường minh khi có `autoCommit=false`.
