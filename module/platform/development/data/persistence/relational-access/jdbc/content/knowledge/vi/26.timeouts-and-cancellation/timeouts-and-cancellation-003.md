# Thiết lập query timeout trên Statement trong JDBC

Khi ứng dụng Java truy cập cơ sở dữ liệu qua **JDBC**, một câu SQL có thể chạy lâu hơn dự kiến vì kế hoạch truy vấn kém, thiếu chỉ mục, dữ liệu lớn, cạnh tranh khóa hoặc DBMS đang quá tải. Nếu không có giới hạn phù hợp, request có thể giữ luồng xử lý và kết nối trong thời gian dài, làm tăng độ trễ và khiến connection pool cạn tài nguyên.

API **`Statement.setQueryTimeout(int seconds)`** cho phép đặt **giới hạn thời gian thực thi câu lệnh theo đơn vị giây** cho một đối tượng `Statement`. API này cũng áp dụng với `PreparedStatement` và `CallableStatement` vì chúng kế thừa `Statement`. Tuy nhiên, đây **không phải đồng hồ đếm ngược cho toàn bộ request** và không bảo đảm mọi driver/DBMS sẽ hủy chính xác ngay khi đủ số giây.

Bài học thuộc chương **Timeout và hủy** của module **JDBC**, tập trung vào cách gọi `setQueryTimeout(...)`, kiểm tra cấu hình bằng `getQueryTimeout()`, bắt lỗi `SQLTimeoutException`, quản lý tài nguyên `Connection`, `PreparedStatement`, `ResultSet` và kết thúc transaction đúng cách khi câu lệnh bị timeout.

## 1. Query timeout là gì?

**Query timeout** đặt giới hạn thời gian mà JDBC driver chờ một `Statement` thực thi. Nếu giới hạn bị vượt qua và driver phát hiện điều đó, nó cố gắng hủy câu lệnh đang chạy và báo lỗi cho ứng dụng, thông thường bằng **`SQLTimeoutException`**.

Ví dụ:

```java
try (Connection connection = dataSource.getConnection();
     Statement statement = connection.createStatement()) {

    statement.setQueryTimeout(5); // Đơn vị: giây.

    try (ResultSet rs =
                 statement.executeQuery("SELECT id, name FROM product")) {
        while (rs.next()) {
            System.out.println(rs.getLong("id")
                    + ": " + rs.getString("name"));
        }
    }
}
```

Trong ví dụ:

1. `getConnection()` mượn hoặc mở một kết nối JDBC.
2. `createStatement()` tạo một `Statement` gắn với kết nối đó.
3. `setQueryTimeout(5)` yêu cầu giới hạn chờ thực thi khoảng **5 giây** cho các lệnh chạy trên statement này.
4. `executeQuery(...)` thực thi SQL. Nếu driver xác định vượt timeout, lệnh có thể bị hủy và ném `SQLTimeoutException`.
5. `try-with-resources` đóng `ResultSet`, `Statement` và `Connection` kể cả khi có lỗi.

Đây là ví dụ với `Statement` thuần và SQL do ứng dụng kiểm soát. Khi SQL có tham số động, nên dùng `PreparedStatement` và placeholder `?` thay vì nối dữ liệu người dùng vào chuỗi truy vấn.

### Timeout không phải lời hứa hoàn thành trong đúng N giây

Tùy driver và DBMS, cơ chế timeout có thể dựa vào timer phía client, timeout phía server, yêu cầu hủy qua mạng hoặc một cách kết hợp. Hệ quả:

- Thời gian thực tế trước khi nhận lỗi có thể lớn hơn giá trị cấu hình vì độ trễ mạng, thời gian xử lý lệnh hủy hoặc hạn chế của driver.
- Một số driver không hỗ trợ đầy đủ query timeout hoặc không thể hủy một lệnh trong mọi trạng thái.
- Giới hạn cho một lời gọi thực thi SQL không đồng nghĩa giới hạn cho toàn bộ các bước `getConnection()`, đọc hết `ResultSet`, xử lý dữ liệu ở Java hay `commit()`.
- Khi đã gửi lệnh ghi, **timeout không chứng minh thao tác chưa có tác động**. Phải xử lý transaction và trường hợp kết quả chưa xác định.

Vì vậy, đặt query timeout là **biện pháp kiểm soát tài nguyên**, không thay thế thiết kế SQL, giới hạn thời gian ở tầng request, kiểm soát giao dịch hay xử lý lỗi mạng.

## 2. Ba giá trị quan trọng của `setQueryTimeout(int seconds)`

| Lời gọi | Ý nghĩa | Cần lưu ý |
|---|---|---|
| `statement.setQueryTimeout(5)` | Đặt giới hạn 5 giây cho việc thực thi câu lệnh trên statement đó. | Không bảo đảm ngắt tức thời tại giây thứ 5. |
| `statement.setQueryTimeout(0)` | Không áp đặt giới hạn query timeout **qua thuộc tính này**. | Không tắt các timeout của DBMS, mạng, pool hoặc ứng dụng. |
| `statement.setQueryTimeout(-1)` | Giá trị âm không hợp lệ. | JDBC có thể ném `SQLException`; không dùng số âm để biểu diễn “vô hạn”. |

Theo hợp đồng JDBC, giá trị mặc định của query timeout thông thường là **0**, nghĩa là không có giới hạn do `Statement` đặt ra. Một `DataSource` hoặc driver có thể có cấu hình riêng và DBMS vẫn có chính sách timeout của nó; vì vậy **`0` không đồng nghĩa câu SQL chắc chắn được chạy mãi**.

Có thể đọc lại giá trị mà statement công bố:

```java
statement.setQueryTimeout(5);

int seconds = statement.getQueryTimeout();
System.out.println("Query timeout (seconds): " + seconds);
```

`getQueryTimeout()` giúp kiểm tra trạng thái cấu hình trên `Statement`. Nó **không phải phép kiểm thử** rằng driver thực sự có thể hủy mọi loại SQL trong thời hạn này. Hãy kiểm tra bằng integration test trên DBMS/driver đang dùng.

### Đơn vị là giây, không phải mili giây

`setQueryTimeout(3)` nghĩa là **3 giây**, không phải 3 mili giây. Không truyền trực tiếp một giá trị lấy từ cấu hình milliseconds mà không chuyển đổi.

```java
int configuredSeconds = 3;
statement.setQueryTimeout(configuredSeconds);
```

Nếu cấu hình thời gian ở ứng dụng là `Duration`:

```java
import java.time.Duration;

Duration timeout = Duration.ofSeconds(3);
long wholeSeconds = timeout.getSeconds();

if (wholeSeconds < 1 || wholeSeconds > Integer.MAX_VALUE) {
    throw new IllegalArgumentException("Timeout không nằm trong phạm vi hỗ trợ");
}
statement.setQueryTimeout((int) wholeSeconds);
```

Đoạn chuyển đổi trên **chỉ chấp nhận giây nguyên dương**. Nếu SLA cần chính xác vài trăm mili giây, không nên âm thầm làm tròn thành 0 vì `0` có nghĩa **không giới hạn** tại API này. Hãy chọn chính sách làm tròn có chủ đích và cân nhắc khả năng timeout ở server/driver cùng deadline của toàn request.

## 3. Query timeout thuộc về `Statement`, không phải toàn Connection

Khi một `Connection` tạo nhiều statement:

```java
try (Connection connection = dataSource.getConnection();
     Statement fast = connection.createStatement();
     Statement slow = connection.createStatement()) {

    fast.setQueryTimeout(2);
    slow.setQueryTimeout(15);

    // Hai statement có cấu hình query timeout riêng.
}
```

Không có một thao tác `Statement.setQueryTimeout` nào tự động áp dụng sang **mọi statement của cùng connection**, các connection khác, hoặc tất cả phiên của pool.

Đối với `PreparedStatement`:

```java
String sql = "SELECT id, name, stock FROM product WHERE id = ?";

try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(sql)) {

    ps.setQueryTimeout(4); // Có được vì PreparedStatement extends Statement.
    ps.setLong(1, 42L);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            System.out.println(rs.getString("name"));
        }
    }
}
```

Đối với `CallableStatement` gọi stored procedure, cũng có thể đặt `setQueryTimeout(...)` trên đối tượng đó, **nếu driver hỗ trợ**. Bản chất stored procedure có thể thực hiện nhiều câu lệnh phía server; thời điểm và mức áp dụng timeout có thể phụ thuộc DBMS, vì vậy phải thử với routine thực tế.

### Đặt timeout trước lệnh thực thi

Thứ tự cần nhớ:

```text
DataSource.getConnection()
      │
      ▼
Connection.prepareStatement(sql) hoặc createStatement()
      │
      ▼
Statement.setQueryTimeout(seconds)
      │
      ▼
Bind tham số nếu là PreparedStatement
      │
      ▼
executeQuery() / executeUpdate() / execute() / executeBatch()
      │
      ├── Thành công → xử lý kết quả → commit khi cần
      │
      └── Timeout/lỗi → xử lý exception → rollback khi cần
```

Đặt timeout **sau** `executeQuery()` không có tác dụng lên lời gọi thực thi đã kết thúc. Không nên thay đổi timeout của cùng một `Statement` đồng thời từ nhiều thread; một statement đang được sử dụng không phải đối tượng dùng chung tự do giữa các request.

## 4. Ví dụ đọc dữ liệu: `PreparedStatement`, timeout và `ResultSet`

Giả sử cơ sở dữ liệu có bảng:

```sql
CREATE TABLE product (
    id BIGINT PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    stock INTEGER NOT NULL
);
```

Mẫu repository dùng `DataSource`, SQL tham số hóa, giới hạn số bản ghi trả về và query timeout:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.SQLTimeoutException;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

public final class ProductReader {
    private final DataSource dataSource;

    public ProductReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public List<String> findProductNames(int minimumStock)
            throws SQLException {

        String sql = "SELECT name FROM product "
                + "WHERE stock >= ? ORDER BY id";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {

            ps.setQueryTimeout(5);
            ps.setMaxRows(100); // Giới hạn số dòng trong ResultSet.
            ps.setInt(1, minimumStock);

            try (ResultSet rs = ps.executeQuery()) {
                List<String> names = new ArrayList<>();
                while (rs.next()) {
                    names.add(rs.getString("name"));
                }
                return names;
            }
        } catch (SQLTimeoutException timeout) {
            // Phân loại được lỗi timeout. Tầng gọi quyết định thông báo/retry.
            throw timeout;
        }
    }
}
```

Trong ví dụ:

- `ps.setQueryTimeout(5)` đặt giới hạn thực thi SQL ở statement.
- `ps.setMaxRows(100)` giới hạn số hàng tối đa trong `ResultSet`, **không phải giới hạn thời gian** và không bảo đảm database sẽ xử lý tối đa 100 hàng trong kế hoạch truy vấn.
- `ps.setInt(1, minimumStock)` bind dữ liệu đầu vào an toàn thay vì ghép vào SQL.
- `ResultSet` được xử lý và đóng trong phạm vi statement/connection còn mở.
- `SQLTimeoutException` là ngoại lệ có thể phân loại ở tầng service hoặc API. Việc bắt rồi ném lại trong ví dụ nhằm minh họa loại lỗi; không nên viết một nhánh `catch` chỉ ném lại nếu không cần xử lý thực tế.

Ví dụ này là luồng **chỉ đọc**, nên không tự đặt transaction nhiều bước. Trong ứng dụng thực tế, một request HTTP có thể có deadline tổng thể và pool có acquisition timeout riêng; các giới hạn đó **cần phối hợp**, không phải chỉ tăng `setQueryTimeout`.

### Timeout trên `executeQuery()` có bao gồm thời gian duyệt hết ResultSet không?

**Không nên giả định.** API `setQueryTimeout` áp dụng cho thời gian thực thi `Statement` mà driver chờ. Việc `ResultSet.next()` có tiếp tục truy cập mạng, tải các trang dữ liệu hoặc chịu chung bộ đếm thời gian không phụ thuộc hoàn toàn vào API JDBC chuẩn mà còn vào driver, chế độ fetch và cách DBMS truyền kết quả.

Ví dụ một câu SQL hoàn tất nhanh nhưng ứng dụng đọc một triệu dòng rồi xử lý CPU nhiều phút: **query timeout 5 giây không được coi là giới hạn 5 giây cho toàn bộ quá trình xử lý kết quả**.

Nếu cần giới hạn tổng request, thêm deadline của tầng ứng dụng và thiết kế đọc dữ liệu có kiểm soát: phân trang, chỉ lấy các cột cần thiết, giới hạn số hàng, fetch size phù hợp, và khả năng hủy tác vụ theo driver.

## 5. Timeout khi ghi dữ liệu: không bỏ qua rollback

Nếu câu SQL là `INSERT`, `UPDATE` hoặc `DELETE`, timeout có thể xảy ra khi driver/DBMS đã bắt đầu thực hiện thao tác. **Không được suy ra rằng dữ liệu chắc chắn chưa thay đổi** chỉ vì `executeUpdate()` ném `SQLTimeoutException`.

Với nghiệp vụ cần atomicity, dùng một transaction JDBC cục bộ:

```sql
UPDATE product
SET stock = stock - ?
WHERE id = ? AND stock >= ?;
```

Mẫu service:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.SQLTimeoutException;
import javax.sql.DataSource;

public final class StockReservation {
    private final DataSource dataSource;

    public StockReservation(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean reserve(long productId, int quantity)
            throws SQLException {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Số lượng phải dương");
        }

        String sql = "UPDATE product SET stock = stock - ? "
                + "WHERE id = ? AND stock >= ?";

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try {
                int affected;

                try (PreparedStatement ps =
                             connection.prepareStatement(sql)) {
                    ps.setQueryTimeout(3);
                    ps.setInt(1, quantity);
                    ps.setLong(2, productId);
                    ps.setInt(3, quantity);

                    affected = ps.executeUpdate();
                }

                if (affected == 0) {
                    connection.rollback();
                    return false;
                }
                if (affected != 1) {
                    throw new SQLException("Số hàng cập nhật không hợp lệ");
                }

                connection.commit();
                return true;

            } catch (SQLTimeoutException timeout) {
                // Không commit khi câu lệnh đã vượt timeout.
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    timeout.addSuppressed(rollbackError);
                }
                throw timeout;

            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    failure.addSuppressed(rollbackError);
                }
                throw failure;
            }
        }
    }
}
```

Trong trường hợp bình thường, `UPDATE` có điều kiện bảo đảm không giảm `stock` xuống âm đối với một hàng được tìm thấy, tùy semantics transaction của DBMS; `executeUpdate()` bằng `0` nghĩa là hàng không tồn tại hoặc không đủ tồn kho, nên ví dụ rollback và trả `false`.

Khi xảy ra `SQLTimeoutException`:

1. Ứng dụng **không gọi commit**.
2. Ứng dụng cố gắng `rollback()` để yêu cầu DBMS hủy các thay đổi **chưa commit** trên kết nối.
3. Nếu rollback cũng thất bại, lỗi rollback được gắn vào ngoại lệ gốc bằng `addSuppressed(...)`.
4. Tầng gọi vẫn nhận lỗi; không được hiểu timeout là một kết quả nghiệp vụ “hết hàng”.

**Giới hạn quan trọng:** `rollback()` có thể thất bại do kết nối hỏng hoặc transaction không còn ở trạng thái bình thường. Nếu `commit()` đã được gửi rồi lỗi do mất phản hồi, kết quả commit có thể **không xác định**; rollback tiếp theo không thể đảo ngược một commit đã hoàn tất. Nghiệp vụ có thể được gửi lại cần **idempotency**, mã yêu cầu duy nhất hoặc đối soát dữ liệu trước khi retry.

### Tránh tự động retry mọi timeout

`SQLTimeoutException` thường được xếp vào nhóm lỗi transient trong phân cấp ngoại lệ JDBC, nhưng điều đó **không đồng nghĩa mọi thao tác đều an toàn để thử lại**:

- Với `SELECT` chỉ đọc, thử lại có giới hạn có thể phù hợp nếu hệ thống còn ngân sách thời gian và độ trễ chấp nhận được.
- Với `UPDATE` trong transaction đã rollback thành công, có thể cân nhắc thử lại **toàn bộ nghiệp vụ** theo chính sách lỗi/DBMS.
- Với một `INSERT` auto-commit hoặc thao tác đã gửi tới hệ thống ngoài DB, trạng thái tác động có thể không rõ. Không retry mù.
- Nếu timeout do tải cao hoặc thiếu chỉ mục, retry liên tiếp có thể làm DBMS càng quá tải.

Luôn giới hạn số lần retry, áp dụng backoff có kiểm soát và tôn trọng deadline còn lại của request.

## 6. Phân biệt query timeout với những timeout khác

Một hệ thống thường có nhiều đồng hồ thời gian hoạt động ở các lớp khác nhau:

| Loại timeout | Phạm vi | API / cơ chế thường gặp | Không bảo đảm điều gì? |
|---|---|---|---|
| **Query timeout** | Thời gian thực thi câu lệnh qua `Statement` | `Statement.setQueryTimeout(int seconds)` | Không giới hạn toàn bộ request hay thời gian mượn connection. |
| **Login timeout** | Thiết lập kết nối/đăng nhập DB | `DataSource.setLoginTimeout(int seconds)` hoặc cấu hình driver | Không giới hạn thời gian chạy SQL. |
| **Pool acquisition timeout** | Chờ pool cấp một `Connection` | Cấu hình pool, tên tham số tùy thư viện | Không điều khiển thời gian DBMS thực thi SQL. |
| **Network timeout** | Thời gian chờ thao tác mạng JDBC theo khả năng driver | `Connection.setNetworkTimeout(Executor, milliseconds)` | Không phải thời gian thực thi câu SQL thuần túy hoặc cơ chế hủy nghiệp vụ an toàn. |
| **Lock timeout** | Thời gian một transaction chờ khóa ở DBMS | Cấu hình session/SQL/DBMS | Không thay thế query timeout cho mọi nguyên nhân chậm. |
| **Transaction timeout** | Giới hạn toàn bộ transaction do môi trường/framework điều phối | Transaction manager hoặc DBMS, tùy nền tảng | Không phải một cấu hình có trên mọi `java.sql.Connection`. |
| **Request deadline** | Thời gian tối đa của một tác vụ ở tầng API/service | Cơ chế timeout của ứng dụng | Không tự bảo đảm JDBC statement đang chạy đã dừng nếu không tích hợp hủy. |

### Câu SQL có thể bị giới hạn bởi nhiều lớp

Giả sử:

- Request HTTP có deadline 10 giây.
- Mượn connection từ pool mất 3 giây.
- Query timeout đặt 8 giây.

Nếu sau khi mượn kết nối mới bắt đầu gọi `executeQuery()`, ngân sách thời gian tổng thể của request còn khoảng 7 giây, **không phải 8 giây**. Đặt query timeout lớn hơn thời gian còn lại có thể khiến JDBC tiếp tục chạy sau khi tầng HTTP đã hết deadline nếu không có phối hợp.

Cách thiết kế tốt là truyền hoặc tính **deadline** ở tầng service rồi cấu hình giới hạn cho các bước con theo ngân sách còn lại, với quy tắc làm tròn giây và các timeout có độ phân giải khác nhau. Tránh dùng `setQueryTimeout(0)` như kết quả của phép làm tròn một ngân sách dưới 1 giây.

### Query timeout khác network timeout

`Connection.setNetworkTimeout(...)` nhận timeout theo **mili giây**, còn `Statement.setQueryTimeout(...)` nhận **giây**. Khi network timeout xảy ra, driver có thể đánh dấu connection không còn dùng được; mức ảnh hưởng tới transaction và khả năng tái sử dụng connection còn tùy driver/DBMS.

Không nên tăng network timeout để “sửa” query timeout, hoặc ngược lại. Nếu câu SQL chờ khóa lâu, server-side lock timeout có thể cung cấp thông tin rõ hơn về nguyên nhân. Nếu mạng hỏng, query timeout riêng có thể không đủ để cứu thao tác bị treo ở tầng socket trong mọi driver.

## 7. Hủy thủ công bằng `Statement.cancel()`

`setQueryTimeout(...)` là cơ chế giới hạn dựa trên thời gian; `Statement.cancel()` cho phép ứng dụng **yêu cầu hủy câu lệnh hiện đang thực thi** khi driver và DBMS hỗ trợ.

Ví dụ một người dùng bấm “Hủy báo cáo” trong UI. Tầng điều phối có thể gọi `cancel()` trên đúng statement đang chạy:

```java
// Minh họa cơ chế, không phải ví dụ chạy độc lập:
Statement runningStatement = ...;

// Trong luồng điều phối hủy, chỉ khi statement còn hợp lệ:
runningStatement.cancel();
```

JDBC cho phép dùng `cancel()` từ một thread để hủy statement đang thực thi ở thread khác nếu DBMS/driver hỗ trợ. Tuy nhiên, việc **chia sẻ statement giữa các thread cho các thao tác SQL khác** không an toàn và không nên làm. Cần quản lý vòng đời, tránh race giữa `cancel()` và `close()`, và xử lý ngoại lệ từ thread thực thi.

Những giới hạn cần nhớ:

1. `cancel()` là **yêu cầu hủy**, không phải cam kết DBMS đã dừng ngay tức thì.
2. Lỗi được trả có thể là `SQLException` hoặc lớp con/SQLState riêng theo driver; không nhất thiết giống lỗi query timeout tự động.
3. Với câu lệnh ghi dữ liệu, hủy không tương đương `rollback()` hay `commit()`.
4. Khi hủy một transaction đang hoạt động, tầng sở hữu transaction vẫn phải quyết định rollback/đóng connection theo trạng thái thực tế.
5. Một số driver không hỗ trợ cancel hoặc không thể can thiệp vào mọi giai đoạn thực thi; hãy kiểm chứng trên hệ thống triển khai.

Không cố “hủy” bằng cách đơn giản gọi `Thread.interrupt()` rồi mặc định SQL đã dừng. Thread interrupt ở Java không phải cơ chế đảm bảo hủy câu SQL phía DBMS. Tương tự, đóng connection từ thread khác trong lúc câu SQL đang chạy có thể gây rủi ro trạng thái và cần tuân thủ hợp đồng driver/pool.

### Khi nào nên dùng timeout, khi nào nên dùng cancel?

| Tình huống | Cơ chế hợp lý |
|---|---|
| Mọi truy vấn báo cáo phải có giới hạn thực thi mặc định | Đặt `setQueryTimeout(...)` trên statement dùng cho báo cáo. |
| Người dùng tự bấm “Hủy” tác vụ đang chạy | Yêu cầu `Statement.cancel()` qua bộ điều phối có kiểm soát, nếu driver hỗ trợ. |
| Hạn mức toàn bộ API/service phải kết thúc trước deadline | Deadline tầng ứng dụng + timeout phù hợp từng bước + cơ chế cancellation. |
| Truy vấn chờ khóa quá lâu | Chẩn đoán lock wait, điều chỉnh SQL/transaction và lock timeout DBMS khi phù hợp. |
| Lỗi mất mạng giữa `commit()` | Cơ chế đối soát/idempotency; query timeout hoặc cancel không xác định được kết quả commit. |

## 8. Batch, stored procedure và nhiều kết quả: phải thử theo driver

Cả `PreparedStatement`, `CallableStatement` và `Statement` đều dùng giao diện `Statement` cho query timeout. Nhưng không nên suy rằng tất cả cách thực thi đều có cách đếm thời gian giống hệt.

### `executeBatch()`

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(
             "UPDATE product SET stock = stock + ? WHERE id = ?")) {

    ps.setQueryTimeout(10);

    ps.setInt(1, 3);
    ps.setLong(2, 101L);
    ps.addBatch();

    ps.setInt(1, 1);
    ps.setLong(2, 102L);
    ps.addBatch();

    int[] results = ps.executeBatch();
    // Kiểm tra update counts và transaction theo yêu cầu nghiệp vụ.
}
```

Đoạn này minh họa API, dùng auto-commit theo cấu hình kết nối. Khi yêu cầu “toàn batch thành công hoặc toàn batch thất bại”, phải dùng transaction với `setAutoCommit(false)`, `commit()` và `rollback()` tường minh.

**Với batch**, driver có thể xử lý từng lệnh hoặc một cơ chế batch riêng; query timeout có thể áp dụng cho toàn lời gọi hoặc từng thao tác bên trong theo triển khai. Nếu một lệnh thất bại, `BatchUpdateException.getUpdateCounts()` có thể cho thông tin phần đã chạy. Đừng mặc định timeout là “không có hàng nào đã thay đổi”, đặc biệt nếu auto-commit bật.

### `CallableStatement`

```java
try (Connection connection = dataSource.getConnection();
     CallableStatement call =
             connection.prepareCall("{call generate_report(?)}")) {

    call.setQueryTimeout(15);
    call.setLong(1, 42L);
    call.execute();
}
```

Stored procedure có thể thực hiện nhiều lệnh SQL nội bộ hoặc trả nhiều `ResultSet`. Driver và DBMS khác nhau có cách thực thi/cancel khác nhau; phải thử với routine thực tế, quyền gọi và dữ liệu tương ứng. Query timeout không phải bảo đảm “mỗi câu SQL bên trong procedure được giới hạn 15 giây”.

## 9. Kích thước thời gian và hiệu năng: chọn timeout dựa trên dữ liệu

Một giá trị cố định như 3 hoặc 5 giây chỉ là **ví dụ học tập**, không phải khuyến nghị chung cho mọi workload.

Khi xác định query timeout, cần xem:

- **Phân loại workload:** truy vấn tra cứu theo khóa chính, báo cáo nhiều bảng, batch ghi dữ liệu, stored procedure dài có yêu cầu khác nhau.
- **Phân bố độ trễ:** p50/p95/p99 của thời gian truy vấn trong điều kiện tải thực tế, không chỉ trung bình.
- **Độ trễ mạng và tải DBMS:** timeout quá ngắn có thể gây lỗi giả khi hệ thống bị tải cao nhưng vẫn có thể phục hồi.
- **Chờ khóa:** một truy vấn bị chậm do transaction khác giữ khóa cần điều tra transaction/locking, không chỉ tăng timeout.
- **SLA tổng thể:** thời gian còn lại của request sau các bước xác thực, mượn connection, xử lý kết quả và gọi hệ thống khác.
- **Chi phí retry:** query timeout quá ngắn kết hợp retry dồn dập có thể làm hệ thống càng chậm.
- **Tài nguyên pool:** câu SQL chạy lâu giữ connection và làm tăng thời gian chờ của request khác.

Ví dụ nhóm nghiệp vụ có thể chọn chính sách **khác nhau**:

| Workload | Cách suy nghĩ về thời hạn |
|---|---|
| Tra cứu sản phẩm để trả HTTP nhanh | Đặt giới hạn phù hợp với SLA request, sau khi đo độ trễ thực tế. |
| Báo cáo tương tác nhiều bảng | Có thể cho thời gian dài hơn, kèm giới hạn số hàng và quyền hủy từ UI. |
| Job batch chạy nền | Xem transaction, khả năng chia batch và phục hồi để quyết định timeout cho từng lệnh/đợt. |
| Cập nhật tiền/tồn kho | Timeout cần đi cùng rollback, idempotency và xử lý xung đột, không chỉ “hết giờ thì gửi lại”. |

### Quan sát SQL timeout

Khi ghi log, nên thu thập:

- Loại statement hoặc tên truy vấn có kiểm soát, **không** log dữ liệu nhạy cảm.
- Timeout đã cấu hình và khoảng thời gian thực tế.
- `SQLState`, mã lỗi DBMS (`SQLException.getErrorCode()`), tên driver/DBMS khi cần điều tra.
- Transaction đã rollback được hay kết quả còn không rõ.
- Thời gian mượn connection, thời gian thực thi SQL, thời gian chờ khóa (nếu DBMS cung cấp).
- Tỷ lệ lỗi timeout, p95/p99 latency và mức sử dụng connection pool.

Với hệ thống dùng JDBC qua framework, kiểm tra framework có đặt query timeout riêng, transaction timeout hoặc ghi đè giá trị trước khi thực thi không. Không nên giả định rằng chỉ cấu hình một giá trị ở service sẽ áp dụng cho mọi `Statement` mới được tạo.

## 10. Các lỗi phổ biến khi thiết lập query timeout

| Sai lầm | Hậu quả | Cách làm đúng |
|---|---|---|
| Dùng `setQueryTimeout(5000)` vì tưởng đơn vị mili giây | Đặt tới 5.000 giây thay vì 5 giây. | Truyền `5` cho 5 giây; ghi rõ đơn vị cấu hình. |
| Dùng `setQueryTimeout(0)` để yêu cầu hủy ngay | `0` nghĩa là không giới hạn qua thuộc tính query timeout. | Dùng thời hạn dương phù hợp, hoặc cơ chế cancel/deadline khi cần dừng. |
| Không đặt timeout trên chính statement chạy SQL | Một statement khác không kế thừa cấu hình của statement trước. | Cấu hình từng `Statement/PreparedStatement/CallableStatement` đúng lúc tạo. |
| Chỉ cấu hình login timeout rồi nghĩ SQL sẽ bị giới hạn | Kết nối có thể được tạo nhanh nhưng query vẫn chạy lâu. | Dùng `setQueryTimeout(...)` cho thời gian thực thi SQL. |
| Nghĩ query timeout bao phủ chờ pool hoặc toàn request | Request có thể hết deadline trước hoặc sau lời gọi SQL. | Phối hợp pool acquisition timeout, request deadline và query timeout. |
| Cho rằng timeout chính xác từng mili giây | JDBC API nhận giây và hành vi hủy phụ thuộc driver/DBMS. | Đo thời gian thực tế, có ngân sách dự phòng. |
| Bắt `SQLTimeoutException` rồi coi là “không có bản ghi” | Timeout là lỗi thực thi, không có nghĩa truy vấn trả 0 hàng. | Trả trạng thái lỗi phù hợp và chỉ đọc kết quả khi truy vấn thành công. |
| Timeout `UPDATE` nhưng vẫn `commit()` | Có nguy cơ xác nhận trạng thái chưa kiểm soát. | Dừng luồng thành công, cố gắng rollback transaction chưa commit. |
| Gọi `rollback()` rồi tin chắc đã hoàn tác dù kết nối hỏng | Rollback có thể không thực hiện được. | Kiểm tra lỗi rollback, đánh dấu trạng thái chưa rõ và đối soát. |
| Retry mọi timeout ngay lập tức | Tăng tải DB và có thể tạo tác động lặp. | Retry có giới hạn, backoff, idempotency và chính sách theo nghiệp vụ. |
| Dùng `Thread.interrupt()` làm bảo đảm hủy SQL | Driver có thể vẫn đang thực thi trên DBMS. | Dùng `Statement.cancel()` khi hỗ trợ và xử lý vòng đời cẩn thận. |
| Chỉ tối ưu timeout thay vì SQL | Query vẫn chậm vì thiếu index, lock hoặc kế hoạch xấu. | Phân tích execution plan, chỉ mục, truy vấn và transaction. |
| Bỏ qua `SQLException` không phải `SQLTimeoutException` | Một số driver có thể báo lỗi timeout theo SQLState/mã vendor. | Ghi nhận ngoại lệ SQL đầy đủ và kiểm chứng driver cụ thể. |

## 11. Kiểm chứng trên DBMS và driver thực tế

Chỉ tạo các thử nghiệm gây chậm hoặc chờ khóa trong **cơ sở dữ liệu kiểm thử**, không làm trên môi trường sản xuất hoặc DB dùng chung.

### Bài 1 — Kiểm tra cấu hình của Statement

1. Tạo `Statement` từ `Connection`.
2. In `getQueryTimeout()` trước khi cấu hình.
3. Gọi `setQueryTimeout(2)`, đọc lại bằng `getQueryTimeout()`.
4. Gọi `setQueryTimeout(0)`, đọc lại một lần nữa.
5. Thử số âm trong môi trường kiểm thử và quan sát `SQLException`.

Mục tiêu là hiểu API và đơn vị **giây**, không phải dùng `0` như thời hạn tức thì.

### Bài 2 — Phân biệt query nhanh và query chậm

Chạy một câu `SELECT` nhanh với `setQueryTimeout(1)`, rồi chạy một câu SQL được thiết kế có kiểm soát để chậm hơn giới hạn theo cú pháp của DBMS đang dùng. Ghi nhận thời điểm bắt đầu, thời điểm nhận exception, kiểu exception, `SQLState` và mức độ khớp giữa số giây cấu hình và thời gian thực tế.

Không có một câu “ngủ N giây” chuẩn dùng cho mọi DBMS; chức năng `SLEEP`, `pg_sleep`, `WAITFOR` hoặc cơ chế tương đương là **đặc thù hệ quản trị**. Hãy dùng cú pháp chính thức và giới hạn tài nguyên của môi trường thử nghiệm.

### Bài 3 — Timeout do chờ khóa

1. Mở kết nối A, bắt đầu một transaction và cập nhật một hàng thử nghiệm nhưng chưa commit.
2. Trên kết nối B, đặt query timeout ngắn rồi thử cập nhật cùng hàng.
3. Quan sát B có chờ và ném `SQLTimeoutException` hoặc lỗi timeout/lock cụ thể của DBMS không.
4. Kết thúc A bằng `rollback()` hoặc `commit()`, xác minh trạng thái của cả hai transaction.

Nếu DBMS có lock timeout riêng, hãy so sánh hiệu ứng với query timeout; không coi chúng là một API duy nhất.

### Bài 4 — Thời gian đọc ResultSet

Chạy `SELECT` trả nhiều hàng ở môi trường test, đặt query timeout ngắn, cố tình làm chậm xử lý Java giữa các lần `rs.next()`. Ghi nhận tổng thời gian tiêu thụ `ResultSet` và xem driver có tiếp tục tính query timeout trong giai đoạn fetch hay không. Không suy từ kết quả ở một driver sang mọi driver khác.

### Bài 5 — Timeout của transaction ghi

Dùng `StockReservation.reserve(...)`, tạo tình huống statement bị timeout do chờ khóa. Kiểm tra nhánh `catch` cố rollback, không commit; sau đó mở transaction đọc mới để đối soát số lượng tồn. Làm lại với lỗi rollback giả lập ở tầng test để thấy vì sao phải giữ thông tin lỗi phụ.

### Bài 6 — Query timeout và pool acquisition timeout

Giữ toàn bộ connection của một pool kiểm thử nhỏ trong một thời gian ngắn có kiểm soát, rồi cho một request khác gọi `getConnection()`. Quan sát request có thể timeout khi **chưa tạo Statement**. So sánh với trường hợp mượn thành công nhưng SQL bị query timeout. Ghi log hai loại thời gian riêng.

### Bài 7 — Tính năng cancel

Trong môi trường kiểm thử, cho một thread thực thi câu SQL chạy đủ lâu. Một thread điều phối được quyền yêu cầu `statement.cancel()` trên **đúng statement** đã chạy, kiểm tra kết quả, vòng đời statement và connection. Không dùng chung statement cho các thao tác SQL khác và không coi cancel là cam kết rollback tự động.

## 12. Câu hỏi tự kiểm tra

**1. `Statement.setQueryTimeout(5)` nhận giây hay mili giây?**

Nhận **giây**. Giá trị `5` biểu thị giới hạn thực thi khoảng 5 giây theo cơ chế driver hỗ trợ.

**2. `setQueryTimeout(0)` có nghĩa là SQL phải hoàn thành ngay không?**

Không. `0` nghĩa là không đặt giới hạn qua thuộc tính query timeout; những timeout ở lớp khác vẫn có thể áp dụng.

**3. `setQueryTimeout` trên Statement A có áp dụng cho PreparedStatement B không?**

Không tự động. Cấu hình gắn với từng đối tượng `Statement` (bao gồm các lớp con); phải đặt trên chính statement sẽ chạy SQL.

**4. Nếu `executeQuery()` ném `SQLTimeoutException`, có thể trả danh sách rỗng như một kết quả bình thường không?**

Không. Danh sách rỗng thể hiện truy vấn đã chạy thành công và trả 0 hàng; timeout là lỗi thực thi chưa hoàn tất bình thường.

**5. Query timeout có giới hạn luôn thời gian `ResultSet.next()`, chờ connection pool và `commit()` không?**

Không có bảo đảm chung. Query timeout chủ yếu dành cho `Statement` thực thi; các giai đoạn khác cần cơ chế riêng và phải xác minh với driver.

**6. Nếu `executeUpdate()` bị timeout khi auto-commit tắt, ứng dụng nên làm gì?**

Không commit theo đường thành công; cố gắng rollback transaction chưa xác nhận, giữ đầy đủ thông tin lỗi và kiểm tra kết quả khi có nghi ngờ.

**7. Có thể thay `Statement.cancel()` bằng `Thread.interrupt()` để chắc chắn ngắt SQL không?**

Không. Việc ngắt Java thread không đồng nghĩa DBMS đã hủy statement; dùng cơ chế cancel do JDBC/driver hỗ trợ và kiểm tra vòng đời.

**8. Có thể dùng cùng một query timeout cho lookup nhanh, báo cáo phức tạp và batch ghi không?**

Có thể, nhưng thường không tối ưu. Nên dựa trên workload, latency thực tế, deadline tổng và độ an toàn khi retry để chọn chính sách.

## 13. Checklist áp dụng trong ứng dụng

- Có xác định **đúng đơn vị giây** và coi `0` là không giới hạn tại `Statement`, không phải timeout tức thì?
- `setQueryTimeout(...)` được gọi **trước execute** trên chính `Statement/PreparedStatement/CallableStatement` đang dùng?
- Có kiểm tra `getQueryTimeout()`, hỗ trợ của driver và thời gian timeout thực tế trên DBMS triển khai?
- Có phân biệt query timeout với login timeout, thời gian mượn pool, network timeout, lock timeout, transaction timeout và request deadline?
- Có đóng `ResultSet`, `Statement` và `Connection` dù câu SQL bị timeout, bằng `try-with-resources`?
- Với DML, transaction có kết thúc rõ ràng bằng `commit/rollback`, không coi timeout là bằng chứng thay đổi chưa được áp dụng?
- Có giữ `SQLState`, vendor error code và lỗi rollback dưới dạng suppressed khi cần chẩn đoán?
- Nếu hỗ trợ retry, có backoff, giới hạn số lần, deadline còn lại và **idempotency** cho thao tác có tác dụng phụ?
- Có kế hoạch dùng `Statement.cancel()` từ cơ chế điều phối được kiểm soát khi người dùng chủ động hủy?
- Query timeout có được phối hợp với tối ưu SQL, chỉ mục, fetch size/số hàng và giới hạn thời gian tổng thể, thay vì được dùng như giải pháp duy nhất?

**Ghi nhớ:** `Statement.setQueryTimeout(int seconds)` đặt một **giới hạn thời gian thực thi cho statement tính bằng giây**; `getQueryTimeout()` cho biết cấu hình mà statement báo về. Khi driver phát hiện quá hạn, nó có thể hủy câu SQL và ném `SQLTimeoutException`, nhưng thời điểm/hành vi hủy còn tùy driver và DBMS. Ứng dụng vẫn phải quản lý `Connection`, `ResultSet`, transaction, retry và những timeout khác một cách độc lập. Đặt đúng query timeout giúp kiểm soát rủi ro truy vấn chạy lâu, nhưng không thay thế SQL hiệu quả hoặc thiết kế giao dịch an toàn.
