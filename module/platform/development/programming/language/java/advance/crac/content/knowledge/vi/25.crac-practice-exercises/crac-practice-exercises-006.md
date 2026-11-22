# Khôi phục ứng dụng JDBC khi nhóm kết nối cũ đã hết hiệu lực

Khi Java application được khôi phục từ CRaC checkpoint, các object Java trong heap có thể vẫn tồn tại, nhưng kết nối JDBC mà chúng đại diện có thể đã mất hiệu lực. Trong lúc JVM dừng, database có thể đóng session vì idle timeout, firewall có thể loại bỏ TCP connection, credential có thể được xoay vòng, proxy có thể đổi backend hoặc database có thể restart. Một `Connection` object còn trong memory không chứng minh socket và session phía server vẫn dùng được.

Cách xử lý an toàn là coi JDBC connection và connection pool là resource gắn với môi trường đang chạy. Trước checkpoint, ứng dụng ngừng nhận công việc mới, hoàn tất transaction đang chạy và đóng các connection cũ. Sau restore, ứng dụng tạo connection pool mới từ cấu hình và credential hiện hành, xác minh kết nối tới database, rồi mới mở readiness và resume các worker phụ thuộc JDBC.

Bài thực hành này xây dựng quy trình đó với JDBC và HikariCP, giải thích cách tích hợp vào Spring lifecycle hoặc CRaC Resource, cách xử lý connection stale, transaction đang mở, credential rotation, reconnect retry và kiểm thử khi database thay đổi trong thời gian checkpoint.

## 1. Vì sao connection cũ không còn đáng tin cậy?

CRaC khôi phục trạng thái process, bao gồm object Java và heap. Database là một hệ thống độc lập và vẫn tiếp tục hoạt động trong khoảng thời gian JVM không chạy. TCP socket, database session, transaction và server-side resource không tự động được tái lập chỉ vì JVM đã được restore.

Một chu trình thường gặp:

~~~text
JVM đang chạy
    │
    ▼
Ứng dụng mượn Connection từ pool
    │
    ▼
beforeCheckpoint
    ├── Ngừng nhận công việc JDBC mới
    ├── Drain transaction đang chạy
    └── Đóng connection pool
    │
    ▼
CRaC tạo checkpoint
    │
    │  JVM tạm dừng; database và network vẫn hoạt động
    │
    ├── Database restart hoặc failover
    ├── Firewall/proxy hết hạn TCP session
    ├── Credential được rotate
    └── Server đóng idle connection
    │
    ▼
CRaC restore JVM
    │
    ▼
afterRestore
    ├── Đọc config/credential hiện hành
    ├── Tạo pool mới
    ├── Mở connection mới
    ├── Validate connection
    └── Mở lại admission/readiness
    │
    ▼
Ứng dụng nhận request JDBC
~~~

Nếu checkpoint được tạo khi pool vẫn chứa connection, object pool và wrapper `Connection` có thể được phục hồi cùng heap. Nhưng file descriptor/socket và session phía server có thể không còn tương ứng với trạng thái trong JVM. Việc gọi lại connection cũ có thể gây `SQLException`, lỗi I/O, socket reset, lỗi transaction hoặc hành vi phụ thuộc driver.

CRaC yêu cầu ứng dụng phối hợp vòng đời của resource không thể được mang nguyên trạng qua checkpoint, ví dụ socket và database connection. Hãy đóng chúng trước checkpoint và tạo lại sau restore. Tham khảo [CRaC: Integrating CRaC in your Application](https://docs.azul.com/crac/usage/integrating-crac) và [CRaC: Implementing the CRaC API](https://crac.org/use/implement-crac/).

### 1.1. Những thành phần JDBC có thể bị ảnh hưởng

| Thành phần | Vì sao có thể stale | Cách xử lý |
|---|---|---|
| `Connection` | TCP socket hoặc server session đã bị đóng | Đóng và lấy connection mới |
| `PreparedStatement` | Gắn với connection/session cũ | Tạo lại sau khi lấy connection mới |
| `ResultSet` | Cursor phụ thuộc session và transaction | Đóng trước checkpoint; truy vấn lại sau restore |
| Transaction | Lock, snapshot và server transaction không thể tiếp tục an toàn | Commit hoặc rollback trước checkpoint |
| Connection pool | Có thể chứa connection wrapper trỏ tới socket cũ | Drain và đóng pool; tạo pool mới |
| Database metadata/cache | Có thể phản ánh schema hoặc endpoint cũ | Refresh nếu môi trường có thể thay đổi |
| JDBC driver state | Có thể giữ native/socket resource hoặc background thread | Theo hướng dẫn driver; khởi tạo lại nếu cần |
| XA/JTA resource | Transaction coordinator và resource manager có trạng thái riêng | Không checkpoint giữa transaction; dùng recovery protocol của transaction manager |

Không cố giữ transaction mở xuyên qua checkpoint. Checkpoint không phải cơ chế serialize transaction của database.

### 1.2. `isClosed()` không xác minh được connection còn sống

JDBC có hai phương thức thường bị nhầm lẫn:

- `Connection.isClosed()` cho biết connection object đã bị đóng theo trạng thái JDBC hay chưa.
- `Connection.isValid(timeout)` yêu cầu driver xác minh connection còn hợp lệ, bằng query hoặc cơ chế tương đương.

Một connection có thể trả `false` từ `isClosed()` nhưng socket đã bị peer đóng hoặc đường mạng đã mất. Java API nêu rõ `isClosed()` không nên được dùng để xác định một connection có còn hợp lệ hay không. Dùng `isValid(timeout)` hoặc validation mechanism do pool/driver cung cấp. [Java JDBC `Connection` API](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Connection.html).

## 2. Mục tiêu của bài thực hành

Sau khi hoàn thành bài này, ứng dụng cần đáp ứng các điều kiện:

1. Không có request hoặc worker mới bắt đầu transaction khi checkpoint preparation đã bắt đầu.
2. Transaction đang chạy được hoàn tất trong một deadline hữu hạn.
3. Không còn connection mượn từ pool trước khi pool bị đóng.
4. Pool cũ được đóng và không được sử dụng lại sau restore.
5. Pool mới lấy cấu hình và credential theo chính sách hiện hành.
6. Kết nối mới được xác minh trước khi ứng dụng nhận traffic.
7. Nếu database tạm thời unavailable, ứng dụng giữ readiness ở trạng thái từ chối traffic và retry có giới hạn.
8. Worker và scheduler chỉ resume sau khi datasource đã sẵn sàng.
9. Nếu checkpoint preparation thất bại, ứng dụng có recovery path để tiếp tục chạy hoặc báo lỗi rõ ràng.
10. Không có hai thành phần cùng sở hữu lifecycle của một connection pool.

Phần code bên dưới là mẫu minh họa cho một ứng dụng dùng HikariCP. Hãy điều chỉnh theo phiên bản HikariCP, JDBC driver, Spring Framework và JDK CRaC thực tế.

## 3. Chuẩn bị JDBC và HikariCP

Ví dụ sử dụng:

- Java với JDK có CRaC support.
- JDBC driver phù hợp database.
- HikariCP làm connection pool.
- Spring JDBC hoặc JDBC thuần để truy cập dữ liệu.
- CRaC API `org.crac` nếu ứng dụng tự đăng ký resource.

Các dependency minh họa cho Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.crac</groupId>
        <artifactId>crac</artifactId>
        <version>1.5.0</version>
    </dependency>

    <dependency>
        <groupId>com.zaxxer</groupId>
        <artifactId>HikariCP</artifactId>
        <version>6.3.0</version>
    </dependency>

    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-jdbc</artifactId>
        <version>6.2.0</version>
    </dependency>
</dependencies>
~~~

Đây là phiên bản ví dụ để minh họa cách khai báo. Chọn phiên bản tương thích với JDK, Spring Boot BOM, JDBC driver và runtime trong dự án. Với Spring Boot, ưu tiên dependency management do Spring Boot cung cấp thay vì tự ghim phiên bản từng thư viện.

### 3.1. Cấu hình pool

Một cấu hình HikariCP có thể bắt đầu như sau:

~~~java
HikariConfig config = new HikariConfig();

config.setJdbcUrl(jdbcUrl);
config.setUsername(username);
config.setPassword(password);

config.setPoolName("orders-db-pool");
config.setMaximumPoolSize(20);
config.setMinimumIdle(2);

config.setConnectionTimeout(5_000);
config.setValidationTimeout(3_000);

config.setMaxLifetime(25 * 60_000L);
config.setKeepaliveTime(2 * 60_000L);
~~~

Các thuộc tính có ý nghĩa khác nhau:

- `maximumPoolSize`: giới hạn tổng số connection trong pool.
- `minimumIdle`: số connection idle mà pool cố gắng duy trì.
- `connectionTimeout`: thời gian tối đa chờ mượn connection.
- `validationTimeout`: thời gian tối đa cho validation.
- `maxLifetime`: tuổi tối đa của một connection trong pool.
- `keepaliveTime`: chu kỳ keepalive cho connection idle.

`maxLifetime` nên ngắn hơn giới hạn tuổi connection do database hoặc hạ tầng áp đặt. `keepaliveTime` giúp kiểm tra/giữ connection idle trong lúc JVM đang chạy. Hai thuộc tính này không thay thế việc đóng và tạo lại pool sau một khoảng checkpoint dài. Trong thời gian JVM bị dừng, scheduler của pool không thể bảo đảm thực hiện keepalive đúng hạn.

## 4. Thiết kế DataSource có thể thay pool

`HikariDataSource` sau khi `close()` được xem là đã shutdown. Không nên đóng pool rồi cố gọi `getConnection()` trên chính object cũ. Cần tạo một instance Hikari mới sau restore.

Một cách tổ chức là đặt một `DataSource` wrapper trước pool thật. Các repository và `JdbcTemplate` chỉ nhìn thấy wrapper; lifecycle manager có thể detach pool cũ và install pool mới mà không phải thay toàn bộ dependency injection graph.

### 4.1. ReloadableDataSource

Ví dụ sau triển khai các phương thức chính của `DataSource` và chuyển tiếp lời gọi sang delegate hiện tại:

~~~java
package com.example.jdbc;

import javax.sql.DataSource;
import java.io.PrintWriter;
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import java.util.concurrent.atomic.AtomicReference;
import java.util.logging.Logger;

public final class ReloadableDataSource implements DataSource {

    private final AtomicReference<DataSource> delegate =
            new AtomicReference<>();

    public void install(DataSource replacement) {
        if (replacement == null) {
            throw new IllegalArgumentException(
                    "replacement must not be null");
        }

        if (!delegate.compareAndSet(null, replacement)) {
            throw new IllegalStateException(
                    "A JDBC pool is already installed");
        }
    }

    public DataSource detach() {
        return delegate.getAndSet(null);
    }

    public boolean isInstalled() {
        return delegate.get() != null;
    }

    private DataSource current() throws SQLException {
        DataSource current = delegate.get();

        if (current == null) {
            throw new SQLException(
                    "JDBC DataSource is unavailable during lifecycle transition");
        }

        return current;
    }

    @Override
    public Connection getConnection() throws SQLException {
        return current().getConnection();
    }

    @Override
    public Connection getConnection(
            String username,
            String password) throws SQLException {

        return current().getConnection(username, password);
    }

    @Override
    public PrintWriter getLogWriter() throws SQLException {
        return current().getLogWriter();
    }

    @Override
    public void setLogWriter(PrintWriter out) throws SQLException {
        current().setLogWriter(out);
    }

    @Override
    public void setLoginTimeout(int seconds) throws SQLException {
        current().setLoginTimeout(seconds);
    }

    @Override
    public int getLoginTimeout() throws SQLException {
        return current().getLoginTimeout();
    }

    @Override
    public Logger getParentLogger()
            throws SQLFeatureNotSupportedException {

        DataSource current = delegate.get();

        if (current == null) {
            throw new SQLFeatureNotSupportedException(
                    "JDBC DataSource is unavailable");
        }

        return current.getParentLogger();
    }

    @Override
    public <T> T unwrap(Class<T> iface) throws SQLException {
        if (iface.isInstance(this)) {
            return iface.cast(this);
        }

        return current().unwrap(iface);
    }

    @Override
    public boolean isWrapperFor(Class<?> iface) throws SQLException {
        return iface.isInstance(this) || current().isWrapperFor(iface);
    }
}
~~~

Wrapper này cung cấp một điểm truy cập ổn định cho repository. Khi `delegate` là `null`, mọi yêu cầu lấy connection mới đều thất bại rõ ràng thay vì vô tình dùng pool cũ.

Lưu ý: `AtomicReference` chỉ giúp thay delegate an toàn ở mức tham chiếu. Nó không tự drain connection đang được mượn. Trước khi gọi `detach()`, ứng dụng vẫn phải ngừng admission và chờ mọi transaction/connection borrower hoàn tất. Không swap pool trong khi request đang sử dụng connection cũ.

### 4.2. Cấu hình repository sử dụng wrapper

Trong Spring, có thể inject wrapper làm datasource chính:

~~~java
@Configuration
public class JdbcConfiguration {

    @Bean
    public ReloadableDataSource reloadableDataSource() {
        return new ReloadableDataSource();
    }

    @Bean
    public JdbcTemplate jdbcTemplate(
            ReloadableDataSource dataSource) {

        return new JdbcTemplate(dataSource);
    }
}
~~~

Các repository dùng `JdbcTemplate` hoặc `DataSource` được inject từ Spring. Chúng không giữ một reference trực tiếp tới `HikariDataSource`.

Nếu dùng `DataSourceTransactionManager` hoặc `JdbcTransactionManager`, hãy cấu hình nó với cùng `ReloadableDataSource`. Transaction manager cần nhìn thấy datasource ổn định; việc thay pool chỉ diễn ra khi không còn transaction active.

## 5. Ngừng transaction mới và drain connection đang sử dụng

Trước khi đóng pool, phải ngăn request mới và worker mới bắt đầu công việc JDBC. Nếu chỉ gọi `HikariDataSource.close()` trong khi transaction đang chạy, ứng dụng có thể mất connection giữa một thao tác nghiệp vụ.

Một admission gate đơn giản có thể đếm số công việc JDBC đang hoạt động:

~~~java
package com.example.jdbc;

import java.time.Duration;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public final class JdbcAdmissionGate {

    private final ReentrantLock lock = new ReentrantLock();
    private final Condition drained = lock.newCondition();

    private boolean accepting = true;
    private int activeOperations;

    public boolean enter() {
        lock.lock();
        try {
            if (!accepting) {
                return false;
            }

            activeOperations++;
            return true;
        } finally {
            lock.unlock();
        }
    }

    public void exit() {
        lock.lock();
        try {
            if (activeOperations <= 0) {
                throw new IllegalStateException(
                        "No active JDBC operation to exit");
            }

            activeOperations--;

            if (activeOperations == 0) {
                drained.signalAll();
            }
        } finally {
            lock.unlock();
        }
    }

    public void pauseAndDrain(Duration timeout)
            throws InterruptedException, TimeoutException {

        long budget = timeout.toNanos();
        if (budget <= 0) {
            throw new IllegalArgumentException(
                    "timeout must be positive");
        }

        long started = System.nanoTime();

        lock.lockInterruptibly();
        try {
            accepting = false;

            while (activeOperations > 0) {
                long remaining =
                        budget - (System.nanoTime() - started);

                if (remaining <= 0) {
                    accepting = true;
                    drained.signalAll();

                    throw new TimeoutException(
                            "JDBC operations did not drain in time");
                }

                drained.awaitNanos(remaining);
            }
        } catch (InterruptedException interrupted) {
            accepting = true;
            drained.signalAll();
            Thread.currentThread().interrupt();
            throw interrupted;
        } finally {
            lock.unlock();
        }
    }

    public void resume() {
        lock.lock();
        try {
            accepting = true;
            drained.signalAll();
        } finally {
            lock.unlock();
        }
    }

    public int activeOperations() {
        lock.lock();
        try {
            return activeOperations;
        } finally {
            lock.unlock();
        }
    }
}
~~~

Mọi đường xử lý JDBC cần đi qua gate và phải gọi `exit()` trong `finally`:

~~~java
public Order loadOrder(long id) {
    if (!jdbcGate.enter()) {
        throw new ServiceUnavailableException(
                "JDBC operations are paused");
    }

    try {
        return orderRepository.findById(id)
                .orElseThrow(OrderNotFoundException::new);
    } finally {
        jdbcGate.exit();
    }
}
~~~

Ví dụ này giả định gate bao phủ toàn bộ đơn vị công việc giữ transaction/connection. Nếu một request gọi nhiều repository trong cùng transaction, hãy đặt gate ở ranh giới transaction hoặc service operation để bộ đếm chỉ tăng/giảm đúng một lần cho toàn bộ công việc.

Không chỉ gate HTTP request. Message listener, scheduler, `@Async` task và worker thread cũng phải dừng admission. Readiness false không tự dừng background work.

### 5.1. Vì sao cần drain trước khi đóng pool?

Khi checkpoint được tạo, ứng dụng không nên còn:

- Transaction chưa commit/rollback.
- Connection đang được mượn.
- Prepared statement hoặc ResultSet còn mở.
- Cursor phía database còn hoạt động.
- Batch update đang thực hiện.
- Message acknowledgement phụ thuộc transaction JDBC.
- Worker đang giữ lock nghiệp vụ hoặc database lock.

Nếu drain không hoàn tất trong deadline, từ chối checkpoint. Không đóng pool để ép transaction kết thúc trừ khi ứng dụng đã có recovery semantics rõ ràng.

## 6. Quản lý pool bằng CRaC Resource

Sau khi có wrapper và admission gate, tạo một resource chịu trách nhiệm đóng pool cũ trước checkpoint và tạo pool mới sau restore.

Ví dụ:

~~~java
package com.example.jdbc;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;
import org.springframework.stereotype.Component;

import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.SQLException;
import java.time.Duration;
import java.util.function.Supplier;

@Component
public final class JdbcPoolCracResource implements Resource {

    private final ReloadableDataSource dataSource;
    private final JdbcAdmissionGate gate;
    private final Supplier<HikariConfig> configSupplier;

    public JdbcPoolCracResource(
            ReloadableDataSource dataSource,
            JdbcAdmissionGate gate,
            Supplier<HikariConfig> configSupplier) {

        this.dataSource = dataSource;
        this.gate = gate;
        this.configSupplier = configSupplier;

        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {

        gate.pauseAndDrain(Duration.ofSeconds(20));

        DataSource old = dataSource.detach();

        if (old instanceof HikariDataSource hikari) {
            hikari.close();
        }
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {

        HikariDataSource replacement = null;

        try {
            HikariConfig config = configSupplier.get();
            replacement = new HikariDataSource(config);

            validate(replacement);

            dataSource.install(replacement);
            replacement = null;

            gate.resume();

        } catch (Exception failure) {
            if (replacement != null) {
                replacement.close();
            }

            // Giữ datasource unavailable và gate đóng.
            throw failure;
        }
    }

    private void validate(HikariDataSource candidate)
            throws SQLException {

        try (Connection connection = candidate.getConnection()) {
            if (!connection.isValid(5)) {
                throw new SQLException(
                        "Database connection validation failed");
            }
        }
    }
}
~~~

Trong ví dụ, cần import `javax.sql.DataSource` cho biến `old`. Phần tạo Hikari config phải lấy JDBC URL, username, password và các thuộc tính khác từ configuration provider của ứng dụng.

Các điểm quan trọng:

1. `beforeCheckpoint` đóng admission và đợi operation đang chạy kết thúc.
2. Pool cũ được detach khỏi wrapper.
3. Pool cũ được close; wrapper không còn cấp connection mới.
4. `afterRestore` tạo một `HikariDataSource` instance mới.
5. Candidate pool được xác minh bằng connection thật.
6. Chỉ sau validation mới install pool vào wrapper.
7. Admission gate chỉ resume sau khi pool đã sẵn sàng.
8. Nếu reconnect thất bại, pool candidate bị đóng, wrapper vẫn unavailable và callback báo lỗi.

Đây là skeleton thể hiện thứ tự lifecycle. Trong code thực tế, hãy xử lý thêm trường hợp checkpoint bị từ chối sau khi pool đã được detach: ứng dụng có thể cần tạo lại pool và resume gate theo recovery policy. Không mặc định `beforeCheckpoint` thất bại sẽ tự động gọi `afterRestore`.

### 6.1. Không đăng ký trùng lifecycle owner

Nếu Spring Framework đã quản lý một bean `Lifecycle` để dừng và khởi động lại datasource, không đồng thời đăng ký một `org.crac.Resource` khác cũng đóng/mở cùng pool. Chọn một nơi làm owner cho pool lifecycle.

Spring Framework hỗ trợ checkpoint/restore bằng cách dừng các bean đang chạy theo `Lifecycle` trước checkpoint và start lại sau restore. Các thư viện không tích hợp Spring có thể được quản lý bằng custom `org.crac.Resource`. Tham khảo [Spring Framework: JVM Checkpoint Restore](https://docs.spring.io/spring-framework/reference/integration/checkpoint-restore.html).

### 6.2. Tạo pool mới từ cấu hình hiện hành

Không lưu password hoặc token trực tiếp trong `HikariConfig` rồi giả định giá trị trong checkpoint luôn còn hợp lệ. Sau restore, configuration supplier nên đọc secret/config theo chính sách hiện tại.

Ví dụ:

~~~java
@Bean
Supplier<HikariConfig> hikariConfigSupplier(
        JdbcProperties properties,
        SecretProvider secretProvider) {

    return () -> {
        HikariConfig config = new HikariConfig();

        config.setJdbcUrl(properties.jdbcUrl());
        config.setUsername(secretProvider.username());
        config.setPassword(secretProvider.password());

        config.setMaximumPoolSize(properties.maximumPoolSize());
        config.setConnectionTimeout(5_000);
        config.setValidationTimeout(3_000);

        return config;
    };
}
~~~

Nếu secret provider không truy cập được, không tạo pool với credential cũ như fallback ngầm. Hãy giữ readiness false và áp dụng retry có giới hạn hoặc báo lỗi cấu hình.

## 7. Validation connection sau restore

Sau khi tạo pool mới, cần xác minh rằng database thực sự chấp nhận kết nối.

### 7.1. Dùng `Connection.isValid(timeout)`

~~~java
try (Connection connection = dataSource.getConnection()) {
    if (!connection.isValid(5)) {
        throw new SQLException("Connection is not valid");
    }
}
~~~

Tham số timeout của `isValid` tính bằng giây. Driver phải gửi query hoặc sử dụng một cơ chế tích cực để xác minh connection. Nếu driver không hỗ trợ hoặc có behavior riêng, kiểm tra tài liệu driver.

### 7.2. Validation query

Một số driver hoặc pool configuration có thể dùng query kiểm tra:

~~~sql
SELECT 1
~~~

Query cụ thể phụ thuộc database. Hãy chọn một câu lệnh nhẹ, không sửa dữ liệu và không yêu cầu quyền ngoài quyền ứng dụng.

HikariCP ưu tiên JDBC4 `Connection.isValid()` khi driver hỗ trợ. Chỉ cấu hình `connectionTestQuery` khi driver cần cách validation đó. Không chạy query nặng hoặc truy cập bảng nghiệp vụ chỉ để health check.

### 7.3. Không dựa vào `isClosed()`

Ví dụ sau không đủ:

~~~java
if (!connection.isClosed()) {
    // Không thể kết luận database session vẫn sống.
}
~~~

`isClosed()` chủ yếu phản ánh trạng thái đóng của object theo JDBC. Nó không bắt buộc kiểm tra socket/peer. Dùng `isValid(timeout)` hoặc để pool xác thực connection theo policy.

### 7.4. Validation khi mượn connection

Sau restore, pool có thể tạo connection theo nhu cầu thay vì mở toàn bộ `maximumPoolSize` ngay lập tức. Điều này tránh tạo connection burst tới database. Tuy nhiên, request đầu tiên chỉ nên được nhận sau khi ít nhất một connection test thành công và readiness policy đã được đáp ứng.

Nếu cần warm-up nhiều connection, hãy giới hạn concurrency và dùng timeout. Không mở đồng thời toàn bộ pool trên tất cả replica nếu database có connection limit thấp.

## 8. HikariCP settings và giới hạn của keepalive

Một số thuộc tính HikariCP giúp xử lý connection bị đóng trong lúc ứng dụng đang hoạt động:

| Thuộc tính | Mục đích | Giới hạn |
|---|---|---|
| `maxLifetime` | Loại connection quá tuổi khỏi pool | Không làm connection cũ sống lại sau checkpoint |
| `keepaliveTime` | Kiểm tra/giữ idle connection hoạt động | Chỉ chạy khi JVM/pool đang hoạt động |
| `connectionTimeout` | Giới hạn thời gian chờ mượn connection | Không sửa lỗi credential hoặc endpoint |
| `validationTimeout` | Giới hạn thời gian validation | Phải thấp hơn connection timeout theo yêu cầu Hikari |
| `idleTimeout` | Loại bỏ connection idle dư thừa | Không thay thế checkpoint lifecycle |
| `leakDetectionThreshold` | Phát hiện connection bị giữ quá lâu | Chẩn đoán leak, không phải cơ chế phục hồi |

HikariCP dùng `maxLifetime` để retire connection theo tuổi; connection đang được mượn không bị loại giữa chừng chỉ vì đạt tuổi tối đa. `keepaliveTime` áp dụng với connection idle. Do JVM không chạy trong thời gian checkpoint, các tác vụ định kỳ trong pool không thể thay thế callback CRaC. Xem [HikariCP configuration](https://github.com/brettwooldridge/HikariCP#frequently-used).

Một cấu hình ví dụ:

~~~yaml
app:
  jdbc:
    maximum-pool-size: 20
    minimum-idle: 2
    connection-timeout: 5s
    validation-timeout: 3s
    max-lifetime: 25m
    keepalive-time: 2m
~~~

Các giá trị chỉ để minh họa. `maxLifetime` nên ngắn hơn giới hạn do database/proxy áp đặt; `keepaliveTime` phải nhỏ hơn `maxLifetime` nếu cả hai được bật. Đo tải thực tế và kiểm tra cấu hình HikariCP của đúng version.

## 9. Tích hợp với Spring Framework và Spring Boot

Nếu ứng dụng dùng Spring, cần xác định checkpoint mode trước khi chọn lifecycle hook.

### 9.1. On-demand checkpoint/restore

Với on-demand checkpoint/restore, Spring Framework dừng các bean đang chạy theo `Lifecycle` trước checkpoint. Sau restore, Spring start lại các bean đó. Các resource có thể được quản lý thông qua `Lifecycle.stop()` và `Lifecycle.start()`.

Có thể triển khai `SmartLifecycle` cho component quản lý JDBC:

~~~java
@Component
public final class JdbcPoolLifecycle implements SmartLifecycle {

    private final ReloadableDataSource dataSource;
    private final JdbcAdmissionGate gate;
    private final Supplier<HikariConfig> configSupplier;

    private volatile boolean running;

    public JdbcPoolLifecycle(
            ReloadableDataSource dataSource,
            JdbcAdmissionGate gate,
            Supplier<HikariConfig> configSupplier) {

        this.dataSource = dataSource;
        this.gate = gate;
        this.configSupplier = configSupplier;
    }

    @Override
    public void start() {
        if (running) {
            return;
        }

        HikariDataSource replacement =
                new HikariDataSource(configSupplier.get());

        try {
            validate(replacement);
            dataSource.install(replacement);
            running = true;
            gate.resume();
        } catch (Exception failure) {
            replacement.close();
            throw new IllegalStateException(
                    "Could not restore JDBC pool", failure);
        }
    }

    @Override
    public void stop() {
        if (!running) {
            return;
        }

        try {
            gate.pauseAndDrain(Duration.ofSeconds(20));

            DataSource old = dataSource.detach();
            if (old instanceof HikariDataSource hikari) {
                hikari.close();
            }

            running = false;
        } catch (Exception failure) {
            throw new IllegalStateException(
                    "Could not prepare JDBC pool for checkpoint",
                    failure);
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return 0;
    }

    private void validate(HikariDataSource candidate)
            throws SQLException {

        try (Connection connection = candidate.getConnection()) {
            if (!connection.isValid(5)) {
                throw new SQLException(
                        "Database connection validation failed");
            }
        }
    }
}
~~~

Ví dụ cần được đặt đúng thứ tự lifecycle so với worker và scheduler. Worker phải dừng trước khi JDBC pool đóng; khi restore, pool phải sẵn sàng trước khi worker resume. Có thể điều chỉnh `getPhase()` để thể hiện quan hệ đó, sau khi kiểm tra thứ tự lifecycle trong ứng dụng.

`SmartLifecycle.stop()` không khai báo checked exception. Nếu stop thất bại, cần xác định rõ policy của framework và ứng dụng. Với resource cần báo lỗi trực tiếp qua CRaC callback, có thể dùng custom `org.crac.Resource` thay cho lifecycle bean.

### 9.2. Automatic checkpoint at startup

Spring Framework phân biệt automatic checkpoint trong giai đoạn refresh với on-demand checkpoint của một ứng dụng đã chạy. Automatic checkpoint xảy ra trước khi lifecycle bean bắt đầu hoạt động. Vì vậy, không thể giả định một pool đã được start rồi sẽ được stop/start theo cùng cách như on-demand checkpoint.

Nếu dùng automatic checkpoint, thiết kế datasource để không mở kết nối database quá sớm khi chưa cần thiết, hoặc xác định đúng phase khởi tạo resource. Sau restore, pool phải được tạo khi lifecycle bắt đầu và trước khi request cần JDBC được chấp nhận.

Spring Framework có mô tả rõ hai mode này trong [JVM Checkpoint Restore](https://docs.spring.io/spring-framework/reference/integration/checkpoint-restore.html).

### 9.3. Không dùng cả SmartLifecycle và Resource cho cùng pool

Một lỗi dễ gặp là:

- `SmartLifecycle.stop()` đóng Hikari pool.
- `org.crac.Resource.beforeCheckpoint()` cũng đóng Hikari pool.
- Sau restore, cả `Lifecycle.start()` và `Resource.afterRestore()` đều tạo pool mới.

Kết quả có thể là pool bị đóng hai lần, delegate bị ghi đè, pool cũ còn chạy hoặc hai pool cùng tồn tại. Chọn một lifecycle owner duy nhất. Coordinator khác có thể quản lý readiness/admission, nhưng không cùng sở hữu thao tác close/install pool.

## 10. Transaction manager và connection được bind theo thread

Spring JDBC transaction thường bind connection vào thread trong suốt transaction. Connection có thể được lấy khi transaction bắt đầu và trả về pool khi transaction kết thúc.

Trước checkpoint, phải bảo đảm:

- Không còn transaction đang active.
- Không có thread đang giữ connection trong `TransactionSynchronizationManager`.
- Không có `@Transactional` method đang chạy.
- Không có async task giữ transaction context bất hợp lệ.
- Không có batch/cursor operation đang mở.
- Transaction manager đã hoàn tất commit hoặc rollback.

Không cố serialize `TransactionStatus`, JDBC connection hoặc server transaction để tiếp tục sau restore. Nếu transaction chưa hoàn tất, hãy để operation kết thúc trước checkpoint. Nếu không thể hoàn tất trong thời gian cho phép, từ chối checkpoint và xử lý nghiệp vụ theo transaction policy.

Với distributed transaction/JTA/XA, recovery phụ thuộc transaction manager và resource manager. Không giả định CRaC checkpoint có thể thay thế transaction log hoặc XA recovery. Hãy dùng cơ chế recovery chính thức của transaction manager và không checkpoint khi transaction đang ở trạng thái in-doubt.

## 11. Credential rotation và cấu hình database thay đổi

Một lợi ích của việc tạo pool mới sau restore là có thể đọc credential hiện hành. Điều này quan trọng khi secret được rotate trong lúc JVM dừng.

Các thông tin nên đọc lại hoặc xác minh:

- JDBC URL và hostname.
- Username/password.
- IAM/database authentication token.
- TLS certificate và truststore.
- Client certificate/private key path.
- Proxy endpoint.
- Database name/schema.
- Connection properties.
- Pool size và timeout policy.

Không lưu secret value vào log hoặc metric. Chỉ log secret version/revision hoặc tên nguồn cấu hình nếu không nhạy cảm.

### 11.1. Token ngắn hạn

Nếu database dùng token ngắn hạn, không tạo pool bằng token được lưu trong checkpoint. `configSupplier` nên yêu cầu token mới khi `afterRestore` hoặc khi tạo connection.

Ví dụ:

~~~java
String token = tokenProvider.createDatabaseToken();

HikariConfig config = new HikariConfig();
config.setJdbcUrl(jdbcUrl);
config.setUsername(databaseUser);
config.setPassword(token);
~~~

Token có thể hết hạn ngay sau khi pool được tạo. Nếu driver hỗ trợ token refresh per connection, cấu hình theo cơ chế của driver. Nếu không, cần một chiến lược tạo lại pool trước khi token hết hạn. Không giả định thay password trên một `HikariConfig` đã khởi tạo sẽ tự thay credential của mọi connection hiện có.

### 11.2. TLS certificate và truststore

Nếu certificate được rotate trong thời gian checkpoint, tạo lại client/pool có thể cần reload SSL context hoặc cấu hình driver. Chỉ cập nhật file certificate trên disk chưa chắc làm SSL context đã khởi tạo trong heap tự thay đổi.

Hãy kiểm tra cách JDBC driver tạo TLS context. Nếu driver giữ SSL context hoặc socket factory trong singleton, cần tái tạo object tương ứng hoặc restart component theo lifecycle.

## 12. Retry khi database chưa sẵn sàng

Database có thể chưa sẵn sàng ngay khi application restore xong. Ví dụ database đang failover hoặc service endpoint chưa ổn định.

Một policy reconnect tốt cần:

- Timeout cho mỗi lần kết nối.
- Số lần retry hoặc tổng deadline.
- Exponential backoff.
- Jitter để tránh nhiều replica retry cùng thời điểm.
- Readiness giữ false trong khi dependency bắt buộc chưa hoạt động.
- Log reason đã chuẩn hóa.
- Không tạo pool mới lặp đi lặp lại mà không đóng pool candidate trước đó.

Ví dụ backoff:

~~~java
import java.util.concurrent.ThreadLocalRandom;

public void reconnectWithRetry(
        int maxAttempts,
        Duration initialDelay,
        Duration maxDelay) throws Exception {

    long delayMillis = initialDelay.toMillis();

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        try {
            installValidatedPool();
            return;
        } catch (Exception failure) {
            if (attempt == maxAttempts) {
                throw failure;
            }

            long jitter = ThreadLocalRandom.current()
                    .nextLong(Math.max(1, delayMillis / 4));

            Thread.sleep(delayMillis + jitter);

            delayMillis = Math.min(
                    delayMillis * 2,
                    maxDelay.toMillis());
        }
    }
}
~~~

Đây là ví dụ rút gọn. Trong production, nên dùng retry library hoặc scheduler có kiểm soát, giới hạn tổng thời gian và tôn trọng interrupt. `Thread.sleep()` trong CRaC callback sẽ kéo dài restore và có thể giữ JVM chưa Ready; nếu retry có thể kéo dài, cân nhắc để callback khởi tạo trạng thái reconnecting rồi chạy recovery worker riêng trong khi readiness vẫn false.

### 12.1. Phân biệt lỗi tạm thời và lỗi cấu hình

| Lỗi | Khả năng retry | Xử lý |
|---|---|---|
| Database failover đang diễn ra | Có | Retry với backoff |
| DNS tạm thời không phân giải | Có | Retry và theo dõi resolver |
| Connection refused | Có, nếu service đang restart | Retry trong deadline |
| Credential sai hoặc hết hạn | Không retry cùng credential | Lấy secret/token mới |
| Database user bị revoke | Không retry vô hạn | Báo lỗi cấu hình/quyền |
| JDBC URL sai | Không retry vô hạn | Dừng readiness và báo cấu hình |
| TLS certificate không tin cậy | Không retry cùng trust config | Sửa certificate/truststore |
| Connection limit đã đầy | Có giới hạn | Backoff, giảm concurrency và kiểm tra pool size |

Không retry vô hạn trong `afterRestore` nếu việc đó làm callback không bao giờ kết thúc. Hãy xác định một deadline restore và một chính sách vận hành rõ ràng cho dependency chưa sẵn sàng.

## 13. Readiness và background worker sau khi pool được khôi phục

Pool mới tạo thành công chưa chắc ứng dụng đã sẵn sàng. Readiness nên chỉ thành công sau khi:

1. Cấu hình JDBC được tải.
2. Credential/token hiện hành được lấy.
3. Pool mới được tạo.
4. Connection validation thành công.
5. Transaction manager và repository có thể sử dụng datasource.
6. Worker cần JDBC đã sẵn sàng để resume.

Với Spring Boot, dùng `ReadinessState.REFUSING_TRAFFIC` trong lúc phục hồi và chỉ chuyển sang `ACCEPTING_TRAFFIC` sau khi datasource và dependency bắt buộc hoạt động.

Ví dụ:

~~~java
publisher.publishEvent(
        new AvailabilityChangeEvent<>(
                this,
                ReadinessState.REFUSING_TRAFFIC));

// Tạo pool mới, validate và khôi phục worker bắt buộc.

publisher.publishEvent(
        new AvailabilityChangeEvent<>(
                this,
                ReadinessState.ACCEPTING_TRAFFIC));
~~~

Readiness của HTTP server không tự dừng scheduler hoặc message consumer. Cần gate riêng cho background worker. Nếu worker sử dụng JDBC, chỉ resume nó sau khi pool mới được install và validation thành công.

## 14. Xử lý `SQLException` sau restore

Một số exception thường gặp khi ứng dụng vô tình dùng connection cũ:

| Exception/SQLState | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `SQLNonTransientConnectionException` | Connection không thể tiếp tục sử dụng | Bỏ connection và tạo mới |
| `SQLRecoverableException` | Driver yêu cầu kết nối lại | Đóng connection cũ, lấy connection mới |
| `SQLTransientConnectionException` | Lỗi kết nối tạm thời | Retry theo policy và deadline |
| `Communications link failure` | Socket/network/server không còn kết nối | Kiểm tra endpoint, network và pool |
| `Connection reset` | Peer hoặc proxy đóng TCP session | Loại bỏ connection và reconnect |
| `Connection is closed` | Pool/driver đã đóng connection | Không dùng reference cũ |
| Authentication failure | Credential hết hạn hoặc bị rotate | Lấy credential mới |
| `Too many connections` | Nhiều pool/replica tạo connection cùng lúc | Kiểm tra pool size, rollout và connection limit |

SQLState và exception class phụ thuộc JDBC driver. Không phân loại mọi `SQLException` là lỗi retryable. Lỗi syntax, constraint violation hoặc permission denied thường cần xử lý khác với network interruption.

### 14.1. Không retry một transaction đã có side effect một cách mù quáng

Nếu connection mất giữa lúc gửi lệnh và lúc nhận kết quả, ứng dụng có thể không biết database đã commit hay chưa. Retry toàn bộ transaction có thể thực hiện side effect hai lần.

Đối với operation có side effect:

- Dùng idempotency key hoặc unique business key.
- Thiết kế transaction để có thể xác định trạng thái đã commit.
- Không tự động retry lệnh ghi khi kết quả commit không rõ.
- Dùng outbox/inbox hoặc cơ chế deduplication khi phù hợp.
- Phân biệt lỗi xảy ra trước khi gửi lệnh, trong lúc thực thi và sau khi commit.

CRaC restore không thay đổi semantics của transaction hoặc tính exactly-once của database/message broker.

## 15. Kiểm tra pool cũ đã thực sự bị loại bỏ

Sau khi restore, không để object graph vô tình giữ reference tới pool cũ.

Các nơi cần kiểm tra:

- Singleton repository/service có giữ trực tiếp `HikariDataSource` cũ.
- `JdbcTemplate` hoặc transaction manager có trỏ tới wrapper hay pool cụ thể.
- ThreadLocal có giữ connection.
- Async task có giữ connection/statement.
- Cache có lưu `Connection`, `PreparedStatement` hoặc `ResultSet`.
- Driver-specific object có giữ socket/session cũ.
- Health indicator có dùng datasource khác với datasource production.

Tất cả truy cập JDBC nên đi qua một datasource entry point có thể thay delegate. Không lưu connection vào field singleton hoặc tái sử dụng connection qua nhiều request.

### 15.1. Kiểm tra connection count

HikariCP có thể cung cấp metrics hoặc JMX cho:

- Active connection count.
- Idle connection count.
- Total connection count.
- Threads awaiting connection.

Sau restore, xác nhận pool mới có tên/identity mới hoặc generation mới trong log, số connection phù hợp và không còn borrower từ pool cũ. Không chỉ dựa vào số connection bằng 0; pool có thể lazy-create connection khi có request đầu tiên.

## 16. Kiểm thử tình huống database thay đổi trong checkpoint

Một bài test restore cần mô phỏng việc database thay đổi trong thời gian JVM không chạy.

### 16.1. Test cơ bản

1. Khởi động ứng dụng với JDBC pool.
2. Gửi một số request để tạo connection.
3. Xác nhận transaction hoàn tất và pool có connection idle.
4. Chuyển readiness sang từ chối traffic.
5. Dừng background worker và drain JDBC operation.
6. Tạo checkpoint bằng CRIU engine thật.
7. Khởi động lại từ checkpoint.
8. Xác nhận pool mới được tạo.
9. Xác nhận connection validation thành công.
10. Xác nhận readiness chuyển sang accepting traffic.
11. Gửi request JDBC và kiểm tra dữ liệu.

### 16.2. Database restart trong thời gian checkpoint

1. Tạo checkpoint sau khi ứng dụng đã drain và đóng pool.
2. Restart database hoặc database container.
3. Restore ứng dụng từ checkpoint.
4. Xác nhận ứng dụng tạo session mới.
5. Kiểm tra request JDBC thành công.
6. Xác nhận không có log sử dụng connection cũ.

Test này chứng minh ứng dụng không phụ thuộc vào session database tại thời điểm checkpoint.

### 16.3. Credential rotation

1. Tạo checkpoint.
2. Rotate password hoặc token của database user.
3. Restore ứng dụng.
4. Xác nhận `configSupplier` đọc credential mới.
5. Xác nhận pool mới kết nối thành công.
6. Xác nhận không log secret.
7. Kiểm tra readiness chỉ thành công sau validation.

Nếu ứng dụng dùng IAM token, mô phỏng token cũ hết hạn và xác nhận pool mới yêu cầu token mới.

### 16.4. Database unavailable sau restore

1. Tạo checkpoint hợp lệ.
2. Khi restore, chặn kết nối tới database.
3. Xác nhận pool creation/validation thất bại theo timeout.
4. Xác nhận wrapper không cấp pool cũ.
5. Xác nhận readiness vẫn false.
6. Khôi phục database.
7. Xác nhận retry tạo pool mới và readiness chuyển thành công.

Nếu retry không thành công trong deadline, kiểm tra recovery policy thay vì để callback chờ vô hạn.

### 16.5. Connection leak hoặc transaction không drain

1. Giữ một connection/transaction active trong staging.
2. Bắt đầu checkpoint.
3. Xác nhận admission gate ngừng task mới.
4. Xác nhận drain chờ transaction đang chạy.
5. Nếu quá deadline, xác nhận checkpoint bị từ chối.
6. Xác nhận ứng dụng rollback trạng thái pause và readiness/gate trở lại đúng policy.
7. Sửa leak và thử lại.

Không cố tạo checkpoint trong khi transaction vẫn giữ connection chỉ để làm test “pass”.

## 17. Chẩn đoán khi restore JDBC thất bại

Thu thập các thông tin sau:

- Checkpoint ID và restore operation ID.
- JDK vendor/version và JDBC driver version.
- Database engine/version và endpoint.
- Hikari pool name/generation.
- Pool active/idle/pending count.
- SQLState và exception class.
- Thời điểm bắt đầu reconnect và validation duration.
- Secret/config revision không nhạy cảm.
- CRaC callback log.
- Pod readiness và container restart events.
- Network/DNS/TLS diagnostics.

Các lệnh Kubernetes hữu ích:

~~~bash
kubectl logs <POD_NAME> -c app
kubectl logs <POD_NAME> -c app --previous
kubectl describe pod <POD_NAME>
kubectl get endpointslices \
  -l kubernetes.io/service-name=<SERVICE_NAME>
~~~

Nếu callback `afterRestore` không chạy, lỗi có thể nằm ở checkpoint engine hoặc JVM resume trước khi JDBC code hoạt động. Nếu callback chạy nhưng `getConnection()` timeout, kiểm tra database endpoint, credential, pool config và network. Nếu pool validation thành công nhưng request nghiệp vụ vẫn fail, kiểm tra transaction manager và code còn giữ reference tới datasource/connection cũ.

## 18. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Giữ pool cũ trong checkpoint | Connection trỏ tới socket/session hết hiệu lực | Đóng pool trước checkpoint và tạo instance mới |
| Chỉ kiểm tra `isClosed()` | Connection stale vẫn có thể được xem là mở | Dùng `isValid(timeout)` hoặc pool validation |
| Đóng pool khi transaction còn active | Request bị lỗi giữa nghiệp vụ | Gate admission và drain trước khi close |
| `DataSource` bean giữ trực tiếp Hikari instance cũ | Repository tiếp tục gọi pool đã đóng | Inject wrapper có thể thay delegate |
| Tạo pool mới nhưng không validate | Pod Ready khi database chưa truy cập được | Test connection trước khi install/readiness |
| Reuse password từ checkpoint | Credential đã rotate hoặc token hết hạn | Đọc secret/token mới sau restore |
| Chỉ dựa vào keepalive | Không xử lý được khoảng JVM bị dừng | Đóng/recreate pool theo CRaC lifecycle |
| Retry vô hạn trong callback | Restore không hoàn tất | Deadline, backoff và recovery policy |
| Worker resume trước pool | Task lỗi hàng loạt hoặc retry storm | Resume theo dependency order |
| Hai lifecycle owner cùng đóng pool | Double close hoặc pool mới bị ghi đè | Chọn một owner duy nhất |
| Health check chỉ kiểm tra object DataSource tồn tại | Readiness báo khỏe giả | Validate connection thật |
| Retry transaction ghi không idempotent | Side effect bị lặp | Thiết kế idempotency/reconciliation |

## 19. Quy trình vận hành đề xuất

Có thể tổ chức lifecycle theo sơ đồ:

~~~text
BEFORE CHECKPOINT
  1. Readiness = REFUSING_TRAFFIC
  2. Stop HTTP/background admission
  3. Pause scheduler/message consumer
  4. Drain active JDBC operations
  5. Commit/rollback transaction
  6. Detach and close old pool
  7. CRaC checkpoint
          │
          ▼
TIME JVM IS STOPPED
  - Database may restart/failover
  - Network sessions may expire
  - Credential may rotate
          │
          ▼
AFTER RESTORE
  1. Keep JDBC admission closed
  2. Load current config and credentials
  3. Create a new HikariDataSource
  4. Validate a fresh JDBC connection
  5. Install the new pool
  6. Resume required workers
  7. Readiness = ACCEPTING_TRAFFIC
          │
          ▼
NORMAL OPERATION
  - Monitor pool and query metrics
  - Retire stale connections
  - Keep transaction and retry policies explicit
~~~

Nếu database chưa sẵn sàng, dừng ở phase reconnect/validation, giữ readiness false và retry theo deadline. Không công bố Ready khi pool chỉ mới được tạo object nhưng chưa kết nối được.

## 20. Checklist trước khi triển khai production

- [ ] Mọi request/worker JDBC đều đi qua admission gate hoặc cơ chế quiesce tương đương.
- [ ] Transaction đang chạy được drain trước checkpoint.
- [ ] Không có connection, statement, result set hoặc cursor mở khi tạo checkpoint.
- [ ] Pool cũ được detach và close trước checkpoint.
- [ ] `DataSource` được inject qua wrapper có thể thay delegate.
- [ ] Pool mới được tạo từ cấu hình và credential hiện hành.
- [ ] Kết nối mới được validate bằng JDBC driver/pool.
- [ ] Readiness giữ false trong lúc reconnect.
- [ ] Background worker chỉ resume sau khi datasource sẵn sàng.
- [ ] Retry có timeout, backoff và giới hạn tổng thời gian.
- [ ] Lỗi credential/config không retry vô hạn bằng giá trị cũ.
- [ ] Transaction manager sử dụng cùng datasource wrapper.
- [ ] Không có hai lifecycle owner cho cùng pool.
- [ ] Checkpoint failure có rollback/resume policy.
- [ ] Đã test database restart, failover và credential rotation.
- [ ] Đã test connection leak hoặc transaction không drain.
- [ ] Đã xác nhận log/metrics không chứa secret.
- [ ] Đã chạy integration test bằng CRaC runtime/engine thật.

## 21. Kết luận thực hành

Connection JDBC là một resource phụ thuộc vào database session, socket và môi trường mạng tại thời điểm nó được tạo. Khi JVM được restore, object `Connection` hoặc pool cũ có thể vẫn nằm trong heap nhưng không còn đại diện cho một kết nối sử dụng được. `isClosed()` không đủ để xác định điều đó.

Hãy thiết kế lifecycle theo hướng đóng pool cũ và tạo pool mới. Trước checkpoint, dừng admission, drain transaction và worker, sau đó close pool. Sau restore, lấy config/credential hiện hành, tạo Hikari pool mới, xác minh connection và chỉ mở readiness khi datasource thực sự sẵn sàng. Với Spring, tận dụng `Lifecycle` integration nếu phù hợp; với resource không được Spring quản lý, đăng ký một `org.crac.Resource`. Không để hai cơ chế cùng quản lý một pool.

Kiểm thử cả database restart, failover, network interruption và credential rotation trong thời gian checkpoint. Khi pool mới chưa thể kết nối, giữ ứng dụng ở trạng thái NotReady và áp dụng retry có giới hạn. Cách làm này bảo vệ transaction, tránh dùng lại connection stale và giúp ứng dụng phục hồi có kiểm soát.

## 22. Tài liệu tham khảo

- [CRaC: Integrating CRaC in your Application](https://docs.azul.com/crac/usage/integrating-crac): đóng và mở lại database connections trong callback.
- [CRaC: Implementing the CRaC API](https://crac.org/use/implement-crac/): đăng ký resource và triển khai `beforeCheckpoint`/`afterRestore`.
- [Spring Framework: JVM Checkpoint Restore](https://docs.spring.io/spring-framework/reference/integration/checkpoint-restore.html): lifecycle stop/start trong checkpoint/restore.
- [Spring Boot: Checkpoint and Restore With the JVM](https://docs.spring.io/spring-boot/reference/packaging/checkpoint-restore.html): hỗ trợ CRaC trong Spring Boot.
- [Java JDBC `Connection` API](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Connection.html): `close`, `isClosed` và `isValid`.
- [HikariCP](https://github.com/brettwooldridge/HikariCP): pool lifecycle, validation, `maxLifetime`, `keepaliveTime` và timeout configuration.
- [Spring JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html): `JdbcTemplate`, datasource và transaction integration.


