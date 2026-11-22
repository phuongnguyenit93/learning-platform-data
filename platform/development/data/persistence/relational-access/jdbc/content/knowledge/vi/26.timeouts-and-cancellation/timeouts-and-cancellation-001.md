# Phân biệt timeout kết nối, mượn pool, truy vấn và mạng

Trong **JDBC (Java Database Connectivity)**, một lời gọi đến cơ sở dữ liệu có thể chậm vì nhiều lý do khác nhau: chưa lấy được kết nối từ pool, chưa thiết lập được kết nối vật lý, câu SQL chạy quá lâu, hoặc driver đang chờ dữ liệu trả về qua mạng. Mỗi nguyên nhân cần một **loại timeout riêng**. Đặt `Statement.setQueryTimeout(5)` không có nghĩa là toàn bộ yêu cầu HTTP hoặc `DataSource.getConnection()` sẽ kết thúc sau đúng năm giây.

Bài học thuộc chương **Timeout và hủy**, tập trung vào bốn cơ chế thường bị nhầm lẫn: **timeout kết nối**, **timeout mượn kết nối từ pool**, **timeout thực thi truy vấn**, và **timeout mạng**. Sau khi đọc, bạn sẽ biết timeout nào tác động lên giai đoạn nào, API hoặc cấu hình thường dùng, cách xử lý khi timeout xảy ra, và giới hạn của cơ chế hủy truy vấn.

## 1. Một yêu cầu JDBC trải qua những giai đoạn nào?

Giả sử API cần lấy danh sách đơn hàng bằng JDBC:

~~~text
HTTP request
  │
  ├─ A. dataSource.getConnection()
  │     ├─ Chờ mượn Connection từ pool (nếu dùng pool)
  │     └─ Có thể phải tạo kết nối vật lý / đăng nhập DB
  │
  ├─ B. connection.prepareStatement(sql)
  │
  ├─ C. statement.executeQuery()
  │     └─ DB lập kế hoạch, chờ khóa, thực thi và trả kết quả
  │
  ├─ D. resultSet.next() / getXxx()
  │     └─ Có thể phải nhận thêm dữ liệu qua mạng
  │
  └─ E. Đóng ResultSet → Statement → Connection
~~~

Các giai đoạn **không nhất thiết độc lập hoàn toàn**. Ví dụ, pool có thể tạo kết nối vật lý ngay trong lúc ứng dụng đang chờ `getConnection()`. Ngoài ra, driver có thể lấy toàn bộ kết quả ở `executeQuery()` hoặc lấy tiếp từng đợt trong `ResultSet.next()`. Vì vậy, một timeout thường chỉ giới hạn **một loại chờ/hoạt động**, không tự động trở thành đồng hồ chung cho tất cả giai đoạn.

## 2. Bảng so sánh bốn timeout

| Loại timeout | Giai đoạn chính | Cơ chế phổ biến | Đơn vị thường dùng | Khi hết hạn |
| --- | --- | --- | --- | --- |
| **Kết nối / login** | Mở kết nối vật lý, xác thực hoặc bắt tay với DB | `DataSource.setLoginTimeout(...)`; `DriverManager.setLoginTimeout(...)`; thuộc tính driver như `connectTimeout` | Giây theo JDBC login timeout; tùy driver với socket/connect | Mở kết nối thất bại |
| **Mượn từ pool** | Chờ pool cấp một `Connection` có thể dùng | Cấu hình riêng của pool, ví dụ HikariCP `connectionTimeout` | Thường là mili giây; theo từng pool | `getConnection()` thất bại vì không lấy được kết nối kịp |
| **Truy vấn** | Driver thực thi một lệnh SQL | `Statement.setQueryTimeout(int seconds)` | Giây | Driver tìm cách hủy câu lệnh; JDBC có thể báo `SQLTimeoutException` |
| **Mạng** | Đợi phản hồi qua kết nối đã thiết lập | `Connection.setNetworkTimeout(Executor, int milliseconds)`; hoặc socket read timeout riêng của driver | Mili giây với JDBC network timeout; driver có thể khác | Lời gọi mạng thất bại; kết nối có thể bị đóng hoặc trở nên không dùng được |

**Tên gọi dễ gây nhầm:** Cấu hình `connectionTimeout` của HikariCP nói về **mượn connection từ pool**. Trong khi đó, `connectTimeout` của một JDBC driver có thể nói về **kết nối TCP đến máy chủ**. Hai thuộc tính có tên gần giống nhau nhưng quản lý hai việc khác nhau; JDBC không định nghĩa một thuộc tính cấu hình chung tên `connectionTimeout` cho mọi driver/pool.

## 3. Timeout kết nối vật lý và đăng nhập cơ sở dữ liệu

Khi một `Connection` mới cần được tạo, driver có thể phải phân giải DNS, mở TCP socket, thiết lập TLS, trao đổi giao thức và xác thực với DB. Nếu máy chủ không phản hồi hoặc mạng có sự cố, ứng dụng có thể bị chặn **trước khi chạy câu SQL đầu tiên**.

JDBC cung cấp các API liên quan:

~~~java
// Áp dụng cho DataSource cụ thể, nếu triển khai hỗ trợ.
dataSource.setLoginTimeout(3);  // Đơn vị: giây.

// Áp dụng ở cấp DriverManager, ảnh hưởng các lần lấy kết nối
// phù hợp với DriverManager trong cùng tiến trình.
java.sql.DriverManager.setLoginTimeout(3); // Đơn vị: giây.
~~~

`DataSource.setLoginTimeout(...)` cấu hình thời gian tối đa chờ khi cố thiết lập kết nối đến cơ sở dữ liệu theo contract của `DataSource`. `DriverManager.setLoginTimeout(...)` là thiết lập tĩnh ở cấp `DriverManager`, không nên dùng tùy tiện trong từng request vì có phạm vi rộng. Khả năng thực thi và hành vi khi hết hạn phụ thuộc driver và triển khai `DataSource`; một số pool có thể không hỗ trợ hoặc không dùng `setLoginTimeout` theo cách bạn kỳ vọng.

Nhiều driver còn có các tham số riêng như **TCP connect timeout**, **socket timeout**, **login timeout**. Các tham số này có thể dùng tên và đơn vị khác nhau. TCP connect timeout thường giới hạn lúc thiết lập socket; JDBC login timeout hướng đến cả quá trình mở kết nối/đăng nhập. Không nên coi chúng là hai tên của cùng một cơ chế nếu chưa kiểm tra tài liệu driver.

**Ví dụ nhận diện:** Khi DB không thể kết nối và ứng dụng lỗi ngay tại `DriverManager.getConnection(...)` hoặc lúc pool tạo kết nối vật lý, cần kiểm tra kết nối/login timeout và thông báo lỗi của driver. Tăng `Statement.setQueryTimeout(...)` sẽ không giúp vì chưa có `Statement` nào tồn tại.

## 4. Timeout mượn kết nối từ pool

Ứng dụng web thường sử dụng **connection pool**. Pool giữ một số `Connection` sẵn có để tái sử dụng, tránh phải xác thực và mở socket mới cho mỗi request.

Nếu pool có giới hạn 10 kết nối và cả 10 đang bận, request mới có thể phải chờ một kết nối được trả lại. Việc chờ đó được giới hạn bởi **pool acquisition timeout** (còn gọi là **borrow timeout**). Đây là một vấn đề khác với việc máy chủ DB có mở được TCP socket hay không.

Ví dụ với **HikariCP** (thư viện bên ngoài JDBC):

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

HikariConfig config = new HikariConfig();
config.setJdbcUrl(jdbcUrl);
config.setUsername(username);
config.setPassword(password);
config.setMaximumPoolSize(10);

// Thời gian tối đa chờ pool cấp một Connection: mili giây.
config.setConnectionTimeout(1_000L);

try (HikariDataSource dataSource = new HikariDataSource(config)) {
    // Sử dụng dataSource trong vòng đời thành phần/ứng dụng.
    // Các request riêng lẻ tự đóng Connection sau khi sử dụng.
}
~~~

Đoạn mã minh họa cấu hình pool: `jdbcUrl`, `username` và `password` là các biến cấu hình có sẵn, không phải hằng số bí mật ghi trực tiếp trong mã nguồn. Trong ứng dụng máy chủ, `HikariDataSource` thường được tạo một lần và đóng khi ứng dụng dừng, **không** tạo/đóng lại cho từng request.

Với HikariCP, `connectionTimeout` giới hạn thời gian lời gọi lấy kết nối chờ pool cấp một kết nối có thể dùng. Khi hết hạn, `getConnection()` thường ném `SQLException` chứa thông tin timeout của pool. Các pool khác có tên cấu hình và ngoại lệ khác. Thời gian khởi tạo kết nối vật lý có thể là một phần đường đi lấy kết nối và chịu thêm giới hạn riêng của driver/pool; không được suy ra rằng pool timeout và login timeout chạy nối tiếp độc lập trong mọi triển khai.

Nếu pool thường xuyên hết hạn khi mượn kết nối, hãy xem **số kết nối đang hoạt động, số request chờ, thời gian giữ connection, giao dịch dài và khả năng rò rỉ connection**. Việc tăng `maximumPoolSize` không tự giải quyết truy vấn chậm và có thể làm DB quá tải hơn.

## 5. Timeout truy vấn: `Statement.setQueryTimeout`

Sau khi đã có kết nối, SQL có thể chạy lâu vì đọc nhiều dữ liệu, chọn kế hoạch không hiệu quả, chờ khóa hoặc máy chủ đang bận. JDBC cho phép đặt timeout trên **từng đối tượng câu lệnh**:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

public final class OrderRepository {

    public static List<Long> findOrderIds(
            DataSource dataSource, long customerId) throws SQLException {

        String sql = "SELECT id FROM orders WHERE customer_id = ?";
        List<Long> ids = new ArrayList<>();

        // getConnection() có timeout riêng của pool/kết nối.
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {

            // 5 giây để JDBC driver thực thi câu lệnh.
            statement.setQueryTimeout(5);
            statement.setLong(1, customerId);

            try (ResultSet rows = statement.executeQuery()) {
                while (rows.next()) {
                    ids.add(rows.getLong("id"));
                }
            }
        } // Lần lượt đóng ResultSet, PreparedStatement, Connection.

        return ids; // Danh sách Java độc lập với tài nguyên JDBC.
    }
}
~~~

`setQueryTimeout(int seconds)` dùng **giây**; giá trị `0` theo API JDBC nghĩa là không đặt giới hạn thời gian thực thi câu lệnh từ thuộc tính này. JDBC yêu cầu driver cố gắng giới hạn thời gian câu lệnh chạy và thực hiện hủy khi hết thời gian; việc đo thời gian, hỗ trợ hủy, loại lỗi, cũng như khả năng bao phủ thời gian lấy thêm dữ liệu từ `ResultSet` có thể khác nhau theo driver.

Khi timeout này xảy ra, `executeQuery()`, `executeUpdate()` hoặc API tương ứng có thể ném `SQLTimeoutException`. Tuy nhiên, trong vận hành thực tế, driver cũng có thể báo loại `SQLException`/SQLState riêng, hoặc việc hủy không hoàn tất ngay lập tức. **Timeout truy vấn là yêu cầu driver kiểm soát câu lệnh; không phải cam kết tuyệt đối về tổng thời gian request.**

**Phân biệt truy vấn và đọc kết quả:** câu lệnh có thể trả về sớm nhưng ứng dụng tiếp tục gọi `rows.next()` hàng nghìn lần, kết hợp xử lý business logic hoặc gọi dịch vụ ngoài. Không mặc nhiên cho rằng `setQueryTimeout(5)` giới hạn toàn bộ vòng lặp hoặc mọi lần tải dữ liệu từ server. Muốn giới hạn tổng thời gian, ứng dụng cần có deadline ở tầng gọi và cơ chế hủy/đóng tài nguyên phù hợp.

## 6. Timeout mạng: chờ phản hồi từ cơ sở dữ liệu

Một câu SQL có thể đã được gửi thành công nhưng driver bị chặn khi chờ phản hồi qua mạng. JDBC cung cấp:

~~~java
// networkTimeoutExecutor là một Executor do ứng dụng quản lý.
// connection là Connection đang mở.
connection.setNetworkTimeout(networkTimeoutExecutor, 8_000);

// 8_000 mili giây là giới hạn chờ phản hồi mạng theo JDBC.
// Đọc giá trị hiện tại:
int networkTimeoutMillis = connection.getNetworkTimeout();
~~~

`Connection.setNetworkTimeout(Executor, int milliseconds)` đặt ngưỡng chờ phản hồi từ cơ sở dữ liệu cho các thao tác liên quan đến kết nối. Giá trị `0` theo JDBC nghĩa là không đặt giới hạn bởi thuộc tính này. Tham số `Executor` được dùng để triển khai xử lý timeout và phải là executor còn khả dụng; việc driver hỗ trợ API và triển khai cụ thể có thể khác nhau.

Khác với `Statement.setQueryTimeout(...)`, network timeout hướng đến **đợi phản hồi qua mạng**, kể cả trong các tình huống truy vấn hoặc đọc dữ liệu mà driver đang chờ server. Khi hết hạn, driver có thể đánh dấu hoặc đóng connection; không nên tiếp tục sử dụng kết nối đó như thể chắc chắn vẫn khỏe mạnh. Pool cần loại bỏ connection không hợp lệ.

Một số driver cũng có thuộc tính **socket read timeout** (`socketTimeout`, `readTimeout` hoặc tên khác), thường được cấu hình trong JDBC URL/properties. Tên, đơn vị, phạm vi áp dụng và tương tác với `setNetworkTimeout(...)` **không thống nhất** giữa các driver. TCP keepalive giúp phát hiện một số kết nối chết trong dài hạn nhưng **không thay thế** query timeout hoặc network read timeout trong một request.

Khi thay đổi network timeout trên một `Connection` lấy từ pool, nên để pool/framework quản lý cấu hình đó, hoặc khôi phục trạng thái ban đầu nếu kết nối vẫn hợp lệ trước khi trả về pool. Tránh đặt một timeout rất ngắn ngay trên đối tượng kết nối chia sẻ mà không biết tác động của nó đến những thao tác kế tiếp.

### Vì sao query timeout và network timeout có thể cạnh tranh?

Giả sử một câu lệnh có query timeout 5 giây, còn connection có network timeout 3 giây. Nếu driver đang chờ phản hồi của DB, network timeout có thể được kích hoạt trước cơ chế hủy truy vấn và kết nối có thể trở nên không dùng được. Kết quả phụ thuộc vị trí driver đang chặn, định nghĩa timeout và cách driver triển khai.

Vì thế, khi cấu hình đồng thời, cần chọn các ngưỡng **có chủ đích**, kiểm thử trên driver/cơ sở dữ liệu thực tế, và có cơ chế loại connection lỗi. Một thiết kế thường dành network timeout đủ chỗ cho thao tác truy vấn thông thường và xử lý trường hợp mạng mất phản hồi, nhưng không tồn tại một tỷ lệ timeout đúng cho mọi hệ thống.

## 7. Ví dụ tổng hợp: bốn cơ chế trong một yêu cầu

Tình huống dưới đây giả định một ứng dụng dùng pool:

| Bước | Đợi điều gì? | Timeout liên quan | Dấu hiệu quan sát |
| --- | --- | --- | --- |
| 1. Gọi `dataSource.getConnection()`, pool đang đầy | Một kết nối được trả lại | Timeout mượn pool | Thời gian chờ pool tăng; số connection đang dùng sát giới hạn |
| 2. Pool cố mở connection vật lý mới | DB chấp nhận TCP/TLS/login | Timeout kết nối/login và tùy chọn driver | Lỗi kết nối/đăng nhập; có thể thấy mạng hoặc máy chủ đích không phản hồi |
| 3. Gọi `statement.executeQuery()` | Câu lệnh thực thi trên DB | Timeout truy vấn | Truy vấn chậm, chờ khóa, lỗi timeout/cancel |
| 4. Driver chờ DB gửi tiếp dữ liệu | Gói phản hồi trên connection | Timeout mạng/read | Lỗi I/O/socket/connection, kết nối có thể bị hỏng |
| 5. Java xử lý kết quả và trả HTTP | Xử lý nghiệp vụ, serialization, dịch vụ khác | Deadline của ứng dụng/request | Thời gian API cao dù từng lệnh JDBC chưa vượt timeout |

Ví dụ: request chờ mượn pool một lúc, sau đó chạy SQL trong thời gian gần query timeout, tiếp tục ánh xạ kết quả thành JSON. **Tổng thời gian request có thể lớn hơn query timeout** vì query timeout chỉ kiểm soát một phần chuỗi công việc. Tương tự, đặt pool timeout thấp không ép các câu SQL đang thực thi kết thúc sớm.

Một cấu hình tham khảo (không phải số mặc định khuyên dùng cho mọi hệ thống) có thể là:

~~~text
Pool borrow:       connectionTimeout = 800 ms    (cấu hình pool)
Driver login:      loginTimeout      = 3 s      (nếu hỗ trợ)
JDBC statement:    setQueryTimeout(5)            (giây)
JDBC network:      setNetworkTimeout(..., 8000)  (mili giây)
HTTP request:      deadline của ứng dụng         (cơ chế riêng)
~~~

Đây là **các phạm vi thời gian khác nhau**; một số phạm vi có thể lồng nhau. Không cộng cơ học các số trên để suy ra thời gian request tối đa. Hãy xác định deadline end-to-end và thời gian còn lại cho mỗi chặng theo yêu cầu nghiệp vụ.

## 8. Timeout không đồng nghĩa với hủy truy vấn thành công

Khi giới hạn đã hết, ứng dụng có thể muốn dừng SQL đang chạy. JDBC cung cấp `Statement.cancel()` để **yêu cầu** driver hủy câu lệnh đang thực thi, kể cả khi lời gọi đó được thực hiện từ một thread khác. Driver và DB quyết định cách tiếp nhận yêu cầu, nên thao tác này không bảo đảm dừng tức thời.

~~~java
// Minh họa trong bộ phận điều phối timeout.
// 'statement' đang thực thi trong một luồng khác.
try {
    statement.cancel(); // Best effort: yêu cầu hủy SQL.
} catch (java.sql.SQLException cancelFailure) {
    // Ghi nhận lỗi hủy; không giả định truy vấn đã dừng.
    cancelFailure.printStackTrace();
}
~~~

Đoạn trên chỉ minh họa thao tác hủy; ứng dụng thực tế phải điều phối thread an toàn, quản lý phạm vi sống của `Statement` và đóng tài nguyên sau khi xử lý. `Future.cancel(true)` hoặc `Thread.interrupt()` chỉ yêu cầu ngắt luồng Java; **không tự bảo đảm JDBC driver đã gửi lệnh cancel đến DB**. Nếu cần, ứng dụng nên giữ khả năng gọi `Statement.cancel()` và đóng statement/connection theo đúng vòng đời, đồng thời tránh tái sử dụng một kết nối chưa xác minh còn an toàn.

Trong giao dịch tường minh (`autoCommit=false`), timeout hoặc cancel có thể khiến **câu lệnh thất bại nhưng giao dịch vẫn ở trạng thái phải xử lý**. Hành vi cụ thể tùy DB; một số DB đánh dấu giao dịch lỗi cho đến khi rollback. Sau lỗi, hãy thực hiện `rollback()` khi còn có thể, hoặc để framework quản lý giao dịch thực hiện rollback. Không coi timeout là bằng chứng rằng mọi tác động của câu lệnh trước đó đã được hoàn tác.

## 9. Cách chẩn đoán đúng loại timeout

Một thông điệp “connection timeout” chưa đủ để biết phải thay tham số nào. Khi phân tích log và metrics, cần xác định **lời gọi JDBC nào đang diễn ra** tại thời điểm lỗi.

1. **Lỗi tại `getConnection()`:** xem chỉ số pool (active/idle/pending, thời gian mượn), số kết nối tối đa và log mở kết nối vật lý. Nếu pool còn khả năng cấp connection nhưng driver không mở được socket, chuyển hướng điều tra sang login/connect timeout.
2. **Lỗi tại `executeQuery()` hoặc `executeUpdate()`:** xem SQL, kế hoạch thực thi, lock wait, query timeout, transaction và log phía DB. Đo thời gian thực thi SQL riêng với thời gian lấy connection.
3. **Lỗi tại `ResultSet.next()` hoặc khi đọc cột:** kiểm tra driver có fetch thêm dữ liệu hay không, mạng và socket/network timeout; điều tra query chậm vẫn cần thiết vì đọc kết quả có thể chờ server.
4. **Lỗi khi `close()` hoặc rollback:** giữ cả lỗi chính lẫn các lỗi bổ sung (`getSuppressed()`), xác minh pool có loại bỏ connection không hợp lệ và liệu giao dịch đã kết thúc hay chưa.
5. **API chậm nhưng JDBC không timeout:** đo end-to-end request, thời gian chờ pool, thời gian SQL, vòng lặp xử lý kết quả và các lời gọi ngoài DB; nếu có deadline tổng, bảo đảm cơ chế hủy được truyền tới nơi đang chạy.

Ví dụ bắt lỗi không giả định tất cả driver trả về một loại exception:

~~~java
try {
    List<Long> ids = OrderRepository.findOrderIds(dataSource, 42L);
    System.out.println(ids.size());
} catch (java.sql.SQLTimeoutException timeout) {
    // Trường hợp JDBC báo timeout theo kiểu chuẩn.
    System.err.println("SQL timeout: " + timeout.getMessage());
} catch (java.sql.SQLException jdbcError) {
    // Lỗi pool, connect, network hoặc vendor-specific có thể tới đây.
    System.err.println("SQLState: " + jdbcError.getSQLState());
    System.err.println("Vendor code: " + jdbcError.getErrorCode());
    System.err.println("Reason: " + jdbcError.getMessage());
}
~~~

Không dùng thông điệp exception đơn lẻ để suy ra toàn bộ nguyên nhân. Cần kết hợp SQLState/vendor code, loại lỗi, metrics của pool, log driver và log DB. Khi log, tránh ghi mật khẩu, token, dữ liệu nhạy cảm hoặc toàn bộ SQL có chứa giá trị thực.

## 10. Chọn timeout theo ngân sách thời gian

Một cách thiết kế thực tế là bắt đầu từ **thời gian tối đa mà nghiệp vụ cho phép**, rồi đặt giới hạn phù hợp cho từng giai đoạn:

- **Borrow timeout:** tránh để request chờ pool quá lâu khi ứng dụng đang quá tải; đo số request chờ và thời gian giữ connection.
- **Login/connect timeout:** phát hiện DB hoặc mạng không thể thiết lập kết nối; đặt cùng với chiến lược retry để tránh làm bùng số lần kết nối.
- **Query timeout:** ngăn câu SQL chiếm tài nguyên quá lâu; chọn theo nhóm truy vấn, có thể kết hợp statement timeout ở DB khi phù hợp.
- **Network timeout:** không để luồng JDBC treo quá lâu khi phía DB hoặc mạng ngừng phản hồi; lưu ý khả năng phải loại connection.
- **Request deadline:** bảo đảm ứng dụng có giới hạn tổng, tính cả pool, SQL, việc đọc kết quả, xử lý và trả phản hồi; cần phối hợp hủy công việc ở các tầng liên quan.

Không nên tăng tất cả timeout chỉ vì quan sát thấy timeout. Ví dụ, khi pool hết connection do truy vấn bị khóa kéo dài, tăng borrow timeout thường chỉ làm số request đang chờ nhiều hơn. Cần giải quyết nguyên nhân truy vấn hoặc giao dịch kéo dài, rồi mới chọn các ngưỡng phù hợp.

## 11. Các nhầm lẫn thường gặp

| Nhầm lẫn | Giải thích chính xác |
| --- | --- |
| “Đặt query timeout 5 giây thì API tối đa 5 giây.” | Thời gian chờ pool, mở kết nối, đọc kết quả và xử lý ứng dụng nằm ngoài phần giới hạn này hoặc phụ thuộc driver. |
| “Pool connectionTimeout là timeout kết nối TCP.” | Trong HikariCP, đó là thời gian chờ mượn `Connection`; TCP connect timeout là cấu hình driver/socket khác. |
| “Login timeout làm SQL đang chạy bị dừng.” | Login timeout liên quan tạo connection mới; SQL đã chạy cần query/network/server-side timeout thích hợp. |
| “Query timeout luôn dừng truy vấn ngay lập tức.” | Driver thường cần gửi yêu cầu cancel; DB có thể xử lý hủy chậm hoặc theo cơ chế riêng. |
| “Socket timeout và network timeout giống hệt ở mọi driver.” | Chúng có thể khác về phạm vi, đơn vị, điểm bắt đầu đếm và hậu quả với connection. |
| “Bị timeout thì có thể trả Connection vào pool và dùng tiếp ngay.” | Khi có lỗi mạng, connection có thể không còn hợp lệ; pool phải kiểm tra hoặc loại bỏ. |
| “Ngắt thread Java là đủ để dừng JDBC.” | Ngắt thread không bảo đảm driver/DB hủy SQL; có thể cần `Statement.cancel()` và đóng tài nguyên. |

## 12. Tự kiểm tra

**Câu 1.** Một ứng dụng HikariCP báo `Connection is not available, request timed out` khi tất cả connection bận. Nên điều tra timeout nào?

Đó chủ yếu là **timeout mượn connection từ pool**. Kiểm tra active/pending connections, thời gian giữ connection, truy vấn/giao dịch dài và cấu hình `connectionTimeout`. Đừng kết luận ngay là DB từ chối mở TCP.

**Câu 2.** `statement.setQueryTimeout(4)` có bảo đảm `resultSet.next()` không bao giờ chặn quá 4 giây không?

Không nên giả định như vậy. Phạm vi timeout khi fetch dữ liệu có thể khác theo driver. Nếu đang chờ phản hồi qua mạng, cần xem cơ chế network/socket read timeout và deadline ở tầng ứng dụng.

**Câu 3.** Driver bị treo khi chờ phản hồi từ DB dù SQL đã gửi thành công. Nên xem cơ chế nào?

Kiểm tra network timeout (`Connection.setNetworkTimeout`) hoặc socket read timeout của driver, cùng log mạng và DB. Query timeout cũng có thể tham gia, nhưng hai cơ chế có mục đích khác nhau.

**Câu 4.** Sau khi `Statement.cancel()` trả về, có thể khẳng định giao dịch đã rollback và connection vẫn an toàn không?

Không. Hủy là yêu cầu best effort. Cần kiểm tra kết quả, trạng thái giao dịch, thực hiện rollback theo thiết kế và xác minh connection còn hợp lệ.

**Ghi nhớ:** Hãy phân loại đúng giai đoạn: **mượn pool → kết nối vật lý/login → thực thi câu lệnh → đợi phản hồi mạng**. Mỗi timeout bảo vệ một loại chờ; deadline của ứng dụng mới là giới hạn tổng cần được thiết kế và thực thi riêng. JDBC cung cấp các API chuẩn cho login, query và network timeout, còn pool/driver bổ sung cấu hình riêng có tên, đơn vị và hành vi cần kiểm chứng.
