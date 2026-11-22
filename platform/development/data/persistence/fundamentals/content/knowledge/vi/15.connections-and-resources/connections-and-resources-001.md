# Vòng đời kết nối từ ứng dụng tới kho dữ liệu

## Mục tiêu học tập

Sau bài học này, người học có thể:

1. Mô tả các bước từ lúc ứng dụng Java yêu cầu một kết nối cho đến khi câu SQL được gửi tới kho dữ liệu và tài nguyên được giải phóng.
2. Phân biệt **kết nối vật lý**, **phiên làm việc (session)** ở database và **đối tượng `Connection` được mượn từ pool**.
3. Sử dụng đúng `DataSource`, `Connection`, `PreparedStatement`, `ResultSet` và `try-with-resources` để tránh rò rỉ.
4. Xác định ranh giới transaction và phản ứng thích hợp khi lỗi mạng, timeout, rollback hoặc mất kết nối lúc commit.
5. Giải thích tác động của connection pool, số request đồng thời, thời gian giữ kết nối và giới hạn kết nối của database đối với hiệu năng.
6. Lập kế hoạch theo dõi, kiểm thử và bảo vệ tài nguyên kết nối trong dịch vụ Java thực tế.

Bài thuộc chương **Kết nối và tài nguyên** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Để lưu trữ dữ liệu bền vững, hiểu mô hình dữ liệu, schema, truy vấn, chỉ mục và giao dịch là cần thiết; nhưng ứng dụng còn phải quản lý cách **đi vào** kho dữ liệu và cách **trả lại** tài nguyên khi có lỗi. Nội dung kết nối liên quan trực tiếp đến ranh giới persistence trong Java, cô lập, kiểm soát đồng thời, xử lý lỗi, bảo mật, sao lưu và tối ưu hiệu năng.

## 1. Một request đi qua những tài nguyên nào?

Giả sử người dùng mở màn hình đơn hàng gần đây. HTTP request đi vào một Java service, service gọi repository, repository truy vấn PostgreSQL và trả danh sách đơn hàng.

~~~text
Client HTTP
    |
    v
Controller / Service (Java)
    |
    v
Repository / DAO
    |
    v
DataSource / connection pool
    |                 |
    | mượn Connection| quản lý kết nối vật lý
    v                 v
JDBC Connection --> JDBC driver
                         |
                         | socket / TLS / giao thức DB
                         v
                 Database server
                session + transaction
                         |
                         v
                    SQL engine
                    buffer / index
                    storage
                         |
                         v
            ResultSet -> Java objects
                         |
                         v
                 Trả Connection về pool
~~~

Các tài nguyên có thời gian sống khác nhau:

| Tài nguyên | Được tạo hoặc lấy ở đâu? | Thời gian sống nên có |
| --- | --- | --- |
| `DataSource` | Cấu hình lúc khởi động ứng dụng | Thường dùng chung theo vòng đời service |
| Kết nối vật lý tới DB | Driver/pool tạo khi cần, gồm giao thức mạng và session | Có thể tồn tại qua nhiều request |
| `Connection` được mượn | `dataSource.getConnection()` | Chỉ trong phạm vi thao tác cần DB |
| `PreparedStatement` | Từ một `Connection` | Trong phạm vi một truy vấn hoặc đợt truy vấn |
| `ResultSet` | Từ việc thực thi statement | Cho đến khi đọc xong và đóng |
| Transaction | Mở và kết thúc theo ranh giới nghiệp vụ | Đủ ngắn để bảo vệ thay đổi cần nguyên tử |
| Object kết quả Java | Tạo khi chuyển dữ liệu từ `ResultSet` | Tùy nhu cầu xử lý, không cần giữ kết nối |

**Một request HTTP không đồng nghĩa với một kết nối vật lý mới.** Với connection pool, hàng trăm request có thể dùng luân phiên một nhóm kết nối đã được tạo sẵn. Ngược lại, một request có thể tạo nhiều giao dịch và nhiều lần mượn kết nối, tùy cách thiết kế.

## 2. Kết nối vật lý, session và kết nối logic

### 2.1. Khi tạo một kết nối vật lý mới

Ở cấu hình JDBC thường gặp, driver cần xác lập giao tiếp tới database. Quá trình có thể bao gồm:

1. Xác định địa chỉ máy chủ, cổng và tên database; phân giải DNS nếu cần.
2. Thiết lập kênh truyền, thường là TCP; một số môi trường hỗ trợ Unix-domain socket hoặc transport khác.
3. Thương lượng TLS nếu được bật, bao gồm kiểm tra chứng chỉ và tên máy chủ theo cấu hình.
4. Thực hiện bắt tay giao thức và xác thực tài khoản.
5. DBMS cấp session hoặc tài nguyên xử lý cho kết nối, thiết lập những tham số ban đầu như múi giờ, schema, quyền và chế độ transaction.

Các bước và thứ tự chính xác phụ thuộc PostgreSQL, MySQL, SQL Server, driver và hạ tầng mạng. **Tạo kết nối không miễn phí**: có độ trễ mạng, CPU, bộ nhớ và tài nguyên trên server. Đây là lý do các ứng dụng có lưu lượng đáng kể thường dùng pool.

Một kết nối vật lý đã được tạo có thể được sử dụng cho nhiều transaction liên tiếp, nhưng **không đồng nghĩa** là transaction, snapshot và khóa từ request trước còn được phép tồn tại sang request sau. Pool phải trả trạng thái session về mức phù hợp theo hợp đồng của nó; mã ứng dụng cũng phải đóng tài nguyên và hoàn tất transaction đúng cách.

### 2.2. Điều gì xảy ra khi `getConnection()` chạy?

Với `DriverManager.getConnection(...)`, ứng dụng thường yêu cầu driver thiết lập một kết nối mới. Với một `DataSource` do connection pool quản lý, `getConnection()` thường là thao tác **mượn (borrow/checkout)** một kết nối logic đại diện cho kết nối vật lý còn dùng được.

Nếu pool có kết nối rảnh, nó có thể trả ngay. Nếu chưa có kết nối rảnh mà vẫn dưới giới hạn, pool có thể tạo thêm kết nối vật lý. Nếu đã tới giới hạn, lời gọi thường phải **chờ** cho đến khi một connection được trả, timeout hoặc bị hủy. Hợp đồng chính xác tùy pool.

~~~text
                     getConnection()
                           |
                           v
                  +----------------+
                  | Pool có kết nối |
                  | rảnh hợp lệ?   |
                  +-------+--------+
                      Có  |  Không
                      |   | 
                      v   v
                   Mượn  Có thể tạo thêm?
                      |       |         |
                      |      Có        Không
                      |       |         |
                      |       v         v
                      |   Mở vật lý   Chờ connection
                      |       |         |
                      +-------+---------+
                              |
                              v
                       JDBC Connection
                              |
                    SQL / COMMIT / ROLLBACK
                              |
                              v
                      connection.close()
                              |
                              v
                  Trả về pool hoặc loại bỏ
                  nếu kết nối đã hỏng
~~~

Hình này trình bày trực giác. Pool thực tế còn có kiểm tra tính hợp lệ, giới hạn lifetime/idle, chính sách tạo kết nối, circuit breaker hoặc các chi tiết triển khai khác.

### 2.3. `close()` có đóng socket ngay không?

- **Kết nối không dùng pool:** `Connection.close()` thường giải phóng kết nối vật lý và tài nguyên giao thức liên quan.
- **Kết nối lấy từ pool:** `Connection.close()` thường đóng **handle logic** và trả kết nối vật lý về pool để request khác mượn.

Vì thế, dù dùng pool, **luôn phải gọi `close()`**, tốt nhất qua `try-with-resources`. Không gọi `close()` vì nghĩ “pool sẽ tự quản lý” là nguyên nhân phổ biến khiến pool cạn kết nối.

Sau khi trả handle, không sử dụng lại nó. Một `Connection` đã được close không phải đối tượng để giữ trong field của singleton service và chia sẻ qua nhiều request.

## 3. Vòng đời điển hình của một thao tác đọc

Lấy ví dụ bảng đơn hàng:

~~~sql
CREATE TABLE orders (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    BIGINT NOT NULL,
    customer_id  BIGINT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    total_amount NUMERIC(14, 2) NOT NULL
);
~~~

Một repository JDBC đọc tối đa 50 đơn gần đây:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

public final class OrderQueries {
    public record OrderRow(long id, BigDecimal amount, Instant createdAt) {}

    private final DataSource dataSource;

    public OrderQueries(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public List<OrderRow> recentOrders(long tenantId, int requestedLimit)
            throws SQLException {

        int limit = Math.max(1, Math.min(requestedLimit, 50));
        String sql = """
            SELECT id, total_amount, created_at
            FROM orders
            WHERE tenant_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """;

        List<OrderRow> result = new ArrayList<>();

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(sql)) {

            statement.setLong(1, tenantId);
            statement.setInt(2, limit);

            try (ResultSet rs = statement.executeQuery()) {
                while (rs.next()) {
                    result.add(new OrderRow(
                        rs.getLong("id"),
                        rs.getBigDecimal("total_amount"),
                        rs.getTimestamp("created_at").toInstant()));
                }
            }
        }
        return result;
    }
}
~~~

Ví dụ sử dụng Java 17 và `DataSource` được cấu hình bên ngoài. Lệnh `SELECT` trả về một danh sách **đã được đưa vào object Java** trước khi đóng kết nối; hàm không cố mang `ResultSet` sống ra khỏi phạm vi `try`.

Có thể lần lượt theo dõi các bước:

1. `getConnection()`: mượn handle, có thể chờ nếu pool bận.
2. `prepareStatement(sql)`: tạo statement và các tài nguyên tương ứng; mức độ chuẩn bị trên server có thể phụ thuộc driver/cấu hình.
3. `setLong`, `setInt`: gắn tham số an toàn, tránh ghép chuỗi SQL từ đầu vào không tin cậy.
4. `executeQuery()`: driver gửi yêu cầu đến DB, DB phân tích, lập kế hoạch hoặc dùng kế hoạch phù hợp, thực thi rồi trả dữ liệu.
5. `ResultSet.next()`: lấy lần lượt các hàng, có thể sử dụng bộ đệm/fetch theo cơ chế driver.
6. Thoát `try`: đóng `ResultSet`, sau đó `PreparedStatement` và `Connection` theo thứ tự ngược lúc tạo.
7. Trong pool, kết nối được trả về để phục vụ request khác.

Việc đóng `ResultSet` là quan trọng khi driver dùng cursor hoặc giữ tài nguyên phía server. `try-with-resources` cũng đóng tài nguyên khi có `SQLException` hoặc exception trong lúc chuyển dữ liệu.

### 3.1. Tại sao không trả thẳng `ResultSet` ra controller?

`ResultSet` gắn với statement và connection. Khi connection bị đóng hoặc statement bị đóng, result set có thể không còn hợp lệ. Ngược lại, nếu giữ kết nối mở để controller từ từ duyệt, request có thể chiếm một slot pool rất lâu.

Trong phần lớn API phân trang, nên chuyển dữ liệu thành DTO/record hoặc đối tượng phù hợp **ngay tại ranh giới persistence** rồi đóng kết nối. Với streaming nhiều dữ liệu, cần thiết kế vòng đời stream, backpressure và chính sách đóng tài nguyên rõ ràng; không coi nó giống thao tác đọc một danh sách nhỏ.

### 3.2. `autoCommit` ảnh hưởng ranh giới như thế nào?

Theo JDBC, connection có chế độ `autoCommit`. Nhiều driver/connection mặc định ở `true`, nơi mỗi statement được commit tự động theo quy tắc JDBC; với truy vấn có `ResultSet`, thời điểm statement được coi là hoàn tất còn phụ thuộc cách tiêu thụ và đóng kết quả.

Trong ví dụ chỉ đọc dữ liệu, không cần mở transaction nhiều câu lệnh. Nếu thao tác gồm nhiều bước phải nhìn hoặc sửa dữ liệu thống nhất, cần **quản lý transaction có chủ đích** qua `setAutoCommit(false)` hoặc transaction manager.

## 4. Vòng đời kết nối trong một transaction ghi

Xét nghiệp vụ đặt hàng gồm **trừ tồn kho và thêm đơn hàng**. Hai câu SQL phải commit hoặc rollback cùng nhau.

Chuẩn bị bảng minh họa trong database thử nghiệm:

~~~sql
CREATE TABLE products (
    id      BIGINT PRIMARY KEY,
    stock   INTEGER NOT NULL CHECK (stock >= 0)
);

CREATE TABLE purchase_orders (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id   BIGINT NOT NULL,
    request_key TEXT NOT NULL,
    product_id  BIGINT NOT NULL REFERENCES products(id),
    quantity    INTEGER NOT NULL CHECK (quantity > 0),
    UNIQUE (tenant_id, request_key)
);
~~~

Giả sử hàng `products(id = 101)` đã tồn tại và còn tồn kho. Một phương thức dùng **cùng Connection** cho hai câu SQL:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class PurchaseRepository {
    private final DataSource dataSource;

    public PurchaseRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean buy(
            long tenantId, String requestKey, long productId, int quantity)
            throws SQLException {

        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        if (requestKey == null || requestKey.isBlank()) {
            throw new IllegalArgumentException("Missing request key");
        }

        String reserveSql = """
            UPDATE products
            SET stock = stock - ?
            WHERE id = ? AND stock >= ?
            """;
        String insertSql = """
            INSERT INTO purchase_orders
                (tenant_id, request_key, product_id, quantity)
            VALUES (?, ?, ?, ?)
            """;

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                int reserved;
                try (PreparedStatement reserve =
                             connection.prepareStatement(reserveSql)) {
                    reserve.setInt(1, quantity);
                    reserve.setLong(2, productId);
                    reserve.setInt(3, quantity);
                    reserved = reserve.executeUpdate();
                }

                if (reserved != 1) {
                    connection.rollback();
                    return false;
                }

                try (PreparedStatement insert =
                             connection.prepareStatement(insertSql)) {
                    insert.setLong(1, tenantId);
                    insert.setString(2, requestKey);
                    insert.setLong(3, productId);
                    insert.setInt(4, quantity);
                    insert.executeUpdate();
                }

                connection.commit();
                return true;
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }
}
~~~

Code là ví dụ JDBC tối giản trên Java 17. `false` biểu thị không đủ tồn kho hoặc không có sản phẩm; lỗi SQL, kể cả trùng `request_key`, **được báo ra** để tầng nghiệp vụ xử lý, không bị coi là hết hàng. Trong ví dụ này khóa `request_key` giúp phát hiện yêu cầu trùng, nhưng chưa triển khai đầy đủ giao thức idempotency.

**Những mốc quan trọng:**

- Cả `UPDATE` lẫn `INSERT` phải đi qua **cùng một connection, cùng transaction**.
- Không xác nhận nghiệp vụ đã thành công chỉ vì `executeUpdate()` không ném lỗi; xác nhận chỉ sau khi `commit()` trả thành công.
- Nếu thiếu tồn kho, `rollback()` kết thúc transaction chủ động; connection vẫn phải được close.
- Nếu câu INSERT lỗi, rollback để hoàn lại phần trừ tồn kho.
- Nếu `commit()` ném lỗi do mất mạng, rollback chỉ là nỗ lực dọn dẹp. **Client có thể không biết DB đã commit hay chưa**; dùng `request_key` và tra cứu trạng thái bằng kết nối mới trước khi thử lại.
- Nếu có tầng transaction manager (Spring/JTA), tránh tự `commit()` trên connection do framework quản lý trừ khi đó là hợp đồng đã chọn.

Ví dụ không thực hiện retry tự động. Retry một nghiệp vụ có tác dụng phụ bên ngoài hoặc có thể đã commit cần được thiết kế theo idempotency và mã lỗi cụ thể.

### 4.1. Điều gì xảy ra với trạng thái connection sau transaction?

Một connection có trạng thái session, ví dụ:

- `autoCommit`, mức cô lập, chế độ read-only.
- Schema hiện hành, client session variables hoặc thông số session.
- Transaction đang mở, các khóa được giữ và trạng thái lỗi của transaction.
- Tài nguyên cursor, statement và temporary object tùy DBMS.

Một pool thông dụng cố gắng trả các thuộc tính JDBC về trạng thái cấu hình trước khi cấp cho request tiếp theo. Tuy nhiên, **không được giả định pool tự biết và reset mọi thay đổi session do ứng dụng thực hiện bằng SQL tùy ý**, ví dụ thay đổi search path, role, biến cấu hình hoặc tạo temporary table.

Ở PostgreSQL, `SET LOCAL` có hiệu lực theo transaction; lựa chọn này có thể phù hợp hơn `SET` cấp session khi cần một cấu hình chỉ tồn tại trong transaction. Với truy cập đa tenant, cần thực hiện phân quyền chắc chắn ở tầng phù hợp và tránh để trạng thái tenant của request trước rò sang request tiếp theo.

## 5. Connection pool vận hành như thế nào?

Một connection pool quản lý tập kết nối vật lý có thể tái sử dụng, thường gồm:

- Giới hạn số lượng kết nối vật lý mở đồng thời.
- Danh sách kết nối rảnh và đang được mượn.
- Thời gian chờ mượn kết nối.
- Kiểm tra kết nối bị hỏng hoặc đã hết hạn.
- Chính sách thời gian tồn tại tối đa, thời gian nhàn rỗi và tạo mới.
- Thống kê về số connection active, idle, pending và thời gian chờ.

Ví dụ, một dịch vụ dùng HikariCP có cấu hình minh họa:

~~~properties
# Các tên tham số dưới đây là cấu hình HikariCP.
maximumPoolSize=12
minimumIdle=4
connectionTimeout=2000
idleTimeout=600000
maxLifetime=1800000
~~~

Các giá trị trên **chỉ là ví dụ**, không phải cấu hình tối ưu chung. `connectionTimeout` tính bằng mili giây trong HikariCP và giới hạn thời gian chờ mượn connection từ pool; `maxLifetime` đặt tuổi thọ tối đa của kết nối theo chính sách pool, không phải timeout của một câu SQL. Cần đối chiếu phiên bản thư viện và cấu hình datasource thực tế.

### 5.1. Các trạng thái cần phân biệt

~~~text
Chưa tạo
    |
    | tạo kết nối vật lý thành công
    v
IDLE (đang rảnh trong pool)
    |
    | mượn
    v
ACTIVE (được request sử dụng)
    |
    | commit/rollback + close handle
    v
IDLE
    |
    | quá tuổi thọ / bị lỗi / pool đóng
    v
EVICTED / CLOSED
~~~

Nếu connection đang ACTIVE bị ngắt mạng, thao tác SQL hoặc kiểm tra kế tiếp có thể báo lỗi; pool cần loại connection hỏng và cấp connection khác ở lần mượn sau theo chính sách. **Pool không tự bảo đảm một transaction dở dang sẽ được thực hiện tiếp trên kết nối mới**. Transaction đang làm dở thường phải được xử lý lại ở tầng nghiệp vụ.

### 5.2. “Pool càng lớn càng nhanh” là suy luận sai

Giả sử có 8 bản sao service, mỗi bản sao cấu hình tối đa 30 connection. Riêng nhóm này **có thể tạo tới 240 kết nối DB**, chưa tính job nền, migration, công cụ giám sát, admin và dịch vụ khác. Nếu database chỉ cho phép số session thấp hơn hoặc không đủ CPU/RAM/IO để xử lý đồng thời từng ấy truy vấn, mở rộng pool sẽ làm tình hình tệ hơn.

Một mô hình ước lượng ban đầu dựa trên **Little's Law**:

`Số connection trung bình đang bận ≈ tốc độ thao tác DB (lần/giây) × thời gian giữ connection trung bình (giây)`

Ví dụ minh họa: 200 thao tác DB/s và mỗi thao tác giữ connection trung bình 60 ms thì số connection bận trung bình khoảng `200 × 0,06 = 12`. Đây là **trung bình trong điều kiện ổn định**; cần xét burst, phân bố thời gian giữ, p95/p99, thời gian chờ và mục tiêu DB. Không chỉ lấy kết quả 12 rồi kết luận chắc chắn pool 12 là đủ.

Thời gian giữ connection khác thời gian chạy một câu SQL: nó còn bao gồm các khoảng chờ trong Java, đọc result set, thao tác khác trong transaction và thời gian chờ khóa.

### 5.3. Phân biệt tải ở pool và tải ở database

| Dấu hiệu | Diễn giải có thể có | Bước kiểm tra |
| --- | --- | --- |
| Pending tăng, active luôn chạm max | Không còn connection rảnh | Xem connection leak, transaction dài, SQL chậm hoặc pool quá nhỏ |
| Active ít nhưng API chậm | Chậm có thể nằm ở tầng khác | Kiểm tra mạng, CPU Java, cache, dịch vụ gọi ngoài |
| Connection tạo mới liên tục | Lifetime, network, DB restart hoặc xác thực | Kiểm tra log pool, kết nối bị reset và churn |
| Nhiều DB session nhưng throughput thấp | Quá nhiều truy vấn cùng chạy, chờ khóa/IO | Xem `pg_stat_activity`, lock wait, CPU/IO |
| Pool báo timeout nhưng DB không quá tải | Request giữ connection quá lâu, cạn pool hoặc deadlock ứng dụng | Đo thời gian borrow/hold, stack và transaction |
| DB báo “too many connections” | Tổng connection các ứng dụng vượt giới hạn | Kiểm tra tổng pool của các instance và dự phòng quản trị |

Pool hữu ích nhất khi kết nối được **mượn đúng lúc cần DB và trả lại sớm**. Giữ connection trong lúc chờ HTTP call đến dịch vụ thanh toán hoặc gửi email có thể khiến pool cạn ngay cả khi SQL chạy rất nhanh.

## 6. Những loại timeout khác nhau

Một lỗi “timeout” không cho biết tầng nào gặp vấn đề. Cần phân biệt rõ:

| Loại timeout | Giai đoạn | Hậu quả chính |
| --- | --- | --- |
| **Pool acquisition timeout** | Chờ `getConnection()` khi pool không có kết nối rảnh | Có thể chưa gửi bất kỳ SQL nào tới DB |
| **Connect timeout** | Thiết lập kết nối mạng mới | Không bắt tay được trong thời gian cho phép |
| **Login/authentication timeout** | Xác thực hoặc tạo phiên DB | Không thiết lập session đúng hạn |
| **Socket/network read timeout** | Chờ byte phản hồi từ server | Trạng thái câu SQL/transaction có thể chưa rõ ở client |
| **Statement/query timeout** | Chờ hoặc thực thi một SQL | Driver/DB có thể yêu cầu hủy statement; cần xác minh transaction |
| **Transaction timeout** | Thời lượng toàn transaction | Phụ thuộc transaction manager/DB; có thể rollback hoặc báo lỗi |
| **Idle-in-transaction timeout** | Session giữ transaction mở nhưng không tiến triển | DB có thể chấm dứt transaction/session để giải phóng tài nguyên |
| **Idle/lifetime của pool** | Giữ kết nối nhàn rỗi hoặc quá tuổi | Pool loại/thay kết nối khi phù hợp |

Một số khả năng cấu hình cụ thể:

- JDBC có `Statement.setQueryTimeout(seconds)` nhưng hiệu lực và cơ chế cancel phụ thuộc driver/DBMS.
- HikariCP có `connectionTimeout` để giới hạn thời gian **mượn**, không thay cho SQL timeout.
- PostgreSQL hỗ trợ `statement_timeout`, `lock_timeout` và `idle_in_transaction_session_timeout` với ý nghĩa khác nhau.
- Driver PostgreSQL có những tùy chọn liên quan đến kết nối và đọc socket; cần kiểm tra đơn vị và phạm vi trong tài liệu phiên bản driver đang dùng.

**Không dùng một timeout dài cho tất cả tầng.** Ví dụ API có thời gian đáp ứng mục tiêu 2 giây nhưng pool cho chờ connection 30 giây là không nhất quán. Ngược lại, đặt SQL timeout quá ngắn có thể khiến truy vấn/transaction thường xuyên thất bại, tạo nhiều retry và tăng tải.

### 6.1. Timeout không có nghĩa thao tác chắc chắn chưa xảy ra

Nếu xảy ra pool acquisition timeout, request có thể chưa mượn được connection nên chưa gửi SQL trong nhánh đó. Nếu **socket timeout sau khi đã gửi UPDATE hoặc COMMIT**, trạng thái phía server không thể suy ra chỉ từ exception phía client.

Với COMMIT, phản hồi có thể bị mất sau khi database đã commit. Cần định danh yêu cầu nghiệp vụ, ràng buộc duy nhất và cách tra cứu trạng thái bằng kết nối mới. Đừng retry nguyên một lệnh tạo đơn với khóa yêu cầu mới chỉ vì `SQLException` hoặc HTTP timeout.

## 7. Đóng tài nguyên đúng cách trong Java

### 7.1. Quy tắc `try-with-resources`

JDBC API cung cấp `AutoCloseable` cho `Connection`, `Statement` và `ResultSet`. Dùng mẫu:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    // Thiết lập tham số và thực thi.
    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            // Chuyển dữ liệu thành DTO hoặc xử lý kết quả.
        }
    }
}
~~~

Khi thoát khối, tài nguyên được đóng theo thứ tự ngược lúc mở. Nếu có exception ở phần chính rồi `close()` cũng ném lỗi, Java có thể đính kèm lỗi đóng dưới dạng **suppressed exception**; không nên chỉ xem thông báo lỗi cuối cùng mà bỏ nguyên nhân đầu tiên.

### 7.2. Một cách làm sai phổ biến

~~~java
// Ví dụ sai: hàm tạo kết nối nhưng không đóng sau khi đọc.
Connection connection = dataSource.getConnection();
PreparedStatement statement = connection.prepareStatement(sql);
ResultSet rs = statement.executeQuery();
return rs; // Tài nguyên còn mở và vòng đời không rõ.
~~~

Nếu nhiều request lặp lại, số connection đang bị mượn tăng lên; cuối cùng pool có thể không còn slot rảnh. Một số pool có phát hiện leak theo thời gian giữ connection, nhưng **leak detection là công cụ quan sát**, không thay cho đóng tài nguyên.

Tương tự, không giữ `Connection`, `PreparedStatement` hoặc `ResultSet` làm field mutable trong singleton service rồi dùng từ nhiều thread. Trong phần lớn thiết kế, hãy chia sẻ **`DataSource`**, còn connection và statement có vòng đời theo một tác vụ/transaction; không giả định object JDBC an toàn để nhiều thread cùng sử dụng.

### 7.3. Đọc dữ liệu khối lượng lớn và cursor

Đọc một triệu hàng vào `List` có thể làm tăng heap và giữ connection rất lâu. Nếu dùng streaming hoặc cursor:

- Cấu hình kích thước fetch phù hợp với driver và workload.
- Bảo đảm stream/cursor đóng được khi client ngắt kết nối hoặc xử lý ném lỗi.
- Giới hạn thời gian transaction và tránh giữ pool slot khi consumer xử lý chậm.
- Với PostgreSQL JDBC, cách streaming sử dụng server-side cursor thường có yêu cầu riêng, trong đó chế độ autocommit và fetch size có thể ảnh hưởng; cần kiểm tra tài liệu của phiên bản driver.

Một API phân trang thường có lợi khi truy vấn theo trang nhỏ và chuyển thành DTO; streaming phù hợp cho tác vụ batch đã được thiết kế riêng về tài nguyên và backpressure.

## 8. Kết nối, transaction và framework

Trong Spring, `@Transactional` thường giao việc mở/đóng transaction cho transaction manager, có thể liên kết một JDBC connection với luồng xử lý trong phạm vi transaction.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void placeOrder(CreateOrderCommand command) {
        repository.reserveStock(command);
        repository.insertOrder(command);
    }
}
~~~

`OrderRepository` và `CreateOrderCommand` trong ví dụ là các lớp của ứng dụng, chưa được định nghĩa tại đây. Đoạn code minh họa **ranh giới khai báo**, không phải chương trình chạy độc lập. Hai lời gọi repository phải thực sự tham gia cùng transaction manager và datasource thì mới ở chung một transaction.

Những điểm cần hiểu:

- Ở cấu hình Spring dùng proxy, self-invocation (`this.method()`) thường không kích hoạt interceptor `@Transactional`.
- Exception xảy ra sau một câu SQL không tự rollback nếu transaction manager không được cấu hình rollback cho loại exception đó; mặc định Spring thường rollback cho unchecked exception, còn checked exception có chính sách riêng.
- Đoạn code **bên trong** phương thức `@Transactional` có thể chạy trước khi transaction manager thực sự commit. Không phát thông điệp “đã commit” cho hệ thống bên ngoài nếu commit còn chưa xong.
- ORM có thể trì hoãn SQL đến `flush()` hoặc commit; entity trong persistence context không chứng minh dữ liệu đã lưu bền.
- Với connection pool, đóng handle logic sau transaction thường trả nó về pool. Việc framework quản lý lifecycle có thể khiến bạn không thấy lời gọi `close()` trực tiếp ở tầng service, nhưng cơ chế giải phóng tài nguyên vẫn phải tồn tại.

Một transaction liên quan **hai database độc lập** không tự trở nên nguyên tử chỉ vì cùng đặt trong một phương thức `@Transactional`. Cần xem phạm vi transaction manager và thiết kế nhất quán liên hệ thống, ví dụ outbox/saga hoặc giao dịch phân tán khi thật sự phù hợp.

## 9. Lỗi kết nối và khôi phục có chủ đích

### 9.1. Các sự cố thường thấy

- **DB chưa sẵn sàng lúc startup:** pool không tạo được kết nối ban đầu; chính sách khởi động thất bại hoặc chờ phụ thuộc cấu hình.
- **Mất mạng hoặc phân vùng mạng:** socket có thể bị reset hoặc treo; một kết nối đang active có thể chết sau khi SQL được gửi.
- **Database restart/failover:** session cũ không còn phù hợp; pool phải bỏ các kết nối lỗi và tạo phiên mới đến endpoint đúng.
- **Credential/token hết hạn hoặc bị rotate:** kết nối mới không xác thực được nếu pool dùng credential cũ.
- **Session bị database cắt do idle timeout:** pool có thể đang giữ handle tới kết nối vật lý đã bị đóng; cần validation/eviction phù hợp.
- **Too many connections:** DB hết slot hoặc tài nguyên chấp nhận session; tăng số thread Java không giúp được.
- **Resource leak:** application không trả connection hoặc statement, làm pool cạn dần.
- **Transaction giữ khóa lâu:** database vẫn kết nối được, nhưng câu SQL phải chờ khóa; có thể trông giống “DB đơ”.

### 9.2. Quy trình xử lý theo nơi lỗi xảy ra

| Điểm lỗi | Điều nên làm | Điều không thể suy ra |
| --- | --- | --- |
| Không mượn được connection | Kiểm tra pool metrics, giới hạn và tình trạng DB; trả lỗi có thể retry ở tầng request | Không kết luận query cụ thể chậm |
| Kết nối mới thất bại | Kiểm tra DNS, mạng, TLS, xác thực, DB limit và failover | Không mặc nhiên do sai SQL |
| SQL lỗi trước COMMIT | Rollback transaction khi có thể, đóng tài nguyên; xét mã lỗi và ràng buộc | Không mặc nhiên mọi lỗi đều transient |
| COMMIT mất phản hồi | Tra cứu idempotency key/trạng thái bằng kết nối mới, rồi quyết định retry | Không biết chắc đã rollback |
| Pool connection hỏng | Để pool loại bỏ và tạo lại kết nối theo chính sách | Không thể “nối tiếp” transaction cũ trên socket mới |
| API client timeout | Phân biệt timeout request, pool, SQL và mạng | Không chắc backend không còn đang xử lý |

Khi retry, cần **giới hạn số lần, backoff, phân loại lỗi và idempotency**. Một transaction thất bại vì deadlock hoặc serialization conflict có thể hợp lý để retry toàn bộ, nếu mọi side effect được thiết kế an toàn khi lặp. Lỗi unique constraint hoặc quyền truy cập thông thường không được sửa bằng retry vô hạn.

### 9.3. Failover và endpoint database

Sau failover, hostname hoặc proxy DB có thể trỏ đến primary mới. Pool còn connection tới primary cũ phải nhận diện lỗi, bỏ connection hỏng và thiết lập session mới. DNS TTL, proxy, driver, trạng thái replication và cách đảm bảo **không ghi vào node read-only** đều cần được kiểm tra theo kiến trúc thật.

Một connection mới hoạt động sau failover **không có nghĩa** transaction đang mở trước failover đã commit. Nếu client từng gửi COMMIT nhưng không nhận phản hồi, vẫn phải thực hiện quy trình xác minh kết quả trên dữ liệu mới.

## 10. Bảo mật và cô lập tenant từ lúc mở kết nối

Kết nối database thường chứa thông tin xác thực và có quyền truy cập dữ liệu quan trọng. Bảo mật cần được xử lý ngay từ cấu hình `DataSource`:

1. Lấy mật khẩu/token từ secret manager hoặc cơ chế cấu hình bảo mật; tránh hard-code trong source hay ghi lộ vào log.
2. Bật mã hóa truyền tải và **kiểm tra chứng chỉ máy chủ** phù hợp; “có TLS” không tự đồng nghĩa đã kiểm tra đúng endpoint.
3. Cấp quyền DB tối thiểu theo vai trò ứng dụng; tách quyền chạy migration và quyền truy cập thông thường khi phù hợp.
4. Thực thi tenant authorization rõ ràng ở service/database. Sử dụng cùng một DB user cho nhiều tenant không được phép làm rò rỉ dữ liệu giữa họ.
5. Thận trọng khi thay đổi `SET ROLE`, `search_path`, session variables hoặc context tenant trên pooled connection; phải quản lý thời gian sống và reset đầy đủ.
6. Khi rotate credential, thiết kế cách connection mới nhận credential và cách pool loại kết nối cũ mà không gây gián đoạn quá mức.

Cần bảo vệ cả câu SQL và dữ liệu trong telemetry: log đầy đủ connection URL có user/password, tham số PII hoặc statement chứa thông tin nhạy cảm có thể trở thành sự cố bảo mật.

## 11. Quan sát vòng đời kết nối trong hệ thống đang chạy

Cần đo từ phía ứng dụng **và** DB để tránh kết luận một chiều:

| Vị trí | Chỉ số nên có | Câu hỏi cần trả lời |
| --- | --- | --- |
| Pool | Active, idle, pending, max | Request có đang chờ mượn kết nối không? |
| Pool | Thời gian acquire, thời gian giữ connection, timeout | Nghẽn xảy ra trước SQL hay trong transaction? |
| Driver/network | Lỗi connect/reset, TLS/auth error, socket timeout | Kết nối vật lý có ổn định không? |
| Application | Số request, độ trễ p95/p99, exception theo công đoạn | Những API nào giữ connection lâu? |
| Database | Số session active/idle, long-running transaction | Có transaction mở mà không làm việc không? |
| Database | Lock wait, deadlock, CPU, I/O, query duration | Connection bận vì cạnh tranh/SQL chậm hay vì thiếu tài nguyên? |
| Database | Connections per application/user/host | Instance nào đang chiếm kết nối bất thường? |

Trong PostgreSQL, có thể tham khảo tình trạng session:

~~~sql
SELECT application_name,
       state,
       COUNT(*) AS session_count
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY application_name, state
ORDER BY application_name, state;
~~~

Và phát hiện những transaction đang mở quá lâu:

~~~sql
SELECT pid,
       application_name,
       state,
       now() - xact_start AS transaction_age,
       wait_event_type,
       wait_event
FROM pg_stat_activity
WHERE datname = current_database()
  AND xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Quyền xem chi tiết session phụ thuộc quyền DB và cấu hình. Dùng dữ liệu này cùng metrics pool để xác định request nào giữ connection, transaction có đang chờ khóa hay không và liệu số kết nối tăng bất thường.

Chỉ nhìn `max_connections` của PostgreSQL là chưa đủ để chọn `maximumPoolSize`: cần dự phòng kết nối cho quản trị, background jobs, migration và các service khác. Còn phải xét năng lực CPU, RAM, I/O, tần suất và độ nặng của câu SQL.

## 12. Kiểm thử vòng đời kết nối

Một môi trường test có database thực và pool nhỏ giúp tái hiện rõ những sai lầm thường gặp.

**Thí nghiệm A — rò rỉ kết nối:** cấu hình pool tối đa 2 kết nối. Trong một bản thử nghiệm, giữ hai `Connection` mà không `close()`; request thứ ba sẽ phải chờ hoặc timeout theo cấu hình. Sau đó sửa bằng `try-with-resources` và quan sát số active trở về bình thường. Không chạy thí nghiệm này trên production.

**Thí nghiệm B — transaction thất bại:** bắt đầu transaction, trừ tồn kho, sau đó cố INSERT trùng khóa UNIQUE để nhận lỗi. Kiểm tra rollback, tồn kho ban đầu và connection được trả về pool. Sau một lỗi SQL ở PostgreSQL, transaction có thể ở trạng thái aborted cho đến rollback; request tiếp theo không được nhận lại một session còn lỗi.

**Thí nghiệm C — SQL chậm với pool nhỏ:** tạo công việc DB chậm trong môi trường thử nghiệm có kiểm soát; đo active, pending, acquire timeout và thời gian giữ connection. Phân biệt “SQL làm connection bận” với “pool thiếu kết nối dù SQL nhanh”.

**Thí nghiệm D — cắt kết nối:** khởi động lại database thử nghiệm hoặc tạo lỗi mạng theo công cụ được môi trường hỗ trợ. Quan sát pool loại kết nối hỏng, thời gian phục hồi và lỗi trả về ứng dụng; không giả định transaction dở dang được hoàn tất tự động.

**Thí nghiệm E — mất phản hồi COMMIT:** dùng bản ghi có `request_key` duy nhất, mô phỏng client mất phản hồi sau khi gửi commit. Kiểm tra cách request mới truy vấn trạng thái bằng key và tránh tạo bản ghi trùng; phân biệt retry an toàn với việc gửi lại yêu cầu logic bằng key khác.

Một test chỉ chạy nhiều thread trong một JVM có ích nhưng chưa phản ánh đầy đủ tình huống nhiều instance sử dụng cùng database. Khi kiểm tra giới hạn pool tổng, cần chạy nhiều tiến trình và đo số session trên DB.

## 13. Những sai lầm cần tránh

**“Pool tự thu hồi mọi kết nối nên không cần đóng.”** Pool thường không thể biết chính xác khi nào application đã dùng xong một connection chưa được đóng; nó có thể ghi cảnh báo leak, nhưng vẫn có nguy cơ cạn pool.

**“`Connection.close()` nghĩa là phải mở TCP mới ở request sau.”** Với pooled connection, close thường trả handle vào pool; tái sử dụng kết nối vật lý là mục đích cốt lõi.

**“Đã `@Transactional` thì hai repository chắc chắn dùng cùng connection.”** Cần xác minh cùng transaction manager/datasource và lời gọi đi qua cơ chế transaction của framework.

**“Tăng pool size sẽ giải quyết mọi timeout.”** Nếu DB nghẽn CPU, I/O hoặc lock, thêm connection có thể tăng tranh chấp và làm p95/p99 xấu hơn.

**“Timeout chứng minh câu ghi chưa xảy ra.”** Đặc biệt khi mất phản hồi COMMIT, client có thể không biết trạng thái đã commit; phải xác minh.

**“JDBC connection an toàn để chia sẻ trong singleton.”** Không được giả định `Connection`/`ResultSet` có thể dùng đồng thời bởi nhiều thread; chia sẻ `DataSource` và quản lý connection theo thao tác.

**“Đọc từ `ResultSet` xong là tài nguyên đã tự dọn.”** Cần đóng result set, statement và connection theo hợp đồng; đừng dựa vào GC.

**“Kết nối rảnh là không chiếm tài nguyên DB.”** Một session idle vẫn có thể chiếm bộ nhớ/slot; số lượng pool trên mọi instance phải được tính chung.

## 14. Bài tập vận dụng

**Bài 1 — vẽ vòng đời:** từ HTTP request tới PostgreSQL, hãy vẽ các mốc: mượn connection, prepare/bind, execute, đọc `ResultSet`, close statement, close connection. Đánh dấu bước nào pool có thể tạo kết nối vật lý và bước nào chỉ trả connection logic.

**Bài 2 — sửa rò rỉ:** một repository trả `ResultSet` cho controller và không đóng `PreparedStatement`. Hãy thay bằng API trả `List<OrderDto>` và dùng `try-with-resources`. Giải thích tại sao điều này giảm thời gian giữ connection.

**Bài 3 — chọn kích thước pool:** một ứng dụng có 6 instance, mỗi pool tối đa 20 kết nối; cùng DB còn 30 kết nối dành cho công việc khác. Hãy tính **mức tối đa dự kiến** có thể dùng (6 × 20 + 30 = 150), so sánh với ngân sách DB và đề xuất phép đo acquire/hold để quyết định kích thước thực. Không chọn size chỉ theo số HTTP thread.

**Bài 4 — xử lý timeout:** request A lỗi khi chưa mượn được connection, request B mất kết nối lúc COMMIT, request C bị `statement_timeout`. Với từng trường hợp, nêu điều có thể biết chắc và hành động tiếp theo; vì sao không nên dùng một chính sách retry giống hệt nhau?

**Bài 5 — đa tenant:** request đầu `SET search_path` trên pooled connection rồi trả pool; request sau đến từ tenant khác. Phân tích nguy cơ nếu session state không được reset. Đề xuất cách giới hạn session setting theo transaction hoặc cơ chế pool bảo đảm reset, kết hợp xác thực quyền truy cập.

## Ghi nhớ

**Vòng đời kết nối không chỉ gồm mở socket và gửi SQL.** Nó bao gồm thiết lập phiên DB, mượn và trả connection, tạo và đóng statement/result set, ranh giới transaction, timeout, kiểm tra kết nối lỗi, quyền truy cập và quan sát tài nguyên. Với Java, nên chia sẻ `DataSource`, quản lý `Connection` theo phạm vi công việc, sử dụng `try-with-resources`, và chỉ xác nhận nghiệp vụ sau ranh giới commit thích hợp.

Connection pool giảm chi phí mở kết nối nhưng cũng tạo giới hạn tài nguyên cần đo và bảo vệ. Một pool tốt không thay thế SQL đúng, transaction ngắn, kiểm soát đồng thời, idempotency hay cơ chế xử lý failover; những phần đó cùng tạo nên lớp persistence vừa đúng đắn vừa vận hành ổn định.
