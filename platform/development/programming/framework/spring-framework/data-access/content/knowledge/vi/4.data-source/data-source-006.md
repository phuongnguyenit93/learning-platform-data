# Kiểm tra kết nối và xử lý kết nối đã hỏng

## 1. Bài toán: một kết nối từng chạy tốt vẫn có thể chết

Trong ứng dụng Spring, `DataSource` cung cấp kết nối JDBC đến cơ sở dữ liệu. Một `Connection` có thể hoạt động tốt khi được tạo, sau đó bị mất vì DB khởi động lại, tường lửa hoặc load balancer đóng kết nối nhàn rỗi, gián đoạn mạng, timeout, hoặc sự cố ở máy chủ. Kết quả là truy vấn thất bại, giao dịch không hoàn thành và request trả lỗi.

Cần trả lời riêng ba câu hỏi:

1. **Trước khi dùng:** làm sao giảm khả năng mượn phải một kết nối đã chết?
2. **Trong lúc dùng:** khi SQL hoặc `COMMIT` gặp lỗi kết nối thì xử lý tài nguyên và giao dịch thế nào?
3. **Sau sự cố:** làm sao để yêu cầu mới lấy được kết nối khỏe, và khi nào một thao tác có thể thử lại mà không gây tác dụng phụ?

Hãy hình dung kết nối như cuộc gọi điện thoại. Việc nghe thấy tín hiệu ở thời điểm hiện tại không bảo đảm đường dây vẫn thông sau một giây. Tương tự, **kiểm tra thành công chỉ xác nhận một thời điểm; mọi câu SQL vẫn phải có đường xử lý lỗi**.

Ví dụ trong bài dùng JDBC 4+, Java 17, Spring JDBC và HikariCP. HikariCP là một loại connection pool (nhóm kết nối); các thuộc tính riêng của nó không tự áp dụng cho mọi cách triển khai `DataSource`. Với Spring Boot, HikariCP thường được tự cấu hình khi thư viện phù hợp có mặt, nhưng luôn cần xác minh loại `DataSource` thực sự được sử dụng.

## 2. Cần hiểu đúng vòng đời `DataSource` và connection pool

`DataSource` là hợp đồng `javax.sql.DataSource`, thường được ứng dụng hoặc Spring gọi qua `getConnection()`. `Connection` là hợp đồng `java.sql.Connection` dùng để chuẩn bị và thực thi SQL, điều khiển giao dịch và giải phóng tài nguyên.

Với HikariCP, cần phân biệt:

- **Kết nối vật lý:** phiên kết nối thật với máy chủ DB, thường đi qua socket và driver.
- **Quyền mượn kết nối:** đối tượng `Connection` mà ứng dụng nhận từ pool, thường là proxy quản lý vòng đời sử dụng.
- **Kết nối nhàn rỗi:** kết nối vật lý đã trả lại pool nhưng có thể tiếp tục tái sử dụng.
- **Kết nối hỏng:** kết nối mà pool/driver xác định không còn sử dụng được, hoặc thao tác thực tế thất bại do đứt phiên.

```text
Ứng dụng / JdbcTemplate
         |
         | lấy kết nối
         v
DataSource / connection pool
         |               \
         |                \ kết nối lỗi qua kiểm tra hoặc JDBC exception
         |                 -> loại bỏ/thay khi có thể
         v
Connection được mượn
         |
         v
SQL / COMMIT / ROLLBACK
         |
         v
close() -> trả quyền mượn cho pool
```

Gọi `connection.close()` trên kết nối mượn từ HikariCP thường **trả kết nối về pool**, không có nghĩa mọi lần gọi đều đóng vật lý socket. Pool có thể quyết định loại bỏ kết nối vật lý đã hỏng hoặc hết tuổi. Ngược lại, giữ `Connection` trong biến `static`, cache, singleton hay để nhiều request dùng chung sẽ phá vỡ cách pool kiểm soát quyền mượn và làm lỗi khó chẩn đoán.

`DriverManagerDataSource` của Spring tạo kết nối JDBC mới mỗi lần được yêu cầu và **không cung cấp pool tái sử dụng**. `SingleConnectionDataSource` cố ý dùng một kết nối liên tục, chủ yếu hợp với kiểm thử, không phải cơ chế pool cho ứng dụng nhiều luồng. Vì vậy nội dung về kiểm tra kết nối trong pool chỉ áp dụng khi thật sự có pool.

## 3. Phân biệt ba phép kiểm tra thường bị đánh đồng

| Cơ chế | Điều nó kiểm tra | Điều nó không bảo đảm |
| --- | --- | --- |
| `Connection.isClosed()` | Đối tượng connection đã được đóng theo trạng thái driver biết | `false` không chứng minh mạng và DB vẫn hoạt động |
| `Connection.isValid(int timeout)` | Driver xác minh khả năng hoạt động bằng truy vấn hoặc cơ chế đáng tin theo JDBC | Không bảo đảm câu lệnh tiếp theo sẽ thành công |
| Truy vấn thử, ví dụ `SELECT 1` | Một câu SQL đơn giản có thực thi và trả kết quả được không | Không bảo đảm truy vấn nghiệp vụ, quyền truy cập hay giao dịch sẽ thành công |

### 3.1. Tại sao `isClosed() == false` chưa đủ?

Một socket có thể bị thiết bị mạng cắt ngầm khi không hoạt động. Driver chưa thực hiện I/O mới nên có thể chưa phát hiện vấn đề. Khi đó `isClosed()` vẫn có thể trả `false` nhưng câu SQL tiếp theo ném `SQLException`. Không dùng `isClosed()` làm phép “ping” mạng.

### 3.2. `Connection.isValid(timeout)` hoạt động ra sao?

JDBC quy định driver phải sử dụng truy vấn hoặc cơ chế xác minh thực sự. `timeout` của `isValid` tính bằng **giây**:

- `connection.isValid(2)`: đề nghị driver giới hạn thao tác xác minh ở hai giây.
- Trả `true`: hiện kết nối còn hợp lệ theo phép kiểm tra của driver.
- Trả `false`: không hợp lệ hoặc thao tác kiểm tra không hoàn thành trước giới hạn.
- Có thể ném `SQLException` trong các trường hợp lỗi; `timeout < 0` là đối số không hợp lệ.
- Giá trị `0` nghĩa là không áp giới hạn thời gian cho thao tác xác minh; không nên mặc định dùng trong health check cần thời gian chờ hữu hạn.

Một phép kiểm tra vẫn có thể thành công rồi kết nối hỏng ngay trước lệnh `UPDATE`; đây là khoảng thời gian giữa kiểm tra và sử dụng (*time-of-check/time-of-use*). Vì vậy luôn xử lý cả lỗi của lệnh thực.

### 3.3. Truy vấn thử `SELECT 1`

Với PostgreSQL, MySQL và H2, `SELECT 1` thường là truy vấn thử nhẹ. Không phải mọi hệ quản trị đều dùng cùng cú pháp; phải kiểm tra loại cơ sở dữ liệu. Một truy vấn kiểm tra vẫn là thêm một lượt trao đổi với DB, nên không nên tự gọi trước mọi câu SQL trong ứng dụng.

Nếu driver hỗ trợ JDBC 4 `Connection.isValid()`, HikariCP khuyến nghị thường **không cấu hình `connectionTestQuery`**. Chỉ cân nhắc truy vấn thử khi driver không hỗ trợ hoặc xác minh qua driver có vấn đề đã kiểm chứng. Đặt cùng lúc nhiều lớp ping không làm biến mất khả năng đứt kết nối giữa chừng.

### 3.4. Ví dụ Spring: kiểm tra kết nối bằng `DataSource`

Đây là lớp ví dụ **trong ứng dụng Spring có bean `DataSource` và `spring-context`**, không phải chương trình độc lập chỉ cần lệnh `javac`:

```java
import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

import org.springframework.stereotype.Component;

@Component
public final class JdbcConnectivityProbe {
    private final DataSource dataSource;

    public JdbcConnectivityProbe(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean available() {
        try (Connection connection = dataSource.getConnection()) {
            return connection.isValid(2); // 2 GIÂY
        } catch (SQLException ex) {
            return false;
        }
    }
}
```

`try-with-resources` đóng đối tượng `Connection` kể cả khi có lỗi. Nếu đây là kết nối được mượn từ pool thì nó thường được trả lại pool; pool quyết định có tái sử dụng được kết nối vật lý hay không. Hàm trả `false` cả khi không mượn được connection vì pool bận, do đó **không được diễn giải mọi kết quả false là “DB đã chết”**.

Ví dụ này phù hợp để hiểu API hoặc làm một phép kiểm tra chuyên biệt, không nên đưa vào mọi repository method. Với Spring Boot có Actuator, ưu tiên cơ chế health indicator đã có thay vì tự gọi `available()` liên tục từ các controller.

## 4. Kiểm tra vào lúc nào mới có giá trị?

Có bốn thời điểm khác nhau:

1. **Lúc khởi tạo pool hoặc ứng dụng:** phát hiện địa chỉ DB, tài khoản, quyền kết nối hoặc TLS sai. Khởi động thành công không chứng minh DB sẽ luôn sẵn sàng.
2. **Lúc mượn connection:** pool có thể kiểm tra kết nối nhàn rỗi và chọn kết nối khác nếu phát hiện kết nối đã hỏng. Không pool nào ngăn được lỗi vừa phát sinh sau khi cấp connection.
3. **Khi connection nhàn rỗi hoặc đã đến tuổi thay:** pool có thể ping, loại bỏ kết nối cũ hoặc tạo kết nối mới theo thiết lập tuổi thọ, thời gian rảnh và keepalive.
4. **Trong lúc thực thi SQL và commit:** lỗi phải được xử lý bằng ngoại lệ và quy tắc giao dịch; không thể chỉ dựa vào lần ping trước đó.

Đặc biệt, health check của DB và kiểm tra connection trong pool không giống phép đảm bảo nghiệp vụ. `isValid()` có thể trả true nhưng truy vấn vẫn sai SQL, thiếu quyền, bị deadlock hoặc trả dữ liệu không như mong muốn.

## 5. Cấu hình HikariCP phù hợp

Mỗi timeout giải quyết một giai đoạn khác nhau. Các thuộc tính sau đều là của **HikariCP**, đơn vị thời gian trên cấu hình dưới đây tính bằng **mili giây**, trừ khi tài liệu riêng của phương thức nêu khác.

| Thuộc tính | Vai trò | Lưu ý |
| --- | --- | --- |
| `connectionTimeout` | Thời gian tối đa ứng dụng chờ mượn connection từ pool | Không phải timeout cho SQL; hết thời gian có thể do pool bão hòa hoặc không tạo được kết nối |
| `validationTimeout` | Thời gian tối đa pool kiểm tra sống của connection | Phải nhỏ hơn `connectionTimeout` |
| `maxLifetime` | Tuổi sống tối đa của một connection trong pool | Connection đang được mượn không bị đóng cưỡng bức chỉ vì chạm mốc này; nên thấp hơn giới hạn của hạ tầng/DB |
| `keepaliveTime` | Khoảng thời gian pool cố gắng ping connection nhàn rỗi để ngừa bị cắt do không hoạt động | Chỉ áp dụng trên connection nhàn rỗi; phải nhỏ hơn `maxLifetime` |
| `idleTimeout` | Thời gian connection nhàn rỗi có thể được nghỉ hưu khi pool có kết nối vượt mức tối thiểu | Không nhất thiết loại toàn bộ kết nối sau đúng khoảng thời gian này |
| `maximumPoolSize` | Giới hạn số connection mà pool có thể giữ | Quá thấp gây xếp hàng; quá cao có thể làm DB quá tải |
| `connectionTestQuery` | SQL kiểm tra sống thay cho JDBC `isValid()` | Thường để trống với driver JDBC 4 đầy đủ |
| `leakDetectionThreshold` | Báo log khi connection bị giữ vượt ngưỡng | Công cụ chẩn đoán, không tự thu hồi connection an toàn hay sửa DB |

Một ví dụ `application.yml` cho ứng dụng Spring Boot dùng HikariCP (giá trị **minh họa**, phải điều chỉnh theo DB, hạ tầng, tải và yêu cầu vận hành):

```yaml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      pool-name: app-db
      maximum-pool-size: 10
      connection-timeout: 30000
      validation-timeout: 3000
      max-lifetime: 1500000
      keepalive-time: 300000
      # Không khai báo connection-test-query khi driver có isValid().
```

Diễn giải: mượn connection có thể đợi tối đa 30 giây; thời gian xác minh giới hạn 3 giây; tuổi tối đa 25 phút; pool cố gắng keepalive kết nối nhàn rỗi ở khoảng 5 phút. Các giá trị này **không bảo đảm tự sửa mọi sự cố** và không phải khuyến nghị mặc định cho tất cả môi trường.

Ví dụ hạ tầng đặt giới hạn **tuổi kết nối tuyệt đối 30 phút**: chọn `maxLifetime` ngắn hơn (chẳng hạn 25 phút) giúp hạn chế dùng connection quá tuổi. Nhưng nếu firewall đóng socket chỉ sau **3 phút nhàn rỗi**, `keepaliveTime` 5 phút không đủ để chủ động ngăn việc đóng do nhàn rỗi; cần điều chỉnh theo giới hạn thật.

Không tăng `maximumPoolSize` theo phản xạ khi gặp lỗi `connectionTimeout`. Hãy kiểm tra truy vấn chậm, giao dịch quá dài, giới hạn connection ở DB và số request đồng thời. Cũng không ping dồn dập với khoảng thời gian rất thấp vì tạo lưu lượng không cần thiết.

Nếu `DataSource` thực tế là pool khác HikariCP hoặc một bean tùy chỉnh, tên thuộc tính và hành vi quản lý connection phải được kiểm tra theo loại pool đó. Tiền tố cấu hình `spring.datasource.hikari.*` không biến `DriverManagerDataSource` thành HikariCP.

## 6. Spring JDBC và giao dịch: ai chịu trách nhiệm giải phóng connection?

### 6.1. Dùng `JdbcTemplate` cho thao tác dữ liệu thường ngày

`JdbcTemplate` dùng các cơ chế của Spring để mượn/giải phóng kết nối, chuẩn bị và chạy SQL, xử lý `ResultSet` và dịch nhiều `SQLException` thành hệ ngoại lệ `DataAccessException`. Trong nhiều trường hợp, cách tốt nhất để giảm lỗi tài nguyên chính là **không giữ connection thủ công**.

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public final class CustomerLookup {
    private final JdbcTemplate jdbc;

    public CustomerLookup(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Customer findById(long id) {
        return jdbc.queryForObject(
            "SELECT id, name FROM customer WHERE id = ?",
            (rs, row) -> new Customer(
                rs.getLong("id"),
                rs.getString("name")
            ),
            id
        );
    }

    public record Customer(long id, String name) {}
}
```

Lớp trên cần có cấu hình Spring JDBC, DB và bảng `customer`, nên **không chạy riêng chỉ bằng JDK**. Nếu không có khách hàng với ID đó, `queryForObject` có thể ném `EmptyResultDataAccessException`; đây là lỗi kết quả truy vấn, không phải dấu hiệu mất kết nối.

Không gọi `Connection.isValid()` trước mỗi lần `queryForObject`, vì ping thêm một lần tạo chi phí và vẫn có thể gặp lỗi khi câu SQL tiếp theo thực thi. Hãy để pool kiểm tra theo thiết kế, dùng `JdbcTemplate` và xử lý ngoại lệ nghiệp vụ hợp lý.

### 6.2. JDBC thuần ở ngoài Spring transaction

Nếu phải thao tác `DataSource.getConnection()` trực tiếp ngoài giao dịch Spring, đóng tài nguyên rõ ràng:

```java
try (Connection connection = dataSource.getConnection();
     var statement = connection.prepareStatement(
         "SELECT name FROM customer WHERE id = ?"
     )) {
    statement.setLong(1, 42L);

    try (var result = statement.executeQuery()) {
        if (result.next()) {
            System.out.println(result.getString("name"));
        }
    }
}
```

Đây là đoạn minh họa cần biến `dataSource`, cơ sở dữ liệu và các import JDBC. Mỗi lần mượn phải được hoàn trả kịp thời ngay cả khi câu SQL thất bại.

Nếu đang trong giao dịch do Spring quản lý, `dataSource.getConnection()` trực tiếp có thể tạo một kết nối không gắn với transaction hiện tại. Khi buộc phải viết JDBC cấp thấp, dùng `DataSourceUtils.getConnection(dataSource)` và `DataSourceUtils.releaseConnection(connection, dataSource)` để tôn trọng kết nối đã gắn với thread/giao dịch, hoặc ưu tiên `JdbcTemplate` vốn đã dùng cơ chế này. Đừng tùy tiện gọi `close()` trực tiếp trên kết nối lấy qua `DataSourceUtils` khi nó đang được Spring quản lý giao dịch.

### 6.3. Kết nối hỏng trong `@Transactional` không thể “nối lại” cùng giao dịch

Giả sử giao dịch chuyển tiền gồm:

```text
BEGIN
  UPDATE account A: trừ tiền
  UPDATE account B: cộng tiền
COMMIT
```

Nếu connection hỏng giữa hai lệnh `UPDATE`, không được lấy connection khác rồi tiếp tục lệnh còn lại như thể đang giữ cùng transaction. Phiên làm việc và ngữ cảnh giao dịch cũ gắn với connection đã hỏng. Spring thường cố hoàn tác/hoàn tất giao dịch theo ngoại lệ, nhưng nếu đường kết nối chết thì lệnh `ROLLBACK` cũng có thể thất bại hoặc không có phản hồi xác nhận.

Đặc biệt nếu ứng dụng gửi `COMMIT` rồi mất kết nối khi chờ phản hồi, **không chắc DB đã commit hay chưa**. Không thể suy diễn “client nhận lỗi = dữ liệu chắc chắn chưa ghi”. Các nghiệp vụ ghi tiền, tạo đơn, phát sự kiện cần khóa chống lặp/idempotency hoặc cơ chế đối soát độc lập.

Ví dụ service đọc dùng Spring transaction:

```java
import java.math.BigDecimal;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public final class AccountReader {
    private final JdbcTemplate jdbc;

    public AccountReader(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(readOnly = true)
    public BigDecimal balance(long accountId) {
        return jdbc.queryForObject(
            "SELECT balance FROM account WHERE id = ?",
            BigDecimal.class,
            accountId
        );
    }
}
```

Ví dụ yêu cầu ứng dụng Spring với transaction manager, `JdbcTemplate` và bảng `account`. Khi lỗi connection xảy ra, để ngoại lệ đi qua ranh giới transaction phù hợp để Spring dọn tài nguyên. Không bắt ngoại lệ rồi cố dùng lại connection đang lỗi, cũng không tự tạo giao dịch mới từ giữa một giao dịch chưa được kết thúc.

## 7. Nhận biết đúng lỗi connection và lỗi truy vấn

Không phải mọi `SQLException` là connection hỏng. Lỗi cũng có thể đến từ vi phạm khóa duy nhất, sai SQL, khóa bị giữ, chờ quá lâu, thiếu quyền hoặc pool không còn connection rảnh.

Một vài biểu hiện thường gặp:

- `CannotGetJdbcConnectionException`: Spring không lấy được JDBC connection; có thể do DB không khả dụng, cấu hình sai hoặc pool hết thời gian chờ.
- Ngoại lệ thuộc họ `DataAccessException`: Spring chuyển đổi từ JDBC theo trường hợp; cần xem loại cụ thể và nguyên nhân.
- `SQLException` với `SQLState` thuộc nhóm `08`: thường báo lỗi kết nối theo quy ước SQLState.
- `SQLTransientConnectionException`, `SQLNonTransientConnectionException` hay `SQLRecoverableException`: cung cấp tín hiệu từ JDBC driver, nhưng quyết định xử lý vẫn phụ thuộc thời điểm lỗi và tính chất nghiệp vụ.
- Lỗi từ pool như “connection is not available” hoặc “failed to validate”: cần phân biệt không mượn được connection vì pool cạn với việc một connection vật lý đã hỏng.

### 7.1. SQLState: phân loại để điều tra, không tự động retry

| Tiền tố SQLState | Nhóm lỗi thường gặp | Hướng suy nghĩ |
| --- | --- | --- |
| `08`, ví dụ `08006` | Connection exception | Xem DB, mạng, phiên kết nối, driver và pool |
| `40`, ví dụ `40001` | Transaction rollback/serialization | Có thể cần thử lại **toàn transaction** trong điều kiện an toàn |
| `23`, ví dụ `23505` | Vi phạm ràng buộc dữ liệu | Tìm trùng khóa hay lỗi nghiệp vụ; mượn connection mới không sửa được |
| `42` | Cú pháp/quyền truy cập theo quy ước SQLState | Kiểm tra SQL, schema và quyền, khác với sự cố mạng |
| `null` hoặc mã riêng | Driver không cung cấp mã chuẩn hoặc dùng quy ước riêng | Xem vendor code, chuỗi nguyên nhân, `getNextException()` và log DB/pool |

Không suy ra “cứ bắt được `DataAccessException` là retry” hoặc “cứ tiền tố `08` là có thể chạy lại lệnh ghi”. SQLState hữu ích để chẩn đoán **loại lỗi**, không trả lời việc nghiệp vụ có thực hiện một phần hoặc đã commit chưa.

### 7.2. Chương trình Java 17 độc lập kiểm tra cách phân loại

Ví dụ không cần Spring/DB thật. Nó tạo bốn `SQLException` giả định để thực hành đọc SQLState, **không phải** bộ quyết định retry trong production.

Tạo tệp `SqlStateDiagnosticDemo.java`:

```java
import java.sql.SQLException;
import java.util.List;

public class SqlStateDiagnosticDemo {
    static String classify(SQLException error) {
        String state = error.getSQLState();
        if (state != null && state.startsWith("08")) {
            return "connection-failure";
        }
        if (state != null && state.startsWith("40")) {
            return "transaction-rollback";
        }
        if (state != null && state.startsWith("23")) {
            return "integrity-constraint";
        }
        return "unknown";
    }

    public static void main(String[] args) {
        List<SQLException> errors = List.of(
            new SQLException("Network lost", "08006"),
            new SQLException("Serialization conflict", "40001"),
            new SQLException("Duplicate key", "23505"),
            new SQLException("Unclassified")
        );

        for (SQLException error : errors) {
            System.out.println(
                error.getSQLState() + " -> " + classify(error)
            );
        }
    }
}
```

Lệnh chạy:

```bash
javac SqlStateDiagnosticDemo.java
java SqlStateDiagnosticDemo
```

Kết quả chính xác:

```text
08006 -> connection-failure
40001 -> transaction-rollback
23505 -> integrity-constraint
null -> unknown
```

Khi điều tra sự cố thực, hãy xác định lỗi xảy ra ở bước **lấy connection, chạy SQL, commit hay rollback**, cùng với SQLState, mã lỗi driver, thông điệp gốc và tình trạng pool. Cùng một chữ “connection closed” nhưng thời điểm khác nhau có thể dẫn tới quyết định nghiệp vụ khác nhau.

## 8. Quy trình xử lý kết nối đã hỏng

**Bước 1 – Dừng sử dụng kết nối hiện tại.** Khi driver/pool báo lỗi kết nối, đừng dùng lại `Connection` đó cho câu SQL tiếp theo. `isClosed() == false` không phải bằng chứng rằng có thể tiếp tục. Nếu đang trong transaction, phải để transaction đi đến ranh giới kết thúc phù hợp.

**Bước 2 – Dọn tài nguyên.** Với JDBC thuần, bảo đảm `ResultSet`, `Statement` và connection được đóng bằng `try-with-resources` hoặc `finally`. Với `JdbcTemplate`/Spring transaction manager, để framework làm phần quản lý theo hợp đồng của nó. Pool xử lý kết nối vật lý đã hỏng khi phát hiện trạng thái không dùng được; không cần ứng dụng giữ connection rồi tự ping vô hạn.

**Bước 3 – Xác định lỗi ở đâu.** Nếu không lấy được connection, xem bão hòa pool, DB, TLS, network và xác thực. Nếu đang chạy SQL, xem query timeout, DB restart, transaction và mạng. Nếu lỗi ngay khi `COMMIT`, trạng thái dữ liệu có thể chưa xác định.

**Bước 4 – Chỉ để yêu cầu/giao dịch mới lấy connection mới.** Sau khi kết thúc thao tác cũ, pool có thể cấp connection khác khi DB sẵn sàng. Đừng tiếp tục nửa transaction còn lại trên connection mới.

**Bước 5 – Quyết định retry dựa trên nghiệp vụ.** Đọc độc lập, lặp lại an toàn có thể thử lại hữu hạn; ghi tiền/đơn hàng yêu cầu kiểm soát chống lặp và đối soát. Không dùng vòng lặp không giới hạn, nhất là khi DB đang quá tải.

**Bước 6 – Ghi nhận và phản hồi rõ ràng.** Log SQLState, loại lỗi, giai đoạn lỗi, pool name, thời lượng, correlation ID, trạng thái còn chờ kết nối. Không ghi mật khẩu hay thông tin nhạy cảm vào log. Nếu không thể xử lý, trả lỗi hạ tầng thích hợp; không trả “thành công” khi kết quả ghi chưa được xác nhận.

## 9. Khi nào được thử lại, và thử lại ở đâu?

| Tình huống | Hướng xử lý |
| --- | --- |
| `SELECT` độc lập, chỉ đọc, có thể lặp an toàn | Có thể retry hữu hạn trên **connection/giao dịch mới**, với tổng timeout và backoff |
| Pool cạn vì nhiều request đang giữ connection | Chẩn đoán tải, giới hạn song song, thời gian giữ connection; retry dồn dập có thể làm nặng thêm |
| Mất kết nối giữa transaction ghi | Dừng transaction cũ, không tiếp tục nó trên connection mới; xem tính an toàn trước khi chạy lại toàn nghiệp vụ |
| Mất phản hồi khi `COMMIT` | Đối soát trạng thái; không mặc định transaction thất bại |
| Lệnh ghi có `idempotency_key` và ràng buộc chống lặp | Có thể thiết kế retry **toàn nghiệp vụ** theo hợp đồng rõ ràng |
| Mật khẩu sai, không tồn tại bảng, cú pháp sai, trùng khóa | Không retry như lỗi connection; sửa nguyên nhân |

Một retry có kiểm soát cần số lần tối đa, khoảng chờ tăng dần có độ ngẫu nhiên (*backoff + jitter*), tổng thời gian chờ và theo dõi tỷ lệ lỗi. Nếu dùng `@Retryable` với `@Transactional`, phải xác minh **thứ tự advice/proxy**: điều quan trọng là mỗi lượt retry được bọc trong một transaction mới, không chạy lại trong transaction đã hỏng.

Ví dụ lệnh tạo thanh toán được gửi, DB đã commit, nhưng response `COMMIT` mất trên đường truyền. Nếu ứng dụng retry `INSERT payment` mà không có định danh nghiệp vụ duy nhất, có thể tạo **hai khoản thanh toán**. Giải pháp thực tế là mã yêu cầu duy nhất được DB ràng buộc `UNIQUE`, hành vi trả lại kết quả cũ và đối soát; việc “chữa” kết nối không giải được tính bất định của commit.

**Retry không làm một transaction đứt kết nối tiếp tục được.** Nó chỉ có thể thực hiện **một lượt nghiệp vụ mới** khi điều kiện an toàn đã được xác định.

## 10. Phân biệt các timeout hay dùng

| Phạm vi | Ví dụ | Kiểm soát |
| --- | --- | --- |
| Chờ mượn pool | `connectionTimeout` của HikariCP | Bao lâu yêu cầu được phép chờ pool cấp connection |
| Xác minh sống | `validationTimeout`, `Connection.isValid(seconds)` | Bao lâu một phép kiểm tra connection có thể đợi |
| Mở kết nối | Connect timeout của JDBC driver | Thời gian thiết lập mạng và bắt tay DB; tên và đơn vị tùy driver |
| Thực thi SQL | `Statement.setQueryTimeout(seconds)`, timeout của DB | Thời gian chạy truy vấn khi driver/DB hỗ trợ |
| Chờ I/O mạng | Socket timeout hoặc `Connection.setNetworkTimeout(...)` khi driver hỗ trợ | Tránh kẹt quá lâu ở lời gọi mạng |
| Transaction | `@Transactional(timeout = ...)` cùng cơ chế quản lý/driver/DB | Giới hạn giao dịch ở phạm vi được hỗ trợ; không phải đồng hồ cưỡng bức mọi driver |

Không dùng `connectionTimeout` để chữa một câu SQL chạy chậm: sau khi mượn được connection, thời gian thực thi SQL được kiểm soát bởi lớp khác. Ngược lại, query timeout không giải quyết pool đã hết connection rảnh.

Đối với `Connection.isValid(2)`, đơn vị là **giây**; với `spring.datasource.hikari.validation-timeout: 3000`, đơn vị là **mili giây**. Nhầm lẫn hai đơn vị có thể tạo timeout quá thấp hoặc quá cao.

## 11. Theo dõi sức khỏe cơ sở dữ liệu và connection pool

Với Spring Boot có `spring-boot-starter-actuator`, Spring Boot có thể tự đăng ký `DataSourceHealthIndicator` để báo sức khỏe nguồn dữ liệu (thường ở thành phần `db` của `/actuator/health`). Health indicator kiểm tra `DataSource` bằng `Connection.isValid()` hoặc một truy vấn thử khi được cấu hình. Quyền truy cập endpoint và thông tin chi tiết trả ra cần được kiểm soát phù hợp.

Phân biệt ba khái niệm:

- **Liveness:** tiến trình ứng dụng có bị lỗi tới mức cần khởi động lại không?
- **Readiness:** ứng dụng có thể nhận loại yêu cầu cần phụ thuộc DB hay chưa?
- **Database health:** phép lấy/kiểm tra connection tại thời điểm quan sát có thành công không?

Không nên cấu hình liveness khiến tất cả bản sao ứng dụng đồng loạt khởi động lại chỉ vì DB chung gián đoạn. Việc đưa DB vào readiness cần xét kiến trúc: có những ứng dụng vẫn phục vụ được chức năng không cần DB khi DB tạm mất. Một health check thành công không bảo đảm query tiếp theo thành công; ngược lại, health check có thể thất bại khi pool bão hòa dù máy chủ DB vẫn còn hoạt động.

Nếu dùng Micrometer với HikariCP, hãy quan sát:

- `hikaricp.connections.active`: số connection đang được mượn.
- `hikaricp.connections.idle`: số connection đang nhàn rỗi.
- `hikaricp.connections.pending`: số yêu cầu đang chờ lấy connection.
- Thời gian chờ lấy connection, số lần timeout, tần suất cảnh báo kiểm tra sống thất bại và log lỗi driver.

Ví dụ, `active` thường xuyên sát `maximumPoolSize` cùng `pending` tăng kéo dài gợi ý bão hòa pool, truy vấn chậm hoặc connection bị giữ lâu. Nó **không trực tiếp chứng minh socket của DB chết**. Ngược lại, lỗi kiểm tra kết nối xuất hiện dày sau giờ nhàn rỗi gợi ý cần kiểm tra timeout hạ tầng/keepalive.

## 12. Chẩn đoán theo tình huống

### Tình huống A: Request đầu tiên sau thời gian nghỉ báo “connection reset”

Một kết nối nhàn rỗi có thể bị DB, proxy hoặc firewall đóng từ trước. Kiểm tra log xác minh kết nối, thời gian rảnh, tuổi kết nối, `keepaliveTime` và `maxLifetime`. Khi pool phát hiện kết nối chết, nó có thể loại bỏ và tạo mới khi DB sẵn sàng. Request đầu tiên đã lỗi vẫn phải được xử lý theo hợp đồng nghiệp vụ; không có bảo đảm mọi trường hợp đều được pool chặn trước.

### Tình huống B: DB restart giữa hai câu SQL trong `@Transactional`

Kết nối đang dùng có thể bị đứt; câu SQL/commit/rollback phát sinh ngoại lệ. Không tiếp tục nửa sau trên connection khác. Kết thúc transaction cũ, dọn tài nguyên và làm rõ kết quả ghi trước khi quyết định chạy lại toàn nghiệp vụ. Đối với đọc idempotent, retry hữu hạn ở ngoài transaction cũ thường dễ kiểm soát hơn.

### Tình huống C: `getConnection()` timeout nhưng ping DB từ máy khác vẫn được

Có thể pool cạn vì truy vấn chậm, transaction dài, ứng dụng giữ connection quá lâu hoặc số request quá lớn. Kiểm tra `active`/`idle`/`pending`, DB connection limit và leak warning. Trước khi tăng pool size, xác định độ dài giao dịch và khả năng DB chịu tải.

### Tình huống D: `isValid()` trả `true` nhưng `UPDATE` vẫn lỗi

Ping chỉ kiểm tra kết nối tại một thời điểm; câu lệnh có thể thất bại vì mất mạng sau ping, khóa, quyền, constraint hoặc timeout. Đọc SQLState/vendor error code và vị trí lỗi; không kết luận `isValid` bị “sai” nếu hai lần gọi xảy ra ở hai thời điểm khác nhau.

### Tình huống E: Đang báo lỗi timeout nhưng nâng `connectionTimeout` vẫn không chữa được

Nếu DB bị kẹt hoặc pool rò rỉ connection, chờ lâu hơn chỉ kéo dài thời gian request treo. Cần xem metrics và nguồn giữ connection. Một timeout ngắn hợp lý có thể giới hạn tác động lên người dùng, nhưng phải chọn dựa trên tải và yêu cầu nghiệp vụ, không theo cảm tính.

## 13. Thực hành có kiểm soát

Trong môi trường thử nghiệm có DB riêng:

1. Khởi động ứng dụng, chạy một truy vấn đọc đơn giản; ghi nhận kết quả health và `active/idle/pending` của pool.
2. Dừng DB thử nghiệm **giữa hai lần đọc**. Ghi ngoại lệ, SQLState và thời điểm lỗi: lúc lấy connection hay lúc SQL thực thi?
3. Khôi phục DB. Gửi yêu cầu mới và xác nhận pool có thể cấp connection mới hoạt động được.
4. Lặp lại với DB bị dừng **trong lúc** một truy vấn thử đang thực thi; quan sát timeout và cách giải phóng tài nguyên. Không dùng dữ liệu/DB production cho thí nghiệm.
5. Tạo số request đọc có giới hạn để khiến pool chờ; so sánh lỗi bão hòa pool với lỗi mất kết nối DB.
6. Với thao tác ghi giả lập, thử tình huống lỗi khi commit và thực hành đối soát dựa trên mã nghiệp vụ duy nhất; không suy ra trạng thái commit từ lỗi mạng.

Mỗi kết quả thử nên ghi rõ: **điểm phát sinh lỗi, nguyên nhân có bằng chứng, trạng thái giao dịch, phản hồi ứng dụng và cách phục hồi**. Nếu chỉ ghi “connection closed” mà không biết ở bước nào, rất khó chọn cách sửa chính xác.

## 14. Câu hỏi và đáp án

**1. Vì sao `connection.isClosed() == false` vẫn có thể gặp lỗi “connection reset”?**  
Vì trạng thái đóng mà driver biết có thể chưa phản ánh việc mạng đã mất kết nối; phải kiểm tra chủ động hoặc chấp nhận phát hiện lỗi khi SQL chạy.

**2. `connection.isValid(2)` có bảo đảm câu `INSERT` ngay sau đó thành công không?**  
Không. DB/mạng có thể hỏng sau ping và câu `INSERT` còn có các nguyên nhân thất bại khác.

**3. `connectionTimeout: 30000` có giới hạn truy vấn SQL tối đa 30 giây không?**  
Không. Nó giới hạn thời gian chờ **mượn connection từ HikariCP**; truy vấn cần timeout ở tầng statement/driver/DB riêng.

**4. Với pool Hikari, nên mặc định thêm `connectionTestQuery: SELECT 1` không?**  
Thường không nếu driver JDBC 4 hỗ trợ `isValid()` đúng chuẩn. Chỉ cấu hình query kiểm tra khi có lý do cụ thể.

**5. Connection hỏng giữa hai lệnh cập nhật trong cùng transaction thì có thể dùng connection mới để tiếp tục lệnh thứ hai không?**  
Không. Giao dịch cũ đã không còn được bảo đảm; phải kết thúc nó và xem xét thực hiện lại toàn nghiệp vụ với chính sách an toàn.

**6. Vì sao không được tự động retry mọi lần thất bại tại `COMMIT`?**  
Vì DB có thể đã commit trước khi client mất phản hồi; retry lệnh ghi có thể tạo dữ liệu/tiền trùng nếu không có cơ chế idempotency và đối soát.

**7. `getConnection()` timeout có chứng minh DB đang down không?**  
Không. Pool có thể đang bão hòa vì connection bị giữ lâu, quá nhiều request hoặc các truy vấn chậm.

## 15. Những nguyên tắc cần nhớ

- `DataSource` cung cấp connection; pool quản lý tái sử dụng và thay thế connection vật lý. **Đóng tài nguyên đúng lúc** là nền tảng.
- `isClosed()` không phải kiểm tra mạng. `isValid(timeout)` và kiểm tra của pool giúp giảm việc lấy phải connection chết nhưng không thể bảo đảm SQL kế tiếp thành công.
- Cấu hình `connectionTimeout`, `validationTimeout`, `maxLifetime` và `keepaliveTime` theo giới hạn thực của DB/mạng; với JDBC 4 thường để trống `connectionTestQuery`.
- `JdbcTemplate` và transaction manager giúp quản lý đúng vòng đời connection; **không tái sử dụng connection/giao dịch đã hỏng**.
- SQLState cùng thông tin driver/pool cho biết hướng chẩn đoán. Một ngoại lệ không tự quyết định được thao tác ghi có an toàn để retry hay không.
- Thử lại đọc độc lập có thể phù hợp; thử lại ghi cần ranh giới giao dịch mới, số lần hữu hạn, **idempotency và đối soát** khi kết quả commit chưa xác định.
- Quan sát cả trạng thái DB và `active`, `idle`, `pending` của pool để phân biệt kết nối chết với pool cạn.

### Tài liệu tham khảo

- [JDK 17: `java.sql.Connection`](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html)
- [Spring Framework: Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)
- [Spring Framework: Data Access with JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html)
- [HikariCP: README cấu hình](https://github.com/brettwooldridge/HikariCP/blob/dev/README.md)
- [Spring Boot 3.3: `DataSourceHealthIndicator`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/jdbc/DataSourceHealthIndicator.html)
