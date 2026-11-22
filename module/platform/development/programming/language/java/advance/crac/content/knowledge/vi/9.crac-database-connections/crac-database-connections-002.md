# Đóng kết nối trước checkpoint và kiểm tra lại sau restore

Kết nối cơ sở dữ liệu là tài nguyên sống bên ngoài tiến trình Java. Một JDBC `Connection` không chỉ là một object trong heap: nó thường đại diện cho một phiên làm việc trên database server, một socket mạng, trạng thái giao thức của driver và có thể cả transaction đang mở. Khi tiến trình được checkpoint rồi restore ở một thời điểm khác, phiên kết nối đó có thể đã bị server đóng, mạng thay đổi hoặc transaction không còn hợp lệ.

Vì vậy, ứng dụng CRaC nên chủ động đưa tầng truy cập dữ liệu về trạng thái an toàn trước checkpoint: ngừng nhận công việc mới, chờ các thao tác đang chạy hoàn tất, commit hoặc rollback transaction, đóng các connection và đóng connection pool theo hướng dẫn của thư viện. Sau restore, ứng dụng cần lấy lại thông tin xác thực còn hiệu lực, tạo pool mới, kiểm tra kết nối thực tế đến database rồi mới cho phép repository, worker và request sử dụng nó.

Điểm quan trọng là checkpoint image chỉ lưu trạng thái tiến trình trong phạm vi cơ chế hỗ trợ. Nó không đóng băng database server, không giữ transaction từ xa và không bảo đảm socket JDBC còn dùng được sau restore. Ứng dụng phải thiết kế vòng đời kết nối rõ ràng ở cả hai phía checkpoint và restore.

## 1. Vì sao không nên giữ JDBC connection qua checkpoint?

Một kết nối JDBC thường bao gồm nhiều lớp trạng thái:

- Object `Connection` và trạng thái driver nằm trong heap JVM.
- Socket TCP hoặc tài nguyên hệ điều hành dùng để trao đổi dữ liệu với database.
- Phiên/session do database server quản lý.
- Trạng thái transaction, lock, cursor, prepared statement và result set.
- Thời hạn kết nối, timeout, keepalive, TLS session và các thông tin xác thực.

Checkpoint có thể lưu trạng thái của object Java và một phần trạng thái tiến trình, nhưng database server vẫn hoạt động độc lập. Trong thời gian image được lưu, server có thể timeout session, restart, failover, thay đổi primary node hoặc kết thúc transaction. Mạng cũng có thể thay đổi địa chỉ, route hoặc trạng thái socket.

Sau restore, object `Connection` cũ có thể vẫn tồn tại trong heap nhưng không còn đại diện cho một phiên database có thể sử dụng. Một lệnh SQL tiếp theo có thể gặp lỗi như:

- Connection đã đóng.
- Socket reset hoặc broken pipe.
- Read timeout hoặc connection timeout.
- Session không còn tồn tại trên database.
- Transaction đã bị rollback hoặc timeout.
- TLS hoặc thông tin xác thực không còn hợp lệ.

Do đó, không nên dựa vào việc object `Connection` vẫn khác `null` để kết luận kết nối còn hoạt động. Cần đóng kết nối trước checkpoint và tạo kết nối mới sau restore.

## 2. Chuẩn bị tầng database trước checkpoint

Trước khi đóng pool, ứng dụng cần ngăn các thành phần tiếp tục sử dụng database. Nếu chỉ gọi `close()` trên connection pool trong khi worker vẫn xử lý request, các thao tác đang chạy có thể thất bại giữa chừng.

Một quy trình chuẩn bị có thể gồm:

1. Ngừng nhận request hoặc message mới ở các thành phần cần database.
2. Tạm dừng scheduler, consumer và worker có thể phát sinh truy vấn.
3. Chờ các request và tác vụ đang chạy hoàn tất trong một khoảng thời gian có giới hạn.
4. Xác nhận các transaction đã commit hoặc rollback.
5. Đóng các `ResultSet`, `Statement`, `EntityManager` hoặc session còn mở theo đúng ownership.
6. Đóng connection pool để giải phóng connection và socket.
7. Chỉ tiếp tục checkpoint khi trạng thái database trong tiến trình đã an toàn.

### 2.1. Ngừng nhận việc mới và drain công việc đang chạy

Một ứng dụng Spring Boot có thể có nhiều nguồn tạo truy vấn: HTTP controller, message listener, scheduler, batch job và background executor. Tất cả các nguồn này cần được đưa vào trạng thái tạm dừng trước khi đóng pool.

Ví dụ, một worker xử lý đơn hàng có thể đang thực hiện ba bước:

1. Đọc đơn hàng từ database.
2. Gọi dịch vụ thanh toán.
3. Cập nhật trạng thái đơn hàng.

Nếu checkpoint xảy ra giữa bước 2 và bước 3, tiến trình có thể được khôi phục với trạng thái trong bộ nhớ không phản ánh chính xác kết quả thanh toán bên ngoài. Vì vậy, cần chờ tác vụ hoàn tất hoặc đưa nó về một ranh giới nghiệp vụ an toàn trước khi checkpoint.

Thời gian drain nên có giới hạn. Nếu hết thời hạn mà vẫn còn request hoặc transaction, chính sách phù hợp thường là hủy checkpoint và tiếp tục phục vụ sau khi khôi phục trạng thái hoạt động. Không nên đóng pool đang được sử dụng chỉ để cố tạo image.

### 2.2. Hoàn tất transaction một cách tường minh

Không nên để transaction đang mở tại thời điểm checkpoint. Hãy hoàn tất hoặc rollback theo chính sách nghiệp vụ trước khi đóng connection.

Với JDBC thủ công:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    try {
        updateOrder(connection, orderId);
        insertAuditRecord(connection, orderId);
        connection.commit();
    } catch (Exception failure) {
        connection.rollback();
        throw failure;
    }
}
```

`try-with-resources` giúp đóng connection sau khi khối xử lý kết thúc. Trong ví dụ, transaction được commit khi cả hai thao tác thành công và rollback khi có lỗi. Ứng dụng thực tế cần xử lý thêm lỗi khi rollback, lỗi khi close và exception của driver theo chính sách của mình.

Với Spring transaction management, hãy để transaction boundary kết thúc trước khi callback checkpoint đóng pool. Không tự đóng connection do transaction manager đang quản lý từ một callback độc lập, vì điều đó có thể làm hỏng transaction đang chạy.

Đóng connection không phải cách thay thế cho việc xác định transaction đã commit hay rollback. Nếu một request đã gửi tác dụng phụ đến dịch vụ bên ngoài rồi mới thất bại khi cập nhật database, ứng dụng vẫn cần idempotency key, outbox hoặc cơ chế đối soát phù hợp.

## 3. Connection pool cần được quản lý như một tài nguyên

Trong ứng dụng server, thường không tạo một JDBC connection mới cho mỗi thành phần rồi giữ mãi. Thay vào đó, ứng dụng dùng connection pool như HikariCP để tái sử dụng connection và giới hạn số kết nối đồng thời.

Pool quản lý nhiều thứ hơn một biến `DataSource`:

- Một tập connection JDBC.
- Socket đang kết nối tới database.
- Thread nền để kiểm tra hoặc quản lý connection.
- Timeout, keepalive và validation.
- Hàng đợi chờ connection và trạng thái shutdown.

Vì vậy, trước checkpoint cần đóng pool theo API của thư viện. Sau restore, thông thường cần tạo một pool mới từ cấu hình hiện hành. Không nên giả định một pool đã `close()` có thể được mở lại bằng cách gọi `getConnection()`.

Ví dụ với HikariCP, `HikariDataSource.close()` đóng pool. Khi cần hoạt động lại, hãy tạo một instance `HikariDataSource` mới thay vì cố tái sử dụng instance đã đóng.

## 4. Kiểm tra kết nối sau restore

Sau restore, việc tạo lại object pool chưa chứng minh database có thể truy cập. Ứng dụng cần xác nhận kết nối thực tế và các điều kiện cần thiết trước khi nhận traffic.

Một quy trình kiểm tra nên bao gồm:

1. Lấy lại endpoint và thông tin xác thực theo cấu hình hiện hành.
2. Tạo connection pool mới.
3. Lấy thử một connection từ pool.
4. Kiểm tra connection còn hoạt động bằng API JDBC hoặc truy vấn kiểm tra phù hợp.
5. Xác nhận database/schema cần dùng có thể truy cập và quyền cần thiết còn hợp lệ.
6. Chỉ sau khi kiểm tra thành công mới cho repository, worker và request tiếp tục hoạt động.

### 4.1. Dùng JDBC `Connection.isValid`

JDBC cung cấp `Connection.isValid(int timeout)` để kiểm tra connection còn hợp lệ. Ví dụ:

```java
try (Connection connection = dataSource.getConnection()) {
    if (!connection.isValid(5)) {
        throw new SQLException("Database connection is not valid");
    }
}
```

Tham số `5` là timeout tính bằng giây theo hợp đồng JDBC. Driver cần hỗ trợ phương thức này; nếu driver có giới hạn hoặc cách kiểm tra riêng, hãy đọc tài liệu driver.

Một số hệ thống chọn chạy truy vấn nhẹ như `SELECT 1`. Cách này có thể xác nhận thêm rằng database thực thi được câu lệnh, nhưng cú pháp và quyền thực hiện cần phù hợp với loại database. Không dùng một truy vấn có tác dụng phụ làm health check.

### 4.2. Kiểm tra pool không đồng nghĩa kiểm tra toàn bộ ứng dụng

Pool có thể kết nối thành công trong khi một dependency khác vẫn chưa sẵn sàng: schema migration chưa hoàn tất, credential chỉ có quyền kết nối nhưng không có quyền truy vấn, database đang ở trạng thái read-only hoặc message consumer chưa đăng ký lại.

Readiness của ứng dụng nên phản ánh các dependency thực sự cần cho traffic. Có thể tách:

- **Liveness:** tiến trình JVM còn hoạt động và không bị kẹt nghiêm trọng.
- **Readiness:** database và các dependency bắt buộc đã sẵn sàng để xử lý request.
- **Startup/restore status:** ứng dụng đang ở giai đoạn phục hồi sau restore.

Không báo readiness thành công chỉ vì callback `afterRestore` đã bắt đầu hoặc pool object đã được tạo.

## 5. Tích hợp với CRaC Resource

CRaC cung cấp `org.crac.Resource` để ứng dụng xử lý tài nguyên ở hai thời điểm:

- `beforeCheckpoint(...)`: ngừng hoạt động sử dụng database, hoàn tất công việc và đóng pool trước khi tạo image.
- `afterRestore(...)`: tạo pool mới, kiểm tra kết nối và mở lại các thành phần phụ thuộc.

Ví dụ dưới đây minh họa cách quản lý một pool HikariCP qua một holder. Repository lấy connection qua holder mỗi lần thực hiện công việc, do đó có thể sử dụng pool instance mới sau restore.

```java
import com.zaxxer.hikari.HikariDataSource;

import java.sql.Connection;
import java.sql.SQLException;
import java.util.concurrent.atomic.AtomicReference;

public final class DatabasePoolHolder {

    private final AtomicReference<HikariDataSource> current =
            new AtomicReference<>();

    public Connection getConnection() throws SQLException {
        HikariDataSource pool = current.get();
        if (pool == null) {
            throw new SQLException("Database pool is not ready");
        }
        return pool.getConnection();
    }

    public void install(HikariDataSource pool) {
        if (!current.compareAndSet(null, pool)) {
            throw new IllegalStateException("Database pool is already installed");
        }
    }

    public void closeCurrent() {
        HikariDataSource previous = current.getAndSet(null);
        if (previous != null) {
            previous.close();
        }
    }
}
```

Resource phối hợp traffic gate, pool holder và factory:

```java
import com.zaxxer.hikari.HikariDataSource;
import org.crac.Context;
import org.crac.Resource;

import java.sql.Connection;
import java.sql.SQLException;
import java.time.Duration;

public final class DatabaseCracResource implements Resource {

    private final TrafficGate trafficGate;
    private final DatabasePoolHolder poolHolder;
    private final DatabasePoolFactory poolFactory;

    public DatabaseCracResource(
            TrafficGate trafficGate,
            DatabasePoolHolder poolHolder,
            DatabasePoolFactory poolFactory) {
        this.trafficGate = trafficGate;
        this.poolHolder = poolHolder;
        this.poolFactory = poolFactory;
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        // Ngừng việc mới và chờ các transaction/request đang chạy kết thúc.
        trafficGate.pauseAndDrain(Duration.ofSeconds(30));

        // Chỉ đóng pool sau khi không còn thành phần sử dụng nó.
        poolHolder.closeCurrent();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        // Factory lấy cấu hình và credential hiện hành rồi tạo pool mới.
        HikariDataSource restoredPool = poolFactory.create();

        boolean installed = false;
        try {
            try (Connection connection = restoredPool.getConnection()) {
                if (!connection.isValid(5)) {
                    throw new SQLException(
                            "Database connection validation failed");
                }
            }

            poolHolder.install(restoredPool);
            installed = true;
            trafficGate.resume();
        } catch (Exception failure) {
            try {
                if (installed) {
                    poolHolder.closeCurrent();
                } else {
                    restoredPool.close();
                }
            } catch (Exception cleanupFailure) {
                failure.addSuppressed(cleanupFailure);
            }
            throw failure;
        }
    }
}
```

Các interface phụ thuộc trong ví dụ có thể được định nghĩa theo ứng dụng:

```java
import com.zaxxer.hikari.HikariDataSource;
import java.time.Duration;

public interface TrafficGate {
    void pauseAndDrain(Duration timeout) throws Exception;
    void resume() throws Exception;
}

public interface DatabasePoolFactory {
    HikariDataSource create() throws Exception;
}
```

`DatabasePoolFactory.create()` nên lấy endpoint và credential hiện hành từ nguồn cấu hình/secret phù hợp, thay vì chỉ tái sử dụng một credential ngắn hạn đã nằm trong heap trước checkpoint. Trong ứng dụng thực tế, `TrafficGate` cần điều phối cả HTTP request, message consumer, scheduler và executor có thể sử dụng database.

Ví dụ là khung minh họa, không phải một cấu hình Spring Boot hoàn chỉnh. Cần đăng ký `DatabaseCracResource` một lần trong CRaC context phù hợp, đảm bảo repository dùng `DatabasePoolHolder`, và xác định cách phục hồi nếu `pauseAndDrain` hoặc đóng pool thất bại. Nếu checkpoint thất bại sau khi traffic đã bị tạm dừng, ứng dụng cần có chính sách đưa traffic trở lại hoặc chuyển instance sang trạng thái lỗi có kiểm soát.

## 6. Quản lý transaction và connection ở các framework

### 6.1. JDBC thuần

Với JDBC thuần, mỗi thao tác nên có ownership rõ ràng. Dùng `try-with-resources` cho `Connection`, `PreparedStatement` và `ResultSet`. Không lưu connection trong static field hoặc singleton dùng lâu dài trừ khi có một lớp quản lý vòng đời chuyên biệt.

Ví dụ:

```java
String sql = "SELECT status FROM orders WHERE id = ?";

try (Connection connection = poolHolder.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, orderId);

    try (ResultSet resultSet = statement.executeQuery()) {
        if (resultSet.next()) {
            return resultSet.getString("status");
        }
    }
}
```

Connection được trả về pool khi đóng, statement và result set cũng được đóng. Khi pool được thay thế sau restore, lần gọi tiếp theo qua holder sẽ nhận connection từ pool mới.

### 6.2. Spring transaction management

Trong Spring, `DataSourceTransactionManager`, `JpaTransactionManager` hoặc transaction manager tương ứng quản lý connection/session theo transaction boundary. Callback checkpoint không nên tự ý lấy connection đang được transaction manager giữ rồi đóng từ một thread khác.

Hãy đảm bảo:

- Không còn transaction đang chạy trước khi đóng pool.
- Các `@Transactional` method đã kết thúc trên thread thực thi của chúng.
- Message listener và scheduler đã dừng nhận công việc mới.
- EntityManager/Session và persistence context không được giữ lại qua restore nếu chúng phụ thuộc connection cũ.
- DataSource được thay thế hoặc khởi tạo lại theo lifecycle mà Spring bean sử dụng.

Nếu `DataSource` được inject trực tiếp vào nhiều bean, việc thay đổi một field ở nơi khác không tự động cập nhật reference mà các bean đang giữ. Có thể dùng một delegating/routing DataSource có thể đổi target hoặc một holder/proxy được thiết kế để mọi repository luôn truy cập pool hiện tại. Phải bảo đảm target cũ đã đóng và target mới đã kiểm tra trước khi traffic được mở lại.

### 6.3. JPA/Hibernate

Không giữ một `EntityManager`, Hibernate `Session`, JDBC `Statement` hoặc `ResultSet` qua checkpoint như một đơn vị công việc đang hoạt động. Những đối tượng này có thể giữ transaction, cursor, connection hoặc trạng thái persistence context gắn với phiên cũ.

Kết thúc transaction trước checkpoint, đóng các session có phạm vi thủ công và để framework tạo persistence context mới cho công việc sau restore. Sau khi pool mới sẵn sàng, kiểm tra một thao tác repository thực tế qua đường đi mà ứng dụng sẽ sử dụng.

## 7. Credential, DNS và các điều kiện thay đổi khi restore

Kết nối mới sau restore có thể cần thông tin khác với lúc tạo image. Ví dụ:

- Password database được xoay vòng.
- Token truy cập database hoặc secret lease hết hạn.
- DNS trỏ đến địa chỉ mới sau failover.
- Database endpoint chuyển primary hoặc thay đổi proxy.
- Chứng thư TLS được cập nhật.
- Network route hoặc firewall policy thay đổi.
- Database vừa restart và cần thời gian nhận kết nối.

Vì vậy, factory tạo pool nên đọc cấu hình có thể thay đổi tại thời điểm restore. Không nên lưu password, token ngắn hạn hoặc địa chỉ IP đã phân giải vào một object tồn tại từ trước checkpoint rồi giả định chúng còn hợp lệ.

Khi có nhiều instance cùng restore, tránh để tất cả pool đồng thời tạo quá nhiều connection. Hãy tính tổng connection budget của database, giới hạn `maximumPoolSize`, cân nhắc staggered startup hoặc retry có backoff để không tạo một đợt kết nối dồn dập.

## 8. Retry và xử lý khi database chưa sẵn sàng

Database có thể chưa nhận kết nối ngay sau khi ứng dụng restore. Có thể do failover, khởi động lại, DNS propagation hoặc giới hạn connection. Ứng dụng cần phân biệt lỗi tạm thời và lỗi cấu hình.

Một chính sách hợp lý có thể gồm:

1. Thử kết nối với timeout hữu hạn.
2. Với lỗi có thể phục hồi, retry một số lần với exponential backoff và jitter.
3. Giới hạn tổng thời gian chờ restore để không giữ instance ở trạng thái lửng vô hạn.
4. Với lỗi credential hoặc cấu hình không hợp lệ, ghi log rõ và giữ readiness thất bại thay vì retry liên tục.
5. Chỉ resume traffic sau khi pool và thao tác kiểm tra bắt buộc thành công.

Không retry mọi exception với cùng một chu kỳ ngắn. Điều đó có thể tạo tải lớn hơn lên database đang gặp sự cố. Cần phân loại lỗi theo SQLState, vendor code hoặc exception của driver và đặt giới hạn phù hợp.

## 9. Kiểm thử vòng đời database qua checkpoint–restore

Một bài kiểm thử tốt phải chứng minh kết nối cũ được đóng, pool mới được tạo và ứng dụng thật sự truy vấn được database sau restore.

Có thể kiểm thử theo chuỗi:

1. Khởi chạy ứng dụng và xác nhận pool ban đầu hoạt động.
2. Thực hiện một truy vấn kiểm tra và ghi nhận connection/pool state.
3. Tạo tải nhỏ để xác nhận traffic gate có thể drain request.
4. Yêu cầu checkpoint; xác nhận worker đã dừng và pool cũ được đóng.
5. Restore image trên môi trường tương thích.
6. Xác nhận `afterRestore` tạo pool mới.
7. Kiểm tra `Connection.isValid` hoặc truy vấn nhẹ.
8. Gọi repository thực tế và xác nhận kết quả đúng.
9. Xác nhận traffic chỉ được resume sau khi database readiness thành công.
10. Thử database không sẵn sàng, credential hết hạn hoặc pool creation thất bại; xác nhận instance không nhận traffic.

Nên thu thập các chỉ số:

| Chỉ số | Ý nghĩa |
|---|---|
| Số connection trước checkpoint | Xác nhận pool có connection đang được quản lý |
| Số transaction còn mở | Phát hiện công việc chưa đạt ranh giới an toàn |
| Thời gian drain | Đo thời gian chờ request/worker kết thúc |
| Thời gian đóng pool | Đo chi phí giải phóng kết nối |
| Thời gian tạo pool sau restore | Đo chi phí tái lập database access |
| Kết quả validation/query | Xác nhận kết nối thật sự dùng được |
| Restore đến readiness | Đo thời gian instance có thể phục vụ traffic |
| Số lần retry và loại lỗi | Chẩn đoán database hoặc mạng chưa sẵn sàng |

Không chỉ kiểm tra log “pool created”. Một pool object có thể được tạo nhưng chưa mở được connection. Hãy thực hiện validation hoặc truy vấn thật trước khi chuyển readiness.

## 10. Những lỗi thường gặp

**Giữ JDBC connection qua checkpoint.** Object Java còn tồn tại không có nghĩa session database và socket còn hợp lệ. Hãy đóng connection trước checkpoint và tạo connection mới sau restore.

**Đóng pool khi request còn đang chạy.** Request có thể lỗi giữa transaction hoặc khi đang dùng statement. Hãy ngừng nhận việc mới và drain công việc trước khi đóng pool.

**Chỉ gọi `Connection.close()` mà không đóng pool.** Connection pool còn thread, socket và connection khác. Hãy gọi API shutdown của pool theo hướng dẫn thư viện.

**Cố tái sử dụng pool đã đóng.** Một số pool như HikariCP không được thiết kế để mở lại sau `close()`. Hãy tạo instance pool mới và chuyển repository sang target mới.

**Checkpoint khi transaction đang mở.** Transaction có thể bị timeout hoặc rollback trong thời gian image được lưu. Hãy commit hoặc rollback trước checkpoint.

**Dùng lại credential cũ sau restore.** Token hoặc password có thể hết hạn hoặc đã được xoay vòng. Hãy lấy credential hiện hành khi tạo pool mới.

**Đánh dấu readiness ngay khi pool object được tạo.** Chỉ báo sẵn sàng sau khi lấy được connection và kiểm tra database thành công.

**Retry không giới hạn.** Retry liên tục có thể gây quá tải database. Dùng timeout, backoff, jitter và phân loại lỗi.

**Để nhiều instance restore tạo quá nhiều kết nối đồng thời.** Tính connection budget, giới hạn pool size và điều tiết startup để không vượt giới hạn database.

**Dùng policy FD thay cho lifecycle database.** `jdk.crac.resource-policies` có thể hỗ trợ một số FD theo phạm vi runtime, nhưng không xử lý transaction, session database hoặc trạng thái connection pool. Hãy quản lý database qua callback và API của pool.

## 11. Tự kiểm tra mức độ hiểu

1. **Vì sao không nên giữ JDBC connection qua checkpoint?** Vì session và socket thuộc hệ thống bên ngoài có thể hết hiệu lực trong lúc tiến trình được lưu; object `Connection` còn trong heap không bảo đảm kết nối còn dùng được.
2. **Cần làm gì trước khi đóng connection pool?** Ngừng nhận việc mới, drain request/worker, hoàn tất hoặc rollback transaction và đóng các statement/session thuộc quyền sở hữu.
3. **Sau restore nên dùng lại pool đã đóng không?** Thông thường cần tạo pool mới theo API của thư viện, ví dụ tạo `HikariDataSource` instance mới.
4. **`Connection.isValid(5)` xác nhận điều gì?** Nó yêu cầu JDBC driver kiểm tra connection còn hợp lệ trong timeout tối đa được chỉ định; vẫn cần kiểm tra các quyền và thao tác nghiệp vụ mà ứng dụng phụ thuộc.
5. **Khi nào readiness nên chuyển sang thành công?** Sau khi pool mới được tạo, lấy được connection, validation/query bắt buộc thành công và các thành phần phụ thuộc đã phục hồi.
6. **Vì sao factory tạo pool cần lấy credential hiện hành?** Vì secret, token hoặc endpoint có thể thay đổi hoặc hết hạn trong thời gian checkpoint image được lưu.
7. **Vì sao không được đóng pool khi transaction còn chạy?** Vì request có thể thất bại giữa chừng, giữ lock hoặc tạo trạng thái nghiệp vụ không nhất quán.

## Kết luận

Kết nối database là tài nguyên gắn với cả tiến trình lẫn hệ thống bên ngoài. Trước checkpoint, hãy dừng công việc mới, drain request đang chạy, hoàn tất transaction và đóng connection pool. Sau restore, lấy cấu hình và credential hiện hành, tạo pool mới, kiểm tra kết nối thực tế rồi mới cho repository, worker và traffic tiếp tục hoạt động.

Trong ứng dụng CRaC, hãy đặt vòng đời database vào `Resource` hoặc một coordinator phù hợp, bảo đảm các thành phần phụ thuộc được dừng trước pool và chỉ được mở lại sau khi pool sẵn sàng. Kiểm thử cả trường hợp thành công lẫn database/credential không sẵn sàng để readiness luôn phản ánh đúng khả năng phục vụ của instance.
