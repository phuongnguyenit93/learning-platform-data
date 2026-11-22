# Không lưu Connection trong trường singleton hoặc chia sẻ giữa các luồng

Trong Spring Data Access, một `Connection` JDBC không nên được lưu thành **trường (field) của Spring singleton bean** và không nên truyền cho nhiều luồng dùng đồng thời. `Connection` biểu diễn một phiên làm việc có trạng thái với cơ sở dữ liệu: nó có transaction hiện tại, chế độ `autoCommit`, mức cô lập, schema/catalog, statement và tài nguyên đang mở. Khi nhiều request hoặc nhiều thread cùng thao tác trên một connection, chúng vô tình chia sẻ **cùng phiên và cùng ranh giới giao dịch**; đóng hoặc thay đổi trạng thái ở nơi này có thể làm hỏng công việc của nơi khác.

Quy tắc thực hành:

> **Chia sẻ `DataSource` và `JdbcTemplate` đã cấu hình ổn định; mỗi tác vụ mượn `Connection` khi cần và trả/giải phóng đúng thời điểm.** Trong Spring transaction, để `JdbcTemplate` và transaction manager quản lý connection gắn với luồng. Không lưu `Connection`, `Statement` hay `ResultSet` trong singleton hoặc cache để tái sử dụng tùy tiện.

Bài này tập trung vào **JDBC đồng bộ** (Spring Framework, `DataSource`, `JdbcTemplate` và JDBC transaction manager), đồng thời chỉ ra ranh giới với tác vụ bất đồng bộ. Không nên suy rộng rằng mọi JDBC driver đều lỗi ngay khi một `Connection` được hai thread gọi: một số driver có cơ chế đồng bộ nội bộ. Vấn đề cốt lõi là JDBC **không bảo đảm tính độc lập transaction/phiên** cho hai tác vụ dùng chung một connection, và mức hỗ trợ concurrent access khác nhau theo driver.

## 1. Phân biệt đối tượng được chia sẻ và tài nguyên có vòng đời ngắn

| Đối tượng | Vai trò | Có nên lưu trong singleton và chia sẻ? |
| --- | --- | --- |
| `DataSource` | Nhà cung cấp connection; có thể dùng connection pool như HikariCP. | **Có**, thường là singleton Spring bean được cấu hình một lần. |
| `JdbcTemplate` | Công cụ thực thi SQL; lấy và giải phóng resource theo Spring. | **Có**, thread-safe sau khi cấu hình xong; tránh thay đổi cấu hình trên instance đang dùng. |
| `Repository`/`Service` không có trạng thái từng request | Điều phối logic nghiệp vụ và truy cập DB. | **Có**, thường là singleton; dependency là final và immutable khi thích hợp. |
| `Connection` | Phiên làm việc JDBC, có transaction và trạng thái phiên. | **Không** giữ như field dùng chung; mượn theo tác vụ hoặc transaction. |
| `PreparedStatement`/`Statement` | Lệnh SQL gắn với một connection, có tham số/con trỏ/trạng thái. | **Không** giữ dùng chung giữa request/thread. |
| `ResultSet` | Con trỏ tới kết quả của một statement; có vòng đời gắn với JDBC resource. | **Không** giữ dùng chung hoặc trả ra ngoài phạm vi resource nếu chưa được xử lý đúng cách. |
| DTO/record bất biến đã đọc xong | Ảnh chụp dữ liệu thuần Java, không giữ JDBC handle. | **Có thể**, nếu dữ liệu không nhạy cảm hoặc phụ thuộc vào trạng thái request và thiết kế cho phép. |

`DataSource` có thể là nguồn mở kết nối mới mỗi lần hoặc nguồn có pool. Một pooled `DataSource` là thành phần **quản lý nhiều connection**, không phải một `Connection` để tất cả thread dùng cùng lúc. Mỗi lần mượn thường nhận một handle logic riêng; khi trả, pool có thể tái sử dụng connection vật lý theo cách tuần tự.

### 1.1. Singleton Spring bean có bao nhiêu bản thể?

Mặc định, một Spring bean có scope `singleton` có **một instance trong mỗi Spring IoC container**, và nhiều request có thể cùng gọi các phương thức của instance đó. Spring **không tự thêm khóa** cho mọi phương thức singleton và không tự tạo field riêng cho từng thread.

Ví dụ, trong một `@Repository` singleton, trường `private final JdbcTemplate jdbc;` là dependency dùng chung an toàn khi template đã cấu hình ổn định. Nhưng trường `private Connection connection;` sẽ thành handle dùng chung giữa những request chạy cùng lúc. `final` chỉ cố định **tham chiếu đến đối tượng**, không biến đối tượng JDBC bên trong thành thread-safe.

## 2. Vì sao dùng chung Connection gây lỗi?

### 2.1. Trạng thái transaction thuộc Connection, không thuộc từng lời gọi SQL

Thông thường, một JDBC `Connection` có thuộc tính `autoCommit`. Nếu đặt `setAutoCommit(false)`, các statement thực thi qua connection đó tham gia transaction hiện hành cho đến khi `commit()` hoặc `rollback()`. Hai thread sử dụng **cùng connection** không có hai transaction JDBC độc lập chỉ vì chúng là hai luồng khác nhau.

Kịch bản rủi ro:

```text
Thread A                       Shared Connection                    Thread B
   |                                  |                                  |
   |-- setAutoCommit(false) --------->|                                  |
   |-- UPDATE accounts ... ---------->|  transaction T đã có thay đổi A  |
   |                                  |<--------- UPDATE orders ... -----|
   |                                  |  thay đổi B cũng vào transaction T
   |-- rollback() ------------------->|                                  |
   |                                  |  rollback cả thay đổi A và B      |
   |                                  |                                  |
```

Nếu B tin rằng lệnh update của mình đã độc lập với A thì kết quả nghiệp vụ sẽ sai. Trường hợp B gọi `commit()` còn nguy hiểm hơn: B có thể commit luôn công việc chưa hoàn thành của A. Việc đổi `autoCommit` giữa lúc đang có transaction cũng có thể làm transaction hiện tại được commit theo quy tắc JDBC.

### 2.2. Trạng thái phiên và con trỏ bị ảnh hưởng chéo

Ngoài commit/rollback, connection còn mang trạng thái như:

- `setTransactionIsolation(...)`: mức cô lập giao dịch; thread khác có thể dùng điều kiện cô lập không mong muốn.
- `setReadOnly(...)`: gợi ý/điều khiển chế độ chỉ đọc tùy driver/DB.
- `setCatalog(...)`, `setSchema(...)`: ngữ cảnh DB/schema cho truy vấn.
- `setAutoCommit(...)`: chế độ transaction của cả connection.
- Temporary tables, session variables, lock, statement và cursor: vòng đời và mức hỗ trợ tùy DBMS/driver.
- `close()`: tài nguyên bị đóng/được trả cho pool; đối tượng connection cũ không còn là handle hợp lệ cho tác vụ đang dùng.

Một `PreparedStatement` có tham số và trạng thái riêng. Nếu singleton lưu nó và thread A/B cùng gọi `setLong(1, ...)` rồi `executeUpdate()`, giá trị bind có thể bị dùng sai. Một `ResultSet` có cursor được dịch chuyển bởi `next()`; hai thread đọc chung có thể bỏ qua hàng, gặp trạng thái không hợp lệ hoặc lỗi driver. **Không dùng `synchronized` như một cách thay thế cho mô hình sở hữu resource**: khóa có thể làm chậm tất cả request nhưng không giải quyết được transaction bị giữ lâu, rò rỉ tài nguyên, hoặc nhu cầu các transaction độc lập.

### 2.3. Một thread đóng, thread khác vẫn sử dụng

```text
A: connection.prepareStatement(...)
B: connection.close()
A: statement.executeQuery()  --> có thể nhận SQLException / statement bị vô hiệu
```

Với HikariCP, `close()` trên logical connection thường **trả handle về pool**. Lúc đó một request C có thể mượn lại connection vật lý; A không còn quyền sử dụng handle cũ. Vì vậy, “đã dùng connection pool” không làm việc giữ chung một `Connection` trở nên an toàn.

## 3. Anti-pattern: lưu Connection trong field của singleton

Đây là ví dụ **cố tình sai để nhận diện lỗi thiết kế**, không dùng trong ứng dụng:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

import org.springframework.stereotype.Repository;

@Repository
public class UnsafeEventRepository {
    private final Connection sharedConnection; // SAI: singleton giữ một JDBC session

    public UnsafeEventRepository(DataSource dataSource) throws SQLException {
        this.sharedConnection = dataSource.getConnection(); // mượn từ lúc khởi tạo
    }

    public void addEvent(long id, String message) throws SQLException {
        try (PreparedStatement ps = sharedConnection.prepareStatement(
                "INSERT INTO audit_event(id, message) VALUES (?, ?)")) {
            ps.setLong(1, id);
            ps.setString(2, message);
            ps.executeUpdate();
        }
    }
}
```

Vấn đề:

1. Nhiều request cùng gọi `addEvent()` trên **cùng** `sharedConnection`.
2. Transaction và session state chung; không có isolation giữa các request ở mức connection.
3. Connection bị giữ suốt vòng đời bean, chiếm một slot pool; không có điểm trả resource rõ ràng. Nếu bean bị đóng mà quên `close()`, pool/DB còn phải xử lý resource bị bỏ quên.
4. Nếu connection bị lỗi mạng hoặc DB cắt sau một thời gian, tất cả request sử dụng field này có thể cùng thất bại.
5. `PreparedStatement` mới mỗi lần **không sửa được lỗi chia sẻ Connection**; nó chỉ tránh chia sẻ chính statement.

Một biến thể khác cũng sai:

```java
private static Connection globalConnection; // SAI: toàn JVM chia sẻ một handle
```

Một biến `ThreadLocal<Connection>` tự quản lý cũng **không phải giải pháp mặc định**: thread trong server thường được tái sử dụng, connection có thể bị giữ quá lâu và rò rỉ slot pool; ứng dụng tự làm lệch transaction lifecycle của Spring. Với Spring, hãy dùng `DataSourceUtils` hoặc `JdbcTemplate` để tương thích transaction, thay vì tự gắn connection vào ThreadLocal.

## 4. Cách đúng với JDBC thuần: mượn, dùng, đóng trong một phạm vi

Với mã JDBC không tham gia transaction do Spring quản lý, đặt `Connection`, `PreparedStatement` và `ResultSet` trong biến cục bộ rồi sử dụng **try-with-resources**.

Tệp `SafeEventRepository.java` dưới đây là lớp Java 17+ hợp lệ, yêu cầu một `DataSource` được truyền từ bên ngoài và bảng `audit_event(id, message)` tồn tại:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class SafeEventRepository {
    private final DataSource dataSource; // Chỉ giữ factory/pool

    public SafeEventRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public int addEvent(long id, String message) throws SQLException {
        String sql = "INSERT INTO audit_event(id, message) VALUES (?, ?)";

        try (Connection con = dataSource.getConnection();
             PreparedStatement ps = con.prepareStatement(sql)) {
            ps.setLong(1, id);
            ps.setString(2, message);
            return ps.executeUpdate();
        }
    }
}
```

Hai thread gọi `addEvent()` sẽ có **hai lượt mượn Connection độc lập**. Pool có thể cấp hai connection vật lý khác nhau khi chúng hoạt động đồng thời; cũng có thể tái sử dụng cùng connection vật lý *sau khi* một lượt mượn đã kết thúc. Tác vụ không giữ connection trong field.

Khi luồng thoát khỏi `try`, Java gọi `close()` theo thứ tự ngược (đóng statement rồi connection). Với nguồn pool, đóng logical connection nghĩa là trả về pool khi hợp lệ; với nguồn không pool, thường là đóng physical connection.

Đoạn mã này chỉ minh họa **sở hữu resource**. Nó không tự giải quyết mọi race nghiệp vụ: hai giao dịch khác nhau vẫn có thể cùng cập nhật một hàng, gặp deadlock hoặc lost update nếu chưa thiết kế khóa, isolation, versioning hay câu SQL nguyên tử đúng cách. Connection độc lập là điều kiện cơ bản, không thay thế transaction correctness.

### 4.1. Khi muốn nhiều câu SQL thuộc một transaction JDBC thuần

Một **tác vụ** có thể hợp lệ dùng cùng một Connection cho nhiều statement, miễn là nó sở hữu connection trong phạm vi transaction và không chia sẻ sang thread khác. Ví dụ dưới đây có thể là lớp Java 17+ trong ứng dụng có `DataSource` và bảng `accounts(id, balance)`; dùng `BigDecimal` cho tiền:

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

    public void transfer(long from, long to, BigDecimal amount) throws SQLException {
        try (Connection con = dataSource.getConnection()) {
            con.setAutoCommit(false);

            try {
                debit(con, from, amount);
                credit(con, to, amount);
                con.commit();
            } catch (SQLException | RuntimeException error) {
                try {
                    con.rollback();
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            }
        }
    }

    private void debit(Connection con, long id, BigDecimal amount)
            throws SQLException {
        String sql = "UPDATE accounts SET balance = balance - ? WHERE id = ?";
        try (PreparedStatement ps = con.prepareStatement(sql)) {
            ps.setBigDecimal(1, amount);
            ps.setLong(2, id);
            if (ps.executeUpdate() != 1) {
                throw new SQLException("Source account not found");
            }
        }
    }

    private void credit(Connection con, long id, BigDecimal amount)
            throws SQLException {
        String sql = "UPDATE accounts SET balance = balance + ? WHERE id = ?";
        try (PreparedStatement ps = con.prepareStatement(sql)) {
            ps.setBigDecimal(1, amount);
            ps.setLong(2, id);
            if (ps.executeUpdate() != 1) {
                throw new SQLException("Destination account not found");
            }
        }
    }
}
```

`con` được truyền giữa các hàm **trong cùng lời gọi đồng bộ**, không được đưa vào field singleton và không gửi cho executor. Mã này chưa triển khai kiểm tra số dư, số tiền âm, quản lý deadlock hay chiến lược concurrency nghiệp vụ; đó là những kiểm soát cần thiết cho chức năng chuyển tiền thực tế.

Với pool, sau khi connection được trả, pool có thể khôi phục một số trạng thái JDBC cơ bản trước lần mượn kế tiếp. Ứng dụng vẫn phải tự commit/rollback đúng cách, tránh để transaction dang dở và tránh thay đổi trạng thái phiên mà pool không thể nhận biết.

## 5. Cách ưu tiên trong Spring: singleton Repository dùng JdbcTemplate

`JdbcTemplate` được Spring mô tả là **thread-safe sau khi cấu hình xong**. Một singleton repository nên giữ `JdbcTemplate`, không giữ `Connection`. Khi gọi `jdbc.update(...)`/`query(...)`, template lấy và giải phóng connection bằng cơ chế tích hợp với `DataSourceUtils` và transaction manager.

Ví dụ repository Spring 6.x / Java 17+:

```java
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public final class EventRepository {
    private final JdbcTemplate jdbc; // Singleton dùng chung an toàn sau cấu hình

    public EventRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int addEvent(long id, String message) {
        return jdbc.update(
            "INSERT INTO audit_event(id, message) VALUES (?, ?)",
            id, message
        );
    }

    public List<Event> findAll() {
        return jdbc.query(
            "SELECT id, message FROM audit_event ORDER BY id",
            (rs, rowNum) -> new Event(
                rs.getLong("id"),
                rs.getString("message")
            )
        );
    }

    public record Event(long id, String message) {}
}
```

Các điểm quan trọng:

- `jdbc` là field `final`; dữ liệu mỗi lời gọi (`id`, `message`) nằm trong tham số/local variable.
- `RowMapper` trích dữ liệu thành `record Event` khi `ResultSet` còn mở, và **trả DTO**, không trả `ResultSet` cho controller dùng sau.
- `JdbcTemplate` tự đóng `Statement`/`ResultSet` và giải phóng connection đúng phạm vi; khi có Spring-managed transaction, nó có thể dùng connection đang gắn với transaction.
- Cần bảo đảm `JdbcTemplate`/`DataSource` đã cấu hình trước khi phục vụ request; không gọi setter để thay đổi cấu hình template giữa các thread đang chạy.
- Một repository singleton **không đồng nghĩa** tất cả request dùng chung một connection vật lý đang active.

### 5.1. Có cần tự gọi DataSource.getConnection() trong Repository?

Nếu chỉ cần SQL CRUD thông thường, **không**: `JdbcTemplate` đã xử lý các bước tài nguyên và chuyển `SQLException` thành ngoại lệ Spring phù hợp.

Nếu cần truy cập JDBC API cấp thấp bên trong Spring transaction, sử dụng `DataSourceUtils.getConnection(dataSource)` và `DataSourceUtils.releaseConnection(con, dataSource)`. Cặp API này biết connection đã liên kết với transaction hiện hành hay chưa.

Tệp `LowLevelJdbcReader.java` là minh họa đặt trong ứng dụng Spring đã cấu hình `DataSource`:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

import org.springframework.jdbc.datasource.DataSourceUtils;

public final class LowLevelJdbcReader {
    private final DataSource dataSource;

    public LowLevelJdbcReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public long countEvents() {
        Connection con = DataSourceUtils.getConnection(dataSource);
        try {
            try (PreparedStatement ps = con.prepareStatement(
                    "SELECT COUNT(*) FROM audit_event");
                 ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException("COUNT did not return a row");
                }
                return rs.getLong(1);
            }
        } catch (SQLException ex) {
            throw new IllegalStateException("Counting events failed", ex);
        } finally {
            DataSourceUtils.releaseConnection(con, dataSource);
        }
    }
}
```

`DataSourceUtils.releaseConnection` không đóng connection đang do transaction manager giữ cho đến khi transaction kết thúc; bên ngoài transaction nó giải phóng connection theo chính sách DataSource. Tránh dùng `try (Connection con = dataSource.getConnection())` *bên trong* một transaction Spring rồi giả định connection đó tự nhiên sẽ tham gia transaction hiện hành; với DataSource thông thường, lời gọi thẳng vào DataSource có thể lấy một connection khác không gắn với transaction.

## 6. @Transactional: Spring giữ Connection theo giao dịch, không phải field của Bean

Với JDBC và `DataSourceTransactionManager`/`JdbcTransactionManager`, transaction imperative thường có tài nguyên **gắn với luồng hiện tại**. Cách hoạt động điển hình:

1. Một lời gọi đi qua Spring transaction proxy vào phương thức `@Transactional`.
2. Transaction manager chuẩn bị transaction JDBC và quản lý connection liên quan tới DataSource trong phạm vi giao dịch.
3. Các thao tác `JdbcTemplate` cùng DataSource trong **cùng luồng và cùng transaction** lấy connection phù hợp qua `DataSourceUtils`.
4. Khi phương thức transaction hoàn tất, Spring commit hoặc rollback theo cấu hình và giải phóng connection.

```text
HTTP request A / thread A                 HTTP request B / thread B
       |                                          |
 Service @Transactional                    Service @Transactional
       |                                          |
  JdbcTemplate A                               JdbcTemplate B
       |                                          |
  DataSourceUtils                              DataSourceUtils
       |                                          |
 Connection gắn với tx A                  Connection gắn với tx B
       |                                          |
       +-------------- cùng DataSource/pool ------+
```

Nếu A và B đang thực hiện **hai transaction độc lập đồng thời**, chúng không nên cùng sử dụng một JDBC Connection active. Pool cấp phát handle theo lượt mượn, trong giới hạn pool.

Ví dụ:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public final class EventService {
    private final EventRepository eventRepository;

    public EventService(EventRepository eventRepository) {
        this.eventRepository = eventRepository;
    }

    @Transactional
    public void storeTwoEvents(long firstId, long secondId) {
        eventRepository.addEvent(firstId, "first");
        eventRepository.addEvent(secondId, "second");
        // Hai lệnh tham gia cùng transaction khi cấu hình tx/JdbcTemplate đúng.
    }
}
```

Các Bean repository/service đều có thể là singleton: transaction của từng lời gọi được Spring quản lý, **không** lưu trong field bean. Nếu câu lệnh thứ hai ném unchecked exception và ngoại lệ thoát khỏi phương thức, cấu hình rollback mặc định của Spring thường rollback cả transaction; quy tắc rollback cho checked exception cần cấu hình nếu muốn hành vi tương tự.

**Lưu ý Spring proxy:** `@Transactional` không có tác dụng chỉ vì annotation xuất hiện. Cần bật transaction management và gọi qua Spring proxy theo chế độ mặc định. Một phương thức cùng bean gọi `this.storeTwoEvents(...)` (self-invocation) thường không đi qua proxy, nên không kích hoạt interception như mong muốn.

### 6.1. @Transactional không biến một Connection thành thread-safe

Một transaction có thể hợp lệ bao gồm nhiều thao tác SQL **tuần tự** trên cùng connection trong cùng luồng. Nó không cấp phép cho nhiều thread đồng thời thao tác trên connection đó. Các câu SQL còn có thể giữ lock, dùng session state và ảnh hưởng nhau.

Không viết:

```java
// SAI: đang cầm một connection của transaction ở thread A.
Connection con = DataSourceUtils.getConnection(dataSource);
executor.submit(() -> useConnection(con)); // Thread B dùng chung handle
```

Mã trên là đoạn **minh họa lỗi**, không phải phương thức đầy đủ và không có phần release. Truyền `con` sang thread B không tự truyền Spring transaction context. Nếu thread B cần thao tác DB, truyền **dữ liệu đầu vào** (id, DTO bất biến) và để B tự gọi repository/JdbcTemplate; khi B cần transaction riêng, thiết lập transaction qua Spring tại ranh giới thực thi của B.

## 7. Async, ExecutorService và @Async: ranh giới thread rất quan trọng

Với imperative `PlatformTransactionManager`, các transaction resource như JDBC Connection thường được gắn với thread thông qua `TransactionSynchronizationManager`. Khi bạn khởi tạo một thread mới trong phương thức `@Transactional` hoặc dùng `CompletableFuture.supplyAsync`/`ExecutorService`, transaction của thread gọi **không tự động truyền** sang worker thread.

| Tình huống | Điều nên làm |
| --- | --- |
| Request thread A gọi hai phương thức repository tuần tự trong một `@Transactional` | Để `JdbcTemplate` tham gia transaction của A, không tự lấy/giữ connection. |
| A dùng `ExecutorService` để xử lý nhiều id | Mỗi task gọi DAO qua `JdbcTemplate`, tự mượn connection phù hợp; không chuyển `Connection`/`ResultSet`. |
| A mong B tham gia cùng transaction JDBC mà A đang mở | Không giả định có thể chia transaction thread-bound bằng cách chuyển object; thiết kế lại ranh giới công việc/giao dịch. |
| Background task cần commit/rollback riêng | Đặt ranh giới transaction trong service được gọi qua Spring proxy trên thread chạy task (hoặc dùng `TransactionTemplate` tại thread đó). |
| A đã trả kết quả query, B xử lý bất đồng bộ | Truyền DTO đã materialize; không truyền `ResultSet`/stream còn phụ thuộc connection. |

Ví dụ triển khai tách tác vụ, **hai đoạn mã đặt trong ứng dụng Spring đã cấu hình `JdbcTemplate`**:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class AsyncCoordinator {
    private final EventRepository repository;

    public AsyncCoordinator(EventRepository repository) {
        this.repository = repository;
    }

    public void storeInBackground(long id, String message) {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            executor.submit(() -> repository.addEvent(id, message)).get();
        } catch (Exception e) {
            throw new IllegalStateException("Background insert failed", e);
        } finally {
            executor.shutdown();
        }
    }
}
```

Đoạn này tạo executor mới chỉ để minh họa **không chuyển Connection giữa thread**; ứng dụng production nên dùng executor do Spring quản lý hoặc pool task dùng chung, tránh tạo/đóng executor cho từng request. `get()` trong ví dụ chờ kết quả nên hành vi bên ngoài vẫn đồng bộ; nếu cần async thật sự, thiết kế API trả `CompletableFuture`/kết quả tác vụ và quản lý lỗi/lifecycle rõ ràng.

Nếu dùng `@Async`, cần cấu hình `@EnableAsync`, đưa tác vụ vào một Spring bean được gọi qua proxy (không self-invocation), và nhớ rằng transaction của caller không tự đi cùng thread chạy tác vụ. Nếu async task cần transaction, đặt `@Transactional` tại ranh giới thực thi phù hợp của task, với transaction manager đang hoạt động. **Không truyền `Connection`, `PreparedStatement`, `ResultSet` hay `EntityManager` sống vào task**. Phần này nói về JDBC đồng bộ; R2DBC/reactive dùng connection và transaction context theo cơ chế khác, không áp dụng ThreadLocal của JDBC một cách máy móc.

## 8. Ví dụ đầy đủ chạy được: singleton JdbcTemplate, hai thread độc lập

Thí nghiệm Spring Boot 3.3.x, Java 17+ và H2 dưới đây chứng minh **cùng một repository/JdbcTemplate bean có thể được nhiều thread gọi**, mà ứng dụng không giữ `Connection` trong field. Hai task thực hiện insert hai id khác nhau, rồi kiểm tra số hàng.

Tạo project Spring Boot Gradle (Groovy DSL) với Spring JDBC và H2. Trong `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

Tệp `src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:scoped_connection_demo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=2
spring.main.web-application-type=none
```

Tệp `src/main/java/example/connection/ConnectionSharingDemoApplication.java` (một file chứa app và bean cho demo):

```java
package example.connection;

import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@SpringBootApplication
public class ConnectionSharingDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConnectionSharingDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(JdbcTemplate jdbc, DemoRepository repository) {
        return args -> {
            jdbc.execute("""
                CREATE TABLE audit_event (
                    id INT PRIMARY KEY,
                    message VARCHAR(100) NOT NULL
                )
                """);

            ExecutorService executor = Executors.newFixedThreadPool(2);
            try {
                List<Callable<Integer>> tasks = List.of(
                    () -> repository.insert(1, "from-A"),
                    () -> repository.insert(2, "from-B")
                );

                List<Future<Integer>> futures = executor.invokeAll(tasks);
                for (Future<Integer> future : futures) {
                    if (future.get() != 1) {
                        throw new IllegalStateException("Insert was not applied");
                    }
                }

                Integer count = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM audit_event", Integer.class);
                System.out.println("rowCount=" + count);
            } finally {
                executor.shutdown();
            }
        };
    }
}

@Repository
class DemoRepository {
    private final JdbcTemplate jdbc;

    DemoRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    int insert(int id, String message) {
        return jdbc.update(
            "INSERT INTO audit_event(id, message) VALUES (?, ?)",
            id, message
        );
    }
}
```

Chạy từ thư mục project có Gradle wrapper:

```bash
./gradlew bootRun
```

Trên Windows PowerShell, dùng `.\gradlew.bat bootRun`. Điều kiện để chương trình chạy: Java 17+ hoạt động, Gradle và dependency tải được, H2 driver nằm trong runtime classpath. Trên môi trường đã chuẩn bị đúng, ứng dụng in dòng do mã demo tạo ra:

```text
rowCount=2
```

Spring Boot/Hikari có thể in thêm log khởi động và dừng. Thứ tự chạy hai task không cố định, nhưng hai id khác nhau và `Future.get()` bảo đảm cả hai insert thành công trước khi đếm. Ví dụ không khẳng định mỗi task nhất thiết đã sử dụng **một connection vật lý khác nhau**: nếu một tác vụ kết thúc trước, pool có thể cấp lại connection vật lý cũ; điểm cần kiểm chứng là hai tác vụ không **chia sẻ một active Connection handle trong field**.

Ứng dụng có `@Repository` singleton, trường `JdbcTemplate` bất biến, SQL độc lập theo lời gọi. Đây là mô hình điển hình cho HTTP controllers, jobs và message listeners khi chúng cùng truy cập repository trong nhiều luồng.

## 9. Vòng đời, connection pool và các hiểu nhầm

### 9.1. Có pool không có nghĩa “một Connection dùng được bởi tất cả thread”

Một pool Hikari được cấu hình `maximumPoolSize=10` có thể cấp tối đa 10 connection vật lý cùng lúc cho các lượt mượn trong pool đó, subject to DB limit và điều kiện runtime. Nếu 10 connection đang active, lượt mượn mới thường phải chờ; hết `connectionTimeout` sẽ thất bại. **Đừng lưu một connection đã mượn rồi phát cho mọi thread** để “tiết kiệm slot”: hành vi đó làm mất giới hạn sở hữu, gây race và giảm tính đúng đắn của transaction.

### 9.2. Có thể giữ Connection trong biến local qua nhiều phương thức không?

Có, nếu tất cả thao tác thuộc **một phạm vi đồng bộ được kiểm soát** và caller quản lý commit/rollback/close. Ví dụ `transfer(...)` trong mục 4 truyền `Connection` từ hàm chính vào `debit(...)` và `credit(...)`. Điều này khác hoàn toàn việc đưa Connection vào singleton field, cache hoặc task bất đồng bộ.

### 9.3. Thay singleton Connection bằng synchronized có ổn không?

`synchronized` đôi khi loại bỏ concurrent execution tại một đoạn mã Java, nhưng tất cả tác vụ vẫn chia một session và trạng thái transaction; nếu các hàm khác dùng connection ngoài khóa, lỗi còn tồn tại. Nếu khóa bao toàn bộ nghiệp vụ và quản lý transaction, bạn đã biến DB access thành nút thắt tuần tự, không đạt mục tiêu thiết kế service nhiều request. Cách đúng là mượn connection theo transaction/task, dùng pool và thiết kế isolation/locking theo nghiệp vụ.

### 9.4. Một transaction dài nên giữ Connection bao lâu?

Chỉ trong phần công việc DB cần transaction; tránh gọi HTTP API chậm, sleep, thao tác tệp lớn hoặc chờ background task trong khi đang giữ transaction và connection không cần thiết. Transaction dài làm tăng lock duration và chiếm slot pool, dẫn đến timeout cho request khác.

### 9.5. PreparedStatement đã được pool/cache thì sao?

Một số driver, DB hoặc pool có cơ chế **statement caching** bên dưới. Điều đó không cấp quyền cho ứng dụng đặt một `PreparedStatement` đang mở vào singleton field để nhiều request đồng thời sửa tham số. Hãy để driver/pool quản lý cache ở tầng thích hợp, còn ứng dụng tạo và đóng statement trong scope sử dụng.

## 10. Lỗi vận hành thường gặp và cách điều tra

| Dấu hiệu | Nghi vấn | Cách xử lý |
| --- | --- | --- |
| `SQLException: Connection is closed` khi có nhiều request | Một thread đóng handle mà thread khác còn dùng; singleton giữ connection quá lâu; DB cắt phiên | Kiểm tra nơi lưu/truyền `Connection`; chuyển sang `DataSource`/`JdbcTemplate` và scope cục bộ. |
| Request A rollback khiến dữ liệu request B biến mất | Cùng connection/transaction bị dùng chéo | Loại bỏ trường connection dùng chung; kiểm tra transaction boundary. |
| Lúc đúng lúc sai dù SQL giống nhau | Race trên `setAutoCommit`, schema, isolation, PreparedStatement params/cursor | Tách connection theo task và đảm bảo mỗi statement/result scoped cục bộ. |
| Hikari timeout “Connection is not available” | Pool cạn do connection bị giữ lâu/leak hoặc SQL/transaction chậm | Theo dõi active/idle/pending, thời gian giữ transaction, đường đóng resource. |
| Active connection không giảm | Không gọi `close()` hoặc trả resource sai cách; giữ connection trong field/ThreadLocal | Dùng try-with-resources, `JdbcTemplate` hoặc `DataSourceUtils.releaseConnection`. |
| `@Transactional` “không chạy” khi gọi nội bộ | Self-invocation bỏ qua Spring proxy ở chế độ proxy | Gọi qua bean được Spring quản lý, tách service hoặc dùng `TransactionTemplate`. |
| Async task thấy DB chưa có thay đổi của caller | Transaction của caller chưa commit; async thread dùng transaction riêng | Thiết kế thứ tự commit, sự kiện sau commit hoặc transaction riêng đúng ý định. |
| Race dữ liệu vẫn xảy ra sau khi bỏ singleton Connection | Transaction isolation/locking nghiệp vụ chưa đủ | Phân tích lost update, optimistic locking, câu SQL nguyên tử, isolation và deadlock. |

Không chỉ dựa vào stack trace; cần đối chiếu luồng thực thi, transaction boundary, thời gian mượn/trả connection, giới hạn pool và hành vi DB. Các metric Hikari như active/idle/pending hữu ích, nhưng tự chúng không kết luận được có data race trong logic ứng dụng hay không.

## 11. Tự kiểm tra

**Câu 1.** Một `@Repository` singleton có trường `private final JdbcTemplate jdbc`. Hai HTTP request đồng thời gọi `jdbc.update`. Có phải hai request luôn dùng cùng một `Connection` không?

**Đáp án:** Không. Cùng JdbcTemplate không đồng nghĩa cùng active Connection. Template lấy connection phù hợp từ DataSource/transaction context theo từng lượt thao tác.

**Câu 2.** Thay `private Connection con` thành `private final Connection con` có làm thread-safe không?

**Đáp án:** Không. `final` chỉ ngăn thay tham chiếu, không loại race trên trạng thái mutable của connection.

**Câu 3.** Một thread gọi `rollback()` khi hai thread dùng chung một connection đang ở `autoCommit=false`. Nó rollback riêng thay đổi của thread đó?

**Đáp án:** Không. Transaction là của connection; thay đổi từ cả hai thread trong transaction hiện tại có thể bị rollback.

**Câu 4.** Dùng `DataSourceUtils.getConnection` trong Spring thì có được `try (Connection con = ...)` và tự đóng như JDBC độc lập không?

**Đáp án:** Không nên. Phải dùng `DataSourceUtils.releaseConnection(con, dataSource)` để Spring quyết định khi nào cần giải phóng, tránh phá vỡ connection đang gắn với transaction.

**Câu 5.** `@Transactional` ở thread A có tự động phủ các lệnh trong `CompletableFuture.supplyAsync` chạy trên thread B không?

**Đáp án:** Không trong mô hình imperative transaction thread-bound thông thường. B cần tự xác lập transaction nếu nghiệp vụ yêu cầu; truyền dữ liệu, không truyền JDBC handles.

**Câu 6.** Dùng connection riêng đã loại hết lỗi cập nhật đồng thời chưa?

**Đáp án:** Chưa. Nó loại lỗi chia sẻ session/handle, nhưng các transaction riêng vẫn có thể tranh chấp dữ liệu; cần kiểm soát isolation/locking/consistency ở DB và nghiệp vụ.

## 12. Checklist code review

- [ ] Singleton/service/repository **không** có field kiểu `Connection`, `Statement`, `ResultSet` hay cache chứa chúng.
- [ ] Bean dùng chung có dependency `DataSource`/`JdbcTemplate` được cấu hình ổn định.
- [ ] Code JDBC thuần dùng local variables và try-with-resources, đóng statement/result set/connection đúng thứ tự.
- [ ] Code dùng Spring-managed transaction ưu tiên `JdbcTemplate`, hoặc cặp `DataSourceUtils.getConnection/releaseConnection`.
- [ ] Không đưa JDBC handle sang `ExecutorService`, `CompletableFuture`, `@Async`, callback hay response sau khi scope đã hết.
- [ ] Ranh giới `@Transactional` được gọi qua Spring proxy khi sử dụng chế độ mặc định; không trông đợi self-invocation hay chuyển thread tự động giữ transaction.
- [ ] Pool có giới hạn và metrics phù hợp; không để transaction dài hoặc giữ connection khi chờ công việc không liên quan DB.
- [ ] Truy vấn đồng thời vẫn được kiểm tra isolation, khóa, constraint và tính nguyên tử ở mức nghiệp vụ.

## Tài liệu tham khảo

- [Spring Framework — Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): `DataSource`, `DataSourceUtils`, kết nối gắn transaction.
- [Spring Framework — JdbcTemplate Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html): xác nhận `JdbcTemplate` thread-safe sau khi cấu hình.
- [Spring Framework — Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): transaction imperative thread-bound và giới hạn khi tạo thread mới.
- [Oracle JDBC Coding Tips — JDBC and Multithreading](https://docs.oracle.com/en/database/oracle/oracle-database/26/jjdbc/JDBC-coding-tips.html): khuyến nghị dùng connection như biến local và không chia sẻ giữa thread.
- [JDK Java SE — java.sql.Connection](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Connection.html): API transaction, `autoCommit`, `commit`, `rollback`, `close`.

**Kết luận:** Một singleton nên giữ **nguồn cấp connection** hoặc **công cụ truy cập dữ liệu**, không giữ **connection đang được mượn**. Connection thuộc về một phạm vi công việc/giao dịch được kiểm soát, được sử dụng tuần tự và được trả đúng lúc; Spring và pool giúp điều phối vòng đời này nhưng không làm một shared JDBC Connection trở thành an toàn cho nhiều luồng.
