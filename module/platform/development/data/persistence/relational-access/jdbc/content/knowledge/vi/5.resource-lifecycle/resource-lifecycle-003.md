# Lựa chọn phạm vi tài nguyên theo một thao tác nghiệp vụ trong JDBC

## 1. Bài toán: tài nguyên JDBC nên tồn tại trong bao lâu?

**JDBC (Java Database Connectivity)** là API chuẩn của Java để truy cập cơ sở dữ liệu quan hệ. Trong JDBC, mỗi truy vấn hoặc cập nhật liên quan đến những tài nguyên có vòng đời riêng: `Connection` đại diện cho phiên kết nối, `Statement` hoặc `PreparedStatement` thực thi SQL, `ResultSet` giữ kết quả có thể duyệt, và đôi khi còn có `Blob`, `Clob`, `InputStream` hay `Reader` phụ thuộc vào kết quả đang mở.

Một thao tác nghiệp vụ có thể chỉ cần đọc một khách hàng, nhưng cũng có thể phải trừ tồn kho và tạo đơn hàng trong **cùng một giao dịch**. Nếu mỗi câu SQL tự mở và đóng một kết nối, thao tác gồm nhiều bước không còn được bảo vệ bởi một local transaction. Ngược lại, nếu giữ kết nối từ lúc bắt đầu một HTTP request đến khi hoàn thành mọi việc, ứng dụng có thể giữ pool connection và khóa database lâu hơn mức cần thiết.

Vì vậy, mục tiêu khi chọn phạm vi tài nguyên là:

- Mỗi tài nguyên có **chủ sở hữu rõ ràng**, biết ai tạo và ai đóng.
- `ResultSet` và `Statement` chỉ tồn tại trong lúc đang đọc hoặc thực thi câu SQL tương ứng.
- `Connection` tồn tại đủ lâu để chứa **toàn bộ phần truy cập database cần dùng chung transaction**, sau đó được giải phóng sớm.
- Các bước nghiệp vụ không cần database, đặc biệt thao tác mạng hoặc chờ người dùng, không giữ kết nối vô ích.

Bài thuộc chương **Vòng đời tài nguyên**, tập trung vào quyết định phạm vi theo **một thao tác nghiệp vụ**: một hành động có ý nghĩa đối với người dùng hoặc hệ thống, ví dụ “xem thông tin sản phẩm”, “chuyển tiền”, “đặt hàng” hoặc “xuất báo cáo”. Phạm vi tài nguyên không phải lúc nào cũng trùng với phạm vi của một request HTTP, một phương thức Java hay một câu SQL.

## 2. Ba cấp tài nguyên và quan hệ sở hữu

~~~mermaid
flowchart TD
    DS["DataSource<br/>nguồn cấp Connection"] --> C["Connection<br/>phạm vi sử dụng database"]
    C --> S["PreparedStatement<br/>phạm vi một câu SQL"]
    S --> R["ResultSet<br/>phạm vi đọc kết quả"]
    R --> B["Giá trị đọc ra / DTO"]
    B --> M["Kết quả nghiệp vụ<br/>có thể dùng sau khi đóng JDBC"]
~~~

| Tài nguyên | Vai trò | Phạm vi hợp lý thường gặp | Người chịu trách nhiệm đóng |
|---|---|---|---|
| `DataSource` | Factory cung cấp `Connection`, có thể được hỗ trợ bởi pool | Được cấu hình và tái sử dụng trong toàn ứng dụng | Vòng đời framework/container/pool; không đóng sau mỗi truy vấn |
| `Connection` | Truy cập database; lưu trạng thái auto-commit, isolation và transaction cục bộ | Một phần công việc cần truy cập database, hoặc một local transaction | Mã đã mượn/mở kết nối hoặc transaction manager |
| `PreparedStatement` | Giữ câu lệnh SQL, tham số và dữ liệu liên quan | Một lần chạy SQL hoặc nhóm lần chạy hợp lý trong cùng connection | Mã tạo statement |
| `ResultSet` | Con trỏ đến các hàng kết quả | Khoảng thời gian duyệt và ánh xạ dữ liệu | Mã nhận kết quả từ statement |
| Stream/LOB có ràng buộc JDBC | Đọc/ghi dữ liệu lớn theo luồng | Khi đối tượng JDBC nguồn còn hợp lệ | Mã mở stream/LOB, theo hợp đồng API/driver |
| DTO/collection đã ánh xạ | Dữ liệu Java độc lập với cursor | Có thể kéo dài qua tầng nghiệp vụ và API | Được quản lý như đối tượng Java thông thường |

**Quan hệ sở hữu rất quan trọng:** phương thức mượn connection từ `DataSource` thường phải đóng handle đó; một phương thức được *truyền vào* `Connection` từ bên ngoài thường **không nên đóng kết nối của caller**. Hàm con vẫn phải đóng các `PreparedStatement` và `ResultSet` do chính nó tạo.

### Điều gì xảy ra khi gọi `close()`?

- `ResultSet.close()` giải phóng tài nguyên của cursor/kết quả. Đóng `Statement` cũng đóng `ResultSet` hiện hành do statement tạo ra.
- `Statement.close()` giải phóng tài nguyên của statement; nó không có nghĩa là phải đóng toàn bộ `Connection` ngay lập tức.
- `Connection.close()` giải phóng tài nguyên kết nối theo hợp đồng JDBC. Với một connection pool, gọi `close()` trên logical connection **thường trả handle về pool** để tái sử dụng kết nối vật lý.
- `DataSource` không có phương thức `close()` trong interface chuẩn; nếu implementation có chức năng shutdown pool riêng, lifecycle đó thuộc tầng quản lý ứng dụng.

Không nên dựa hoàn toàn vào việc đóng connection để cleanup các tài nguyên con: đóng rõ `ResultSet` và `Statement` giúp phạm vi tài nguyên dễ kiểm soát hơn và tránh phụ thuộc hành vi triển khai.

## 3. Nguyên tắc chọn phạm vi theo thao tác nghiệp vụ

Trước khi viết mã truy cập dữ liệu, hãy đặt ba câu hỏi:

1. **Thao tác nghiệp vụ bao gồm những bước SQL nào?** Các bước này cần cùng thành công/thất bại hay độc lập?
2. **Có phần xử lý nào không cần giữ connection?** Ví dụ xác thực đầu vào tại bộ nhớ, gọi HTTP, gửi email, chờ phản hồi, tính toán kéo dài.
3. **Dữ liệu trả về có còn cần `ResultSet` mở không?** Nếu chỉ cần DTO, hãy ánh xạ xong và đóng tài nguyên trước khi rời tầng truy cập dữ liệu.

Bảng quyết định:

| Thao tác | Ranh giới connection/transaction phù hợp | Lý do |
|---|---|---|
| Tìm một sản phẩm theo mã | Mượn connection → chạy SELECT → đọc DTO → đóng | Chỉ một truy vấn và không cần giữ cursor bên ngoài |
| Cập nhật một trạng thái đơn hàng | Mượn connection → chạy UPDATE → đóng | Một câu DML có thể tự commit nếu auto-commit phù hợp |
| Trừ tồn kho **và** tạo đơn hàng phải cùng thành công | Một connection, auto-commit tắt, nhiều statement, commit/rollback chung | Bảo đảm tính nguyên tử của phần cập nhật database |
| Đọc hàng loạt dữ liệu để xuất tệp lớn | Connection và cursor tồn tại trong pha đọc tuần tự; đóng ngay sau đó | Tránh nạp toàn bộ dữ liệu nhưng phải kiểm soát thời gian giữ kết nối |
| Xác minh đầu vào, gọi dịch vụ bên ngoài rồi mới ghi dữ liệu | Chỉ mở connection khi tới phần SQL, nếu yêu cầu nhất quán cho phép | Giảm giữ kết nối khi chờ I/O không thuộc database |
| Xử lý tác vụ nền theo nhiều lô độc lập | Mỗi lô có connection/transaction và checkpoint riêng khi phù hợp | Tránh transaction khổng lồ và khóa kéo dài |

**Quy tắc thực dụng:** một *đơn vị công việc với database* nên có người sở hữu ranh giới kết nối. Khi cần atomicity qua nhiều câu SQL, ranh giới transaction quan trọng hơn việc chia mã thành bao nhiêu phương thức hay lớp.

## 4. Trường hợp đơn giản: một truy vấn, một phạm vi đọc

Giả sử chức năng “xem sản phẩm” trả về mã, tên và giá. Repository chỉ cần mượn connection trong lúc truy vấn và ánh xạ `ResultSet` thành `Product`:

~~~java
import java.math.BigDecimal;

public record Product(long id, String name, BigDecimal price) {}
~~~

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import javax.sql.DataSource;

public final class ProductReader {
    private final DataSource dataSource;

    public ProductReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Optional<Product> findById(long id) throws SQLException {
        String sql = """
                SELECT id, name, price
                FROM products
                WHERE id = ?
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, id);

            try (ResultSet rs = statement.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty();
                }
                Product product = new Product(
                        rs.getLong("id"),
                        rs.getString("name"),
                        rs.getBigDecimal("price"));
                return Optional.of(product);
            }
        }
    }
}
~~~

Ví dụ dùng Java 17+ (record và text block), bảng minh họa `products(id, name, price)`, driver thích hợp và `DataSource` đã cấu hình.

Diễn giải phạm vi:

1. **Repository mượn `Connection`** khi công việc database bắt đầu.
2. **Statement** tồn tại để thực thi câu `SELECT`; tham số `id` được bind bằng `setLong(1, id)` nhằm tránh ghép chuỗi SQL.
3. **ResultSet** tồn tại chỉ trong phạm vi `executeQuery()` và đọc các cột.
4. **Product** là bản sao dữ liệu Java; không chứa con trỏ JDBC.
5. `try-with-resources` đóng tài nguyên theo thứ tự ngược khi rời khối, kể cả trường hợp trả về sớm hoặc ném ngoại lệ.

Sau khi gọi `findById`, tầng service nhận `Optional<Product>` và có thể xử lý tiếp mà **không giữ connection**. Một method chỉ cần trả DTO không nên đẩy nghĩa vụ đóng `ResultSet` lên controller.

### Tránh trả `ResultSet` vượt quá vòng đời connection

Ví dụ sai:

~~~java
// SAI: ResultSet sẽ không còn sử dụng an toàn sau khi đóng Statement/Connection.
ResultSet findAll(DataSource source) throws SQLException {
    try (Connection connection = source.getConnection();
         PreparedStatement statement =
                 connection.prepareStatement("SELECT * FROM products")) {
        return statement.executeQuery();
    }
}
~~~

Lúc caller nhận kết quả, khối `try-with-resources` đã đóng statement và connection. Một lựa chọn khác là để caller giữ cả connection, statement và result set, nhưng API trở nên khó quản lý và dễ rò rỉ tài nguyên. Với truy vấn thông thường, ánh xạ sang DTO/collection trước khi đóng tài nguyên đơn giản và an toàn hơn.

## 5. Trường hợp nhiều câu SQL: một thao tác nghiệp vụ, một transaction

Giả sử chức năng **“đặt hàng”** cần thực hiện hai bước:

1. Giảm số lượng tồn kho của sản phẩm.
2. Tạo bản ghi đơn hàng.

Yêu cầu nghiệp vụ: nếu không còn đủ hàng hoặc không thể tạo đơn, thay đổi tồn kho **không được lưu lại**. Hai bước phải là một local transaction trên cùng database và cùng connection.

~~~mermaid
sequenceDiagram
    participant Service as OrderService
    participant DS as DataSource
    participant DB as Database
    Service->>DS: getConnection()
    DS-->>Service: Connection
    Service->>Service: setAutoCommit(false)
    Service->>DB: UPDATE products giảm tồn kho
    DB-->>Service: Số hàng bị ảnh hưởng
    alt Đủ tồn kho và UPDATE thành công
        Service->>DB: INSERT orders
        DB-->>Service: Kết quả INSERT
        Service->>DB: commit()
    else Có lỗi / hết hàng
        Service->>DB: rollback()
    end
    Service->>DS: Connection.close()
    Note over DS: Pool có thể tái sử dụng<br/>kết nối vật lý
~~~

### Ví dụ: tầng service sở hữu transaction, helper sở hữu statement

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class OrderService {
    private final DataSource dataSource;

    public OrderService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void placeOrder(long orderId, long productId, int quantity)
            throws SQLException {
        if (orderId <= 0 || productId <= 0 || quantity <= 0) {
            throw new IllegalArgumentException("Thông tin đơn hàng không hợp lệ");
        }

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                int updated = decreaseAvailableStock(
                        connection, productId, quantity);
                if (updated != 1) {
                    throw new SQLException(
                            "Sản phẩm không tồn tại hoặc không đủ tồn kho");
                }

                insertOrder(connection, orderId, productId, quantity);
                connection.commit();
            } catch (SQLException | RuntimeException problem) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackProblem) {
                    problem.addSuppressed(rollbackProblem);
                }
                throw problem;
            }
        }
    }

    private static int decreaseAvailableStock(
            Connection connection, long productId, int quantity)
            throws SQLException {
        String sql = """
                UPDATE products
                SET available = available - ?
                WHERE id = ? AND available >= ?
                """;

        // Helper đóng Statement do chính mình tạo, không đóng Connection.
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setInt(1, quantity);
            statement.setLong(2, productId);
            statement.setInt(3, quantity);
            return statement.executeUpdate();
        }
    }

    private static void insertOrder(
            Connection connection, long orderId, long productId, int quantity)
            throws SQLException {
        String sql = """
                INSERT INTO orders (id, product_id, quantity)
                VALUES (?, ?, ?)
                """;

        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, orderId);
            statement.setLong(2, productId);
            statement.setInt(3, quantity);
            if (statement.executeUpdate() != 1) {
                throw new SQLException("Không thể tạo đơn hàng");
            }
        }
    }
}
~~~

Giả định database hỗ trợ transaction, bảng `products(id, available)` và `orders(id, product_id, quantity)` tồn tại, cùng các khóa/ràng buộc thích hợp. Ví dụ đơn giản hóa nghiệp vụ: mã đơn hàng được cấp trước khi gọi, không tính giá và không phối hợp dịch vụ ngoài. Điều kiện `available >= ?` trong `UPDATE` là một cách kiểm tra số lượng tồn kho ngay ở database; vẫn cần đánh giá isolation, locking và ràng buộc dữ liệu theo hệ quản trị thực tế.

### Tại sao đây là một ranh giới hợp lý?

- Service mượn **một `Connection` duy nhất** và là chủ sở hữu của transaction.
- `setAutoCommit(false)` bắt đầu chế độ quản lý transaction thủ công; hai câu DML được xác nhận chung bằng `commit()`, hoặc hoàn tác bằng `rollback()`.
- Các helper nhận `Connection` để tham gia transaction; mỗi helper chỉ đóng `PreparedStatement` do mình tạo.
- Connection chỉ được đóng sau khi transaction đã commit hoặc rollback. Khi dùng pool, việc đóng handle sẽ giải phóng suất kết nối cho thao tác khác.
- Nếu rollback cũng lỗi, ngoại lệ rollback được gắn dưới dạng **suppressed exception** vào lỗi ban đầu để hỗ trợ chẩn đoán.

Nếu `commit()` gặp lỗi do kết nối gián đoạn, trạng thái xác nhận ở phía database có thể không rõ ràng đối với ứng dụng. Không được tự động phát lại thao tác tạo đơn nếu chưa có cơ chế idempotency/kiểm tra trạng thái phù hợp.

**Chú ý:** ví dụ tự quản lý local transaction. Trong ứng dụng sử dụng transaction manager (Spring, Jakarta EE...), giao dịch thường nên do framework quản lý; mã repository dùng API tham gia transaction do framework cung cấp. Không tùy tiện gọi `setAutoCommit`, `commit` hoặc `rollback` trên kết nối mà transaction manager đang sở hữu.

## 6. Sai lệch phổ biến: mỗi helper tự lấy connection

Xem luồng thiết kế sau:

~~~text
placeOrder()
  ├── productRepository.decreaseStock()
  │     ├── DataSource.getConnection()  -> Connection A
  │     ├── UPDATE products
  │     └── close() / auto-commit
  └── orderRepository.insertOrder()
        ├── DataSource.getConnection()  -> Connection B
        ├── INSERT orders
        └── close() / auto-commit
~~~

Nếu mỗi repository tự lấy kết nối và tự commit, cập nhật tồn kho trên **Connection A** có thể thành công trong khi tạo đơn trên **Connection B** thất bại. Khi đó có nguy cơ tồn kho đã giảm nhưng không tồn tại đơn hàng tương ứng.

Cách tổ chức phù hợp với JDBC thuần khi cần một local transaction là cho **lớp điều phối nghiệp vụ sở hữu `Connection`** và truyền nó vào các hàm truy cập dữ liệu tương ứng. Một kiến trúc khác có thể dùng transaction manager giúp các repository tham gia cùng transaction mà không truyền `Connection` theo cách thủ công.

**Phân biệt:** không phải cứ hai lệnh SQL được gọi trong một phương thức Java thì chúng tự động nằm cùng transaction; và cũng không phải cứ dùng cùng `DataSource` thì hai lần `getConnection()` sẽ dùng chung transaction. Ranh giới transaction phụ thuộc cách lấy/điều phối connection và cơ chế transaction thực tế.

## 7. Phạm vi tài nguyên khác phạm vi phương thức và request

Một yêu cầu HTTP có thể đi qua nhiều giai đoạn:

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Kiểm tra input<br/>không cần Connection"]
    B --> C["Tính toán / kiểm tra quyền<br/>không cần Connection nếu đã có dữ liệu"]
    C --> D["Mượn Connection"]
    D --> E["SQL + transaction nếu cần"]
    E --> F["commit / rollback<br/>và đóng Connection"]
    F --> G["Chuyển DTO thành response"]
    G --> H["HTTP response"]
~~~

Phần công việc cần giữ connection có thể chỉ là một đoạn giữa request. Ví dụ, xác thực định dạng số điện thoại hoặc giá trị đầu vào ngay trong bộ nhớ không cần mở connection từ đầu. Khi đã đọc xong dữ liệu và đóng tài nguyên JDBC, việc định dạng JSON không cần giữ kết nối.

Một connection thuộc pool là tài nguyên hữu hạn và có chi phí; việc kéo dài phạm vi làm tăng thời gian chiếm slot pool và có thể kéo dài **khóa**, transaction hoặc trạng thái server. Tuy nhiên, tối ưu thời gian giữ connection không được phá vỡ tính nhất quán: nếu các bước cần chung transaction, không được đóng connection ở giữa chỉ để giảm thời gian mượn.

### Không giữ connection khi chờ dịch vụ bên ngoài

Ví dụ một đơn hàng cần gọi cổng thanh toán hoặc gửi email. Những lời gọi này có thể chậm, timeout hoặc retry; việc đặt chúng giữa `setAutoCommit(false)` và `commit()` thường làm transaction kéo dài:

~~~text
Không nên mặc định:
BEGIN -> UPDATE/INSERT -> gọi HTTP 15 giây -> COMMIT
                       (giữ connection và có thể giữ lock)
~~~

Thực tế cần chọn ranh giới nghiệp vụ và cơ chế phối hợp phù hợp: xác thực điều kiện trước, ghi trạng thái trong một database transaction ngắn, rồi thực hiện I/O bên ngoài sau commit hoặc qua queue/outbox khi cần giao việc tin cậy. **Database rollback không tự hoàn tác được email đã gửi hay thanh toán đã thực hiện.** Nếu có yêu cầu nhất quán xuyên nhiều hệ thống, cần thiết kế idempotency, trạng thái trung gian, retry hoặc cơ chế điều phối phù hợp.

## 8. Khi xử lý kết quả lớn: tài nguyên có thể cần tồn tại lâu hơn

Với truy vấn trả về vài triệu hàng, việc tạo `List` chứa toàn bộ đối tượng có thể tiêu thụ nhiều bộ nhớ. Một cách là xử lý từng hàng trong lúc `ResultSet` còn mở:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.function.Consumer;
import javax.sql.DataSource;

public final class CustomerScanner {
    private final DataSource dataSource;

    public CustomerScanner(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void scanCustomers(Consumer<CustomerRow> consumer)
            throws SQLException {
        String sql = "SELECT id, email FROM customers ORDER BY id";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setFetchSize(500); // Gợi ý cho driver, không bảo đảm streaming.

            try (ResultSet rs = statement.executeQuery()) {
                while (rs.next()) {
                    consumer.accept(new CustomerRow(
                            rs.getLong("id"),
                            rs.getString("email")));
                }
            }
        }
    }

    public record CustomerRow(long id, String email) {}
}
~~~

Trong ví dụ, callback chạy **đồng bộ** bên trong phạm vi `ResultSet`. Chỉ chuyển các giá trị Java đã đọc sang callback, không truyền cursor `ResultSet` để lưu dùng sau. Nếu `consumer.accept(...)` ném ngoại lệ runtime, `try-with-resources` vẫn đóng tài nguyên.

Một số giới hạn cần hiểu:

- `setFetchSize(500)` là gợi ý. Streaming/cursor thật sự phụ thuộc driver, cấu hình và đôi khi transaction/auto-commit hoặc kiểu câu lệnh.
- Callback xử lý quá chậm có thể giữ `Connection` và server cursor lâu. Không nên gọi API bên ngoài chậm hoặc đẩy công việc dài hạn trực tiếp từ callback trong khi giữ cursor.
- Nếu cần xử lý độc lập sau khi kết nối đóng, hãy ánh xạ sang DTO, chia trang/lô hoặc sao chép dữ liệu vào một cấu trúc ngoại tuyến có giới hạn.
- Duyệt nhiều hàng không đồng nghĩa cần một transaction ghi kéo dài. Mức isolation và snapshot nhất quán phải được quyết định theo yêu cầu nghiệp vụ và khả năng database.

## 9. Những tài nguyên phụ thuộc vào `ResultSet`

Đôi khi kết quả SQL chứa dữ liệu lớn như `BLOB`, `CLOB` hoặc `SQLXML`. API có thể trả đối tượng/stream phụ thuộc kết nối, câu lệnh hoặc kết quả nguồn. Ví dụ:

~~~java
try (ResultSet rs = statement.executeQuery()) {
    if (rs.next()) {
        try (java.io.InputStream input = rs.getBinaryStream("file_data")) {
            if (input != null) {
                // Đọc nội dung khi ResultSet và Statement vẫn còn hợp lệ.
                byte[] buffer = new byte[8192];
                while (input.read(buffer) != -1) {
                    // Xử lý từng khối; ví dụ minh họa không lưu toàn bộ file.
                }
            }
        }
    }
}
~~~

Đây là đoạn minh họa bên trong ngữ cảnh đã có `statement`; thực tế cần xử lý hoặc khai báo `IOException` bên cạnh `SQLException`. Đối tượng LOB/stream có chi tiết vòng đời riêng theo driver/API và đôi khi cần giải phóng thêm (ví dụ `Blob.free()`, `Clob.free()`).

Đừng trả về một `InputStream` trực tiếp từ `ResultSet` sau khi kết nối đã đóng, vì việc đọc stream sau đó có thể thất bại. Với response tải tệp, có thể thiết kế streaming có quản lý vòng đời đến khi hoàn tất truyền, hoặc sao chép dữ liệu sang tệp/bộ nhớ có giới hạn trước khi đóng JDBC.

## 10. Trách nhiệm đóng tài nguyên trong các tầng ứng dụng

Một quy ước đơn giản giúp mã dễ kiểm tra:

| Ai tạo hoặc nhận tài nguyên? | Trách nhiệm |
|---|---|
| Thành phần cấu hình tạo `DataSource`/pool | Quản lý lifecycle pool khi ứng dụng khởi động và dừng |
| Service chủ động mượn `Connection` để quản lý transaction | `commit`/`rollback` đúng lúc; đóng connection sau khi kết thúc |
| Repository được truyền `Connection` có sẵn | Dùng connection đó; **không đóng connection của caller** |
| Repository chủ động mượn `Connection` cho truy vấn độc lập | Đọc/map xong thì đóng connection của chính mình |
| Hàm tạo `PreparedStatement`/`ResultSet` | Đóng chúng trong phạm vi dùng, thường với `try-with-resources` |
| Transaction manager/framework sở hữu transaction/connection | Framework quản lý commit/rollback/close theo cơ chế tương ứng |

Đừng để `Connection`, `PreparedStatement` hay `ResultSet` làm **field dùng chung cho các request** trong một singleton service/repository:

~~~java
// KHÔNG NÊN: một Connection chia sẻ trên nhiều request/thread.
class UnsafeRepository {
    private Connection sharedConnection;
}
~~~

`DataSource` hoặc pool thường được thiết kế để chia sẻ an toàn; **một `Connection` đang có trạng thái transaction** không nên được dùng tùy tiện cho nhiều luồng đồng thời. Mỗi thao tác nghiệp vụ lấy một logical connection riêng (hoặc sử dụng context transaction framework đang quản lý).

### `try-with-resources` giúp gì?

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
             connection.prepareStatement("SELECT COUNT(*) FROM customers");
     ResultSet rs = statement.executeQuery()) {

    if (rs.next()) {
        System.out.println(rs.getLong(1));
    }
}
~~~

Tài nguyên được đóng theo thứ tự ngược với khai báo: `ResultSet`, `PreparedStatement`, rồi `Connection`. Nếu phần thân ném ngoại lệ và `close()` cũng lỗi, Java giữ lỗi phần thân là ngoại lệ chính, gắn lỗi khi đóng vào danh sách **suppressed exceptions**. Vì thế `try-with-resources` thường đáng tin cậy và dễ đọc hơn các khối `finally` dài.

**Ngoại lệ quan trọng:** `try-with-resources` không thay thế **`commit()`/`rollback()`** cho thao tác nhiều bước khi đã tắt auto-commit. Nếu đóng connection trong khi transaction đang mở, kết quả có thể phụ thuộc driver/database; hãy hoàn tất transaction rõ ràng trước khi đóng.

## 11. Vòng đời và transaction khi dùng framework

Với Spring JDBC, một phương thức service được quản lý transaction (ví dụ `@Transactional` trong cấu hình phù hợp) có thể bao trùm nhiều lời gọi repository. Khi đó, lớp truy cập dữ liệu dùng API tham gia transaction như `JdbcTemplate`/`DataSourceUtils` theo cơ chế Spring, thay vì tùy tiện tự tạo và tự commit một kết nối bằng `DriverManager`.

Với Jakarta EE hoặc các transaction manager khác, container có thể quản lý connection và ranh giới transaction theo hợp đồng riêng. Ý tưởng nghiệp vụ vẫn giống nhau: **các bước SQL cần atomicity phải tham gia cùng transaction**, và người sở hữu transaction phải quản lý kết thúc/giải phóng tài nguyên.

Cần phân biệt:

- **Local transaction:** do một `java.sql.Connection` quản lý qua auto-commit, commit và rollback.
- **Transaction framework:** transaction manager điều phối việc truy cập dữ liệu trong phạm vi nghiệp vụ; mã ứng dụng phải sử dụng đúng API để tham gia.
- **Distributed transaction (XA):** xử lý việc phối hợp nhiều tài nguyên khi thật sự cần; có chi phí và giới hạn riêng, không tự phát sinh chỉ vì ứng dụng gọi hai repository.

Không nên dùng `Connection.close()` trực tiếp đối với kết nối đang do transaction framework quản lý nếu API framework yêu cầu phương thức giải phóng riêng. Ví dụ trong Spring, việc lấy connection trực tiếp từ `DataSource` thông thường có thể không tuân theo transaction context mong muốn; dùng cơ chế do Spring cung cấp hoặc repository dựa trên `JdbcTemplate`.

## 12. Tình huống thực tế và đánh đổi

| Tình huống | Lỗi thiết kế dễ gặp | Cách chọn phạm vi |
|---|---|---|
| API đọc chi tiết đơn hàng | Trả `ResultSet` ra controller; đóng connection trước khi JSON được dựng | Ánh xạ DTO ngay trong repository, đóng JDBC rồi trả DTO |
| Đặt hàng | Mỗi cập nhật lấy connection độc lập và auto-commit | Một transaction bao gồm toàn bộ bước SQL cần cùng thành công |
| Duyệt nhiều sản phẩm | Giữ một `ResultSet` trong session người dùng | Phân trang, cache dữ liệu giới hạn hoặc truy vấn lại theo nhu cầu |
| Xuất dữ liệu lớn | Đọc hết vào `List` khổng lồ | Duyệt tuần tự và quản lý rõ lifetime của connection/cursor |
| Gọi thanh toán bên ngoài | Gọi HTTP giữa `UPDATE` và `COMMIT` | Thiết kế trạng thái nghiệp vụ và phối hợp ngoài DB, giảm thời gian giữ transaction |
| Xử lý batch lâu | Một transaction quá lớn, giữ lock hàng phút | Chia lô nếu nghiệp vụ cho phép và có checkpoint/idempotency |
| Repository singleton | Lưu `Connection` vào field chia sẻ | Chia sẻ `DataSource`; connection gắn với operation/transaction |
| Ứng dụng dùng pool | Không gọi `close()` vì tưởng pool tự thu hồi | Gọi `close()` đúng thời điểm để trả logical connection |
| Thất bại giữa nhiều câu DML | Trông chờ connection `close()` sẽ luôn rollback | `rollback()` chủ động khi lỗi, `commit()` rõ ràng khi thành công |

### Tại sao phạm vi quá dài gây áp lực?

Giả sử pool có 10 connection và 10 request cùng giữ mỗi connection để chờ API ngoài trong nhiều giây. Request thứ 11 có thể phải chờ dù database không xử lý SQL nào trong thời gian đó. Nếu transaction đã khóa các bản ghi, request khác còn có thể bị chặn tại database. Cần đo **thời gian mượn connection**, thời gian giao dịch, số connection đang dùng, hàng chờ pool và thời gian SQL để hiểu nút thắt.

### Tại sao phạm vi quá ngắn cũng nguy hiểm?

Nếu một thao tác chuyển tiền gồm trừ tiền rồi cộng tiền được tách ra hai connection với hai lần auto-commit độc lập, thành công từng phần có thể làm dữ liệu sai lệch. Trong trường hợp này, phạm vi connection/transaction phải bao trùm **cả hai câu UPDATE**, mặc dù ta có thể tách logic vào hai phương thức Java.

## 13. Cách nhận biết và chẩn đoán rò rỉ tài nguyên

Rò rỉ ở đây thường là **connection hoặc cursor không được đóng đúng thời điểm**, không nhất thiết là “memory leak” của Java heap. Một số dấu hiệu:

- Pool hết connection, yêu cầu mới phải chờ hoặc timeout dù database vẫn hoạt động.
- Số lượng connection “active/in use” không giảm sau khi tải nghiệp vụ kết thúc.
- Database có nhiều session giữ transaction mở hoặc giữ khóa quá lâu.
- Ứng dụng báo lỗi “too many connections”, “connection not available” hoặc “too many open cursors” tùy môi trường.

Các biện pháp kiểm tra:

1. Đọc code path có ngoại lệ hoặc `return` sớm để bảo đảm tất cả tài nguyên được đóng.
2. Dùng `try-with-resources` hoặc API framework quản lý tài nguyên đúng cách.
3. Kiểm tra mọi helper có vô tình đóng connection do caller sở hữu hoặc mở thêm connection tách transaction hay không.
4. Xem số connection đang mượn và thời gian mượn trong pool; đối chiếu transaction dài và truy vấn SQL chậm.
5. Nếu pool có tính năng cảnh báo connection leak, dùng như tín hiệu chẩn đoán; một thao tác hợp lệ nhưng quá lâu cũng có thể kích hoạt cảnh báo.

Đừng khắc phục một connection leak bằng cách chỉ tăng kích thước pool. Việc đó có thể che vấn đề tạm thời và tăng tải lên database.

## 14. Checklist chọn phạm vi trước khi triển khai

- [ ] Tôi xác định rõ **đơn vị công việc nghiệp vụ** và các câu SQL liên quan.
- [ ] Nếu nhiều câu SQL phải cùng thành công/thất bại, chúng tham gia **cùng transaction** theo cơ chế được sử dụng.
- [ ] Tôi biết tầng nào sở hữu `Connection`, tầng nào chỉ nhận connection để dùng.
- [ ] `PreparedStatement` và `ResultSet` được đóng tại nơi tạo/sử dụng bằng `try-with-resources`.
- [ ] Tôi không trả `ResultSet` hoặc stream phụ thuộc connection sau khi connection đóng.
- [ ] Tôi không giữ connection qua tác vụ chờ dài, I/O bên ngoài hoặc công việc không cần database khi không có yêu cầu nhất quán buộc phải giữ.
- [ ] Với dữ liệu lớn, tôi đã cân nhắc streaming, phân trang, dung lượng bộ nhớ và thời gian chiếm connection.
- [ ] Với transaction thủ công, đường thành công gọi `commit()` và đường lỗi gọi `rollback()`, kể cả khi exception phát sinh.
- [ ] Nếu dùng connection pool hoặc transaction framework, tôi theo đúng lifecycle và API do chúng quy định.

## 15. Câu hỏi tự kiểm tra

1. Một service gồm `UPDATE products` và `INSERT orders` phải cùng thành công. Vì sao mỗi repository tự `getConnection()` rồi tự commit là thiết kế nguy hiểm?
2. Một repository mở `Connection`, trả về `ResultSet` nhưng đã thoát khối `try-with-resources`. Vấn đề ở đâu? Nên trả về kiểu nào?
3. Hàm `decreaseAvailableStock(Connection connection, ...)` có nên gọi `connection.close()` không? Vì sao?
4. Một request mất hai giây để gọi API thanh toán và 30 ms để chạy SQL. Nếu không có yêu cầu giữ transaction trong suốt hai giây, nên mở connection ở giai đoạn nào?
5. `setFetchSize(500)` có bảo đảm driver chỉ giữ 500 hàng trong bộ nhớ không? Tại sao cần đọc tài liệu driver?
6. Vì sao `try-with-resources` không thay thế được `commit()`/`rollback()` trong transaction thủ công?
7. Với connection pool, `Connection.close()` thường có tác dụng gì và vì sao vẫn phải gọi?

**Điểm cần nhớ:** **ràng buộc phạm vi tài nguyên JDBC theo phần việc thật sự cần database**, và **ràng buộc transaction theo tính nguyên tử của nghiệp vụ**. Một truy vấn đọc đơn giản thường mượn connection, ánh xạ DTO rồi đóng ngay. Một thao tác gồm nhiều thay đổi phụ thuộc nhau cần cùng connection/transaction, còn các statement và result set nên được tạo và đóng ở phạm vi hẹp nhất có thể.

### Tài liệu tham khảo

- [Java SE 21 — `java.sql.Connection`](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Connection.html)
- [Java SE 21 — `java.sql.Statement`](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Statement.html)
- [Java SE 21 — `java.sql.ResultSet`](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/ResultSet.html)
- [Java SE 21 — `java.sql.PreparedStatement`](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/PreparedStatement.html)
- [Java SE 21 — `javax.sql.DataSource`](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/javax/sql/DataSource.html)
- [Java Language Specification — try-with-resources](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.3)
