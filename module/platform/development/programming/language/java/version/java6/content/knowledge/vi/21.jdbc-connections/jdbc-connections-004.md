# Connection.isValid và kiểm tra tình trạng kết nối JDBC trong Java

## 1. Tại sao một đối tượng Connection chưa đóng vẫn có thể hỏng?

Khi ứng dụng Java mở kết nối JDBC tới một hệ quản trị cơ sở dữ liệu, nó nhận về đối tượng `java.sql.Connection`. Kết nối có thể được dùng để thực thi truy vấn, quản lý transaction và đọc metadata. Tuy nhiên, **sự tồn tại của object không chứng minh đường truyền đến database hiện vẫn hoạt động**.

Sau vài phút hoặc vài giờ, kết nối từng hoạt động tốt có thể bị mất hiệu lực vì:

- Database restart, failover hoặc đóng session.
- Firewall/NAT/load balancer xóa kết nối TCP nhàn rỗi.
- Network partition, rớt VPN, lỗi DNS khi tái kết nối hoặc ngắt mạng tạm thời.
- Database chủ động đóng idle sessions do giới hạn tài nguyên hoặc timeout.
- Pool giữ một kết nối nhàn rỗi lâu hơn thời gian sống do hạ tầng cho phép.
- Driver phát hiện lỗi giao thức hoặc lỗi kết nối nghiêm trọng.

Đây là lý do JDBC có **`Connection.isValid(int timeout)`**: yêu cầu driver **chủ động xác minh** rằng connection còn hợp lệ thay vì chỉ nhìn một cờ trạng thái cục bộ.

Cần phân biệt ba câu hỏi:

1. **`connection.isClosed()`**: object có đang được đánh dấu đã đóng theo hợp đồng JDBC không?
2. **`connection.isValid(timeout)`**: driver có thể kiểm tra và xác nhận connection hiện còn hợp lệ trong giới hạn thời gian không?
3. **Thao tác nghiệp vụ tiếp theo có thành công không?** Chỉ biết chắc khi chính thao tác đó thực hiện; tình trạng mạng có thể đổi ngay sau khi kiểm tra.

Thông điệp chính: **`isClosed() == false` không chứng minh kết nối còn sống; `isValid(...) == true` chỉ là quan sát tại thời điểm kiểm tra, không phải bảo đảm tương lai.**

~~~text
Ứng dụng / Connection pool
            |
            v
    Connection object
            |
       isClosed()?
            |
   +--------+--------+
   |                 |
  true              false
   |                 |
   v                 v
Đã đóng       Không đủ để kết luận
                       |
                       v
                isValid(timeout)
                       |
         +-------------+-------------+
         |             |             |
        true          false       SQLException
         |             |             |
         v             v             v
    Có tín hiệu      Không hợp lệ  Lỗi lúc kiểm tra
    hợp lệ lúc      / hết thời gian;  / lỗi input
    kiểm tra        loại bỏ/recreate  theo driver
         |
         v
   Thực hiện công việc
   VẪN phải xử lý SQLException
~~~

`Connection.isValid` nằm trong API `java.sql` tiêu chuẩn, có từ JDBC 4.0/Java 6 và **vẫn là cách kiểm tra connection hiện hành trên Java 17+**. Nó không phải tính năng đã legacy.

## 2. Hợp đồng chính xác của `Connection.isValid(int timeout)`

Phương thức:

~~~java
boolean isValid(int timeout) throws SQLException;
~~~

Đây là **chữ ký API**, không phải chương trình độc lập. Trong Java 17+, một cách gọi thường gặp:

~~~java
boolean alive = connection.isValid(2);
~~~

Ở đây `connection` là đối tượng `Connection` do driver/JDBC pool trả về.

Theo tài liệu Java SE:

- `true` nếu connection **chưa đóng và vẫn hợp lệ**.
- `false` nếu connection không hợp lệ **hoặc** operation kiểm tra không hoàn tất trước timeout.
- Driver phải gửi **một query** trên connection hoặc dùng **cơ chế khác thực sự xác minh connection còn hợp lệ**. Chỉ kiểm tra một biến `boolean open` cục bộ là **không đủ** để một driver thật đáp ứng yêu cầu này.
- Nếu driver dùng query để xác minh, query đó phải chạy trong **ngữ cảnh transaction hiện tại** của connection.
- `timeout` là **số giây** chờ operation validation.
- Nếu `timeout == 0`, **không áp timeout** cho operation validation. Điều này **không có nghĩa là kiểm tra tức thời**.
- Nếu `timeout < 0`, lời gọi phải báo `SQLException` theo hợp đồng.
- `isValid` có thể là một operation liên quan đến I/O và có chi phí; không phải accessor thuần bộ nhớ.

### 2.1. Bảng ý nghĩa tham số timeout

| Lệnh | Ý nghĩa |
| --- | --- |
| `connection.isValid(1)` | Driver có tối đa khoảng một giây theo hạn mức operation validation |
| `connection.isValid(3)` | Yêu cầu thời hạn validation ba giây |
| `connection.isValid(0)` | Không giới hạn thời gian validation **bởi tham số này** |
| `connection.isValid(-1)` | Không hợp lệ; phát `SQLException` |
| `connection.isValid()` | **Không tồn tại** overload không tham số trong interface JDBC `Connection` |

Khi dùng một timeout khác không, vẫn cần kiểm tra khả năng và cấu hình driver. Một số giới hạn khác như socket timeout, network timeout và hệ điều hành có thể ảnh hưởng hành vi thực tế. **Không coi `isValid(2)` là một cam kết hard real-time chính xác tới mili giây trên mọi driver/platform**, nhưng theo hợp đồng driver phải áp thời hạn cho hoạt động validation.

### 2.2. False và exception khác nhau ra sao?

Mẫu xử lý đúng:

~~~java
try {
    if (connection.isValid(2)) {
        // Connection hiện đang vượt qua phép kiểm tra của driver.
    } else {
        // Không sử dụng tiếp: false có thể do invalid hoặc hết thời hạn.
    }
} catch (SQLException error) {
    // Lỗi khi thực hiện kiểm tra hoặc tham số không hợp lệ.
}
~~~

Đây là **snippet** trong method đã có `connection`; không phải một chương trình có `main`. Phân biệt `false` với `SQLException` giúp quan sát nguyên nhân:

- `false` không cho biết chính xác database restart, firewall timeout hay driver timeout; nó chỉ cho biết **không nhận được xác nhận hợp lệ**.
- `SQLException` có thể mang `SQLState`, vendor error code và cause hữu ích cho chẩn đoán. Theo JavaDoc, timeout âm là trường hợp được nêu rõ sẽ phát `SQLException`.
- Với health check hay pool validation, cả **false** và **lỗi trong lúc validation** thường khiến connection **không được xem là an toàn để tái sử dụng**. Chính sách cụ thể thuộc pool/ứng dụng.
- Đừng tự chuyển mọi exception trong **truy vấn nghiệp vụ** thành “database đã chết”; lỗi constraint, cú pháp SQL hay quyền truy cập cũng có thể tạo `SQLException` trong khi connection vẫn sử dụng được.

### 2.3. Query của driver có thể thực thi trong transaction đang mở

Đặc tả JDBC nói rằng nếu driver gửi query để validate thì query phải thực thi **trong transaction context hiện tại**.

Ví dụ:

~~~java
connection.setAutoCommit(false);
// Một transaction nghiệp vụ đang mở.
boolean valid = connection.isValid(2);
// Chưa đồng nghĩa transaction đã commit/rollback.
~~~

Đây là snippet trong method có xử lý `SQLException`. Không suy luận rằng `isValid` **tự commit** hay **tự rollback**; đồng thời không coi validation luôn “không hề tương tác transaction”, vì driver có thể thực thi query trong context ấy.

Với transaction dài, cách đơn giản nhất thường là **tránh chèn những health-check round trips không cần thiết** vào giữa logic nghiệp vụ và dựa vào kết quả truy vấn/transaction thực, với error handling phù hợp.

## 3. `isClosed()`, `isValid()` và việc thực thi SQL

### 3.1. Vì sao `isClosed()` không đủ?

`Connection.isClosed()` chỉ hỏi trạng thái đóng của connection object. Theo JavaDoc, method này chỉ được bảo đảm trả `true` sau khi `close()` được gọi (và có thể trả `true` trong một số trạng thái lỗi nghiêm trọng do driver nhận diện). Nó **không được thiết kế để phát hiện mọi trường hợp kết nối database đã không còn hợp lệ**.

Giả sử hạ tầng đã cắt TCP nhưng driver chưa thực hiện I/O nào. Object có thể vẫn ở trạng thái:

~~~text
isClosed() = false
isValid(2) = false
~~~

Đây là **trường hợp mô phỏng có thể xảy ra**, không phải kết quả được bảo đảm cho mọi DB. Chỉ khi driver thực hiện validation nó mới có thể nhận ra đường kết nối thực không dùng được.

Ngược lại:

~~~text
connection.close()
isClosed() = true
isValid(2) = false
~~~

đúng với hành vi bình thường của một connection đã được đóng theo hợp đồng.

**Không thay `isValid` bằng `!isClosed` trong code quản lý health.**

### 3.2. Đã `isValid` thành công vẫn phải bắt lỗi SQL

Giữa hai thời điểm:

~~~text
T1: connection.isValid(2) == true
T2: connection.prepareStatement(...).executeQuery()
~~~

mạng có thể ngắt, database có thể failover hoặc session có thể bị đóng. `isValid` tạo **ảnh chụp tức thời**, không khóa database vào trạng thái hoạt động cho tất cả thao tác tiếp theo.

Do đó:

~~~java
try (PreparedStatement statement =
        connection.prepareStatement("SELECT id FROM items WHERE id = ?")) {
    statement.setLong(1, id);
    try (ResultSet result = statement.executeQuery()) {
        // Đọc kết quả.
    }
} catch (SQLException e) {
    // Xử lý lỗi nghiệp vụ/I/O thực tế; phân loại phù hợp.
}
~~~

Đây là snippet minh họa cần biến `connection` và `id`; **không phải ứng dụng độc lập**, và bảng `items` chỉ là giả định. Validation trước đó **không loại bỏ yêu cầu xử lý `SQLException` ở đây**.

Một chiến lược đáng tin cậy thường là để pool quản lý việc lấy connection hợp lệ, rồi ứng dụng **thực thi operation và xử lý lỗi thật**, thay vì luôn ping trước mỗi câu SQL.

## 4. JDBC driver thực hiện health probe ra sao?

Hợp đồng `isValid(...)` không buộc tất cả database phải có một câu SQL cụ thể. Driver có thể:

- Gửi một câu truy vấn nhẹ tương thích dialect của database.
- Dùng cơ chế protocol-level ping/round trip, nếu driver hỗ trợ và nó thật sự xác minh session.
- Sử dụng cách khác được nhà phát triển driver thiết kế, miễn thỏa hợp đồng JDBC.

Do vậy **`isValid(2)` không tương đương chắc chắn `SELECT 1`**. Một driver có thể không gửi chuỗi SQL ấy, hoặc gửi hoạt động validation khác.

### 4.1. Tại sao ưu tiên `isValid` thay cho tự viết `SELECT 1`?

Nếu viết thủ công:

~~~java
try (Statement statement = connection.createStatement();
     ResultSet ignored = statement.executeQuery("SELECT 1")) {
    return ignored.next();
}
~~~

đây là **snippet minh họa ý tưởng**, không phải code có thể dùng cho mọi DB:

- Không phải tất cả SQL dialect và JDBC driver có cùng yêu cầu cú pháp.
- Bạn phải tự cấu hình `Statement.setQueryTimeout(...)`, xử lý exception và đóng resource.
- Query có thể tạo transaction work và round trip khác với cơ chế chuyên biệt của driver.
- Nếu pool đã có phép validation, thêm query này có thể nhân đôi chi phí.

Trong hệ sinh thái JDBC hiện đại, **ưu tiên `Connection.isValid` nếu driver hỗ trợ đúng chuẩn**. Ví dụ tài liệu HikariCP khuyên không cấu hình `connectionTestQuery` cho driver JDBC 4 tuân thủ `isValid`; query tuỳ chỉnh chủ yếu dành cho trường hợp driver không thể dùng API tiêu chuẩn.

### 4.2. Nếu driver không tương thích thì sao?

Một driver đời cũ hoặc implementation không đúng chuẩn có thể xử lý `isValid` không đầy đủ. Với dự án Java 17+, nên:

1. Nâng lên **JDBC driver còn được bảo trì** tương thích với DB server và JDK đang chạy.
2. Kiểm thử `isValid(timeout)` trong integration environment, gồm tình huống mạng ngắt và database restart.
3. Cấu hình pool theo tài liệu driver khi có một trường hợp đặc thù cần `connectionTestQuery`.
4. Không đưa một câu `SELECT 1` tự viết vào mọi nơi như fallback mặc định, rồi làm mất lợi thế chuẩn hóa của JDBC 4.

Không phụ thuộc vào API JDBC đã bị thay thế hoặc driver không được hỗ trợ chỉ để duy trì một cơ chế validation cũ.

## 5. Timeout: giây, mili giây và các loại thời hạn khác nhau

Một trong những bug nghiêm trọng nhất là **trộn đơn vị**.

| API / cấu hình | Đơn vị | Phạm vi |
| --- | --- | --- |
| `Connection.isValid(int timeout)` | **Giây** | Thời gian chờ operation kiểm tra connection |
| `Statement.setQueryTimeout(int seconds)` | **Giây** | Giới hạn cho các thao tác execute của Statement |
| `Connection.setNetworkTimeout(Executor, int milliseconds)` | **Mili giây** | Giới hạn chờ phản hồi database của network requests theo driver |
| `DriverManager.setLoginTimeout(int seconds)` | **Giây** | Thời gian đợi quá trình thiết lập login/connection, theo driver |
| `HikariCP.validationTimeout` | **Mili giây** | Giới hạn cấu hình validation của pool |
| `HikariCP.connectionTimeout` | **Mili giây** | Thời gian caller chờ mượn connection từ pool |

**Không có phép chuyển đổi ngầm giữa các API này.**

Ví dụ:

~~~java
boolean ready = connection.isValid(3); // 3 giây
~~~

không giống:

~~~java
connection.setNetworkTimeout(executor, 3000); // 3000 mili giây
~~~

Hai snippet minh họa hai phương thức khác nhau. Snippet thứ hai cần một `Executor executor` thích hợp do ứng dụng/pool cung cấp; driver có thể không hỗ trợ `setNetworkTimeout` và ném `SQLFeatureNotSupportedException`. Đừng thêm nó chỉ để “làm cho isValid nhanh hơn” khi pool đã quản lý network timeout.

### 5.1. `isValid(0)` không phải kiểm tra “0 giây”

`0` **vô hiệu hóa timeout của operation validation**. Trong sự cố mạng, việc không có giới hạn rõ ràng có thể khiến thread chờ lâu tùy driver/socket/OS. Khi cần health check với latency budget, chọn một số giây dương và kiểm chứng driver thực sự áp hạn mức.

Cẩn thận: `isValid` không phải công cụ đặt timeout khi **mở connection**. `DriverManager.getConnection(...)` hoặc `DataSource.getConnection()` có cơ chế cấu hình connection/login/socket timeout riêng.

### 5.2. `setNetworkTimeout` không phải một bản sao của `isValid`

`setNetworkTimeout` có thể làm driver **đánh dấu connection đã đóng** nếu request chờ phản hồi database quá hạn; nó là cơ chế giới hạn I/O nghiêm ngặt hơn. Trong khi đó, `isValid(timeout)` trả `false` khi operation validation hết hạn theo hợp đồng; không nên mặc định mọi driver sẽ đóng connection khi `isValid` trả `false`.

Nếu pool đã quản lý network timeout, việc thay đổi thủ công trên borrowed connection có thể làm hỏng giả định của pool. Hãy để pool và driver thực hiện chính sách giới hạn chung thay vì thay chúng tùy tiện trong mỗi business request.

### 5.3. Đừng dùng một thread khác chỉ để áp timeout mà bỏ mặc I/O đang chạy

Mẫu nguy hiểm:

~~~text
Future<Boolean> future = executor.submit(() -> connection.isValid(0));
future.get(2, SECONDS);   // hết hạn từ phía caller
// ... rồi coi I/O trên connection đã chấm dứt
~~~

Đây là **sơ đồ anti-pattern**, không phải chương trình hoàn chỉnh. `Future.get(...)` hết hạn **không bảo đảm** I/O JDBC đã dừng hoặc connection vẫn ở trạng thái an toàn. Nếu timeout ở tầng caller mà driver thread còn hoạt động, việc tái sử dụng connection ngay sau đó có thể gây chồng thao tác. Ưu tiên timeout hỗ trợ bởi driver/pool và chính sách đóng/bỏ kết nối có lỗi.

## 6. Khi nào nên gọi `isValid`?

### 6.1. Trường hợp phù hợp

- **Pool validation:** trước khi cấp lại một connection đã nhàn rỗi lâu, theo chính sách của connection pool.
- **Health probe có giới hạn:** kiểm tra một connection lấy từ `DataSource` với timeout nhỏ và đóng/trả nó sau kiểm tra.
- **Sau sự cố đã nhận biết:** kiểm tra connection theo một quy trình recovery được thiết kế, thường do pool quản lý.
- **Integration testing driver:** xác minh driver thực sự phát hiện kết nối đã bị đóng ở phía database hoặc đường mạng.
- **Chẩn đoán:** khi phân biệt object đã đóng với session vẫn mở nhưng không thể liên lạc.

### 6.2. Trường hợp không nên lạm dụng

- **Trước mỗi truy vấn:** validation có thể là một round trip thừa, làm tăng latency và tải DB.
- **Giữa transaction dài:** có thể gây thêm I/O trong transaction hiện tại.
- **Để thay thế xử lý exception SQL:** trạng thái có thể thay đổi ngay sau probe.
- **Làm bằng chứng nghiệp vụ:** `isValid` không xác nhận schema/migration, quyền SELECT, replication lag hay một bảng cụ thể.
- **Trên một connection dùng chung nhiều thread không kiểm soát:** JDBC Connection thường không phải resource nên được thao tác đồng thời tùy tiện; pool cấp connection theo ownership mỗi request.

Nếu đang dùng một **connection pool hiện đại**, hãy để pool quyết định **khi nào** cần validate, thay vì mỗi function nghiệp vụ lại tự ping. Code ở tầng ứng dụng nên dùng `DataSource` để mượn/trả connection và xử lý đúng lỗi thực tế.

## 7. Ví dụ Java 17+ tự chạy: mô phỏng trạng thái của JDBC Connection

### 7.1. Vì sao ví dụ này dùng test double?

JDK cung cấp `java.sql` nhưng **không tự đi kèm một JDBC driver và database hoạt động cho tất cả môi trường**. Một chương trình muốn chứng minh mạng thật phải có DB server, driver JAR, credentials và kết nối mà người học có thể truy cập.

Để đảm bảo bài học có **ví dụ hoàn chỉnh, tự biên dịch và chạy được chỉ với Java 17+**, phần này dùng **dynamic proxy mô phỏng `Connection`**. Nó kiểm tra **logic ứng dụng** quanh `isValid`, không giả mạo việc đã thực hiện một DB round trip thật.

Test double mô phỏng:

- Connection đang mở và backend reachable → `isValid(2) == true`.
- Backend được đánh dấu unreachable nhưng connection chưa bị gọi `close()` → `isClosed() == false`, `isValid(2) == false`.
- Probe gặp lỗi driver → ném `SQLException`.
- Timeout âm → ném `SQLException` với SQLState mô phỏng `HY092`.
- Gọi `close()` → `isClosed() == true` và `isValid(2) == false`.

**Giới hạn:** test double dùng `AtomicBoolean` để tạo trạng thái, **không đáp ứng yêu cầu round trip của một JDBC driver production**; nó chỉ được dùng cho unit/demo test. Phần 8 có ví dụ kết nối database thật khi người đọc có driver và DB.

### 7.2. Source hoàn chỉnh: `JdbcHealthDemo.java`

~~~java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Proxy;
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import java.util.concurrent.atomic.AtomicBoolean;

public class JdbcHealthDemo {
    enum Health { VALID, INVALID, ERROR }

    static Health check(Connection connection, int timeoutSeconds) {
        try {
            return connection.isValid(timeoutSeconds)
                    ? Health.VALID : Health.INVALID;
        } catch (SQLException e) {
            return Health.ERROR;
        }
    }

    static Connection simulatedConnection(
            AtomicBoolean reachable, AtomicBoolean probeThrows) {
        AtomicBoolean closed = new AtomicBoolean(false);

        InvocationHandler handler = (proxy, method, args) -> {
            switch (method.getName()) {
                case "isValid" -> {
                    int seconds = (Integer) args[0];
                    if (seconds < 0) {
                        throw new SQLException(
                                "Negative validation timeout", "HY092");
                    }
                    if (closed.get()) {
                        return false;
                    }
                    if (probeThrows.get()) {
                        throw new SQLException(
                                "Simulated transport failure", "08006");
                    }
                    return reachable.get();
                }
                case "isClosed" -> {
                    return closed.get();
                }
                case "close" -> {
                    closed.set(true);
                    return null;
                }
                case "toString" -> {
                    return "SimulatedJdbcConnection";
                }
                default -> throw new SQLFeatureNotSupportedException(
                        method.getName() + " is not implemented in test double");
            }
        };

        return (Connection) Proxy.newProxyInstance(
                Connection.class.getClassLoader(),
                new Class<?>[] {Connection.class}, handler);
    }

    public static void main(String[] args) throws SQLException {
        AtomicBoolean reachable = new AtomicBoolean(true);
        AtomicBoolean probeThrows = new AtomicBoolean(false);
        Connection connection =
                simulatedConnection(reachable, probeThrows);

        try (connection) {
            System.out.println("Initially closed: " + connection.isClosed());
            System.out.println("Initially valid: " + check(connection, 2));

            reachable.set(false);
            System.out.println("Closed after simulated outage: "
                    + connection.isClosed());
            System.out.println("After simulated outage: "
                    + check(connection, 2));

            reachable.set(true);
            probeThrows.set(true);
            System.out.println("On simulated SQLException: "
                    + check(connection, 2));

            probeThrows.set(false);
            try {
                connection.isValid(-1);
                throw new AssertionError("Negative timeout accepted");
            } catch (SQLException expected) {
                System.out.println("Negative timeout SQLState: "
                        + expected.getSQLState());
            }
        }

        System.out.println("Closed after try-with-resources: "
                + connection.isClosed());
        System.out.println("After close: " + check(connection, 2));
    }
}
~~~

Các import đều thuộc Java SE. `Proxy.newProxyInstance(...)` tạo một object triển khai `Connection` mà không cần tự viết hàng chục method của interface. `InvocationHandler` nhận tên method và mô phỏng chỉ những lời gọi cần thiết:

- `isValid` kiểm tra timeout và trạng thái giả lập.
- `isClosed` đọc biến trạng thái đóng.
- `close` chuyển trạng thái đóng; `try-with-resources` gọi method này.
- Các JDBC methods khác ném `SQLFeatureNotSupportedException` để không bị hiểu nhầm là có khả năng query database thật.

`AtomicBoolean` ở đây cho phép điều chỉnh trạng thái test rõ ràng. Nó **không chứng minh một connection thật nên được chia sẻ giữa nhiều thread**.

### 7.3. Phương thức `check(...)` và ba trạng thái

Thay vì chỉ trả `boolean`, hàm demo phân biệt:

| Trạng thái | Diễn giải |
| --- | --- |
| `Health.VALID` | Driver/test double xác nhận connection hợp lệ tại thời điểm probe |
| `Health.INVALID` | `isValid` trả false — không thể tin cậy connection để dùng tiếp |
| `Health.ERROR` | `isValid` phát `SQLException`, cần chẩn đoán; không coi connection đã được xác nhận |

Điểm mạnh của ba trạng thái là dễ phân loại **metrics/logs** trong test. Tuy nhiên ứng dụng production **không nên luôn nuốt `SQLException`** như phương thức demo: nơi có chẩn đoán và phục hồi cần ghi nhận SQLState, nguyên nhân và quyết định có thay connection/thoát request hay không. Hàm demo dùng enum chỉ để output ổn định, tránh log hệ thống phụ thuộc driver.

### 7.4. Biên dịch và chạy

Lưu file đúng tên `JdbcHealthDemo.java` rồi chạy:

~~~sh
javac --release 17 JdbcHealthDemo.java
java JdbcHealthDemo
~~~

**Stdout chính xác** (đã biên dịch bằng JDK 24 với `--release 17` và chạy):

~~~text
Initially closed: false
Initially valid: VALID
Closed after simulated outage: false
After simulated outage: INVALID
On simulated SQLException: ERROR
Negative timeout SQLState: HY092
Closed after try-with-resources: true
After close: INVALID
~~~

Các dòng trên được tạo từ **mô phỏng được kiểm soát**, không phải phép đo một database thật.

### 7.5. Điều cần rút ra từ output

1. Hai dòng đầu cho thấy trạng thái bình thường: object chưa đóng và validation xác nhận hợp lệ.
2. `Closed after simulated outage: false` rồi `After simulated outage: INVALID` chứng minh **`isClosed` không thay thế `isValid`**.
3. `On simulated SQLException: ERROR` cho thấy nhánh exception cần được xử lý riêng.
4. `HY092` là **SQLState do test double đặt ra**, minh họa cách thu thập mã lỗi; không phải cam kết rằng mọi JDBC driver dùng đúng SQLState ấy cho timeout âm.
5. `try-with-resources` gọi `close` nên output cuối báo object đã đóng và không còn hợp lệ.

**Phạm vi kiểm thử:** mọi nhánh demo đã chạy đúng với Java 17 syntax. Để xác minh mạng thật, driver và database là điều kiện bên ngoài; không suy ra từ mock rằng một driver production đã được chứng thực hoạt động.

## 8. Ví dụ thứ hai: gọi `isValid` trên database thật khi có JDBC driver

Dùng `DriverManager` giúp minh họa nhanh một phép probe thực. Trong ứng dụng server lâu dài, **`DataSource` và connection pool thường là lựa chọn tốt hơn**; `DriverManager` chủ yếu tiện cho công cụ nhỏ, test hoặc code học tập.

### 8.1. Chương trình `LiveJdbcProbe.java`

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.Properties;

public class LiveJdbcProbe {
    public static void main(String[] args) throws SQLException {
        String url = System.getenv("JDBC_URL");
        if (url == null || url.isBlank()) {
            System.out.println("Set JDBC_URL and provide a JDBC driver.");
            return;
        }

        Properties properties = new Properties();
        String user = System.getenv("JDBC_USER");
        String password = System.getenv("JDBC_PASSWORD");
        if (user != null) properties.setProperty("user", user);
        if (password != null) properties.setProperty("password", password);

        try (Connection connection =
                     DriverManager.getConnection(url, properties)) {
            boolean valid = connection.isValid(3);
            System.out.println("Reachable now: " + valid);
            if (!valid) {
                throw new SQLException("Connection validation failed");
            }
        }
    }
}
~~~

**Lệnh biên dịch thuần JDK:**

~~~sh
javac --release 17 LiveJdbcProbe.java
~~~

Đã biên dịch thành công với JDK 24, không cần driver JAR ở **thời điểm compile** vì chương trình chỉ tham chiếu các interface JDBC chuẩn.

Nếu **chưa cung cấp `JDBC_URL`**, lệnh:

~~~sh
java LiveJdbcProbe
~~~

in **stdout chính xác**:

~~~text
Set JDBC_URL and provide a JDBC driver.
~~~

Đã kiểm thử nhánh không có cấu hình. Đây là nhánh phòng vệ, **không** thực hiện kết nối database.

### 8.2. Chạy với một driver thật

Khi đã có database, driver JAR tương thích và credentials, cấu hình biến môi trường `JDBC_URL`, `JDBC_USER`, `JDBC_PASSWORD`. Ví dụ URL dành cho PostgreSQL:

~~~text
jdbc:postgresql://localhost:5432/appdb
~~~

Đây là **ví dụ cú pháp URL**, không phải khẳng định trên máy học có một PostgreSQL server ở đó. Hãy dùng hostname/database thật của môi trường mà bạn có quyền truy cập.

Đưa driver vào runtime classpath. Trên Linux/macOS, **mẫu lệnh**:

~~~sh
java -cp ".:/path/to/postgresql-driver.jar" LiveJdbcProbe
~~~

Trên Windows PowerShell/cmd, dấu phân cách classpath là `;`:

~~~powershell
java -cp ".;C:\drivers\postgresql-driver.jar" LiveJdbcProbe
~~~

Những đường dẫn driver trong hai lệnh là **ví dụ để thay bằng đường dẫn JAR thực tế**, không phải file đã được tạo sẵn.

Nếu kết nối được thiết lập và driver xác nhận hợp lệ, stdout:

~~~text
Reachable now: true
~~~

Nếu driver trả false, chương trình in `Reachable now: false` rồi ném `SQLException` với thông báo đã viết. Nếu không kết nối được, `DriverManager.getConnection(...)` có thể ném `SQLException` ngay **trước khi gọi `isValid`**. Không có DB/driver thực tế trong môi trường kiểm thử của bài, vì thế **chưa xác minh nhánh live database bằng runtime**.

### 8.3. Không hardcode credentials hoặc lộ thông tin trong log

Bài thực hành đọc credentials từ biến môi trường để tránh đặt trực tiếp trong source. Với production, cân nhắc secret manager, cấu hình TLS, IAM/database auth và luồng cấp/luân chuyển secrets. Biến môi trường cũng không phải giải pháp bảo mật tuyệt đối; giá trị có thể lộ qua cấu hình, process inspection hoặc logs nếu hệ thống vận hành sai.

Không in URL chứa password, không log properties nguyên vẹn và không trả SQL exception chi tiết của nội bộ database cho người dùng cuối. Nếu cần log lỗi kết nối, ghi metadata đã loại dữ liệu bí mật, SQLState, vendor code và context phù hợp.

## 9. Dùng `DataSource` trong ứng dụng thực tế

`javax.sql.DataSource` là cách cấu hình, quản lý và lấy connection được JavaDoc khuyến nghị cho nhiều ứng dụng. Một `DataSource` có thể do pool cung cấp và quản lý các kết nối vật lý ở phía sau.

Ví dụ health-check function:

~~~java
import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class DatabaseReadiness {
    private DatabaseReadiness() {}

    public static boolean reachable(DataSource source) {
        try (Connection connection = source.getConnection()) {
            return connection.isValid(2);
        } catch (SQLException e) {
            return false;
        }
    }
}
~~~

Đây là **class Java 17+ hợp lệ**, nhưng cần caller cung cấp một `DataSource` thật được cấu hình. `reachable(...)` không phải test network tự chạy vì nó không tự tạo DB hoặc pool.

Ý nghĩa:

1. Mượn connection từ nguồn dữ liệu.
2. Gọi validation với timeout ngắn.
3. Khi kết thúc hoặc gặp exception, `try-with-resources` gọi `close()` trên connection đã mượn.
4. Nếu đây là pool proxy, `close()` thường nghĩa là **trả logical connection về pool** (pool quyết định có nên loại bỏ physical connection). Không tự giả định mọi `close()` đều đóng socket vật lý.
5. Nếu validation trả false hoặc ném exception, health result là `false`; pool/driver phải được cấu hình xử lý connection hỏng. Không cố tái sử dụng một connection vừa bị đánh dấu không an toàn.

Trong chương trình production, có thể giữ exception để log/metrics:

~~~java
try (Connection c = source.getConnection()) {
    if (!c.isValid(2)) {
        // Ghi nhận failure; trả trạng thái not-ready.
    }
} catch (SQLException e) {
    // Ghi SQLState, vendorCode, loại lỗi nhưng không lộ secret.
}
~~~

Đây là **snippet** có biến `source` đã được cung cấp, không phải chương trình độc lập.

### 9.1. Readiness, liveness và “DB reachable” không giống nhau

Nếu triển khai trong container orchestration:

- **Liveness:** ứng dụng còn xử lý được event loop/request cơ bản hay không. Không phải lúc nào cũng nên buộc nó phụ thuộc DB đang tạm mất.
- **Readiness:** instance có sẵn sàng nhận traffic nghiệp vụ không; có thể phụ thuộc vào việc mượn connection và query các nguồn thiết yếu.
- **Connection validation:** một connection cụ thể được driver xem là hợp lệ tại thời điểm ping.

Chỉ một `connection.isValid(2)` **không chứng minh** migrations đúng, table tồn tại, DB user có quyền đọc/ghi, replica theo kịp primary hoặc dịch vụ bên ngoài khác sẵn sàng. Với readiness có yêu cầu nghiệp vụ, cân nhắc một **read-only query tối thiểu** đúng hợp đồng hệ thống, nhưng không thay mọi health probe bằng transaction tốn kém.

Tránh chạy phép kiểm tra database quá dày khiến health-check tự làm tăng tải, làm sự cố nặng hơn. Kết hợp timeout, cadence, caching ngắn và threshold theo thiết kế vận hành.

## 10. `Connection.isValid` trong connection pool

Nhiều ứng dụng Java hiện đại dùng connection pool như HikariCP, Agroal hoặc pooling tích hợp trong application server. Pool duy trì một tập physical connections để giảm chi phí mở/kết nối lại database cho mỗi request.

Vai trò của pool:

~~~text
Pool (physical connections)
  |
  +--> idle healthy
  +--> idle stale
  +--> in-use
  |
  v
Borrow connection
  |
  +--> Pool có thể kiểm tra validity theo policy
  |    (ví dụ gọi JDBC4 Connection.isValid(timeout))
  |
  v
Ứng dụng dùng logical Connection
  |
  +--> SQL operations, transaction
  |
  v
close() logical connection
  |
  +--> Pool quyết định reuse / discard / replace
~~~

### 10.1. `isValid` thường được pool gọi thay bạn

Tài liệu HikariCP hiện hành ghi rằng, với driver JDBC4 phù hợp, nên **không cấu hình `connectionTestQuery`** và để pool dùng cơ chế validation `Connection.isValid(...)` mặc định. Điều này tránh query validation SQL tùy chỉnh không cần thiết.

Đừng hiểu lầm: dùng pool không có nghĩa mỗi lần borrow đều bắt buộc được ping trong mọi điều kiện. Pool có các tối ưu và chính sách validation để cân bằng latency với độ an toàn, cũng như keepalive trên idle connections khi được cấu hình.

**Không tự xây vòng lặp ping bằng `isValid` trên tất cả physical connections của pool**, vì pool đã sở hữu lifecycle và synchronization của chúng.

### 10.2. Các cấu hình pool quan trọng nhưng khác nhau

Với HikariCP, những tên cấu hình cần hiểu:

| Cấu hình | Mục đích |
| --- | --- |
| `validationTimeout` | Giới hạn thời gian pool được phép validation (đơn vị **mili giây**) |
| `connectionTimeout` | Thời gian mượn connection từ pool trước khi fail (mili giây) |
| `maxLifetime` | Tuổi thọ tối đa của physical connection trong pool |
| `idleTimeout` | Kiểm soát loại bỏ idle connections khi điều kiện pool phù hợp |
| `keepaliveTime` | Chu kỳ ping connection nhàn rỗi để hạn chế bị hạ tầng đóng |
| `connectionTestQuery` | Câu SQL validation tùy chỉnh khi thật sự cần; thường bỏ qua nếu JDBC4 driver hỗ trợ `isValid` |

Không lấy số `2000` trong `validationTimeout=2000` rồi truyền vào `isValid(2000)`; cái thứ nhất là **2.000 ms**, cái thứ hai là **2.000 giây**. Pool thường có logic đổi đơn vị và kết hợp network timeout riêng.

Với một driver tốt, cấu hình connection pool đúng lifecycle/keepalive thường hữu ích hơn việc thêm một `connection.isValid` nữa vào mọi phương thức repository.

### 10.3. Chọn `maxLifetime` ngắn hơn giới hạn hạ tầng

Nếu database hoặc hạ tầng đóng connection sau một khoảng thời gian cố định, pool nên có chính sách retirement phù hợp thay vì để stale physical connection tồn tại quá lâu. Pool có thể tự thay connection đã hết hạn.

Tuy nhiên, max lifetime/idle timeout cần được xác định từ điều kiện deploy thực, không copy giá trị trên blog cho mọi hệ thống. Quan sát database connection cap, firewall idle timeout, pool sizing, failover, traffic pattern và tỷ lệ validation errors.

## 11. Chiến lược lỗi và phục hồi sau khi `isValid` thất bại

Một câu hỏi quan trọng: **isValid trả false thì có nên retry ngay trên cùng Connection?**

Thông thường, **không**. Connection chưa được xác nhận hợp lệ, có thể bị hỏng về protocol/session state. Nếu đang sử dụng pool, trả/đóng logical handle để pool quản lý và lấy **connection mới** cho request tiếp theo theo policy retry của ứng dụng.

### 11.1. Retry chỉ có ý nghĩa theo transaction semantics

Giả sử đang thực hiện lệnh ghi tiền hoặc tạo đơn hàng:

~~~text
START TRANSACTION
UPDATE balances ...
network error xảy ra khi COMMIT
~~~

Khi gặp lỗi, **không được tự gọi lại toàn bộ transaction mà không biết commit trước đó đã thành công chưa**. `isValid` sau lỗi không trả lời “transaction trước đã commit hay chưa”; nó chỉ kiểm tra hiện connection còn hợp lệ hay không.

Chiến lược phục hồi cần:

- Phân loại lỗi có thể retry hay không (SQLState, vendor code, loại operation).
- Dùng **idempotency key** hoặc cơ chế chống ghi trùng khi retry request quan trọng.
- Hiểu kết quả không xác định của transaction đang chờ commit.
- Để pool tạo connection mới nếu connection cũ bị lỗi giao thức.
- Sử dụng backoff và giới hạn số lần thử để tránh retry storm khi database đang outage.

**Không biến `isValid` thành công thành giấy phép retry transaction đã thất bại mà không xem xét atomicity.**

### 11.2. `SQLState` giúp chẩn đoán nhưng không phải rule toàn năng

`SQLException` có:

~~~java
String sqlState = e.getSQLState();
int vendorCode = e.getErrorCode();
SQLException next = e.getNextException();
~~~

Đây là snippet trong một `catch (SQLException e)`. Nhiều driver dùng SQLState class `08` để biểu thị các lỗi liên quan đến connection, nhưng cách báo lỗi cụ thể và vendor codes phụ thuộc driver. Không giả định mọi `SQLException` là lỗi mạng.

Ngược lại, `SQLException` do dữ liệu vi phạm unique constraint không mặc nhiên có nghĩa connection cần bị bỏ. Pool có logic phát hiện exception làm connection không còn dùng được; đừng override cơ chế đó chỉ bằng một `catch` chung.

### 11.3. Khi `close()` cũng phát exception

`Connection.close()` khai báo `throws SQLException`. `try-with-resources` đảm bảo cố đóng resource khi rời scope. Nếu vừa có lỗi nghiệp vụ vừa có lỗi đóng connection, Java có cơ chế **suppressed exceptions**; đừng chỉ nhìn exception ngoài cùng rồi làm mất nguyên nhân.

Nếu dùng pool, `close()` thường trả handle; nếu lỗi xảy ra khi trả về pool, cần xử lý theo tiêu chuẩn framework. Không nuốt hết lỗi và vẫn báo success cho transaction.

## 12. Cần kiểm tra trạng thái kết nối lúc nào trong transaction?

### 12.1. Trước transaction

Lúc pool cho mượn connection, validation có thể hữu ích nếu connection đã idle lâu. Sau đó ứng dụng bắt đầu transaction.

~~~text
borrow -> (pool validates if needed) -> begin transaction
                                  -> business SQL
                                  -> commit/rollback
                                  -> return connection
~~~

Một lần kiểm tra hợp lý tại ranh giới lifecycle có thể phát hiện stale sessions trước khi business SQL gặp lỗi. Nhưng **không có bảo đảm 100%** do network có thể ngắt sau validation.

### 12.2. Trong transaction

Vì validation query của driver phải thực thi **trong current transaction context**, chèn `isValid` nhiều lần giữa các thao tác có thể tăng latency và khiến transaction giữ locks lâu hơn.

Không dùng `isValid` như heartbeat cho transaction kéo dài. Nếu một transaction phải tồn tại lâu, nên xem lại thiết kế nghiệp vụ/timeout/connection ownership; transaction dài thường tiềm ẩn rủi ro khác ngoài health validation.

### 12.3. Khi transaction thất bại

Sau `SQLException` nghiêm trọng trong transaction:

- Đừng mặc định rollback có thể luôn thành công nếu connection đã mất liên lạc.
- Không cố tiếp tục dùng connection chỉ vì `isClosed()` vẫn false.
- Nếu trạng thái commit không rõ, cần reconcile với dữ liệu/idempotency theo nghiệp vụ.
- Để pool/driver quyết định có loại bỏ physical connection và tái tạo session hay không.
- Bổ sung logging đúng lớp để phân biệt DB outage với business constraint errors.

## 13. Testing: không trộn unit test giả lập với integration test thật

Bài này gồm hai cấp kiểm thử có mục tiêu riêng.

| Cấp | Test cái gì? | Cần database thật? |
| --- | --- | --- |
| Unit test với dynamic proxy | Code xử lý true/false/SQLException, closed state, timeout âm | **Không** |
| Driver integration test | Driver thực sự gửi validation round trip và áp timeout | **Có** |
| Pool integration test | Pool loại stale connections và cấp connection mới | **Có** |
| Fault injection | Đóng TCP, restart DB, network partition, idle timeout | **Có hạ tầng kiểm thử an toàn** |
| Production monitoring | Tỷ lệ validation failures, borrow wait, failover, pool exhaustion | **Có** |

### 13.1. Unit tests quan trọng

Mẫu proxy ở mục 7 có thể được trích thành test fixture. Một bộ test nên bao gồm:

1. `isClosed=false` và `isValid=true` ở trạng thái bình thường.
2. Backend unreachable nhưng `isClosed=false`; `isValid=false`.
3. Driver probe throws `SQLException`; ứng dụng không báo `VALID`.
4. `isValid(-1)` gây `SQLException`.
5. `close()` được gọi khi thoát `try-with-resources`.
6. Sau đóng, `isClosed=true` và `isValid=false`.
7. Không reuse connection sau khi đã nhận kết quả invalid/error.
8. Kiểm tra timeout được truyền **theo giây**, không nhầm milliseconds.

**Đây mới là kiểm thử logic application**, không xác nhận tính tuân thủ JDBC của một driver bên ngoài.

### 13.2. Integration tests có giá trị thực tế

Khi có database thử nghiệm:

1. Mở connection qua driver được sử dụng trong production.
2. Xác minh `isValid(2)` trả true trên connection vừa mở.
3. Tạo tình huống DB đóng session hoặc kill connection được phép trong **test environment**.
4. Xác minh lời gọi `isValid(timeout)` tiếp theo trả false hoặc phát lỗi mà code/pool xử lý an toàn.
5. Đo **thời gian elapsed** thực tế và xác nhận timeout được driver/pool áp hợp lý.
6. Xác minh connection cũ không được tái sử dụng sau khi health check thất bại.
7. Lấy connection mới và xác nhận recovery sau khi DB trở lại.
8. Kiểm tra transaction đang mở hoặc failover trong phạm vi tài nguyên kiểm thử.
9. Kiểm tra health/liveness không gây retry storm hoặc leak resources.

Không thực hiện thử ngắt TCP, stop DB hoặc kill sessions trên production chỉ để chứng minh ví dụ.

### 13.3. Không suy luận thất bại từ việc network request thiếu phản hồi đúng một lần

Trong distributed systems, một validation timeout có thể là kết quả của network latency spike, server overload hoặc đường mạng tạm không ổn định. Vì thế:

- **Một physical connection có lỗi** → không tái sử dụng connection ấy khi chưa được xác nhận.
- **Database service có outage toàn hệ thống** → cần tín hiệu tổng hợp qua nhiều connection/request/metrics, không kết luận chỉ từ một probe.
- **Readiness/liveness** → dùng threshold và backoff phù hợp, tránh chuyển instance liên tục giữa ready/not-ready khi jitter.

Trong thiết kế production, nên theo dõi thời gian mất kết nối, tỷ lệ kết nối hỏng, latency của pool borrow và số lỗi SQLState thay vì log một boolean trơ trọi.

## 14. Observability: ghi gì khi validation thất bại?

Một sự kiện health failure hữu ích có thể có:

~~~text
timestamp
pool_name
database_role_or_alias
validation_timeout_seconds
elapsed_ms
result = false | SQLException
sql_state (nếu có)
vendor_error_code (nếu có)
driver_version (ở mức cấu hình/metadata)
pool_active / pool_idle / pool_pending
~~~

Đây là **schema telemetry minh họa**, không phải một format mặc định của JDBC.

Quy tắc bảo mật:

- Không log password, access token hoặc toàn bộ `Properties` kết nối.
- Cẩn thận URL JDBC nếu URL chứa credentials/secret/hostname nhạy cảm.
- Không ghi mỗi ping thành log error nếu pool thực hiện health check thường xuyên; ưu tiên counters, histograms và rate-limited diagnostics.
- Không dùng exception message thô làm metric label có cardinality không giới hạn.
- Ghi rõ kết quả **validation** khác với **business query failure**.

Nếu dùng HikariCP, pool đã xuất nhiều chỉ số liên quan đến borrow, active, idle, pending và connection timeouts; tận dụng integration metrics sẵn có thay vì tự mở nhiều connection chỉ để đo health.

## 15. Các lỗi phổ biến và cách sửa

| Sai lầm | Tại sao sai | Cách sửa |
| --- | --- | --- |
| Dùng `!connection.isClosed()` như health check | Chưa đóng cục bộ không chứng minh mạng còn hoạt động | `isValid(timeout)` khi thực sự cần check |
| Dùng `isValid(0)` để “không chờ” | `0` nghĩa là **không áp timeout** | Số giây dương phù hợp |
| Truyền `2000` vào `isValid` vì nghĩ mili giây | Thành 2.000 giây | Phân biệt timeout seconds vs pool milliseconds |
| Dùng `isValid(-1)` | Không hợp lệ, gây `SQLException` | Validate cấu hình timeout trước |
| Coi `isValid(true)` như bảo đảm query sau sẽ chạy | TOCTOU: tình trạng mạng có thể đổi | Bắt lỗi SQL tại operation thực |
| Tự chạy `SELECT 1` ở mọi repository | Query dư thừa, có thể không portable | Để driver/pool dùng `isValid` |
| Ping trước mỗi statement | Latency và DB load tăng | Pool quản lý validation theo lifecycle |
| Dùng một connection đã `isValid=false` | Không có xác nhận an toàn | Trả/bỏ connection, mượn connection mới |
| Ném mọi `SQLException` vào nhóm “mất kết nối” | Có cả lỗi dữ liệu/schema/quyền | Phân loại SQLState/vendor/operation |
| Retry write transaction sau lỗi mạng một cách mù quáng | Có thể gây ghi trùng hoặc double-commit effect | Idempotency và recovery theo nghiệp vụ |
| Gọi `isValid` trong transaction như heartbeat liên tục | Tốn I/O, chạy trong current transaction | Probe ở ranh giới hợp lý |
| Đặt `setNetworkTimeout` không xem pool policy | Tác động lên mọi DB requests/driver lifecycle | Cấu hình ở pool/driver và test |
| Dùng test double và tuyên bố DB thật đã reachable | Mock chỉ mô phỏng trạng thái | Integration test với driver/server thật |
| Không đóng/trả connection khi check xong | Leak pool slots/sessions | `try-with-resources` |
| Coi `isValid` là kiểm tra quyền hoặc schema | Nó chỉ xác minh validity của connection | Readiness/business checks chuyên biệt |
| Log password trong sự cố connection | Lộ dữ liệu nhạy cảm | Structured logs có redaction |

## 16. Câu hỏi kiểm tra kiến thức

**Câu 1.** Vì sao `connection.isClosed() == false` chưa đủ để kết luận DB còn reachable?

**Trả lời:** `isClosed` mô tả trạng thái đóng của object và không thực hiện phép xác minh database bắt buộc. Network/session có thể mất trong khi object chưa biết; `isValid` yêu cầu driver xác nhận qua query hoặc cơ chế thích hợp.

**Câu 2.** `connection.isValid(2)` dùng đơn vị gì?

**Trả lời:** **Hai giây** cho operation validation theo hợp đồng JDBC. Không phải hai mili giây.

**Câu 3.** `isValid(0)` có nghĩa gì?

**Trả lời:** Không áp timeout qua tham số validation này. Nó không bảo đảm trả về ngay; cần lưu ý các timeout khác của driver/OS.

**Câu 4.** Khi timeout validation hết hạn trước khi operation hoàn tất, `isValid` trả gì theo JavaDoc?

**Trả lời:** `false`. Khi tham số timeout âm, API nêu trường hợp `SQLException`.

**Câu 5.** Driver có được implement `isValid` bằng cách chỉ đọc một flag “chưa close” mà không xác nhận database không?

**Trả lời:** Không đáp ứng hợp đồng JDBC thật. Driver phải gửi query hoặc một cơ chế **thực sự xác minh** connection còn hợp lệ.

**Câu 6.** `isValid` thực thi query trong transaction nào?

**Trả lời:** Nếu driver dùng query để validate, query ấy chạy trong **current transaction context** của connection theo JavaDoc.

**Câu 7.** Sau `isValid(true)`, câu `UPDATE` ngay sau đó có chắc chắn thành công không?

**Trả lời:** Không. Connection/mạng có thể lỗi giữa hai operation; business SQL phải xử lý `SQLException` và transaction outcome đúng cách.

**Câu 8.** Dùng HikariCP với driver JDBC4 đạt chuẩn, có nên luôn khai báo `connectionTestQuery=SELECT 1`?

**Trả lời:** Không. Tài liệu HikariCP khuyến nghị để pool dùng `Connection.isValid` mặc định nếu driver hỗ trợ đúng chuẩn; query tùy chỉnh chỉ khi có yêu cầu đặc thù.

**Câu 9.** `HikariCP.validationTimeout=2000` tương đương `Connection.isValid(2000)` không?

**Trả lời:** Không. `validationTimeout` tính bằng **mili giây**; `isValid` tính bằng **giây**.

**Câu 10.** Nếu `isValid` trả false trong khi transaction vừa COMMIT bị ngắt mạng, có thể xác định COMMIT chắc chắn chưa thành công không?

**Trả lời:** Không. Validation chỉ kiểm tra khả năng sử dụng connection ở thời điểm gọi; kết quả transaction trước có thể không xác định. Cần cơ chế reconcile/idempotency.

**Câu 11.** Mock `Connection` ở mục 7 có chứng minh JDBC driver thật áp timeout được không?

**Trả lời:** Không. Nó kiểm tra logic ứng dụng và các nhánh kết quả; chỉ integration test trên driver/database thật mới kiểm tra round trip/timeout thực tế.

**Câu 12.** Một readiness check đã trả true thì DB đã có schema phù hợp và đầy đủ quyền nghiệp vụ chưa?

**Trả lời:** Chưa chắc. `isValid` chỉ xác nhận connection, không xác minh bảng, migration, quyền và các dependency khác.

**Ghi nhớ:** Với JDBC hiện đại, **`Connection.isValid(timeout)` là API chuẩn kiểm tra connection**, `timeout` tính bằng **giây** và phải không âm. `isClosed` không phải health check; `isValid` cũng không bảo đảm công việc sau đó sẽ thành công. Trong production, ưu tiên **pool/DataSource** quản lý validation và lifecycle, áp timeout phù hợp, tránh ping dư thừa, luôn xử lý `SQLException` của business SQL, và không retry transaction không idempotent một cách mù quáng.

### Tài liệu chính thức và tham khảo hiện hành

- [Oracle Java SE 26 — java.sql.Connection](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Connection.html): `isValid`, `isClosed`, `setNetworkTimeout`, transaction và `close`.
- [Oracle Java SE 26 — java.sql.Statement](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Statement.html): `setQueryTimeout` và các timeout thực thi.
- [Oracle Java SE 26 — DriverManager](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/DriverManager.html): kết nối, login timeout và service provider drivers.
- [Oracle Java SE 26 — DataSource](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/javax/sql/DataSource.html): nguồn kết nối JDBC.
- [HikariCP — tài liệu cấu hình chính thức](https://github.com/brettwooldridge/HikariCP): `validationTimeout`, `connectionTestQuery`, `keepaliveTime`, `maxLifetime`.
