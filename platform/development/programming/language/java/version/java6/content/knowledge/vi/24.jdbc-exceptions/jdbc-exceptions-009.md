# StatementEventListener và sự kiện PreparedStatement trong pool

## 1. Vì sao JDBC cần một listener riêng cho PreparedStatement?

Trong Java, một ứng dụng thường lấy `Connection` từ `DataSource`, tạo `PreparedStatement`, truyền tham số, thực thi rồi đóng statement qua `try-with-resources`. Nếu hệ thống có **connection pool** và **statement pool**, thao tác `close()` mà ứng dụng thực hiện trên một statement không nhất thiết đồng nghĩa với việc hủy ngay mọi tài nguyên prepared statement vật lý của driver. Tầng pool có thể muốn **tái sử dụng prepared statement phía dưới** để tiết kiệm chi phí chuẩn bị SQL.

Nhưng có một tình huống nguy hiểm: prepared statement từng được cache có thể **không còn hợp lệ** sau DDL, thay đổi metadata/schema, thay đổi trạng thái phiên hoặc khi driver phát hiện một lý do vendor-specific. Nếu pool trả lại một statement không còn hợp lệ, câu truy vấn tiếp theo sẽ thất bại. Pool cần được thông báo **khi prepared statement được đóng hoặc driver xác định nó bị invalid**.

JDBC cung cấp hai API chuẩn cho đúng bài toán này:

- `javax.sql.StatementEventListener`: interface nhận hai callbacks `statementClosed(StatementEvent)` và `statementErrorOccurred(StatementEvent)`.
- `javax.sql.StatementEvent`: sự kiện mang **PooledConnection nguồn**, **PreparedStatement liên quan** và, nếu có, **SQLException driver sắp ném**.

Listener được đăng ký **trên `javax.sql.PooledConnection`**, không phải trên một `PreparedStatement` trực tiếp và cũng không phải trên mọi `DataSource`.

Bài **“StatementEventListener và sự kiện PreparedStatement trong pool”** thuộc chủ đề **Ngoại lệ JDBC**, nên trọng tâm gồm:

1. Cơ chế và hai callbacks, đặc biệt ý nghĩa **driver-detected invalidation**.
2. Phân biệt đóng statement với statement trở nên invalid; phân biệt statement error với lỗi query bình thường và connection error.
3. Vòng đời `PooledConnection` / logical `Connection` / `PreparedStatement` và vai trò cache invalidation.
4. `StatementEvent.getSource()`, `getStatement()`, `getSQLException()`.
5. Capability `DatabaseMetaData.supportsStatementPooling()` và **hint** `Statement.setPoolable(boolean)`.
6. Cách viết observer/pool integration, xử lý cache eviction, đăng ký/hủy listener đúng lúc.
7. Lỗi phổ biến, concurrency/resource ownership, cách test bằng Java 17+ và xác nhận với driver/pool thật.

**Giới hạn của bài:** Java SE hiện hành có các interface này và chúng **không phải legacy API cần tránh**. Tuy nhiên một ứng dụng thông thường **không nhất thiết phải tự cài StatementEventListener**: đây chủ yếu là API cho infrastructure/pool manager. Nhiều pool/driver có cơ chế prepared statement caching riêng; không suy ra họ đều phát sự kiện `StatementEvent` theo cùng cách chỉ từ việc ứng dụng có `PreparedStatement`.

Ví dụ chính `StatementPoolingEventsDemo.java` là một chương trình Java 17+ **không cần database/driver bên ngoài**. Nó mô phỏng các sự kiện qua dynamic proxies, biên dịch bằng `javac --release 17` và đã chạy trên OpenJDK 24 với **41/41 assertions PASS**. Nó kiểm chứng hợp đồng API và logic event routing; không giả vờ có physical prepared-statement cache thực sự.

## 2. Phân biệt Connection pool và Statement pool

### 2.1. Connection pool tái sử dụng kết nối vật lý

Trong kiến trúc JDBC có pool:

```text
Application
     |
     | DataSource.getConnection()
     v
Logical Connection handle (Connection)
     |
     | delegate / proxy
     v
PooledConnection (physical resource managed by pool)
     |
     v
JDBC driver / database session
```

`javax.sql.PooledConnection` đại diện cho nguồn kết nối vật lý của pool. Ứng dụng thường chỉ nhận một **logical `Connection` handle** và gọi `Connection.close()` khi hoàn tất. Đối với pool, close logical handle thường **trả kết nối vật lý về pool**, không trực tiếp đóng socket.

Ngược lại, `PooledConnection.close()` đóng **physical connection** do pool quản lý. Theo Javadoc, ứng dụng thông thường không tự gọi method này; pool manager gọi khi shutdown hoặc kết nối vật lý không thể dùng tiếp. Không được giữ reference `PooledConnection` của infrastructure rồi tự đóng trong code nghiệp vụ.

### 2.2. Statement pool tái sử dụng prepared statement phía dưới

Nếu pool hỗ trợ pooling/caching prepared statements:

```text
Connection (logical, borrowed)
     |
     v
PreparedStatement (logical, used by request)
     |
     v
Prepared statement entry owned by statement pool
     |
     v
Driver/database prepared statement resource
```

Khi application gọi `PreparedStatement.close()`, một statement pool có thể:
- Đóng logical handle (caller không được dùng lại nó).
- Ghi nhận rằng entry đã có thể trở thành cache candidate.
- Reset parameters, result sets, timeout, fetch settings và state tùy implementation.
- Tái sử dụng hoặc huỷ cache entry theo capacity, schema, session, invalidation policy.

**Không được hiểu** rằng cùng Java object `PreparedStatement` đã đóng sẽ được ứng dụng lấy lại và sử dụng như chưa đóng. API vẫn coi logical handle đã closed; pool có thể tạo **một logical handle mới** trỏ vào resource vật lý được tái sử dụng.

### 2.3. Hai cấp event khác nhau

| Cấp quản lý | Listener | Event | Mục đích |
| --- | --- | --- | --- |
| Connection pool | `ConnectionEventListener` | `ConnectionEvent` | Logical connection closed / connection error, để pool quản lý physical connection |
| Prepared-statement pool | `StatementEventListener` | `StatementEvent` | PreparedStatement closed / driver phát hiện statement invalid |
| Business layer | Không bắt buộc dùng hai listeners trên | `SQLException` tại JDBC calls | Tầng nghiệp vụ xử lý lỗi/transaction/retry |

Hai loại events **không thay thế nhau**. `statementErrorOccurred` không mặc định báo physical connection đã chết, còn `connectionErrorOccurred` không phải “một prepared statement riêng bị invalid”.

## 3. `javax.sql.StatementEventListener` gồm những gì?

Javadoc Java SE 26 định nghĩa:

```java
public interface StatementEventListener
        extends java.util.EventListener {

    void statementClosed(StatementEvent event);

    void statementErrorOccurred(StatementEvent event);
}
```

Đây là chữ ký interface minh họa; trong code Java dùng type có sẵn trong `javax.sql`, không tự định nghĩa lại.

Một listener cần implement **cả hai abstract methods**, nên nó không phải một `@FunctionalInterface` một-method lambda thông thường.

### 3.1. `statementClosed(StatementEvent event)`

Driver gọi callback này khi phát hiện **PreparedStatement được đóng** và có listener đã đăng ký với `PooledConnection` liên quan.

Trong pool, callback giúp manager biết một logical prepared statement không còn được borrower sử dụng và có thể bắt đầu quy trình **cache candidate / release / eviction**.

**Không tự động hiểu** rằng mọi statement đã đóng đều lập tức được cache:
- Cache có thể disabled hoặc full.
- Statement có thể không phù hợp để cache.
- Application có thể đặt `setPoolable(false)`.
- Statement có thể đã bị invalid trước đó.
- Driver/pool có vendor-specific restrictions.

Callback chỉ cho biết **sự kiện đóng**, không đảm bảo reuse.

### 3.2. `statementErrorOccurred(StatementEvent event)`

Callback này xảy ra khi **driver xác định một PreparedStatement invalid**. Theo Javadoc, driver gọi method **ngay trước khi ném SQLException tương ứng cho application**.

Tầng pool có thể dùng callback để:
- Đánh dấu statement đã invalid.
- Evict cache entry liên quan.
- Không tái sử dụng statement đó khi borrower gọi close sau lỗi.
- Bảo đảm không để một prepared statement stale quay lại cache.

**Quan trọng:** Đây **không phải** một callback cho *mọi* `SQLException` từ mọi `PreparedStatement`.

Ví dụ `INSERT` vi phạm unique constraint có thể ném `SQLIntegrityConstraintViolationException`/`SQLException` nhưng bản thân prepared statement vẫn hợp lệ cho một lần thực thi tiếp theo với tham số khác. Driver không có nghĩa vụ coi mọi lỗi SQL là “statement invalidation” và phát `statementErrorOccurred`. Ngược lại, một thay đổi DDL làm cached plan invalid là ví dụ rõ được Javadoc nêu.

Ngoài ra, `statementErrorOccurred` **không xử lý ngoại lệ thay ứng dụng**: driver vẫn ném `SQLException`, application vẫn phải bắt/rollback/retry theo business và transaction semantics.

## 4. `StatementEvent` mang dữ liệu gì?

Một sự kiện `javax.sql.StatementEvent` là subclass của `java.util.EventObject` và có:

| Method | Return type | Ý nghĩa |
| --- | --- | --- |
| `event.getSource()` | `Object` | `PooledConnection` nguồn phát event |
| `event.getStatement()` | `PreparedStatement` | Statement đã đóng hoặc bị xác định invalid |
| `event.getSQLException()` | `SQLException` | Exception driver chuẩn bị ném, hoặc `null` trong close-only constructor |

Constructors Java SE:

```java
new StatementEvent(PooledConnection source,
                   PreparedStatement statement);

new StatementEvent(PooledConnection source,
                   PreparedStatement statement,
                   SQLException exception);
```

**Constructor thứ nhất** mặc định đặt exception thành `null`. **Constructor thứ hai** lưu exception được truyền. Truyền `null` làm PooledConnection nguồn gây `IllegalArgumentException`; event phải có source hợp lệ.

Trong callback, thường đọc:

```java
@Override
public void statementErrorOccurred(StatementEvent event) {
    PreparedStatement invalid = event.getStatement();
    SQLException error = event.getSQLException();
    Object source = event.getSource(); // PooledConnection
    // Pool-specific invalidation logic.
}
```

Đây là **đoạn minh họa ở trong một class implement StatementEventListener**. Không gọi method JDBC trên `invalid` tùy tiện: nó đã bị driver đánh dấu invalid và có thể đang xử lý một lỗi. Thông tin này để pool nhận diện/evict, không để callback tự phát lại SQL.

### 4.1. `getSource` không phải chính PreparedStatement

Một lỗi dễ gặp là cast:

```java
PreparedStatement ps =
        (PreparedStatement) event.getSource();
```

Đây là **anti-pattern**: `getSource()` là **`PooledConnection`** của event, còn `event.getStatement()` mới là `PreparedStatement`. Dùng đúng getter để tránh `ClassCastException` và cache invalidation sai resource.

### 4.2. SQLException trong event và exception application nhận

Với `statementErrorOccurred`, Javadoc nêu `getSQLException()` là exception driver **sắp ném**. Trong một implementation mô phỏng hợp đồng, listener nhìn thấy **cùng object exception** trước khi caller catch được nó. Điều này được kiểm thử trong chương trình chạy đầy đủ.

Listener có thể ghi **SQLState**, vendor error code và dấu hiệu invalidation cho diagnostics, nhưng phải redact SQL/parameter values có thông tin nhạy cảm. Không giữ `SQLException` nặng trong cache mãi mãi; có thể chỉ lưu metadata cần thiết.

## 5. Đăng ký listener ở đâu?

`PooledConnection` khai báo:

```java
void addStatementEventListener(StatementEventListener listener);

void removeStatementEventListener(StatementEventListener listener);
```

Ví dụ infrastructure code:

```java
PooledConnection physical = cpds.getPooledConnection();
StatementEventListener observer = new PoolStatementObserver();

physical.addStatementEventListener(observer);
try {
    // Pool manager vận hành các logical Connections và statements.
} finally {
    physical.removeStatementEventListener(observer);
    physical.close();
}
```

**Đây là pseudocode/minh họa, không standalone.** `cpds` cần là một `ConnectionPoolDataSource` được triển khai thật và `PoolStatementObserver` là implementation của bạn. Ứng dụng production không tự quản lý physical pool nếu framework đã làm điều đó; việc đóng PooledConnection trong finally ở đây là trách nhiệm **pool manager sau khi đã ngừng cho mượn**, không phải hành động của business request.

### 5.1. Đăng ký theo `PooledConnection`, không theo `DataSource`

`DataSource.getConnection()` trả `Connection` cho ứng dụng. Trong khi đó `ConnectionPoolDataSource.getPooledConnection()` được thiết kế cho connection-pool manager và trả `PooledConnection`.

Không viết:

```java
// Sai về API:
dataSource.addStatementEventListener(observer);
connection.addStatementEventListener(observer);
```

Vì `DataSource` và `java.sql.Connection` chuẩn **không có** methods như vậy. Chúng là methods trên **`javax.sql.PooledConnection`**.

### 5.2. Đăng ký và hủy listener

Pool manager phải hủy registration khi không còn quan tâm tới events, đặc biệt khi:
- Physical connection bị đóng/evict.
- Pool shutdown/reconfiguration.
- Listener thay thế bằng một instance khác.
- Tầng monitoring/plugin đã uninstall.

Không bỏ quên registration nếu nó giữ reference tới pool manager, metrics registry hoặc objects có lifecycle dài. Nếu listener được đăng ký nhiều lần, semantics có thể phụ thuộc implementation; tạo một registration policy rõ và test.

### 5.3. Đây là interface của `javax.sql`, không phải `jakarta.sql`

Trong Java SE 26, package vẫn là **`javax.sql`**, thuộc module `java.sql`. Việc các Jakarta EE APIs khác dùng prefix `jakarta.*` **không** biến các standard JDBC interfaces này thành `jakarta.sql`. Đừng đổi imports theo phỏng đoán.

## 6. Hai events trong trình tự thời gian

### 6.1. Đóng statement thông thường

```text
Application borrows logical Connection
              |
              v
   Connection.prepareStatement(sql)
              |
              v
       PreparedStatement
              |
              v
         execute...
              |
              v
   PreparedStatement.close()
              |
              v
   Driver detects statement close
              |
              v
 StatementEvent(source=PooledConnection,
                statement=that PreparedStatement,
                exception=null)
              |
              v
  listener.statementClosed(event)
              |
              v
   Pool considers cache/release
              |
              v
   Logical statement remains closed
```

Sơ đồ mô tả cơ chế sự kiện của JDBC. Thứ tự chi tiết giữa event, cache reset và physical cleanup có thể phụ thuộc driver/pool. **Không** dựa vào việc application nhận “thông báo trước” vì listener này thường thuộc infrastructure và được driver gọi nội bộ.

### 6.2. Prepared statement invalid

```text
Cached/borrowed PreparedStatement
              |
              v
      execute or related action
              |
              v
 Driver determines statement INVALID
              |
              v
 StatementEvent(source=PooledConnection,
                statement=invalid PreparedStatement,
                exception=SQLException)
              |
              v
listener.statementErrorOccurred(event)
              |
              v
Pool marks invalid / evicts cache entry
              |
              v
Driver throws corresponding SQLException
              |
              v
  Application catches SQLException
              |
              v
Rollback / retry / error response policy
```

**Điểm khác biệt trọng tâm:** callback `statementErrorOccurred` xảy ra **trước** exception được ném đến application, giúp pool dọn entry invalid sớm. Nó không đồng nghĩa query “tự retry thành công”, và không hứa một update thất bại là side-effect-free.

### 6.3. Đóng logical Connection

```text
Application: connection.close()
              |
              v
Driver/pool: ConnectionEvent
              |
              v
ConnectionEventListener.connectionClosed(...)
              |
              v
Physical connection recycled (pool-specific)
```

Không nhầm **connectionClosed** với **statementClosed**. Một connection đóng không đương nhiên làm listener nhận một `StatementEvent` riêng cho mọi SQL statement từng chạy; điều đó phụ thuộc driver/implementation và resource-close propagation.

## 7. `supportsStatementPooling` và `setPoolable`

Hai API liên quan nhưng **không giống** statement events:

### 7.1. `DatabaseMetaData.supportsStatementPooling()`

```java
boolean supported =
        connection.getMetaData().supportsStatementPooling();
```

Giá trị này cho biết **DBMS + JDBC driver có support statement pooling capability** theo metadata. Nó **không chứng minh**:
- Ứng dụng đã bật statement cache.
- Pool đang có cache entries.
- Đã đăng ký `StatementEventListener`.
- Cụ thể một prepared statement chắc chắn được reuse.
- Cache capacity còn trống.

Khi dùng `supportsStatementPooling`, nên kết hợp **pool configuration, driver documentation, metrics và integration tests**.

### 7.2. `Statement.setPoolable(boolean)`

Javadoc Java SE 26:

```java
statement.setPoolable(true);
boolean requested = statement.isPoolable();
```

`setPoolable` là một **hint/yêu cầu** với statement-pool manager; manager **có quyền không áp dụng**. Nó áp dụng cho internal driver statement cache lẫn external statement caches.

Default theo JDBC:
- `Statement` thông thường: **not poolable** khi tạo.
- `PreparedStatement`: **poolable** khi tạo.
- `CallableStatement`: **poolable** khi tạo.

Vì vậy “PreparedStatement mặc định poolable” **không có nghĩa** tất cả drivers/pools thực tế đang bật prepared statement caching hoặc sẽ reuse object đó.

### 7.3. Khi `setPoolable(false)` có tác dụng gì?

Nếu application biết một statement không thích hợp để reuse, có thể đặt:

```java
try (PreparedStatement ps =
        connection.prepareStatement("SELECT id FROM documents WHERE id = ?")) {
    ps.setPoolable(false);
    ps.setLong(1, documentId);
    try (ResultSet rs = ps.executeQuery()) {
        // Đọc kết quả.
    }
}
```

Đây là **snippet tích hợp**, cần `connection/documentId` và DB thật. `false` là hint, **không phải mệnh lệnh tuyệt đối**. Pool có thể quyết định giữ hoặc hủy entry theo cấu hình và policy.

Quan trọng: dù hint là false, `PreparedStatement.close()` vẫn đóng logical statement, và nếu infrastructure nhận `StatementEvent` thì callback đóng vẫn có thể được phát. **Pooling eligibility** khác **event notification**.

## 8. Mẫu implementation listener tối giản

Một listener dùng cho infrastructure có thể viết:

```java
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.StatementEvent;
import javax.sql.StatementEventListener;

public final class LoggingStatementListener
        implements StatementEventListener {

    @Override
    public void statementClosed(StatementEvent event) {
        PreparedStatement statement = event.getStatement();
        // Mark logical statement closed; pool decides whether to reuse
        // its underlying physical cache entry. Do not execute it here.
    }

    @Override
    public void statementErrorOccurred(StatementEvent event) {
        PreparedStatement statement = event.getStatement();
        SQLException failure = event.getSQLException();

        // Invalidate matching cache entry in the pool's own bookkeeping.
        // Do not catch/suppress SQL exception for application.
        if (failure != null) {
            String sqlState = failure.getSQLState();
            int vendorCode = failure.getErrorCode();
            // Record safe diagnostics/metrics only, not raw parameters.
        }
    }
}
```

Code trên là một **class Java có thể biên dịch** (lưu `LoggingStatementListener.java`), nhưng **không tự phát events** hoặc tạo database; nó phải được đăng ký bởi một `PooledConnection` implementation.

Không tự đóng `statement` trong `statementClosed` callback vì nó đã đang được đóng. Không gọi `statement.executeQuery()` trong `statementErrorOccurred` vì driver đã xác định invalid. Với pool thật, cache invalidation phải ánh xạ đúng statement entry của đúng physical connection và bảo vệ concurrency.

## 9. Chương trình thực hành hoàn chỉnh: mock PooledConnection + 41 kiểm thử

### 9.1. Thiết kế và phạm vi

Chương trình Java 17 dưới đây dựng các thành phần:

```text
FakePooledConnection
  │ PooledConnection proxy
  │
  ├── statementListeners:
  │    ├── PoolObserver
  │    └── AuditObserver (đăng ký rồi gỡ)
  │
  ├── connectionListeners:
  │    └── ConnectionObserver
  │
  └── getConnection()
       └── logical Connection proxy
            ├── getMetaData()
            │    └── supportsStatementPooling() -> true
            ├── prepareStatement("OK")
            │    └── PreparedStatement proxy
            │         ├── isPoolable() -> true
            │         ├── executeUpdate() -> 1
            │         └── close()
            │              └── statementClosed(event)
            ├── prepareStatement("INVALID")
            │    └── PreparedStatement proxy
            │         └── executeUpdate()
            │              ├── statementErrorOccurred(event)
            │              └── throw same SQLException
            ├── prepareStatement("ORDINARY_ERROR")
            │    └── SQLException without invalidation event
            └── createStatement()
                 └── Statement proxy (no StatementEvent)
```

Tập tests cố tình có:
- **Đăng ký hai listeners**, kiểm tra cả hai nhận event và việc `removeStatementEventListener` thật sự có tác dụng.
- Kiểm tra **source identity** qua `event.getSource() == pooled`.
- Kiểm tra **statement identity** qua `event.getStatement() == ps`.
- Event đóng có `getSQLException() == null`.
- Event invalid có **cùng SQLException object** mà `executeUpdate` ném sau callback.
- Tách **invalidating error** khỏi một **ordinary SQL error** không làm cached statement invalid.
- `setPoolable(false)` làm mock observer không chọn entry làm candidate nhưng callback đóng vẫn có.
- `Statement` thường không gửi `StatementEvent`.
- `ConnectionEventListener` nhận logical connection close, tách biệt khỏi statement events.
- `PooledConnection.close()` là đóng physical resource, không phải logical connection close.
- Một `StatementEvent` phải có source `PooledConnection` không null.

**Cảnh báo:** `PoolObserver.candidates` trong fixture chỉ là **tập markers** để chứng minh pool manager có thể ghi nhận một event. Nó **không phải một statement cache thật** và **không tái sử dụng Java `PreparedStatement` đã đóng**. Production pool phải quản lý riêng physical/driver statement objects và logical handles. Việc test cache candidate theo identity ở đây chỉ minh họa *quyết định* caching/eviction, không mô tả chi tiết lifecycle của driver statement vật lý.

### 9.2. File `StatementPoolingEventsDemo.java`

Lưu nguyên toàn bộ đoạn sau vào một file `StatementPoolingEventsDemo.java`.

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import java.sql.SQLSyntaxErrorException;
import java.sql.Statement;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.CopyOnWriteArrayList;
import javax.sql.ConnectionEvent;
import javax.sql.ConnectionEventListener;
import javax.sql.PooledConnection;
import javax.sql.StatementEvent;
import javax.sql.StatementEventListener;

public final class StatementPoolingEventsDemo {
    private static int passed;

    private static void check(String label, boolean ok) {
        if (!ok) throw new AssertionError("FAIL " + label);
        System.out.println("PASS " + label);
        passed++;
    }

    private static <T> T makeProxy(Class<T> type, InvocationHandler h) {
        return type.cast(Proxy.newProxyInstance(
                StatementPoolingEventsDemo.class.getClassLoader(),
                new Class<?>[] { type }, h));
    }

    private static Object objectMethod(
            Object proxy, Method m, Object[] args) {
        return switch (m.getName()) {
            case "equals" -> proxy == args[0];
            case "hashCode" -> System.identityHashCode(proxy);
            case "toString" -> m.getDeclaringClass().getSimpleName()
                    + "-mock";
            default -> throw new IllegalStateException(m.getName());
        };
    }

    static final class StatementState {
        final boolean prepared;
        final String sql;
        boolean closed;
        boolean invalid;
        boolean poolable;

        StatementState(boolean prepared, String sql) {
            this.prepared = prepared;
            this.sql = sql;
            this.poolable = prepared; // JDBC default hint
        }
    }

    static final class FakePooledConnection
            implements InvocationHandler {
        final PooledConnection pooled;

        final CopyOnWriteArrayList<StatementEventListener>
                statementListeners = new CopyOnWriteArrayList<>();

        final CopyOnWriteArrayList<ConnectionEventListener>
                connectionListeners = new CopyOnWriteArrayList<>();

        final Map<PreparedStatement, StatementState> states =
                Collections.synchronizedMap(new IdentityHashMap<>());

        boolean physicalClosed;

        FakePooledConnection() {
            pooled = makeProxy(PooledConnection.class, this);
        }

        StatementState stateOf(PreparedStatement ps) {
            return states.get(ps);
        }

        void notifyClosed(PreparedStatement ps) {
            StatementEvent event = new StatementEvent(pooled, ps);
            for (StatementEventListener l : statementListeners) {
                l.statementClosed(event);
            }
        }

        void notifyInvalid(PreparedStatement ps, SQLException error) {
            StatementEvent event =
                    new StatementEvent(pooled, ps, error);
            for (StatementEventListener l : statementListeners) {
                l.statementErrorOccurred(event);
            }
        }

        @Override
        public Object invoke(Object p, Method m, Object[] args)
                throws SQLException {
            if (m.getDeclaringClass() == Object.class) {
                return objectMethod(p, m, args);
            }

            return switch (m.getName()) {
                case "addStatementEventListener" -> {
                    statementListeners.add(
                            (StatementEventListener) args[0]);
                    yield null;
                }
                case "removeStatementEventListener" -> {
                    statementListeners.remove(
                            (StatementEventListener) args[0]);
                    yield null;
                }
                case "addConnectionEventListener" -> {
                    connectionListeners.add(
                            (ConnectionEventListener) args[0]);
                    yield null;
                }
                case "removeConnectionEventListener" -> {
                    connectionListeners.remove(
                            (ConnectionEventListener) args[0]);
                    yield null;
                }
                case "getConnection" -> {
                    if (physicalClosed) {
                        throw new SQLException("pool closed");
                    }
                    yield connection();
                }
                case "close" -> {
                    physicalClosed = true;
                    yield null;
                }
                default ->
                        throw new SQLFeatureNotSupportedException(
                                m.getName());
            };
        }

        DatabaseMetaData metadata() {
            return makeProxy(DatabaseMetaData.class, (p, m, args) -> {
                if (m.getDeclaringClass() == Object.class) {
                    return objectMethod(p, m, args);
                }
                if (m.getName().equals("supportsStatementPooling")) {
                    return true;
                }
                throw new SQLFeatureNotSupportedException(
                        m.getName());
            });
        }

        Connection connection() {
            return makeProxy(Connection.class,
                    new InvocationHandler() {
                boolean closed;

                @Override
                public Object invoke(
                        Object p, Method m, Object[] args)
                        throws SQLException {
                    if (m.getDeclaringClass() == Object.class) {
                        return objectMethod(p, m, args);
                    }

                    if (m.getName().equals("close")) {
                        if (!closed) {
                            closed = true;
                            ConnectionEvent event =
                                    new ConnectionEvent(pooled);
                            for (ConnectionEventListener l
                                    : connectionListeners) {
                                l.connectionClosed(event);
                            }
                        }
                        return null;
                    }

                    if (m.getName().equals("isClosed")) {
                        return closed;
                    }
                    if (closed) {
                        throw new SQLException(
                                "logical handle closed");
                    }

                    return switch (m.getName()) {
                        case "getMetaData" -> metadata();
                        case "prepareStatement" ->
                                newStatement(true, (String) args[0]);
                        case "createStatement" ->
                                newStatement(false, null);
                        default ->
                                throw new SQLFeatureNotSupportedException(
                                        m.getName());
                    };
                }
            });
        }

        Object newStatement(boolean prepared, String sql) {
            StatementState state =
                    new StatementState(prepared, sql);
            Class<?> type = prepared
                    ? PreparedStatement.class
                    : Statement.class;

            Object stmt = Proxy.newProxyInstance(
                    StatementPoolingEventsDemo.class.getClassLoader(),
                    new Class<?>[] { type },
                    new InvocationHandler() {

                @Override
                public Object invoke(
                        Object p, Method m, Object[] args)
                        throws SQLException {
                    if (m.getDeclaringClass() == Object.class) {
                        return objectMethod(p, m, args);
                    }

                    if (m.getName().equals("close")) {
                        if (!state.closed) {
                            state.closed = true;
                            if (state.prepared) {
                                notifyClosed((PreparedStatement) p);
                            }
                        }
                        return null;
                    }

                    if (m.getName().equals("isClosed")) {
                        return state.closed;
                    }
                    if (state.closed) {
                        throw new SQLException(
                                "statement handle closed");
                    }

                    switch (m.getName()) {
                        case "setPoolable" -> {
                            state.poolable = (Boolean) args[0];
                            return null;
                        }
                        case "isPoolable" -> {
                            return state.poolable;
                        }
                        case "executeUpdate" -> {
                            if (!state.prepared) {
                                throw new SQLFeatureNotSupportedException(
                                        "not a prepared query");
                            }

                            if ("INVALID".equals(state.sql)) {
                                SQLSyntaxErrorException error =
                                        new SQLSyntaxErrorException(
                                                "prepared plan invalid",
                                                "42P01");
                                state.invalid = true;
                                notifyInvalid(
                                        (PreparedStatement) p, error);
                                throw error; // Callback before throw.
                            }

                            if ("ORDINARY_ERROR".equals(state.sql)) {
                                throw new SQLException(
                                        "regular SQL error", "23505");
                            }

                            return 1;
                        }
                        default ->
                                throw new SQLFeatureNotSupportedException(
                                        m.getName());
                    }
                }
            });

            if (prepared) {
                states.put((PreparedStatement) stmt, state);
            }
            return stmt;
        }
    }

    static final class PoolObserver
            implements StatementEventListener {

        final FakePooledConnection pool;
        final Set<PreparedStatement> candidates =
                Collections.newSetFromMap(
                        new IdentityHashMap<>());
        final Set<PreparedStatement> invalid =
                Collections.newSetFromMap(
                        new IdentityHashMap<>());

        int closedCount;
        int invalidCount;
        StatementEvent lastClosed;
        StatementEvent lastError;

        PoolObserver(FakePooledConnection pool) {
            this.pool = pool;
        }

        @Override
        public void statementClosed(StatementEvent event) {
            closedCount++;
            lastClosed = event;

            PreparedStatement stmt = event.getStatement();
            StatementState state = pool.stateOf(stmt);
            if (!invalid.contains(stmt) && state.poolable) {
                candidates.add(stmt);
            }
        }

        @Override
        public void statementErrorOccurred(
                StatementEvent event) {
            invalidCount++;
            lastError = event;

            PreparedStatement stmt = event.getStatement();
            invalid.add(stmt);
            candidates.remove(stmt);
        }
    }

    static final class AuditObserver
            implements StatementEventListener {
        int closed;
        int invalid;

        @Override
        public void statementClosed(StatementEvent e) {
            closed++;
        }

        @Override
        public void statementErrorOccurred(StatementEvent e) {
            invalid++;
        }
    }

    static final class ConnectionObserver
            implements ConnectionEventListener {
        int closed;
        int errors;
        ConnectionEvent last;

        @Override
        public void connectionClosed(ConnectionEvent e) {
            closed++;
            last = e;
        }

        @Override
        public void connectionErrorOccurred(ConnectionEvent e) {
            errors++;
            last = e;
        }
    }

    public static void main(String[] args) throws Exception {
        FakePooledConnection backend =
                new FakePooledConnection();
        PooledConnection pooled = backend.pooled;

        PoolObserver poolEvents = new PoolObserver(backend);
        AuditObserver audit = new AuditObserver();
        ConnectionObserver connEvents =
                new ConnectionObserver();

        pooled.addStatementEventListener(poolEvents);
        pooled.addStatementEventListener(audit);
        pooled.addConnectionEventListener(connEvents);

        Connection logical = pooled.getConnection();

        check("driver-reports-pooling",
                logical.getMetaData()
                        .supportsStatementPooling());

        PreparedStatement first =
                logical.prepareStatement("OK");
        check("prepared-default-poolable",
                first.isPoolable());
        check("successful-prepared-execute",
                first.executeUpdate() == 1);

        first.close();
        check("closed-event-fired",
                poolEvents.closedCount == 1);
        check("closed-event-source-is-pooled",
                poolEvents.lastClosed.getSource() == pooled);
        check("closed-event-statement-identity",
                poolEvents.lastClosed.getStatement() == first);
        check("closed-event-exception-null",
                poolEvents.lastClosed.getSQLException() == null);
        check("closed-becomes-cache-candidate",
                poolEvents.candidates.contains(first));
        check("logical-prepared-closed", first.isClosed());

        first.close();
        check("double-close-does-not-repeat-event",
                poolEvents.closedCount == 1);
        check("second-listener-received-close",
                audit.closed == 1);

        pooled.removeStatementEventListener(audit);

        PreparedStatement invalid =
                logical.prepareStatement("INVALID");
        SQLException caught = null;
        boolean errorAlreadyNotified = false;

        try {
            invalid.executeUpdate();
        } catch (SQLException e) {
            caught = e;
            errorAlreadyNotified =
                    poolEvents.invalidCount == 1;
        }

        check("invalid-statement-throws",
                caught != null);
        check("invalid-error-before-exception",
                errorAlreadyNotified);
        check("invalid-error-event-source",
                poolEvents.lastError.getSource() == pooled);
        check("invalid-error-statement-identity",
                poolEvents.lastError.getStatement() == invalid);
        check("invalid-error-same-sql-exception",
                poolEvents.lastError.getSQLException() == caught);
        check("invalid-flag-seen",
                backend.stateOf(invalid).invalid);
        check("invalid-entry-evicted",
                poolEvents.invalid.contains(invalid)
                && !poolEvents.candidates.contains(invalid));

        invalid.close();
        check("invalid-close-event-still-fires",
                poolEvents.closedCount == 2);
        check("invalid-never-recached",
                !poolEvents.candidates.contains(invalid));
        check("removed-listener-no-more-events",
                audit.closed == 1 && audit.invalid == 0);

        PreparedStatement ordinary =
                logical.prepareStatement("ORDINARY_ERROR");
        int priorInvalidEvents = poolEvents.invalidCount;
        boolean ordinaryErrorThrown = false;

        try {
            ordinary.executeUpdate();
        } catch (SQLException expected) {
            ordinaryErrorThrown =
                    "23505".equals(expected.getSQLState());
        }

        check("ordinary-sql-error-thrown",
                ordinaryErrorThrown);
        check("ordinary-error-not-statement-invalidation",
                poolEvents.invalidCount == priorInvalidEvents);

        ordinary.close();
        check("ordinary-close-event",
                poolEvents.closedCount == 3);
        check("ordinary-close-candidate",
                poolEvents.candidates.contains(ordinary));

        PreparedStatement optedOut =
                logical.prepareStatement("OK");
        optedOut.setPoolable(false);
        check("setpoolable-false-hint",
                !optedOut.isPoolable());

        optedOut.close();
        check("optout-still-closed-event",
                poolEvents.closedCount == 4);
        check("optout-not-cached",
                !poolEvents.candidates.contains(optedOut));

        int beforePlainClose = poolEvents.closedCount;
        Statement plain = logical.createStatement();
        check("plain-statement-default-not-poolable",
                !plain.isPoolable());

        plain.close();
        check("plain-statement-does-not-fire-statement-event",
                poolEvents.closedCount == beforePlainClose);

        check("active-statement-listener-registered",
                backend.statementListeners
                        .contains(poolEvents));

        pooled.removeStatementEventListener(poolEvents);
        PreparedStatement afterRemoval =
                logical.prepareStatement("OK");
        afterRemoval.close();

        check("removed-listener-gets-no-event",
                poolEvents.closedCount == beforePlainClose);
        check("all-statement-listeners-removed",
                backend.statementListeners.isEmpty());

        int oldClosed = poolEvents.closedCount;
        logical.close();

        check("logical-connection-close-event",
                connEvents.closed == 1
                && connEvents.last.getSource() == pooled);
        check("logical-close-does-not-generate-statement-event",
                poolEvents.closedCount == oldClosed);
        check("logical-handle-is-closed",
                logical.isClosed());
        check("physical-still-open-after-logical-close",
                !backend.physicalClosed);

        pooled.close();
        check("pooled-close-marks-physical-closed",
                backend.physicalClosed);

        boolean noNewLogicalConnection = false;
        try {
            pooled.getConnection();
        } catch (SQLException expected) {
            noNewLogicalConnection = true;
        }
        check("cannot-borrow-after-physical-close",
                noNewLogicalConnection);
        check("connection-error-not-emitted-by-logical-close",
                connEvents.errors == 0);

        boolean nullSourceRejected = false;
        try {
            new StatementEvent(null, first);
        } catch (IllegalArgumentException expected) {
            nullSourceRejected = true;
        }
        check("event-requires-pooled-source",
                nullSourceRejected);

        System.out.println("passed=" + passed);
    }
}
```

### 9.3. Biên dịch và chạy

Đặt terminal tại folder có `StatementPoolingEventsDemo.java`:

```bash
javac --release 17 -encoding UTF-8 StatementPoolingEventsDemo.java
java StatementPoolingEventsDemo
```

Các lệnh này chạy trên Linux/macOS hoặc Windows PowerShell có JDK 17+. Không cần JDBC driver bên ngoài, cơ sở dữ liệu thật, HikariCP, Maven hay Gradle.

Lưu ý: Code chạy vì `PooledConnection`, `StatementEventListener`, `StatementEvent`, `ConnectionEventListener` thuộc module **`java.sql`** của JDK. Dynamic proxy ở đây **chỉ hiện thực methods được test**; các methods còn lại ném `SQLFeatureNotSupportedException`.

### 9.4. Stdout đã xác minh thực tế

```text
PASS driver-reports-pooling
PASS prepared-default-poolable
PASS successful-prepared-execute
PASS closed-event-fired
PASS closed-event-source-is-pooled
PASS closed-event-statement-identity
PASS closed-event-exception-null
PASS closed-becomes-cache-candidate
PASS logical-prepared-closed
PASS double-close-does-not-repeat-event
PASS second-listener-received-close
PASS invalid-statement-throws
PASS invalid-error-before-exception
PASS invalid-error-event-source
PASS invalid-error-statement-identity
PASS invalid-error-same-sql-exception
PASS invalid-flag-seen
PASS invalid-entry-evicted
PASS invalid-close-event-still-fires
PASS invalid-never-recached
PASS removed-listener-no-more-events
PASS ordinary-sql-error-thrown
PASS ordinary-error-not-statement-invalidation
PASS ordinary-close-event
PASS ordinary-close-candidate
PASS setpoolable-false-hint
PASS optout-still-closed-event
PASS optout-not-cached
PASS plain-statement-default-not-poolable
PASS plain-statement-does-not-fire-statement-event
PASS active-statement-listener-registered
PASS removed-listener-gets-no-event
PASS all-statement-listeners-removed
PASS logical-connection-close-event
PASS logical-close-does-not-generate-statement-event
PASS logical-handle-is-closed
PASS physical-still-open-after-logical-close
PASS pooled-close-marks-physical-closed
PASS cannot-borrow-after-physical-close
PASS connection-error-not-emitted-by-logical-close
PASS event-requires-pooled-source
passed=41
```

Đã biên dịch với `javac --release 17` trên OpenJDK 24 và chạy thành công: **41/41 checks PASS**.

### 9.5. Diễn giải kết quả kiểm thử

| Kiểm thử | Tình huống | Kết luận |
| --- | --- | --- |
| `driver-reports-pooling` | Metadata trả `true` | Capability tồn tại trong mock, chưa nói cache thật đã active |
| `prepared-default-poolable` | PreparedStatement mới | JDBC default hint là true |
| `successful-prepared-execute` | Execute SQL giả lập "OK" | Statement có thể thực thi mà không có invalidation event |
| `closed-event-fired` | Close logical prepared handle | Listener nhận callback |
| `closed-event-source-is-pooled` | Kiểm tra `getSource` | Nguồn là đúng PooledConnection |
| `closed-event-statement-identity` | Kiểm tra `getStatement` | Đúng PreparedStatement đã đóng |
| `closed-event-exception-null` | Close-only constructor | Không có SQLException đính kèm |
| `closed-becomes-cache-candidate` | Observer bookkeeping | Có thể đánh dấu entry eligible |
| `logical-prepared-closed` | Sau `ps.close` | App không dùng lại handle |
| `double-close-does-not-repeat-event` | Close hai lần | Mock không double-notify |
| `second-listener-received-close` | Có hai subscribers | Cả hai nhận event trong mock |
| `invalid-error-before-exception` | Invalidating execute | Callback chạy **trước** khi caller catch |
| `invalid-error-same-sql-exception` | So error object identity | Event mang đúng exception được ném |
| `invalid-entry-evicted` | Invalidation | Candidate bị loại bỏ |
| `invalid-never-recached` | Close sau invalidation | Không đưa entry invalid về candidate set |
| `ordinary-error-not-statement-invalidation` | SQL failure thông thường | Không mặc định coi mọi SQLException là invalidating |
| `setpoolable-false-hint` | Opt-out pooling | Pooling hint false |
| `optout-still-closed-event` | Opt-out rồi close | Hệ thống vẫn thấy close event |
| `plain-statement-does-not-fire-statement-event` | `createStatement` thường | Không coi plain Statement là PreparedStatement event |
| `removed-listener-gets-no-event` | Hủy registration | Không tiếp tục nhận event |
| `logical-connection-close-event` | `Connection.close` | Event thuộc `ConnectionEventListener` |
| `physical-still-open-after-logical-close` | Close logical handle | Physical mock vẫn tồn tại |
| `pooled-close-marks-physical-closed` | Pool manager close | Kết thúc physical resource |
| `event-requires-pooled-source` | `new StatementEvent(null,...)` | `IllegalArgumentException` đúng Javadoc |

**Đối chiếu với driver thật:** Một lỗi SQL thường có thể làm statement invalid ở một driver/version khác; kết luận “ordinary SQL error không làm invalid” là **behavior của fixture trong tình huống được thiết kế**, không phải một luật JDBC rằng mã SQLState `23` không bao giờ invalidates. Ngược lại, driver cũng có thể bắt lỗi nhưng không phát sự kiện nếu statement pooling integration không được triển khai. Cần test theo driver và pool thực tế.

## 10. Vì sao observer trong demo không phải cache thật?

Trong code `PoolObserver`:

```java
final Set<PreparedStatement> candidates =
        Collections.newSetFromMap(new IdentityHashMap<>());
final Set<PreparedStatement> invalid =
        Collections.newSetFromMap(new IdentityHashMap<>());
```

Khi `statementClosed` được gọi, observer ghi nhận **identity của logical statement** để mô phỏng quyết định cache. Khi `statementErrorOccurred` xảy ra, observer đánh dấu invalid và loại khỏi candidates. Cách đó minh họa nguyên tắc **“đừng reuse entry đã invalid”**.

Trong pool thực:
- Cần ánh xạ logical statement handle → driver prepared-statement resource / cache entry.
- Cache key thường phụ thuộc SQL text, schema, connection identity, result set options và driver settings.
- Cần xử lý cleanup state, liveness, transaction boundary, cache TTL/capacity, concurrency.
- Không được trả lại **cùng logical `PreparedStatement` đã closed** cho application như thể nó còn mở.
- Các error events có thể đến gần đồng thời với close. Pool cần tránh case **evicted rồi bị close reinsert**.
- Event source là `PooledConnection` nên các entries phải được scope theo physical connection tương ứng; không dùng statement identity từ pool A để xóa entry pool B.

Nếu muốn implement một statement cache production, đây là một bài toán infrastructure phức tạp; hãy dùng pool/driver được duy trì và test theo documentation. Demo của bài **không khuyến nghị tự xây cache** bằng Set của closed statements.

## 11. Chiến lược invalidation trong production

### 11.1. Khi nhận `statementErrorOccurred`

Pool manager nên có các bước logic:

1. Xác định `PooledConnection` nguồn qua `event.getSource()`.
2. Xác định PreparedStatement qua `event.getStatement()`.
3. Nhận `SQLException` để ghi diagnostics an toàn và biết driver đã phát hiện invalidation.
4. Đánh dấu cache entry liên quan là **invalid** theo identity/key đúng của pool.
5. Evict hoặc ngăn entry đó quay lại cache khi borrower close.
6. Giải phóng underlying statement resources theo quyền sở hữu của pool/driver.
7. Không làm mất `SQLException` application cần nhận; không retry query trong callback.

### 11.2. Khi nhận `statementClosed`

Pool manager nên:

1. Xác định entry (nếu pool có cache).
2. Nếu entry đã invalid → **không tái sử dụng**, phải dispose theo policy.
3. Nếu không invalid và ứng dụng/manager muốn pooling → cân nhắc caching.
4. Nếu cache đầy/disabled → đóng physical statement resource theo quyền sở hữu.
5. Không expose closed logical handle trở lại ứng dụng.

Có thể có thứ tự `statementErrorOccurred` rồi `statementClosed` cho cùng statement: demo đã test case này. Nếu listener viết `statementClosed` thành “always cache”, entry invalid sẽ quay lại cache. Vì thế **invalidation status phải thắng close event**.

### 11.3. Một SQLException không có nghĩa statement invalid

Ví dụ:
- Unique constraint violation.
- Dữ liệu bind không hợp lệ.
- SQL timeout/lock wait.
- Permission/transaction conflict.
- DDL làm cached plan stale.
- Lỗi driver/server connection.

**Không** tự suy tất cả các lỗi trên đều phải phát `statementErrorOccurred`. Chỉ khi driver **xác định PreparedStatement invalid** thì API event liên quan được sử dụng. Pool cũng có thể áp quy tắc eviction/health-check riêng, nhưng đó là **pool policy**, không phải tự động là JDBC StatementEvent contract.

Nếu connection vật lý hỏng, tầng `ConnectionEventListener.connectionErrorOccurred` và connection pool liveness policy có thể cần xử lý; evict một statement không thay được reconnect.

## 12. Liên hệ với ngoại lệ JDBC

Bài thuộc **Ngoại lệ JDBC**, nên cần hiểu cách exception được truyền:

```text
Driver detects invalid PreparedStatement
               |
               v
Constructs/holds SQLException
               |
               v
statementErrorOccurred(StatementEvent)
  -> getSQLException(): driver error
               |
               v
Driver throws SQLException to application
               |
               v
try/catch SQLException around execute...
               |
               v
Transaction rollback/recovery/business response
```

Listener **không ném lại SQLException hộ ứng dụng** và không thể chuyển một query lỗi thành query thành công.

Một application có thể nhận `SQLSyntaxErrorException`, `SQLRecoverableException`, `SQLTimeoutException` hoặc `SQLException` theo điều kiện. Tên subclass không tự cho biết statement cần evict hay không; Javadoc của `StatementEventListener` dựa vào **driver xác định invalid**. Pool không nên chỉ dùng `getSQLState()` để phát lại event do giả định.

### 12.1. Ví dụ driver-detected invalidation

Một database có thể invalidate prepared statement sau DDL thay đổi bảng, như Javadoc dùng làm ví dụ. Driver phát hiện prepared statement unusable và gọi:

```java
listener.statementErrorOccurred(
        new StatementEvent(pooledConnection, statement, error));
throw error;
```

Đây là **snippet mô tả hành vi của mock/driver**, không là code application nên tự chèn vào `catch(SQLException)`. Driver hoặc pool implementation mới là bên phát StatementEvent. App chỉ xử lý `SQLException` nhận được ở `execute`.

### 12.2. Query timeout có phải statementErrorOccurred không?

**Không mặc định.** Một timeout chỉ cho thấy thời gian thực thi statement đã vượt ngưỡng; driver có thể cancel thành công và prepared statement vẫn hợp lệ. Nhưng một timeout do connection hỏng cũng có thể làm resource invalid tùy driver.

Không dùng listener này như hệ thống telemetry cho mọi query timeout; dùng application tracing, metrics, JDBC exception handling và driver/pool-specific instrumentation.

### 12.3. Lỗi connection có phải statementErrorOccurred không?

Lỗi connection thường liên quan đến `ConnectionEventListener.connectionErrorOccurred` và pool's physical connection eviction policy. Một lỗi nghiêm trọng có thể làm nhiều statements trên cùng connection bị invalid, nhưng event mechanism và recovery scope khác.

Nếu underlying physical connection đã chết, retry cùng statement object thường không hợp lệ. Cần đóng borrowed handles và lấy connection mới theo recovery policy; không cố “cache lại” prepared statements trên kết nối hỏng.

## 13. Cách kiểm tra statement pooling có thực sự hoạt động

### 13.1. Metadata chỉ là một phần

```java
boolean supported = connection.getMetaData()
        .supportsStatementPooling();
```

Kết quả `true` chỉ nói driver/database support capability. Bạn còn cần biết pool configuration, statement cache enabled, limits, driver-side cache, underlying connection scope.

`Statement.isPoolable()` cũng chỉ cho biết flag/hint trên statement; nó không chứng minh cache hit.

### 13.2. Quan sát metrics

Nếu pool/driver cung cấp telemetry, hãy theo dõi:
- Prepared statement cache hits/misses.
- Number of cached entries theo physical connection.
- Statement close events.
- Invalidation events và evictions.
- Cache entry age, capacity, memory footprint.
- Physical connections idle/active.
- Query/prepare latency trước/sau bật caching.
- Number of invalid cached plan failures.
- SQL error rate và connection reset rate.

Không tự tạo một SQL text cache toàn app rồi suy nó tương đương prepared statement cache phía driver. Cache scope theo physical connection và session state có thể rất quan trọng.

### 13.3. Test DDL invalidation trên database thật

Ví dụ với test-only DB có hỗ trợ statement pooling:
1. Mở pooled connection, register listener của infrastructure.
2. Tạo prepared statement tham chiếu một table tạm.
3. Thực thi thành công và đóng logical statement.
4. Dùng DDL thay đổi/drop/recreate table theo transaction constraints của DB.
5. Mượn statement cùng SQL và làm driver phát hiện cached plan invalid.
6. Ghi event và SQLException thật.
7. Xác minh pool evict entry invalid; query sau chạy bằng statement mới nếu appropriate.
8. Kiểm tra connection vẫn khỏe hay cần reconnect, theo vendor behavior.

**Cần test isolation**. Không chạy destructive DDL trên production tables. Một số databases tự reprepare hoặc invalidate theo cơ chế khác và **không phát sự kiện đúng như scenario giả định**. Integration test phải chấp nhận behavior được tài liệu hóa của driver, không ép mọi DB có cùng events.

## 14. Concurrency, listener thread và tính an toàn

### 14.1. Callback chạy trên thread nào?

Javadoc của `StatementEventListener` mô tả notification contract, **không quy định listener luôn chạy trên một background thread riêng**. Một implementation có thể gọi callback ngay trên đường xử lý close/execute của application hoặc một thread nội bộ.

Vì vậy callback nên:
- Ngắn và non-blocking càng tốt.
- Không chờ một global lock dài hoặc làm I/O mạng nặng.
- Không gọi SQL lần nữa trên statement đã invalid.
- Không throw unchecked exceptions tùy ý làm gián đoạn driver callback path.
- Đồng bộ state cache đúng cách với nhiều connection/worker threads.
- Chỉ ghi metrics/logging an toàn, không serialize các `PreparedStatement` references ra ngoài.

Demo dùng `CopyOnWriteArrayList` để mô phỏng danh sách listeners và `IdentityHashMap` cho test identity. Đó là sự lựa chọn **single-thread fixture**. Một production cache không thể chỉ dùng `IdentityHashMap` không khóa rồi giả định safe khi callback đồng thời; cần concurrency strategy rõ ràng và test race conditions.

### 14.2. Race giữa invalidation và close

Một race có thể xảy ra:
- Thread A phát hiện statement invalid.
- Thread B hoặc cleanup path đóng logical statement.
- `statementClosed` handler thấy “poolable” và cố đưa entry vào cache.
- `statementErrorOccurred` sau đó evict hoặc ngược lại.

Tầng pool nên có **state transition** rõ, ví dụ `ACTIVE → CLOSING → INVALID/RELEASED`, bảo đảm **INVALID là trạng thái cấm reuse** bất kể event order. Một atomic state machine sẽ phù hợp hơn một cặp booleans không đồng bộ.

### 14.3. Kỹ thuật identity

Nếu pool phải theo dõi một prepared statement proxy cụ thể, object identity thường khác logical equality. `IdentityHashMap` trong fixture là một cách minh họa map theo identity thay vì tin `equals/hashCode` của proxy. Nhưng khi resource được recycle, cache key còn cần physical connection ID, SQL text và statement options; identity alone **không đủ** để quản lý toàn bộ cache production.

### 14.4. Hạn chế giữ reference lâu dài

`StatementEvent` chứa `PreparedStatement`, còn `getSource` chứa `PooledConnection`. Nếu listener gửi event object vào queue dài hạn hoặc giữ trong global metrics registry, nó có thể vô tình giữ physical resources sống lâu hơn cần thiết. Chỉ trích xuất metadata cần thiết, không cache raw events/Statements sau disposal.

## 15. Mẫu sử dụng chuẩn trong ứng dụng bình thường

Trong phần lớn business code, **không cần tự đăng ký StatementEventListener**. Hãy dùng:

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(
             "SELECT name FROM customers WHERE id = ?")) {
    ps.setLong(1, customerId);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            String name = rs.getString("name");
            // Xử lý tên khách hàng theo business rules.
        }
    }
}
```

Đây là **snippet tích hợp**, cần `javax.sql.DataSource`, imports từ `java.sql`, `customerId` và database schema thật. Logic kết nối và transaction thuộc policy ứng dụng.

Application cần:
- Đóng `PreparedStatement` bằng try-with-resources, **kể cả khi pool có cache**.
- Không giữ statement sau close hoặc giữa các requests.
- Không gọi `PooledConnection.close()` trực tiếp.
- Xử lý `SQLException` phù hợp, không dùng listener để “bắt mọi lỗi”.
- Để pool/driver làm statement caching/invalidation theo contract.

### 15.1. Nếu cần giám sát PreparedStatement errors?

Dùng instrumentation ở tầng query execution như tracing/metrics/JDBC proxy logging hoặc pool-specific metrics nếu mục tiêu là **mọi SQL errors**. `StatementEventListener` chỉ được thiết kế cho statement pooling lifecycle, không phải một callback chung cho mọi SQL operation.

### 15.2. Nếu không có pooling?

Không nên tự lắp listener phức tạp khi driver/pool không dùng `PooledConnection` statement event mechanism. Một `DriverManager.getConnection()` bình thường trả `Connection`; không có chuẩn API để gọi `connection.addStatementEventListener(...)` trên đó. Kiểm tra requirements thực sự trước khi thêm abstraction.

## 16. Lỗi thường gặp

**1. Đăng ký `StatementEventListener` lên `Connection` thay vì `PooledConnection`.**  
Sai API. Listener registration methods thuộc `javax.sql.PooledConnection`.

**2. Tưởng `StatementEventListener` được gọi với mọi `Statement` thông thường.**  
Không. Contract nói về `PreparedStatement` trong statement pool; đừng nhầm `Connection.createStatement()` với `prepareStatement()`.

**3. Tưởng mọi `SQLException` từ `PreparedStatement` là `statementErrorOccurred`.**  
Sai. Callback này dành cho trường hợp **driver xác định statement invalid**, không phải mọi query failure.

**4. Tưởng `statementClosed` đồng nghĩa cache hit hoặc statement chắc chắn được reuse.**  
Không. Callback chỉ phát sự kiện đóng; pool quyết định caching.

**5. Tưởng `statementErrorOccurred` thay thế application `catch(SQLException)`.**  
Không. Driver gọi callback trước rồi ném exception cho application.

**6. Tưởng `event.getSource()` là `PreparedStatement`.**  
Sai. `getSource()` là `PooledConnection`; `getStatement()` mới là PreparedStatement.

**7. Tưởng `getSQLException()` trên close-only event không bao giờ null.**  
Sai. Constructor đóng hai tham số dùng `null` cho exception.

**8. Nhận invalid event nhưng không evict cache entry.**  
Dễ trả lại stale statement sau close; đánh dấu invalid rồi loại cache.

**9. Luôn cache mọi statement khi nhận `statementClosed`.**  
Không kiểm tra invalid/poolable/capacity dễ đưa resource hỏng vào cache.

**10. Coi `setPoolable(false)` là lệnh bắt buộc pool phải tuân.**  
Không. Đây là hint, manager có quyền bỏ qua.

**11. Coi `PreparedStatement` mặc định poolable nghĩa cache tự bật.**  
Không. Metadata, config và implementation quyết định cache thực tế.

**12. Coi `supportsStatementPooling() == true` chứng minh có listener được đăng ký.**  
Không. Nó chỉ nói driver/database support capability.

**13. Đóng physical `PooledConnection` trong business request.**  
Không. Pool sở hữu physical connection; app chỉ close logical `Connection`.

**14. Giữ lại closed logical `PreparedStatement` để reuse trực tiếp.**  
Không. Handle đã đóng; pool có thể recycle underlying resource nhưng không được biến closed handle thành usable cho caller.

**15. Dùng `ConnectionEventListener` để thay `StatementEventListener`.**  
Hai events khác cấp quản lý và payload khác nhau.

**16. Bắt `SQLTimeoutException` rồi phát `statementErrorOccurred` thủ công.**  
Không đúng contract: timeout không tự chứng minh statement invalid, và driver/pool mới quản lý lifecycle event.

**17. Listener thực hiện I/O hoặc SQL blocking dài trong callback.**  
Có thể kéo dài close/execute path và tạo deadlock; giữ callback ngắn.

**18. Không đồng bộ dữ liệu cache giữa threads.**  
Dễ race invalidation/close, reuse stale entry. Áp dụng state machine/concurrency policy.

**19. Lưu raw `StatementEvent` lâu dài trong metrics/log queue.**  
Có thể giữ reference tới PreparedStatement/PooledConnection, dẫn tới resource retention.

**20. Không gỡ listener khi physical connection bị đóng.**  
Làm rò references/registrations tùy implementation; quản lý lifecycle có chủ đích.

**21. Cho rằng event luôn tới trước cả SQL exception do application bắt.**  
Chỉ có contract đó cho **driver-detected invalidation** của `statementErrorOccurred`, không phải mọi SQLException.

**22. Quên gọi `PreparedStatement.close()` vì nghĩ pool tự dọn.**  
Không. Caller phải giải phóng logical statement đúng scope.

**23. Tin rằng một test mock 41 PASS chứng minh driver production có statement cache thật.**  
Không. Mock chỉ chứng minh Java contracts và model; cần test pool/driver/server đúng phiên bản.

**24. Không phân biệt physical cache entry và logical statement identity.**  
Candidate marker trong demo không phải underlying prepared statement resource để app tái sử dụng.

**25. Giữ cache entry theo SQL text duy nhất trên mọi physical connections.**  
Prepared statements có thể gắn với session/schema/driver options; không dùng global SQL key đơn giản nếu driver không cho phép.

**26. Dùng `javax.sql` như một API cũ đã bị thay bởi `jakarta.sql`.**  
Sai. Các JDBC pool event interfaces vẫn ở `javax.sql` trong Java SE 26.

## 17. Checklist cho pool/driver integration

Trước khi triển khai statement pooling hoặc listener tùy biến:

- [ ] Dùng đúng `javax.sql.PooledConnection` từ infrastructure, không làm ứng dụng tự quản lý physical connections.
- [ ] Xác nhận driver/database support `DatabaseMetaData.supportsStatementPooling()` nhưng không coi nó là cache-enabled state.
- [ ] Xác định statement cache là driver-side, pool-side hay application-server-side.
- [ ] Đọc tài liệu driver/pool của **version đang chạy** về event dispatch, invalidation và cache.
- [ ] Đăng ký `StatementEventListener` đúng physical PooledConnection.
- [ ] Kiểm thử `statementClosed` mang `PooledConnection` nguồn và đúng PreparedStatement.
- [ ] Kiểm thử close-only `StatementEvent.getSQLException()` có thể null.
- [ ] Kiểm thử `statementErrorOccurred` có exception tương ứng trước khi SQL exception reaches application.
- [ ] Đảm bảo invalid entry không quay lại cache sau close.
- [ ] Không coi mọi lỗi SQL là invalidation, không hủy mọi cache entry một cách mù quáng.
- [ ] Kiểm tra `Statement.setPoolable` chỉ là hint và default của PreparedStatement/Statement khác nhau.
- [ ] Cấu hình capacity, eviction/TTL, reset statement state, metrics và physical connection scoping.
- [ ] Kiểm tra thread safety của listener/cache và các race giữa error/close/shutdown.
- [ ] Đóng logical `PreparedStatement` và `Connection` đúng scope; không để app đóng `PooledConnection`.
- [ ] Gỡ listener khi không còn sử dụng; không giữ raw StatementEvent references lâu dài.
- [ ] Dùng connection-event error path để xử lý physical connection failures; không thay bằng statement invalidation.
- [ ] Integration-test với DB, driver, pool và schema migration/DDL của production.
- [ ] Review performance khi bật statement caching: hits, misses, memory, session state, latency.

Checklist này dành cho những hệ thống **thực sự cần** quản lý statement pooling. Nếu ứng dụng chỉ thực thi SQL thông thường qua một pool đã được cấu hình, nên để framework quản lý listeners và không thêm code can thiệp.

## 18. Ma trận kiểm thử đề xuất

| Kiểm thử | Fixture cần có | Điều xác minh |
| --- | --- | --- |
| Register listener | `PooledConnection.addStatementEventListener` | Listener nhận sự kiện |
| Remove listener | `removeStatementEventListener` | Không nhận events tiếp theo |
| Two listeners | Hai subscribers | Cả hai được gọi khi còn đăng ký |
| Closed event | `PreparedStatement.close()` | `statementClosed`, nguồn và statement đúng |
| Close exception | `StatementEvent` 2-argument constructor | `getSQLException() == null` |
| Error event | Driver phát hiện invalid | `statementErrorOccurred` trước khi throw |
| Error identity | Event chứa SQLException | Object/fields trùng exception driver ném |
| Invalidation evicts | Cache candidate tồn tại | Candidate bị loại, không reuse invalid entry |
| Error then close | Statement invalid rồi close | Không reinsert invalid entry |
| Ordinary SQL failure | Unique constraint violation giả lập | Không tự gọi invalidation event |
| Default prepared hint | `PreparedStatement.isPoolable()` | true khi tạo |
| Opt out pooling | `setPoolable(false)` | Hint false; pool policy vẫn quyết định |
| Plain Statement | `Connection.createStatement()` | Không coi nó là PreparedStatement event |
| Logical connection close | `Connection.close` | `ConnectionEventListener.connectionClosed` |
| Physical connection close | `PooledConnection.close` | Physical resource closed trong pool |
| No new borrow after close | `PooledConnection` đã close | Driver/pool từ chối tạo logical handle |
| Event source not null | `new StatementEvent(null, ps)` | `IllegalArgumentException` |
| Production DDL | DB có prepared plan invalidation | Driver/pool-specific evict/reprepare behavior |
| Concurrent invalid/close | Hai threads/race | Invalid wins; không reuse stale entry |
| Cache full | Capacity reached | LRU/eviction hoặc close resources an toàn |
| Pool shutdown | Driver/pool shutdown | Listeners and cached resources cleaned |
| Pool version upgrade | New driver/pool version | Không regression callback/eviction semantics |

**Không viết tests giả định** mọi vendor chắc chắn emit StatementEvent trên một câu DDL đã chọn. Kiểm tra documentation của đúng driver trước, và chấp nhận vendor implementation có thể làm reprepare/cache invalidation ở lớp khác.

## 19. Bài tập tư duy

**Tình huống A:** App có `PreparedStatement` được lấy qua `Connection.prepareStatement`. Một câu lệnh bị unique-constraint violation. Có phải listener chắc chắn nhận `statementErrorOccurred` không?

**Không.** Driver chỉ gọi event này khi xác định prepared statement invalid. Dữ liệu vi phạm constraint không tự có nghĩa plan/resource đã invalid. Application vẫn bắt SQLException để xử lý constraint violation.

**Tình huống B:** `statementClosed` đã thêm entry vào candidates, sau đó `statementErrorOccurred` báo invalid. Có thể reuse entry không?

**Không.** Invalidation phải loại entry khỏi cache và ngăn reinsert. Cần đồng bộ và state machine đúng, đặc biệt khi callbacks concurrent.

**Tình huống C:** `StatementEvent.getSQLException() == null` trong close-only callback. Có phải driver quên gửi lỗi?

**Không.** Hai-argument `StatementEvent` constructor mặc định SQLException null. Event chỉ mô tả close, không phải invalidation error.

**Tình huống D:** `DatabaseMetaData.supportsStatementPooling() == true`, nhưng app không thấy statement cache hits. Có chắc driver lỗi?

**Không.** Capability khác configuration/active cache; có thể pool không bật statement caching, cache key không match hoặc capacity/memory policy không cho reuse.

**Tình huống E:** `PreparedStatement.setPoolable(false)` rồi gọi close. Có thể vẫn có `statementClosed` event không?

**Có thể.** `setPoolable` chỉ là hint về caching; sự kiện đóng là notification khác. Mock đã test case này.

**Tình huống F:** App gọi `connection.close()` trên pooled logical handle. Có chắc listener nhận `statementClosed` cho tất cả statements trước đây không?

**Không.** Đó là connection lifecycle event; statement close events phụ thuộc driver và các statements còn active hay không.

**Tình huống G:** `statementErrorOccurred` chạy trước exception được throw. Listener có nên tự retry SQL không?

**Không.** Nó là callback infrastructure để quản lý invalid resource. Retry theo transaction/business policy ở tầng thích hợp.

**Tình huống H:** Có thể tự sử dụng `StatementEventListener` thay vì application JDBC SQL exception handler không?

**Không.** Các callbacks chỉ quan sát statement pooling lifecycle; business code vẫn xử lý SQLException/rollback/error response.

## 20. Câu hỏi tự kiểm tra

**1. `StatementEventListener` nằm trong package nào?**  
`javax.sql`, module `java.sql`; không chuyển sang `jakarta.sql` trong Java SE 26.

**2. Hai methods của listener là gì?**  
`statementClosed(StatementEvent)` và `statementErrorOccurred(StatementEvent)`.

**3. Listener được đăng ký ở đâu?**  
`PooledConnection.addStatementEventListener(listener)`.

**4. Ai thường đăng ký listener này trong kiến trúc có pool?**  
Connection/statement pool manager hoặc infrastructure, không phải service business code thông thường.

**5. `statementClosed` được gọi khi nào?**  
Khi driver phát hiện một `PreparedStatement` liên quan đã đóng.

**6. `statementErrorOccurred` được gọi khi nào?**  
Khi driver phát hiện một `PreparedStatement` invalid, ngay trước khi ném SQLException liên quan cho application.

**7. `event.getSource()` trả gì?**  
`PooledConnection` nguồn phát event, ở dạng `Object` theo `EventObject` API.

**8. `event.getStatement()` trả gì?**  
`PreparedStatement` đã đóng hoặc invalid.

**9. `event.getSQLException()` có thể null không?**  
Có. Close-only constructor mặc định null.

**10. Có phải mọi SQLException từ execute đều kích hoạt `statementErrorOccurred`?**  
Không. Chỉ driver-detected statement invalidation theo contract.

**11. `supportsStatementPooling()` có đủ chứng minh pool đang reuse cached statements không?**  
Không. Nó chỉ là capability metadata.

**12. `setPoolable(false)` có bắt buộc pool không cache statement không?**  
Không tuyệt đối; đó là hint.

**13. Default `isPoolable` của `PreparedStatement` mới là gì?**  
`true` theo JDBC; plain `Statement` mặc định `false`.

**14. `StatementEventListener` có dùng thay `ConnectionEventListener` không?**  
Không. Hai listener theo dõi những loại resource khác nhau.

**15. Một `PreparedStatement` logical đã đóng có được app dùng lại không?**  
Không. Pool có thể tái sử dụng underlying resource, không phải closed logical handle của app.

**16. Nếu event invalid đến rồi event close, pool nên làm gì?**  
Không đưa entry invalid trở lại cache; invalidation phải thắng.

**17. Tại sao observer không nên lưu raw `StatementEvent` vô hạn?**  
Có thể giữ references tới `PooledConnection` và `PreparedStatement`, gây resource retention.

**18. Tại sao 41 PASS của mock chưa chứng minh database production support statement events?**  
Mock cố ý emit callbacks; driver/pool thật có semantics, configuration, vendor-specific caching và event delivery riêng.

## 21. Tài liệu chính thức hiện hành

- [Oracle Java SE 26 — `javax.sql.StatementEventListener`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/javax/sql/StatementEventListener.html): hai callbacks, invalidation notification trước SQLException, đóng statement và mục đích external statement pooling.
- [Oracle Java SE 26 — `javax.sql.StatementEvent`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/javax/sql/StatementEvent.html): constructors, `getStatement()`, `getSQLException()`, `getSource()` và yêu cầu PooledConnection nguồn.
- [Oracle Java SE 26 — `javax.sql.PooledConnection`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/javax/sql/PooledConnection.html): physical-vs-logical connection, listener registration/removal, connection/statement pooling.
- [Oracle Java SE 26 — `javax.sql.ConnectionEventListener`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/javax/sql/ConnectionEventListener.html): logical connection close và connection-error events.
- [Oracle Java SE 26 — `javax.sql.ConnectionEvent`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/javax/sql/ConnectionEvent.html): event của PooledConnection dành cho connection listener.
- [Oracle Java SE 26 — `javax.sql.ConnectionPoolDataSource`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/javax/sql/ConnectionPoolDataSource.html): nguồn tạo PooledConnection cho pool manager.
- [Oracle Java SE 26 — `javax.sql` package summary](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/javax/sql/package-summary.html): vai trò của connection pooling và statement pooling trong kiến trúc JDBC.
- [Oracle Java SE 26 — `java.sql.DatabaseMetaData`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/DatabaseMetaData.html#supportsStatementPooling()): statement pooling capability check.
- [Oracle Java SE 26 — `java.sql.Statement`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Statement.html#setPoolable(boolean)): `setPoolable/isPoolable` là hints; defaults của `Statement` và `PreparedStatement`.
- [Oracle Java SE 26 — `java.sql.PreparedStatement`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/PreparedStatement.html): typed prepared SQL statements, `close`, execution và SQL exceptions.
- [Oracle Java SE 26 — `java.sql.SQLException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLException.html): chain, SQLState, vendor error code; listener không thay thế business error handling.

**Ghi nhớ:** `StatementEventListener` là một phần của **infrastructure JDBC statement pooling**, không phải một global callback cho mọi lỗi SQL. `statementClosed` báo logical PreparedStatement đã đóng; `statementErrorOccurred` báo **driver-detected invalidation** và mang SQLException driver sắp ném. Pool phải phân biệt **closed/eligible** với **invalid/evicted**, tránh tái sử dụng stale cache entries, đồng thời để application xử lý SQLException/transactions theo chính sách riêng. Kiểm tra capability, pooling hints và driver/pool thực tế trước khi kết luận statement cache đã hoạt động.
