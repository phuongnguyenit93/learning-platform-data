# Luồng xử lý từ mở kết nối đến đọc kết quả và giải phóng tài nguyên trong JDBC

## 1. Toàn cảnh một lượt truy cập cơ sở dữ liệu bằng JDBC

**JDBC (Java Database Connectivity)** là API tiêu chuẩn để ứng dụng Java giao tiếp với cơ sở dữ liệu quan hệ: mở kết nối, gửi câu lệnh SQL, nhận kết quả và quản lý tài nguyên. Trong chương **Nền tảng**, hiểu trọn vẹn luồng xử lý này giúp bạn viết được mã truy cập dữ liệu đúng, dễ bảo trì và hạn chế lỗi rò rỉ kết nối.

Một lượt **đọc dữ liệu** điển hình có thể diễn đạt như sau:

~~~mermaid
flowchart TD
    A["Ứng dụng cần đọc dữ liệu"] --> B["Lấy Connection"]
    B --> C["Tạo PreparedStatement"]
    C --> D["Gán tham số cho câu SQL"]
    D --> E["executeQuery()"]
    E --> F["Nhận ResultSet"]
    F --> G{"resultSet.next()?"}
    G -->|Có| H["Đọc cột và ánh xạ sang đối tượng Java"]
    H --> G
    G -->|Không| I["Đóng ResultSet"]
    I --> J["Đóng PreparedStatement"]
    J --> K["Đóng/trả Connection"]
    K --> L["Trả dữ liệu cho tầng gọi"]
~~~

Ba đối tượng xuất hiện thường xuyên nhất là:

| Đối tượng | Vai trò | Điểm cần nhớ |
| --- | --- | --- |
| `Connection` | Đại diện cho một phiên làm việc JDBC với cơ sở dữ liệu | Cấp `PreparedStatement`, chứa trạng thái giao dịch, cần đóng/trả pool đúng lúc. |
| `PreparedStatement` | Câu lệnh SQL đã được chuẩn bị, có thể chứa tham số `?` | Dùng `setXxx()` để truyền giá trị; thực thi bằng `executeQuery()` hoặc `executeUpdate()`. |
| `ResultSet` | Kết quả dạng bảng/cursor sau khi thực thi truy vấn | Duyệt bằng `next()`, đọc giá trị bằng `getXxx()`, cần đóng khi dùng xong. |

**Nguyên tắc sở hữu tài nguyên:** phương thức hoặc tầng nào lấy `Connection` thường chịu trách nhiệm kết thúc vòng đời của nó. Nếu một DAO chỉ **nhận** `Connection` từ service đang quản lý giao dịch, DAO không nên tự đóng kết nối đó; DAO vẫn phải đóng những `Statement` và `ResultSet` do mình tạo.

## 2. Bước 1 — Lấy kết nối với cơ sở dữ liệu

Bạn có thể lấy kết nối trực tiếp bằng `DriverManager` hoặc thông qua `DataSource`:

~~~java
// Cách A: kết nối trực tiếp; URL là ví dụ cho PostgreSQL.
String url = "jdbc:postgresql://localhost:5432/shop";
try (Connection connection =
         DriverManager.getConnection(url, username, password)) {
    // Thao tác JDBC tại đây.
}
~~~

`DriverManager.getConnection(...)` yêu cầu driver JDBC tương ứng có trên classpath/module path và phải sử dụng JDBC URL đúng định dạng của driver. Driver hiện đại thường tự đăng ký qua cơ chế service provider của JDBC; bạn không cần mặc định viết `Class.forName("...Driver")` trong mọi dự án.

Trong ứng dụng nhiều yêu cầu, `DataSource` thường được ưu tiên vì dễ cấu hình kết nối và tích hợp connection pool:

~~~java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.SQLException;

public void work(DataSource dataSource) throws SQLException {
    try (Connection connection = dataSource.getConnection()) {
        // Sử dụng connection trong phạm vi khối try.
    } // close() được gọi tự động.
}
~~~

`DataSource` được cấu hình ở bên ngoài ví dụ (qua container, framework hoặc thư viện pool). Với pool, `Connection.close()` **thường trả kết nối về pool**, không nhất thiết đóng socket vật lý; vì vậy đóng kết nối vẫn là thao tác bắt buộc để pool tái sử dụng tài nguyên.

### Điều gì xảy ra khi lấy kết nối?

Một lần `getConnection()` có thể bao gồm việc mượn kết nối từ pool hoặc mở phiên mới với DBMS, xác thực, thiết lập trạng thái session và kiểm tra khả năng kết nối. Thao tác có thể thất bại vì sai URL, sai thông tin đăng nhập, mạng lỗi, DBMS không hoạt động hoặc pool đã hết kết nối khả dụng.

Không nên giữ `Connection` dưới dạng biến `static` để tái sử dụng tùy tiện giữa nhiều luồng. Một kết nối có trạng thái giao dịch, tập câu lệnh và tài nguyên đang mở; chia sẻ không kiểm soát dễ dẫn tới lỗi đóng nhầm hoặc commit/rollback nhầm. Thông thường mỗi lượt xử lý nghiệp vụ sẽ mượn một kết nối trong thời gian cần thiết.

## 3. Bước 2 — Chuẩn bị SQL và truyền tham số

`Connection` tạo ra `Statement`, `PreparedStatement` hoặc `CallableStatement`. Với truy vấn có dữ liệu đầu vào, nên bắt đầu bằng `PreparedStatement`:

~~~java
String sql = """
    SELECT id, name, price, stock_quantity
    FROM product
    WHERE id = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 42L);
    // Thực thi câu lệnh ở bước tiếp theo.
}
~~~

Trong cú pháp Java trên, text block `"""` yêu cầu Java 15 trở lên; nếu sử dụng Java cũ hơn, chỉ cần thay bằng chuỗi thông thường. Dấu `?` là **placeholder** cho *giá trị* SQL; tham số JDBC được đánh số từ **1**, do đó `setLong(1, 42L)` gán giá trị cho placeholder đầu tiên.

Một số phương thức gán giá trị phổ biến:

| Giá trị Java | Phương thức thường dùng |
| --- | --- |
| `long`, `int` | `setLong(index, value)`, `setInt(index, value)` |
| `String` | `setString(index, value)` |
| `BigDecimal` | `setBigDecimal(index, value)` |
| `boolean` | `setBoolean(index, value)` |
| `LocalDate` | `setObject(index, date)` khi driver hỗ trợ JDBC 4.2 |
| SQL `NULL` có kiểu xác định | `setNull(index, java.sql.Types.INTEGER)`, hoặc kiểu SQL phù hợp |

Ví dụ có hai tham số:

~~~java
String sql = "SELECT id, name FROM product WHERE price >= ? AND name LIKE ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setBigDecimal(1, new BigDecimal("100.00"));
    ps.setString(2, "Laptop%");
    // Hai giá trị được truyền tách khỏi nội dung câu SQL.
}
~~~

`PreparedStatement` giúp tránh lỗi SQL injection khi truyền **giá trị**. Không ghép giá trị lấy từ người dùng vào SQL bằng nối chuỗi:

~~~java
// Tránh: trực tiếp nối input thành mã SQL.
String unsafe = "SELECT id FROM product WHERE name = '" + inputName + "'";

// Nên: truyền input như một tham số.
String safe = "SELECT id FROM product WHERE name = ?";
try (PreparedStatement ps = connection.prepareStatement(safe)) {
    ps.setString(1, inputName);
}
~~~

Placeholder không thay thế trực tiếp được **tên bảng, tên cột, từ khóa SQL hoặc toàn bộ mệnh đề ORDER BY**. Nếu cần chọn cột để sắp xếp, hãy giới hạn chúng trong danh sách tên cột được phép rồi xây dựng SQL từ các hằng số đã kiểm soát.

## 4. Bước 3 — Thực thi câu SQL

Không phải câu SQL nào cũng trả về `ResultSet`. Chọn phương thức theo kết quả mong muốn:

| Phương thức | Thường dùng cho | Giá trị trả về |
| --- | --- | --- |
| `executeQuery()` | `SELECT` hoặc câu SQL trả một tập kết quả | `ResultSet` |
| `executeUpdate()` | `INSERT`, `UPDATE`, `DELETE`; đôi khi DDL | `int`: số dòng tác động (DDL có thể trả `0`) |
| `execute()` | Trường hợp tổng quát khi có thể có kết quả, số dòng tác động hoặc nhiều kết quả | `boolean`: `true` khi kết quả đầu tiên là `ResultSet` |

Ví dụ `UPDATE`:

~~~java
String sql = "UPDATE product SET stock_quantity = ? WHERE id = ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setInt(1, 12);
    ps.setLong(2, 42L);

    int affectedRows = ps.executeUpdate();
    if (affectedRows != 1) {
        throw new SQLException("Không tìm thấy đúng một sản phẩm cần cập nhật");
    }
}
~~~

`executeUpdate()` **không trả về `ResultSet`** trong mô hình sử dụng thông thường; nó trả số dòng mà câu lệnh tác động. Khi cần đọc các hàng của `SELECT`, dùng `executeQuery()` rồi duyệt kết quả.

## 5. Bước 4 — Đọc và ánh xạ dữ liệu từ ResultSet

Ngay sau `executeQuery()`, con trỏ của `ResultSet` nằm **trước dòng đầu tiên**. Cần gọi `next()` trước khi dùng `getXxx()` để đọc các cột:

~~~java
try (ResultSet rs = ps.executeQuery()) {
    while (rs.next()) {
        long id = rs.getLong("id");
        String name = rs.getString("name");
        BigDecimal price = rs.getBigDecimal("price");
        System.out.println(id + " | " + name + " | " + price);
    }
}
~~~

Mỗi lần gọi `next()` sẽ cố di chuyển tới dòng tiếp theo; phương thức trả `false` khi hết dữ liệu. Với truy vấn chỉ cần **một** sản phẩm, dùng `if (rs.next())` và xác định rõ cách xử lý khi không tìm thấy dòng nào. Với danh sách, dùng `while (rs.next())`.

Bạn có thể đọc cột theo tên/nhãn (`rs.getString("name")`) hoặc theo vị trí (`rs.getString(2)`, bắt đầu từ **1**). Đọc theo tên thường dễ hiểu và ít bị ảnh hưởng khi vị trí cột thay đổi, miễn là tên/nhãn cột trong kết quả không mơ hồ. Truy vấn có nhiều cột trùng tên nên dùng alias rõ ràng.

### SQL NULL và getter của kiểu nguyên thủy

Các getter kiểu đối tượng như `getString()` hoặc `getBigDecimal()` có thể trả `null` khi cột chứa SQL `NULL`. Trái lại, `getInt()`, `getLong()` và một số getter kiểu nguyên thủy trả giá trị mặc định (`0`, `false`...) nếu SQL là `NULL`, nên cần gọi `wasNull()` **ngay sau getter đó** để phân biệt:

~~~java
int discountPercent = rs.getInt("discount_percent");
Integer discount = rs.wasNull() ? null : discountPercent;
~~~

`wasNull()` kiểm tra giá trị của **lần đọc cột gần nhất**, không phải kiểm tra mọi cột của dòng. Vì vậy hãy dùng ngay sau `getInt` tương ứng.

### ResultSet có phải toàn bộ dữ liệu đã ở trong bộ nhớ?

Không nhất thiết. `ResultSet` là giao diện để đọc kết quả; tùy driver, DBMS, chế độ cursor và cấu hình fetch, dữ liệu có thể được tải theo lô hoặc được bộ đệm. `Statement.setFetchSize(n)` chỉ là **gợi ý** số dòng nên fetch mỗi lần, không bảo đảm streaming thật sự trên mọi driver.

Không nên giữ `ResultSet` mở trong thời gian dài để truyền cho tầng giao diện hoặc trả nó ra khỏi một phương thức đã đóng `Connection`. Hãy chuyển các dòng cần thiết thành đối tượng Java trong phạm vi tài nguyên còn mở; với tập dữ liệu lớn, nghiên cứu phân trang hoặc cơ chế streaming riêng của driver.

## 6. Ví dụ hoàn chỉnh: đọc một sản phẩm theo ID

Giả sử cơ sở dữ liệu có bảng:

~~~sql
CREATE TABLE product (
    id             BIGINT PRIMARY KEY,
    name           VARCHAR(200) NOT NULL,
    price          DECIMAL(12, 2) NOT NULL,
    stock_quantity INTEGER NOT NULL
);

INSERT INTO product (id, name, price, stock_quantity)
VALUES (42, 'Bàn phím cơ', 890000.00, 8);
~~~

Phương thức sau minh họa trọn vẹn **lấy Connection → tạo PreparedStatement → gán tham số → thực thi → duyệt ResultSet → ánh xạ dữ liệu → giải phóng tài nguyên**. Mã sử dụng Java 17 trở lên để định nghĩa `record`; có thể thay record bằng POJO trong phiên bản Java cũ.

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class ProductRepository {
    private final DataSource dataSource;

    public ProductRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public record Product(
            long id,
            String name,
            BigDecimal price,
            int stockQuantity) {
    }

    public Product findById(long productId) throws SQLException {
        String sql = """
                SELECT id, name, price, stock_quantity
                FROM product
                WHERE id = ?
                """;

        // 1. Lấy Connection; 2. Tạo PreparedStatement.
        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {

            // 3. Gán giá trị cho placeholder đầu tiên.
            ps.setLong(1, productId);

            // 4. Thực thi SQL; 5. Nhận ResultSet.
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return null; // Không có sản phẩm ứng với ID.
                }

                // 6. Chuyển một hàng thành đối tượng Java.
                return new Product(
                        rs.getLong("id"),
                        rs.getString("name"),
                        rs.getBigDecimal("price"),
                        rs.getInt("stock_quantity"));
            } // 7a. Đóng ResultSet trước.
        } // 7b. Đóng PreparedStatement, rồi Connection.
    }
}
~~~

Sử dụng repository:

~~~java
ProductRepository repository = new ProductRepository(dataSource);
ProductRepository.Product product = repository.findById(42L);

if (product == null) {
    System.out.println("Không tìm thấy sản phẩm");
} else {
    System.out.println(product.name() + " - " + product.price());
}
~~~

Ví dụ giả định `dataSource` đã được cấu hình và bảng `product` có dữ liệu. Không đưa username/password thật trực tiếp vào mã nguồn; cấu hình kết nối thường được nạp từ hệ thống quản lý bí mật hoặc môi trường triển khai.

**Lưu ý về vị trí `return`:** dù phương thức trả về ngay trong khối `try`, Java vẫn chạy thao tác `close()` cho các tài nguyên trước khi trả kết quả. Đối tượng `Product` đã được tạo trong bộ nhớ nên có thể dùng an toàn sau khi `ResultSet` và `Connection` đóng.

## 7. Giải phóng tài nguyên bằng try-with-resources

JDBC thường gắn với tài nguyên giới hạn: phiên DBMS, socket mạng, cursor, bộ đệm, statement handle và vị trí trong connection pool. Bỏ quên đóng tài nguyên có thể dẫn tới tình trạng **hết kết nối khả dụng**, tăng bộ nhớ dùng hoặc để giao dịch giữ khóa quá lâu.

`try-with-resources` là cơ chế Java tự gọi `close()` với đối tượng triển khai `AutoCloseable`. `Connection`, `Statement` và `ResultSet` đều hỗ trợ cơ chế này.

~~~java
try (Connection c = dataSource.getConnection();
     PreparedStatement ps = c.prepareStatement(sql);
     ResultSet rs = ps.executeQuery()) {
    while (rs.next()) {
        // Đọc dữ liệu.
    }
}
// Thứ tự đóng: rs -> ps -> c (ngược thứ tự khởi tạo).
~~~

Trong ví dụ rút gọn, truy vấn không có placeholder vì `executeQuery()` được gọi ngay trong phần khởi tạo `ResultSet`. Với câu SQL có tham số, hãy gán bằng `setXxx()` trước khi gọi `executeQuery()`; do đó cú pháp `try` lồng nhau ở mục 6 thường dễ đọc hơn.

**Thứ tự và quyền sở hữu cần phân biệt:**

| Tình huống | Ai đóng tài nguyên? |
| --- | --- |
| Repository tự gọi `dataSource.getConnection()` | Repository đóng `ResultSet`, `PreparedStatement` và `Connection` đã mượn. |
| Service tạo `Connection` rồi truyền xuống nhiều DAO | Service đóng `Connection` sau khi các DAO hoàn thành; mỗi DAO đóng statement/result set do mình tạo. |
| `ResultSet` được tạo từ `PreparedStatement` | Thường đóng `ResultSet` trước khi đóng `PreparedStatement`. |
| Kết nối thuộc connection pool | `close()` thường hoàn trả đối tượng logic về pool; vẫn phải gọi đúng hạn. |

Một số driver tự đóng `ResultSet` khi đóng `Statement` liên quan, và đóng `Connection` cũng thường giải phóng tài nguyên con; **không nên chỉ dựa vào đóng tài nguyên cha** để che giấu việc quản lý sai vòng đời. Việc đóng tường minh từng tài nguyên giúp mã có thứ tự rõ ràng và dễ phát hiện lỗi.

Khi phần thân `try` và việc đóng tài nguyên cùng phát sinh ngoại lệ, Java giữ ngoại lệ chính và ghi các lỗi đóng ở `getSuppressed()`. Đây là một ưu điểm của `try-with-resources` so với nhiều khối `finally` thủ công.

## 8. Xử lý SQLException và giao dịch trong luồng JDBC

Mở kết nối, chuẩn bị SQL, gán tham số, thực thi và đọc kết quả đều có thể ném `SQLException`. Ngoại lệ cung cấp thông tin kỹ thuật như:

- `getMessage()`: mô tả lỗi do driver cung cấp.
- `getSQLState()`: mã SQLState để phân loại nhóm lỗi theo chuẩn/triển khai.
- `getErrorCode()`: mã lỗi riêng của nhà cung cấp DBMS.
- `getNextException()`: chuỗi ngoại lệ JDBC bổ sung, nếu có.

Ví dụ chặn lỗi ở ranh giới ứng dụng:

~~~java
try {
    ProductRepository.Product result = repository.findById(42L);
    // Sử dụng kết quả.
} catch (SQLException error) {
    System.err.println("SQLState: " + error.getSQLState());
    System.err.println("Mã lỗi DBMS: " + error.getErrorCode());
    // Ghi log theo chính sách ứng dụng rồi thông báo phù hợp cho người dùng.
    throw error;
}
~~~

Không nên tiết lộ toàn bộ thông tin kết nối, truy vấn có dữ liệu nhạy cảm hoặc thông báo lỗi hệ thống cho người dùng cuối. Ngoài ra, không nuốt `SQLException` rồi trả danh sách trống: khi đó tầng gọi khó phân biệt “không có dữ liệu” với “đã lỗi truy vấn”.

### Auto-commit liên quan gì tới luồng xử lý?

Theo mặc định, các kết nối JDBC mới thường bật `autoCommit=true`: mỗi câu lệnh SQL sẽ được commit khi câu lệnh **hoàn tất** theo ngữ nghĩa JDBC. Với truy vấn trả `ResultSet`, việc hoàn tất có thể gắn với việc tiêu thụ hoặc đóng kết quả. Đối với thao tác ghi nhiều bước cần cùng thành công hoặc cùng thất bại, phải xác định ranh giới giao dịch thủ công hoặc dùng transaction manager.

Ví dụ đơn giản cho **hai câu lệnh cập nhật trong một giao dịch**, trên cùng `Connection`:

~~~java
try (Connection c = dataSource.getConnection()) {
    c.setAutoCommit(false);
    try {
        // Thực thi SQL A bằng PreparedStatement tạo từ c.
        // Thực thi SQL B bằng PreparedStatement tạo từ c.
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
~~~

Đây là phác thảo để minh họa vai trò của kết nối; trong mã dùng connection pool còn cần quản lý việc khôi phục trạng thái (`autoCommit`, isolation...) và xử lý trường hợp `rollback` thất bại theo hợp đồng của pool. **Không dựa vào `Connection.close()` như cách thay thế `commit()/rollback()`**, vì trạng thái giao dịch còn mở khi đóng có thể được xử lý khác nhau theo driver/pool.

## 9. Các lỗi thường gặp khi ghép các bước

| Hiện tượng | Nguyên nhân có thể xảy ra | Cách khắc phục |
| --- | --- | --- |
| `SQLException: No suitable driver` | Chưa có driver phù hợp hoặc JDBC URL sai | Kiểm tra dependency driver, JDBC URL và cách nạp driver. |
| `SQLException` khi đọc cột | Tên cột/alias sai hoặc dùng getter không tương thích | Kiểm tra cột thực tế của `SELECT`, dùng alias rõ ràng. |
| Đọc kết quả trước khi gọi `next()` | Con trỏ `ResultSet` chưa nằm trên dòng hợp lệ | Dùng `if (rs.next())` hoặc `while (rs.next())`. |
| Kết quả có `0` dù cột nullable | Dùng `getInt()` cho SQL `NULL` | Gọi `wasNull()` ngay sau getter, hoặc dùng kiểu nullable phù hợp. |
| Đọc dữ liệu sau khi phương thức đã trả về | Trả `ResultSet` khi statement/connection đã đóng | Ánh xạ sang DTO/POJO khi tài nguyên còn mở. |
| Pool hết kết nối | Quên đóng `Connection` hoặc giữ kết nối quá lâu | Dùng `try-with-resources`, giới hạn phạm vi thao tác, điều tra leak. |
| `executeQuery()` dùng cho `UPDATE` | Chọn sai API thực thi | Dùng `executeUpdate()` để nhận số dòng tác động. |
| Lỗi tham số `?` | Đánh số từ 0, thiếu tham số hoặc sai kiểu | Đánh số từ 1, gán đủ tham số và dùng `setXxx` đúng kiểu. |
| Giao dịch bị commit/rollback ngoài ý muốn | Nhiều DAO tự thay đổi trạng thái hoặc đóng cùng một `Connection` | Xác định rõ tầng sở hữu giao dịch và vòng đời kết nối. |
| Truy vấn kéo dài hoặc tải quá nhiều dữ liệu | Không giới hạn tập kết quả; phụ thuộc cách fetch của driver | Chọn cột cần thiết, phân trang, cân nhắc query timeout/fetch size và lập chỉ mục. |

Khi cần giới hạn thời gian thực thi, có thể gọi `ps.setQueryTimeout(seconds)`, nhưng mức độ hỗ trợ/cách hủy truy vấn có thể khác theo driver. Với dữ liệu lớn, `setFetchSize(...)` là một gợi ý; hãy kiểm tra hành vi thực tế của DBMS thay vì mặc định tất cả driver đều streaming.

## 10. Bài thực hành: đọc nhiều sản phẩm và đóng tài nguyên đúng cách

Từ bảng `product` ở mục 6, hãy viết phương thức `findWithMinimumPrice(DataSource dataSource, BigDecimal minimum)` trả danh sách sản phẩm có giá không thấp hơn `minimum`. Các yêu cầu:

1. Lấy một `Connection` từ `DataSource`, tạo `PreparedStatement` với điều kiện `price >= ?`.
2. Gán `minimum` bằng `setBigDecimal(1, minimum)`.
3. Gọi `executeQuery()`, dùng `while (rs.next())` để duyệt toàn bộ dòng.
4. Ánh xạ từng dòng thành `Product`, thêm vào `List<Product>`; không trả trực tiếp `ResultSet`.
5. Dùng `try-with-resources` để đảm bảo `ResultSet`, `PreparedStatement` và `Connection` được đóng ngay cả khi có ngoại lệ.

Một cách triển khai phần trọng tâm:

~~~java
public List<Product> findWithMinimumPrice(BigDecimal minimum)
        throws SQLException {
    String sql = "SELECT id, name, price, stock_quantity "
               + "FROM product WHERE price >= ? ORDER BY id";
    List<Product> products = new ArrayList<>();

    try (Connection c = dataSource.getConnection();
         PreparedStatement ps = c.prepareStatement(sql)) {
        ps.setBigDecimal(1, minimum);

        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                products.add(new Product(
                        rs.getLong("id"),
                        rs.getString("name"),
                        rs.getBigDecimal("price"),
                        rs.getInt("stock_quantity")));
            }
        }
    }
    return products;
}
~~~

Đoạn này được đặt **bên trong `ProductRepository`** ở mục 6 và cần bổ sung import `java.util.List` cùng `java.util.ArrayList`. Khi không có sản phẩm phù hợp, phương thức trả danh sách rỗng; khi SQL xảy ra lỗi, nó ném `SQLException` để tầng gọi xử lý.

Bạn có thể tự kiểm tra bằng cách chủ động tạo lỗi SQL (ví dụ đổi tên cột thành tên không tồn tại), quan sát ngoại lệ, rồi xác nhận connection pool vẫn nhận lại kết nối. Nếu thêm phần ghi dữ liệu nhiều bước, hãy bổ sung xử lý giao dịch trước khi trả kết nối.

## 11. Ghi nhớ trình tự thực thi

Mỗi khi viết mã JDBC, hãy tự trả lời:

- **Kết nối được lấy từ đâu?** `DriverManager` hay `DataSource`, và ai sở hữu quyền đóng nó?
- **Câu SQL và tham số là gì?** Dùng `PreparedStatement`, gán đúng số thứ tự và kiểu của `?`.
- **Đang đọc hay ghi?** Dùng `executeQuery()` và `ResultSet` cho tập kết quả, `executeUpdate()` cho số dòng được tác động.
- **Đọc kết quả ra sao?** Gọi `next()` trước các getter, xử lý trường hợp không có dòng, SQL `NULL` và ánh xạ dữ liệu vào đối tượng Java.
- **Tài nguyên được giải phóng khi nào?** Đóng `ResultSet`, `Statement`, `Connection` theo đúng quyền sở hữu, ưu tiên `try-with-resources`.
- **Nếu lỗi hoặc có nhiều thao tác ghi thì sao?** Để ngoại lệ được xử lý minh bạch; đặt `commit/rollback` trong ranh giới giao dịch phù hợp.

**Cốt lõi của luồng JDBC:** *lấy `Connection` → chuẩn bị và truyền tham số qua `PreparedStatement` → thực thi SQL → duyệt `ResultSet` nếu có → đóng tài nguyên đúng thứ tự*. Hiểu rõ từng bước giúp viết những phương thức truy cập dữ liệu an toàn về vòng đời tài nguyên và dễ mở rộng lên DAO, repository hoặc framework giao dịch sau này.
