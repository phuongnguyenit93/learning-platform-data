# JDBC kết nối: `Wrapper.isWrapperFor` và `unwrap`

## Mục tiêu học tập

Khi ứng dụng Java truy cập cơ sở dữ liệu, đối tượng nhận được từ `DataSource.getConnection()` hoặc một connection pool có thể **không phải chính xác đối tượng driver gốc**. Nó có thể là proxy/wrapper do pool, framework, observability layer hoặc JDBC driver tạo ra. Giao diện chuẩn `java.sql.Wrapper` cho phép kiểm tra và truy cập **một interface nằm phía sau lớp wrapper** mà không cần ép kiểu trực tiếp một cách mạo hiểm.

Sau bài này, bạn có thể:

- Hiểu mục đích của `java.sql.Wrapper` trong JDBC và biết những API đang dùng nó như `Connection`, `Statement`, `PreparedStatement`, `ResultSet`, `DatabaseMetaData` và `DataSource`.
- Đọc đúng hợp đồng `boolean isWrapperFor(Class<?> iface) throws SQLException` và `<T> T unwrap(Class<T> iface) throws SQLException`.
- Phân biệt **đối tượng đang được gọi**, **delegate trực tiếp**, **delegate sau nhiều lớp wrapper** và **proxy trả về**.
- Viết kiểm tra hỗ trợ theo interface trước khi truy cập phần mở rộng đặc thù driver; giữ đường đi **JDBC chuẩn** khi driver không cung cấp interface cần tìm.
- Hiểu rằng `isWrapperFor(true)` đảm bảo `unwrap` tương ứng sẽ thành công theo hợp đồng của implementation tuân thủ JDBC, nhưng **không đảm bảo trả đúng identity của raw physical connection**.
- Tránh các lỗi với connection pool: ép kiểu trực tiếp, dùng đối tượng đã unwrap bên ngoài phạm vi connection, đóng hai lần hoặc bypass quản lý transaction/close của pool.
- Biên dịch và chạy **một ví dụ Java 17+ độc lập**, mô phỏng hai lớp `Connection` proxy và một interface mở rộng được bọc bên trong; không cần cài driver hay database.
- Tổ chức integration tests với **driver và pool thực** khi đưa cơ chế này vào ứng dụng, vì khả năng unwrap phụ thuộc implementation và driver version.

**Special Note:** kiến thức được trình bày theo API JDBC **vẫn còn hiệu lực trong Java SE 26**. `Wrapper` là giao diện chuẩn của `java.sql` (tồn tại từ Java 6/JDBC 4.0 và vẫn được sử dụng trong JDK mới), không phải tính năng legacy cần thay thế. Các ví dụ ưu tiên Java 17+.

## 1. Vì sao JDBC cần `Wrapper`?

Ứng dụng Java thường chỉ làm việc với những interfaces chuẩn:

```java
Connection connection = dataSource.getConnection();
PreparedStatement statement = connection.prepareStatement("SELECT 1");
ResultSet resultSet = statement.executeQuery();
```

Đoạn trên là **minh họa trong một method**, cần có `DataSource` đã cấu hình và một JDBC driver thật; không phải chương trình độc lập.

Trong thực tế, `connection` có thể là đối tượng do connection pool cấp:

```text
Business code
    |
    |  Connection (JDBC interface)
    v
Connection pool proxy
    |
    v
Metrics / tracing wrapper
    |
    v
JDBC driver connection
    |
    +--> Vendor-specific feature interface
```

Nếu nhà cung cấp driver có thêm một API ngoài JDBC chuẩn, ví dụ khả năng truy cập một cấu hình đặc thù, việc làm sau đây **không đáng tin cậy**:

```java
// Không an toàn nếu connection đang là proxy của pool:
VendorConnection nativeConnection = (VendorConnection) connection;
```

`VendorConnection` ở đây là **tên giả định** cho một loại của driver, không phải API chuẩn Java SE. Nếu `connection` thực chất là một proxy triển khai `java.sql.Connection` nhưng **không implement loại vendor**, ép kiểu có thể gây `ClassCastException`.

Giải pháp là hỏi đối tượng thông qua giao diện `Wrapper`:

```java
if (connection.isWrapperFor(VendorFeature.class)) {
    VendorFeature feature = connection.unwrap(VendorFeature.class);
    feature.enableVendorOption();
}
```

`VendorFeature` và `enableVendorOption` là **API minh họa**, chưa có định nghĩa đầy đủ ở đoạn này. Code thực tế phải dùng interface thật do thư viện JDBC driver cung cấp, và chỉ dùng một tính năng thực sự cần thiết. Ví dụ chạy độc lập trong bài sẽ tự định nghĩa `VendorFeature` để quan sát cơ chế, không giả vờ đó là API của driver thực.

**Điểm cốt lõi:** `Connection` có thể không trực tiếp là instance của interface mở rộng, nhưng **nó biết cách unwrap đến một đối tượng ở bên trong** có interface đó.

## 2. `java.sql.Wrapper` định nghĩa những gì?

Java SE 26 Javadoc khai báo đúng hai phương thức:

```java
boolean isWrapperFor(Class<?> iface) throws SQLException;

<T> T unwrap(Class<T> iface) throws SQLException;
```

Đây là **chữ ký của API**, không phải mã tự định nghĩa lại interface `Wrapper`.

`Wrapper` nằm trong package `java.sql`, thuộc module chuẩn `java.sql`. Các interfaces chính của JDBC được thiết kế để kế thừa `Wrapper`, nên ứng dụng thường gọi trực tiếp:

```java
connection.isWrapperFor(MyInterface.class);
connection.unwrap(MyInterface.class);
```

thay vì cast `Connection` sang `Wrapper`. Tuy nhiên, bạn có thể viết helper nhận `Wrapper` khi muốn dùng chung logic cho `Connection`, `Statement`, `ResultSet` và các đối tượng JDBC khác.

### 2.1. So sánh nhanh

| API | Mục đích | Trả về | Lỗi có thể phát sinh |
| --- | --- | --- | --- |
| `isWrapperFor(Class<?> iface)` | Hỏi đối tượng hiện tại hoặc lớp delegate mà nó bọc có hỗ trợ interface không. | `boolean` | `SQLException` nếu có lỗi khi xác định khả năng unwrap |
| `unwrap(Class<T> iface)` | Nhận một đối tượng hoặc proxy **implement interface T** để gọi các phương thức tương ứng. | `T` | `SQLException` nếu không tìm được đối tượng hỗ trợ hoặc có lỗi JDBC khác |

**Cùng tham số:** cả hai nhận đối tượng `Class` đại diện cho **interface muốn truy cập**, ví dụ `Connection.class` hoặc `SomeVendorExtension.class`. Không truyền tên interface dưới dạng `String` hay tên class do driver tạo ra một cách tùy tiện.

### 2.2. `isWrapperFor` thực sự kiểm tra điều gì?

Theo Java SE 26:

- Trả `true` nếu đối tượng đang được gọi **tự implement interface đó**.
- Hoặc trả `true` nếu nó **bọc trực tiếp hoặc gián tiếp** một đối tượng implement interface đó.
- Nếu không đáp ứng cả hai, trả `false`.
- Có thể ném `SQLException` nếu quá trình kiểm tra không thực hiện được do lỗi.
- Được thiết kế như **phép kiểm tra tương đối ít tốn chi phí** so với thử `unwrap` có thể thất bại.
- Khi `isWrapperFor(iface)` trả `true`, một implementation tuân thủ hợp đồng phải cho phép `unwrap(iface)` thành công.

Một `Connection` bình thường đã implement `Connection`, nên `connection.isWrapperFor(Connection.class)` về nguyên tắc phải `true`. Đây **không** phải bằng chứng rằng còn một connection driver khác nằm ở phía trong; chỉ có thể đối tượng hiện tại đã implement interface này.

### 2.3. `unwrap` trả cái gì?

Javadoc nói `unwrap(iface)` trả một đối tượng **implement interface được yêu cầu**. Nó có thể là:

1. Chính đối tượng nhận lời gọi, nếu đối tượng đó implement interface.
2. Đối tượng delegate được bọc trực tiếp.
3. Một delegate nằm sau nhiều lớp bọc.
4. **Một proxy** đại diện cho một trong các đối tượng trên.

Do đó, cách sử dụng đúng là:

```java
MyExtension extension = connection.unwrap(MyExtension.class);
// Dùng các method thuộc interface MyExtension.
```

Không suy luận:

```java
// KHÔNG có bảo đảm tổng quát:
connection.unwrap(Connection.class) == connection
```

Việc trả cùng reference có thể đúng với một số implementation, nhưng **không phải bất biến JDBC bắt buộc**. Bạn cũng không được giả định `unwrap` luôn trả về **raw physical connection** không còn lớp proxy nào.

### 2.4. Khi không hỗ trợ interface

Nếu đối tượng hiện tại và các delegate không implement interface được yêu cầu, `unwrap` phải ném `SQLException` theo hợp đồng. Đừng dựa vào việc nó trả `null` để báo unsupported.

```java
if (!connection.isWrapperFor(VendorFeature.class)) {
    // Tính năng vendor không có qua Connection này.
} else {
    VendorFeature feature = connection.unwrap(VendorFeature.class);
    // Có thể dùng tính năng đặc thù.
}
```

**Phân biệt:** `false` là “không có interface được yêu cầu”, còn exception từ `isWrapperFor` là “không kiểm tra được do lỗi”. Không nên catch mọi `SQLException` rồi coi là `false`; có những lỗi hạ tầng cần được xử lý.

## 3. “Implements trực tiếp” và “wrap gián tiếp”

Hãy tưởng tượng:

```text
Connection outerProxy : Connection, Wrapper
        |
        v
Connection innerProxy : Connection, Wrapper
        |
        v
VendorSession : VendorFeature
```

`outerProxy` không implement `VendorFeature`, nhưng có thể khám phá delegate:

```text
outerProxy.isWrapperFor(VendorFeature.class)
    |
    +--> outerProxy tự implement? NO
    |
    +--> innerProxy tự implement? NO
    |
    +--> innerProxy bọc VendorSession? YES
    |
    +--> true
```

Và:

```text
outerProxy.unwrap(VendorFeature.class)
    |
    +--> tìm interface qua các lớp bọc
    |
    +--> VendorSession hoặc proxy cho VendorSession
    |
    +--> gọi driverTag() qua VendorFeature
```

Đây chính là hành vi mà lớp `Wrapper` được thiết kế để chuẩn hóa. Một ứng dụng có thể không biết chính xác có bao nhiêu proxy trong pool/framework.

**Tuy nhiên:** “wrapper chuẩn” phụ thuộc implementation. Nếu một lớp proxy bên thứ ba không implement đúng quy tắc `Wrapper` hoặc ngăn truy cập một delegate, bạn không có quyền vượt qua bằng reflection vào trường riêng của pool. Khi gặp vấn đề, kiểm tra driver/pool version và contract thực sự.

## 4. Những interfaces JDBC đã có `Wrapper`

Theo Javadoc Java SE 26, các giao diện sau đều có đường truy cập `isWrapperFor`/`unwrap`:

| Interface | Ví dụ dùng |
| --- | --- |
| `java.sql.Connection` | Kết nối đang được driver hoặc pool bao bọc |
| `java.sql.Statement` | Statement do driver/framework tạo |
| `java.sql.PreparedStatement` | Prepared statement, có thể được wrapper bởi statement cache |
| `java.sql.CallableStatement` | Gọi stored procedure qua proxy |
| `java.sql.ResultSet` | Tập kết quả bọc bởi tracing/driver |
| `java.sql.DatabaseMetaData` | Metadata của kết nối từ driver |
| `java.sql.ResultSetMetaData` | Metadata từng cột |
| `java.sql.ParameterMetaData` | Metadata tham số chuẩn bị |
| `javax.sql.DataSource` | Đối tượng tạo connection, có thể là pool DataSource |
| `javax.sql.RowSet` và các subinterfaces | Cấu trúc row-set chuẩn có `Wrapper` |
| `javax.sql.RowSetMetaData` | Metadata của rowset |

**Cẩn thận về phạm vi:** Gọi `dataSource.unwrap(SomeConnectionInterface.class)` không tương đương `dataSource.getConnection().unwrap(SomeConnectionInterface.class)`. `DataSource` đại diện cho **factory**, còn `Connection` đại diện cho **một phiên kết nối**; chúng là hai đối tượng khác, bọc những delegate khác nhau.

Tương tự, `statement.unwrap(VendorStatementExtension.class)` và `connection.unwrap(VendorConnectionExtension.class)` phục vụ hai mục tiêu khác nhau. Không phải mọi `Wrapper` đều có quyền tìm đến mọi đối tượng JDBC khác trong ứng dụng.

## 5. Cách dùng thực tế: kiểm tra hỗ trợ trước khi unwrap

Trong một ứng dụng có driver vendor và connection pool, một pattern an toàn là:

```java
try (Connection connection = dataSource.getConnection()) {
    if (connection.isWrapperFor(MyVendorExtension.class)) {
        MyVendorExtension extension =
                connection.unwrap(MyVendorExtension.class);
        extension.applyFeature();
    } else {
        // Đường đi JDBC portable hoặc lựa chọn không dùng tính năng này.
    }
}
```

**Đây là đoạn tích hợp minh họa, không chạy độc lập**: cần `dataSource` thật và `MyVendorExtension`/`applyFeature` do driver cung cấp. Khối `try-with-resources` quản lý **đối tượng `Connection` ứng dụng nhận từ pool**.

### 5.1. Vì sao kiểm tra trước?

- Không giả định phiên bản driver nào cũng hỗ trợ interface.
- Không coi mọi proxy đều implement vendor interface trực tiếp.
- Có thể chọn đường xử lý chuẩn khi extension không sẵn có.
- Dễ biểu đạt feature detection thay vì rải rác `ClassCastException`.
- Tránh một số lời gọi `unwrap` thất bại không cần thiết.

Tuy vậy, `isWrapperFor` cũng có `throws SQLException`. Không biến nó thành phép kiểm tra chắc chắn không lỗi hoặc “một API thuần” không cần exception handling.

### 5.2. Trường hợp hỗ trợ đã thay đổi giữa kiểm tra và sử dụng?

Theo contract, `true` phải dẫn tới `unwrap` thành công trong điều kiện hợp lệ. Nhưng **không có hợp đồng biến một connection đã đóng, mất kết nối hoặc bị pool thu hồi thành đối tượng mãi mãi usable**. Trong code thực tế, vẫn phải xử lý `SQLException` từ `unwrap` và từ các thao tác tiếp theo.

Không sử dụng `isWrapperFor` như health-check hoặc connectivity test. Nó không thay thế `Connection.isValid(timeout)`, quy tắc quản lý timeout, và các thao tác SQL/transaction cần thiết.

### 5.3. Khi nào nên gọi thẳng unwrap?

Nếu một phần mềm **chỉ có thể hoạt động** với extension bắt buộc, bạn có thể gọi `unwrap(MyVendorExtension.class)` trực tiếp, bắt `SQLException` và trả lỗi cấu hình rõ ràng. Khi extension chỉ là **tính năng tùy chọn**, pattern `isWrapperFor` rồi `unwrap` thường dễ đọc và phù hợp.

**Không bắt buộc phải gọi cả hai** như một luật máy móc. Chọn theo policy nghiệp vụ và hợp đồng của driver.

## 6. Ví dụ độc lập Java 17+: hai lớp Connection proxy, một interface vendor

Để kiểm chứng mà không cần cài DB hoặc driver, chương trình sau dùng `java.lang.reflect.Proxy` tạo hai đối tượng implement `Connection`. Mỗi proxy biết ủy quyền `isWrapperFor` và `unwrap` cho đối tượng mà nó bao bọc.

**Giới hạn minh bạch:** Đây là **mô phỏng hành vi `Wrapper`**, **không phải JDBC driver** và không thực thi SQL. Những methods `Connection` khác ngoài tập tối thiểu trong demo sẽ ném `SQLFeatureNotSupportedException`; ví dụ chỉ chứng minh hợp đồng wrapper và vòng đời proxy đơn giản. Để đánh giá driver/pool thật, xem mục kiểm thử tích hợp.

### 6.1. Cây file

```text
jdbc-wrapper-demo/
└── JdbcWrapperDemo.java
```

Không cần thư viện ngoài JDK; `java.sql` là module chuẩn.

### 6.2. Toàn bộ file `JdbcWrapperDemo.java`

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import java.sql.Wrapper;

public final class JdbcWrapperDemo {
    public interface VendorFeature {
        String driverTag();
    }

    private static final class VendorSession implements VendorFeature {
        @Override
        public String driverTag() { return "DEMO_DRIVER"; }
    }

    private static final class ConnectionProxyHandler implements InvocationHandler {
        private final Object delegate;
        private boolean closed;

        ConnectionProxyHandler(Object delegate) { this.delegate = delegate; }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws SQLException {
            String name = method.getName();
            if (name.equals("isWrapperFor")) {
                Class<?> iface = (Class<?>) args[0];
                return iface.isInstance(proxy)
                        || iface.isInstance(delegate)
                        || (delegate instanceof Wrapper w && w.isWrapperFor(iface));
            }
            if (name.equals("unwrap")) {
                Class<?> iface = (Class<?>) args[0];
                if (iface.isInstance(proxy)) return iface.cast(proxy);
                if (iface.isInstance(delegate)) return iface.cast(delegate);
                if (delegate instanceof Wrapper w) return w.unwrap(iface);
                throw new SQLException("No object implements " + iface.getName());
            }
            if (name.equals("close")) {
                closed = true;
                if (delegate instanceof Connection c) c.close();
                return null;
            }
            if (name.equals("isClosed")) return closed;
            if (name.equals("toString")) return "DemoConnectionProxy";
            if (name.equals("equals")) return proxy == args[0];
            if (name.equals("hashCode")) return System.identityHashCode(proxy);
            throw new SQLFeatureNotSupportedException(
                    "This example is not a database driver: " + name);
        }
    }

    private static Connection wrap(Object delegate) {
        return (Connection) Proxy.newProxyInstance(
                JdbcWrapperDemo.class.getClassLoader(),
                new Class<?>[] {Connection.class},
                new ConnectionProxyHandler(delegate));
    }

    private static void check(String label, boolean result) {
        if (!result) throw new AssertionError(label);
        System.out.println(label + "=true");
    }

    public static void main(String[] args) throws SQLException {
        Connection inner = wrap(new VendorSession());
        Connection outer = wrap(inner);

        check("outerIsConnection", outer instanceof Connection);
        check("outerNotVendorFeature", !(outer instanceof VendorFeature));
        check("supportsJdbcInterface", outer.isWrapperFor(Connection.class));
        check("supportsIndirectVendor", outer.isWrapperFor(VendorFeature.class));

        VendorFeature feature = outer.unwrap(VendorFeature.class);
        check("unwrapVendorTag", feature.driverTag().equals("DEMO_DRIVER"));
        check("unwrapJdbcType", outer.unwrap(Connection.class) instanceof Connection);
        check("unrelatedInterfaceFalse", !outer.isWrapperFor(ResultSet.class));

        boolean failedAsExpected = false;
        try {
            outer.unwrap(ResultSet.class);
        } catch (SQLException expected) {
            failedAsExpected = true;
        }
        check("unsupportedUnwrapThrowsSQLException", failedAsExpected);

        outer.close();
        check("outerClosed", outer.isClosed());
        check("innerClosed", inner.isClosed());
    }
}
```

### 6.3. Biên dịch và chạy

Trong thư mục chứa file:

```bash
javac --release 17 JdbcWrapperDemo.java
java JdbcWrapperDemo
```

Có thể chạy giống nhau trong PowerShell, cmd hoặc terminal Bash nếu `javac`/`java` của JDK 17+ có trong `PATH`.

### 6.4. Stdout chính xác đã kiểm chứng trên OpenJDK 24

```text
outerIsConnection=true
outerNotVendorFeature=true
supportsJdbcInterface=true
supportsIndirectVendor=true
unwrapVendorTag=true
unwrapJdbcType=true
unrelatedInterfaceFalse=true
unsupportedUnwrapThrowsSQLException=true
outerClosed=true
innerClosed=true
```

Đây là **10 kiểm tra có assertions**, không phải một danh sách kết quả được in không điều kiện. Nếu phép kiểm tra nào sai, `check(...)` ném `AssertionError` và chương trình dừng. Mã đã được biên dịch bằng `javac --release 17` rồi chạy trên JDK 24.

### 6.5. Diễn giải từng dòng kết quả

| Dòng | Chứng minh |
| --- | --- |
| `outerIsConnection` | Proxy bên ngoài implement `java.sql.Connection`. |
| `outerNotVendorFeature` | Proxy bên ngoài **không implement trực tiếp** interface của vendor, nên ép kiểu trực tiếp không phù hợp. |
| `supportsJdbcInterface` | Đối tượng tự implement `Connection`, do đó hỗ trợ unwrap theo interface đó. |
| `supportsIndirectVendor` | `isWrapperFor` đi qua outer → inner → `VendorSession`. |
| `unwrapVendorTag` | `unwrap(VendorFeature.class)` truy cập được interface nằm phía sâu và gọi method. |
| `unwrapJdbcType` | `unwrap(Connection.class)` trả về đối tượng implement `Connection`, không cần kiểm tra identity. |
| `unrelatedInterfaceFalse` | Không có `ResultSet` nằm trong chuỗi bọc, nên kiểm tra trả `false`. |
| `unsupportedUnwrapThrowsSQLException` | `unwrap(ResultSet.class)` ném `SQLException` thay vì trả `null`. |
| `outerClosed` | Proxy ngoài nhận lệnh đóng. |
| `innerClosed` | Implementation demo chuyển tiếp đóng tới proxy trong. |

**Đừng suy rộng behavior `close` của demo sang pool thật:** một pooled connection `close()` có thể trả logical connection về pool, không nhất thiết đóng physical DB socket. Demo chỉ cho thấy cách mô phỏng vòng đời wrapper. Không tự triển khai Connection proxy ở production dựa trên 30 dòng handler của ví dụ: JDBC có rất nhiều methods cần hợp đồng, error handling và quản lý transaction chính xác.

## 7. Phân tích cơ chế trong `ConnectionProxyHandler`

### 7.1. Vì sao `Proxy.newProxyInstance`?

`java.sql.Connection` là một interface lớn. Thay vì tự viết hàng chục methods cho một lớp giả, `Proxy` tạo object implements `Connection`; `InvocationHandler` nhận các lời gọi như `isWrapperFor` và `unwrap`.

```java
return (Connection) Proxy.newProxyInstance(
        JdbcWrapperDemo.class.getClassLoader(),
        new Class<?>[] {Connection.class},
        new ConnectionProxyHandler(delegate));
```

Đây là một **đoạn trong helper `wrap`**. Chúng ta dùng `ClassLoader` của lớp demo để proxy có thể triển khai đúng interface ở runtime.

**Không cần dùng reflection để unwrap driver thật.** Trong ứng dụng JDBC production, gọi trực tiếp `Connection.isWrapperFor`/`unwrap` theo contract; dynamic proxy chỉ là công cụ tạo mô hình minh họa trong bài.

### 7.2. Kiểm tra chính mình trước

`iface.isInstance(proxy)` kiểm tra proxy hiện tại có implement interface yêu cầu không. Nếu `iface=Connection.class`, điều kiện đúng. Đây là lý do `isWrapperFor(Connection.class)` có thể trả `true` **ngay khi chưa có delegate**.

### 7.3. Kiểm tra delegate trực tiếp

`iface.isInstance(delegate)` kiểm tra chính delegate ngay bên trong. Nếu delegate đã implement `VendorFeature`, không cần đi sâu hơn.

### 7.4. Đệ quy thông qua Wrapper khác

`delegate instanceof Wrapper w && w.isWrapperFor(iface)` chuyển truy vấn sang delegate nếu delegate cũng là một `Wrapper`. Ví dụ `outer` biết `inner`, `inner` biết `VendorSession`. Phương thức `unwrap` cũng đệ quy qua cùng chuỗi.

**Với driver thật:** không được giả định chuỗi wrapper luôn cấu thành danh sách đơn giản hoặc không có cycle; implementation của pool/driver chịu trách nhiệm quản lý. Ví dụ demo không có cycle và không phải thư viện wrapper production.

### 7.5. Trả về proxy hoặc delegate theo interface

`iface.cast(proxy)` là một dynamic cast được kiểm tra; chỉ chạy sau khi `iface.isInstance(proxy)`. Nếu delegate phù hợp, trả `iface.cast(delegate)`. Đường gián tiếp gọi `w.unwrap(iface)` theo hợp đồng.

Không nên nhận `Object raw` rồi ép sang một implementation class khác với interface đã yêu cầu. Nếu code thực sự cần API đặc thù, yêu cầu **đúng interface cần dùng**.

### 7.6. Đường không hỗ trợ ném `SQLException`

`throw new SQLException("No object implements " + iface.getName());` minh họa kết quả bắt buộc khi không tìm được interface phù hợp. Đây là loại exception trong hợp đồng `unwrap`, không dùng `ClassCastException` như cách ép kiểu tùy tiện.

### 7.7. Tại sao không gọi các JDBC methods khác?

Handler cố ý ném:

```java
throw new SQLFeatureNotSupportedException(
        "This example is not a database driver: " + name);
```

Đây là cách thể hiện giới hạn của mock. `SQLFeatureNotSupportedException` là subclass của `SQLException` dùng khi một optional JDBC feature không được hỗ trợ. **Không đồng nghĩa** driver hoặc connection thật sẽ dùng exception đó cho mọi lỗi `unwrap`: hợp đồng `Wrapper.unwrap` chỉ yêu cầu `SQLException` trong trường hợp không tìm được interface.

## 8. `DataSource` khác `Connection` khi unwrap

`javax.sql.DataSource` cũng extends `Wrapper`. Nhưng lớp bọc DataSource thường làm công việc **cấu hình và cung cấp connection**, không phải đại diện trực tiếp cho một phiên DB.

```java
// dataSource là DataSource đã được cấu hình:
if (dataSource.isWrapperFor(VendorDataSourceConfig.class)) {
    VendorDataSourceConfig settings =
            dataSource.unwrap(VendorDataSourceConfig.class);
    // Sử dụng cấu hình nếu API này thực sự được hỗ trợ.
}

try (Connection connection = dataSource.getConnection()) {
    if (connection.isWrapperFor(VendorConnectionFeature.class)) {
        VendorConnectionFeature feature =
                connection.unwrap(VendorConnectionFeature.class);
        // Tính năng thuộc về phiên kết nối này.
    }
}
```

Đây là **đoạn minh họa tích hợp**, với hai vendor interfaces chỉ là tên mẫu; không chạy độc lập. Đọc Javadoc driver thật trước khi viết code như vậy.

| Đối tượng | Phạm vi |
| --- | --- |
| `DataSource` | Factory/pool configuration và việc cấp connections |
| `Connection` | Một logical JDBC session, transaction context và vòng đời của phiên |
| `Statement` / `PreparedStatement` | Một statement, prepared operation và statement-specific options |
| `ResultSet` | Tập kết quả và cursor-related capabilities |

**Không suy ra**: nếu `DataSource` hỗ trợ `VendorDataSourceConfig` thì mọi `Connection` từ DataSource cũng có thể `unwrap` ra loại đó. Hai wrapper chains khác nhau.

## 9. `Statement`, `PreparedStatement` và `ResultSet`

Khi một driver cung cấp extension riêng cho prepared statement, việc unwrap đúng đối tượng quan trọng hơn việc “unwrap càng sâu càng tốt”.

Ví dụ mô hình:

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(
             "SELECT id FROM orders WHERE id = ?")) {
    ps.setLong(1, id);

    if (ps.isWrapperFor(MyStatementExtension.class)) {
        MyStatementExtension extra = ps.unwrap(MyStatementExtension.class);
        extra.setDriverSpecificHint();
    }

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long orderId = rs.getLong(1);
            // Xử lý kết quả.
        }
    }
}
```

Đây là **đoạn minh họa**, cần `dataSource`, `id`, bảng `orders`, extension do vendor cung cấp. Nó không thể chạy nếu không có database.

Một số JDBC pools cũng bọc `Statement` để quản lý statement caching hoặc metrics; vì vậy ép kiểu vendor trực tiếp trên `ps` cũng không đáng tin.

**Lưu ý thứ tự và vòng đời:** Phương thức extension phải được gọi ở thời điểm driver cho phép, chẳng hạn trước execute nếu nó ảnh hưởng statement execution. Không giữ `extra` để dùng lại sau khi `ps` đã được đóng.

## 10. `Class.cast`, `instanceof` và `unwrap` khác nhau thế nào?

### `instanceof`

```java
boolean direct = connection instanceof MyVendorInterface;
```

Kiểm tra object đang giữ trực tiếp có implement interface không. Nếu đó là pooled proxy không implement vendor interface nhưng bọc một object có, kết quả có thể `false`.

### `Class.isInstance`

```java
boolean direct = MyVendorInterface.class.isInstance(connection);
```

Tương tự `instanceof` nhưng interface được biểu diễn bằng `Class` runtime. Không tự đi qua delegate chain.

### `Class.cast`

```java
MyVendorInterface x = MyVendorInterface.class.cast(connection);
```

Chỉ ép kiểu object đang cầm; **có thể ném `ClassCastException`**, không hỏi `Wrapper` và không đệ quy qua pool.

### `Wrapper.isWrapperFor`

```java
boolean available = connection.isWrapperFor(MyVendorInterface.class);
```

Có thể nhận `true` ngay cả khi `instanceof` trả `false`, vì wrapper biết interface ở delegate. Có thể ném `SQLException`.

### `Wrapper.unwrap`

```java
MyVendorInterface x = connection.unwrap(MyVendorInterface.class);
```

Lấy object hoặc proxy implement interface yêu cầu; có thể ném `SQLException` khi không hỗ trợ. Đây là **API JDBC chuẩn** cho nhu cầu tìm delegate capability.

**Kết luận:** `unwrap` không chỉ là phiên bản khác của `Class.cast`. Nó có thể đi qua lớp bọc, kiểm tra contract và trả proxy thích hợp.

## 11. Interface là yêu cầu quan trọng

Javadoc mô tả tham số `iface` là `Class` **định nghĩa một interface**. Trong Java, cú pháp `Class<T>` cho phép biểu diễn cả nhiều loại class khác, nhưng điều đó **không có nghĩa driver có trách nhiệm hỗ trợ unwrap về mọi concrete implementation class**.

Nên ưu tiên:

```java
if (connection.isWrapperFor(VendorExtensionInterface.class)) {
    VendorExtensionInterface vendor =
            connection.unwrap(VendorExtensionInterface.class);
}
```

thay vì:

```java
// Không nên dựa vào concrete class không được driver bảo đảm:
Object x = connection.unwrap(SomeInternalDriverClass.class);
```

Hai tên ở đây là **giả định**, không phải package Java SE. Nếu tài liệu driver mô tả một cách dùng riêng với concrete type, đó là **hợp đồng vendor-specific**; không biến nó thành bảo đảm chung của JDBC.

Lợi ích của interface:

- Tách ứng dụng khỏi implementation details có thể thay đổi theo driver version.
- Có thể dùng mock/fake để test năng lực ở tầng interface.
- Dễ phát triển optional feature handling.
- Giảm nhu cầu truy cập reflective vào classes nội bộ của pool.
- Rõ ràng hơn về methods được hỗ trợ và lifetime.

## 12. Làm việc với connection pool: bảo vệ vòng đời tài nguyên

Đây là phần rất quan trọng khi ứng dụng dùng HikariCP, application server pool hoặc một thư viện pooling khác.

### 12.1. “Pooled Connection” có thể là logical handle

Một pool cấp `Connection` cho caller. Khi caller gọi `close()`, điều đó thường **trả logical handle về pool** thay vì đóng vật lý socket. Chi tiết cụ thể do pool quyết định.

`unwrap` có thể trả một proxy khác hoặc đối tượng driver bên trong. **Không tự giả định object được trả về có cùng quy tắc `close` với logical handle**.

### 12.2. Đừng đóng riêng raw delegate

**Không an toàn:**

```java
Connection pooled = dataSource.getConnection();
Connection raw = pooled.unwrap(Connection.class);
raw.close();
pooled.close();
```

Đoạn này là **anti-pattern minh họa**. Vấn đề không nằm ở việc `unwrap(Connection.class)` luôn trả raw; nó có thể trả proxy hay self. Vấn đề là **ứng dụng đang cố quản lý hai references** như hai resources sở hữu độc lập trong khi chúng có thể đại diện cho cùng logical/physical session. Nếu nó thực sự chạm vào physical delegate, việc đóng ngoài lifecycle của pool có thể phá hủy một connection đang được pool quản lý.

**Đúng hướng:**

```java
try (Connection pooled = dataSource.getConnection()) {
    if (pooled.isWrapperFor(MyVendorExtension.class)) {
        MyVendorExtension ext = pooled.unwrap(MyVendorExtension.class);
        ext.doVendorOperation();
    }
    // JDBC operations dùng cùng pooled handle.
}
// Chỉ close đối tượng pooled do caller được cấp.
```

Đây là pattern minh họa, cần driver extension thật. **Ownership của connection** nằm ở handle từ `DataSource`; phần mở rộng được dùng trong phạm vi lifetime đó.

### 12.3. Không lưu delegate vào cache lâu dài

`unwrap` không có nghĩa tạo một connection có thể dùng mãi. Tránh giữ:

```java
// Anti-pattern: biến toàn cục giữ một extension gắn với connection tạm thời.
static Object cachedUnwrapped;
```

Nếu một request mượn connection từ pool, giữ delegate trong singleton có thể:

- Trỏ vào connection đã trả về pool.
- Bỏ qua kiểm soát transaction của request hiện tại.
- Tạo use-after-close hoặc gọi vào session thuộc request khác.
- Làm application server/pool khó quản lý metrics hoặc validation.
- Làm giới hạn concurrency/thread-safety không được tôn trọng.

**Mọi hành động lên extension nên diễn ra khi logical connection vẫn đang được sở hữu hợp lệ**, theo đúng tài liệu của driver và pool.

### 12.4. Không thay thế transaction API chuẩn bằng hack vendor

Nếu JDBC đã có method chuẩn như `setAutoCommit`, `setReadOnly`, `setTransactionIsolation`, `commit`, `rollback`, `setNetworkTimeout` hoặc `isValid`, hãy ưu tiên API đó khi nó đáp ứng yêu cầu. Đừng unwrap chỉ để truy cập một method tương đương trên implementation nội bộ.

Cách này giảm ràng buộc vào driver và tránh bỏ qua các quy tắc pool reset/transaction synchronization.

## 13. Khi interface không được hỗ trợ: chính sách fallback

Không phải mọi tính năng vendor đều thiết yếu.

### 13.1. Feature tùy chọn

```java
static boolean tryVendorFeature(
        Connection connection, VendorExtensionInterface.class) {
    // Đây là ý tưởng API, KHÔNG phải chữ ký Java hợp lệ.
    return false;
}
```

Đoạn trên chỉ là **phác thảo ý tưởng**; để tránh viết một function signature gây hiểu nhầm, bạn nên dùng helper generic thực sự ở mục 13.2. **Không copy phác thảo này vào project**.

**Mô hình đúng:**

```java
if (connection.isWrapperFor(MyVendorExtension.class)) {
    connection.unwrap(MyVendorExtension.class).applyOptionalFeature();
} else {
    // Tiếp tục với JDBC chuẩn, nếu tính năng thật sự optional.
}
```

Nếu phần mở rộng không có, code vẫn hoạt động theo đường portable; chỉ nên làm vậy khi bỏ qua extension không làm thay đổi tính đúng đắn nghiệp vụ.

### 13.2. Helper generic kiểm tra và lấy extension

Một helper dùng lại cho nhiều loại `Wrapper`:

```java
import java.sql.SQLException;
import java.sql.Wrapper;
import java.util.Optional;

public final class JdbcExtensionSupport {
    private JdbcExtensionSupport() {}

    public static <T> Optional<T> tryUnwrap(
            Wrapper wrapper, Class<T> extensionType) throws SQLException {
        if (!wrapper.isWrapperFor(extensionType)) {
            return Optional.empty();
        }
        return Optional.of(wrapper.unwrap(extensionType));
    }
}
```

Đây là một **lớp Java độc lập** dùng API hiện hành, compile được trên Java 17+, nhưng chỉ là helper chứ không có `main`; khi tích hợp, hãy chọn đúng type đã được driver hỗ trợ.

Ví dụ dùng:

```java
Optional<MyVendorExtension> ext =
        JdbcExtensionSupport.tryUnwrap(
                connection, MyVendorExtension.class);
if (ext.isPresent()) {
    ext.get().applyOptionalFeature();
}
```

Lưu ý: `Optional.of(...)` giả định driver tuân thủ contract `unwrap` và trả đối tượng non-null khi hỗ trợ. Nếu một vendor driver bất thường trả null, đó là vấn đề về implementation/contract cần điều tra, không nên im lặng coi extension tồn tại mà null là thành công.

**Đừng nuốt SQLException:** helper vẫn khai báo `throws SQLException`. Lỗi truy cập connection hoặc driver configuration nên được xử lý ở tầng JDBC error handling của ứng dụng.

### 13.3. Feature bắt buộc

Nếu nghiệp vụ không thể hoạt động khi không có extension, nên báo lỗi cấu hình có nguyên nhân rõ ràng:

```java
if (!connection.isWrapperFor(RequiredVendorFeature.class)) {
    throw new SQLException(
            "Configured JDBC driver/pool does not expose required interface");
}
RequiredVendorFeature feature =
        connection.unwrap(RequiredVendorFeature.class);
```

Đây là **đoạn tích hợp**, interface `RequiredVendorFeature` chỉ là ví dụ. Đừng tự động tiếp tục với đường fallback thiếu bảo đảm nếu extension thực sự cần cho dữ liệu/transaction.

## 14. Khả năng tương thích driver và thư viện

**`Wrapper` là API ổn định**, nhưng **interface mở rộng của vendor không portable**.

### 14.1. Dependencies

Code gọi `VendorExtension.class` phải biên dịch được với thư viện cung cấp interface ấy. Nếu interface nằm trong JAR của driver, dự án có thể cần khai báo dependency phù hợp. Không nên dùng tên `Class.forName(...)` bằng chuỗi tùy ý và reflection chỉ để né dependency nếu có thể thiết kế adapter rõ ràng.

Với đa driver, một **adapter pattern** tách vendor handling khỏi business code thường phù hợp hơn:

```text
BusinessService
       |
       v
PortableRepository (java.sql)
       |
       +--> Default JDBC operations
       |
       +--> VendorAdapterA (optionally unwraps VendorAInterface)
       |
       +--> VendorAdapterB (optionally unwraps VendorBInterface)
```

### 14.2. Thay driver hoặc nâng version

Khi nâng driver, kiểm tra lại:

- Interface extension có còn tồn tại/đúng package không?
- Connection pool có expose interface đó qua `isWrapperFor` và `unwrap` không?
- API extension có thay đổi semantics khi chạy trong transaction không?
- Có thể triển khai behavior tương đương bằng JDBC chuẩn mới hơn không?
- Lớp pool có thêm/bớt một tầng proxy khiến việc ép kiểu implementation class bị hỏng không?
- Thời điểm close/reuse/prepare/execute có còn hợp lệ với extension không?

**Đừng coi kết quả từ một driver là luật cho tất cả driver.**

### 14.3. Class loader và module path

JDBC driver/pool có thể chạy trong application server, plugin class loader hoặc named module. Một interface được xem là “cùng tên” nhưng đến từ **hai class loaders khác nhau** không phải một `Class` giống nhau. `isWrapperFor(iface)` nhận chính `Class<?>`, nên việc chọn đúng dependency và class loader có thể ảnh hưởng kết quả.

Trong dự án lớn, tránh tạo một bản copy khác của vendor API trong class loader không tương thích; xem class path/module path và cách ứng dụng triển khai driver.

## 15. Phân biệt các lỗi liên quan

| Hiện tượng | Ý nghĩa thường gặp | Hướng xử lý |
| --- | --- | --- |
| `ClassCastException` khi cast pooled connection thành vendor implementation | Proxy ngoài không implement concrete type | Thay bằng `isWrapperFor`/`unwrap` theo interface |
| `isWrapperFor(...) == false` | Interface không được wrapper chain expose | Dùng đường portable hoặc báo thiếu required capability |
| `isWrapperFor(...)` ném `SQLException` | Lỗi JDBC khi xác định khả năng unwrap | Xử lý/log theo JDBC error path; không coi mặc định là false |
| `unwrap(...)` ném `SQLException` | Không tìm được interface hoặc lỗi trong quá trình unwrap | Kiểm tra type/driver/pool; bắt SQLException có thông báo phù hợp |
| `SQLFeatureNotSupportedException` | Một optional JDBC feature không được driver hỗ trợ | Kiểm tra JDBC alternatives và driver capabilities |
| `connection.isClosed() == true` | Logical handle đã đóng | Không dùng extension gắn với connection đó |
| Dùng được extension nhưng hành vi transaction kỳ lạ | Bypass pool/framework semantics | Dùng JDBC chuẩn khi có; đọc tài liệu driver/pool |
| Không thể import vendor interface | Thiếu dependency hoặc sai version | Thêm driver API phù hợp, tránh ép kiểu theo tên implementation |
| Cùng driver nhưng `unwrap` khác qua pool | Pool có chính sách proxy/wrapper riêng | Kiểm tra driver và pool phối hợp, integration test |
| `unwrap(Connection.class)` không cho “raw” như kỳ vọng | Wrapper được phép trả chính nó hoặc proxy | Đừng lấy `Connection.class` như cách phá lớp pool |
| Extension dừng hoạt động sau try-with-resources | Connection đã được trả về pool | Không lưu extension qua vòng đời mượn connection |

### `SQLException` không có nghĩa luôn là “không hỗ trợ”

Hợp đồng `unwrap` yêu cầu `SQLException` nếu không tìm được interface, nhưng `isWrapperFor` cũng có thể ném do lỗi nội bộ. Do đó trong ứng dụng quan trọng, cần phân loại thông điệp/cause/SQLState theo **hợp đồng driver cụ thể** thay vì dùng một catch-all để biến mọi lỗi thành tính năng vắng mặt.

## 16. Kiểm thử với driver và pool thật

Ví dụ mock của mục 6 giúp kiểm tra **hợp đồng thuật toán**, nhưng không chứng minh kết quả của PostgreSQL, SQL Server, Oracle, MySQL hoặc pool cụ thể. Khi triển khai production, nên có **integration tests**:

| Ca kiểm thử | Điều cần xác minh |
| --- | --- |
| JDBC chuẩn không extension | `Connection` thực hiện query/transaction bình thường, không lệ thuộc unwrap |
| `isWrapperFor(Connection.class)` | Trả true cho object implement `Connection` theo contract |
| Driver extension có hỗ trợ | `isWrapperFor(VendorInterface.class)` true và `unwrap` trả object implement interface |
| Không hỗ trợ | `isWrapperFor` false; `unwrap` báo `SQLException` nếu vẫn gọi |
| Driver trực tiếp, không pool | Behavior phù hợp Javadoc driver |
| Cùng driver qua pool | Behavior có đúng qua proxy pool không |
| Hai tầng wrapper | Extension vẫn được expose nếu implementation hỗ trợ |
| Thực thi method vendor | Đầu ra/side effects đúng trong transaction |
| `close`/trả về pool | Không leak connection, không đóng raw physical session sai cách |
| Reuse và nhiều requests | Extension không bị giữ sang request khác |
| Statement extension | `Statement` hoặc `PreparedStatement` unwrap đúng type, đúng thời điểm |
| ResultSet extension | Không giữ cursor sau khi result set đóng |
| Driver nâng version | API và behavior không bị thay đổi bất ngờ |
| Failure path | SQLException được log/phân loại, rollback và cleanup đúng |

### Gợi ý test kết hợp `try-with-resources`

```java
try (Connection c = dataSource.getConnection()) {
    if (!c.isValid(3)) {
        throw new SQLException("Connection invalid");
    }
    if (c.isWrapperFor(MyVendorExtension.class)) {
        MyVendorExtension ext = c.unwrap(MyVendorExtension.class);
        ext.runCheck();
    }
}
```

Đây là **mẫu tích hợp**, cần `dataSource`, interface/method driver thật, DB và timeout tùy môi trường. `isValid(3)` kiểm tra connection theo contract JDBC với timeout tính bằng giây; **nó là một phép kiểm tra khác với `isWrapperFor`**.

**Không xây test chỉ dựa vào tên class của `c.getClass()`**. Pool hoặc driver có thể đổi implementation/proxy mà ứng dụng vẫn hoàn toàn đúng về mặt JDBC. Kiểm thử theo **interfaces, behavior và ownership**.

## 17. Lỗi thiết kế phổ biến và cách tránh

1. **Ép kiểu trực tiếp connection của pool** sang driver class rồi catch `ClassCastException`: dùng `isWrapperFor` + `unwrap` theo interface; nếu không được, chọn portable fallback hoặc báo cấu hình.
2. **Cho rằng unwrap luôn trả raw physical connection**: Javadoc cho phép trả proxy; không có lời hứa về identity, physical socket hoặc quyền quản lý trực tiếp.
3. **Đóng cả proxy và delegate như hai resources khác nhau**: chỉ đóng handle do `DataSource` cấp theo vòng đời đã được tài liệu hóa.
4. **Giữ extension trong biến static/cache**: có thể vượt vòng đời logical connection; dùng nó trong phạm vi request/transaction mượn connection.
5. **Gọi `unwrap` với concrete internal driver class** theo suy đoán: API nhận `Class` định nghĩa interface; nên dựa vào vendor-supported interface.
6. **Nuốt mọi SQLException** rồi coi unsupported: phân biệt “không có extension” với lỗi hạ tầng.
7. **Coi isWrapperFor là health-check**: nó không chứng minh DB vẫn kết nối hoặc transaction còn hợp lệ.
8. **Coi DataSource và Connection unwrap là một**: chúng có phạm vi ownership khác nhau, không bảo đảm expose cùng interface.
9. **Dùng extension khi đã có JDBC chuẩn tương đương**: làm code phụ thuộc vendor và có thể bypass pool logic.
10. **Lệ thuộc class identity/`getClass().getName()`** trong logic nghiệp vụ: proxies có thể thay đổi khi nâng pool.
11. **Chỉ test driver raw, không test pool**: ứng dụng production có thể dùng proxy khác với lúc integration test.
12. **Không khai báo dependency của vendor interface**: code có thể thiếu class tại compile/run time hoặc class loader không tương thích.

## 18. Câu hỏi tự kiểm tra

**1. `Wrapper` thuộc package nào và có cần dependency ngoài JDK không?**

`java.sql.Wrapper` nằm trong module chuẩn `java.sql`. Không cần dependency ngoài JDK để gọi API này. Muốn dùng interface extension của driver cụ thể thì cần thư viện driver tương ứng.

**2. `isWrapperFor(iface)` kiểm tra object hiện tại hay cả delegate chain?**

Cả hai. Nếu object tự implement interface thì true; nếu trực tiếp hoặc gián tiếp bọc một object implement interface thì cũng true, theo hợp đồng.

**3. Nếu `connection instanceof VendorFeature` trả false, `isWrapperFor(VendorFeature.class)` có thể true không?**

Có. `connection` có thể là proxy pool chỉ implement `Connection`, nhưng bao bọc một delegate có `VendorFeature`.

**4. `unwrap(Connection.class)` có luôn trả raw connection và luôn khác `connection` không?**

Không. Nó có thể trả chính object đó, một delegate hoặc proxy implement `Connection`. Không dùng nó để suy ra mình đã thoát khỏi pool.

**5. Gọi `unwrap(UnsupportedInterface.class)` khi không hỗ trợ có trả null không?**

Theo contract, ném `SQLException` khi không tìm được object implement interface đó. Không dùng null-check làm đường xử lý mặc định.

**6. Có bắt buộc gọi `isWrapperFor` trước `unwrap` không?**

Không. Nếu tính năng bắt buộc, có thể gọi `unwrap` và xử lý `SQLException`. Khi tính năng tùy chọn, kiểm tra trước giúp quyết định fallback rõ ràng.

**7. `isWrapperFor` có thể ném SQLException không?**

Có. Nó không phải phép kiểm tra chắc chắn không lỗi. `false` và `SQLException` là hai trạng thái khác nhau.

**8. Có nên đóng object được `unwrap` ra ngay sau khi dùng không?**

Không mặc định. Nếu nó là delegate của pooled logical connection, đóng trực tiếp có thể phá lifecycle của pool. Giữ ownership ở Connection được caller mượn, trừ khi vendor cung cấp hợp đồng quản lý khác rõ ràng.

**9. Một `DataSource` implement `Wrapper` thì `dataSource.unwrap(Connection.class)` có bắt buộc trả Connection không?**

Không. DataSource là factory, không phải một phiên Connection. Chỉ có thể unwrap interface mà DataSource hoặc delegate của chính DataSource hỗ trợ.

**10. Nếu JDBC chuẩn đã có method tương đương tính năng vendor, nên chọn gì?**

Thường ưu tiên JDBC chuẩn để portable, giảm coupling và phù hợp hơn với connection pool/transaction management.

**11. Vì sao cần test qua connection pool thật dù demo giả đã pass?**

Vì từng pool/driver có thể expose extensions, cấu trúc proxy và semantics close khác nhau. Demo chỉ chứng minh một implementation mô phỏng tuân thủ một phần của Wrapper.

**12. `isWrapperFor(Connection.class) == true` có chứng minh Connection đang kết nối DB không?**

Không. Chỉ xác nhận khả năng truy cập interface `Connection`, không phải lệnh kiểm tra kết nối sống. Dùng `isValid` hoặc thao tác JDBC phù hợp khi cần health check.

## Tài liệu chính thức và thực tiễn hiện hành

- [Oracle Java SE 26 — `java.sql.Wrapper`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Wrapper.html): hợp đồng `isWrapperFor` và `unwrap`, chuỗi delegate và quyền trả proxy.
- [Oracle Java SE 26 — `java.sql.Connection`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Connection.html): extends `Wrapper`, `AutoCloseable`, `isValid`, transaction và cách close.
- [Oracle Java SE 26 — `java.sql.Statement`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Statement.html): statement extends `Wrapper`.
- [Oracle Java SE 26 — `java.sql.PreparedStatement`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/PreparedStatement.html): prepared statement và JDBC extension handling.
- [Oracle Java SE 26 — `java.sql.ResultSet`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/ResultSet.html): result set và wrapper APIs.
- [Oracle Java SE 26 — `javax.sql.DataSource`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/javax/sql/DataSource.html): DataSource extends `Wrapper`, provider connection và pooling lifecycle.
- [Oracle Java SE 26 — `java.sql.SQLException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLException.html): checked exceptions, SQLState và diagnostics.
- [Oracle Java SE 26 — `SQLFeatureNotSupportedException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLFeatureNotSupportedException.html): khi driver không hỗ trợ optional JDBC feature.
- [Microsoft Learn — JDBC Driver for SQL Server: Wrappers and interfaces](https://learn.microsoft.com/en-us/sql/connect/jdbc/wrappers-and-interfaces): ví dụ driver thực có hỗ trợ `Wrapper`; không biến chi tiết vendor thành luật chung JDBC.

**Ghi nhớ:** `isWrapperFor(MyInterface.class)` hỏi liệu đối tượng JDBC có **trực tiếp hoặc gián tiếp expose một interface** hay không; `unwrap(MyInterface.class)` trả một **đối tượng hoặc proxy implement interface đó**, hoặc ném `SQLException` khi không hỗ trợ. Đây là cầu nối chuẩn cho JDBC driver-specific features trong hệ thống dùng proxy/pool, **không phải công cụ bỏ qua ownership, transaction hoặc lifecycle của connection**. Chỉ unwrap khi cần, luôn ưu tiên JDBC portable nếu đáp ứng nghiệp vụ, và kiểm thử với driver/pool thật trước khi phát hành.
