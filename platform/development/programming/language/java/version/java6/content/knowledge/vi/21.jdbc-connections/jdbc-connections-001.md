# JDBC 4.0 và các hợp đồng tiếp tục được dùng trong driver hiện đại

## 1. Học JDBC 4.0 ở thời điểm Java hiện đại là học điều gì?

**JDBC (Java Database Connectivity)** là API chuẩn của Java để truy cập dữ liệu có cấu trúc, chủ yếu là cơ sở dữ liệu quan hệ. JDBC tách **mã ứng dụng** khỏi **driver của nhà cung cấp cơ sở dữ liệu**: ứng dụng làm việc với `Connection`, `PreparedStatement`, `ResultSet`, `SQLException`, còn driver chuyển lời gọi chuẩn thành giao thức thực của PostgreSQL, MySQL, SQL Server, Oracle Database, v.v.

**JDBC 4.0** được phát hành cùng **Java SE 6**. Nhiều hợp đồng rất quan trọng từ phiên bản ấy vẫn hiện diện trong driver hiện đại: **tự phát hiện driver qua service provider**, `Connection.isValid(int)`, `Wrapper.unwrap/isWrapperFor`, các kiểu `SQLXML`/`RowId`/`NClob` và **cấu trúc `SQLException` rõ hơn**. Những API lõi đã tồn tại trước JDBC 4.0 — `DataSource`, `DriverManager`, `Connection`, `PreparedStatement`, `ResultSet`, transaction — vẫn quan trọng và **không nên bị mô tả nhầm là tính năng mới ra đời ở 4.0**.

Tính đến tài liệu **Java SE 26**, gói `java.sql` mô tả **JDBC 4.5** như API hiện hành, tích lũy các đời trước. Vì vậy bài này **không** dạy cách chạy “một driver JDBC 4.0 đời cũ” trên Java mới; nó giải thích **hợp đồng từ JDBC 4.0 nào còn sống, cách dùng an toàn ngày nay và điểm khác các bản JDBC 4.1+**.

### Sau bài học bạn sẽ làm được

1. Giải thích lớp `DriverManager`, interface `Driver`, `DataSource` và driver JAR phối hợp thế nào.
2. Chạy một ví dụ `java.sql.Driver` tự khai báo qua `META-INF/services/java.sql.Driver` mà **không cần database server**, kiểm tra `Connection.isValid`, `Wrapper`, xử lý lỗi và đóng kết nối.
3. Viết code ứng dụng dùng `DataSource` + `PreparedStatement` + `ResultSet` và quản lý tài nguyên bằng try-with-resources trong **Java 17+**.
4. Biết khi nào `SQLXML`, `RowId`, `NClob` và các phương thức JDBC 4.0 có thể được dùng, đồng thời xử lý driver **không hỗ trợ** một tính năng.
5. Phân biệt API được giới thiệu ở **JDBC 4.0** với JDBC 4.1/4.2/4.3/4.4/4.5; tránh kết luận “có method trong JDK” là “mọi database đều hỗ trợ”.

## 2. Sơ đồ hợp đồng kết nối

~~~text
                         Application / Service
                         (Data Access Layer)
                                    |
                       +------------+------------+
                       |                         |
                       v                         v
                 DataSource                 DriverManager
              (recommended)                  (supported)
                       |                         |
                       +------------+------------+
                                    |
                                    v
                           java.sql.Connection
                                    |
                 +------------------+------------------+
                 |                  |                  |
                 v                  v                  v
          PreparedStatement    Transaction        DatabaseMetaData
                 |           commit/rollback          |
                 v                  |                  |
              ResultSet             |                  |
                 +------------------+------------------+
                                    |
                                    v
                    Vendor JDBC driver implementation
                                    |
                                    v
                           Database server
~~~

Trong sơ đồ:

- **Ứng dụng** chỉ cần thao tác với hợp đồng chuẩn khi có thể.
- **Driver** triển khai các interface chuẩn và giao tiếp với database. Một JAR driver có thể được ServiceLoader tìm thấy qua metadata; nó vẫn phải tuân thủ registration/driver lookup contract.
- **DriverManager** chọn driver phù hợp theo JDBC URL nếu ứng dụng chọn cơ chế trực tiếp.
- **DataSource** là factory kết nối được **Oracle Java API khuyến nghị** cho ứng dụng, vì có thể gắn cấu hình, pool và transaction infrastructure tùy implementation.
- **Connection/PreparedStatement/ResultSet** là các đối tượng thực thi: tạo kết nối, bind parameters, thực thi SQL và đọc kết quả.
- **Transaction lifecycle** thuộc hợp đồng `Connection`, nhưng mức isolation, semantics của SQL và khả năng từng feature cần được kiểm tra theo database.

JDBC API nằm trong **module `java.sql`** ở Java 9+, gồm `java.sql` và `javax.sql`. Một **driver JAR riêng** vẫn phải có mặt ở runtime — JDK cung cấp interface, **không tự tích hợp driver cho mọi database**.

## 3. Timeline: JDBC 4.0 thực sự thêm gì, và cái gì là bổ sung sau này?

Tài liệu `java.sql` của Oracle Java SE 26 có bảng phân biệt các đời API. Nắm rõ mốc này giúp không sao chép kiến thức lỗi thời và không gán sai công trạng cho JDBC 4.0.

| API / thay đổi | Phiên bản được giới thiệu | Điều còn liên quan |
| --- | --- | --- |
| `Connection`, `Statement`, `PreparedStatement`, `ResultSet`, `SQLException`, `DriverManager` | Có **trước JDBC 4.0** | Vẫn là hợp đồng nền tảng |
| `javax.sql.DataSource`, pool/XA interfaces | JDBC 2.x, **trước JDBC 4.0** | `DataSource` hiện vẫn là cách cấp connection được khuyến nghị |
| **Tự phát hiện `java.sql.Driver` bằng service provider** | **JDBC 4.0 / Java 6** | Driver JAR hiện đại thường tự được tìm thấy; không cần `Class.forName` khi cấu hình chuẩn |
| `Connection.isValid(int)` | **JDBC 4.0 / Java 6** | Kiểm tra tính khả dụng của connection, timeout tính bằng giây |
| `Wrapper.isWrapperFor/unwrap` | **JDBC 4.0 / Java 6** | Truy cập vendor extension khi cần và có thể kiểm tra trước |
| `SQLXML`, national character types, `RowId` | **JDBC 4.0 / Java 6** | Chỉ dùng khi DB và driver hỗ trợ |
| `createBlob/createClob/createNClob/createSQLXML` và giải phóng LOB | **JDBC 4.0 / Java 6** | Quản lý lifecycle dữ liệu lớn/tài nguyên đặc biệt |
| Cải tiến `SQLException` và nhóm subclass theo SQLState | **JDBC 4.0 / Java 6** | Phân biệt nhóm lỗi tạm thời, không tạm thời, timeout, integrity... |
| **Try-with-resources cho Connection/Statement/ResultSet** | **JDBC 4.1 / Java 7** | Cách viết **nên dùng ngày nay**; không phải tính năng có sẵn trong Java 6 |
| `Connection.setSchema`, `abort`, `setNetworkTimeout`, typed `getObject` | **JDBC 4.1 / Java 7** | Không gán là JDBC 4.0 |
| `SQLType`, `JDBCType`, hỗ trợ large update counts | **JDBC 4.2 / Java 8** | Mapping type hiện đại, tránh giả định có từ Java 6 |
| `DriverManager.drivers()`, request hints, sharding API | **JDBC 4.3 / Java 9** | Chỉ cần cho trường hợp có hỗ trợ thực tế |
| JDBC 4.4 | **Java 24** | Tiếp tục thay đổi API/contracts của JDK hiện hành |
| JDBC 4.5, hỗ trợ `AutoCloseable` trên một số SQL data interfaces, thêm kiểu `JSON`/`DECFLOAT` | **Java 26** | Không dùng các API này nếu đang biên dịch với `--release 17` |

**Ví dụ quan trọng:** phần code Java 17+ của bài này có `try (Connection c = ...)` để đóng tài nguyên an toàn, nhưng **đó là cách viết từ JDBC 4.1**, chỉ áp dụng trên runtime Java hiện đại, chứ **không phải khả năng mới xuất hiện trong JDBC 4.0**. Tương tự, việc dùng `DataSource` ở production là lời khuyên vẫn đúng, nhưng `DataSource` **đã xuất hiện trước JDBC 4.0**.

## 4. DriverManager, Driver và tự phát hiện driver

### 4.1. Cơ chế từ JDBC 4.0

Trước cơ chế phát hiện tự động, nhiều ví dụ Java cần:

~~~java
Class.forName("com.vendor.jdbc.Driver");
~~~

Đây là **minh họa cách nạp class thủ công**, **không phải khuyến nghị mặc định cho driver hiện đại**. Kể từ JDBC 4.0, `DriverManager` có thể tìm driver qua cơ chế **Java Service Provider**: JAR driver thường đóng gói resource:

~~~text
META-INF/services/java.sql.Driver
~~~

Nội dung là tên class triển khai `java.sql.Driver`, ví dụ trong bài lab:

~~~text
demo.jdbc.TrainingDriver
~~~

Khi khởi tạo, `DriverManager` tìm các service providers theo cơ chế của Java, sau đó thử các driver đã đăng ký/được nhìn thấy để tìm driver phù hợp với URL.

**Chi tiết dễ bỏ sót khi tự viết driver:** một driver implementation phải **đăng ký một instance với `DriverManager.registerDriver(...)`**, thông thường qua **static initializer của chính driver class** khi được nạp. Service descriptor làm lớp driver **được phát hiện/nạp**; driver phải thực hiện **registration contract**. Ví dụ ở mục 5 có cả hai phần nên đã kiểm thử được việc autodiscovery thực tế.

Với driver JAR chính thống được đóng gói đúng, **ứng dụng bình thường không tự gọi `Class.forName` hay `registerDriver`**. Việc tạo driver mới hoặc trình cắm tự viết là phạm vi đặc thù; thư viện driver của vendor đã lo đăng ký.

### 4.2. JDBC URL và việc chọn driver

JDBC URL có dạng tổng quát:

~~~text
jdbc:subprotocol:subname
~~~

Phần chi tiết thuộc từng driver, không có một JDBC URL chung cho tất cả database. Ví dụ `jdbc:training:demo` trong bài là **URL giả của driver tự viết**, không phải database network endpoint.

`DriverManager.getConnection(url)` tìm một driver nhận URL. `DriverManager.getDriver(url)` tìm một driver khai báo chấp nhận URL qua `Driver.acceptsURL`. Nếu không có driver phù hợp hoặc không tạo được connection, bạn có thể nhận `SQLException`.

**Contract cho người viết driver:**

- `Driver.acceptsURL(url)`: báo driver có hiểu URL không.
- `Driver.connect(url, properties)`: **trả `null`** nếu URL **không thuộc driver này**, để DriverManager thử driver khác.
- Nếu URL thuộc driver nhưng tạo kết nối thất bại, `connect` nên ném **`SQLException` phù hợp**, không lặng lẽ trả `null` như thể URL không được hỗ trợ.
- Driver có thể đưa ra `DriverPropertyInfo`, version và trạng thái JDBC-compliance.
- Môi trường class loader/module phức tạp có thể ảnh hưởng driver visibility; `DriverManager` dùng cơ chế service-provider với **thread context class loader** ở thời điểm khởi tạo lazy.

### 4.3. Không dùng mỗi Class.forName để chẩn đoán "No suitable driver"

Một lỗi “No suitable driver” có thể do **thiếu JAR** trong runtime classpath/module path, sai URL, service file thiếu, driver không register, class loader không nhìn thấy driver, hoặc ứng dụng không có quyền/trạng thái phù hợp để kết nối.

Chỉ thêm `Class.forName` thường che giấu một vấn đề đóng gói/configuration. Khi debug:

1. Xác minh đúng JDBC URL theo tài liệu vendor.
2. Xác minh runtime có JAR đúng phiên bản JDK/server.
3. Kiểm tra `META-INF/services/java.sql.Driver` của JAR.
4. Kiểm tra class loader/module và `DriverManager` có thấy driver.
5. Xác nhận thông tin từ `SQLException.getSQLState()/getMessage()/getCause`, tránh in thông tin đăng nhập.

`Class.forName` vẫn có thể là công cụ chẩn đoán trong trường hợp classloading đặc biệt, nhưng **không phải bước bắt buộc của mọi ứng dụng JDBC 4.0+**.

## 5. Lab tự chạy: mock driver minh họa JDBC 4.0 contracts

Để không ép người học phải cài PostgreSQL, MySQL hay database server, ví dụ này tự tạo **một driver mô phỏng tối thiểu**. Nó dùng `java.sql.Driver` và **Java dynamic proxy** để trả về một `Connection` hỗ trợ số ít phương thức đủ cho bài test.

**Giới hạn:** driver này **không nói chuyện với database thật**, không hiểu SQL, không lưu dữ liệu và không phải template để triển khai production JDBC driver. `commit()/rollback()` trong mock chỉ kiểm tra trạng thái; **không có giao dịch thực**. Mục đích duy nhất là test các hợp đồng `DriverManager`, `isValid`, `Wrapper`, SQLState và đóng tài nguyên.

### 5.1. Cấu trúc các tệp

~~~text
jdbc-4-lab/
├── src/
│   └── demo/
│       └── jdbc/
│           ├── TrainingDriver.java
│           ├── DriverContractsDemo.java
│           └── CustomerQueries.java
└── out/
    ├── demo/jdbc/*.class
    └── META-INF/services/java.sql.Driver
~~~

Cần Java 17+ và terminal. Có thể tạo thư mục theo cấu trúc trên bằng IDE, shell hoặc công cụ quản lý file thông thường. Tất cả class của lab đều thuộc package `demo.jdbc`.

### 5.2. File src/demo/jdbc/TrainingDriver.java

~~~java
package demo.jdbc;
import java.lang.reflect.*;
import java.sql.*;
import java.util.Properties;
import java.util.logging.Logger;

public final class TrainingDriver implements Driver {
    public static final String URL = "jdbc:training:demo";
    static {
        try {
            DriverManager.registerDriver(new TrainingDriver());
        } catch (SQLException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    @Override public boolean acceptsURL(String url) { return URL.equals(url); }

    @Override public Connection connect(String url, Properties info) throws SQLException {
        if (!acceptsURL(url)) return null;
        InvocationHandler handler = new InvocationHandler() {
            boolean closed;
            boolean autoCommit = true;

            @Override public Object invoke(Object proxy, Method m, Object[] args)
                    throws Throwable {
                switch (m.getName()) {
                    case "isValid":
                        if ((Integer) args[0] < 0)
                            throw new SQLException("Negative timeout", "HY092");
                        return !closed;
                    case "close": closed = true; return null;
                    case "isClosed": return closed;
                    case "getAutoCommit": return autoCommit;
                    case "setAutoCommit":
                        if (closed) throw new SQLException("Closed", "08003");
                        autoCommit = (Boolean) args[0];
                        return null;
                    case "commit":
                    case "rollback":
                        if (closed) throw new SQLException("Closed", "08003");
                        if (autoCommit)
                            throw new SQLException("Auto-commit enabled", "25000");
                        return null;
                    case "isWrapperFor":
                        return ((Class<?>) args[0]).isInstance(proxy);
                    case "unwrap":
                        Class<?> type = (Class<?>) args[0];
                        if (type.isInstance(proxy)) return type.cast(proxy);
                        throw new SQLException("Not a wrapper for " + type.getName());
                    case "toString": return "TrainingConnection";
                    case "equals": return proxy == args[0];
                    case "hashCode": return System.identityHashCode(proxy);
                    default: throw new SQLFeatureNotSupportedException(
                            "Demo only: " + m.getName());
                }
            }
        };
        return (Connection) Proxy.newProxyInstance(
                Connection.class.getClassLoader(),
                new Class<?>[]{Connection.class}, handler);
    }

    @Override public DriverPropertyInfo[] getPropertyInfo(String url, Properties info) {
        return new DriverPropertyInfo[0];
    }
    @Override public int getMajorVersion() { return 1; }
    @Override public int getMinorVersion() { return 0; }
    @Override public boolean jdbcCompliant() { return false; }
    @Override public Logger getParentLogger() { return Logger.getLogger("demo.jdbc"); }
}
~~~

### 5.3. Giải thích từng phần của fake driver

- `URL` là giá trị cố định `jdbc:training:demo`; `acceptsURL` trả `true` đúng URL ấy.
- **Static initializer** gọi `DriverManager.registerDriver(new TrainingDriver())`. Khi ServiceLoader nạp class, driver được **đăng ký** theo hợp đồng.
- `connect` trả `null` nếu URL khác, **không ném SQLException** cho một URL mà driver không chịu trách nhiệm.
- `Proxy.newProxyInstance` tạo một object triển khai interface `Connection`; invocation handler mô phỏng các lời gọi.
- `isValid(timeout)` trả `!closed` và từ chối timeout âm. **Một driver thật phải kiểm tra kết nối theo contract của JDBC**, không thể chỉ dựa vào biến bool. Mock được gắn nhãn rõ để không lẫn với kết nối thật.
- `setAutoCommit`, `commit` và `rollback` chỉ thay/kiểm tra trạng thái, không thực thi transaction thật.
- `isWrapperFor`/`unwrap` cho phép truy cập object proxy khi interface được yêu cầu là `Connection`, thể hiện hợp đồng `java.sql.Wrapper`.
- Những method không mô phỏng ném `SQLFeatureNotSupportedException` thay vì giả vờ thành công.
- `getParentLogger()` được yêu cầu trong interface `Driver` trên **JDK 17+**; nó thuộc giai đoạn JDBC 4.1/Java 7, **không được trình bày nhầm là phương thức mới của JDBC 4.0**.
- `jdbcCompliant()` trả `false` vì đây không phải driver SQL thật. Giá trị này **không** dùng để quyết định driver nào có tất cả chức năng của JDBC 4.0/4.5.

### 5.4. File src/demo/jdbc/DriverContractsDemo.java

~~~java
package demo.jdbc;
import java.sql.*;

public final class DriverContractsDemo {
    static void check(boolean ok, String detail) {
        if (!ok) throw new AssertionError(detail);
    }

    public static void main(String[] args) throws Exception {
        check(DriverManager.getDriver(TrainingDriver.URL) instanceof TrainingDriver,
                "service discovery/registration failed");
        System.out.println("driver-auto-discovered=true");

        Connection c = DriverManager.getConnection(TrainingDriver.URL);
        try (c) {
            check(c.isValid(2), "invalid connection");
            System.out.println("connection-valid=true");
            check(c.getAutoCommit(), "default autoCommit");
            c.setAutoCommit(false);
            check(!c.getAutoCommit(), "setAutoCommit");
            c.commit();
            c.rollback();
            System.out.println("transaction-contract=true");
            check(c.isWrapperFor(Connection.class), "isWrapperFor");
            check(c.unwrap(Connection.class) == c, "unwrap");
            System.out.println("wrapper-contract=true");
            try {
                c.isValid(-1);
                throw new AssertionError("expected SQLException");
            } catch (SQLException expected) {
                check("HY092".equals(expected.getSQLState()), "SQLState");
                System.out.println("sqlstate=HY092");
            }
        }
        check(c.isClosed(), "try-with-resources");
        System.out.println("closed-after-try=true");

        try {
            DriverManager.getConnection("jdbc:training:other");
            throw new AssertionError("unknown URL must be rejected");
        } catch (SQLException expected) {
            System.out.println("unknown-url=SQLException");
        }
        System.out.println("tests=PASS");
    }
}
~~~

Lưu ý `TrainingDriver.URL` là hằng số compile-time. Dù class chính tham chiếu constant ấy, Java **không cần chạy static initializer của TrainingDriver chỉ để đọc constant**. Chương trình vẫn thử được việc **DriverManager phát hiện và nạp driver qua service file**. Nếu bỏ service file hoặc bỏ registration trong `TrainingDriver`, test `DriverManager.getDriver(...)` có thể thất bại với `SQLException`.

### 5.5. File service của JDBC driver

Tạo file:

~~~text
out/META-INF/services/java.sql.Driver
~~~

với **một dòng**:

~~~text
demo.jdbc.TrainingDriver
~~~

Phải đóng gói file này **bên trong JAR** nếu tự tạo JAR; khi chạy lab, file ở đúng `out/META-INF/services/...` và thư mục `out` có mặt trên classpath là đủ.

Đây là **service configuration file UTF-8**, không phải Java class. Các library JDBC production đã cung cấp metadata tương ứng; ứng dụng không nên copy một file service giả sang JAR thật.

### 5.6. Biên dịch/chạy trên Linux hoặc macOS

Từ thư mục `jdbc-4-lab`:

~~~bash
mkdir -p out/META-INF/services
javac -encoding UTF-8 --release 17 -d out src/demo/jdbc/TrainingDriver.java src/demo/jdbc/DriverContractsDemo.java src/demo/jdbc/CustomerQueries.java
printf 'demo.jdbc.TrainingDriver\n' > out/META-INF/services/java.sql.Driver
java -cp out demo.jdbc.DriverContractsDemo
~~~

### 5.7. Biên dịch/chạy trên Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force 'out/META-INF/services' | Out-Null
javac -encoding UTF-8 --release 17 -d out src/demo/jdbc/TrainingDriver.java src/demo/jdbc/DriverContractsDemo.java src/demo/jdbc/CustomerQueries.java
$utf8 = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText('out/META-INF/services/java.sql.Driver', 'demo.jdbc.TrainingDriver' + [Environment]::NewLine, $utf8)
java -cp out demo.jdbc.DriverContractsDemo
~~~

Dùng `UTF8Encoding($false)` tránh BOM đầu service file, đặc biệt khi dùng Windows PowerShell 5.1.

### 5.8. Stdout đã chạy và xác minh

Ví dụ đã biên dịch và chạy trên **OpenJDK 24** với `javac --release 17`, kết quả chính xác:

~~~text
driver-auto-discovered=true
connection-valid=true
transaction-contract=true
wrapper-contract=true
sqlstate=HY092
closed-after-try=true
unknown-url=SQLException
tests=PASS
~~~

Test bao gồm:

- DriverManager thật sự thấy driver qua service file + static registration.
- `Connection.isValid(2)` trả `true` trước khi đóng trong fake.
- `setAutoCommit(false)` rồi gọi `commit()/rollback()` được handler nhận diện.
- `isWrapperFor(Connection.class)` và `unwrap(Connection.class)` hoạt động.
- `isValid(-1)` gây `SQLException` với SQLState được **fake định nghĩa là `HY092`**.
- Try-with-resources gọi `close()`; sau đó `isClosed()` là `true`.
- URL khác bị `DriverManager.getConnection` từ chối.

**Không suy rộng** rằng database nào cũng sẽ dùng SQLState `HY092` cho mọi invalid timeout: test chỉ assert giá trị do mock tạo. Không suy rằng `c.commit()` đã ghi dữ liệu: không có database. Muốn chứng minh SQL/transactions thực sự thành công, cần **integration test với vendor driver và database thật**.

## 6. DataSource và code ứng dụng thực tế

Oracle Java SE 26 vẫn ghi rõ: **`javax.sql.DataSource` là cách được ưu tiên để lấy connection**, trong khi `DriverManager` vẫn được hỗ trợ. `DataSource` đã tồn tại trước JDBC 4.0, nhưng sự phân tách factory/connection của nó cực kỳ quan trọng trong kiến trúc ứng dụng hiện đại.

### 6.1. DriverManager phù hợp ở đâu?

`DriverManager.getConnection(url, properties)` rất hữu ích cho:

- Công cụ CLI nhỏ hoặc thử nghiệm ban đầu.
- Bài học về JDBC driver discovery và URL.
- Trường hợp không có dependency-injection hay pooling infrastructure.

Nhược điểm của việc gọi trực tiếp khắp code: cấu hình URL/user/password và lựa chọn pool khó tập trung, tạo kết nối vật lý liên tục có thể tốn tài nguyên.

### 6.2. DataSource cho ứng dụng có nhiều request

`DataSource.getConnection()` trả một `Connection` theo implementation. Một `DataSource` có thể là:

- Basic factory của vendor.
- Một DataSource được pool manager bọc quanh, cấp **logical connections** từ pool.
- Cấu hình được quản lý bởi framework/container, có thể tham gia transaction management.

**`DataSource` không tự động có pooling** chỉ vì nó là DataSource: phải có implementation và cấu hình pool phù hợp. Ngược lại, khi dùng pooled DataSource, `Connection.close()` thường **trả logical connection về pool**, không nhất thiết đóng TCP/database physical connection ngay lập tức.

### 6.3. Tệp Java đã kiểm tra biên dịch: CustomerQueries.java

Mẫu này sử dụng `DataSource`, `PreparedStatement` và `ResultSet`. Nó được **biên dịch với Java 17**, nhưng để **chạy query** phải có driver, `DataSource` được cấu hình và bảng `customers(id, name)` tồn tại ở database. Không khẳng định đã thực hiện SQL trên database thật trong bài lab không có server.

~~~java
package demo.jdbc;

import java.sql.*;
import java.util.Objects;
import java.util.Optional;
import javax.sql.DataSource;

public final class CustomerQueries {
    private final DataSource dataSource;

    public CustomerQueries(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public Optional<String> findName(long id) throws SQLException {
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(
                     "SELECT name FROM customers WHERE id = ?")) {
            statement.setLong(1, id);
            try (ResultSet rows = statement.executeQuery()) {
                return rows.next()
                        ? Optional.ofNullable(rows.getString("name"))
                        : Optional.empty();
            }
        }
    }

    public int rename(long id, String newName) throws SQLException {
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(
                     "UPDATE customers SET name = ? WHERE id = ?")) {
            statement.setString(1, newName);
            statement.setLong(2, id);
            return statement.executeUpdate();
        }
    }
}
~~~

### 6.4. Đọc code theo hợp đồng

- `dataSource.getConnection()` lấy logical/physical connection tùy implementation.
- `connection.prepareStatement("... ?")` tạo prepared statement với **parameter markers**.
- `setLong(1, id)`, `setString(1, newName)` truyền **dữ liệu**, không tự nối chuỗi SQL.
- `ResultSet.next()` di chuyển cursor; lúc đầu cursor ở trước hàng đầu tiên. `getString("name")` đọc cột theo label.
- `Optional.empty()` khi không có hàng. Nếu có hàng nhưng giá trị SQL NULL, `getString` trả `null`, nên `Optional.ofNullable(...)` giữ contract Java.
- `executeUpdate()` trả số hàng bị ảnh hưởng theo semantics của driver/DB; repository/caller có thể kiểm tra có đúng 1 hàng hay không.
- `try (...)` đóng ResultSet, PreparedStatement và Connection theo cơ chế **AutoCloseable từ JDBC 4.1/Java 7**. Các tài nguyên được đóng ngay cả khi có `SQLException` trong khối.

### 6.5. PreparedStatement có ngăn được mọi SQL injection?

Parameterized SQL bảo vệ **các giá trị được bind bằng dấu `?`**, tránh việc đưa input thành SQL syntax. Nhưng **table names, column names, order-direction và nhiều SQL identifiers không thể thay thế bằng `?`**. Nếu chúng phải thay đổi theo yêu cầu người dùng, dùng **allowlist tường minh** và quote identifier theo API/DB thích hợp.

Không tạo SQL kiểu:

~~~java
// ĐOẠN PHẢN VÍ DỤ - KHÔNG LÀM NHƯ VẬY:
String sql = "SELECT name FROM customers WHERE id = " + inputFromUser;
~~~

Đây là **minh họa sai**, không phải chương trình đầy đủ. Việc nối input chưa tin cậy vào SQL có thể tạo SQL injection và lỗi type/escaping.

Bên cạnh parameterization còn cần **least-privilege database credentials**, TLS theo driver, timeout, kiểm tra quyền truy cập dữ liệu ở application, logging loại bỏ secrets và audit.

## 7. Connection lifecycle: điều hợp đồng vẫn giữ nguyên

### 7.1. isClosed khác isValid

`Connection.isClosed()` chỉ cho biết object connection đã bị đóng theo API; nó **không nhất thiết gửi phép kiểm tra tích cực đến database**. Một socket bị ngắt không luôn được phát hiện tức thì chỉ qua `isClosed()`.

`Connection.isValid(int timeout)`, có từ Java 6/JDBC 4.0, yêu cầu driver kiểm tra tính hợp lệ bằng query hoặc cách khác **tích cực xác nhận kết nối**. Nó:

- Trả `true` nếu connection còn hợp lệ, `false` nếu đóng/không hợp lệ theo contract.
- Tham số `timeout` là **giây**, `0` có nghĩa không áp một giới hạn timeout cho phép kiểm tra.
- Timeout âm phải gây `SQLException`.
- Hoạt động kiểm tra thực tế là **driver-dependent** và có thể tốn round-trip; không gọi vô điều kiện trước **mỗi câu SQL** nếu pool đã có chính sách validation hợp lý.
- Không thay thế `SQLException` handling: connection có thể mất ngay **sau** khi `isValid` trả true.

Trong fake driver, `isValid` chỉ kiểm tra flag đóng **để minh họa contract**, không phải kiểu implementation đúng cho driver network thật.

### 7.2. Auto-commit, commit và rollback

Khi connection mới được tạo, auto-commit thường **bật** theo hợp đồng JDBC: từng SQL statement hoàn tất sẽ được commit theo quy tắc DB. Gọi:

~~~java
connection.setAutoCommit(false);
~~~

là **đoạn trích** cho một `Connection` chưa đóng. Sau đó ứng dụng quản lý transaction boundaries bằng `commit()` và `rollback()`. Trong ứng dụng thực, phải:

1. Bảo đảm mọi statement cần transaction dùng **cùng một Connection**.
2. Tắt auto-commit trước chuỗi thao tác cần atomicity.
3. Xác nhận **số hàng bị ảnh hưởng** và các điều kiện nghiệp vụ.
4. `commit()` chỉ sau khi tất cả bước thành công.
5. `rollback()` khi có lỗi hoặc bất biến không đạt; tránh để lỗi rollback che mất exception gốc.
6. Dọn statement/result set và **trả connection về pool** qua `close()`/try-with-resources.
7. Khi tự quản lý connection từ pool, khôi phục trạng thái transaction/isolation/readOnly theo policy của pool; không phụ thuộc mù quáng vào việc pool sẽ reset mọi trạng thái.
8. Khi giao dịch do framework/container/XA quản lý, **không tự gọi `commit/rollback/setAutoCommit`** phá vỡ transaction manager.

**Lưu ý:** `setAutoCommit(true)` khi có transaction đang hoạt động có thể làm transaction được commit theo JDBC contract. Đừng dùng nó như lệnh “reset vô hại” trong khối `finally` nếu vẫn còn transaction chưa được xử lý. Hãy commit hoặc rollback rõ ràng trước.

Không đóng connection giữa một transaction đang dở rồi giả định tất cả driver đều rollback theo một cách giống nhau. Kết thúc transaction bằng lệnh rõ trước khi đóng.

### 7.3. Isolation và DatabaseMetaData

Các mức isolation chuẩn gồm:

~~~text
TRANSACTION_READ_UNCOMMITTED
TRANSACTION_READ_COMMITTED
TRANSACTION_REPEATABLE_READ
TRANSACTION_SERIALIZABLE
~~~

Tùy database, các mức này có thể hỗ trợ khác nhau, đặc biệt do MVCC/snapshot isolation. Hãy kiểm tra `DatabaseMetaData.supportsTransactionIsolationLevel(...)` và hiểu semantics của DB thật thay vì kết luận mọi driver cung cấp tất cả.

`Connection.setTransactionIsolation(...)` thay đổi trạng thái connection; với pooled connection cần quản lý việc trả lại trạng thái mặc định.

### 7.4. Resource ownership

**Một connection không nhất thiết dùng lại được sau `close`.** Với pooled DataSource, `close` trả logical connection về pool; giữ object ấy để dùng ở request sau là sai.

PreparedStatement/ResultSet cũng có lifecycle riêng. Ví dụ thử:

~~~java
try (Connection c = source.getConnection();
     PreparedStatement ps = c.prepareStatement("SELECT id FROM customers")) {
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("id");
            // Sử dụng id ngay trong phạm vi ResultSet còn mở.
        }
    }
}
~~~

Đây là **đoạn minh họa**; `source` phải là một `DataSource` có database và bảng `customers`. Không trả `ResultSet` đã đóng hoặc `Stream` phụ thuộc vào connection đã bị đóng ra ngoài repository.

## 8. java.sql.Wrapper: mở rộng driver mà giữ facade chuẩn

JDBC 4.0 giới thiệu hợp đồng `java.sql.Wrapper` với hai method:

~~~java
boolean isWrapperFor(Class<?> iface) throws SQLException;
<T> T unwrap(Class<T> iface) throws SQLException;
~~~

Các interface JDBC như `Connection`, `Statement`, `ResultSet` và metadata interfaces hỗ trợ cơ chế này. Lý do là pool, application server hoặc vendor thường trả các **wrapper/proxy objects** thay vì trực tiếp đối tượng nội bộ. Khi thật sự cần một vendor extension:

~~~java
if (connection.isWrapperFor(VendorConnection.class)) {
    VendorConnection vendor = connection.unwrap(VendorConnection.class);
    // Chỉ ở vùng tích hợp vendor-specific; không rải khắp business logic.
}
~~~

Đây là **pseudo-Java snippet**, `VendorConnection` là interface giả định từ driver vendor, **không tồn tại trong JDK**. Code thực phải import đúng API từ vendor library tương ứng.

**Không gọi unwrap vô điều kiện** mà giả định driver nào cũng hỗ trợ cùng vendor class. Với pool/proxy nhiều lớp, việc unwrap có thể tạo object không còn chịu cùng lifecycle contract; chỉ dùng trong phạm vi tài liệu vendor cho phép và không tự đóng underlying physical connection sai tầng.

Trong fake driver, `isWrapperFor(Connection.class)` và `unwrap(Connection.class)` được kiểm tra, đủ để chứng minh contract. Một nhà cung cấp driver thật còn có thể expose extensions đặc biệt mà fake không hỗ trợ.

## 9. JDBC 4.0 với kiểu dữ liệu SQLXML, RowId, NClob

Một phần quan trọng của JDBC 4.0 là hỗ trợ những dữ liệu SQL:2003 mới hoặc mở rộng:

| Java API | Ý nghĩa | Lưu ý về tính hỗ trợ |
| --- | --- | --- |
| `SQLXML` | Dữ liệu SQL XML; có `getString/setString` và stream APIs | Chỉ khi DB/driver hỗ trợ XML type |
| `RowId` | SQL ROWID; `ResultSet.getRowId`, `PreparedStatement.setRowId` | Thời gian sống và semantics do DB quyết định |
| `NClob` | National character large object | Không phải mọi DB tách national char types theo cùng cách |
| `setNString/getNString` | Giá trị NCHAR/NVARCHAR theo SQL national character set | Phụ thuộc schema và driver |
| `Connection.createBlob/createClob/createNClob/createSQLXML` | Tạo object để ghi giá trị tương ứng | Cần `free()` khi không dùng nữa |
| `Blob/Clob/NClob.free()`, `SQLXML.free()` | Giải phóng tài nguyên có liên quan | Không nhầm với `Connection.close()` |

**Không mặc định tất cả driver hỗ trợ đủ mọi kiểu**, chỉ vì interface có method. `SQLFeatureNotSupportedException` được thiết kế cho việc thể hiện một tính năng không được triển khai. Với driver/database riêng, cần kiểm tra tài liệu và integration tests.

### 9.1. File chỉ kiểm tra biên dịch: Jdbc40Types.java

File dưới đây là Java 17+ hợp lệ và đã được **biên dịch thành công bằng `javac --release 17`**. Nó **không có main** và không chạy SQL trong lab vì không có database thật/bảng tương ứng. Các methods thể hiện cách dùng chuẩn của kiểu JDBC 4.0.

~~~java
package demo.jdbc;

import java.sql.*;

public final class Jdbc40Types {
    public static boolean checkConnection(Connection connection) throws SQLException {
        return connection.isValid(2);
    }

    public static void updateXml(Connection connection, long id, String xmlText)
            throws SQLException {
        SQLXML xml = connection.createSQLXML();
        try {
            xml.setString(xmlText);
            try (PreparedStatement ps = connection.prepareStatement(
                    "UPDATE documents SET body = ? WHERE id = ?")) {
                ps.setSQLXML(1, xml);
                ps.setLong(2, id);
                ps.executeUpdate();
            }
        } finally {
            xml.free();
        }
    }

    public static void updateNationalText(Connection connection, long id, String text)
            throws SQLException {
        try (PreparedStatement ps = connection.prepareStatement(
                "UPDATE customers SET display_name = ? WHERE id = ?")) {
            ps.setNString(1, text);
            ps.setLong(2, id);
            ps.executeUpdate();
        }
    }

    public static String getNationalText(ResultSet rows) throws SQLException {
        return rows.getNString("display_name");
    }

    public static RowId readRowId(ResultSet rows) throws SQLException {
        return rows.getRowId("rid");
    }

    public static void bindRowId(PreparedStatement statement, RowId rowId)
            throws SQLException {
        statement.setRowId(1, rowId);
    }
}
~~~

Compile:

~~~bash
javac -encoding UTF-8 --release 17 -d out src/demo/jdbc/Jdbc40Types.java
~~~

`updateXml` giả định bảng `documents(id, body)` với kiểu tương thích XML; `updateNationalText` giả định bảng `customers(id, display_name)` với type tương thích; `readRowId` giả định result set có cột `rid`. Nếu DB/driver không hỗ trợ kiểu tương ứng, các lời gọi có thể ném `SQLFeatureNotSupportedException`/`SQLException`.

### 9.2. Giải phóng SQLXML trên Java 17

Ở Java 17, `SQLXML` có `free()` và **không được sử dụng như một `AutoCloseable` trong try-with-resources**. Tài liệu **Java SE 26/JDBC 4.5** mới mô tả `Array`, `Blob`, `Clob`, `NClob` và `SQLXML` mở rộng `AutoCloseable`. Vì mục tiêu compile là `--release 17`, code dùng:

~~~java
SQLXML xml = connection.createSQLXML();
try {
    xml.setString("<entry>sample</entry>");
    // Gửi XML qua PreparedStatement nếu database hỗ trợ.
} finally {
    xml.free();
}
~~~

Đây là **đoạn trích**, cần biến `Connection connection` đang mở. XML do bên ngoài cung cấp cần giới hạn kích thước và cấu hình parser an toàn nếu application tự phân tích XML; `SQLXML` không tự trở thành biện pháp chống XXE hoặc XML injection.

### 9.3. RowId không phải khóa lâu dài có thể chuyển qua mọi database

`RowId` thường liên quan cách database định danh vị trí hàng. `DatabaseMetaData.getRowIdLifetime()` cho biết đời sống RowId theo hỗ trợ của DB; RowId có thể không ổn định sau cập nhật/move/backup hoặc giữa các connection/database.

Đừng lưu `RowId` làm business identifier vĩnh viễn nếu schema có `PRIMARY KEY` thông thường. Chỉ dùng khi chức năng DB cụ thể đòi hỏi và đã kiểm thử semantics.

### 9.4. Unicode và national character types

Java `String` bản thân lưu text Unicode. **Không cần dùng `setNString` chỉ vì chuỗi chứa tiếng Việt**: chọn `setString` hay `setNString` tùy **loại cột SQL** và khả năng của driver/database. Ví dụ với SQL Server NVARCHAR có thể cần mapping national type tùy driver; với database có Unicode mặc định, `VARCHAR` cũng có thể lưu Unicode đúng.

Hãy kiểm tra schema, collation, encoding của kết nối và tài liệu driver; **không áp dụng một quy tắc chung cho mọi vendor**.

## 10. SQLException và lỗi theo nhóm

JDBC 4.0 cải tiến hệ phân cấp exception để lỗi database có thể được phân loại rõ hơn. Thay vì chỉ xử lý mọi `SQLException` như nhau, cần xem:

- `getSQLState()`: mã SQLState theo chuẩn hoặc vendor.
- `getErrorCode()`: error code do vendor cung cấp.
- `getMessage()`: thông báo lỗi, có thể chứa chi tiết cần lọc khi log.
- `getCause()`: nguyên nhân lồng nhau.
- `getNextException()`: chuỗi các `SQLException` liên quan (ví dụ batch).
- Các subclass như `SQLTransientException`, `SQLNonTransientException`, `SQLIntegrityConstraintViolationException`, `SQLTimeoutException`, `SQLFeatureNotSupportedException`, `SQLRecoverableException`.

Ví dụ log lỗi **không chứa password hoặc full JDBC URL có credentials**:

~~~java
try {
    // Thao tác JDBC ở đây.
} catch (java.sql.SQLIntegrityConstraintViolationException e) {
    // Lỗi constraint: thường yêu cầu sửa dữ liệu/quy tắc, không retry mù quáng.
} catch (java.sql.SQLTransientConnectionException e) {
    // Lỗi kết nối tạm thời: retry có giới hạn nếu operation idempotent.
} catch (java.sql.SQLException e) {
    String state = e.getSQLState();
    int code = e.getErrorCode();
    // Ghi log đã lọc, gửi thông báo an toàn cho người dùng.
    throw e;
}
~~~

Đây là **đoạn phác thảo trong method có `throws SQLException`**, không phải file Java độc lập. **Không** dùng exception class đơn lẻ để chắc chắn một lỗi có thể retry; còn phải xét **idempotency, transaction state và semantics của database**. Ví dụ transaction commit có thể đã xảy ra dù client mất kết nối trước khi nhận response, nên retry nguyên lệnh chuyển tiền một cách mù quáng có thể gây double write.

### 10.1. SQLFeatureNotSupportedException

Method tồn tại ở Java SE API **không có nghĩa driver/database hỗ trợ được**. Các lựa chọn đúng:

1. Xác minh khả năng với metadata hoặc tài liệu driver nếu có.
2. Thực hiện một integration test trên DB thật.
3. Bắt `SQLFeatureNotSupportedException` **chỉ ở nơi có một phương án thay thế hợp lệ**.
4. Không nuốt lỗi rồi trả giá trị mặc định làm ứng dụng tưởng đã lưu dữ liệu thành công.

Ví dụ `NClob`, `RowId`, `SQLXML` và result-set types nâng cao đều có thể bị giới hạn theo vendor.

### 10.2. SQLState trong fake driver

Mock ở phần 5 ném:

~~~java
throw new SQLException("Negative timeout", "HY092");
~~~

và test đọc lại `expected.getSQLState()`. `HY092` trong lab là **mã mà chính mock chọn để chứng minh cơ chế**, không phải tuyên bố mọi driver hoặc mọi trường hợp timeout âm sẽ trả đúng mã này. Contract của `Connection.isValid(-1)` là có `SQLException`; SQLState cụ thể phải kiểm tra theo driver.

## 11. Connection pool, timeout và metadata trên ứng dụng hiện đại

### 11.1. Pooling và logical connections

Trong service có nhiều request, tạo physical DB connection liên tục có thể tốn thời gian, bộ nhớ và quota phía server. Nên dùng **DataSource có pooling được cấu hình đúng**. `getConnection` thường cấp một logical connection từ pool, và `close()` trả nó về pool.

Đừng giữ connection trong static field của repository để tái sử dụng giữa các request. Cũng không share `Connection` giữa threads bừa bãi; concurrency guarantees và trạng thái transaction cần theo hợp đồng của driver/pool.

### 11.2. Các loại timeout khác nhau

| Timeout | API/điểm cấu hình | Điều kiểm soát |
| --- | --- | --- |
| Login/connection acquisition | `DriverManager.setLoginTimeout` hoặc cấu hình `DataSource`/pool | Chờ tạo/lấy connection, tùy implementation |
| Validation | `Connection.isValid(seconds)` | Giới hạn chờ phép kiểm tra connection |
| Query | `Statement.setQueryTimeout(seconds)` | Thời gian chờ thực thi statement, với semantics driver |
| Network/socket | Thuộc driver/pool, `Connection.setNetworkTimeout` từ JDBC 4.1 | Network I/O, theo vendor/driver |
| Pool acquisition | Cấu hình pool manager | Thời gian chờ mượn logical connection |

Không nhầm `isValid(3)` với “mọi query chạy tối đa ba giây”. `Statement.setQueryTimeout` cũng có khác biệt mức hỗ trợ/cancellation giữa vendors; hãy kiểm thử.

### 11.3. DatabaseMetaData thay vì đoán

`Connection.getMetaData()` cho phép truy vấn `DatabaseMetaData`:

~~~java
java.sql.DatabaseMetaData m = connection.getMetaData();
int major = m.getJDBCMajorVersion();
int minor = m.getJDBCMinorVersion();
boolean transactions = m.supportsTransactions();
boolean savepoints = m.supportsSavepoints();
~~~

Đây là **đoạn minh họa** với `connection` là Connection thật. Chú ý: metadata trả thông tin được driver khai báo, **không đủ để chứng minh mọi trường hợp sử dụng một feature sẽ thành công**. Ví dụ chỉ vì `getJDBCMajorVersion() >= 4` không có nghĩa `SQLXML`/`RowId` hoạt động trên mọi type/table/DBMS.

Đối với những feature quan trọng, kiểm tra cụ thể và viết integration tests.

## 12. Không nhầm JDBC 4.0 contracts với cách dùng cũ

| Thói quen gây nhầm | Vấn đề | Cách phù hợp ngày nay |
| --- | --- | --- |
| “JDBC 4.0 phải gọi `Class.forName` trước mọi connection” | Không đúng với driver JAR đóng gói service đúng | Dựa vào auto discovery; chỉ nạp thủ công khi kiến trúc classloading yêu cầu |
| “Java SE 26 vẫn là JDBC 4.0” | API đã phát triển qua 4.1–4.5 | Dùng docs đúng JDK và biết feature ra đời ở phiên bản nào |
| “Try-with-resources thuộc Java 6/JDBC 4.0” | JDBC4.1 mới đưa AutoCloseable cho các JDBC interfaces | Dùng try-with-resources trên Java17+ nhưng ghi đúng lịch sử |
| “DataSource mới xuất hiện ở JDBC 4.0” | Nó đã có từ JDBC 2.x | Vẫn nên ưu tiên DataSource có cấu hình/pool phù hợp |
| “DriverManager tự tạo pool” | Không có đảm bảo pooling từ DriverManager | Dùng DataSource/pool manager |
| “Đã implements Driver và có service file là chắc chắn getConnection thấy driver” | Driver còn cần registration và visibility đúng | Đảm bảo driver class tự register/được load như contract; kiểm tra URL/classloader |
| “Driver hỗ trợ mọi method xuất hiện trong java.sql” | Driver/DB có thể không hỗ trợ feature cụ thể | Kiểm tra metadata/driver docs/integration; xử lý SQLFeatureNotSupportedException |
| “isClosed() cho biết database còn sống” | Không kiểm tra tích cực connection | Dùng isValid khi phù hợp, pool validation, xử lý lỗi lúc query |
| “isValid() thay cho transaction management” | Chỉ kiểm tra kết nối | Xác định commit/rollback/isolation riêng |
| “Cứ tạo NClob/SQLXML là portable tuyệt đối” | DB types và driver mapping khác nhau | Kiểm tra schema và hỗ trợ của vendor |
| “SQLXML dùng `try(SQLXML x=...)` trên Java17” | AutoCloseable cho SQLXML chỉ có trong đời JDK mới | Dùng `free()` trong finally trên Java17 |
| “SQLType/JDBCType ra đời cùng Java6” | JDBC4.2/Java8 | Ghi đúng API timeline |
| “Cứ bắt SQLException rồi retry” | Có thể double write hoặc gây sai transaction | Phân loại lỗi, xác định idempotency, retry có kiểm soát |
| “Gắn password trực tiếp vào URL để debug” | Dễ lộ trong log/lịch sử/sự kiện | Dùng secrets/config an toàn, không log credentials |

## 13. Kiểm thử driver hiện đại: contract tests và integration tests

**Contract tests** của fake driver hữu ích để hiểu các interface và driver discovery. Nhưng chúng **không kiểm tra** giao thức SQL, query thực, TLS, isolation, pool hay semantics vendor.

### 13.1. Các tầng test

| Tầng | Test gì? | Cần DB thật? |
| --- | --- | --- |
| Compile/source compatibility | `javac --release 17` cho code JDBC | Không |
| JDBC SPI/unit demo | Service discovery, registration, URL routing, mock isValid/wrapper, close | Không |
| Repository unit test với abstraction | SQL string, parameter binding, mapping qua mock | Không, nhưng fake behavior không phải vendor |
| Integration DB | Mở connection, SQL thật, transactions, constraints, timeouts, SQLXML/NClob/RowId | **Có** |
| Pool/infrastructure integration | Acquire/release, validation, reset state, timeout, health checks | Thường có DB hoặc test environment tương đương |
| End-to-end security | TLS/certificates, credentials, least privilege, SQL injection defenses, failure handling | Có môi trường đích |

### 13.2. Những test thực tế nên chạy với database/driver vendor

1. **Driver JAR discovery:** mở connection không phải gọi `Class.forName`.
2. **URL routing:** URL đúng nhận driver, URL sai không nhận.
3. **Network/auth failures:** DNS/refused connection/incorrect password → SQLException thích hợp, không leak credentials.
4. **Connection validation:** `isValid(timeout)` khi mở, sau đóng, khi server ngừng/mất mạng, trong phạm vi timeout chấp nhận.
5. **PreparedStatement:** bind string với ký tự đặc biệt, SQL injection payload như text, SQL NULL, Unicode, binary.
6. **ResultSet:** đọc column name, index, SQL NULL và `wasNull` cho primitive getter khi cần.
7. **Transactions:** commit thành công, rollback sau lỗi, isolation, lost connection during commit, handling idempotency.
8. **Pool:** mượn/trả logical connection, trạng thái autoCommit/isolation được reset, leak detection, max size và acquisition timeout.
9. **Advanced types:** `createSQLXML`, `getRowId`, `setNString` trên schema thực; feature không hỗ trợ phải được phát hiện.
10. **Wrapper:** `unwrap` đúng vendor class nếu cần, không phá lifecycle pool.
11. **Metadata:** query `getJDBCMajorVersion`, transaction support, identifier quoting; xác nhận feature thực dùng được.
12. **Parallelism:** concurrency dưới load, statement/resource leak, slow queries.
13. **Version upgrades:** driver mới hơn tương thích JDK, DB server và connection pool đang dùng.
14. **Operations:** logs không có passwords, TLS certificate validation bật, secrets được quản lý đúng, query timeout/transaction timeout.

### 13.3. Những điểm cần đo trên production

Giám sát connection pool: số logical connections đang mượn, thời gian chờ, số connection tạo mới, leak detection, số lỗi xác thực và network. Đo query latency và failure rate, phân biệt timeouts với constraint violations. Đừng chỉ kiểm tra “isValid trả true” rồi coi hệ thống JDBC khỏe toàn diện.

## 14. Bài tập thực hành và đáp án

**Câu 1.** Vì sao JDBC 4.0 giúp bỏ `Class.forName(...)` với driver JAR hiện đại?

**Đáp án:** DriverManager sử dụng cơ chế Java service-provider để phát hiện driver implementation; driver tự đăng ký với DriverManager theo hợp đồng. Khi JAR được đóng gói đúng và class loader nhìn thấy, ứng dụng không cần gọi `Class.forName` thủ công.

**Câu 2.** `getConnection` dùng `Driver` hay `DataSource` thì tốt hơn?

**Đáp án:** `DriverManager` vẫn hỗ trợ và phù hợp demo/công cụ nhỏ; Oracle khuyến nghị `DataSource` cho code ứng dụng, vì có thể tách cấu hình, pool và transaction infrastructure. `DataSource` không tự động có pool nếu implementation không hỗ trợ.

**Câu 3.** `try (Connection c = ...)` có phải JDBC 4.0 feature không?

**Đáp án:** Không. AutoCloseable cho JDBC Connection/Statement/ResultSet được bổ sung trong JDBC 4.1/Java 7. Ta dùng nó trong Java17+ vì nó vẫn là cách quản lý tài nguyên đúng hiện nay.

**Câu 4.** `isClosed() == false` có bảo đảm DB server còn sống không?

**Đáp án:** Không. `isValid` kiểm tra tích cực khi driver hỗ trợ đúng contract; vẫn phải xử lý SQLException lúc query vì connection có thể hỏng sau validation.

**Câu 5.** Vì sao `Driver.connect(...)` nên trả `null` nếu không hiểu JDBC URL?

**Đáp án:** DriverManager có thể hỏi nhiều drivers. `null` nghĩa driver này không áp dụng và cho driver khác thử; với URL thuộc driver nhưng kết nối lỗi cần ném SQLException thích hợp.

**Câu 6.** `SQLXML` có dùng try-with-resources như `Connection` trên `--release 17` không?

**Đáp án:** Không. Dùng `SQLXML.free()` trong finally ở Java17. Java26/JDBC4.5 mở rộng AutoCloseable cho một số SQL data interfaces.

**Câu 7.** Có thể thay tên bảng SQL bằng dấu `?` không?

**Đáp án:** Không. Parameter marker dùng cho **giá trị dữ liệu**, không thay identifiers/cú pháp SQL. Với tên bảng/cột động cần allowlist chặt chẽ.

**Câu 8.** `getJDBCMajorVersion() >= 4` có chứng minh driver hỗ trợ RowId trên mọi DB không?

**Đáp án:** Không. Driver/DB có thể không hỗ trợ một type hay method cụ thể. Hãy kiểm tra metadata chuyên biệt, driver docs và integration test trên schema thực.

**Câu 9.** Vì sao fake driver được phép in `transaction-contract=true` nhưng không được coi là đã kiểm thử ACID?

**Đáp án:** Mock chỉ xác nhận các lời gọi `setAutoCommit/commit/rollback` đi qua interface, không kết nối database, không ghi dữ liệu và không chứng minh isolation/durability.

**Câu 10.** Nếu SQLException xảy ra khi commit và client mất response thì có retry ngay thao tác thanh toán không?

**Đáp án:** Không nên retry mù quáng. Trạng thái commit có thể không rõ; phải có cơ chế idempotency, tra cứu trạng thái giao dịch và xử lý theo domain để tránh ghi hai lần.

### Bài tập áp dụng

1. **SPI failure:** bỏ file `META-INF/services/java.sql.Driver` khỏi `out` rồi chạy lại `DriverContractsDemo`, xác nhận lỗi. Sau đó khôi phục và chạy PASS.
2. **Registration contract:** bỏ static initializer của `TrainingDriver`, giữ service file; quan sát vì sao `DriverManager.getDriver` không thấy driver khi class không tự register.
3. **URL handling:** thêm URL `jdbc:training:readonly`, định nghĩa rõ `acceptsURL`/`connect` và thêm test.
4. **Wrapper:** thử `c.unwrap(Runnable.class)` và xác nhận SQLException vì interface không được hỗ trợ.
5. **isValid:** test timeout âm, sau khi đóng, và so sánh với `isClosed`. Giải thích sự khác biệt với database thật.
6. **DataSource:** cấu hình một driver thật/DB test nhỏ từ vendor để chạy `CustomerQueries`, tạo bảng `customers` phù hợp và xác nhận query, update count.
7. **SQLXML/national text:** với DB có type phù hợp, mở rộng integration tests cho `Jdbc40Types` và kiểm tra `SQLFeatureNotSupportedException`.
8. **Transaction:** viết hai updates trong cùng connection, bắt lỗi giữa chừng và chứng minh rollback dùng DB thật; không chỉ dùng fake.
9. **Pooling:** cấu hình một DataSource có pool, kiểm tra rằng `close` trả connection để tái sử dụng, không giữ lại logical connection đã đóng.
10. **Phiên bản:** lấy API package summary Java 26, phân loại 15 phương thức vào JDBC4.0, 4.1, 4.2, 4.3+ và các API cũ hơn.

## 15. Tài liệu chính thức còn áp dụng

- [Oracle Java SE 26 — java.sql package summary](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/package-summary.html): **bảng lịch sử JDBC 4.0–4.5**, giới hạn phiên bản và các thành phần lõi.
- [Oracle Java SE 26 — DriverManager](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/DriverManager.html): service provider discovery, `getConnection`, `registerDriver` và class loader.
- [Oracle Java SE 26 — Driver](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Driver.html): `connect`, `acceptsURL`, driver registration.
- [Oracle Java SE 26 — Connection](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Connection.html): `isValid`, transaction, `createSQLXML`, lifecycle và metadata.
- [Oracle Java SE 26 — Wrapper](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Wrapper.html): `isWrapperFor` và `unwrap`.
- [Oracle Java SE 26 — PreparedStatement](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/PreparedStatement.html): parameter binding, `setNString`, `setSQLXML`.
- [Oracle Java SE 26 — ResultSet](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/ResultSet.html): cursor, getters, `getNString` và `getRowId`.
- [Oracle Java SE 26 — SQLException](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLException.html): SQLState, next exception, error code, cause.
- [Oracle Java SE 26 — SQLXML](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLXML.html): SQL XML data type và lifecycle.
- [Oracle Java SE 26 — javax.sql.DataSource](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/javax/sql/DataSource.html): cách cấp connection được khuyến nghị, pooling/XA implementations.
- [Oracle Java SE 26 — javax.sql package summary](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/javax/sql/package-summary.html): DataSource, pooling, transaction infrastructure.
- [Oracle Java SE 17 — java.sql package summary](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/package-summary.html): đối chiếu API cho `--release 17`.

**Ghi nhớ:** JDBC 4.0 không phải “driver cũ cần được hồi sinh”: những hợp đồng nền tảng của nó **tiếp tục được driver hiện đại sử dụng**. Dùng service provider discovery và driver registration đúng, ưu tiên `DataSource`, bind dữ liệu bằng `PreparedStatement`, quản lý tài nguyên bằng try-with-resources của JDBC 4.1+, kiểm tra `isValid` và feature support đúng mức, xử lý SQLException/transactions an toàn, và test database thật cho hành vi vượt ngoài mock.
