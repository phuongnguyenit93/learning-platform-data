# Truy cập API mở rộng của driver qua wrapper đúng kiểu trong JDBC

## 1. Bài toán và mục tiêu

Trong Java hiện đại, code ứng dụng thường nhận một `java.sql.Connection` từ `DataSource` hoặc `DriverManager`. Tuy nhiên object runtime có thể là:

- Kết nối do JDBC driver trực tiếp tạo.
- Logical connection handle do pool cấp.
- Proxy của framework transaction/monitoring.
- Một proxy lồng bên ngoài wrapper khác, cuối cùng mới đến connection của driver.

Khi cần gọi một **API mở rộng không thuộc JDBC chuẩn**, ví dụ pgJDBC `org.postgresql.PGConnection` để dùng LISTEN/NOTIFY hoặc COPY, ép kiểu trực tiếp vào vendor interface có thể thất bại dù driver bên trong thực sự có API đó. `Connection` chỉ mô tả contract chuẩn, **không bảo đảm lớp ngoài cùng implement vendor interface**.

Java cung cấp một lối đi chính thức: **`java.sql.Wrapper`** với `isWrapperFor(Class<?>)` và `unwrap(Class<T>)`. `Connection` extends `Wrapper`, nên ứng dụng có thể hỏi capability và lấy interface đúng kiểu, bất kể có một hoặc nhiều wrapper trung gian **nếu chúng triển khai đúng JDBC contract**.

Sau bài, bạn sẽ hiểu:

1. Sự khác biệt giữa `Connection` chuẩn, logical connection, driver delegate và vendor extension interface.
2. Vì sao `(VendorType) connection` và `connection instanceof VendorType` không thể phát hiện extension nằm dưới proxy.
3. Cách dùng `connection.isWrapperFor(ExpectedInterface.class)` và `connection.unwrap(ExpectedInterface.class)` đúng kiểu, bắt `SQLException` và chọn fallback.
4. Vì sao unwrap có thể trả **chính object, delegate hoặc proxy tương thích**, không nhất thiết là physical connection.
5. Cách chọn đúng public driver interface thay vì class implementation/internal.
6. Cách giữ lifetime của extension **bên trong lifetime của borrowed JDBC connection**, không đóng underlying connection sau lưng pool.
7. Cách kiểm thử hai tầng wrapper, positive/negative cases, lỗi SQL, connection close, pool/driver integration.
8. Cách đóng gói logic vendor-specific trong adapter mà business code không phụ thuộc toàn bộ vào driver.

Bài dùng kiến thức **còn áp dụng trên Java SE 26**, ưu tiên Java 17+. Ví dụ thực hành chính có thể biên dịch/chạy bằng JDK 17+ **không cần database hoặc thư viện ngoài**. Nó đã được test với `javac --release 17` trên OpenJDK 24 và **13/13 assertions PASS**. Mẫu pgJDBC sau đó là **snippet tích hợp**, phải có pgJDBC và PostgreSQL thật.

## 2. Giao diện JDBC chuẩn và driver extension

`java.sql.Connection` biểu diễn một session đến database. Nó cung cấp các phương thức chuẩn như:

- `createStatement()`, `prepareStatement(sql)` để truy vấn.
- `setAutoCommit(boolean)`, `commit()`, `rollback()` để quản lý transaction.
- `getMetaData()` để đọc JDBC database metadata.
- `setTransactionIsolation(level)` để cấu hình transaction isolation.
- `setSchema(...)`, `setReadOnly(...)` và các connection properties được chuẩn hóa.
- `close()` để kết thúc lifetime của logical/physical handle do caller đang sở hữu.

Nếu nhiệm vụ thực hiện được bằng `Connection` chuẩn, **không cần** truy cập object nội bộ của driver. Ví dụ muốn tắt auto-commit, hãy gọi `connection.setAutoCommit(false)`; không unwrap chỉ để sửa một trường nội bộ của driver.

Nhưng driver có thể cung cấp thêm capabilities chuyên biệt:

| Tính năng | JDBC chuẩn? | API vendor có thể cung cấp |
| --- | --- | --- |
| Execute SQL và prepared statements | Có | Không cần unwrap |
| Transaction `commit/rollback` | Có | Ưu tiên JDBC |
| PostgreSQL LISTEN/NOTIFY notifications | Không có extension tương đương đầy đủ trong `Connection` | pgJDBC `PGConnection.getNotifications()` |
| PostgreSQL COPY streaming API | Không có API COPY chuyên biệt trong `Connection` | pgJDBC `PGConnection.getCopyAPI()` |
| PostgreSQL replication API | Ngoài JDBC core | pgJDBC extension phù hợp |
| Driver-specific session/diagnostic methods | Tùy driver | Public interface vendor document |
| Quản lý pool logical/physical lifecycle | Không phải lệnh truy cập internal của ứng dụng | Pool/container chịu trách nhiệm |

**Lưu ý:** Dù `unwrap` là cơ chế chuẩn, method mà bạn gọi sau unwrap vẫn **không portable** giữa vendors. Không giả định một extension có cùng semantics trên PostgreSQL, Oracle, SQL Server hoặc MySQL.

## 3. Hợp đồng `java.sql.Wrapper`

`java.sql.Wrapper` công bố hai method:

```java
<T> T unwrap(Class<T> iface) throws SQLException;

boolean isWrapperFor(Class<?> iface) throws SQLException;
```

Đây là **chữ ký API**, không phải class Java standalone. `Connection`, `Statement`, `PreparedStatement`, `ResultSet`, `DataSource` và một số JDBC types khác đều hỗ trợ hợp đồng này qua inheritance.

### 3.1. `isWrapperFor` — kiểm tra capability

`connection.isWrapperFor(DriverFeature.class)` trả true khi receiver:

- Tự implement interface được yêu cầu; hoặc
- Là wrapper trực tiếp của object implement interface đó; hoặc
- Là wrapper gián tiếp qua một chuỗi delegates/proxies có thể cung cấp interface đó.

Ngược lại nó trả false khi không có interface phù hợp. Tuy nhiên **method này khai báo `throws SQLException`**, nên code phải xử lý lỗi khi JDBC implementation không thể xác định capability.

Javadoc Java SE 26 khuyến nghị `isWrapperFor` được implement rẻ hơn `unwrap`, giúp caller kiểm tra trước những lần unwrap có khả năng thất bại. Nhưng đây không phải phép kiểm tra phi chi phí, không thay thế timeout/connection health checks.

### 3.2. `unwrap` — trả object đúng type

`connection.unwrap(DriverFeature.class)` có generic type `T`, nên compiler biết kết quả là `DriverFeature`; không cần cast thủ công sang một implementation type sau đó.

Javadoc quy định kết quả có thể là:

1. Receiver nếu receiver implement interface.
2. Object bên trong wrapper implement interface.
3. **Proxy** của receiver hoặc delegate implement interface.
4. Kết quả truy vấn đệ quy qua delegate chain.

Vì vậy **không hứa hẹn object identity** và không hứa rằng bạn lấy physical connection.

Nếu không tìm thấy implementation phù hợp, `unwrap` ném **`SQLException`**. Đây là checked exception đúng ngữ cảnh JDBC; đừng dùng `ClassCastException` của direct cast để thay thế.

### 3.3. Quan hệ giữa hai phương thức

Theo contract, nếu `isWrapperFor(SomeInterface.class)` trả true thì `unwrap(SomeInterface.class)` với cùng interface **nên thành công trong trạng thái ổn định**. Song connection có thể đóng/lỗi giữa hai thao tác. Vì vậy:

```java
if (connection.isWrapperFor(DriverFeature.class)) {
    DriverFeature feature =
            connection.unwrap(DriverFeature.class);
    // Sử dụng feature bên trong lifetime của connection.
}
```

Đây là **đoạn minh họa** có `connection`, `DriverFeature` được khai báo ở scope thích hợp và caller xử lý `SQLException`. Logic đúng cần còn có nhánh unsupported và exception policy.

### 3.4. Truyền một interface chính xác

Hợp đồng `unwrap(Class<T>)` được tài liệu hóa cho **interface** mà bạn muốn sử dụng. Chọn **public driver extension interface** đúng version. Không chọn `connection.getClass()` vì đó chỉ là class runtime của wrapper ngoài cùng; không chọn class nội bộ bằng tên nhìn trong stack trace.

Một lỗi thường gặp:

```java
// Không phải cách lấy vendor feature:
Connection physical =
        connection.unwrap(Connection.class);
```

Vì proxy ngoài đã implement `Connection`, `unwrap(Connection.class)` có thể trả chính proxy đó. Đây **không phải** API để “lấy underlying physical socket” hay bypass pool.

## 4. Vì sao cast và instanceof không đủ?

Một chuỗi wrapper có thể là:

```text
        Application reference
            Connection
                |
                v
       Pool connection proxy
      implements Connection only
                |
                v
        Observability proxy
      implements Connection only
                |
                v
         Driver connection
      implements Connection and
           VendorFeature
```

Do đó:

```text
connection instanceof VendorFeature          = false
connection.isWrapperFor(VendorFeature.class)  = true
connection.unwrap(VendorFeature.class)        = valid vendor API
```

Cast trực tiếp:

```java
VendorFeature feature = (VendorFeature) connection;
```

có thể gây `ClassCastException`. `instanceof` chỉ kiểm tra object **ngoài cùng**; nó không duyệt các delegates.

Dùng `isWrapperFor`/`unwrap` theo contract tốt hơn vì:

- Không phụ thuộc tên class pool.
- Cho phép wrapper chain nhiều tầng.
- Trả type compile-time chính xác.
- Báo unsupported qua JDBC semantics thay vì cast thất bại.
- Có thể dùng tương tự trên các JDBC types khác có `Wrapper`.

**Điều kiện:** Wrapper implementation phải hỗ trợ đúng interface và delegate lookup. Nếu pool chặn hoặc không expose extension, đừng cố phá abstraction bằng reflection/truy cập field nội bộ. Kiểm tra driver/pool config và chọn fallback/giải pháp công khai.

## 5. Chọn public driver API đúng kiểu

Ví dụ thực tế còn đang được duy trì: pgJDBC định nghĩa **`org.postgresql.PGConnection`**, một public extension interface cho các tính năng PostgreSQL. `PGConnection` **không tự extends `java.sql.Connection`**; implementation driver connection có thể implement cả hai interfaces.

Mẫu:

```java
org.postgresql.PGConnection pg =
        connection.unwrap(org.postgresql.PGConnection.class);
```

Đoạn này **không thuộc JDK-only**: nó cần dependency pgJDBC đúng version. `connection` phải thực sự đến từ driver PostgreSQL thông qua kết nối đang mở, có thể qua pool.

Không nên dựa vào concrete class `org.postgresql.jdbc.PgConnection` hoặc class proxy của pool. `PGConnection` là public interface được pgJDBC document; dùng type mà vendor cam kết hỗ trợ.

Các driver khác có API extension riêng:
- Oracle JDBC có một số `oracle.jdbc.*` extension interfaces/classes được công bố.
- Microsoft JDBC Driver for SQL Server có public `SQLServer...` types/extension methods.
- Các driver có thể không cung cấp bất kỳ extension nào cho tính năng bạn muốn.

**Đừng viết code đoán tên type vendor**. Tham khảo chính xác Javadocs của driver đang chạy. Nếu ứng dụng hỗ trợ nhiều DB, nên đóng gói kiến thức vendor trong một adapter, không import vendor type vào mọi service.

### Compile-time vs runtime dependency

Code gọi `PGConnection.class` cần **pgJDBC JAR lúc biên dịch**. Runtime cũng phải tải đúng phiên bản tương thích. Nếu class version khác nhau:

- `NoClassDefFoundError` có thể do thiếu dependency.
- `NoSuchMethodError` có thể do compile với API mới nhưng chạy JAR cũ.
- Hai class loaders có thể tải cùng tên API thành **hai `Class` objects khác nhau**, khiến `unwrap` không nhận diện được type mong muốn.
- Driver implementation và pool có thể thay đổi wrapper behavior giữa releases.

Nên pin/truy vết dependency versions, test artifact triển khai cuối và tránh duplicated driver JARs.

## 6. Ví dụ Java 17+ đầy đủ: hai tầng wrapper và typed unwrap

Demo tạo:

- `driver`: dynamic proxy implement `Connection` **và** `DriverFeature`.
- `inner`: proxy chỉ implement `Connection`, wrap `driver`.
- `outer`: proxy chỉ implement `Connection`, wrap `inner`.
- `MissingFeature`: interface không có object nào trong chain implement.

Không có database thật; `java.lang.reflect.Proxy` được dùng để viết một mô phỏng có thể chạy với ít code hơn so với việc hiện thực toàn bộ methods của `Connection`.

### 6.1. File `WrapperDemo.java`

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;

public final class WrapperDemo {
    // An extension interface need not extend Connection.
    public interface DriverFeature {
        String driverTag() throws SQLException;
    }
    public interface MissingFeature { }

    private static int passed;

    private static void check(String name, boolean ok) {
        if (!ok) throw new AssertionError("FAIL " + name);
        System.out.println("PASS " + name);
        passed++;
    }

    private static final class Layer implements InvocationHandler {
        private final Connection downstream;
        private final boolean driver;
        private boolean closed;

        Layer(Connection downstream, boolean driver) {
            this.downstream = downstream;
            this.driver = driver;
        }

        static Connection create(Connection downstream, boolean driver) {
            Class<?>[] apis = driver
                    ? new Class<?>[]{Connection.class, DriverFeature.class}
                    : new Class<?>[]{Connection.class};

            return (Connection) Proxy.newProxyInstance(
                    WrapperDemo.class.getClassLoader(),
                    apis,
                    new Layer(downstream, driver));
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            String name = method.getName();

            if (method.getDeclaringClass() == Object.class) {
                return switch (name) {
                    case "equals" -> proxy == args[0];
                    case "hashCode" -> System.identityHashCode(proxy);
                    case "toString" -> driver
                            ? "driver-mock" : "wrapper-mock";
                    default -> throw new IllegalStateException(name);
                };
            }

            if (name.equals("isClosed")) {
                return closed;
            }

            if (name.equals("close")) {
                if (!closed) {
                    closed = true;
                    if (downstream != null) downstream.close();
                }
                return null;
            }

            if (closed) {
                throw new SQLException("Connection handle is closed");
            }

            if (name.equals("isWrapperFor")) {
                Class<?> iface = (Class<?>) args[0];
                return iface.isInstance(proxy)
                        || (downstream != null
                        && downstream.isWrapperFor(iface));
            }

            if (name.equals("unwrap")) {
                Class<?> iface = (Class<?>) args[0];
                if (iface.isInstance(proxy)) return iface.cast(proxy);
                if (downstream != null) return downstream.unwrap(iface);
                throw new SQLException("Unsupported interface: "
                        + iface.getName());
            }

            if (name.equals("driverTag") && driver) {
                return "mock-driver/1";
            }

            throw new SQLFeatureNotSupportedException(
                    "Not a database: " + name);
        }
    }

    public static void main(String[] args) throws SQLException {
        Connection driver = Layer.create(null, true);
        Connection inner = Layer.create(driver, false);
        Connection outer = Layer.create(inner, false);

        try (Connection borrowed = outer) {
            boolean failedCast = false;
            try {
                DriverFeature ignored = (DriverFeature) borrowed;
            } catch (ClassCastException expected) {
                failedCast = true;
            }

            check("direct-cast-fails", failedCast);
            check("generic-connection",
                    borrowed instanceof Connection);
            check("typed-wrapper-detects-feature",
                    borrowed.isWrapperFor(DriverFeature.class));
            check("unwrap-is-typed",
                    "mock-driver/1".equals(
                            borrowed.unwrap(DriverFeature.class)
                                    .driverTag()));
            check("two-hop-wrapper",
                    inner.isWrapperFor(DriverFeature.class));
            check("unwrap-connection-interface",
                    borrowed.isWrapperFor(Connection.class)
                    && borrowed.unwrap(Connection.class)
                            instanceof Connection);
            check("missing-feature-reported",
                    !borrowed.isWrapperFor(MissingFeature.class));

            boolean throwsSql = false;
            try {
                borrowed.unwrap(MissingFeature.class);
            } catch (SQLException expected) {
                throwsSql = true;
            }
            check("missing-unwrap-throws-sql", throwsSql);

            check("driver-feature-different-from-connection",
                    !Connection.class.isAssignableFrom(
                            DriverFeature.class));
            check("open-during-scope",
                    !borrowed.isClosed() && !driver.isClosed());
        }

        check("outer-closed-after-scope", outer.isClosed());
        check("delegate-closed-in-demo", driver.isClosed());

        boolean deniedAfterClose = false;
        try {
            driver.unwrap(DriverFeature.class).driverTag();
        } catch (SQLException expected) {
            deniedAfterClose = true;
        }
        check("extension-handle-after-close-rejected",
                deniedAfterClose);

        System.out.println("passed=" + passed);
    }
}
```

### 6.2. Lệnh biên dịch và chạy

Trong thư mục chứa file:

```bash
javac --release 17 -encoding UTF-8 WrapperDemo.java
java WrapperDemo
```

Dùng được trên Linux/macOS hoặc Windows PowerShell khi có JDK 17+ trên PATH.

### 6.3. Stdout chính xác đã xác minh

```text
PASS direct-cast-fails
PASS generic-connection
PASS typed-wrapper-detects-feature
PASS unwrap-is-typed
PASS two-hop-wrapper
PASS unwrap-connection-interface
PASS missing-feature-reported
PASS missing-unwrap-throws-sql
PASS driver-feature-different-from-connection
PASS open-during-scope
PASS outer-closed-after-scope
PASS delegate-closed-in-demo
PASS extension-handle-after-close-rejected
passed=13
```

Code được biên dịch `javac --release 17` và chạy trên OpenJDK 24, tất cả **13/13 assertions PASS**.

### 6.4. Hiểu kết quả theo contract

| Test | Ý nghĩa |
| --- | --- |
| `direct-cast-fails` | Outer proxy không implement extension dù driver bên trong có. |
| `generic-connection` | Outer vẫn là `Connection` từ góc nhìn application. |
| `typed-wrapper-detects-feature` | `isWrapperFor` đi qua delegate chain. |
| `unwrap-is-typed` | `unwrap` trả đúng `DriverFeature`, gọi được `driverTag`. |
| `two-hop-wrapper` | Một wrapper trung gian cũng support extension bên trong. |
| `unwrap-connection-interface` | Outer implement `Connection`, nên có thể tự đáp ứng interface này. |
| `missing-feature-reported` | Unsupported interface được báo false. |
| `missing-unwrap-throws-sql` | Khi không tìm thấy interface, unwrap ném `SQLException`. |
| `driver-feature-different-from-connection` | Extension không buộc phải extends `Connection`. |
| `open-during-scope` | Borrowed handle đang mở trong try block. |
| `outer-closed-after-scope` | Try-with-resources gọi close trên outer. |
| `delegate-closed-in-demo` | Mock triển khai close propagation qua delegates. |
| `extension-handle-after-close-rejected` | Mock báo lỗi khi dùng feature sau close. |

**Không nhầm demo với pool thật:** `Layer.close` ở đây chủ động đóng mọi mock layer để test. Pool thực tế thường đóng **logical handle** rồi **tái sử dụng physical connection**; không được sao chép nguyên handler này thành connection pool.

## 7. Vì sao demo dùng `java.lang.reflect.Proxy`?

`Connection` có nhiều phương thức. Viết một class implement toàn bộ chỉ để minh họa hai methods của `Wrapper` sẽ làm loãng kiến thức. Java dynamic proxies cho phép chọn interfaces mà runtime object implement:

```java
Class<?>[] driverApis = {
    Connection.class, DriverFeature.class
};
Class<?>[] wrapperApis = {
    Connection.class
};
```

`Proxy.newProxyInstance(...)` sẽ tạo object với đúng interfaces; `InvocationHandler.invoke` nhận các method calls.

Khi proxy là `outer` mà caller yêu cầu `DriverFeature.class`:

1. `iface.isInstance(outer)` là false.
2. `outer` gọi `inner.isWrapperFor(iface)` hoặc `inner.unwrap(iface)`.
3. `inner` cũng không implement feature, tiếp tục tới `driver`.
4. `driver` implement feature nên trả đúng proxy typed.
5. Caller dùng `DriverFeature` mà không cast outer.

Nếu yêu cầu `MissingFeature.class`, cả ba đều không implement; `isWrapperFor` trả false và `unwrap` cuối chain ném `SQLException`.

Trong ứng dụng thực tế, pool/proxy có logic phức tạp về statements, transaction, instrumentation, session reset. Demo không thực hiện SQL và ném `SQLFeatureNotSupportedException` với methods ngoài phạm vi. Đây là **mô phỏng contract**, không phải production JDBC driver.

## 8. Tích hợp thực tế với pgJDBC

`org.postgresql.PGConnection` là một ví dụ tốt vì nó là public extension interface. Để code Java compile bạn cần pgJDBC dependency đúng version; để code chạy cần PostgreSQL server và connection thực.

### 8.1. Helper yêu cầu PGConnection

```java
import java.sql.Connection;
import java.sql.SQLException;
import org.postgresql.PGConnection;

static PGConnection requirePg(Connection connection)
        throws SQLException {
    if (!connection.isWrapperFor(PGConnection.class)) {
        throw new SQLException(
                "This connection does not expose pgJDBC PGConnection");
    }
    return connection.unwrap(PGConnection.class);
}
```

Đây là **method minh họa**, phải đặt trong class và có runtime dependency pgJDBC. Đừng dùng nó như một ví dụ JDK-only; `org.postgresql.*` không thuộc `java.sql`.

Có thể thêm fallback nếu feature là tùy chọn, hoặc fail rõ ràng nếu ứng dụng bắt buộc dùng nó.

### 8.2. LISTEN/NOTIFY

pgJDBC hiện hành có `PGConnection.getNotifications()` và overload `getNotifications(int timeoutMillis)`. Với connection còn mở:

```java
import java.sql.Connection;
import java.sql.Statement;
import org.postgresql.PGConnection;
import org.postgresql.PGNotification;

// Bên trong method có Connection conn và PostgreSQL server thực:
PGConnection pg = conn.unwrap(PGConnection.class);

try (Statement stmt = conn.createStatement()) {
    stmt.execute("LISTEN orders_changed");
}

PGNotification[] received = pg.getNotifications();
for (PGNotification n : received) {
    System.out.println(n.getName()
            + ": " + n.getParameter());
}
```

Đây là **snippet tích hợp, không standalone**. Nó không có stdout cố định: số notifications phụ thuộc server/session/transactions và có thể bằng không. Nếu ứng dụng không có PostgreSQL connection hoặc pgJDBC dependency, code không chạy.

Tài liệu pgJDBC mô tả không có background reader thread riêng cho notifications; ứng dụng cần gọi `getNotifications` để thu những events đã nhận. Overload timeout có thể **block**; `timeoutMillis == 0` có thể chờ vô hạn. Đừng gọi chế độ chờ vô hạn trong HTTP request thread. Với event processing production, thiết kế dedicated connection, cancel/timeouts, retry và lifecycle riêng.

### 8.3. COPY API

`PGConnection.getCopyAPI()` cho phép dùng COPY streaming. Snippet:

```java
PGConnection pg = conn.unwrap(PGConnection.class);
org.postgresql.copy.CopyManager copy = pg.getCopyAPI();
```

Mã này cũng cần pgJDBC dependency/connection thật; muốn thực hiện COPY còn cần SQL, stream input/output và exception handling riêng. Đừng dùng COPY extension chỉ vì có thể unwrap nếu chuẩn `PreparedStatement` đã đáp ứng nhu cầu.

### 8.4. Vendor interface không phải physical connection ownership

Dù pgJDBC cung cấp PGConnection, object được unwrap **không tự mang quyền quản lý physical connection**. Trong pool:

```java
try (Connection conn = dataSource.getConnection()) {
    PGConnection pg = conn.unwrap(PGConnection.class);
    // Gọi API PostgreSQL ngay trong scope này.
}
```

Đây là snippet tích hợp cần `dataSource` được cấu hình và pgJDBC. Try-with-resources đóng **borrowed handle**. Không giữ `pg` sau block, không đóng underlying delegate độc lập.

## 9. Logical connection và physical connection khác nhau

### 9.1. Connection pool hoạt động thế nào?

Theo hợp đồng `javax.sql.PooledConnection`, pool quản lý physical database connections và trao các **logical Connection handles** cho application. Khi application gọi `close()` trên logical handle, pool nhận thông báo và có thể **recycle physical connection** thay vì đóng socket.

Vì vậy:

- **Application sở hữu** borrowed logical handle trong một scope.
- **Pool sở hữu** physical connection và session lifecycle.
- **Driver extension** nhận từ unwrap chỉ được dùng trong phạm vi hợp lệ của borrowed handle.
- `close()` physical connection trực tiếp có thể phá pool, gây lỗi connection reuse hoặc leak.

Không hiểu `unwrap(Connection.class)` là “lấy physical”. Kết quả thậm chí có thể là chính pool proxy.

### 9.2. Try-with-resources vẫn là mặc định đúng

```java
try (Connection conn = dataSource.getConnection()) {
    // Standard JDBC operations
    // Optional driver extension access
}
```

Đây là snippet yêu cầu một `javax.sql.DataSource` thật. Nó bảo đảm borrowed connection handle được close dù logic bên trong ném exception, theo semantics `AutoCloseable`.

Với transaction do app quản lý, phải commit/rollback trước khi close theo policy. Javadoc `Connection.close` nhấn mạnh hành vi khi transaction đang mở có thể phụ thuộc implementation. Nếu framework quản lý transaction, đừng tự commit/rollback/đổi autoCommit ngoài quy định.

### 9.3. Không cache object unwrapped ngoài scope

Sai về lifetime:

```java
// Ý tưởng sai: cache PGConnection trong singleton rồi
// dùng ở request khác sau khi connection đã trả về pool.
```

Reference extension có thể trỏ tới physical resource đang được request khác dùng hoặc đã bị đóng. Hậu quả:
- Race giữa requests và transaction boundaries.
- Session state contamination.
- Gọi API trên connection đã invalid.
- Vượt chính sách access/monitoring của wrapper.
- Sai semantics của pool retry/reset.

**Quy tắc:** Mượn connection → unwrap → dùng feature → hoàn tất transaction → đóng borrowed handle. Không cất extension làm singleton field hay trả về từ method nếu chính method đã close logical handle.

## 10. Đừng phá các kiểm soát của wrapper

Một pool hoặc framework có thể bọc methods chuẩn JDBC để theo dõi:
- Transaction boundaries, auto-commit, commit/rollback.
- Metrics, spans, logging.
- Query timeout/cancellation.
- Resource leaks, session cleanup.
- Authentication/authorization ở tầng ứng dụng.

Gọi trực tiếp vendor-specific API trên underlying object có thể **không đi qua tất cả hooks** đó. Vì vậy:

1. Chỉ dùng extension khi có yêu cầu rõ.
2. Ưu tiên `Connection` chuẩn cho những tác vụ đã chuẩn hóa.
3. Không dùng reflection để lấy field delegate private của pool.
4. Không gọi driver-specific close/abort/configure làm mất đồng bộ với pool.
5. Không chia sẻ một borrowed `Connection` giữa threads nếu driver/pool không document thread safety.
6. Với COPY/replication, giới hạn kích thước stream, timeout và connection lifetime.
7. Với notifications, dùng listener lifecycle được quản lý; không block request threads vô hạn.
8. Ghi log failures mà không để lộ database URL chứa credentials hoặc dữ liệu nhạy cảm.

`unwrap` là cổng truy cập type-safe, **không** phải cách né sandbox/transaction policy.

## 11. Những JDBC objects khác hỗ trợ `Wrapper`

Không chỉ `Connection`. Nhiều interfaces JDBC kế thừa `Wrapper`:

| Receiver | Có thể unwrap khi | Cần tránh |
| --- | --- | --- |
| `Connection` | Extension của database session | Nhầm với physical pool connection |
| `Statement` | Driver-specific statement capability | Dùng interface thuộc Connection |
| `PreparedStatement` | Extension của prepared statement | Bỏ parameter binding/transaction policy |
| `CallableStatement` | Extension của callable statement | Dựa vào unsupported vendor call |
| `ResultSet` | ResultSet-specific optimization | Giả định nó expose connection feature |
| `DataSource` | DataSource/pool-specific public interface | Dùng như bypass pool lifecycle |
| `DatabaseMetaData` | Vendor-specific metadata | Cast vào implementation internal |

Các `Vendor...` types không phải lúc nào cũng có. Hãy tra **đúng extension của receiver tương ứng**. Việc `ResultSet` là Wrapper không có nghĩa nó cung cấp `PGConnection`. Dùng đúng nơi tính năng được vendor document.

### isWrapperFor trên DataSource có giống Connection không?

Cả hai dùng interface `Wrapper`, nhưng **không cùng object**. Một `DataSource` có thể expose API cấu hình pool, còn `Connection` expose API driver/session. Không nên gọi `dataSource.unwrap(PGConnection.class)` chỉ vì connection mà nó tạo đến PostgreSQL; `PGConnection` thường là extension của `Connection`.

## 12. Thiết kế adapter để giảm phụ thuộc vendor

Một ứng dụng chỉ nhắm PostgreSQL có thể gọi PGConnection ở tầng persistence. Nếu muốn hỗ trợ nhiều databases, tốt hơn là tách interface nghiệp vụ:

```java
public interface DatabaseNotifications {
    java.util.List<String> readPending()
            throws java.sql.SQLException;
}
```

Đây là **interface minh họa**, chưa có implementation. Một implementation của PostgreSQL có thể nhận borrowed connection, unwrap PGConnection và lấy pending events. Những database khác có thể implement bằng cơ chế khác hoặc báo unsupported.

Lợi ích:
- Business logic không cần import `org.postgresql.*`.
- Có nơi tập trung capability detection và diagnostics.
- Dễ test fallback trên non-PostgreSQL database.
- Dễ nâng driver/pool versions.
- Có thể quản lý timeout/transaction/connection lifetime ở một boundary.

### Capability là optional hay required?

Nếu optional, code có thể:

```java
if (conn.isWrapperFor(DriverFeature.class)) {
    DriverFeature ext = conn.unwrap(DriverFeature.class);
    // Fast path qua driver extension.
} else {
    // API JDBC chuẩn hoặc behavior được product cho phép.
}
```

Đây là snippet minh họa dùng `DriverFeature` đã khai báo trong fixture. Nếu feature là **bắt buộc**, đừng fallback im lặng sang logic sai khác. Có thể ném `SQLFeatureNotSupportedException` hoặc một exception domain mô tả không đáp ứng capability.

Dù dùng check trước, cả `isWrapperFor` và `unwrap` vẫn cần exception policy; không lẫn “không hỗ trợ” với “kết nối bị lỗi”.

## 13. Kiểm thử unit và integration

### 13.1. Unit test nguyên lý

Fixture đã kiểm thử:
- Outer proxy không implement vendor interface, direct cast thất bại.
- Hai wrappers vẫn tìm thấy extension ở delegate.
- `isWrapperFor(Connection.class)` true.
- `unwrap(DriverFeature.class)` có method gọi được.
- Interface không hỗ trợ → false/SQLException.
- Connection được close bởi try-with-resources.
- Mock không cho dùng extension sau close.

Nó **không cần** database và không chịu tác động của pool version. Đây là kiểm thử contract ở mức cơ chế.

### 13.2. Integration test theo driver/pool thật

| Trường hợp | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Driver trực tiếp | JDBC connection không qua pool | Vendor interface nhận diện đúng |
| Pool connection | `DataSource.getConnection()` từ pool | Wrapper traversal hợp lệ hoặc unsupported rõ |
| Hai proxy tầng | Pool + tracing/transaction wrapper | Extension hoạt động nếu wrappers hỗ trợ |
| Database khác | Driver không có extension | Fallback hoặc required feature error |
| Wrong interface | Truyền API type không thuộc driver | isWrapperFor false; unwrap SQLException |
| Driver update | Thay version ở test environment | Không có linkage/classloader errors |
| Pool handle đóng | `close` borrowed connection | Không sử dụng unwrapped reference |
| Reborrow | Trả A về pool, nhận B | Extension của A không bị giữ dùng lại |
| Server permission | Feature đòi quyền SQL | SQL error rõ, không coi là unwrap failure |
| Transaction manager | Managed transaction | Vendor operations tuân policy |
| Packaged artifact | Fat JAR/containers | Dependency driver và API còn nguyên |
| Statement/ResultSet extension | Đúng JDBC receiver type | Unwrap đúng vendor interface |
| Concurrency | Nhiều requests | Không dùng chung borrowed handle trái contract |

Một test tích hợp có thể dùng PostgreSQL instance trong CI và pgJDBC, nhưng **phải quản lý credentials, database lifecycle, test isolation**. Không hard-code server port/password hoặc đoán toàn bộ hệ thống đã hỗ trợ interface chỉ vì unit fixture pass.

### 13.3. Assertion hợp lý

Với driver thật:

```java
try (Connection conn = dataSource.getConnection()) {
    if (!conn.isWrapperFor(PGConnection.class)) {
        throw new AssertionError("PGConnection unavailable");
    }
    PGConnection pg = conn.unwrap(PGConnection.class);
    if (pg == null) {
        throw new AssertionError("Invalid unwrap result");
    }
}
```

Đây là snippet **không standalone**: cần `DataSource` được tạo, pgJDBC dependency, PostgreSQL server và imports. Không assert `pg == conn` vì Javadoc không bảo đảm object identity. Không assert concrete pool proxy class name.

## 14. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách giải quyết |
| --- | --- | --- |
| `ClassCastException` | Cast outer wrapper trực tiếp | Dùng `isWrapperFor`/`unwrap` với interface |
| `isWrapperFor` false | Interface không được expose hoặc sai driver | Kiểm tra public vendor API, pool/config/version |
| `unwrap` ném `SQLException` | Unsupported interface hoặc JDBC error | Bắt lỗi, phân biệt capability và connection failure |
| `NoClassDefFoundError` | Thiếu vendor API JAR runtime | Sửa dependency packaging |
| `NoSuchMethodError` | Compile/run driver versions lệch | Pin versions, kiểm tra classpath |
| `SQLFeatureNotSupportedException` | Driver không hỗ trợ feature | Fallback hoặc báo unsupported |
| Feature sau close bị lỗi | Dùng reference ngoài lifetime | Giữ scope trong try-with-resources |
| Database feature error | Quyền/transaction/server config | Sửa server-side policy, không chỉ unwrap |
| Pool connection bị hỏng | Đóng physical delegate ngoài pool | Chỉ close borrowed logical handle |
| Unwrap sang `Connection.class` không lấy driver | Outer đã là Connection | Unwrap **đúng extension interface** |
| Unit pass, production fail | Pool/version/classloader khác | Integration test với môi trường thực |

### Những nhầm lẫn cần tránh

**1. `connection instanceof VendorInterface` false nghĩa driver không có tính năng.**  
Sai. Wrapper ngoài có thể không implement extension, còn delegate có.

**2. `unwrap` luôn trả object bên trong cùng của pool.**  
Sai. API cho phép receiver hoặc proxy phù hợp; không đồng nghĩa physical connection.

**3. Cast sang implementation class vì đã thấy tên nó trong logs.**  
Không bền vững; lớp đó có thể là nội bộ, thay đổi khi nâng driver/pool.

**4. `isWrapperFor` không bao giờ ném lỗi.**  
Sai. Method khai báo `SQLException`.

**5. `isWrapperFor` true thì có thể bỏ catch `SQLException` ở `unwrap`.**  
Không. Connection có thể đóng/lỗi giữa calls; code JDBC vẫn cần error handling.

**6. `unwrap(Connection.class)` sẽ bypass pool.**  
Không. Proxy có thể trả chính nó vì đã implement Connection.

**7. Chỉ cần thêm JAR vendor vào classpath là proxy sẽ expose extension.**  
Không nhất thiết. Pool/wrappers cũng phải hỗ trợ contract và đúng interface.

**8. Có thể close riêng extension handle rồi vẫn dùng pooled connection.**  
Không được. Extension có thể tác động physical resource do pool quản lý.

**9. Có thể cache extension ở singleton rồi dùng qua nhiều requests.**  
Không. Vòng đời không dài hơn borrowed connection handle.

**10. Driver extension portable giữa databases.**  
Không. Cơ chế unwrap portable; API extension vendor-specific.

**11. Dùng reflection truy cập private field của pool khi unwrap false.**  
Không phải API được hỗ trợ, có thể phá pool/security/module encapsulation.

**12. Khi cần chỉnh auto-commit cũng phải unwrap.**  
Sai. `Connection.setAutoCommit` là JDBC chuẩn; gọi trực tiếp.

**13. `PGConnection` bắt buộc extends `java.sql.Connection`.**  
Không. Public pgJDBC interface độc lập; driver object có thể implement cả hai.

**14. Mọi instance của `ResultSet` đều unwrap được PGConnection.**  
Không. Wrapper contract áp dụng theo receiver và interface mà receiver hỗ trợ.

**15. Test với fake driver là đủ để chứng minh pool thật.**  
Không. Test thật với pool và driver/version mà production dùng.

**16. Khi connection pool trả logical handle về pool, extension object vẫn còn hợp lệ.**  
Không nên giả định. Đừng dùng sau close/recycle.

**17. Unwrap thành công là PostgreSQL feature đã sẵn sàng ở server.**  
Không. Còn permission, transaction, network và server support.

**18. Bắt mọi exception rồi tiếp tục như thể feature không quan trọng.**  
Không. Nếu tính năng bắt buộc, báo lỗi rõ; nếu optional, fallback có kiểm chứng semantics.

## 15. Câu hỏi tự kiểm tra

**1. Vì sao cast `(PGConnection) connection` từ pool có thể thất bại?**  
Vì proxy ngoài thường chỉ implement `Connection`, không trực tiếp implement `PGConnection`.

**2. Phương thức chuẩn nào kiểm tra interface ở delegate chain?**  
`isWrapperFor(Interface.class)`.

**3. Phương thức chuẩn nào trả extension typed?**  
`unwrap(Interface.class)`, có thể ném `SQLException`.

**4. `unwrap` luôn trả physical driver connection?**  
Không. Có thể trả receiver, delegate hoặc proxy phù hợp.

**5. `unwrap(Connection.class)` có phải cách lấy physical object không?**  
Không. Outer wrapper tự implement Connection nên có thể đáp ứng ngay.

**6. `PGConnection` thuộc JDK hay pgJDBC?**  
pgJDBC. Cần dependency khi compile và runtime.

**7. `PGConnection` bắt buộc extends `Connection` không?**  
Không. Extension interface có thể độc lập.

**8. Cần đóng resource nào sau khi dùng extension từ pooled connection?**  
Đóng borrowed logical `Connection` ban đầu bằng try-with-resources, không tự đóng physical delegate.

**9. Nếu `isWrapperFor` false, có nhất thiết phải fail không?**  
Tùy feature bắt buộc hay optional. Fallback khi semantics tương đương, hoặc báo unsupported.

**10. Có nên lưu `PGConnection` trong singleton ngoài borrowed connection lifetime không?**  
Không nên, vì pool có thể recycle session và handle hết hạn.

**11. `Connection.commit` có yêu cầu unwrap không?**  
Không. Đó là JDBC chuẩn.

**12. Vì sao phải test với pool production nếu unit mock đã pass?**  
Mock chứng minh contract; pool/driver cụ thể còn có classloader, wrapper behavior, versions và server state.

**13. Nếu `getNotifications()` trả mảng rỗng, chắc unwrap sai?**  
Không. Có thể chưa có notification hoặc chưa được giao; cần kiểm tra server/session/transaction.

**14. Lỗi runtime `NoSuchMethodError` thường gợi ý gì?**  
Compile/runtime binary API mismatch hoặc driver version không đồng nhất.

**15. Cần làm gì khi `unwrap` trả proxy thay vì concrete driver object?**  
Dùng **interface đã yêu cầu**; không ép kiểu thêm sang internal implementation class.

## 16. Tài liệu hiện hành

- [Java SE 26 — `java.sql.Wrapper`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Wrapper.html): hợp đồng unwrap, isWrapperFor, delegate và proxy.
- [Java SE 26 — `java.sql.Connection`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Connection.html): Connection extends Wrapper/AutoCloseable, close và transaction semantics.
- [Java SE 26 — `javax.sql.DataSource`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/javax/sql/DataSource.html): datasource và Wrapper.
- [Java SE 26 — `javax.sql.PooledConnection`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/javax/sql/PooledConnection.html): logical handle và physical connection ownership.
- [Java SE 26 — `Statement`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Statement.html) và [`ResultSet`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/ResultSet.html): các JDBC types với Wrapper.
- [Java SE 26 — `SQLException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLException.html), [`SQLFeatureNotSupportedException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLFeatureNotSupportedException.html): error contracts.
- [Java SE 26 — `Proxy`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/Proxy.html) và [`InvocationHandler`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/InvocationHandler.html): dynamic proxy được dùng trong demo.
- [pgJDBC `PGConnection` interface](https://github.com/pgjdbc/pgjdbc/blob/master/pgjdbc/src/main/java/org/postgresql/PGConnection.java): public extension interface của PostgreSQL JDBC driver.
- [pgJDBC PostgreSQL features](https://vlsi.github.io/pgjdbc/documentation/postgresql-features/): dùng `Connection.unwrap(PGConnection.class)` cho COPY, LISTEN/NOTIFY và các capabilities.
- [pgJDBC LISTEN/NOTIFY](https://vlsi.github.io/pgjdbc/documentation/postgresql-features/listen-notify/): thông báo, timeout và không có background reader thread.

**Kết luận:** Cách đúng để truy cập API mở rộng JDBC là **yêu cầu đúng public interface của vendor** qua `isWrapperFor` và `unwrap`, không cast một wrapper theo suy đoán. Giữ extension trong lifetime của borrowed connection, xử lý `SQLException` và unsupported capabilities, ưu tiên JDBC chuẩn khi có, và integration-test với driver/pool/server thực trước khi triển khai tính năng phụ thuộc vendor.
