# Phát hiện rò rỉ và kết nối bị giữ quá lâu trong JDBC connection pool

Trong chương **Pool kết nối**, ứng dụng Java thường lấy `Connection` từ một `DataSource` có pool, thực hiện truy vấn thông qua `PreparedStatement`/`ResultSet` rồi gọi `close()`. Pool tái sử dụng kết nối vật lý để tránh chi phí liên tục mở kết nối mới tới cơ sở dữ liệu. Cơ chế này giúp tăng thông lượng, nhưng một kết nối **không được trả lại** hoặc **được giữ quá lâu** có thể khiến những request khác phải chờ, dù SQL của chúng hoàn toàn bình thường.

Ví dụ, API tra cứu khách hàng mượn một connection, gọi `SELECT` và trả về kết quả. Nếu một nhánh xử lý lỗi quên đóng connection, số kết nối đang được mượn (*active/borrowed*) có thể tăng dần cho tới khi chạm giới hạn pool. Trường hợp khác, code **vẫn đóng** kết nối nhưng giữ nó trong lúc gọi HTTP API bên ngoài hoặc xuất báo cáo rất lâu: pool vẫn cạn vì mỗi request giữ tài nguyên quá lâu. Hai tình huống có triệu chứng gần giống nhau nhưng phải xử lý khác nhau.

Bài này hướng dẫn nhận diện **connection leak** và **long-held connection**, đọc các chỉ số của pool, đo thời gian mượn/trả, dùng cảnh báo dò rò rỉ của nhà cung cấp khi có hỗ trợ, tìm nguyên nhân trong CRUD/transaction/batching và khắc phục bằng vòng đời JDBC đúng chuẩn. Các ví dụ chủ yếu dùng `DataSource`, `Connection` và `try-with-resources`; các đoạn dùng HikariCP được ghi rõ là **API của thư viện ngoài JDBC chuẩn**.

## 1. Hiểu vòng đời kết nối khi có pool

Luồng thông thường:

```text
Request / Job
    |
    v
DataSource.getConnection()  -----> Pool chọn kết nối còn dùng được
    |                                     |
    v                                     v
Connection được mượn                active tăng
    |
    +--> PreparedStatement.executeQuery/executeUpdate
    |          |
    |          +--> ResultSet / transaction / batch
    |
    v
Connection.close()  -------------> Trả kết nối logic về pool
                                         |
                                         v
                                 active giảm; idle tăng
```

Trong cấu hình pool thông dụng, `Connection` mà code nhận được là một **đại diện logic** (*proxy/wrapper*) của kết nối vật lý. Gọi `connection.close()` thường có nghĩa **trả quyền sử dụng về pool**, không nhất thiết đóng socket tới DB. Khi pool quyết định loại bỏ kết nối hỏng, hết tuổi thọ hoặc đang shutdown, nó mới có thể đóng kết nối vật lý. Hành vi cụ thể phụ thuộc triển khai pool.

Cần phân biệt:

- **Leak thật:** ứng dụng mượn connection và không trả về trong các đường xử lý cần trả; ví dụ quên `close()` khi ném exception.
- **Giữ quá lâu:** connection cuối cùng vẫn được trả, nhưng thời gian từ `getConnection()` thành công đến `close()` lớn bất thường, khiến các request khác phải chờ.
- **Pool cạn kết nối:** trạng thái thiếu connection sẵn có; có thể do leak, truy vấn chậm, transaction/khóa DB, lưu lượng vượt công suất hoặc cấu hình pool. **Không thể kết luận leak chỉ từ lỗi timeout.**
- **Kết nối vật lý lỗi:** DB đóng socket, mạng gián đoạn hoặc connection bị đánh dấu không dùng được. Đây không tự động là lỗi leak; pool phải kiểm tra và thay thế kết nối theo chính sách.

### Tại sao chỉ đóng `Statement`/`ResultSet` chưa đủ?

`ResultSet` gắn với `Statement`, còn statement thuộc `Connection`. Đóng các đối tượng con là cần thiết để giải phóng cursor và tài nguyên, nhưng **không thay thế việc trả `Connection` về pool**:

```java
Connection connection = dataSource.getConnection();
PreparedStatement ps = connection.prepareStatement(
        "SELECT email FROM customer WHERE id = ?");
// Nếu ở đây ném SQLException và không có finally/try-with-resources,
// cả ps lẫn connection có thể không được đóng.
```

Thiết kế tốt nhất là mỗi nơi mượn kết nối cũng phải có quy tắc đóng rõ ràng, trừ khi kết nối được quản lý hoàn toàn bởi transaction manager ở tầng ngoài.

## 2. Triệu chứng và chỉ số cần theo dõi

Pool thường cung cấp một nhóm chỉ số tương đương nhau, dù tên metric khác theo thư viện và hệ thống quan sát:

| Chỉ số/tín hiệu | Ý nghĩa | Cách diễn giải thận trọng |
| --- | --- | --- |
| **Active / in-use / borrowed** | Số connection đang được mượn | Luôn cao không tự chứng minh leak; có thể vì request dài hoặc nhu cầu lớn |
| **Idle / available** | Số connection rảnh trong pool | Bằng 0 trong lúc tải tăng có thể bình thường nếu pool đang bận |
| **Total / pool size** | Số connection pool đang quản lý | Thường gồm active và idle; có thể biến động theo chính sách tạo/loại |
| **Pending / waiting threads** | Số yêu cầu đang chờ mượn kết nối | Kéo dài cùng active sát giới hạn là dấu hiệu nghẽn |
| **Acquisition / borrow wait time** | Thời gian chờ `getConnection()` thành công | Tăng khi thiếu connection sẵn có hoặc khi pool gặp sự cố |
| **Checkout / hold duration** | Thời gian giữa mượn và trả connection | Là tín hiệu trực tiếp để tìm connection bị giữ quá lâu |
| **Acquisition timeout count** | Lượt chờ vượt giới hạn do pool cấu hình | Phải điều tra nguyên nhân thay vì chỉ tăng kích thước pool |
| **DB sessions / long-running transactions** | Trạng thái phiên kết nối ở phía DB | Giúp phân biệt SQL chậm, đợi khóa và kết nối idle-in-transaction |

Không nên chỉ nhìn một ảnh chụp metric. Quan sát **xu hướng theo thời gian**, thời điểm lưu lượng tăng/giảm, phiên bản vừa deploy, số request đồng thời và các chỉ số DB tương ứng.

Một mô hình khả nghi:

```text
Active: 2 -> 4 -> 6 -> 8 -> 10 -> 10
Idle:   8 -> 6 -> 4 -> 2 ->  0 ->  0
Waiters:0 -> 0 -> 0 -> 1 -> 5 -> 12
```

Số liệu chỉ mang tính minh họa. **Giả thuyết** là pool đang không nhận đủ kết nối trả về; cần kiểm tra thời gian giữ và stack trace. Nếu active giảm về mức bình thường sau đợt xử lý dài, đó có thể là hiện tượng *long hold*, không phải leak tồn tại vĩnh viễn.

### Quan hệ giữa tải, thời gian giữ và số kết nối

Với tải ổn định, nhu cầu connection đồng thời có xu hướng tăng khi **số công việc DB mỗi giây** hoặc **thời gian giữ một connection** tăng. Có thể dùng trực giác từ định luật Little:

```text
Số connection trung bình đang bận
    xấp xỉ
Số công việc cần connection hoàn tất mỗi giây
    nhân với
Thời gian trung bình giữ connection (giây)
```

Đây là cách lập luận định tính về công suất, không phải công thức đảm bảo đủ pool cho mọi tải. Khi có phân phối độ trễ dài, spike hoặc transaction chờ khóa, cần đo cả percentile cao và số yêu cầu chờ.

## 3. Những nguyên nhân rò rỉ phổ biến trong code JDBC

### Không đóng trên mọi nhánh exception

```java
// SAI: không có finally hoặc try-with-resources.
Connection connection = dataSource.getConnection();
PreparedStatement ps = connection.prepareStatement(
        "UPDATE account SET status = ? WHERE id = ?");
ps.setString(1, "ACTIVE");
ps.setLong(2, accountId);
ps.executeUpdate();
connection.close(); // Bị bỏ qua nếu một bước phía trên ném lỗi.
```

Ngược lại, dùng `try-with-resources` bảo đảm các tài nguyên khai báo sẽ được cố gắng đóng kể cả khi bind tham số hay thực thi SQL thất bại.

### Trả `ResultSet`/`Stream` phụ thuộc vào connection ra khỏi phạm vi sở hữu

```java
// THIẾT KẾ KHÔNG AN TOÀN: ai và khi nào đóng connection?
public ResultSet loadRows() throws SQLException {
    Connection c = dataSource.getConnection();
    PreparedStatement ps = c.prepareStatement("SELECT * FROM customer");
    return ps.executeQuery();
}
```

Nếu bên gọi quên đóng toàn bộ chuỗi tài nguyên, connection sẽ bị giữ. Nếu repository đóng connection trước khi trả, `ResultSet` cũng không còn sử dụng an toàn. Hãy **đọc/ánh xạ kết quả bên trong phạm vi mở kết nối**, trả DTO hoặc tập dữ liệu ngoại tuyến phù hợp; với streaming, phải thiết kế API mà bên tiêu thụ quản lý vòng đời rõ ràng.

### Mượn connection trước khi làm việc không cần DB

```java
// SAI VỀ PHẠM VI GIỮ CONNECTION (dù có close cuối cùng).
try (Connection connection = dataSource.getConnection()) {
    callExternalPaymentApi();     // Có thể mất hàng giây hoặc timeout.
    generateLargePdfDocument();   // Có thể tốn CPU/I/O.
    persistPayment(connection);   // Chỉ bước này cần DB.
}
```

Nếu các thao tác ngoài DB không cần cùng transaction, hãy làm trước/sau phạm vi mượn connection. Nếu nghiệp vụ phải phối hợp DB và hệ thống ngoài, cần thiết kế idempotency, outbox, saga hoặc quy trình nhất quán tương ứng; **không giải quyết bằng cách giữ connection qua một lời gọi mạng chậm**.

### Transaction mở mà không kết thúc

`setAutoCommit(false)` không tự `commit` hay `rollback`. Một transaction mở có thể giữ khóa, snapshot và connection; truy vấn tiếp theo có thể chờ khóa trong khi pool vẫn thấy connection đang được mượn. Ngay cả transaction chỉ đọc cũng có thể giữ tài nguyên DB nếu kéo dài.

### Xử lý bất đồng bộ sai quyền sở hữu

Truyền một `Connection` cho task bất đồng bộ rồi đóng ở request gốc, hoặc ngược lại để callback giữ connection không thời hạn, đều dễ gây lỗi. Đa số ứng dụng JDBC nên **mượn và trả connection trong cùng đơn vị công việc đồng bộ**; chỉ truyền connection giữa các luồng nếu contract của provider và cơ chế quản lý transaction cho phép và đã kiểm chứng.

## 4. Viết repository tự trả kết nối về pool

Ví dụ thao tác đọc một khách hàng qua `DataSource`:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import javax.sql.DataSource;

public final class CustomerRepository {
    private final DataSource dataSource;

    public CustomerRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Optional<String> findEmail(long id) throws SQLException {
        String sql = "SELECT email FROM customer WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, id);

            try (ResultSet rs = ps.executeQuery()) {
                if (rs.next()) {
                    return Optional.ofNullable(rs.getString("email"));
                }
                return Optional.empty();
            }
        }
    }
}
```

Đường đi thành công, không tìm thấy hàng và ngoại lệ đều đi qua cơ chế đóng tài nguyên. `ResultSet` đóng trước `PreparedStatement`, sau cùng mới đến `Connection`. Với `DataSource` backed by pool, `close()` của connection logic trả kết nối cho pool khi trạng thái hợp lệ.

**Đừng coi `Connection.close()` là tùy chọn** chỉ vì đang dùng pool. Đó chính là tín hiệu để pool lấy lại kết nối.

Nếu repository nhận `Connection` từ caller (chẳng hạn trong một transaction nhiều bước), repository **không nên tự đóng connection của caller**. Khi đó tầng đã mượn/được giao quyền sở hữu connection phải đảm bảo một nơi kết thúc transaction và trả connection; trách nhiệm này cần thể hiện trong API và quy tắc code review.

## 5. Đo thời gian chờ mượn và giữ kết nối

Một kỹ thuật đơn giản là đo hai khoảng thời gian khác nhau:

1. **Acquisition time:** từ trước `dataSource.getConnection()` tới lúc nhận connection.
2. **Hold time:** từ lúc nhận connection đến sau khi khối `try-with-resources` đã đóng/trả nó.

Dùng `System.nanoTime()` để đo **khoảng thời gian** thay vì lấy hiệu từ đồng hồ hệ thống `currentTimeMillis()`, vì đồng hồ lịch có thể bị chỉnh.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.concurrent.TimeUnit;
import javax.sql.DataSource;

public static long countCustomers(DataSource dataSource) throws SQLException {
    long acquisitionStarted = System.nanoTime();
    Connection connection = dataSource.getConnection();
    long borrowedAt = System.nanoTime();

    try (connection) { // Java 9+: connection là biến effectively final.
        try (PreparedStatement ps = connection.prepareStatement(
                "SELECT COUNT(*) FROM customer");
             ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) {
                throw new SQLException("COUNT(*) không trả hàng nào");
            }
            return rs.getLong(1);
        }
    } finally {
        long releasedAt = System.nanoTime(); // Đã chạy connection.close().
        long acquireMs = TimeUnit.NANOSECONDS.toMillis(
                borrowedAt - acquisitionStarted);
        long holdMs = TimeUnit.NANOSECONDS.toMillis(
                releasedAt - borrowedAt);

        System.out.printf(
                "JDBC customer-count acquire=%dms hold=%dms%n",
                acquireMs, holdMs);
    }
}
```

Đây là ví dụ đo cho **lời gọi `getConnection()` thành công**. Nếu `getConnection()` ném `SQLException` vì timeout, cần ghi nhận thời gian chờ ở một khối bắt lỗi quanh bước acquisition riêng. Trong production nên dùng metrics/logging có nhãn như `operation=customer-count`, thay vì dùng `System.out`.

**Lưu ý độ chính xác:** thời gian `holdMs` bao gồm cả thời gian đóng/trả connection, còn `acquireMs` có thể gồm kiểm tra/tạo kết nối vật lý nếu pool cần bổ sung tài nguyên. Một khoảng hold dài không chứng minh SQL là nguyên nhân; hãy đo riêng **thời gian thực thi câu SQL**, thời gian chờ khóa và thời gian xử lý dữ liệu trong cùng scope.

Đừng log nguyên câu SQL có giá trị người dùng hoặc thông tin định danh kết nối chứa credential. Chỉ log tên thao tác an toàn, thời gian, trạng thái thành công/thất bại, mã SQLState nếu có và correlation ID không nhạy cảm.

## 6. Dò rò rỉ bằng tính năng của pool: ví dụ HikariCP

`DataSource` là API chuẩn JDBC, nhưng các khả năng theo dõi pool **không được chuẩn hóa trong `javax.sql.DataSource`**. HikariCP là một thư viện pool phổ biến, có cấu hình `leakDetectionThreshold`: nếu một connection được mượn lâu hơn ngưỡng, pool có thể ghi cảnh báo và stack trace của vị trí mượn.

Ví dụ cấu hình minh họa (phụ thuộc `com.zaxxer:HikariCP`):

```java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

HikariConfig config = new HikariConfig();
config.setJdbcUrl(System.getenv("JDBC_URL"));
config.setUsername(System.getenv("DB_USER"));
config.setPassword(System.getenv("DB_PASSWORD"));

config.setMaximumPoolSize(10);
config.setConnectionTimeout(3_000);       // mili giây, ví dụ.
config.setLeakDetectionThreshold(10_000); // mili giây, ví dụ.

try (HikariDataSource pool = new HikariDataSource(config)) {
    CustomerRepository repository = new CustomerRepository(pool);
    System.out.println(repository.findEmail(42L));
}
```

**Giá trị cấu hình chỉ phục vụ minh họa**, không phải đề xuất cố định cho mọi hệ thống. Ngưỡng dò leak phải dài hơn thời gian giữ connection hợp lệ trong tải bình thường, và giới hạn pool phải được chọn từ đo đạc thực tế cùng công suất DB. Biến môi trường cũng cần được xác nhận tồn tại; hệ thống production nên dùng cơ chế quản lý bí mật phù hợp, không đưa mật khẩu ra log.

### Cảnh báo “possible connection leak” không phải kết luận cuối

- Stack trace trong cảnh báo thường cho biết **nơi mượn connection**, không tự chỉ ra statement nào chậm hay nơi quên đóng.
- Một báo cáo dài nhưng sau đó gọi `close()` có thể bị cảnh báo là *suspected leak*, dù thực tế không rò rỉ vĩnh viễn. Một số phiên bản pool có thể ghi thêm sự kiện connection được trả sau cảnh báo.
- Khi không thấy cảnh báo, **không thể chứng minh hệ thống không có leak**. Cần xem ngưỡng, mức log, việc bật tính năng, đường chạy code và metrics.
- Bật cảnh báo cho nhiều pool và nhiều instance có thể tạo log lớn; chỉ bật hoặc điều chỉnh ngưỡng theo kế hoạch chẩn đoán, không coi nó là cách sửa leak.

HikariCP còn có `HikariPoolMXBean`, cung cấp các phép đo tại thời điểm đọc:

```java
import com.zaxxer.hikari.HikariPoolMXBean;
import com.zaxxer.hikari.HikariDataSource;

public static void printPoolState(HikariDataSource pool) {
    HikariPoolMXBean state = pool.getHikariPoolMXBean();
    if (state == null) {
        return; // Chưa có pool hoạt động hoặc chưa lấy được MXBean.
    }

    System.out.printf(
            "active=%d idle=%d total=%d awaiting=%d%n",
            state.getActiveConnections(),
            state.getIdleConnections(),
            state.getTotalConnections(),
            state.getThreadsAwaitingConnection());
}
```

Những chỉ số tức thời có thể thay đổi ngay sau lời gọi getter; không nên dùng chúng để suy ra một snapshot nguyên tử tuyệt đối. Để quan sát dài hạn, tích hợp JMX/metrics (ví dụ bộ quan sát của ứng dụng) và lưu chuỗi thời gian.

**Tính khả chuyển:** tên cấu hình, định nghĩa cảnh báo, phương thức MXBean và hỗ trợ metrics thuộc **HikariCP**, không áp dụng nguyên xi cho Apache Commons DBCP, c3p0 hay pool của application server. Với pool khác, đọc tài liệu tương ứng. Đừng ép kiểu một `DataSource` bất kỳ sang `HikariDataSource`.

## 7. Rò rỉ và truy vấn chậm: phân biệt bằng bằng chứng

Khi active cao và waiter tăng, hãy hỏi:

| Tình huống | Quan sát bổ sung | Giả thuyết phù hợp |
| --- | --- | --- |
| Active tăng dần, không trở về mức thấp sau khi hết tải | Checkout stack lặp lại, request đã hoàn tất nhưng connection không trả | Có đường code quên `close()` |
| Active cao trong thời gian tạo báo cáo, sau đó giảm | Hold time dài ở một số thao tác; không còn dư kết nối sau khi job xong | Giữ quá lâu nhưng không nhất thiết leak |
| SQL time rất cao, DB có nhiều session chờ khóa | Stack thread chờ trong `executeQuery/executeUpdate` | Query/khóa DB khiến connection bận |
| Nhiều thread chờ `getConnection()`, DB ít hoạt động | Pool không còn connection cấp mới; các connection đang được mượn ở đâu? | Leak, long hold hoặc pool giới hạn quá thấp |
| Acquisition time cao nhưng active không sát giới hạn lâu dài | Pool/DB có thể đang tạo/kiểm tra connection chậm hoặc mạng lỗi | Không kết luận leak |
| Log “connection leak detected” rồi có thông báo connection trả lại | Hold time vượt ngưỡng nhưng connection được trả | Cảnh báo chậm trả, không đủ kết luận leak thật |

Ngoài metric pool, có thể sử dụng:

- **Thread dump / stack trace** để xem luồng đang chờ mượn connection, thực thi SQL, đợi khóa hay xử lý HTTP khi giữ connection.
- **DB monitoring** để xem câu SQL đang chạy, khóa và phiên ở trạng thái idle-in-transaction (nếu DB cung cấp).
- **Trace theo request** để đối chiếu thời điểm mượn/trả với HTTP endpoint, job, thời gian SQL và call ngoài DB.
- **Log SQLState/vendor code** khi lỗi timeout/connection/transaction phát sinh, nhưng không cho rằng tất cả driver báo cùng mã.

Nếu code có transaction kéo dài, hãy điều tra **ranh giới giao dịch trước** khi tăng số kết nối pool. Tăng pool size có thể chỉ che tạm thời leak và đẩy thêm áp lực lên giới hạn session của DB.

## 8. Transaction: tránh connection ở trạng thái không rõ ràng

Một transaction CRUD gồm nhiều thao tác phải dùng **cùng một `Connection`** và kết thúc rõ ràng. Ví dụ chuyển tiền chỉ minh họa ranh giới connection:

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class TransferRepository {
    private final DataSource dataSource;

    public TransferRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void transfer(long from, long to, BigDecimal amount)
            throws SQLException {
        if (from == to || amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("Thông tin chuyển tiền không hợp lệ");
        }

        try (Connection connection = dataSource.getConnection()) {
            // Mẫu tự sở hữu transaction này yêu cầu kết nối vừa lấy
            // chưa tham gia transaction ngoài.
            if (!connection.getAutoCommit()) {
                throw new SQLException(
                        "Ví dụ yêu cầu autoCommit=true khi bắt đầu");
            }

            connection.setAutoCommit(false);
            boolean transactionEnded = false;
            try {
                String debitSql = """
                        UPDATE account
                        SET balance = balance - ?
                        WHERE id = ? AND balance >= ?
                        """;
                try (PreparedStatement ps =
                        connection.prepareStatement(debitSql)) {
                    ps.setBigDecimal(1, amount);
                    ps.setLong(2, from);
                    ps.setBigDecimal(3, amount);
                    if (ps.executeUpdate() != 1) {
                        throw new SQLException(
                                "Nguồn không tồn tại hoặc số dư không đủ");
                    }
                }

                String creditSql =
                        "UPDATE account SET balance = balance + ? WHERE id = ?";
                try (PreparedStatement ps =
                        connection.prepareStatement(creditSql)) {
                    ps.setBigDecimal(1, amount);
                    ps.setLong(2, to);
                    if (ps.executeUpdate() != 1) {
                        throw new SQLException("Đích không tồn tại");
                    }
                }

                connection.commit();
                transactionEnded = true;
            } catch (SQLException | RuntimeException failure) {
                if (!transactionEnded) {
                    try {
                        connection.rollback();
                        transactionEnded = true;
                    } catch (SQLException rollbackFailure) {
                        failure.addSuppressed(rollbackFailure);
                    }
                }
                throw failure;
            } finally {
                if (transactionEnded) {
                    connection.setAutoCommit(true);
                }
                // Không setAutoCommit(true) khi rollback thất bại:
                // có thể gây commit ngoài ý muốn.
            }
        }
    }
}
```

Ví dụ giả định có bảng `account(id, balance)` với số dư có kiểu SQL chính xác (`DECIMAL`), `amount` đã được chuẩn hóa theo số chữ số thập phân của nghiệp vụ và DB hỗ trợ transaction trên bảng đó. `PreparedStatement` của từng bước được đóng ngay, transaction được kết thúc trước khi trả connection.

Ngay cả ở nhánh lỗi, `try-with-resources` sẽ cố đóng `Connection`. Nếu `rollback()` thất bại, connection có thể ở trạng thái không đáng tin cậy; **ứng dụng không được giả định pool đã reset an toàn mọi thuộc tính**. Tùy pool/driver, cần đánh dấu hoặc loại bỏ kết nối hỏng theo cơ chế nhà cung cấp và giám sát lỗi cleanup. Nếu `commit()` lỗi do mất kết nối, kết quả giao dịch cũng có thể không xác định; không tự retry một lệnh chuyển tiền khi thiếu idempotency.

**Tách quyền sở hữu:** Khi dùng Spring/JTA hoặc transaction manager khác, repository không tự bật/tắt `autoCommit` và không tự `close()` connection đang do transaction manager quản lý. Hãy để tầng sở hữu transaction quyết định commit/rollback và trả về pool.

## 9. Các tác vụ thường khiến connection bị giữ lâu

### Truy vấn đọc rất nhiều hàng hoặc BLOB/CLOB

`ResultSet` dạng streaming có thể giảm mức nhớ Java nhưng giữ connection trong suốt quá trình đọc. Nếu kết quả được xử lý chậm, pool thấy connection active lâu. `ResultSet.getBinaryStream()` hoặc `getCharacterStream()` thường yêu cầu giữ tài nguyên JDBC còn mở cho đến khi đọc hết luồng. **Không trả một stream gắn với ResultSet ra ngoài mà không có hợp đồng đóng rõ ràng.**

Giải pháp tùy bài toán:

- Phân trang hoặc chia thành các đợt đọc nhỏ bằng SQL tham số hóa, mỗi đợt trả connection sớm.
- Xử lý và ghi ra đích trong một phạm vi có timeout/giám sát phù hợp, nếu bắt buộc cần streaming trực tiếp.
- Khi cần xử lý ngoại tuyến, ánh xạ ra DTO hoặc `CachedRowSet` cho tập dữ liệu **vừa phải** rồi đóng connection; lưu ý bản sao ngoại tuyến tốn heap.
- Không tăng `fetchSize` hay thay chế độ cursor mù quáng: cách driver triển khai streaming, transaction và fetch size khác nhau.

### Batch lớn, cập nhật nhiều bảng

Một `executeBatch()` kéo dài có thể giữ connection và transaction lâu vì số lệnh, khóa, log DB hoặc network. Chia batch thành chunk có thể giảm thời gian giữ connection mỗi lượt, nhưng nếu mỗi chunk commit riêng thì nghiệp vụ **cho phép hoàn thành một phần**; cần thiết kế retry và idempotency phù hợp.

### Gọi mạng, sleep, xử lý CPU trong transaction

Không làm việc không liên quan DB trong phạm vi transaction trừ khi thiết kế nhất quán đòi hỏi và đã xem xét timeout. Tránh giữ connection trong lúc chờ người dùng xác nhận, gọi API thanh toán hoặc đợi tác vụ nền. Khi cần phối hợp nhiều hệ thống, cân nhắc outbox hoặc một quy trình ứng dụng có trạng thái.

### Vòng lặp truy vấn kiểu N+1

Hàng loạt câu `SELECT` tuần tự trong cùng connection có thể khiến checkout kéo dài dù từng SQL nhanh. Điều tra số query mỗi request, cân nhắc `JOIN`, truy vấn theo tập ID hoặc batching phù hợp; bảo đảm kết quả đúng trước khi tối ưu.

## 10. Quy trình chẩn đoán có hệ thống

Khi ứng dụng xuất hiện timeout lúc mượn connection, một trình tự hữu ích là:

1. **Ghi nhận hiện tượng:** thời gian, endpoint/job, phiên bản deploy, số lượng request đang chạy, acquisition timeout và giới hạn pool.
2. **Đọc chuỗi metric:** active, idle, total, waiting, acquisition duration và hold duration. So với đường cơ sở khi không có sự cố.
3. **Phân nhóm truy vấn:** thao tác nào có hold time dài? SQL của chúng có chậm không? Có gọi mạng hay xử lý tệp bên trong phạm vi connection không?
4. **Bật chẩn đoán đúng mức:** dùng cơ chế leak-detection của pool nếu có, lấy stack tại nơi mượn kết nối, tránh ngưỡng quá thấp gây nhiễu.
5. **Đối chiếu DB:** xem session đang chạy SQL, đang chờ khóa, idle-in-transaction hay không; kiểm tra các transaction kéo dài.
6. **Đọc code theo nhánh exception:** tất cả đường đi `return`, `throw`, cancellation, timeout và callback có trả connection không? Ai sở hữu connection khi repository được gọi từ transaction manager?
7. **Tái hiện trong môi trường thử nghiệm:** tạo tải lặp lại có kiểm soát, ghi nhận active/waiters và xác nhận active giảm sau khi hết tải.
8. **Sửa nguyên nhân:** thêm `try-with-resources`, thu hẹp thời gian giữ, kết thúc transaction, sửa SQL/khóa hoặc cấu hình công suất theo kết quả đo.
9. **Kiểm tra hồi quy:** thử cả nhánh thành công, ngoại lệ, timeout, hủy tác vụ, rollback thất bại và tình huống DB tạm mất kết nối.

Không chỉ tăng `maximumPoolSize` rồi coi sự cố đã hết. Nếu mỗi request không trả connection, pool lớn hơn chỉ kéo dài thời gian đến lúc cạn. Nếu nguyên nhân là DB không xử lý kịp, nhiều connection hơn có thể làm tăng cạnh tranh tài nguyên.

## 11. Bài kiểm thử rò rỉ và giữ kết nối quá lâu

Thực hành trên một pool thử nghiệm với giới hạn kết nối nhỏ, ví dụ tối đa **2** connection, không kết nối đến dữ liệu production:

1. **Đường bình thường:** gọi `CustomerRepository.findEmail(...)` nhiều lần. Quan sát active tăng khi xử lý rồi trở về mức thấp khi hoàn tất.
2. **Nhánh lỗi:** cố tình dùng SQL sai hoặc tham số vi phạm ràng buộc và xác nhận sau exception connection vẫn được trả; không dựa vào việc request trả HTTP 500 để kết luận tài nguyên đã dọn dẹp.
3. **Leak có kiểm soát:** trong một test riêng, mượn connection rồi cố tình không `close()` ngay; xác nhận waiter/acquisition timeout tăng khi hết connection. Sau đó test phải đóng **mọi connection đã mượn** trong `finally` để tránh để lại rò rỉ trong môi trường.
4. **Long hold:** giữ một connection trong một phạm vi có kiểm soát rồi trả về sau ngưỡng chẩn đoán; so sánh stack cảnh báo với metric hold duration. Sau khi trả, active phải giảm. Test này cho thấy một cảnh báo leak **chưa đủ** để khẳng định rò rỉ thật.
5. **Khóa DB:** mở transaction A cập nhật một hàng và chưa commit; transaction B thử cập nhật cùng hàng trong môi trường test. Quan sát B có thể chờ khóa và giữ connection, dù code đều dùng `try-with-resources`. Luôn đặt timeout và rollback các transaction.
6. **Stream/BLOB:** đọc nội dung lớn qua `ResultSet.getBinaryStream()`, so thời gian giữ connection với cách đọc dữ liệu theo chunk hoặc sao chép hợp lệ ở tầng khác.
7. **Hồi quy:** thực thi test đồng thời nhiều lần. Sau khi tất cả request/job hoàn thành, xác nhận pool không còn connection bị mượn vô lý và không còn waiter tồn tại kéo dài.

Đối với test nhiều luồng, dùng công cụ đồng bộ như `CountDownLatch` để điều khiển thời điểm mượn/trả thay vì chỉ dựa vào `Thread.sleep(...)`. Có timeout cho test để không treo CI khi có deadlock. Không giữ `Connection` xuyên các luồng chỉ để giảm số lần mượn; mỗi tác vụ nên có phạm vi sở hữu và đóng rõ ràng.

### Câu hỏi tự kiểm tra

- Tại sao `Connection.close()` trong ứng dụng dùng pool thường không đóng socket DB ngay?
- Active bằng giới hạn tối đa và idle bằng 0 có đủ để khẳng định connection leak không? Cần thêm dữ liệu nào?
- Cảnh báo `leakDetectionThreshold` có chứng minh connection không bao giờ được trả không?
- Tại sao một câu `SELECT` nhanh vẫn có thể khiến connection bị giữ lâu?
- Vì sao chuyển việc gọi HTTP API ra ngoài `try (Connection ...)` thường giúp giảm nghẽn pool?
- `Statement.close()` có thay thế được `Connection.close()` trong trách nhiệm trả kết nối không?
- Khi `rollback()` thất bại, vì sao không nên tự ý bật `autoCommit(true)` để “reset” kết nối?
- Trong hệ thống dùng transaction manager, lớp nào phải chịu trách nhiệm cuối cùng về `commit`, `rollback` và trả connection?

## 12. Checklist vận hành

| Việc cần xác nhận | Mục tiêu |
| --- | --- |
| Mọi `getConnection()` đều có chủ sở hữu và đường đóng | Không rò rỉ do bỏ sót nhánh lỗi |
| `PreparedStatement`/`ResultSet` được đóng trong phạm vi hợp lệ | Không giữ cursor, stream hoặc tài nguyên JDBC quá lâu |
| Transaction kết thúc rõ trước khi trả connection | Hạn chế khóa và trạng thái session kéo dài |
| Không giữ connection qua I/O ngoài DB khi không cần | Rút ngắn thời gian mượn |
| Có metric active/idle/waiters/acquisition/hold | Phân biệt leak, tải cao và SQL chậm |
| Có công cụ dò leak đúng phiên bản pool | Tìm stack nơi mượn, không phán đoán chỉ từ ngưỡng |
| Cấu hình giới hạn pool dựa trên tải và công suất DB | Tránh che leak bằng cách tăng pool vô hạn |
| Test nhánh lỗi, cancellation và timeout | Xác minh tài nguyên được trả khi nghiệp vụ không thành công |

**Ghi nhớ:** Trong JDBC có pool, `Connection.close()` thường có nghĩa **trả kết nối về pool**. **Leak thật** là không trả kết nối; **long hold** là có trả nhưng quá chậm. Cả hai có thể làm active sát giới hạn và gây timeout cho request khác. Hãy đo thời gian mượn/trả, quan sát active/idle/waiters, kết hợp dấu vết từ code và DB, dùng `try-with-resources` với quyền sở hữu rõ ràng, kết thúc transaction sớm và chỉ điều chỉnh cấu hình pool sau khi tìm được nguyên nhân.
