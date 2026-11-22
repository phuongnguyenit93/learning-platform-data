# Quản lý vòng đời DataSource và nhóm kết nối JDBC

Trong ứng dụng Java, DataSource là điểm vào chuẩn để lấy kết nối JDBC. Ở môi trường thực tế, DataSource thường được cung cấp bởi một connection pool như HikariCP, Apache Commons DBCP hoặc một pool do application server quản lý. Pool giữ các kết nối vật lý tới database, quản lý thời gian chờ, tái sử dụng connection và chạy các tác vụ nền để kiểm tra hoặc loại bỏ kết nối.

Khi dùng CRaC (Coordinated Restore at Checkpoint), vòng đời của DataSource và connection pool cần được phối hợp với checkpoint/restore. Một Connection đang mở thường gắn với socket, trạng thái transaction, driver và tài nguyên native của tiến trình. Những kết nối này có thể không còn hợp lệ sau khi tiến trình được restore. Cách tổ chức phổ biến là ngừng nhận công việc mới, hoàn tất transaction, trả connection về pool, đóng pool trước checkpoint rồi tạo pool mới sau restore.

## 1. DataSource, Connection và connection pool

JDBC định nghĩa DataSource trong package javax.sql. DataSource là một factory cung cấp Connection; nó tách mã ứng dụng khỏi cách tạo kết nối cụ thể.

~~~java
DataSource dataSource = obtainDataSource();

try (Connection connection = dataSource.getConnection()) {
    // Thực hiện truy vấn JDBC.
}
~~~

Một connection pool triển khai DataSource và giữ một tập kết nối vật lý để tái sử dụng. Khi ứng dụng gọi getConnection(), pool thường cho mượn một connection đang rảnh. Khi ứng dụng gọi close() trên Connection được mượn, connection thường được trả về pool thay vì đóng socket vật lý ngay lập tức.

Các thành phần thường gặp:

| Thành phần | Vai trò |
|---|---|
| DataSource | API chuẩn để lấy Connection |
| Connection | Phiên làm việc JDBC với database |
| Connection pool | Quản lý và tái sử dụng các kết nối vật lý |
| Driver JDBC | Giao tiếp với database qua giao thức tương ứng |
| PreparedStatement | Thực thi câu lệnh SQL có tham số |
| ResultSet | Đọc kết quả truy vấn |
| Transaction | Nhóm thao tác cần commit hoặc rollback nhất quán |

### DataSource không đồng nghĩa với pool

DataSource là interface chuẩn; nó không quy định mọi DataSource đều có pool hoặc có phương thức shutdown. Interface DataSource không định nghĩa close().

Một pool cụ thể có thể có API đóng riêng. Ví dụ, HikariDataSource cung cấp close(); Apache Commons DBCP BasicDataSource cũng có lifecycle method riêng. Khi quản lý vòng đời, cần giữ tham chiếu đến đối tượng pool cụ thể hoặc dùng một abstraction có phương thức close rõ ràng. Không nên ép kiểu mọi DataSource sang AutoCloseable nếu không biết implementation.

### Connection.close() khác pool.close()

Hai lời gọi này có ý nghĩa khác nhau:

- Connection.close(): kết thúc việc sử dụng connection hiện tại; với pool, thường trả connection về pool.
- Pool.close(): dừng pool, giải phóng các kết nối vật lý và tài nguyên nội bộ theo implementation.

Không gọi pool.close() sau mỗi request. Pool được tạo và đóng theo vòng đời ứng dụng hoặc một thành phần dịch vụ.

## 2. Vòng đời thông thường của một JDBC pool

Một ứng dụng có thể tạo pool lúc khởi động, dùng pool trong suốt thời gian phục vụ và đóng pool khi shutdown.

~~~text
Ứng dụng khởi động
        |
        v
Đọc cấu hình JDBC
        |
        v
Tạo DataSource / connection pool
        |
        v
Nhận request và lấy Connection
        |
        v
Thực hiện transaction
        |
        v
Connection.close() trả connection về pool
        |
        v
Ứng dụng shutdown
        |
        v
Đóng connection pool
~~~

Trong chu kỳ bình thường, pool có thể duy trì kết nối idle, tạo kết nối mới khi tải tăng và loại bỏ kết nối hết hạn. Các pool cũng có thể chạy housekeeper, validation hoặc eviction task trên các thread nền.

Trong CRaC, checkpoint không giống shutdown thông thường. Ứng dụng sẽ tiếp tục từ checkpoint image ở một thời điểm khác. Vì vậy, cần chuẩn bị pool sao cho các socket, thread nền và trạng thái connection không bị dùng lại trong điều kiện không còn phù hợp.

## 3. Vì sao cần đóng pool trước checkpoint?

Connection JDBC đang mở thường gắn với:

- Socket TCP đến database hoặc proxy.
- Session và transaction ở phía database.
- Trạng thái protocol trong JDBC driver.
- Buffer và tài nguyên native.
- Thread nền của pool để kiểm tra hoặc quản lý connection.
- Credential, token hoặc thông tin xác thực được dùng lúc mở kết nối.

Trong thời gian ứng dụng được checkpoint, database có thể timeout session, proxy có thể đóng socket, network route có thể thay đổi hoặc credential có thể được xoay vòng. Khi restore, một Connection vẫn tồn tại trong heap chưa chắc còn sử dụng được ở phía database.

Do đó, không nên xem connection đang mượn từ pool là tài nguyên có thể tiếp tục sử dụng an toàn sau restore. Ứng dụng cần hoàn tất transaction và giải phóng connection trước checkpoint, sau đó đóng pool để runtime không phải khôi phục các socket hoặc thread nền đã gắn với pool cũ.

Một quy trình phổ biến:

~~~text
Ngừng nhận request mới
        |
        v
Chờ request đang chạy hoàn tất
        |
        v
Commit / rollback transaction
        |
        v
Đóng các Connection đang được mượn
        |
        v
Đóng DataSource / connection pool
        |
        v
Checkpoint
        |
        v
Restore
        |
        v
Tạo connection pool mới
        |
        v
Kiểm tra database và mở lại lưu lượng
~~~

Đóng pool không thay thế việc drain request. Nếu còn thread đang sử dụng Connection, việc đóng pool có thể làm request lỗi hoặc khiến transaction bị gián đoạn. Ứng dụng phải kiểm soát công việc đang chạy trước.

## 4. Quản lý Connection và transaction trước checkpoint

### Luôn đóng Connection bằng try-with-resources

Mỗi Connection được mượn cần có vòng đời rõ ràng:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
         connection.prepareStatement(
             "select id, name from customer where id = ?")) {

    statement.setLong(1, customerId);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            // Xử lý dữ liệu.
        }
    }
}
~~~

Khi khối try kết thúc, ResultSet, PreparedStatement và Connection được đóng theo thứ tự ngược. Với pool, Connection.close() trả connection về pool.

Không giữ Connection trong field static, singleton hoặc ThreadLocal qua nhiều request. Không để Connection sống lâu hơn transaction hoặc công việc cần nó. Một connection được giữ qua checkpoint có thể đại diện cho transaction chưa hoàn tất và socket không còn hợp lệ sau restore.

### Hoàn tất transaction

Với auto-commit tắt, ứng dụng phải quyết định commit hoặc rollback trước khi trả connection:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        updateAccount(connection);
        insertAuditRecord(connection);

        connection.commit();
    } catch (Exception failure) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }

        throw failure;
    }
}
~~~

Không nên để transaction đang mở khi bắt đầu checkpoint. Transaction có thể giữ lock trong database, chiếm connection trong pool và để lại trạng thái không rõ ràng nếu socket bị mất.

Ứng dụng cần xác định chính sách cho công việc đang chạy:

- Chờ transaction hoàn tất trong một khoảng thời gian giới hạn.
- Nếu quá thời hạn, yêu cầu tầng nghiệp vụ hủy công việc và rollback.
- Nếu không thể xác định transaction đã commit hay chưa do lỗi kết nối, dùng transaction ID, idempotency key hoặc cơ chế đối soát để tránh thực hiện trùng.

Đừng suy luận rằng transaction đã rollback chỉ vì client connection bị đóng. Database có thể đã commit trước khi client mất kết nối nhưng phản hồi chưa đến ứng dụng.

### Theo dõi connection đang được mượn

Để drain chính xác, ứng dụng có thể theo dõi số request đang chạy hoặc số connection đang được sử dụng. Một số pool cung cấp metrics như active, idle, total và pending threads. Tên API phụ thuộc implementation.

Chỉ khi request đã dừng và số connection active về 0 (hoặc đạt điều kiện đã định nghĩa), ứng dụng mới nên đóng pool. Đặt timeout cho bước drain để tránh checkpoint bị treo vô hạn.

## 5. DataSource và connection pool trong CRaC

CRaC cung cấp interface Resource trong package org.crac. Một thành phần triển khai Resource có thể đăng ký với global context để nhận callback:

- beforeCheckpoint(): chuẩn bị resource trước khi tạo checkpoint image.
- afterRestore(): tạo lại resource sau khi tiến trình được khôi phục.

Với JDBC, resource thường chịu trách nhiệm đóng pool cũ trước checkpoint và tạo pool mới sau restore.

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class JdbcPoolResource implements Resource {
    private final JdbcPoolFactory factory;
    private JdbcPoolHandle pool;

    public JdbcPoolResource(JdbcPoolFactory factory) throws Exception {
        this.factory = factory;
        this.pool = factory.create();
        Core.getGlobalContext().register(this);
    }

    public synchronized DataSource dataSource() {
        if (pool == null) {
            throw new IllegalStateException(
                "JDBC pool is not ready"
            );
        }
        return pool.dataSource();
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        if (pool == null) {
            return;
        }

        if (!pool.awaitIdle()) {
            throw new IllegalStateException(
                "JDBC pool still has active connections"
            );
        }

        JdbcPoolHandle oldPool = pool;
        oldPool.close();
        pool = null;
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        pool = factory.create();
    }

    public synchronized void reopenAfterAbortedCheckpoint()
            throws Exception {
        if (pool == null) {
            pool = factory.create();
        }
    }
}
~~~

JdbcPoolFactory và JdbcPoolHandle là abstraction của ứng dụng, không phải lớp JDBC chuẩn. Ví dụ rút gọn để làm rõ trách nhiệm:

~~~java
public interface JdbcPoolFactory {
    JdbcPoolHandle create() throws Exception;
}

public interface JdbcPoolHandle {
    DataSource dataSource();

    boolean awaitIdle() throws Exception;

    void close() throws Exception;
}
~~~

Implementation của JdbcPoolHandle có thể bọc HikariDataSource, BasicDataSource hoặc pool khác. awaitIdle() cần dùng API metrics hoặc cơ chế drain của pool cụ thể. Nếu pool không cung cấp phương thức chờ idle, ứng dụng có thể phối hợp bằng bộ đếm request/connection do mình quản lý.

Trong code thật, cần xử lý trường hợp close() thất bại một phần. Không đặt pool thành null và báo thành công nếu implementation chưa thực sự đóng; nếu không thể xác định trạng thái, giữ ứng dụng ở trạng thái chưa sẵn sàng và báo lỗi.

### Giữ DataSource injection ổn định

Nhiều ứng dụng inject DataSource vào repository hoặc DAO khi khởi động. Nếu đóng pool cũ rồi tạo một đối tượng pool mới, các repository vẫn có thể giữ tham chiếu đến pool cũ đã đóng.

Có hai cách thiết kế phổ biến:

1. Dùng một wrapper DataSource ổn định, wrapper chuyển getConnection() tới delegate hiện tại. Khi restore, thay delegate bằng pool mới.
2. Quản lý pool như một bean có lifecycle được cập nhật bởi container, bảo đảm repository lấy đúng DataSource mới sau restore.

Nếu dùng wrapper, mọi phương thức DataSource cần được delegate nhất quán; không chỉ cập nhật một field trong resource trong khi các thành phần khác vẫn giữ pool cũ.

Không nên tạo một pool mới trong afterRestore() mà không cập nhật nơi cung cấp DataSource cho ứng dụng. Khi đó pool mới có thể hoạt động nhưng request vẫn gọi đối tượng cũ.

## 6. Ví dụ với HikariCP

HikariCP là một connection pool phổ biến. HikariDataSource có phương thức close() để dừng pool. Cấu hình nên được tạo từ cấu hình ứng dụng, không hard-code mật khẩu trong mã nguồn.

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

public final class HikariPoolFactory {
    public HikariDataSource create() {
        HikariConfig config = new HikariConfig();

        config.setJdbcUrl(System.getenv("JDBC_URL"));
        config.setUsername(System.getenv("JDBC_USER"));
        config.setPassword(System.getenv("JDBC_PASSWORD"));

        config.setMaximumPoolSize(10);
        config.setMinimumIdle(2);
        config.setConnectionTimeout(10_000);
        config.setValidationTimeout(5_000);

        return new HikariDataSource(config);
    }
}
~~~

Một wrapper có thể giữ reference tới HikariDataSource và cung cấp lifecycle:

~~~java
public final class HikariPoolHandle implements JdbcPoolHandle {
    private final HikariDataSource dataSource;

    public HikariPoolHandle(HikariDataSource dataSource) {
        this.dataSource = dataSource;
    }

    @Override
    public DataSource dataSource() {
        return dataSource;
    }

    @Override
    public boolean awaitIdle() {
        // Dùng metrics hoặc bộ đếm active connection
        // do ứng dụng quản lý để xác nhận đã drain.
        return dataSource.getHikariPoolMXBean() != null
            && dataSource.getHikariPoolMXBean()
                         .getActiveConnections() == 0;
    }

    @Override
    public void close() {
        dataSource.close();
    }
}
~~~

Đoạn ví dụ chỉ minh họa cách bọc pool. Trong ứng dụng thực tế, không nên dùng một lần đọc metrics làm cơ chế drain nếu vẫn có thể xuất hiện request mới. Phải dừng nhận việc trước, chờ in-flight request kết thúc, rồi mới kiểm tra active connection. Cần xử lý trường hợp getHikariPoolMXBean() chưa sẵn sàng hoặc pool đã shutdown.

Khi restore, factory tạo một HikariDataSource mới từ cấu hình hiện tại. Kết nối vật lý sẽ được tạo theo nhu cầu hoặc theo minimumIdle tùy cấu hình pool.

Với Apache Commons DBCP, Oracle UCP hoặc pool do application server quản lý, dùng API lifecycle tương ứng. Không giả định mọi pool có cùng hành vi close, eviction, validation hoặc khả năng tích hợp CRaC.

## 7. Điều phối checkpoint để đóng và mở lại pool

Nếu ứng dụng chủ động gọi Core.checkpointRestore(), bộ điều phối có thể kiểm soát việc dừng lưu lượng, chờ transaction hoàn tất và phục hồi pool khi checkpoint bị hủy.

~~~java
import org.crac.CheckpointException;
import org.crac.Core;
import org.crac.RestoreException;

public final class DatabaseCheckpointCoordinator {
    private final RequestGate requestGate;
    private final JdbcPoolResource jdbcPool;

    public DatabaseCheckpointCoordinator(
            RequestGate requestGate,
            JdbcPoolResource jdbcPool) {
        this.requestGate = requestGate;
        this.jdbcPool = jdbcPool;
    }

    public void checkpoint() throws Exception {
        requestGate.stopAcceptingNewRequests();

        boolean readyToResume = false;

        try {
            requestGate.awaitInFlightRequests();

            Core.checkpointRestore();

            // Khi thực thi tiếp tục sau restore,
            // callback afterRestore() đã tạo pool mới.
            readyToResume = true;

        } catch (CheckpointException checkpointFailure) {
            try {
                jdbcPool.reopenAfterAbortedCheckpoint();
                readyToResume = true;
            } catch (Exception reopenFailure) {
                checkpointFailure.addSuppressed(reopenFailure);
                markApplicationNotReady();
            }

            throw checkpointFailure;

        } catch (RestoreException restoreFailure) {
            // Instance đã restore nhưng callback restore có lỗi.
            // Không mở lưu lượng khi pool chưa sẵn sàng.
            markApplicationNotReady();
            throw restoreFailure;

        } finally {
            if (readyToResume) {
                requestGate.resumeAcceptingRequests();
            }
        }
    }

    private void markApplicationNotReady() {
        // Cập nhật readiness/health state để không nhận traffic.
    }
}
~~~

RequestGate là abstraction của ứng dụng để ngừng request mới và chờ request đang chạy kết thúc. Ví dụ giả định resource JDBC đã được đăng ký với CRaC và afterRestore() tạo pool mới. Nếu callback afterRestore() thất bại, không được mở lưu lượng.

Khi checkpoint thất bại, Core.checkpointRestore() ném CheckpointException trong instance ban đầu. Bộ điều phối gọi reopenAfterAbortedCheckpoint() để tạo pool mới. Nếu việc mở lại cũng thất bại, lỗi phục hồi được gắn vào exception gốc và ứng dụng giữ trạng thái not-ready.

Nếu dùng jcmd trực tiếp từ bên ngoài:

~~~bash
jcmd <pid> JDK.checkpoint
~~~

Luồng nghiệp vụ của ứng dụng không có lời gọi Core.checkpointRestore() để bắt CheckpointException. Vì vậy, không thể dựa vào catch block trong coordinator để xử lý trường hợp checkpoint bị hủy bởi lệnh jcmd. Nếu yêu cầu rollback pool tự động là bắt buộc, nên gửi yêu cầu qua cơ chế quản trị của ứng dụng để coordinator gọi API CRaC. Nếu vẫn dùng jcmd, cần thiết kế callback và quy trình vận hành có khả năng phục hồi phù hợp.

## 8. Cấu hình pool sau restore

Không nên giả định cấu hình pool trước checkpoint luôn còn phù hợp sau restore. Khi tạo pool mới, ứng dụng có thể cần đọc lại cấu hình hoặc thông tin xác thực theo chính sách triển khai.

Các thông tin thường cần kiểm tra:

- JDBC URL và hostname database.
- Username, password hoặc token.
- TLS certificate và truststore.
- Connection timeout và validation timeout.
- Maximum pool size và minimum idle.
- Transaction isolation mặc định.
- Driver version và các tùy chọn vendor-specific.
- Cấu hình proxy, failover hoặc read replica.

Nếu credential được xoay vòng trong thời gian checkpoint, việc dùng password đã lưu trong heap có thể khiến kết nối mới thất bại. Có thể đọc lại secret từ secret manager hoặc nguồn cấu hình sau restore, tùy mô hình bảo mật.

Không ghi URL có token, password hoặc dữ liệu xác thực vào log. Nên log tên database/service, thời gian kết nối và mã lỗi đã được loại bỏ thông tin nhạy cảm.

### Kiểm tra database sẵn sàng

Pool được tạo thành công chưa chắc database đã sẵn sàng nhận truy vấn. Sau restore, cần xác minh kết nối theo cách phù hợp với pool và driver.

Ví dụ:

~~~java
try (Connection connection = dataSource.getConnection()) {
    if (!connection.isValid(5)) {
        throw new SQLException("Database connection is not valid");
    }
}
~~~

Connection.isValid() phụ thuộc driver và database. Một số pool có connection test query hoặc validation mechanism riêng. Hãy dùng cấu hình được driver hỗ trợ và tránh chạy truy vấn kiểm tra quá nặng.

Nếu database chưa sẵn sàng, có thể retry với exponential backoff và giới hạn tổng thời gian. Không tạo vô hạn pool hoặc vô hạn thread retry. Chỉ đánh dấu ứng dụng ready khi các dependency bắt buộc đã hoạt động.

## 9. Pool sizing và giới hạn kết nối database

Restore nhiều instance từ cùng một checkpoint có thể làm số lượng connection pool tăng nhanh. Nếu mỗi instance tạo pool có maximumPoolSize là 20 và có 10 instance, tổng số kết nối có thể lên đến 200, chưa kể các ứng dụng khác.

Cần tính toán theo giới hạn database:

~~~text
Tổng kết nối tối đa
    = số instance
      x maximumPoolSize mỗi instance
      + kết nối quản trị
      + kết nối từ ứng dụng khác
~~~

Một pool lớn không tự động làm ứng dụng nhanh hơn. Số connection quá cao có thể tăng tranh chấp lock, bộ nhớ và chi phí lập lịch ở database.

Khi scale out từ checkpoint image:

- Chọn maximumPoolSize theo tổng ngân sách connection của database.
- Không để mọi instance đồng loạt mở pool quá lớn ngay khi restore.
- Có thể dùng minimumIdle thấp và tạo connection theo nhu cầu.
- Áp dụng backoff khi database từ chối kết nối.
- Theo dõi active, idle, pending, timeout và connection creation failures.
- Dùng giới hạn kết nối ở tầng database hoặc proxy nếu cần bảo vệ dịch vụ.

## 10. Thread nền và tài nguyên do pool quản lý

Một connection pool thường có các thread nền để quản lý idle connection, kiểm tra thời gian sống, dọn connection hết hạn hoặc xử lý tác vụ nội bộ.

Trước checkpoint, đóng pool giúp kết thúc vòng đời các thread và socket do pool sở hữu. Sau restore, pool mới tạo các thread và connection theo cấu hình hiện tại.

Không nên:

- Giữ một Connection trong ThreadLocal qua checkpoint.
- Giữ ScheduledExecutorService của pool cũ rồi tạo thêm pool mới mà không đóng executor cũ.
- Tạo pool mới trong afterRestore() nhưng bỏ quên pool cũ.
- Đóng pool trong khi request vẫn đang dùng connection.
- Tạo connection mới từ callback trước checkpoint sau khi đã chuyển service sang trạng thái drain.
- Chạy health check đồng thời với quá trình đóng pool.

Nếu ứng dụng tự tạo executor để quản lý JDBC retry hoặc health check, cần quản lý vòng đời executor riêng. Resource của database có thể phụ thuộc vào executor đó; hãy xác định thứ tự dừng và khởi động lại rõ ràng.

## 11. Thứ tự callback và các thành phần phụ thuộc database

Ứng dụng có thể có nhiều Resource: request listener, transaction manager, DataSource, cache và worker. Chúng có quan hệ phụ thuộc.

Ví dụ, request handler dùng repository, repository dùng DataSource:

~~~text
RequestHandler
      |
      v
Repository / DAO
      |
      v
TransactionManager
      |
      v
DataSource / JDBC Pool
      |
      v
Database
~~~

Trước checkpoint, cần dừng request và worker trước, chờ transaction hoàn tất, sau đó mới đóng pool. Sau restore, cần tạo pool và xác minh database trước khi mở request handler.

Không dựa vào thứ tự đăng ký Resource một cách ngầm định để thay thế quy trình drain. Hãy dùng một coordinator hoặc lifecycle manager để đảm bảo các bước phụ thuộc được thực hiện theo thứ tự đúng. Nếu dùng nhiều Resource callback, kiểm tra quy tắc thứ tự của phiên bản CRaC đang chạy và thiết kế sao cho callback vẫn an toàn khi một dependency chưa sẵn sàng.

## 12. Các lỗi thường gặp

### Connection đã đóng nhưng repository vẫn dùng pool cũ

Nguyên nhân thường là repository giữ tham chiếu tới DataSource cũ sau khi resource tạo pool mới.

Cách xử lý: dùng wrapper DataSource ổn định hoặc cập nhật bean/container để mọi repository nhận delegate mới. Kiểm tra pool instance ID trong log để nhận biết tham chiếu cũ.

### Pool shutdown trong khi còn connection active

Request có thể gặp SQLException hoặc transaction bị gián đoạn.

Cách xử lý: dừng request mới, chờ in-flight request, kiểm tra active connection và chỉ đóng pool khi đã đạt điều kiện drain.

### Database từ chối kết nối sau restore

Có thể do database chưa sẵn sàng, DNS hoặc network chưa ổn định, credential đã đổi, giới hạn kết nối bị chạm hoặc TLS configuration không hợp lệ.

Cách xử lý: kiểm tra lỗi driver, xác minh secret/config, retry có giới hạn và chỉ mở readiness sau khi pool hoạt động.

### Transaction bị xử lý không rõ kết quả

Client có thể mất kết nối sau khi database đã commit nhưng trước khi nhận acknowledgement.

Cách xử lý: dùng idempotency key, transaction identifier hoặc đối soát trạng thái ở database. Không tự động lặp lại thao tác không idempotent chỉ vì client nhận lỗi kết nối.

### Checkpoint bị hủy sau khi pool đã đóng

Nếu callback đóng pool thành công nhưng callback khác hoặc engine checkpoint thất bại, instance ban đầu có thể tiếp tục với pool null hoặc đã shutdown.

Cách xử lý: khi dùng Core.checkpointRestore(), bắt CheckpointException và tạo pool mới. Nếu dùng jcmd bên ngoài, cần quy trình phục hồi riêng hoặc cơ chế quản trị gọi checkpoint từ trong ứng dụng.

### Tạo quá nhiều pool khi restore nhiều instance

Mỗi instance khôi phục có thể tạo một pool mới, làm vượt giới hạn kết nối database.

Cách xử lý: tính tổng connection budget, giới hạn pool size, giảm minimum idle và điều tiết quá trình khởi động instance.

## 13. Quan sát và vận hành

Nên theo dõi các chỉ số của pool trước và sau restore:

| Chỉ số | Ý nghĩa |
|---|---|
| active_connections | Số connection đang được mượn |
| idle_connections | Số connection sẵn sàng |
| total_connections | Tổng connection trong pool |
| pending_threads | Số thread đang chờ connection |
| connection_timeout_total | Số lần chờ connection quá hạn |
| connection_creation_failure_total | Số lần tạo connection thất bại |
| pool_lifecycle_state | Pool đang ACTIVE, PREPARING, CLOSED hay RESTORING |
| database_validation_failure_total | Số lần kiểm tra database thất bại |

Log nên có pool ID hoặc generation ID để phân biệt pool trước checkpoint và pool sau restore. Ghi lại thời gian bắt đầu drain, thời gian chờ connection, thời gian đóng pool, thời gian tạo pool và kết quả kiểm tra database.

Không log password, token, JDBC URL có chứa credential hoặc dữ liệu truy vấn nhạy cảm. Với exception từ driver, kiểm tra nội dung trước khi đưa vào hệ thống log tập trung.

## 14. Quy trình đề xuất

### Trước checkpoint

1. Chuyển ứng dụng sang trạng thái không nhận request mới.
2. Chờ request và tác vụ nền đang sử dụng database hoàn tất.
3. Commit hoặc rollback transaction đang mở.
4. Đóng ResultSet, Statement và Connection bằng try-with-resources.
5. Xác nhận connection active đã về 0 hoặc đạt điều kiện drain.
6. Đóng DataSource/connection pool bằng API của implementation.
7. Ghi log pool đã được đóng và sẵn sàng checkpoint.

### Sau restore

1. Đọc lại cấu hình database và secret nếu chính sách yêu cầu.
2. Tạo một pool mới bằng factory.
3. Cập nhật delegate DataSource hoặc bean mà repository sử dụng.
4. Kiểm tra kết nối database.
5. Khởi động lại worker và tác vụ nền phụ thuộc database.
6. Chỉ mở request listener khi pool và dependency đã sẵn sàng.

### Khi checkpoint bị hủy

Nếu ứng dụng gọi Core.checkpointRestore():

1. Bắt CheckpointException.
2. Kiểm tra trạng thái pool.
3. Nếu pool đã đóng, tạo pool mới.
4. Kiểm tra database.
5. Chỉ mở request listener khi pool đã hoạt động.
6. Nếu phục hồi thất bại, giữ readiness ở trạng thái false và báo lỗi.

Nếu checkpoint được gửi bằng jcmd trực tiếp, không có catch block trong luồng gọi API của ứng dụng. Thiết kế lifecycle và quy trình quản trị cần phản ánh giới hạn này.

## 15. Nguyên tắc cần ghi nhớ

- DataSource là factory chuẩn của JDBC; không phải mọi DataSource đều là connection pool.
- DataSource interface không định nghĩa close(); đóng pool bằng API của implementation.
- Connection.close() thường trả connection về pool; pool.close() đóng pool và giải phóng tài nguyên.
- Dùng try-with-resources để đóng Connection, Statement và ResultSet.
- Hoàn tất hoặc rollback transaction trước checkpoint.
- Ngừng nhận việc mới và drain connection active trước khi đóng pool.
- Không giữ Connection hoặc transaction qua checkpoint.
- Tạo pool mới trong afterRestore() và cập nhật nơi cung cấp DataSource cho repository.
- Xác minh database trước khi đánh dấu ứng dụng ready.
- Bắt CheckpointException để phục hồi pool khi checkpoint bị hủy nếu ứng dụng chủ động gọi Core.checkpointRestore().
- Với jcmd từ bên ngoài, xây dựng quy trình phục hồi riêng vì luồng nghiệp vụ không bắt được exception đó.
- Tính tổng connection budget khi restore nhiều instance.
- Quản lý riêng thread nền, executor, retry và health check do pool hoặc ứng dụng tạo ra.

DataSource và connection pool là tài nguyên có vòng đời gắn với database, network và thread của tiến trình. Khi ứng dụng drain request, hoàn tất transaction, đóng pool trước checkpoint và tạo pool mới sau restore, các repository có thể tiếp tục dùng JDBC với kết nối hợp lệ. Việc kiểm tra readiness và giới hạn connection sau restore giúp tránh đưa một instance chưa kết nối được database vào phục vụ lưu lượng.
