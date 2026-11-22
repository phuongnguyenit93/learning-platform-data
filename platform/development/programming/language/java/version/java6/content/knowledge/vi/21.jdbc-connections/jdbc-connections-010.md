# Connection pool, proxy và phân biệt kết nối logic với kết nối vật lý trong JDBC

Trong JDBC, cùng interface `java.sql.Connection` có thể đại diện cho một **kết nối trực tiếp** do JDBC driver tạo hoặc một **handle logic** mà **connection pool** cho ứng dụng mượn tạm thời. Đối với pool, lời gọi `Connection.close()` trên handle thường **trả quyền sử dụng kết nối về pool**, không ngắt ngay database session/socket ở tầng vật lý.

Pool thường sử dụng một **proxy/wrapper** thực thi `Connection`: wrapper nhận `close()`, kiểm tra lượt mượn còn hiệu lực, chuyển tiếp các lời gọi JDBC được cho phép và phối hợp với pool để reset session state. Vì vậy, hai `Connection` Java objects khác nhau **có thể dùng lại cùng một physical database connection ở hai thời điểm khác nhau**.

Đây là kiến thức còn áp dụng cho **Java 17+ và JDK hiện hành**, dựa trên `java.sql.Connection`, `javax.sql.DataSource`, `javax.sql.ConnectionPoolDataSource`, `javax.sql.PooledConnection` và `ConnectionEventListener`. Bài học có ví dụ Java 17+ độc lập được kiểm chứng trên JDK 24 để nhìn rõ logical/physical lifecycle mà **không cần cài đặt database**. Ví dụ sử dụng simulated physical resource, vì vậy **không phải một pool dùng được trong production**.

## 1. Bạn sẽ học được gì?

- Phân biệt **physical connection**, **logical connection/lease**, **wrapper/proxy**, **pool manager** và **DataSource**.
- Giải thích vì sao `close()` trên logical handle không luôn đóng physical connection; khi nào pool thực sự đóng physical.
- Hiểu `PooledConnection.getConnection()` khác `PooledConnection.close()` thế nào và cách pool nhận events.
- Dùng `try-with-resources` đúng cách, tránh leak slots và sử dụng lại một handle đã bị đóng.
- Hiểu tại sao cần rollback/reset `autoCommit`, isolation, schema và session state trước khi tái sử dụng.
- Nhận diện pool exhaustion, borrow timeout, query timeout, network failure, dead connections và leak detection.
- Biết cấu hình pool và quan sát các chỉ số active/idle/waiting/lifetime ở mức hợp lý.
- Chạy chương trình mock một-slot với hai lượt borrow, chỉ tạo một physical, và kiểm chứng 14 dòng output.
- Biết giới hạn của proxy, `unwrap`, các transaction managers và những vấn đề liên quan tới multi-tenancy.

## 2. Bản chất của physical và logical connection

| Đối tượng/khái niệm | Phạm vi sống | Điều gì xảy ra khi kết thúc? |
| --- | --- | --- |
| **Physical DB connection** | Phiên kết nối thực, có thể gồm socket, TLS, authentication, server-side session và transaction state. | Pool/driver đóng khi shutdown, eviction, fatal error hoặc chính sách lifecycle yêu cầu. |
| **Logical `Connection`** | Một **lượt mượn** của operation/request. | `Connection.close()` làm handle mất hiệu lực và thường trả slot về pool. |
| **Connection pool** | Vòng đời ứng dụng hoặc thành phần quản lý database resources. | Quản lý số physical, cấp/thu hồi handles, validation, reset, eviction và shutdown. |
| **Proxy/wrapper** | Thường gắn với lượt mượn. | Chặn các method như `close` và chuyển tiếp method khác đến driver/physical. |
| **`DataSource`** | Factory được ứng dụng nắm giữ/inject. | Implementation có thể là basic hoặc pooling; interface không tự bảo đảm pool. |

Một sơ đồ hai yêu cầu theo thời gian:

```text
Request A                    Connection pool                 Database
   |                                |                            |
   +-- ds.getConnection() --------->|                            |
   |                                +-- physical #1 open ------->|
   |<------ logical handle A -------|                            |
   +-- execute SQL through A -------+-- driver/physical #1 ----->|
   +-- A.close() ------------------>|                            |
   |                                +-- slot #1 available        |
   |                                                             |
Request B                    Connection pool                    |
   +-- ds.getConnection() --------->|                            |
   |<------ logical handle B -------+-- reuse physical #1        |
   +-- execute SQL through B -------+-- driver/physical #1 ----->|
   +-- B.close() ------------------>|                            |
                                    |                            |
App shutdown ---------------------->+-- close physical #1 ------>|
```

`A` và `B` có thể là **hai Java objects khác nhau** nhưng cùng truy cập physical #1 ở những khoảng thời gian không chồng lấn. Không có yêu cầu API phải cấp một physical cố định cho mọi request: pool có thể chọn, tạo, loại bỏ hoặc thay physical theo health và policy.

**Không đồng nhất identity của wrapper với identity của DB session.** `connectionA == connectionB`, tên class của connection proxy, hoặc `System.identityHashCode` không phải chỉ số physical database sessions đáng tin. Dùng driver/pool instrumentation nếu cần đo physical.

## 3. Vì sao cần connection pooling?

Một kết nối thật có thể tiêu tốn DNS, TCP/TLS handshake, authentication, session initialization, DB locks/state và resources trên server. Nếu ứng dụng mở/đóng physical connection cho mọi HTTP request, chi phí tạo connection và tải trên DBMS có thể lớn.

Pool cho phép **reuse** những physical connections lành mạnh. Tuy nhiên:

1. Pool không tạo ra vô hạn capacity: số physical bị giới hạn bởi cấu hình và sức chứa DB server.
2. Pool không loại bỏ network/SQL latency, lock contention hoặc transaction failures.
3. Một physical đang được mượn thường không được dùng cho hai borrowers độc lập đồng thời theo kiểu thiếu đồng bộ.
4. Pool phải phát hiện connection bị hỏng, tránh tái cấp tài nguyên không còn sử dụng được.
5. Pool phải kiểm soát rò tài nguyên và state rò từ borrower trước sang borrower sau.

**Connection pooling là tối ưu hóa và quản lý vòng đời**, không phải bảo đảm mọi truy vấn được chạy nhanh hơn hoặc không còn lỗi kết nối.

### 3.1. DataSource không đồng nghĩa pool

`javax.sql.DataSource` là factory cho connections, được Java SE API xem là phương thức lấy connection phù hợp hơn `DriverManager` trong ứng dụng. Tài liệu mô tả các implementation dạng **basic**, **connection-pooling** và **distributed-transaction**.

```java
// Mảnh code trong một method, với DataSource đã được inject:
try (Connection c = dataSource.getConnection()) {
    // Sử dụng Connection và đóng khi xong.
}
```

Cú pháp không đổi giữa basic và pooling DataSource. Với basic implementation, `close()` có thể đóng tài nguyên vật lý thật; với pooled implementation, thường trả một logical handle. Việc dùng interface `DataSource` **không khiến JDBC tự có pool**.

## 4. Connection.close trên hai loại connection

`Connection` kế thừa `AutoCloseable` và `java.sql.Wrapper`. Ứng dụng nên dùng:

```java
// Mảnh code cần import java.sql.Connection và javax.sql.DataSource:
try (Connection c = dataSource.getConnection()) {
    // Thực hiện công việc JDBC trong phạm vi lượt mượn.
}
```

Sau khi rời khối, Java gọi `c.close()` ngay cả khi body ném exception.

**Khi không pooled:** driver có thể đóng tài nguyên kết nối thực và giải phóng server session tương ứng.

**Khi pooled:** proxy thường được đánh dấu closed, pool nhận lại slot, reset state và giữ physical nếu lành mạnh; nếu physical không thể dùng, pool đóng/thay thế nó.

**Khi pool shutdown/eviction:** tầng quản lý đóng physical theo hợp đồng của implementation; không phải ứng dụng business gọi `PooledConnection.close()` trực tiếp.

### 4.1. Vì sao không được “bỏ close để tiết kiệm connection”?

Nếu không gọi `close()` cho logical handle, pool vẫn thấy slot đang **borrowed**, dù request không còn cần. Nhiều requests như vậy làm toàn pool cạn slot, khiến requests mới chờ hoặc timeout.

Ngược lại, `try-with-resources` trả slot đúng thời điểm, **không làm mất lợi ích reuse physical**. Không cần tự gọi `System.gc()` hoặc trông chờ finalizer trả tài nguyên; garbage collection không phải cơ chế connection lifecycle đáng tin.

Nếu cả body và `close()` ném exception, semantics của Java try-with-resources giữ lỗi primary và gắn lỗi đóng vào `getSuppressed()`. Log nguyên exception tree ở boundary thích hợp để điều tra.

## 5. JDBC standard pooling APIs phía hạ tầng

Các interface trong package `javax.sql` **vẫn thuộc Java SE, module `java.sql`**. Tên `javax.sql` này không phải một API JDBC đã bị loại bỏ; ứng dụng Java hiện hành vẫn dùng chúng.

### 5.1. `ConnectionPoolDataSource` tạo physical PooledConnection

`javax.sql.ConnectionPoolDataSource` là **factory của `PooledConnection`**. Nó có các method:

```java
PooledConnection getPooledConnection() throws SQLException;
PooledConnection getPooledConnection(String user, String password)
        throws SQLException;
```

Đây là **chữ ký API minh họa**, không phải source file biên dịch độc lập. `ConnectionPoolDataSource` thường do driver cung cấp để tầng trung gian/pool manager tạo physical. Nó **không tự là một pool hoàn chỉnh**, không tự cung cấp mọi chính sách queue, timeout, eviction và monitoring.

### 5.2. `PooledConnection` là đối tượng quản lý physical

`javax.sql.PooledConnection` đại diện cho physical connection trong mô hình JDBC pooling tiêu chuẩn:

```java
// Mảnh code dành cho pool manager, không phải cách application dùng JDBC:
Connection logical = pooled.getConnection();
pooled.close();
```

- `PooledConnection.getConnection()` trả một **logical Connection handle** đến physical connection được quản lý.
- `Connection.close()` trên logical handle được driver/pool dùng để biết lượt mượn đã kết thúc.
- `PooledConnection.close()` **đóng physical connection**.
- Pool manager giữ `PooledConnection`, application thông thường chỉ thấy `java.sql.Connection`.

Do đó **không được cast `Connection` thành `PooledConnection`** hoặc tự close tầng vật lý trong service code. Chúng là hai abstraction khác nhau.

### 5.3. `ConnectionEventListener`

Tầng quản lý pool có thể đăng ký `javax.sql.ConnectionEventListener` qua `PooledConnection.addConnectionEventListener(...)`:

| Callback | Ý nghĩa |
| --- | --- |
| `connectionClosed(ConnectionEvent event)` | Application đã close logical Connection; pool biết physical slot có thể được tái sử dụng. |
| `connectionErrorOccurred(ConnectionEvent event)` | Driver nhận thấy lỗi nghiêm trọng khiến physical không còn thích hợp tái sử dụng. |

**`connectionClosed` là event của logical handle**, không phải khẳng định socket vừa bị đóng. `connectionErrorOccurred` thường dẫn tới việc pool loại/đóng physical. Một lỗi SQL constraint hoặc syntax bình thường **không nhất thiết** là lỗi fatal của physical connection.

Một số pool hiện đại có implementation wrapper và lifecycle nội bộ riêng, không phơi trực tiếp các đối tượng này cho application. Các interface tiêu chuẩn vẫn hữu ích để hiểu mô hình.

### 5.4. Pooling statement khác pooling connection

JDBC cũng định nghĩa `StatementEventListener` / `StatementEvent` cho prepared statement pooling trong những implementation hỗ trợ. Có connection pool **không đồng nghĩa** hệ thống có prepared statement cache. Không tự giả định driver/pool luôn cache statements theo mong muốn của bạn.

## 6. Proxy/Wrapper giữ vai trò gì?

Một connection pool có thể trao object triển khai `Connection` nhưng xử lý bên trong bằng wrapper/proxy. Nó có thể:

- Chặn `close()` để **return to pool** thay vì đóng physical.
- Giữ cờ “closed” riêng cho **logical lease**.
- Chặn method gọi sau close và ném `SQLException`.
- Chuyển tiếp `prepareStatement`/`commit`/`rollback`/`setAutoCommit` tới connection thật.
- Theo dõi transaction state, borrow duration và warning/error.
- Nhận diện fatal connection failures và hỗ trợ pool eviction.
- Hạn chế những thao tác có thể phá vỡ resource ownership.

Proxy có thể được tạo bằng class cụ thể, decorator, bytecode/proxy class hoặc `java.lang.reflect.Proxy`. **Không nên kiểm tra tên class để đoán pool library** vì tên implementation có thể thay đổi qua phiên bản.

### 6.1. Wrapper APIs

`Connection` kế thừa `java.sql.Wrapper`:

```java
boolean isWrapperFor(Class<?> iface) throws SQLException;
<T> T unwrap(Class<T> iface) throws SQLException;
```

Chúng giúp truy cập interface mà driver/wrapper hỗ trợ, **không hứa** mọi pool sẽ lộ object vật lý hoặc cho phép ứng dụng đóng physical ở bên dưới. Khi sử dụng vendor-specific API qua `unwrap`, tôn trọng thời hạn logical handle và contract của pool.

### 6.2. Sau close, handle phải xem như không còn hợp lệ

Trong pooling:

```text
logical-A.close()   -> logical-A.isClosed() có thể true
physical-P          -> vẫn open trong pool
logical-B           -> handle mới dùng lại physical-P
```

Không đưa `logical-A` vào một async task sau khi nó đã được trả. Java reference còn sống **không kéo dài lease**. Một connection proxy đã closed không trở nên hợp lệ trở lại chỉ vì pool có physical idle.

## 7. Ví dụ Java 17+ đầy đủ, không cần database

Để không phụ thuộc DBMS, ta dùng **mock single-slot DataSource**:

- Một object `Physical` tượng trưng cho physical DB session, **không mở socket**.
- Mỗi `getConnection` cấp một **Java dynamic proxy** cho `Connection`.
- Chỉ một lượt mượn hoạt động cùng lúc; lượt mượn thứ hai khi slot bận ném `SQLTransientConnectionException`.
- Logical `close` trả slot và vô hiệu hóa handle.
- Khi return với `autoCommit=false`, demo **đếm một rollback giả lập** và reset state thành true.
- Lần borrow sau tạo logical proxy mới nhưng dùng lại một Physical cũ.
- `pool.close()` đóng physical resource mô phỏng.

**Đây chỉ là demo giáo dục**, không phải connection pool/driver thật: không có network, SQL, database, transaction thật, validation, wait queue, credentials, leak detection hay transaction isolation. Mọi method không được liệt kê rõ đều ném `SQLFeatureNotSupportedException`. Không dùng class này trong sản phẩm.

### 7.1. File `LogicalVsPhysicalDemo.java`

```java
import java.io.PrintWriter;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import java.sql.SQLTransientConnectionException;
import java.util.logging.Logger;
import javax.sql.DataSource;

public final class LogicalVsPhysicalDemo {
    static final class OneSlotDataSource implements DataSource, AutoCloseable {
        private static final class Physical {
            final int id;
            boolean open = true;
            boolean autoCommit = true;

            Physical(int id) { this.id = id; }
        }

        private Physical physical;
        private boolean borrowed;
        private boolean shutdown;
        private int physicalOpens;
        private int physicalCloses;
        private int logicalReturns;
        private int simulatedRollbacks;
        private PrintWriter logWriter;
        private int loginTimeout;

        @Override
        public synchronized Connection getConnection() throws SQLException {
            if (shutdown) throw new SQLException("Pool is shut down");
            if (borrowed) throw new SQLTransientConnectionException("No free slot");
            if (physical == null || !physical.open) {
                physical = new Physical(++physicalOpens);
            }
            borrowed = true;
            InvocationHandler h = new LogicalHandler(physical);
            return (Connection) Proxy.newProxyInstance(
                    LogicalVsPhysicalDemo.class.getClassLoader(),
                    new Class<?>[] {Connection.class}, h);
        }

        private final class LogicalHandler implements InvocationHandler {
            private final Physical target;
            private boolean closed;

            LogicalHandler(Physical target) { this.target = target; }

            @Override
            public Object invoke(Object proxy, Method method, Object[] args)
                    throws Throwable {
                String name = method.getName();
                if (name.equals("close")) {
                    synchronized (OneSlotDataSource.this) {
                        if (!closed) {
                            closed = true;
                            if (borrowed) {
                                if (!target.autoCommit) {
                                    simulatedRollbacks++;
                                    target.autoCommit = true;
                                }
                                borrowed = false;
                                logicalReturns++;
                            }
                        }
                    }
                    return null;
                }
                if (name.equals("isClosed")) {
                    synchronized (OneSlotDataSource.this) {
                        return closed || !target.open;
                    }
                }
                if (name.equals("toString")) {
                    return "LogicalHandle(physical-" + target.id + ")";
                }
                if (name.equals("equals")) return proxy == args[0];
                if (name.equals("hashCode")) return System.identityHashCode(proxy);
                if (name.equals("isWrapperFor")) {
                    return ((Class<?>) args[0]).isInstance(proxy);
                }
                if (name.equals("unwrap")) {
                    Class<?> type = (Class<?>) args[0];
                    if (type.isInstance(proxy)) return type.cast(proxy);
                    throw new SQLException("Not a supported wrapper");
                }
                synchronized (OneSlotDataSource.this) {
                    if (closed || !target.open) {
                        throw new SQLException("Logical handle is closed");
                    }
                    return switch (name) {
                        case "getAutoCommit" -> target.autoCommit;
                        case "setAutoCommit" -> {
                            target.autoCommit = (Boolean) args[0];
                            yield null;
                        }
                        default -> throw new SQLFeatureNotSupportedException(
                                "Demo does not implement: " + name);
                    };
                }
            }
        }

        synchronized int physicalOpens() { return physicalOpens; }
        synchronized int physicalCloses() { return physicalCloses; }
        synchronized int logicalReturns() { return logicalReturns; }
        synchronized int simulatedRollbacks() { return simulatedRollbacks; }
        synchronized boolean physicalOpen() {
            return physical != null && physical.open;
        }

        @Override
        public synchronized void close() {
            if (!shutdown) {
                shutdown = true;
                if (physical != null && physical.open) {
                    physical.open = false;
                    physicalCloses++;
                }
            }
        }

        @Override
        public Connection getConnection(String user, String password)
                throws SQLException {
            throw new SQLFeatureNotSupportedException("No authentication in mock");
        }
        @Override public synchronized PrintWriter getLogWriter() {
            return logWriter;
        }
        @Override public synchronized void setLogWriter(PrintWriter out) {
            logWriter = out;
        }
        @Override public synchronized int getLoginTimeout() {
            return loginTimeout;
        }
        @Override public synchronized void setLoginTimeout(int seconds) {
            loginTimeout = seconds;
        }
        @Override public Logger getParentLogger() {
            return Logger.getLogger("demo.pool");
        }
        @Override public <T> T unwrap(Class<T> type) throws SQLException {
            if (type.isInstance(this)) return type.cast(this);
            throw new SQLException("Not a supported wrapper");
        }
        @Override public boolean isWrapperFor(Class<?> type) {
            return type.isInstance(this);
        }
    }

    public static void main(String[] args) throws SQLException {
        OneSlotDataSource pool = new OneSlotDataSource();
        try (pool) {
            Connection first = pool.getConnection();
            try (first) {
                System.out.println("physical.opens=" + pool.physicalOpens());
                System.out.println("first.autoCommit=" + first.getAutoCommit());
                first.setAutoCommit(false);
                System.out.println("first.autoCommitChanged=" + first.getAutoCommit());
                try {
                    pool.getConnection();
                } catch (SQLTransientConnectionException expected) {
                    System.out.println("whileBorrowed=" + expected.getMessage());
                }
            }
            System.out.println("first.isClosed=" + first.isClosed());
            System.out.println("physical.openAfterReturn=" + pool.physicalOpen());
            System.out.println("simulatedRollbacks=" + pool.simulatedRollbacks());
            try {
                first.getAutoCommit();
            } catch (SQLException expected) {
                System.out.println("staleHandle=" + expected.getMessage());
            }

            try (Connection second = pool.getConnection()) {
                System.out.println("second.sameHandle=" + (first == second));
                System.out.println("second.autoCommit=" + second.getAutoCommit());
                System.out.println("physical.opensAfterReuse=" + pool.physicalOpens());
            }
            System.out.println("logical.returns=" + pool.logicalReturns());
            System.out.println("physical.closesBeforeShutdown=" + pool.physicalCloses());
        }
        System.out.println("physical.closesAfterShutdown=" + pool.physicalCloses());
    }
}
```

### 7.2. Biên dịch và chạy

```bash
javac --release 17 -encoding UTF-8 LogicalVsPhysicalDemo.java
java LogicalVsPhysicalDemo
```

Ví dụ sử dụng `switch` expression (hỗ trợ Java 17), `Proxy` của JDK và `try (first)` hợp lệ với biến effectively final. Không cần Maven, Gradle, database hay JDBC driver ngoài.

### 7.3. Kết quả đã chạy thực tế trên JDK 24

**Stdout chính xác gồm 14 dòng:**

```text
physical.opens=1
first.autoCommit=true
first.autoCommitChanged=false
whileBorrowed=No free slot
first.isClosed=true
physical.openAfterReturn=true
simulatedRollbacks=1
staleHandle=Logical handle is closed
second.sameHandle=false
second.autoCommit=true
physical.opensAfterReuse=1
logical.returns=2
physical.closesBeforeShutdown=0
physical.closesAfterShutdown=1
```

Giải thích:

1. `physical.opens=1`: pool chỉ tạo một simulated physical.
2. `first.autoCommit=true` rồi `first.autoCommitChanged=false`: một borrower sửa state.
3. `whileBorrowed=No free slot`: pool một slot đang có người giữ; demo cố ý không chờ timeout.
4. `first.isClosed=true`: sau try-with-resources, logical handle thứ nhất đã mất hiệu lực.
5. `physical.openAfterReturn=true`: physical vẫn sống cho borrower kế tiếp.
6. `simulatedRollbacks=1`: demo mô phỏng cleanup transaction; **không hề rollback database thật**.
7. `staleHandle=Logical handle is closed`: handle cũ bị từ chối sử dụng.
8. `second.sameHandle=false`: một proxy Java mới được cấp.
9. `second.autoCommit=true`: state đã được reset.
10. `physical.opensAfterReuse=1`: physical được tái sử dụng, không tạo instance mới.
11. `logical.returns=2`: hai lượt borrow đều được trả.
12. `physical.closesBeforeShutdown=0`: trả logical handle không đóng physical.
13. `physical.closesAfterShutdown=1`: pool đóng simulated physical khi kết thúc.

**Lưu ý:** danh sách bên trên gộp các nhóm output nhưng stdout thực tế có đủ 14 dòng như code fence. Số `physical.opens` không đếm socket; chỉ đếm đối tượng mock để kiểm tra lifecycle. Không dùng mock làm benchmark hay xác nhận hiệu năng database.

## 8. Vấn đề lớn nhất khi reuse: transaction và session state

Một physical connection không chỉ chứa socket; nó còn có session state mà borrower có thể thay đổi. Nếu request A mượn rồi trả và request B nhận lại cùng physical mà state chưa được reset, ứng dụng có thể hoạt động sai hoặc rò dữ liệu.

| State | Cách thay đổi | Rủi ro khi tái sử dụng |
| --- | --- | --- |
| `autoCommit` | `setAutoCommit(false)`. | Request sau không tự commit, giữ transaction/locks ngoài ý định. |
| Active transaction | DML chưa commit/rollback. | Transaction/locks của A ảnh hưởng B. |
| Isolation level | `setTransactionIsolation(...)`. | B đọc dữ liệu với consistency khác mong đợi. |
| `readOnly` | `setReadOnly(true)`. | B bất ngờ không thực thi được thao tác ghi. |
| Catalog/schema | `setCatalog` / `setSchema`. | B đọc/ghi nhầm DB namespace hoặc tenant. |
| Holdability | `setHoldability`. | ResultSet behavior thay đổi qua commit. |
| Warnings | `SQLWarning`. | Diagnostics bị lẫn sự kiện borrower trước. |
| Session variables | SQL `SET ...`, search path, timezone. | B dùng config còn sót lại từ A. |
| Temp objects/cursors | Temporary tables/cursors. | Resource leak hoặc rò dữ liệu cross-request. |
| Network timeout/client info | `setNetworkTimeout` / `setClientInfo`. | Latency/metadata khác kỳ vọng. |

**Không có bảo đảm JDBC rằng mọi connection pool đều tự reset tất cả state thay đổi bằng SQL tùy ý.** Nhiều pool theo dõi một số setter chuẩn, nhưng session variables thay qua native SQL có thể không được phát hiện. Cần test chính xác với driver/pool đang triển khai.

### 8.1. Đừng bật autoCommit để thay cho rollback

Theo contract JDBC, `setAutoCommit(true)` có thể **commit transaction đang hoạt động** khi chuyển trạng thái. Vì vậy nếu một request bị lỗi sau khi `setAutoCommit(false)`, đừng chỉ set lại true rồi coi như sạch. Phải **commit hoặc rollback có chủ đích** trước khi trả connection.

Mảnh code cho ứng dụng tự quản lý transaction (không phải chương trình độc lập):

```java
try (Connection c = dataSource.getConnection()) {
    c.setAutoCommit(false);
    try {
        // Thực thi các PreparedStatement của transaction tại đây.
        c.commit();
    } catch (SQLException | RuntimeException original) {
        try {
            c.rollback();
        } catch (SQLException rollbackFailure) {
            original.addSuppressed(rollbackFailure);
        }
        throw original;
    }
}
```

Cần khai báo `throws SQLException` cho method chứa đoạn này và có `DataSource dataSource` thật. Nếu có transaction manager/framework, để framework quản lý transaction; không tự commit/rollback một connection thuộc transaction đang được điều phối.

`try-with-resources` vẫn đóng logical handle kể cả khi transaction code ném lỗi. Việc giữ `original` và `rollbackFailure` giúp chẩn đoán đúng sự cố.

### 8.2. `beginRequest` và `endRequest` của JDBC

`Connection.beginRequest()` / `endRequest()` có từ Java 9 (JDBC 4.3), là **request-boundary hints** cho driver/pool. Default implementation có thể không thực hiện thao tác gì; ứng dụng không nên coi chúng là bảo đảm transaction được rollback hoặc physical bị đóng.

Đối với implementation pooling hiện đại, tài liệu `Connection`/`PooledConnection` mô tả cách pool manager sử dụng request boundary hoặc đóng logical handle khi return. Điều này **không thay thế** trách nhiệm gọi `close()` của ứng dụng sau lượt mượn.

## 9. Khi pool cạn slot, điều gì xảy ra?

Một pool có `maxPoolSize` (tên cụ thể tùy thư viện). Khi mọi physical đang bận:

- Pool có thể chờ một connection được trả.
- Pool có thể tạo thêm physical nếu chưa chạm giới hạn.
- Nếu chờ quá thời hạn, pool báo lỗi mượn connection, thường qua `SQLException` hoặc subclass.
- Nếu database không cho mở thêm connections, lỗi tạo physical có thể là network/authentication/server-capacity issue.

Trong demo, capacity = 1 và **không có wait queue**, nên yêu cầu thứ hai ngay lập tức ném `SQLTransientConnectionException("No free slot")`. Điều này được thiết kế để test deterministic, **không mô tả mặc định của mọi pool thật**.

### 9.1. Timeout không phải một loại duy nhất

| Loại | Áp dụng cho | Cần chú ý |
| --- | --- | --- |
| Pool acquisition timeout | Thời gian borrower chờ **slot**. | Thường là property riêng của pooling library. |
| Connection/login timeout | Thiết lập physical connection tới DBMS. | Không đồng nghĩa chờ pool slot. |
| Network/socket timeout | Đợi network I/O. | Phụ thuộc driver và hạ tầng. |
| Query timeout | Thực thi SQL statement. | `Statement.setQueryTimeout` và behavior driver. |
| Transaction timeout | Toàn bộ giao dịch nghiệp vụ. | Framework/transaction manager có thể kiểm soát. |

`DataSource.setLoginTimeout` không phải một API chuẩn điều khiển tất cả loại wait/borrow timeout của mọi pool. Tên như `connectionTimeout`, `idleTimeout`, `maximumPoolSize`, `maxLifetime` có thể là **configuration riêng từng thư viện**, không phải method chuẩn của `DataSource`.

### 9.2. Vì sao tăng pool size không luôn tốt hơn?

Nếu nhiều requests chạy SQL nặng, tăng số sessions có thể làm DB server bị contention, tốn RAM, sockets và locks. Công thức sizing sơ bộ:

```text
Tổng physical DB connections tiềm năng
≈ (số application replicas × max connections mỗi pool)
  + jobs, admin tools, migrations, monitoring và những clients khác
```

Cần so tổng này với giới hạn server và workload thực tế. Đừng chọn một con số pool “thật lớn” chỉ để tránh timeout mà không đo query duration, active/idle/waiting và database CPU/locks.

## 10. Metrics và connection leaks

| Metric | Giải thích |
| --- | --- |
| Active/borrowed | Connections đang được application giữ. |
| Idle/available | Connections sẵn có để mượn. |
| Pending/waiting | Requests đang đợi được borrow. |
| Borrow duration | Thời gian một logical handle bị giữ. |
| New physical opens | Số lượng/tần suất kết nối vật lý mới. |
| Evictions | Physical bị loại do lỗi, idle, max lifetime hoặc shutdown. |
| Validation failures | Tài nguyên bị lỗi khi health check. |
| Borrow timeouts | Thời hạn chờ slot đã hết. |
| Leak warnings | Borrower giữ connection lâu bất thường so với ngưỡng policy. |

**Leak warning không có nghĩa pool đã lấy lại handle**. Query dài hoặc transaction chính đáng có thể kích hoạt cảnh báo nếu threshold quá thấp. Nên ghi traces/operation IDs phù hợp, xem duration của SQL/transaction, và đóng connection trong scope đúng thay vì chỉ tăng kích thước pool.

**Số proxy objects có thể lớn hơn rất nhiều số physical DB sessions.** Do mỗi lượt borrow tạo một logical handle, việc đếm Java Connection objects bằng heap profiler cần được diễn giải đúng.

## 11. Validation, fatal errors và eviction

Idle physical có thể bị DB/network đóng khi không sử dụng. Một pool lành mạnh thường có chiến lược:

1. Kiểm tra `Connection.isValid(timeout)` nếu driver hỗ trợ phù hợp.
2. Hoặc validation query/heartbeat theo contract của driver/pool.
3. Dùng idle/maximum lifetime phù hợp với DB server và load balancer timeouts.
4. Nhận biết fatal connection error, loại bỏ physical không an toàn.
5. Thay physical bằng kết nối mới khi có nhu cầu và DB sẵn sàng.
6. Tránh retry storm nếu database đang outage.
7. Đóng toàn bộ physical còn sở hữu khi pool shutdown hợp lệ.

**`Connection.isClosed()` không phải network health check đầy đủ**. Logical handle chưa đóng không chứng minh server vẫn reachable; network failure có thể chỉ xuất hiện lúc thực hiện I/O.

`connectionErrorOccurred` của `ConnectionEventListener` thông báo driver thấy pooled connection không còn an toàn. Ngược lại, **không phải mọi `SQLException` đều fatal**; lỗi syntax, uniqueness constraint hoặc nghiệp vụ có thể không khiến physical hỏng. Pool/driver phải phân loại lỗi thích hợp.

## 12. Transaction-aware proxies và nhiều lớp wrapper

Trong hệ thống có framework, object `Connection` ứng dụng nhận có thể được bọc qua nhiều tầng:

```text
Application code
      |
Transaction-aware Connection wrapper
      |
Metrics / tracing proxy
      |
Connection pool logical proxy
      |
Driver physical connection
      |
Database server
```

Đây là ví dụ tổng quát, không phải mọi ứng dụng đều có tất cả các tầng. Transaction manager có thể giữ một connection cho transaction rồi tái sử dụng trong các repository methods; pool proxy bảo đảm return-to-pool; driver làm việc với DB protocol.

**Không dựa vào `connection.getClass().getName()` để xác định driver vật lý.** Nếu cần vendor-specific access, dùng `isWrapperFor`/`unwrap` theo API mà implementation cho phép, nhưng không giữ object được unwrap sau khi handle đã đóng hoặc cố bypass quyền quản lý physical.

Nếu framework sở hữu transaction, tuân thủ contract framework để tránh double-commit hoặc close sai thời điểm. Đừng tự ý truyền một handle giữa threads khi transaction context chỉ được định nghĩa trong một scope.

## 13. Multi-tenancy: state rò giữa các borrowers

Ví dụ nguy hiểm:

```text
Request tenant A:
  borrow physical #1
  SET search_path = tenant_a
  query...
  return physical #1  (không reset session state)

Request tenant B:
  borrow physical #1
  query không chỉ rõ schema
  -> có thể truy cập nhầm tenant_a
```

Đây là tình huống minh họa phụ thuộc DBMS. Nếu ứng dụng sử dụng schema switching, session variables hoặc role switching, **việc reset trạng thái là yêu cầu bảo mật**, không đơn thuần là tối ưu hóa.

Biện pháp:

- Thiết kế tenant isolation từ database permissions, query scoping và schema policy.
- Reset schema/session variables rõ ràng theo driver/database contract.
- Test hai lượt mượn tuần tự A → B trên cùng pool.
- Không mặc định mọi pool phát hiện thay đổi bằng raw SQL `SET ...`.
- Không dùng pool wrapper như một security sandbox; nó là cơ chế quản lý tài nguyên.
- Với workload đa tenant yêu cầu ranh giới mạnh, cân nhắc separate pools/credentials hoặc DB roles theo security model.

## 14. Mẫu JDBC code dùng DataSource trong ứng dụng thật

Ví dụ sau là **mảnh code tích hợp**, cần DataSource thật, JDBC driver, schema và bảng tương ứng:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

static String readDisplayName(DataSource dataSource, long id)
        throws SQLException {
    String sql = "SELECT display_name FROM accounts WHERE id = ?";
    try (Connection c = dataSource.getConnection();
         PreparedStatement ps = c.prepareStatement(sql)) {
        ps.setLong(1, id);
        try (ResultSet rs = ps.executeQuery()) {
            return rs.next() ? rs.getString(1) : null;
        }
    }
}
```

Code minh họa đúng ownership:

- Lấy connection khi bắt đầu operation và **close ở cuối scope**.
- `PreparedStatement` tham số hóa input; không nối trực tiếp dữ liệu user vào SQL.
- ResultSet/statement/connection được đóng theo thứ tự ngược.
- Code nghiệp vụ không cố thao tác physical connection riêng.
- DataSource/pool implementation chịu trách nhiệm physical lifecycle.
- Không dùng JDBC connection chung trong singleton qua các requests.

Đây **không có stdout cố định** vì phải kết nối database thật. Chỉ chương trình `LogicalVsPhysicalDemo` ở mục 7 là self-contained và đã được thử nghiệm Java 17+.

## 15. Khi nào physical bị đóng?

| Tình huống | Logical handle | Physical resource |
| --- | --- | --- |
| Application close pooled handle bình thường | Mất hiệu lực / returned. | Thường tiếp tục sống trong pool. |
| Application quên close handle | Vẫn giữ slot. | Bị giữ khỏi borrowers khác, gây exhaustion. |
| Pool nhận fatal error | Handle báo lỗi hoặc bị đóng theo implementation. | Physical thường bị loại và đóng. |
| Idle/lifetime eviction | Chỉ xử lý physical không còn borrower theo policy an toàn. | Physical bị đóng/thay thế. |
| Pool shutdown | Pool ngừng cho borrow mới. | Dọn physical đang sở hữu theo lifecycle. |
| Không có pooling | Driver Connection close trực tiếp. | Thường đóng session/tài nguyên thực. |
| GC của Java wrapper | Không phải thao tác cleanup đáng tin. | Không được phụ thuộc vào finalization. |

Không mặc định mọi lần close pooled handle sẽ giữ physical nguyên vẹn: pool có thể quyết định evict nếu resource quá hạn hoặc có lỗi. API không bảo đảm physical identity giữa các lần borrow.

## 16. Lỗi thường gặp

| Hiểu nhầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| “Connection.close luôn ngắt socket.” | Pooled Connection thường là logical handle. | Phân biệt close logical và physical. |
| “Đã dùng DataSource chắc chắn có pool.” | DataSource là factory, có basic implementation. | Chọn và cấu hình pooling implementation. |
| “Không close thì pool được reuse.” | Không close giữ slot borrowed. | Luôn close logical handle khi xong. |
| “Hai Connection khác nhau nghĩa hai physical.” | Nhiều logical handles có thể reuse cùng physical. | Dùng metrics/driver diagnostics. |
| “isClosed false bảo đảm DB còn sống.” | Không phải health check đầy đủ. | Validation theo pool/driver. |
| “PooledConnection.close chỉ trả slot.” | Nó đóng **physical connection**. | Để pool manager sở hữu method này. |
| “ConnectionPoolDataSource là pool hoàn chỉnh.” | Nó chỉ tạo PooledConnection. | Cần pool manager. |
| “connectionClosed event nghĩa TCP đã đóng.” | Event nói logical handle đã đóng. | Hiểu event ownership. |
| “Mọi SQLException phải hủy physical.” | Lỗi SQL không fatal có thể giữ connection hợp lệ. | Phân loại lỗi. |
| “Reset autoCommit=true luôn rollback.” | Nó có thể commit transaction hiện tại. | Commit/rollback chủ đích. |
| “Pool tự reset mọi session variables.” | SQL SET state có thể ngoài vùng tracking. | Thiết kế/test cleanup state. |
| “Một connection nên chia sẻ cho mọi threads.” | State/transaction có thể xung đột. | Borrow per operation. |
| “Pool càng lớn càng tốt.” | DB server có capacity/locking contention. | Đo workload, giới hạn DB. |
| “Acquisition timeout là query timeout.” | Chờ slot và chờ query khác nhau. | Cấu hình riêng. |
| “Unwrap luôn lấy được physical.” | Implementation có thể che giấu/giới hạn. | Tôn trọng `Wrapper` contract. |
| “Leak detector sẽ tự sửa leak.” | Thường chỉ phát cảnh báo. | Scope và đóng resources chính xác. |
| “Demo mock là connection pool production.” | Không có DB, SQL, health, queue, TLS. | Dùng thư viện pool đáng tin. |

## 17. Bài tập thực hành

**A.** Bỏ `close()` của handle đầu trong demo; giải thích vì sao borrow lần hai bị từ chối và tại sao quên close trong server gây exhaustion.

**B.** Bỏ `first.setAutoCommit(false)`; chạy lại và kiểm tra `simulatedRollbacks`. Vì sao state cleanup quan trọng cho borrower tiếp theo?

**C.** Sau `first.close()`, thử gọi `first.getAutoCommit()`. Giải thích vì sao physical còn mở không khiến handle cũ được tái sử dụng.

**D.** Nâng mock lên 2 slots và thiết kế wait queue có timeout. Phân tích race conditions khi nhiều threads cùng trả/mượn, và vì sao không nên đưa mock lên production.

**E.** Trên database thật, tạo một transaction rồi rollback, trả connection, mượn lại, xác minh state và locks không rò sang lượt sau.

**F.** Dùng database hỗ trợ schema per tenant, kiểm thử borrower A đổi schema và borrower B nhận lại cùng physical. Viết cleanup logic rõ ràng.

**G.** Quan sát metrics của pool production: active/idle/pending, borrow latency, physical creations, idle evictions và validation failures. Phân biệt physical count với số Java proxy objects.

**H.** Test shutdown khi tất cả handles đã được trả; kiểm tra physical closes. Trên pool thật, định nghĩa cách xử lý in-flight borrowers khi tắt dịch vụ.

## 18. Checklist đưa vào sản phẩm

1. Xác nhận `DataSource` thực sự có pooling hay chỉ là basic factory.
2. Lấy và close `Connection` trong đúng scope, ưu tiên `try-with-resources` khi code sở hữu connection.
3. Không giữ một logical handle trong singleton hoặc dùng sau close.
4. Phân biệt active/idle/physical count với số wrapper objects.
5. Đặt pool size theo DB connection limits và số replicas, không chỉ theo peak request count.
6. Tách pool borrow timeout khỏi driver login/network timeout và statement query timeout.
7. Thiết lập validation/eviction phù hợp với server idle timeouts.
8. Có policy rollback/reset `autoCommit`, isolation, readOnly, schema và session variables.
9. Với multi-tenancy, kiểm thử cross-tenant state leakage.
10. Phân loại fatal vs nonfatal SQLExceptions.
11. Bật metrics và leak detection ở ngưỡng thực tế, tránh false-positive noise.
12. Quản lý pool shutdown và health checks theo lifecycle framework.
13. Dùng `isWrapperFor`/`unwrap` chỉ theo driver/pool contract, không bypass physical ownership.
14. Không nhầm `PooledConnection.close` với application `Connection.close`.
15. Dùng thư viện pool được duy trì và kiểm chứng, không dùng mock demo làm implementation.
16. Kiểm thử tài nguyên JDBC/DB thật bằng integration tests riêng ngoài demo.

## 19. Câu hỏi tự kiểm tra

**1.** `DataSource.getConnection()` có luôn trả physical driver object không? — **Không.** Khi pooling, nó thường trả logical `Connection` wrapper.

**2.** `Connection.close()` của một pooled handle có nhất thiết đóng physical không? — **Không.** Nó thường trả slot cho pool. Pool có thể đóng physical khi eviction/shutdown/fatal.

**3.** `PooledConnection.getConnection()` và `PooledConnection.close()` khác nhau thế nào? — **Method đầu tạo logical handle; method sau đóng physical** theo contract JDBC.

**4.** Tại sao hai logical handles có thể dùng một physical? — **Vì pool tái sử dụng physical tuần tự** sau khi borrower trước trả slot.

**5.** Tại sao không được tránh close vì sợ tốn chi phí mở DB? — **Không close giữ slot và gây leak.** Pool quyết định có giữ physical hay không.

**6.** `ConnectionEventListener.connectionClosed` có phải socket closed không? — **Không**, đó là sự kiện đóng logical handle trong cơ chế pooling chuẩn.

**7.** Vì sao setAutoCommit(true) không phải rollback? — Vì thay trạng thái có thể **commit transaction hiện hành**; cần xử lý transaction có chủ đích.

**8.** `DataSource` có tự cung cấp connection pool không? — **Không**, chỉ là interface factory; cần implementation có pooling.

**9.** `isClosed()==false` có chứng minh DB healthy không? — **Không**, cần validation và xử lý network failure.

**10.** Tại sao `physical.opensAfterReuse=1` nhưng `logical.returns=2`? — Hai handle được mượn/trả, một simulated physical được reuse.

## 20. Tài liệu Java chính thức hiện hành

- [DataSource — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/javax/sql/DataSource.html): basic/pooled/distributed implementations và contract tạo connections.
- [ConnectionPoolDataSource — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/javax/sql/ConnectionPoolDataSource.html): factory cho `PooledConnection`.
- [PooledConnection — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/javax/sql/PooledConnection.html): physical vs logical handle, events và cách đóng physical.
- [ConnectionEventListener — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/javax/sql/ConnectionEventListener.html): logical close và fatal connection error.
- [Connection — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Connection.html): `close`, transaction, `autoCommit`, `isValid`, `beginRequest`/`endRequest`.
- [Wrapper — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Wrapper.html): `isWrapperFor`/`unwrap`.
- [javax.sql package — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/javax/sql/package-summary.html): tổng quan DataSource, connection pooling, statement pooling.
- [SQLException — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLException.html): lỗi kết nối và thông tin chẩn đoán.

**Ghi nhớ:** Logical `Connection` là một **lượt mượn**; physical connection là **tài nguyên DB thực tế**. Với connection pool, `close()` trên logical handle thường **trả slot**, còn physical vẫn được giữ để tái sử dụng. `PooledConnection.close()` thuộc tầng quản lý và đóng physical. Vì vậy luôn trả handle đúng scope, dọn transaction/session state, cấu hình validation/limits và dùng DataSource/pool implementation phù hợp với database thật.
