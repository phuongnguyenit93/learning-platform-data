# Các thuật ngữ cốt lõi và trình tự học JDBC

**JDBC (Java Database Connectivity)** là API tiêu chuẩn của Java để làm việc với cơ sở dữ liệu quan hệ: mở kết nối, gửi câu lệnh SQL, nhận dữ liệu, kiểm soát giao dịch và xử lý lỗi. Khi mới học, người đọc thường gặp nhiều tên gọi gần giống nhau như *driver*, *connection*, *statement*, *result set*, *transaction* và *data source*. Nếu chưa phân biệt vai trò của chúng, rất dễ học API theo kiểu nhớ từng lệnh mà không hiểu một truy vấn đã đi từ chương trình Java tới cơ sở dữ liệu như thế nào.

Bài thuộc chương **Nền tảng** này xây dựng một bản đồ thuật ngữ và lộ trình học có thứ tự. Mục tiêu là giúp bạn đọc mã JDBC, tự viết một thao tác dữ liệu nhỏ và biết cần học tiếp phần nào khi chương trình gặp vấn đề về độ đúng, bảo mật hoặc hiệu năng.

## 1. Nắm mô hình tổng thể trước khi nhớ tên lớp

Một ứng dụng Java có thể cần tìm khách hàng, thêm đơn hàng hoặc chuyển tiền giữa hai tài khoản. Dữ liệu được quản lý bởi **DBMS (Database Management System, hệ quản trị cơ sở dữ liệu)**, ví dụ PostgreSQL, MySQL hoặc một hệ quản trị quan hệ khác. Java không trực tiếp sửa tệp dữ liệu của DBMS; ứng dụng gửi yêu cầu qua giao thức mà DBMS hỗ trợ.

JDBC cung cấp **giao diện lập trình chung** để ứng dụng không phải tự hiện thực giao thức của từng DBMS. Nhà cung cấp driver viết một thư viện cụ thể để kết nối JDBC với hệ quản trị tương ứng.

~~~mermaid
flowchart TD
    A["Mã Java: service / repository"] --> B["JDBC API: java.sql / javax.sql"]
    B --> C["JDBC driver tương ứng DBMS"]
    C --> D["Kết nối và giao thức DBMS"]
    D --> E[("Cơ sở dữ liệu quan hệ")]
    E --> D
    D --> C
    C --> B
    B --> A
~~~

Trong một thao tác đọc dữ liệu, luồng điển hình là:

1. Ứng dụng có một kết nối tới DBMS, thường lấy qua `DataSource` hoặc `DriverManager`.
2. Ứng dụng tạo `PreparedStatement` cho SQL và gắn các giá trị cần truy vấn.
3. Driver chuyển yêu cầu theo giao thức DBMS.
4. DBMS kiểm tra quyền, phân tích và thực thi SQL, rồi trả kết quả.
5. Ứng dụng đọc từng hàng qua `ResultSet` và chuyển dữ liệu sang đối tượng Java.
6. Tài nguyên JDBC được đóng hoặc kết nối được trả về pool để dùng lại.

Điểm quan trọng: **JDBC là lớp giao tiếp; SQL quyết định dữ liệu cần đọc/sửa; DBMS thực hiện lưu trữ và đảm bảo các quy tắc dữ liệu**.

## 2. Bộ thuật ngữ về dữ liệu quan hệ

Trước khi gọi JDBC, cần biết mình đang truy cập đối tượng gì trong DBMS.

| Thuật ngữ | Ý nghĩa | Ví dụ trong ứng dụng bán hàng |
| --- | --- | --- |
| **Database** (cơ sở dữ liệu) | Tập dữ liệu được DBMS quản lý | Dữ liệu của hệ thống đặt hàng |
| **Schema** | Không gian/định nghĩa cấu trúc đối tượng trong DB; cách tổ chức tùy DBMS | Schema `sales` chứa bảng đơn hàng |
| **Table** (bảng) | Tập hàng có các cột đã định nghĩa | `customer`, `orders` |
| **Row / Record** (hàng / bản ghi) | Một phần tử dữ liệu trong bảng | Một khách hàng có `id = 42` |
| **Column** (cột) | Thuộc tính có kiểu dữ liệu | `customer_id`, `email`, `created_at` |
| **SQL data type** | Kiểu dữ liệu cột mà DBMS hiểu | `BIGINT`, `VARCHAR`, `DECIMAL`, `DATE` |
| **Primary key (PK)** | Khóa chính xác định duy nhất một hàng | `customer.id` |
| **Foreign key (FK)** | Ràng buộc tham chiếu tới khóa ở bảng khác | `orders.customer_id` tham chiếu `customer.id` |
| **Constraint** | Quy tắc DB bắt buộc dữ liệu thỏa mãn | `NOT NULL`, `UNIQUE`, `CHECK`, FK |
| **Index** | Cấu trúc hỗ trợ tìm kiếm/sắp xếp trong một số trường hợp | Chỉ mục trên `customer.email` |

Một lược đồ minh họa:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(200) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    total_amount DECIMAL(14, 2) NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customer(id)
);
~~~

Đây là SQL minh họa: cách tự sinh khóa, tên kiểu, câu lệnh tạo chỉ mục và một số ràng buộc có thể khác giữa các DBMS. Người học nên kiểm tra cú pháp theo hệ quản trị đang sử dụng.

### SQL và CRUD

**SQL (Structured Query Language)** là ngôn ngữ truy vấn và thao tác cơ sở dữ liệu quan hệ. Trong giai đoạn nhập môn, cần phân biệt hai nhóm thực hành:

| Hành động CRUD | SQL thông dụng | Điều cần hiểu |
| --- | --- | --- |
| **Create** (tạo hàng dữ liệu) | `INSERT INTO ... VALUES ...` | Thêm hàng, kiểm tra khóa/ràng buộc |
| **Read** (đọc) | `SELECT ... FROM ... WHERE ...` | Lọc và lấy cột cần thiết |
| **Update** (cập nhật) | `UPDATE ... SET ... WHERE ...` | Thay đổi hàng thỏa điều kiện |
| **Delete** (xóa) | `DELETE FROM ... WHERE ...` | Xóa hàng thỏa điều kiện |

CRUD là cách nói về thao tác dữ liệu, **không phải** tên bốn lớp JDBC. Ngoài SQL thao tác dữ liệu, bạn còn gặp **DDL** (*Data Definition Language* như `CREATE TABLE`, `ALTER TABLE`) để thay đổi cấu trúc. Tên nhóm thuật ngữ là cách phân loại để học; các DBMS có thể khác nhau về việc DDL tham gia transaction như thế nào.

## 3. Bộ thuật ngữ về JDBC và trách nhiệm của từng đối tượng

Các lớp và interface quan trọng nằm chủ yếu trong `java.sql`; `DataSource` nằm trong `javax.sql`.

| Thành phần | Vai trò chính | Khi nào gặp? |
| --- | --- | --- |
| **JDBC API** | Hợp đồng Java dùng để tương tác với dữ liệu quan hệ | Mọi chương trình dùng JDBC |
| **JDBC driver** | Thư viện hiện thực giao tiếp JDBC với DBMS cụ thể | Cấu hình dependency khi bắt đầu dự án |
| **JDBC URL** | Chuỗi xác định kiểu driver và vị trí cơ sở dữ liệu | `jdbc:postgresql://localhost:5432/shop` |
| **`DriverManager`** | Tìm driver phù hợp và tạo kết nối | Ví dụ nhập môn, công cụ nhỏ |
| **`DataSource`** | Trừu tượng cung cấp kết nối; thường kết hợp pool | Ứng dụng dịch vụ, ứng dụng web |
| **`Connection`** | Một phiên/kết nối logic tới DBMS, gắn với giao dịch | Trước khi chạy SQL |
| **`Statement`** | Thực thi chuỗi SQL được cung cấp | SQL cố định; cần thận trọng với nối chuỗi |
| **`PreparedStatement`** | Thực thi SQL có các vị trí tham số `?` | Hầu hết truy vấn có đầu vào |
| **`CallableStatement`** | Gọi stored procedure theo cú pháp driver/DBMS hỗ trợ | Ứng dụng dùng procedure |
| **`ResultSet`** | Tập kết quả đọc theo con trỏ từ câu `SELECT` | Khi duyệt các hàng kết quả |
| **`SQLException`** | Ngoại lệ cho lỗi JDBC/SQL | Khi kết nối/truy vấn có vấn đề |
| **`DatabaseMetaData`** | Thông tin về DBMS/driver, bảng, khả năng hỗ trợ | Công cụ kiểm tra hoặc lập trình động |
| **`ResultSetMetaData`** | Thông tin các cột của kết quả truy vấn | Đọc danh sách cột/tên/kiểu |

Trong bảng, **driver** là thư viện được thêm vào runtime của ứng dụng; **Connection**, **PreparedStatement** và **ResultSet** là những đối tượng mà mã Java làm việc khi đã chạy.

### Phân biệt `DriverManager`, `DataSource` và connection pool

- `DriverManager.getConnection(...)` yêu cầu tạo kết nối dựa trên URL và thông tin xác thực. Phù hợp để học cơ chế JDBC ở quy mô nhỏ.
- `DataSource.getConnection()` lấy kết nối qua một đối tượng đã được cấu hình. Mã ứng dụng phụ thuộc vào interface `DataSource` thay vì rải URL và credential tại nhiều nơi.
- **Connection pool** là cơ chế giữ và tái sử dụng kết nối để giảm chi phí tạo kết nối mới. Nhiều `DataSource` triển khai pool, nhưng **không phải mọi `DataSource` đều tự động có pool**.

Một `Connection` lấy từ pool thường được **trả lại pool khi gọi `close()`**, thay vì đóng kết nối vật lý ngay. Mã ứng dụng vẫn có trách nhiệm đóng theo hợp đồng để không làm cạn pool.

## 4. Các phương thức thực thi SQL thường bị nhầm

`PreparedStatement` kế thừa các khả năng từ `Statement`, nhưng các phương thức thực thi có ý nghĩa khác nhau.

| Phương thức | Mục đích chính | Kết quả |
| --- | --- | --- |
| `executeQuery()` | Truy vấn trả một `ResultSet`, thường là `SELECT` | `ResultSet` |
| `executeUpdate()` | `INSERT`, `UPDATE`, `DELETE` và một số lệnh DDL | Số hàng bị ảnh hưởng hoặc giá trị theo hợp đồng JDBC |
| `execute()` | SQL có thể trả result set, update count hoặc nhiều kết quả | `boolean` chỉ ra kết quả đầu tiên có phải `ResultSet` không |
| `addBatch()` / `executeBatch()` | Gom nhiều lần thao tác để thực thi batch | Mảng kết quả cho các lệnh |

Không nên hiểu `executeUpdate()` luôn trả số hàng bằng 1, hoặc `execute() == false` luôn có nghĩa truy vấn thất bại. Với `execute()`, `false` có thể có nghĩa kết quả đầu tiên là update count hoặc không có kết quả; phải kiểm tra `getUpdateCount()`/`getResultSet()` khi dùng API này.

Khi bắt đầu, hãy sử dụng `executeQuery()` cho truy vấn đọc và `executeUpdate()` cho thao tác cập nhật; chỉ học `execute()` khi thực sự gặp câu lệnh có nhiều kiểu kết quả.

## 5. Chu kỳ sống tối thiểu của một thao tác JDBC

Hãy hình dung ứng dụng cần tìm tên khách hàng theo ID. Đầu vào đến từ ứng dụng, được gắn vào SQL và kết quả trả về từ DBMS.

~~~mermaid
sequenceDiagram
    participant App as Java application
    participant JDBC as JDBC driver
    participant DB as Database server
    App->>JDBC: getConnection(...)
    JDBC->>DB: Mở kết nối và xác thực
    DB-->>JDBC: Kết nối sẵn sàng
    JDBC-->>App: Connection
    App->>JDBC: prepareStatement(SQL có ?)
    App->>JDBC: setLong(1, customerId)
    App->>JDBC: executeQuery()
    JDBC->>DB: Thực thi truy vấn với tham số
    DB-->>JDBC: Các hàng kết quả
    JDBC-->>App: ResultSet
    App->>App: while (rs.next()) / rs.getString(...)
    App->>JDBC: close() tài nguyên
~~~

### Ví dụ Java đầy đủ

Ví dụ dưới đây giả định một bảng `customer(id, full_name, email)` đã tồn tại, driver của DBMS đã có trong classpath/runtime và các biến môi trường `JDBC_URL`, `DB_USER`, `DB_PASSWORD` đã được cấu hình.

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public class CustomerLookup {
    public static void main(String[] args) throws SQLException {
        String url = System.getenv("JDBC_URL");
        String user = System.getenv("DB_USER");
        String password = System.getenv("DB_PASSWORD");

        String sql = """
                SELECT id, full_name, email
                FROM customer
                WHERE id = ?
                """;

        try (Connection connection =
                     DriverManager.getConnection(url, user, password);
             PreparedStatement ps = connection.prepareStatement(sql)) {

            ps.setLong(1, 42L);

            try (ResultSet rs = ps.executeQuery()) {
                if (rs.next()) {
                    long id = rs.getLong("id");
                    String name = rs.getString("full_name");
                    String email = rs.getString("email");
                    System.out.println(id + " - " + name + " - " + email);
                } else {
                    System.out.println("Không tìm thấy khách hàng");
                }
            }
        }
    }
}
~~~

Ví dụ dùng **text block** (`"""`) của Java 15 trở lên; có thể thay bằng chuỗi SQL thông thường nếu dùng Java cũ hơn. Trong ứng dụng thực tế, hãy kiểm tra cấu hình đầu vào trước khi mở kết nối và xử lý `SQLException` tại ranh giới phù hợp. Không nhúng password thật vào mã nguồn.

Từ đoạn này cần hiểu những chi tiết nhỏ nhưng rất hay gặp:

1. `Connection` gắn với một phiên làm việc DB và phải được đóng đúng lúc.
2. `?` là vị trí tham số; `ps.setLong(1, 42L)` đặt giá trị **đầu tiên**. Chỉ số tham số JDBC bắt đầu từ **1**.
3. `ResultSet` ban đầu đứng **trước hàng đầu tiên**. Gọi `rs.next()` để chuyển tới hàng; hàm trả `false` nếu không còn hàng.
4. `getLong("id")` và `getString("full_name")` đọc cột của hàng hiện tại; tên cột phải khớp kết quả SQL.
5. `try-with-resources` tự đóng `ResultSet`, `PreparedStatement` và `Connection` theo thứ tự ngược lúc khai báo/mở tài nguyên.
6. Driver JDBC hiện đại thường được phát hiện qua cơ chế service provider khi dependency có mặt. Việc phải gọi thủ công `Class.forName("...Driver")` là kiến thức hữu ích cho ứng dụng/driver cũ, không phải bước bắt buộc cho mọi ứng dụng hiện đại.

### Vì sao nên dùng `PreparedStatement`?

Khi SQL nhận dữ liệu bên ngoài, hãy truyền dữ liệu bằng các hàm `setString`, `setLong`, `setObject`… Điều này giữ ranh giới giữa **cú pháp truy vấn** và **giá trị đầu vào**, tránh SQL injection kiểu nối chuỗi.

~~~java
// Không an toàn: đầu vào trở thành một phần câu SQL.
String unsafe = "SELECT id FROM customer WHERE email = '" + email + "'";

// An toàn cho giá trị email: SQL giữ nguyên cấu trúc.
String safe = "SELECT id FROM customer WHERE email = ?";
try (PreparedStatement ps = connection.prepareStatement(safe)) {
    ps.setString(1, email);
    try (ResultSet rs = ps.executeQuery()) {
        // Xử lý dữ liệu...
    }
}
~~~

Tham số `?` chỉ đại diện cho **giá trị**, không thay thế tên bảng, tên cột, từ khóa `ASC`/`DESC` hoặc cả đoạn SQL. Khi phần cấu trúc phải thay đổi, ánh xạ lựa chọn của người dùng sang **danh sách tên/cú pháp đã định nghĩa sẵn**, rồi vẫn bind mọi giá trị còn lại.

## 6. Phân biệt kiểu dữ liệu Java và SQL

DBMS có hệ kiểu riêng; mã Java cũng có hệ kiểu riêng. JDBC chịu trách nhiệm giúp truyền/nhận giá trị qua hai phía, nhưng ứng dụng phải chọn kiểu có ý nghĩa phù hợp.

| Ý nghĩa dữ liệu | Kiểu SQL thường gặp | Kiểu Java thường dùng | Lưu ý |
| --- | --- | --- | --- |
| Mã định danh số nguyên lớn | `BIGINT` | `long` / `Long` | Kiểm tra miền giá trị và NULL |
| Tên, email | `VARCHAR` | `String` | Kiểm tra độ dài và mã hóa |
| Giá tiền/giá trị thập phân chính xác | `DECIMAL(p,s)` | `BigDecimal` | Tránh dùng `double` khi cần số thập phân chính xác |
| Cờ đúng/sai | `BOOLEAN` nếu DB hỗ trợ | `boolean` / `Boolean` | Cách lưu boolean khác nhau theo DB |
| Ngày lịch | `DATE` | `LocalDate` | Không tự mang múi giờ |
| Giờ trên đồng hồ | `TIME` | `LocalTime` | Không tự xác định thời điểm |
| Ngày giờ không có múi giờ | `TIMESTAMP` | `LocalDateTime` | Phải có quy ước nếu muốn diễn giải như mốc UTC |
| Mốc thời gian có offset theo SQL | `TIMESTAMP WITH TIME ZONE` nếu DB hỗ trợ | `OffsetDateTime` | Đổi sang `Instant` theo nghiệp vụ |

Các kiểu `java.time` tiêu chuẩn được JDBC 4.2 hỗ trợ ở những ánh xạ nhất định, nhưng khả năng cụ thể cần kiểm tra với phiên bản driver và DBMS đang dùng. Ví dụ:

~~~java
import java.math.BigDecimal;
import java.time.LocalDate;

String sql = """
        INSERT INTO product (id, product_name, price, available_from)
        VALUES (?, ?, ?, ?)
        """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 101L);
    ps.setString(2, "Sổ tay");
    ps.setBigDecimal(3, new BigDecimal("25.50"));
    ps.setObject(4, LocalDate.of(2026, 11, 16));
    ps.executeUpdate();
}
~~~

Điều cần học không chỉ là tên hàm `setXxx`: bạn còn phải phân biệt `NULL` với giá trị mặc định, độ chính xác của số/giờ, và cách driver chuyển đổi dữ liệu. Đặc biệt, gọi `rs.getInt(...)`/`rs.getLong(...)` trên cột SQL `NULL` có thể trả về giá trị nguyên thủy `0`; sử dụng `rs.wasNull()` nếu cần phân biệt null, hoặc dùng ánh xạ đối tượng phù hợp.

## 7. Giao dịch, tự động commit và tính nhất quán

**Transaction (giao dịch)** là một đơn vị gồm một hoặc nhiều thao tác được xử lý theo ranh giới commit/rollback. Trong JDBC, thông thường `Connection` mặc định ở chế độ **auto-commit**: mỗi câu SQL hoàn tất sẽ được commit theo quy tắc của driver/DBMS.

Khi nghiệp vụ yêu cầu nhiều câu lệnh **cùng thành công hoặc cùng thất bại**, hãy tắt auto-commit trong phạm vi giao dịch:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public static void transfer(
        Connection connection,
        long fromAccount,
        long toAccount,
        java.math.BigDecimal amount
) throws SQLException {
    if (amount.signum() <= 0 || fromAccount == toAccount) {
        throw new IllegalArgumentException("Giao dịch không hợp lệ");
    }

    boolean originalAutoCommit = connection.getAutoCommit();
    connection.setAutoCommit(false);

    try {
        String debitSql = """
                UPDATE account
                SET balance = balance - ?
                WHERE id = ? AND balance >= ?
                """;
        try (PreparedStatement debit = connection.prepareStatement(debitSql)) {
            debit.setBigDecimal(1, amount);
            debit.setLong(2, fromAccount);
            debit.setBigDecimal(3, amount);
            if (debit.executeUpdate() != 1) {
                throw new SQLException("Tài khoản nguồn không đủ tiền hoặc không tồn tại");
            }
        }

        String creditSql = """
                UPDATE account
                SET balance = balance + ?
                WHERE id = ?
                """;
        try (PreparedStatement credit = connection.prepareStatement(creditSql)) {
            credit.setBigDecimal(1, amount);
            credit.setLong(2, toAccount);
            if (credit.executeUpdate() != 1) {
                throw new SQLException("Tài khoản đích không tồn tại");
            }
        }

        connection.commit();
    } catch (SQLException | RuntimeException failure) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
        throw failure;
    } finally {
        connection.setAutoCommit(originalAutoCommit);
    }
}
~~~

Ví dụ minh họa cách tổ chức hai thay đổi trong một transaction; để dùng thực tế còn phải xác định đặc tính DBMS, isolation, khóa, deadlock, thứ tự thao tác, ràng buộc và chiến lược retry. Đặc biệt, nếu lỗi khôi phục `autoCommit` xảy ra, ngoại lệ đó cũng cần được hệ thống giám sát phù hợp.

Các thuật ngữ giao dịch nên học theo thứ tự:

- **Commit:** xác nhận những thay đổi của transaction.
- **Rollback:** hủy thay đổi chưa commit trong transaction hiện tại.
- **ACID:** bốn thuộc tính *Atomicity, Consistency, Isolation, Durability* thường dùng để mô tả giao dịch của DBMS quan hệ.
- **Isolation level:** mức cô lập ảnh hưởng tới những gì transaction có thể quan sát từ giao dịch khác; ví dụ `READ_COMMITTED` hoặc `SERIALIZABLE`.
- **Lock / Deadlock:** cơ chế đồng bộ truy cập cạnh tranh và tình huống các giao dịch chờ nhau.
- **Savepoint:** điểm khôi phục trong transaction nếu DB/driver hỗ trợ.

Chưa cần nhớ mọi hiện tượng cô lập ngay từ đầu. Trước tiên hãy biết **khi nào phải tắt auto-commit, khi nào commit và cách rollback khi lỗi**.

## 8. Xử lý lỗi, tài nguyên và giới hạn hiệu năng

### `SQLException` chứa gì?

Lỗi có thể xuất hiện khi kết nối, chuẩn bị statement, bind sai kiểu, thực thi SQL hoặc đọc `ResultSet`. `SQLException` cung cấp thông điệp, **SQLState** (mã phân loại lỗi theo chuẩn/quy ước), mã lỗi riêng của nhà cung cấp và đôi khi có ngoại lệ liên kết.

~~~java
try (Connection connection =
             DriverManager.getConnection(url, user, password)) {
    // Thực hiện thao tác JDBC.
} catch (SQLException ex) {
    System.err.println("SQLState: " + ex.getSQLState());
    System.err.println("Vendor code: " + ex.getErrorCode());
    // Tại tầng phù hợp: ghi log có kiểm soát và chuyển lỗi sang ngữ cảnh nghiệp vụ.
    throw ex;
}
~~~

Không giả định mọi `SQLState` đều được driver cung cấp hoặc có cùng ý nghĩa ở mọi DBMS; kiểm tra tài liệu khi triển khai chính sách retry. Không trả trực tiếp SQL, chi tiết schema hoặc credential trong phản hồi API cho người dùng cuối.

### `try-with-resources` và kết nối rò rỉ

`Connection`, `Statement`/`PreparedStatement` và `ResultSet` là tài nguyên có vòng đời. Nếu quên đóng, ứng dụng có thể cạn kết nối, giữ cursor/tài nguyên trên DBMS hoặc làm hệ thống chậm dần. Dùng `try-with-resources` làm mặc định và đặt tài nguyên trong phạm vi ngắn nhất hợp lý.

Không nên chia sẻ một `Connection` duy nhất cho mọi request hoặc mọi thread nếu không có hợp đồng rõ ràng về thread-safety; thông thường ứng dụng lấy kết nối từ `DataSource` cho một đơn vị công việc rồi trả lại pool.

### Hiệu năng: những tên gọi nên nhận diện

| Thuật ngữ | Ý nghĩa cần nhớ ở giai đoạn đầu |
| --- | --- |
| **Connection pool** | Tái sử dụng kết nối, giảm chi phí thiết lập |
| **Batch processing** | Gom các thao tác lặp lại, có thể giảm số lượt trao đổi với DB |
| **Fetch size** | Gợi ý lượng hàng được lấy mỗi lượt; cách thực hiện phụ thuộc driver/DB |
| **Query timeout** | Giới hạn thời gian thực thi theo cơ chế JDBC/driver; cần kiểm chứng hành vi |
| **Index / execution plan** | DBMS chọn cách tìm dữ liệu; `EXPLAIN` là công cụ khảo sát tùy hệ quản trị |
| **N+1 query problem** | Nhiều truy vấn nhỏ lặp lại khi duyệt danh sách; cần thiết kế truy vấn hợp lý |

Đừng tối ưu quá sớm bằng cách tạo một câu SQL khổng lồ hoặc giữ kết nối vô hạn. Đầu tiên hãy làm cho kết quả **đúng, an toàn và tài nguyên được đóng**; sau đó đo đạc truy vấn và xem xét batch, pool, index, fetch size.

## 9. Trình tự học JDBC theo từng chặng

Học JDBC hiệu quả nhất khi mỗi giai đoạn có một **kết quả có thể chạy và kiểm chứng**. Các chặng dưới đây đi từ nền tảng quan hệ tới thao tác nhiều bước và vận hành.

| Chặng | Kiến thức cần học | Bài thực hành nhỏ | Tiêu chí đạt |
| --- | --- | --- | --- |
| **1. SQL và mô hình dữ liệu** | Bảng/cột, PK/FK, `SELECT`/`INSERT`/`UPDATE`/`DELETE` | Tạo hai bảng `customer` và `orders`, viết truy vấn lọc | Hiểu các hàng bị ảnh hưởng và ràng buộc |
| **2. Driver và kết nối** | JDBC URL, dependency driver, `DriverManager`, `DataSource` | Kết nối DB và chạy `SELECT 1` nếu DB hỗ trợ | Kết nối được; phân biệt lỗi URL/credential/driver |
| **3. Truy vấn an toàn** | `PreparedStatement`, marker `?`, `ResultSet` | Tìm khách theo ID/email và thêm khách | Không nối dữ liệu request vào SQL; đóng tài nguyên |
| **4. Ánh xạ dữ liệu** | `setXxx`/`getXxx`, SQL `NULL`, `BigDecimal`, `java.time` | Ánh xạ một hàng sang đối tượng Java | Không làm mất ý nghĩa kiểu dữ liệu |
| **5. CRUD hoàn chỉnh** | DAO/repository, khóa sinh, số hàng ảnh hưởng, batch cơ bản | Thêm/sửa/xóa một đơn hàng và kiểm tra kết quả | Rõ đầu vào, đầu ra, trường hợp không tìm thấy |
| **6. Giao dịch** | Auto-commit, commit/rollback, ACID, isolation | Cập nhật hai bảng trong một transaction | Lỗi ở thao tác sau có thể rollback thao tác trước |
| **7. Độ tin cậy và hiệu năng** | `SQLException`, SQLState, timeout, pool, index, fetch size | Chạy nhiều thao tác và đo số truy vấn/thời gian | Không rò rỉ kết nối, có log và kiểm soát lỗi |
| **8. Bảo mật và hoàn thiện** | Phân quyền DB, SQL injection, giới hạn dữ liệu, secret | Rà soát toàn bộ câu SQL động và quyền DB | Giá trị được bind, cú pháp động có whitelist |

Các chặng có thể học xen kẽ khi thực hành, nhưng **kết nối thành công không có nghĩa là đã nắm JDBC**. Bạn cần viết được một truy vấn có tham số, hiểu `ResultSet`, biết đóng tài nguyên và xử lý transaction trước khi chuyển sang tối ưu.

### Chặng 1: SQL phải vững ở những câu đơn giản

Đặt mục tiêu giải thích được:

~~~sql
SELECT c.id, c.full_name, o.total_amount
FROM customer AS c
JOIN orders AS o ON o.customer_id = c.id
WHERE c.id = ?
ORDER BY o.id DESC
~~~

Bạn cần biết `JOIN` kết hợp bảng, `WHERE` lọc hàng, `ORDER BY` sắp xếp và `?` sẽ được JDBC gắn bằng tham số. Nếu chưa phân biệt được các phần này, rất dễ quy lỗi SQL thành lỗi driver.

### Chặng 2–3: Đọc mã JDBC theo thứ tự thực thi

Khi thấy một phương thức truy cập DB, tự hỏi:

1. Kết nối đến từ đâu? `DriverManager` hay `DataSource`?
2. SQL là chuỗi cố định hay có nối chuỗi động?
3. `PreparedStatement` có bao nhiêu dấu `?`? Các giá trị đã bind đủ và đúng thứ tự chưa?
4. Phương thức được gọi là `executeQuery`, `executeUpdate` hay `execute`?
5. `ResultSet` có được duyệt bằng `next()` và đọc đúng kiểu không?
6. Mọi tài nguyên có được đóng ngay cả khi phát sinh lỗi không?

Thực hành tốt là viết một phương thức trả `Optional<Customer>` hoặc kết quả tương đương để thể hiện trường hợp không có bản ghi, thay vì trả đối tượng với các trường giả định.

### Chặng 4–5: Gắn dữ liệu DB với mô hình Java

Ví dụ một đối tượng miền dữ liệu đơn giản:

~~~java
public record Customer(long id, String fullName, String email) {}
~~~

Java `record` yêu cầu Java 16 trở lên. Sau khi đọc thành công hàng từ `ResultSet`, có thể tạo:

~~~java
Customer customer = new Customer(
        rs.getLong("id"),
        rs.getString("full_name"),
        rs.getString("email")
);
~~~

Chọn kiểu trả về mang ý nghĩa nghiệp vụ và quy ước xử lý `NULL` rõ ràng. Không nên để đối tượng `ResultSet` thoát ra ngoài khối đã đóng `Connection`/`Statement` vì việc truy cập kết quả sau khi đóng tài nguyên có thể thất bại.

### Chặng 6–8: Nâng chất lượng mã thực tế

Khi đã làm được CRUD, tạo bài thử có lỗi giữa hai câu `UPDATE` để quan sát rollback. Sau đó thử truy vấn với dữ liệu chứa dấu nháy đơn, chạy nhiều request liên tiếp để phát hiện cạn pool, xem số hàng ảnh hưởng và tìm các câu SQL chậm.

Đối với ứng dụng lớn, có thể tổ chức:

~~~text
HTTP/API layer
    |
Service (quy tắc nghiệp vụ, ranh giới transaction)
    |
Repository / DAO (SQL, tham số, ánh xạ kết quả)
    |
DataSource / JDBC driver
    |
DBMS
~~~

**DAO (Data Access Object)** và **Repository** là cách tổ chức mã truy cập dữ liệu; chúng không phải lớp bắt buộc của JDBC. Framework có thể quản lý connection, transaction hoặc mapper, nhưng bạn vẫn cần hiểu các khái niệm JDBC bên dưới để chẩn đoán lỗi.

## 10. Bảng phân biệt những cặp thuật ngữ thường nhầm

| Dễ nhầm | Phân biệt đúng |
| --- | --- |
| **JDBC API và JDBC driver** | API là hợp đồng Java; driver là thư viện hiện thực cho DBMS |
| **DBMS và database** | DBMS là hệ thống quản lý; database là dữ liệu và cấu trúc được quản lý |
| **`Connection` và connection pool** | `Connection` là đối tượng phiên làm việc; pool quản lý và tái sử dụng nhiều kết nối |
| **`Statement` và `PreparedStatement`** | `PreparedStatement` hỗ trợ marker và bind giá trị; `Statement` thực thi SQL text |
| **`PreparedStatement` và `ResultSet`** | Statement gửi lệnh; ResultSet cho phép đọc hàng của kết quả |
| **SQL `NULL` và Java `null`** | SQL `NULL` có logic ba trị; Java `null` là vắng tham chiếu |
| **`executeQuery()` và `executeUpdate()`** | Một bên trả `ResultSet`; bên kia trả update count |
| **`commit()` và `close()`** | Commit xác nhận transaction; close giải phóng/trả kết nối, không thay thế quy tắc commit |
| **`LocalDateTime` và `Instant`** | Một bên là ngày giờ địa phương chưa gắn zone; bên kia là một thời điểm tuyệt đối |
| **JDBC và ORM (ví dụ JPA)** | JDBC trực tiếp điều phối SQL/kết nối; ORM quản lý ánh xạ đối tượng–quan hệ ở tầng trừu tượng cao hơn |

JDBC thông thường là API **đồng bộ, chặn luồng** trong quá trình truy cập DB. Không nên hiểu nó đồng nghĩa với cơ chế truy cập không chặn hoặc reactive; những cơ chế đó có API và hợp đồng thực thi riêng.

## 11. Những lỗi nhập môn và cách tìm nguyên nhân

| Triệu chứng | Câu hỏi kiểm tra đầu tiên |
| --- | --- |
| Không thể kết nối DB | URL, host/port, DB đang chạy, quyền mạng và credential có đúng không? |
| “No suitable driver” | Driver JDBC phù hợp đã có trong runtime/classpath? JDBC URL đúng loại? |
| Sai số lượng tham số | Có đủ lời gọi `setXxx` với index bắt đầu từ 1? |
| SQL syntax error | Cú pháp SQL đúng theo DBMS? Có ghép chuỗi vào SQL? |
| Truy vấn trả 0 hàng | Điều kiện `WHERE`, dữ liệu và transaction hiện tại có đúng? |
| `ResultSet` không đọc được | Đã gọi `rs.next()` trước `getXxx`? Statement/connection đã bị đóng? |
| Dữ liệu `NULL` thành `0` | Đã kiểm tra `rs.wasNull()` hoặc dùng kiểu nullable? |
| `UPDATE` báo thành công nhưng dữ liệu không đổi | Update count thực tế là bao nhiêu, đã commit chưa, đang dùng đúng DB/schema? |
| Lỗi khi dùng chung connection | Có chia sẻ connection không phù hợp giữa thread/request? Transaction chưa kết thúc? |
| Hết connection trong pool | Có rò rỉ connection, giao dịch quá dài hoặc pool quá nhỏ so với tải? |

Một số lỗi không nằm ở JDBC: SQL sai logic, index thiếu, bảng chưa có dữ liệu hoặc ràng buộc DB không cho phép thay đổi. Dùng nhật ký có kiểm soát, SQLState, thông tin driver/DBMS và dữ liệu kiểm thử nhỏ để khoanh vùng, thay vì sửa ngẫu nhiên phần Java.

## 12. Bài thực hành tổng hợp: “Sổ khách hàng”

Sau khi đọc xong, hãy xây dựng một ứng dụng console hoặc một lớp DAO với bảng `customer` đã tạo ở phần đầu.

**Yêu cầu tối thiểu:**

1. Kết nối DB bằng driver JDBC tương ứng; lấy URL/user/password từ cấu hình môi trường.
2. Viết hàm thêm khách hàng bằng `PreparedStatement`, sử dụng tham số cho `id`, `full_name` và `email`.
3. Viết hàm tìm khách theo `id`, trả kết quả rõ ràng khi không tìm thấy.
4. Viết hàm đổi email theo `id`; kiểm tra update count để nhận biết bản ghi có tồn tại hay không.
5. Viết hàm xóa khách theo `id`; thử trường hợp bị ràng buộc FK chặn.
6. Đảm bảo mọi `Connection`, `PreparedStatement` và `ResultSet` được đóng đúng cách.
7. Thử input tên `O'Connor` và email chứa ký tự lạ để chắc chắn dữ liệu được bind an toàn.
8. Thử thực thi hai câu thay đổi trong một transaction; cố ý gây lỗi ở câu sau và kiểm tra rollback.

**Tự đánh giá bằng năm câu hỏi:**

1. Vai trò của JDBC API khác JDBC driver ở đâu?
2. Vì sao `PreparedStatement` giúp ngăn SQL injection nhưng không cho phép dùng `?` để thay tên cột?
3. `ResultSet` đứng ở đâu trước lần gọi `next()` đầu tiên?
4. Khi nào cần tắt `autoCommit` và gọi `rollback()`?
5. Vì sao chương trình cần đóng `Connection` ngay cả khi kết nối đến từ pool?

Nếu trả lời được các câu hỏi này và chạy được bài thực hành, bạn đã có nền tảng để học sâu các chủ đề tiếp theo của JDBC: **driver và kết nối, CRUD và truy vấn nâng cao, ánh xạ kiểu dữ liệu, transaction/isolation, batch, xử lý lỗi, tối ưu hiệu năng và bảo mật**. Các chủ đề nâng cao đều quay lại những thành phần cốt lõi vừa học: SQL, `Connection`, `PreparedStatement`, `ResultSet` và ranh giới transaction.
