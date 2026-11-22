# Phạm vi an toàn khi chia sẻ Connection giữa nhiều luồng trong JDBC

Trong chương **Quản lý kết nối**, câu hỏi quan trọng khi xây dựng ứng dụng chạy song song là: **có thể dùng chung một đối tượng `java.sql.Connection` giữa nhiều luồng Java không?** Câu trả lời thực hành là **không nên sử dụng đồng thời một `Connection` cho nhiều công việc độc lập**. Tùy driver và cách sử dụng, một số thao tác có thể được hỗ trợ, nhưng JDBC không đưa ra một cam kết chung rằng việc dùng đồng thời cùng một kết nối là an toàn cho mọi driver, mọi thao tác và mọi giao dịch.

**JDBC (Java Database Connectivity)** là API Java để truy cập cơ sở dữ liệu quan hệ. `Connection` đại diện cho một phiên làm việc với cơ sở dữ liệu, mang theo nhiều trạng thái có thể thay đổi. Vì vậy, cần xác định rõ **ai sở hữu kết nối, ai có quyền kết thúc giao dịch và khi nào kết nối được trả về pool**. Bài học giải thích ranh giới an toàn, những lỗi cạnh tranh thường gặp và cách tổ chức mã đúng trong ứng dụng nhiều luồng.

## 1. Vì sao Connection là tài nguyên có trạng thái?

Một `Connection` không đơn thuần là một “đường dây truyền SQL”. Nó có thể quản lý hoặc phản ánh các trạng thái như:

- **Auto-commit:** `setAutoCommit(false)` quyết định các câu SQL có tham gia cùng một giao dịch hay không.
- **Transaction:** `commit()`, `rollback()` và `setSavepoint()` ảnh hưởng đến công việc chưa được xác nhận trên kết nối.
- **Mức cô lập:** `setTransactionIsolation(...)` có thể thay đổi cách giao dịch quan sát dữ liệu đồng thời.
- **Chế độ chỉ đọc, schema/catalog:** `setReadOnly(...)`, `setSchema(...)`, `setCatalog(...)` có thể thay đổi ngữ cảnh cho các lệnh tiếp theo tùy DBMS/driver.
- **Trạng thái phiên trên máy chủ:** bảng tạm, biến phiên, thiết lập SQL, khóa, cursor và tài nguyên gắn với phiên, tùy hệ quản trị.
- **Statement/ResultSet:** các câu lệnh và tập kết quả đang mở có vòng đời liên hệ với kết nối.

Ví dụ, luồng A gọi `connection.setAutoCommit(false)`, sau đó luồng B chạy `UPDATE` trên **chính** `connection` đó. Nếu luồng A gọi `rollback()`, thao tác của B có thể bị hoàn tác cùng giao dịch của A. Lệnh `rollback()` không phân biệt câu SQL do luồng Java nào gửi đi.

**Ranh giới giao dịch là ranh giới của phiên kết nối**, không tự động là ranh giới của từng luồng Java. Mức `TRANSACTION_SERIALIZABLE` cũng không biến hai luồng cùng dùng một `Connection` thành hai giao dịch độc lập.

## 2. Phân biệt đối tượng có thể chia sẻ và đối tượng cần có chủ sở hữu

| Đối tượng | Quy tắc dùng trong ứng dụng nhiều luồng | Lý do |
|---|---|---|
| `DataSource` sử dụng pool hỗ trợ đồng thời | Có thể dùng làm điểm cấp kết nối chung cho nhiều luồng | Pool quản lý việc mượn/trả kết nối và phân phối tài nguyên |
| `Connection` đang được sử dụng | Nên có **một chủ sở hữu tại một thời điểm**, theo phạm vi công việc/giao dịch | Có trạng thái giao dịch và phiên dùng chung |
| `PreparedStatement` / `Statement` | Giữ trong phạm vi công việc sở hữu `Connection`; không gửi sang luồng khác tùy tiện | Gắn với kết nối và trạng thái thực thi câu SQL |
| `ResultSet` | Đọc và đóng trong phạm vi đang sở hữu statement/kết nối | Cursor và dữ liệu có thể bị vô hiệu hóa khi statement/kết nối thay đổi |
| Transaction manager của framework | Dùng theo hợp đồng framework, thường gắn ngữ cảnh transaction với luồng | Transaction có quy tắc truyền ngữ cảnh riêng |

**Điểm phân biệt cốt lõi:** chia sẻ một **`DataSource` có pool được thiết kế thread-safe** khác với chia sẻ trực tiếp một **`Connection` đã mượn từ pool**. Nhiều luồng có thể đồng thời gọi `dataSource.getConnection()`; mỗi lần mượn thành công, pool phải bảo đảm không giao cùng một kết nối vật lý cho hai chủ sở hữu hoạt động đồng thời. Khi chủ sở hữu gọi `close()` trên proxy kết nối, pool thường nhận lại tài nguyên để cho lượt mượn kế tiếp.

`DataSource` là một interface; khả năng dùng đồng thời và quy tắc vòng đời cụ thể phụ thuộc triển khai. Với ứng dụng sản xuất, hãy dùng pool được tài liệu nhà cung cấp xác nhận hỗ trợ truy cập đa luồng, thay vì mặc định rằng mọi triển khai `DataSource` có cùng đặc tính.

## 3. Các lỗi cạnh tranh khi hai luồng dùng chung Connection

Giả sử một ứng dụng giữ `Connection shared` trong đối tượng singleton, rồi hai request A và B chạy trên hai luồng khác nhau:

```text
Thời điểm       Luồng A                         Luồng B
-------------------------------------------------------------------
t1              shared.setAutoCommit(false)
t2                                              UPDATE đơn hàng B
t3              UPDATE đơn hàng A
t4              shared.rollback()
t5                                              B tưởng UPDATE thành công
-------------------------------------------------------------------
Thực tế: B có thể đã tham gia giao dịch của A và bị rollback.
```

Đây là lỗi *giao thoa transaction*: ý định của hai request khác nhau, nhưng `Connection` không tách chúng thành hai transaction riêng.

Các tình huống nguy hiểm khác:

1. **Commit nhầm công việc:** A đang ghi dở, B gọi `commit()` trên cùng kết nối khiến một phần thay đổi của A được xác nhận sớm.
2. **Đổi trạng thái phiên:** A gọi `setSchema(...)` hoặc `setTransactionIsolation(...)`, B thực thi câu SQL trong ngữ cảnh khác dự kiến.
3. **Đóng kết nối khi luồng khác đang dùng:** B gọi `close()` trong lúc A đang thực thi hoặc đọc `ResultSet`; A có thể nhận `SQLException` và mất tài nguyên.
4. **Dùng chung statement/cursor:** hai luồng gọi `executeQuery()`, thay đổi tham số hoặc đóng cùng `PreparedStatement`/`ResultSet`, dẫn đến dữ liệu không nhất quán hoặc lỗi tài nguyên.
5. **Giữ kết nối quá lâu:** một luồng chờ tác vụ bên ngoài trong khi vẫn giữ kết nối, gây thiếu kết nối cho phần còn lại của ứng dụng.
6. **Hủy/timeout ngoài dự kiến:** một luồng tìm cách hủy một tác vụ đang chạy mà không có quy trình điều phối phù hợp, làm luồng khác nhận lỗi và khó xác định trạng thái transaction.

Đặc biệt, các lỗi này **không được loại bỏ chỉ bằng cách chuyển sang isolation level cao hơn**, vì isolation chủ yếu điều phối **các giao dịch khác nhau** ở phía cơ sở dữ liệu. Hai luồng chung một connection thường can thiệp vào **cùng trạng thái transaction**.

## 4. Anti-pattern: lưu Connection trong singleton hoặc trường static

Mã sau minh họa điều **không nên làm**:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public final class UnsafeOrderRepository {
    // Cùng một Connection bị mọi request/luồng dùng chung.
    private final Connection sharedConnection;

    public UnsafeOrderRepository(Connection sharedConnection) {
        this.sharedConnection = sharedConnection;
    }

    public void updateStatus(long orderId, String status) throws SQLException {
        sharedConnection.setAutoCommit(false);
        try (PreparedStatement statement = sharedConnection.prepareStatement(
                "UPDATE orders SET status = ? WHERE order_id = ?")) {
            statement.setString(1, status);
            statement.setLong(2, orderId);
            statement.executeUpdate();
            sharedConnection.commit();
        } catch (SQLException error) {
            sharedConnection.rollback();
            throw error;
        }
    }
}
```

Ngay cả khi mỗi lời gọi tạo một `PreparedStatement` mới, `sharedConnection` vẫn mang trạng thái transaction dùng chung. Nếu hai luồng đi vào `updateStatus` cùng lúc, một lời gọi có thể commit hoặc rollback thay đổi của lời gọi kia. Kết nối cũng không được trả về pool theo vòng đời request.

Chuyển trường thành `static Connection` còn mở rộng phạm vi lỗi ra toàn ứng dụng; đặt `Connection` trong HTTP session hay cache dùng chung cũng có vấn đề tương tự.

### Vì sao `synchronized` từng phương thức JDBC không đủ?

Giả sử chỉ khóa từng câu lệnh riêng lẻ:

```java
synchronized (connection) {
    connection.setAutoCommit(false);
}
// Luồng khác có thể chen vào đây.
synchronized (connection) {
    doBusinessUpdate(connection);
}
// Luồng khác lại có thể chen vào trước commit.
synchronized (connection) {
    connection.commit();
}
```

Mọi thao tác riêng đều có khóa nhưng **toàn bộ transaction không còn nguyên tử theo góc nhìn các luồng**. Để điều phối trên một kết nối duy nhất, phải khóa trọn phạm vi công việc: mở transaction, toàn bộ statement và cursor, commit/rollback, khôi phục trạng thái và dọn tài nguyên. Làm vậy khiến các công việc phải chạy lần lượt và vẫn phụ thuộc vào đặc tính driver, cách xử lý lỗi và nguồn gốc của kết nối.

Trong phần lớn ứng dụng, **dùng kết nối riêng được pool cấp cho mỗi công việc** rõ ràng và hiệu quả hơn. Không dùng `synchronized` như một bản vá mặc định cho kết nối chia sẻ.

## 5. Mẫu an toàn: chia sẻ DataSource, mượn Connection theo công việc

Một repository có thể được dùng chung bởi nhiều luồng nếu nó **không giữ `Connection` hoặc `PreparedStatement` đang hoạt động trong trường đối tượng**, mà chỉ giữ `DataSource` được phép gọi đồng thời:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class OrderRepository {
    private final DataSource dataSource;

    public OrderRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public long countOrdersByCustomer(long customerId) throws SQLException {
        String sql = "SELECT COUNT(*) FROM orders WHERE customer_id = ?";

        // Mỗi lời gọi mượn một connection trong phạm vi riêng.
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {

            statement.setLong(1, customerId);
            try (ResultSet resultSet = statement.executeQuery()) {
                resultSet.next();
                return resultSet.getLong(1);
            }
        } // Đóng ResultSet -> Statement -> Connection.
    }
}
```

Điều kiện của ví dụ: đã có bảng `orders` với cột `customer_id`, `DataSource` được cấu hình và triển khai hỗ trợ sử dụng đồng thời. Repository này chỉ đọc dữ liệu nên không cần mở giao dịch thủ công. `try-with-resources` bảo đảm hoàn trả kết nối ngay cả khi câu SQL phát sinh lỗi.

Với connection pool, gọi `connection.close()` thường **trả kết nối logic về pool** thay vì đóng ngay socket vật lý. Chi tiết này phụ thuộc pool và không cho phép giữ tham chiếu `Connection` để dùng lại sau `close()`.

### Ví dụ gọi repository từ nhiều luồng

```java
import java.sql.SQLException;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class ConcurrentOrderQueries {

    public static void run(OrderRepository repository) {
        ExecutorService executor = Executors.newFixedThreadPool(4);
        try {
            List<Long> customerIds = List.of(10L, 20L, 30L, 40L);

            List<CompletableFuture<Long>> tasks = customerIds.stream()
                    .map(id -> CompletableFuture.supplyAsync(() -> {
                        try {
                            return repository.countOrdersByCustomer(id);
                        } catch (SQLException error) {
                            throw new CompletionException(error);
                        }
                    }, executor))
                    .toList();

            for (int i = 0; i < tasks.size(); i++) {
                System.out.printf("Khách hàng %d có %d đơn hàng%n",
                        customerIds.get(i), tasks.get(i).join());
            }
        } finally {
            executor.shutdown();
        }
    }
}
```

Ví dụ dùng Java 16+ cho `Stream.toList()`; trên Java cũ có thể dùng `collect(Collectors.toList())`. Điểm an toàn nằm ở chỗ **mỗi task gọi phương thức tự lấy rồi đóng kết nối của riêng mình**. Không tạo `Connection` một lần bên ngoài rồi truyền tham chiếu đó vào bốn task.

Pool phải được cấu hình có sức chứa phù hợp nhu cầu thực tế, không nhất thiết bằng số luồng. Nếu mọi kết nối đã được mượn, `getConnection()` có thể phải chờ rồi timeout theo cấu hình; đó là cơ chế giới hạn tài nguyên, không phải lý do để nhiều luồng dùng chung một connection đang hoạt động.

## 6. Phạm vi giao dịch: một chủ sở hữu cho toàn bộ chuỗi thao tác

Một giao dịch nhiều câu SQL phải dùng **cùng connection**, nhưng điều này **không có nghĩa chia sẻ connection giữa các luồng**. Thay vào đó, một công việc/luồng mượn connection và thực hiện tuần tự toàn bộ các bước cần commit/rollback cùng nhau.

Ví dụ xử lý chuyển tiền đơn giản giữa hai tài khoản trong cùng cơ sở dữ liệu:

```java
import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public final class TransferService {
    private final DataSource dataSource;

    public TransferService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void transfer(long fromId, long toId, BigDecimal amount)
            throws SQLException {
        if (amount == null || amount.signum() <= 0 || fromId == toId) {
            throw new IllegalArgumentException("Chuyển tiền không hợp lệ");
        }

        try (Connection connection = dataSource.getConnection()) {
            boolean originalAutoCommit = connection.getAutoCommit();
            boolean finished = false;

            // Bắt đầu transaction thuộc quyền sở hữu của riêng lời gọi này.
            connection.setAutoCommit(false);
            try {
                try {
                    int debit;
                    try (PreparedStatement stmt = connection.prepareStatement(
                            "UPDATE accounts "
                          + "SET balance = balance - ? "
                          + "WHERE id = ? AND balance >= ?")) {
                        stmt.setBigDecimal(1, amount);
                        stmt.setLong(2, fromId);
                        stmt.setBigDecimal(3, amount);
                        debit = stmt.executeUpdate();
                    }
                    if (debit != 1) {
                        throw new SQLException("Tài khoản nguồn không đủ tiền/không tồn tại");
                    }

                    int credit;
                    try (PreparedStatement stmt = connection.prepareStatement(
                            "UPDATE accounts SET balance = balance + ? WHERE id = ?")) {
                        stmt.setBigDecimal(1, amount);
                        stmt.setLong(2, toId);
                        credit = stmt.executeUpdate();
                    }
                    if (credit != 1) {
                        throw new SQLException("Không tìm thấy tài khoản đích");
                    }

                    connection.commit();
                    finished = true;
                } catch (SQLException | RuntimeException error) {
                    try {
                        connection.rollback();
                        finished = true;
                    } catch (SQLException rollbackError) {
                        error.addSuppressed(rollbackError);
                    }
                    throw error;
                }
            } finally {
                // Tránh bật auto-commit khi transaction chưa kết thúc:
                // chuyển false -> true có thể khiến công việc còn lại được commit.
                if (finished) {
                    connection.setAutoCommit(originalAutoCommit);
                }
            }
        }
    }
}
```

Ví dụ giả định bảng `accounts(id, balance)` với `balance` là `DECIMAL`, khóa chính trên `id` và ràng buộc số dư phù hợp. Với nghiệp vụ tiền thật cần kiểm tra thêm idempotency, chính sách số dư, ghi sổ, retry deadlock/timeout và trường hợp không biết chắc kết quả `commit()` vì mất kết nối.

Các điểm quan trọng:

1. `TransferService` có thể được tạo một lần và gọi bởi nhiều request **nếu `DataSource` hỗ trợ mượn kết nối đồng thời**; nó không lưu connection làm trường.
2. Một lời gọi `transfer(...)` mượn **một connection** cho cả bước trừ và cộng, giúp hai bước nằm cùng transaction.
3. Phải kiểm tra số dòng được cập nhật; `executeUpdate()` có thể trả về `0` mà không ném lỗi.
4. Khi có lỗi, `rollback()` cố hoàn tác toàn bộ phần việc chưa commit trên connection **thuộc lời gọi này**.
5. Chỉ hoàn trả cấu hình auto-commit khi đã kết thúc giao dịch; nếu rollback thất bại, connection cần được xem là không an toàn để tiếp tục sử dụng.

Một sai lầm đối nghịch cũng cần tránh: mỗi helper trong cùng nghiệp vụ tự gọi `dataSource.getConnection()` rồi chạy `UPDATE` trên các connection khác nhau. Hai helper đó sẽ không tự động nằm trong cùng transaction JDBC thủ công; phải truyền **connection thuộc quyền sở hữu của một luồng giao dịch** vào các helper đồng bộ hoặc để transaction manager của framework điều phối.

## 7. Connection pool: chia sẻ khả năng truy cập, không chia sẻ quyền sở hữu

Có thể hình dung pool như nơi cấp các phiên kết nối theo lượt:

```text
               DataSource / Connection Pool
                         |
         +---------------+---------------+
         |               |               |
         v               v               v
    Connection A    Connection B    Connection C
         |               |               |
         v               v               v
     Task/luồng 1    Task/luồng 2    Task/luồng 3
         |               |               |
       close()         close()         close()
         \               |               /
          +---- Trả kết nối về pool ----+
                 (có thể tái sử dụng tuần tự)
```

Trong sơ đồ, các tên “Connection A/B/C” đại diện cho những lượt mượn riêng biệt. Pool có thể tái sử dụng cùng một kết nối vật lý **sau** khi lượt mượn trước đã kết thúc; điều đó khác với việc hai luồng cùng sở hữu tài nguyên vật lý vào một thời điểm.

Mỗi lần mượn cần tuân thủ những nguyên tắc:

- Lấy connection càng gần vị trí thực hiện SQL càng tốt, trả lại ngay khi hoàn tất.
- Dùng `try-with-resources` để đóng cả `ResultSet`, `Statement` và `Connection`, kể cả lúc có lỗi.
- Không giữ `Connection`, `PreparedStatement` hoặc `ResultSet` trong cache, singleton, đối tượng lâu sống, callback bất đồng bộ hay response gửi ra bên ngoài.
- Kết thúc transaction bằng `commit()` hoặc `rollback()`; không dựa vào `close()` như một cách rollback mặc định.
- Khi tự đổi isolation, read-only, schema hoặc auto-commit, xem xét phục hồi trạng thái an toàn trước khi trả về pool. Các pool phổ biến thường có cơ chế reset, nhưng ứng dụng vẫn phải làm theo hợp đồng của pool.
- Khi sử dụng transaction manager, không tự gọi `commit()` hoặc `close()` trên connection do framework đang quản lý trừ khi tài liệu framework yêu cầu.

**Connection leak** xảy ra khi mượn kết nối nhưng không trả đúng lúc. Dưới tải song song, rò rỉ khiến pool cạn và request mới phải đợi/timeout. Cấu hình giám sát số kết nối đang hoạt động, số kết nối chờ và thời gian giữ connection thường hữu ích hơn tăng kích thước pool vô hạn.

## 8. Các tình huống bất đồng bộ và truyền ngữ cảnh transaction

### 8.1. Không đưa Connection vào một tác vụ khác chạy song song

Tránh cách viết này:

```java
try (Connection connection = dataSource.getConnection()) {
    CompletableFuture<Void> task = CompletableFuture.runAsync(() -> {
        // Sai thiết kế: một task khác sử dụng connection mượn ở luồng hiện tại.
        // Có thể chạy đồng thời hoặc chạy sau khi try-with-resources đã close.
        useConnection(connection);
    });
    // Đường xử lý bên ngoài có thể còn tiếp tục dùng connection.
}
```

Ngay cả khi hiện tại tác vụ thường hoàn thành trước khi `close()` xảy ra, lịch chạy luồng có thể thay đổi. Vấn đề còn nghiêm trọng hơn nếu hai tác vụ cùng gọi `commit()`/`rollback()` hoặc cùng đọc một `ResultSet`.

Thay thế bằng việc chuyển **dữ liệu đầu vào** (ID, tham số truy vấn, DTO bất biến) sang task, rồi để task tự lấy connection:

```java
CompletableFuture<Long> task = CompletableFuture.supplyAsync(() -> {
    try {
        return repository.countOrdersByCustomer(customerId);
    } catch (SQLException error) {
        throw new CompletionException(error);
    }
}, executor);
```

Nếu các tác vụ cần tạo thành **một transaction nguyên tử**, việc cho mỗi task mượn connection riêng không làm chúng thành một transaction chung. Cách đơn giản là thực thi các câu SQL liên quan **tuần tự trên cùng connection trong một đơn vị công việc**, hoặc chọn cơ chế giao dịch phân tán nếu kiến trúc thực sự cần nhiều tài nguyên giao dịch.

### 8.2. Spring `@Transactional` và `@Async`

Nhiều framework quản lý transaction gắn trạng thái giao dịch với luồng hiện tại. Trong Spring, `@Transactional` kiểu thông thường sử dụng tài nguyên liên kết với luồng khi chạy theo mô hình transaction đồng bộ; khởi chạy `@Async`, `CompletableFuture` hoặc tạo luồng mới **không tự động chuyển transaction sang luồng mới**.

Vì vậy:

- Không giả định tác vụ `@Async` tham gia cùng transaction của phương thức gọi.
- Không truyền thủ công connection đang do transaction manager quản lý sang tác vụ async.
- Nếu cần transaction riêng cho tác vụ async, để framework tạo ranh giới giao dịch trong chính tác vụ, theo cấu hình thích hợp.
- Nếu một nghiệp vụ bắt buộc atomicity, thiết kế lại ranh giới công việc thay vì cố chia một `Connection` cho nhiều luồng.

Các mô hình reactive hoặc transaction manager không gắn trực tiếp với luồng có cơ chế context khác; cần tuân theo tài liệu của chính framework. Không áp dụng máy móc quy tắc `ThreadLocal` cho mọi kiến trúc.

### 8.3. ThreadLocal không tự biến Connection thành an toàn

`ThreadLocal<Connection>` có thể khiến mỗi luồng thấy một tham chiếu riêng, nhưng **không tự tạo ra quản lý transaction, quyền sở hữu hay dọn tài nguyên đúng cách**. Trong executor hoặc web server, luồng thường được tái sử dụng cho nhiều request; nếu không `remove()` và `close()` ở `finally`, connection có thể bị rò rỉ hoặc trạng thái của request trước tràn sang request sau.

Ưu tiên pool và transaction manager đã được kiểm chứng thay vì tự viết cơ chế giữ connection theo luồng.

## 9. Có trường hợp nào dùng một Connection từ nhiều luồng được không?

Cần phân biệt **truy cập đồng thời** và **bàn giao tuần tự**:

| Tình huống | Đánh giá |
|---|---|
| Hai luồng đồng thời thực thi SQL/commit/rollback trên cùng connection | Không nên; rất dễ giao thoa transaction và trạng thái phiên |
| Luồng A hoàn tất, bảo đảm không còn statement/result set đang dùng; sau đó bàn giao connection cho luồng B | Có thể điều phối tuần tự theo hợp đồng driver, nhưng phức tạp và thường không cần thiết khi có pool |
| Một luồng giữ connection và một luồng khác cố đóng connection để “hủy” nó | Không xem đây là cơ chế hủy chuẩn; có thể gây lỗi và trạng thái không xác định |
| Một luồng hủy statement đang thực thi ở luồng khác bằng `Statement.cancel()` | JDBC cung cấp API cho tình huống này **nếu driver và DBMS hỗ trợ**; chỉ áp dụng cho thao tác hủy có chủ đích, không có nghĩa mọi thao tác trên connection đều thread-safe |
| Các luồng cùng gọi `dataSource.getConnection()` trên pool hỗ trợ đa luồng | Cách tổ chức thông dụng và phù hợp |

`Statement.cancel()` có mục đích riêng: một luồng có thể yêu cầu hủy câu lệnh đang chạy ở luồng khác nếu được driver/DBMS hỗ trợ. Kết quả và thời điểm hủy có thể khác nhau, phải xử lý `SQLException` và xác định lại trạng thái transaction trước khi dùng tiếp. Có thể dùng timeout ở `Statement.setQueryTimeout(...)` và giới hạn thời gian ở tầng dịch vụ để giảm nhu cầu can thiệp xuyên luồng.

Một số driver có tài liệu nói rõ những thao tác nào được đồng bộ nội bộ, hoặc có thể hỗ trợ nhiều statement chạy trên cùng connection theo một số điều kiện. **Đó là bảo đảm riêng của driver và cấu hình cụ thể**, không biến việc chia sẻ tùy tiện thành quy tắc JDBC chung. Khi phải sử dụng, cần xem tài liệu phiên bản driver, định nghĩa rõ chủ sở hữu transaction, bảo vệ toàn bộ trạng thái liên quan và có integration test cạnh tranh thực tế.

## 10. Cách kiểm thử thiết kế nhiều luồng

Kiểm thử chỉ chứng minh hành vi trong những điều kiện đã chạy; không thể suy từ một lần chạy thành công rằng mọi lần chạy song song đều an toàn. Với ứng dụng JDBC có nhiều luồng, nên thực hiện:

1. **Thử nhiều request đồng thời** thực hiện đọc/ghi bằng repository; xác minh mỗi request giữ transaction riêng và kết quả không bị giao thoa.
2. **Chèn lỗi có chủ đích** vào bước giữa transaction; bảo đảm rollback chỉ tác động công việc của request đó, không hủy dữ liệu của request khác.
3. **Thử pool nhỏ hơn số luồng**; xác minh luồng chờ kết nối hoạt động theo timeout, không chia một kết nối đang được mượn cho hai request.
4. **Giám sát rò rỉ:** mọi nhánh, kể cả exception và hủy tác vụ, đều phải đóng statement/result set và trả connection.
5. **Thử trạng thái phiên:** sau các giao dịch có đổi isolation/auto-commit/read-only/schema, xác nhận lượt mượn kế tiếp nhận cấu hình mong đợi.
6. **Thử lỗi DBMS:** mất kết nối, deadlock, timeout và commit thất bại; không tiếp tục sử dụng connection không còn trạng thái đáng tin cậy.

Một bài test đáng giá là chạy **hai giao dịch độc lập**, trong đó transaction A chủ động rollback còn B commit. Khi dùng pool đúng cách và logic SQL phù hợp, rollback của A không được hoàn tác thay đổi của B chỉ vì hai request chạy song song.

## 11. Checklist thiết kế Connection an toàn

| Câu hỏi | Hướng lựa chọn |
|---|---|
| Repository/service có `static Connection` hoặc field `Connection` dùng chung không? | Loại bỏ; giữ `DataSource` được phép dùng đồng thời |
| Một transaction cần nhiều câu SQL? | Dùng một connection thuộc một chủ sở hữu xuyên suốt chuỗi thao tác |
| Nhiều tác vụ đọc/ghi song song? | Mỗi tác vụ mượn connection riêng từ pool |
| Có chia sẻ `Statement` hoặc `ResultSet` qua luồng khác? | Đưa việc đọc/ghi về cùng phạm vi sở hữu; chuyển DTO sau khi đọc xong |
| Có `CompletableFuture` hoặc `@Async`? | Xác định transaction độc lập của task; không truyền connection đang mở |
| Có dùng `synchronized` để “vá” connection dùng chung? | Xem lại ranh giới transaction và ownership; ưu tiên pool |
| Exception có dẫn đến connection không được trả lại? | Dùng `try-with-resources`, kết thúc transaction rõ ràng và giám sát pool |
| Driver tuyên bố hỗ trợ thao tác đa luồng đặc thù? | Đọc điều kiện hỗ trợ chính thức và kiểm thử đúng phiên bản/DBMS |

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Một service singleton chứa trường `private final DataSource dataSource`. Các luồng cùng gọi phương thức, mỗi lần đều lấy connection bằng `getConnection()` rồi đóng trong `try-with-resources`. Thiết kế có phù hợp không?

**Đáp án:** Có, nếu triển khai `DataSource`/pool hỗ trợ dùng đồng thời và mỗi lần mượn được quản lý đúng vòng đời. Mục đích chia sẻ là đầu mối cấp kết nối, không phải chính kết nối đang hoạt động.

**Câu 2.** Luồng A gọi `setAutoCommit(false)` trên connection chung. Luồng B thực hiện `UPDATE` trên connection đó. Sau đó A gọi `rollback()`. B có độc lập với A không?

**Đáp án:** Không. `rollback()` áp dụng cho transaction của connection, vì vậy thay đổi của B có thể cũng bị hủy.

**Câu 3.** Nếu dùng `synchronized (connection)` quanh từng lời gọi `executeUpdate()`, `commit()` và `rollback()`, đã an toàn chưa?

**Đáp án:** Chưa. Các lời gọi của transaction khác vẫn có thể chen giữa chúng. Bảo vệ từng thao tác không bảo đảm ranh giới nguyên tử của **toàn transaction**.

**Câu 4.** Muốn chạy bốn câu `SELECT` độc lập song song, cách tổ chức nào phù hợp?

**Đáp án:** Dùng executor với bốn task; mỗi task mượn và đóng connection của riêng mình qua `DataSource`. Không truyền một connection đang mở cho cả bốn task.

**Câu 5.** Có thể dùng bốn connection trong bốn luồng và gọi `commit()` trên mỗi cái để có một transaction JDBC nguyên tử chung không?

**Đáp án:** Không. Mỗi connection có ranh giới giao dịch riêng. Muốn một transaction thủ công JDBC, thực hiện công việc trên một connection; bài toán nhiều tài nguyên phải dùng cơ chế điều phối giao dịch phù hợp.

**Câu 6.** Việc `Statement.cancel()` có thể được gọi từ luồng khác chứng minh `Connection` hoàn toàn thread-safe không?

**Đáp án:** Không. Đây là một khả năng hủy lệnh có mục đích rõ ràng và phụ thuộc driver/DBMS, không phải cam kết sử dụng đồng thời mọi API JDBC.

**Câu 7.** Vì sao không nên giữ connection trong `ThreadLocal` của thread pool nếu không có quy trình dọn dẹp?

**Đáp án:** Luồng được tái sử dụng cho request khác; connection có thể bị rò rỉ, giữ transaction/thiết lập phiên cũ hoặc bị sử dụng ngoài phạm vi mong đợi.

Trong JDBC, lựa chọn an toàn nhất cho phần lớn ứng dụng đa luồng là **chia sẻ `DataSource` được thiết kế dùng đồng thời, nhưng cấp `Connection` theo từng đơn vị công việc hoặc transaction có chủ sở hữu rõ ràng**. Kết thúc transaction và đóng tài nguyên trước khi bàn giao khả năng truy cập cho công việc tiếp theo giúp tránh giao thoa trạng thái, rollback nhầm và cạn connection pool.
