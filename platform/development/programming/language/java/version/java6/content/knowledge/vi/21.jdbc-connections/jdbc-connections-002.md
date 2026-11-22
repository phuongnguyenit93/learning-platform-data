# Tự phát hiện java.sql.Driver bằng cơ chế service provider trong JDBC

Từ **JDBC 4.0 (Java 6)**, ứng dụng Java có thể **tự phát hiện JDBC driver** thông qua cơ chế **Java Service Provider**. Thay vì luôn gọi `Class.forName("tên-class-driver")` để ép nạp class, ứng dụng thông thường chỉ cần có **driver JAR đúng chuẩn trên runtime classpath hoặc module path**, rồi gọi `DriverManager.getConnection(...)` với JDBC URL phù hợp. Khi được khởi tạo, `DriverManager` dùng service-provider loading để tìm các implementation của `java.sql.Driver`.

Đây là kiến thức **vẫn còn áp dụng trong Java 17+ và JDK hiện hành**. Tuy nhiên, tự phát hiện driver **khác** với mở kết nối thành công: ứng dụng vẫn cần driver dependency chính xác, database URL, quyền truy cập, credentials và kết nối mạng/TLS phù hợp.

`java.sql.Driver` là **service type**, một interface. Provider là một class triển khai interface này. Trên classpath, provider được khai báo bằng một file có tên chính xác **`META-INF/services/java.sql.Driver`**. Trên JPMS named module, provider có thể được công bố bằng `provides java.sql.Driver with ...`. `DriverManager` quản lý registry của những drivers được đăng ký và chọn driver hiểu URL khi kết nối.

Bài thuộc chủ đề **JDBC kết nối**, đi sâu vào:

- Cách `DriverManager` khởi tạo, tìm service provider, đăng ký driver và chọn driver cho URL.
- Phân biệt discovery, registration, URL matching và connection.
- Tên chính xác và nội dung của service descriptor.
- Khi nào không cần `Class.forName`, khi nào phải chú ý classloader/module.
- Ví dụ **Java 17+ có thể chạy ngay không cần database**, đã kiểm chứng hai trạng thái **có và không có descriptor**.
- Khắc phục `SQLException: No suitable driver`, những lỗi packaging, fat JAR, plugin, TCCL và dynamic loading.
- Vai trò của `DataSource`/connection pooling và các lưu ý bảo mật/vòng đời driver.

## 1. Kiến trúc tổng quát

| Thành phần | Chức năng |
| --- | --- |
| `java.sql.Driver` | Interface triển khai bởi một JDBC driver. Có `connect(...)` và `acceptsURL(...)`. |
| `java.sql.DriverManager` | Quản lý tập drivers, tìm driver phù hợp URL và gọi driver để mở kết nối. |
| `java.util.ServiceLoader` | Cơ chế nền tảng giúp tìm service provider implementations. |
| `META-INF/services/java.sql.Driver` | Service configuration file dành cho **classpath**. |
| `DriverManager.registerDriver(driver)` | Đăng ký một instance vào registry của DriverManager. |
| `DriverManager.getDriver(url)` | Tìm driver hiểu URL; **không mở kết nối**. |
| `DriverManager.getConnection(url, ...)` | Yêu cầu mở một `Connection` thật nếu driver có thể thực hiện. |
| `javax.sql.DataSource` | Abstraction lấy connection; tài liệu Java khuyến nghị ưu tiên cho ứng dụng production. |

Sơ đồ học tập:

```text
Ứng dụng + driver library
         |
         v
runtime classpath / module path
         |
         v
META-INF/services/java.sql.Driver
hoặc JPMS provides java.sql.Driver with ...
         |
         v
DriverManager lần đầu khởi tạo
         |
         v
ServiceLoader<java.sql.Driver>
         |
         v
Load/instantiate provider
         |
         v
Provider tự đăng ký DriverManager.registerDriver(...)
         |
         v
DriverManager.getDriver("jdbc:demo:memory")
         |
         v
DriverManager.getConnection("jdbc:demo:memory")
         |
         v
Driver.connect(url, properties)
         |
         +-- Không hiểu URL -> null
         +-- Hiểu URL nhưng lỗi -> SQLException
         +-- Thành công -> Connection
```

Sơ đồ này mô tả luồng điển hình, **không phải lời hứa về thứ tự nội bộ của mọi driver vendor**. Cách driver thực thi registration là một phần của implementation; Java API khuyến nghị driver tạo và đăng ký instance của mình khi driver class được nạp.

### 1.1. Ba chuyện riêng biệt

**Discovery:** môi trường runtime tìm ra class provider. Có class `DriverImpl.class` trên classpath chưa chắc đồng nghĩa ServiceLoader sẽ tìm nó. Service descriptor hoặc module declaration phải đúng.

**Registration:** `DriverManager` quản lý các **driver instances đã đăng ký**. Driver implementation thường tự gọi `DriverManager.registerDriver` trong static initializer hoặc theo thiết kế của nó. Application thông thường không cần gọi registration thủ công khi driver JAR được chuẩn bị đúng.

**Connection:** `getConnection` lựa chọn và gọi driver để mở kết nối. Driver có thể đã được discover/registered nhưng trả lỗi do URL, credentials, TLS, server down hoặc network timeout.

Không dùng một kết quả “driver đã phát hiện” làm bằng chứng rằng database hoạt động.

## 2. Vì sao JDBC 4.0 không còn cần ứng dụng gọi Class.forName?

Ở chương trình JDBC hiện đại, thường chỉ cần:

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;

// Mảnh code minh họa trong một method đã được khai báo throws SQLException:
try (Connection c = DriverManager.getConnection(
        "jdbc:vendor:database", user, password)) {
    // Dùng Connection do driver thật tạo ra.
}
```

`"jdbc:vendor:database"` là **placeholder giải thích**, không phải URL kết nối thật. URL vendor-specific cần lấy từ tài liệu driver; `user`/`password` do tầng cấu hình hoặc secret manager cung cấp. Ví dụ **không thể chạy độc lập** nếu chưa có driver và database tương ứng.

Trước cơ chế JDBC SPI, mã có thể chủ động kích hoạt driver bằng:

```java
// Cách nạp class tường minh còn có thể gặp trong code cũ:
Class.forName("vendor.jdbc.Driver");
```

`Class.forName` vẫn là một API Java hợp lệ. Nhưng với driver hỗ trợ JDBC 4.0+ **được đăng ký service đúng**, ứng dụng **không phải biết tên class driver** để tải bằng tay. Nếu bạn thường xuyên phải bổ sung `Class.forName` mới chạy, nên kiểm tra runtime dependency, service descriptor và classloader trước khi coi đó là cách sửa lâu dài.

**Có thể vẫn cần nạp/đăng ký tường minh** trong những môi trường cố tình quản lý driver động, chẳng hạn plugin classloader riêng. Đây không phải quy tắc chung cho mọi ứng dụng.

### 2.1. JDK có DriverManager nhưng không có mọi database driver

Module `java.sql` cung cấp **JDBC API**, không phải gói sẵn mọi driver cho PostgreSQL/MySQL/SQL Server. Driver JAR của vendor hoặc implementation được ứng dụng lựa chọn vẫn phải hiện diện lúc chạy.

Biên dịch thành công một class chỉ import `java.sql.DriverManager` **không chứng minh** runtime có driver database. `DriverManager` chỉ là cơ sở quản lý drivers.

## 3. Hợp đồng của java.sql.Driver

`java.sql.Driver` là interface trong module `java.sql`. Một JDBC driver cần triển khai các method:

| Method | Ý nghĩa |
| --- | --- |
| `connect(String url, Properties info)` | Thử tạo Connection; **trả null** nếu driver không hiểu URL; ném `SQLException` nếu driver hiểu nhưng không kết nối được. |
| `acceptsURL(String url)` | Thể hiện có nhận dạng URL hay không. |
| `getPropertyInfo(String url, Properties info)` | Cung cấp mô tả các thuộc tính kết nối. |
| `getMajorVersion()` / `getMinorVersion()` | Báo phiên bản driver. |
| `jdbcCompliant()` | Chỉ trả true nếu thực sự đáp ứng các yêu cầu JDBC compliance. |
| `getParentLogger()` | Truy cập logger gốc của driver theo API. |

### 3.1. Driver.connect không được “chiếm” mọi URL

Giả sử `DemoDriver` chỉ hỗ trợ `jdbc:demo:`:

```java
// Mảnh code nằm trong một Driver implementation:
@Override
public boolean acceptsURL(String url) {
    return url != null && url.startsWith("jdbc:demo:");
}

@Override
public Connection connect(String url, Properties info) throws SQLException {
    if (!acceptsURL(url)) {
        return null;
    }
    // Tạo Connection thực sự hoặc ném SQLException nếu thất bại.
}
```

Nếu URL của vendor khác, driver cần trả null để DriverManager có thể thử driver tiếp theo. Nếu URL **đúng** nhưng không truy cập được server, hãy ném `SQLException` có thông tin phù hợp, không trả null như thể URL không thuộc mình.

`DriverManager.getDriver(url)` và `getConnection(url)` không giống nhau. Method thứ nhất tìm một driver hiểu URL; method thứ hai có thể mở socket, xác thực credentials, thỏa thuận TLS và khởi tạo tài nguyên DB.

### 3.2. Không đoán định dạng JDBC URL

JDBC URL thường có dạng `jdbc:subprotocol:subname`, nhưng phần đằng sau phụ thuộc vendor. `jdbc:demo:memory` của bài chỉ là **URL giả lập**, không phải engine database trong bộ JDK. Khi thực hành với database thật, hãy dùng URL, options và driver class do vendor chính thức công bố.

## 4. Service descriptor phải có tên đúng tuyệt đối

Với **classpath**, nội dung driver JAR cần có file:

```text
META-INF/services/java.sql.Driver
```

Nếu implementation class là `demo.jdbc.DemoDriver`, nội dung file gồm:

```text
demo.jdbc.DemoDriver
```

**Tên file** là fully qualified name của **service**; **nội dung file** là fully qualified name của **provider implementation**.

Những cách sai phổ biến:

- `META-INF/services/demo.jdbc.DemoDriver`: nhầm service name và provider name.
- `META-INF/services/java.sql.Driver.txt`: thêm extension khiến ServiceLoader không tra đúng tên.
- `META-INF/services/javax.sql.Driver`: package service sai.
- Chỉ để file này ở source tree, không package vào JAR/classpath lúc chạy.
- Ghi nhầm provider class name, class không public/không implement interface hoặc constructor không hợp lệ.
- Đóng gói shaded JAR nhưng ghi đè/mất descriptor khi merge.
- Đặt file metadata trong sai classpath root (ví dụ thêm một cấp thư mục `resources` không mong muốn).

Một service file có thể liệt kê nhiều class providers, mỗi tên một dòng; chú thích bắt đầu bằng `#`. Với Java, file này theo định dạng chuẩn của `ServiceLoader`; nên dùng UTF-8 **không BOM** cho portability.

Lệnh xem danh sách entries của JAR:

```bash
jar tf driver.jar
```

Đây là lệnh kiểm tra một JAR **giả định**. Sau build, bạn cần thấy class provider **và** `META-INF/services/java.sql.Driver`. Nếu có nhiều driver dependencies trong fat JAR, cần cấu hình **merge service descriptors**, không chỉ copy class files.

### 4.1. Điều gì xảy ra khi thiếu descriptor?

Có thể class `DemoDriver.class` hoàn toàn nằm trong runtime classpath nhưng **không ai kích hoạt class initialization**. `ServiceLoader` không có metadata để tìm class; DriverManager không có driver được đăng ký, nên `getDriver("jdbc:demo:...")`/`getConnection` có thể báo `No suitable driver`.

Trong phần thực hành, ta kiểm tra chính xác điều đó bằng **hai runtime classpaths**: một có descriptor, một vẫn có toàn bộ class driver nhưng không có descriptor. App không bao giờ tự gọi `Class.forName`.

## 5. DriverManager tự khám phá và đăng ký ở thời điểm nào?

Tài liệu Java SE 26 của `DriverManager` ghi:

- Việc khởi tạo DriverManager là **lazy**.
- DriverManager khám phá các `java.sql.Driver` service providers bằng `ServiceLoader`.
- Thực thi hiện hành tìm các provider qua **thread context classloader (TCCL)** của thread làm kích hoạt driver initialization.
- Ngoài SPI, system property `jdbc.drivers` vẫn hỗ trợ danh sách driver class names.
- Khi lựa chọn kết nối, DriverManager chỉ xét những drivers **caller có thể truy cập** theo classloader.

Một việc dễ xảy ra trong container: thread A chạm DriverManager lần đầu với TCCL không nhìn thấy plugin X, sau đó plugin X được tải bởi classloader khác. Việc gọi `getConnection` sau đó không bảo đảm DriverManager tự lặp lại toàn bộ khám phá service providers.

### 5.1. Discovery không đồng nghĩa registration

`ServiceLoader` tìm và tạo provider object. `DriverManager` duy trì **registry riêng** với `registerDriver`/`deregisterDriver`. Java API của `Driver` khuyến nghị class driver tự tạo và đăng ký instance khi class được tải.

Ví dụ trong `DemoDriver`:

```java
static {
    try {
        DriverManager.registerDriver(new DemoDriver());
    } catch (SQLException e) {
        throw new ExceptionInInitializerError(e);
    }
}
```

Đoạn trên nằm **bên trong thư viện driver**, không phải ở ứng dụng. App chỉ biết interface `java.sql.Driver` và gọi `DriverManager`.

Mỗi vendor có thể chọn chi tiết implementation khác nhau; điều ứng dụng cần là **driver được đăng ký và có thể truy cập**, không phải biết constructor/static block của driver vendor.

### 5.2. Kiểm tra driver mà caller thực sự nhìn thấy

`DriverManager.getDrivers()` trả `Enumeration<Driver>`; `DriverManager.drivers()` (có từ Java 9) trả `Stream<Driver>`, **chỉ gồm các driver caller có thể truy cập**.

```java
// Mảnh Java 17+ chẩn đoán trong một method:
DriverManager.drivers()
        .forEach(d -> System.out.println(d.getClass().getName()));
```

Không coi danh sách này là “toàn bộ JDBC drivers cài trên máy”. Không coi thứ tự enumeration là thứ tự ưu tiên ổn định cho các driver có URL overlap.

## 6. Demo Java 17+ hoàn chỉnh: auto-discovery có và không có service descriptor

Ví dụ xây **một JDBC driver giả lập** không yêu cầu cài cơ sở dữ liệu, nhằm chứng minh cơ chế SPI bằng API thật. Driver trả `Connection` dưới dạng Java dynamic proxy, hỗ trợ đúng ba thao tác quan sát: `close`, `isClosed`, `toString`. Các method còn lại ném `SQLFeatureNotSupportedException`; driver **không hỗ trợ SQL và không dành cho production**.

Cấu trúc:

```text
jdbc-spi-demo/
  driver-src/demo/jdbc/DemoDriver.java
  app-src/demo/JdbcDiscoveryDemo.java
  build/
    driver/
      demo/jdbc/DemoDriver.class
      demo/jdbc/DemoDriver$1.class
      META-INF/services/java.sql.Driver
    app/demo/JdbcDiscoveryDemo.class
    no-spi/demo/jdbc/DemoDriver.class
    no-spi/demo/jdbc/DemoDriver$1.class
```

Các file bên dưới là code hoàn chỉnh biên dịch với `javac --release 17`.

### 6.1. Driver: `driver-src/demo/jdbc/DemoDriver.java`

```java
package demo.jdbc;

import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Proxy;
import java.sql.Connection;
import java.sql.Driver;
import java.sql.DriverManager;
import java.sql.DriverPropertyInfo;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import java.util.Properties;
import java.util.logging.Logger;

public final class DemoDriver implements Driver {
    static {
        try {
            DriverManager.registerDriver(new DemoDriver());
        } catch (SQLException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public DemoDriver() {}

    @Override
    public boolean acceptsURL(String url) {
        return url != null && url.startsWith("jdbc:demo:");
    }

    @Override
    public Connection connect(String url, Properties properties) throws SQLException {
        if (!acceptsURL(url)) {
            return null;
        }
        InvocationHandler handler = new InvocationHandler() {
            private boolean closed;

            @Override
            public Object invoke(Object proxy, java.lang.reflect.Method method,
                                 Object[] args) throws Throwable {
                return switch (method.getName()) {
                    case "close" -> { closed = true; yield null; }
                    case "isClosed" -> closed;
                    case "toString" -> "MockConnection(" + url + ")";
                    case "isWrapperFor" -> false;
                    default -> throw new SQLFeatureNotSupportedException(
                            "Demo is not a real database: " + method.getName());
                };
            }
        };
        return (Connection) Proxy.newProxyInstance(
                DemoDriver.class.getClassLoader(),
                new Class<?>[] { Connection.class },
                handler);
    }

    @Override
    public DriverPropertyInfo[] getPropertyInfo(String url, Properties info) {
        return new DriverPropertyInfo[0];
    }

    @Override public int getMajorVersion() { return 1; }
    @Override public int getMinorVersion() { return 0; }
    @Override public boolean jdbcCompliant() { return false; }
    @Override public Logger getParentLogger() {
        return Logger.getLogger("demo.jdbc");
    }
}
```

**Phân tích:**

- Class implements `Driver`, có constructor public không tham số để ServiceLoader khởi tạo.
- Static initializer gọi `DriverManager.registerDriver(new DemoDriver())` đúng contract; không cần ứng dụng gọi.
- `acceptsURL` nhận duy nhất URL bắt đầu `jdbc:demo:`.
- `connect` trả null khi URL không thuộc driver; trả mock Connection nếu thuộc.
- `InvocationHandler` chỉ minh họa cách tạo object implementing `Connection`; không có database/transaction/query.
- `getParentLogger` trả Java logger bình thường; `jdbcCompliant` phải false vì driver giả không đáp ứng JDBC compliance.
- Class có nested class anonymous implementation được javac tạo thành `DemoDriver$1.class`; khi test không có descriptor cần copy **cả nested class**, nếu không `connect` sẽ gặp `NoClassDefFoundError`.

**Vì sao có thể có hai DemoDriver objects?** ServiceLoader có thể khởi tạo provider instance, trong khi static initializer tạo một instance khác để đăng ký với DriverManager. Trong demo, điều quan trọng là registry chỉ có **một driver được đăng ký** qua static block; các chi tiết instance là quyết định của implementation.

### 6.2. App: `app-src/demo/JdbcDiscoveryDemo.java`

```java
package demo;

import java.sql.Connection;
import java.sql.Driver;
import java.sql.DriverManager;
import java.sql.SQLException;

public final class JdbcDiscoveryDemo {
    public static void main(String[] args) throws SQLException {
        long registered = DriverManager.drivers()
                .filter(d -> d.getClass().getName().equals("demo.jdbc.DemoDriver"))
                .count();
        System.out.println("registered=" + registered);

        try {
            Driver selected = DriverManager.getDriver("jdbc:demo:memory");
            System.out.println("selected=" + selected.getClass().getName());

            Connection c = DriverManager.getConnection("jdbc:demo:memory");
            try (c) {
                System.out.println("connection=" + c);
                System.out.println("closed.inTry=" + c.isClosed());
            }
            System.out.println("closed.afterTry=" + c.isClosed());
        } catch (SQLException ex) {
            System.out.println("sqlState=" + ex.getSQLState());
            System.out.println("message=" + ex.getMessage());
        }
    }
}
```

Ứng dụng **không import DemoDriver**, không gọi `Class.forName` hoặc `registerDriver`. Nó chỉ gọi JDBC API.

- `DriverManager.drivers()` là bước chẩn đoán và đếm đúng class name để không phụ thuộc các driver khác trong JVM.
- `getDriver` tìm driver hiểu `jdbc:demo:memory` mà không tạo connection.
- `getConnection` gọi driver và nhận proxy.
- `try (c)` là try-with-resources hợp lệ trên Java 17, đóng connection sau block.
- Nếu discovery không có, `getDriver` ném SQLException, app báo SQLState/message.

### 6.3. Service descriptor

Tệp:

```text
build/driver/META-INF/services/java.sql.Driver
```

Nội dung:

```text
demo.jdbc.DemoDriver
```

Đặt đúng nơi ứng với **classpath root `build/driver`**, không đặt vào `build/app` trừ khi muốn service metadata thuộc app artifact. Ứng dụng không được trực tiếp tạo DemoDriver.

### 6.4. Chạy trên Bash (Linux/macOS)

```bash
mkdir -p build/driver/META-INF/services build/app build/no-spi/demo/jdbc

javac --release 17 -encoding UTF-8 -d build/driver \
  driver-src/demo/jdbc/DemoDriver.java

javac --release 17 -encoding UTF-8 -d build/app \
  app-src/demo/JdbcDiscoveryDemo.java

printf 'demo.jdbc.DemoDriver\n' \
  > build/driver/META-INF/services/java.sql.Driver

# Case A: có service descriptor.
java -cp "build/driver:build/app" demo.JdbcDiscoveryDemo

# Case B: vẫn giữ toàn bộ class, nhưng không copy descriptor.
cp build/driver/demo/jdbc/DemoDriver*.class build/no-spi/demo/jdbc/
java -cp "build/no-spi:build/app" demo.JdbcDiscoveryDemo
```

Dấu phân cách classpath trên Linux/macOS là `:`. Những lệnh này không cần database thật, cũng không cần Maven/Gradle hoặc driver vendor bên ngoài.

### 6.5. Chạy trên PowerShell (Windows)

```powershell
New-Item -ItemType Directory -Force build/driver,build/app,build/no-spi/demo/jdbc,build/driver/META-INF/services | Out-Null

javac --release 17 -encoding UTF-8 -d build/driver driver-src/demo/jdbc/DemoDriver.java
javac --release 17 -encoding UTF-8 -d build/app app-src/demo/JdbcDiscoveryDemo.java

$utf8 = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText("build/driver/META-INF/services/java.sql.Driver", "demo.jdbc.DemoDriver" + [Environment]::NewLine, $utf8)

java -cp 'build/driver;build/app' demo.JdbcDiscoveryDemo

Copy-Item build/driver/demo/jdbc/DemoDriver*.class -Destination build/no-spi/demo/jdbc/
java -cp 'build/no-spi;build/app' demo.JdbcDiscoveryDemo
```

Windows phân tách classpath bằng `;`. `UTF8Encoding($false)` tạo service configuration file không có BOM. Trong Windows PowerShell 5.1, tránh dùng một chuỗi ghi file UTF-8 có BOM khiến tên provider bị thêm ký tự ẩn ở đầu.

### 6.6. Stdout kiểm chứng thực tế trên JDK 24

**Case A — có descriptor và class driver:**

```text
registered=1
selected=demo.jdbc.DemoDriver
connection=MockConnection(jdbc:demo:memory)
closed.inTry=false
closed.afterTry=true
```

**Case B — class driver vẫn có nhưng không có descriptor:**

```text
registered=0
sqlState=08001
message=No suitable driver
```

Đã chạy hai Java processes tách biệt sau khi biên dịch `--release 17`; những dòng trên là **stdout thực tế** của bản thử nghiệm JDK 24. Cụm `No suitable driver`/SQLState `08001` được kiểm chứng trên runtime đó; đừng dựa vào exact English message thay cho error category của mọi driver/JDK.

**Bài học từ Case B:** nếu chỉ sao chép class file mà mất `META-INF/services/java.sql.Driver`, ServiceLoader không biết provider để tự khám phá. Ứng dụng không gọi tên class driver bằng tay, vì vậy registry vẫn trống trong test. Điều này chứng minh lý do descriptor quan trọng.

**Giới hạn:** Connection trong Case A chỉ là proxy, không xử lý SQL. `createStatement`, transactions, metadata và những method khác chưa hỗ trợ sẽ ném `SQLFeatureNotSupportedException`. Không sử dụng driver này trong ứng dụng sản xuất.

## 7. Chẩn đoán “No suitable driver” theo đúng nguyên nhân

Khi thấy lỗi:

```text
java.sql.SQLException: No suitable driver
```

hãy phân loại:

| Nhóm | Dấu hiệu | Cách kiểm tra |
| --- | --- | --- |
| **JAR thiếu** | App compile được nhưng runtime không có vendor driver. | In runtime classpath/module path, kiểm tra dependency scopes và artifact. |
| **Service descriptor thiếu/sai** | Class driver có mặt nhưng không được đăng ký tự động. | Mở JAR, xem `META-INF/services/java.sql.Driver` và nội dung. |
| **URL sai** | Driver đã đăng ký nhưng không driver nào nhận URL. | Đối chiếu vendor URL, thử `DriverManager.getDriver(url)`. |
| **Classloader visibility** | Plugin/app server gọi DriverManager từ classloader khác. | Kiểm tra TCCL của thread init, caller loader và driver class identity. |
| **JPMS module** | Provider module không resolve hoặc thiếu `provides`. | Xem module graph và module descriptor. |
| **Class initialization lỗi** | ServiceLoader tìm provider nhưng nó không khởi tạo được. | Kiểm tra transitive dependencies, `ServiceConfigurationError`/initializer failure. |
| **Packaging fat JAR** | Khi merge nhiều JAR, service descriptors bị ghi đè. | Cấu hình service descriptor merger, xem output artifact cuối cùng. |
| **Dynamic loading muộn** | JAR nạp sau khi DriverManager đã initialized. | Thiết kế registration/lifecycle rõ, không chờ auto-rescan. |
| **Database/network/auth lỗi** | Driver đã chọn, nhưng connect thất bại. | Đọc SQLException, SQLState, vendor code/cause, kiểm tra server/TLS/credentials. |

**Phân biệt:** một `No suitable driver` không đồng nghĩa database down. Nếu `getDriver(url)` trả driver nhưng `getConnection(url)` báo lỗi, nhiều khả năng lỗi đã đi qua giai đoạn discovery. Đừng biến mọi SQLException thành “thiếu driver”.

### Mẫu diagnostics tối thiểu

```java
// Mảnh code trong ứng dụng, có import java.sql.DriverManager:
DriverManager.drivers().forEach(driver ->
        System.out.println("driver=" + driver.getClass().getName()));
```

Không dùng log danh sách drivers để suy ra kết nối thành công: `DriverManager.drivers` chỉ hiển thị những driver **caller có quyền truy cập**.

Với `SQLException`, có thể dùng `getSQLState()`, `getErrorCode()`, `getCause()`, `getNextException()` cùng logging framework phù hợp. Tránh in password, token hoặc JDBC URL chứa credentials vào log.

## 8. TCCL, classloader isolation và plugin systems

Theo implementation note của `DriverManager` hiện hành, service-provider loading trong lần khởi tạo đầu dùng **thread context classloader**. Ở server/plugin host, mỗi webapp hoặc plugin có thể có classloader riêng; vì vậy driver hiện diện ở plugin A không đồng nghĩa plugin B có thể dùng.

```java
// Mảnh chẩn đoán môi trường:
ClassLoader loader = Thread.currentThread().getContextClassLoader();
System.out.println("TCCL=" + loader);
```

Các hệ quả:

- DriverManager có thể đã khởi tạo từ một thread không nhìn thấy driver JAR muốn thêm.
- Một driver có thể được đăng ký nhưng **caller khác không có classloader visibility phù hợp** nên `getDriver/getConnection/getDrivers` không dùng hoặc không hiện nó.
- Class cùng tên nhưng nạp bởi hai classloaders khác nhau không có cùng class identity.
- Tự thay đổi TCCL trong thread pool có thể ảnh hưởng hàng loạt SPI khác; chỉ thay có chủ đích và khôi phục trong `finally`.

Việc `ServiceLoader.reload()` trên một instance `ServiceLoader` do ứng dụng tạo **không phải cách ra lệnh DriverManager khám phá lại registry**. DriverManager đã quản lý state riêng và có cơ chế đăng ký riêng.

### Hot-loading cần lifecycle riêng

Với hệ thống cố ý thêm driver trong lúc chạy:

1. Quản lý thời điểm tạo classloader/module layer.
2. Đăng ký instance driver trong phạm vi có thể truy cập bằng `DriverManager.registerDriver` khi phù hợp.
3. Đảm bảo caller dùng đúng classloader/driver.
4. Quản lý connections, pools, thread resources và cleanup khi plugin dừng.
5. Nếu driver được deregister, các connections cũ **không chắc tự đóng** (tùy implementation).
6. Tránh giữ classloader plugin lâu dài qua static registry/reference.

Không tự động deregister mọi driver của JVM từ một plugin không sở hữu chúng.

## 9. JPMS: named module cung cấp java.sql.Driver

Với classpath driver JAR, `META-INF/services` là registration tiêu chuẩn. Trong ứng dụng **JPMS named modules**, provider module thường dùng `provides`:

```java
// module-info.java của driver module, mảnh minh họa:
module demo.jdbc.driver {
    requires java.sql;
    provides java.sql.Driver with demo.jdbc.DemoDriver;
}
```

- `requires java.sql` vì service interface nằm trong module `java.sql`.
- `provides ... with ...` công bố implementation cho module-aware ServiceLoader.
- Provider module cần **được resolve** và có implementation hợp lệ; chỉ đặt file JAR vào một thư mục chưa đủ.
- Module chuẩn `java.sql` có `uses java.sql.Driver` theo Java SE 26 module descriptor; ứng dụng gọi `DriverManager` bình thường không cần tự triển khai `ServiceLoader`.
- Nếu **ứng dụng named module** tự gọi `ServiceLoader.load(Driver.class)`, nó phải đáp ứng yêu cầu `uses java.sql.Driver` của `ServiceLoader` trong chính module tương ứng.
- Không nhầm tệp `META-INF/services` dành cho classpath với directive `provides` cho named module.

Đoạn descriptor trên **không phải dự án modular hoàn chỉnh**. Demo mục 6 được xác minh theo classpath, không tuyên bố đã kiểm thử riêng module mode.

Trong JDK 9+ (bao gồm 17+), service discovery ở module path còn phụ thuộc module resolution/layers. Xem build tool và tài liệu driver vendor để triển khai đúng hệ thống của bạn.

## 10. DriverManager, DataSource và connection pooling

`DriverManager.getConnection` là một factory kết nối cấp thấp tiện cho ví dụ và chương trình đơn giản. Nó **không cung cấp pooling**.

Tài liệu Java hiện hành của `DriverManager` nói rõ **`javax.sql.DataSource` là cách được ưu tiên hơn** để lấy database connections trong ứng dụng.

```java
import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

// Mảnh code trong service, dataSource đã được cấu hình/inject:
try (Connection c = dataSource.getConnection()) {
    // Thao tác JDBC nghiệp vụ.
}
```

Những lợi ích có thể đạt được:

- Tách JDBC URL, driver credentials và thiết lập TLS khỏi business code.
- Dependency injection và testability tốt hơn.
- Pooling, metrics, resource limits/timeout nếu **DataSource implementation có hỗ trợ**.
- Thay nguồn dữ liệu mà không gắn tên driver class vào code nghiệp vụ.
- Quản lý lifecycle của pool khi ứng dụng dừng.

**DataSource không tự động bảo đảm pooling**: cần dùng implementation/pool phù hợp và cấu hình đúng. Dù dùng DataSource hay DriverManager, database driver/implementation vẫn phải có trong runtime.

## 11. Vấn đề bảo mật khi auto-load bên thứ ba

Driver SPI có thể **thực thi code trong JVM tại thời điểm discovery/initialization**. Vì vậy cơ chế service provider là cơ chế mở rộng **đáng tin cậy**, không phải sandbox cho mã không rõ nguồn gốc.

- Chỉ sử dụng JDBC driver dependencies từ nguồn được tổ chức chấp thuận, có quản lý versions và vulnerability scanning.
- Không tải và chạy JAR JDBC không tin cậy chỉ vì file descriptor của nó đúng cú pháp.
- Dùng JDBC URL/credentials theo vendor và chính sách bảo mật; không lưu password trong source hoặc lệnh CLI.
- Kiểm tra TLS/certificate/hostname verification theo driver vendor; SPI auto-discovery **không tự thiết lập TLS an toàn**.
- Không in toàn bộ `Properties` chứa username/password hoặc token vào log.
- Tránh đặt password trong URL nếu có kênh secrets riêng; URL dễ bị log/telemetry thu thập.
- Dùng `PreparedStatement` với SQL thực để phòng SQL injection; việc tự tìm driver không thay thế parameter binding.
- Đóng `Connection`, `Statement` và `ResultSet` theo lifecycle/try-with-resources.
- Không dùng mock driver trong bài làm bằng chứng rằng đã test database, network hoặc transactions.

## 12. Vòng đời registration và deregistration

`DriverManager` duy trì registry static trong JVM. API:

```java
// Mảnh API minh họa, không phải chương trình độc lập:
DriverManager.registerDriver(driver);
DriverManager.registerDriver(driver, action);
DriverManager.deregisterDriver(driver);
```

`DriverAction` là callback tùy chọn để driver được thông báo khi deregister. Đây là khả năng còn áp dụng, không phải bắt buộc với ứng dụng CRUD thông thường.

Trong app server/plugin, classloader leak có thể xảy ra nếu một registry giữ driver của classloader đã không còn sống. Quản lý deregistration hợp lý khi unload là cần thiết, nhưng **không gọi `deregisterDriver` sau mỗi connection**. Kết nối đang mở không tự động bị đóng theo contract chỉ vì driver deregister; cách xử lý connections phụ thuộc driver.

Ứng dụng dùng DataSource/pool vẫn phải đóng pool/threads/timers theo lifecycle. Đừng kỳ vọng DriverManager deregister thay thế toàn bộ việc giải phóng tài nguyên.

## 13. Các lỗi phổ biến

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “JDK có java.sql nên tự có PostgreSQL/MySQL driver.” | API khác driver implementation. | Thêm JDBC driver dependency đúng vào runtime. |
| “Class file có sẵn thì tự động discover.” | ServiceLoader phải biết provider thông qua descriptor/module metadata. | Giữ `META-INF/services/java.sql.Driver` hoặc `provides`. |
| “Phải gọi Class.forName ở mọi kết nối.” | JDBC 4.0+ hỗ trợ SPI auto-discovery. | Sửa package/loader/URL thay vì bắt buộc legacy workaround. |
| “Có descriptor tức là DB kết nối thành công.” | Discovery không kiểm chứng server/credentials/TLS. | Xử lý `getConnection` và SQLException riêng. |
| “No suitable driver chỉ do thiếu JAR.” | Có thể do URL hoặc classloader. | Kiểm tra registry, URL, module path và TCCL. |
| “Driver.connect phải ném lỗi khi gặp URL của driver khác.” | Contract yêu cầu trả null nếu URL không thuộc driver. | Kiểm tra `acceptsURL` trước khi connect. |
| “Đã nhận URL nhưng DB down thì trả null.” | Trường hợp lỗi khi kết nối thực phải báo SQLException. | Propagate nguyên nhân kết nối đúng. |
| “DriverManager.drivers() là tất cả drivers của JVM.” | Chỉ gồm drivers caller có thể truy cập. | Kiểm tra classloader/caller. |
| “Copy class vào fat JAR là đủ.” | Service descriptor có thể bị mất khi shading. | Merge descriptor, kiểm tra final artifact. |
| “Đổi classpath sau init sẽ tự scan lại.” | Khởi tạo SPI là lazy và không hứa tự rescan. | Dynamic registration/lifecycle riêng. |
| “Module path giống classpath.” | Named modules dùng `provides` và resolution. | Thiết lập JPMS đúng. |
| “DriverManager có connection pool.” | DriverManager chỉ chọn và mở connection. | Dùng DataSource/pool implementation khi cần. |
| “Deregister driver sẽ đóng mọi connections.” | Active-connection behavior phụ thuộc implementation. | Đóng connection/pool theo lifecycle. |
| “Chỉ chạy ServiceLoader.load để kiểm tra DriverManager.” | ServiceLoader discovery và DriverManager registry không hoàn toàn đồng nhất. | Test `getDriver`/`drivers()` từ caller thực tế. |
| “Log nguyên URL và connection Properties an toàn.” | Có thể chứa credentials. | Redact logs, quản lý secrets. |

## 14. Checklist QA cho ứng dụng JDBC thật

- [ ] Driver JAR phù hợp JDK và phiên bản database?
- [ ] Dependency có ở **runtime**, không chỉ compile/test?
- [ ] Provider class triển khai `java.sql.Driver` và có thể khởi tạo?
- [ ] Classpath descriptor đúng `META-INF/services/java.sql.Driver`? Nếu module path, có `provides` đúng?
- [ ] Final JAR/fat JAR còn nguyên metadata và class names sau relocation?
- [ ] `DriverManager.getDriver(url)` tìm driver cho đúng vendor JDBC URL?
- [ ] TCCL và caller classloader có thể nhìn thấy provider?
- [ ] Database thực sự reachable, TLS/credentials đúng theo vendor?
- [ ] `getConnection` báo lỗi có SQLState/cause hữu ích nhưng không rò secret?
- [ ] Connection được đóng bằng try-with-resources hoặc pool lifecycle?
- [ ] Production đã cân nhắc `DataSource`/pool và giới hạn tài nguyên?
- [ ] Hot-load/unload có registration/deregistration và classloader cleanup?
- [ ] Tests có hai tình huống: **có metadata** và **chỉ có class mà không có metadata**?
- [ ] Không dùng “driver đã được discover” thay cho test tích hợp database?

## 15. Bài tập thực hành

**A — Xóa descriptor.** Giữ nguyên mọi `DemoDriver*.class` trên classpath nhưng bỏ `META-INF/services/java.sql.Driver`. Chạy lại app và giải thích `registered=0`; vì sao đây là phép thử chính xác hơn việc xóa hẳn driver JAR?

**B — URL không khớp.** Sửa URL `jdbc:demo:memory` thành `jdbc:other:memory`. Dự đoán lỗi ở `getDriver` và giải thích tại sao `connect` của DemoDriver phải trả null cho URL đó.

**C — Class.forName và cơ chế cũ.** Trong **một test riêng**, ở chế độ không có descriptor, thử nạp `demo.jdbc.DemoDriver` bằng `Class.forName` trước khi gọi `DriverManager.drivers()`. Static initializer đã làm gì? Tại sao đây không phải cách phải thêm mặc định vào mọi app JDBC 4.0+?

**D — Đóng gói JAR.** Dùng `jar` tạo artifact từ `build/driver`, xem `jar tf`, rồi đặt JAR trong classpath. Đổi metadata và kiểm tra output.

**E — ServiceLoader và registry.** Thử `ServiceLoader.load(Driver.class)` trong một chương trình test phù hợp, so với `DriverManager.drivers()`. Phân biệt provider discovery và các instances đã được đăng ký.

**F — Named module.** Tạo module descriptor `provides java.sql.Driver with demo.jdbc.DemoDriver`, chạy với module path được resolve đúng và so với classpath variant.

**G — DataSource.** Với một driver thật, thay service code sử dụng `DriverManager.getConnection` bằng `DataSource.getConnection`, inject DataSource và thử implementation có pool. Không dùng mock Connection để đo hiệu năng DB.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** JDBC 4.0 còn yêu cầu app tự `Class.forName` mọi driver?

**Đáp án:** Không. Driver JAR đúng chuẩn SPI được DriverManager tự khám phá khi khởi tạo; application có thể gọi thẳng `getConnection`.

**Câu 2.** Tên service descriptor trên classpath là gì?

**Đáp án:** `META-INF/services/java.sql.Driver`. Nội dung ghi fully qualified implementation class name.

**Câu 3.** Class driver tồn tại trong JAR mà thiếu descriptor có được tự phát hiện không?

**Đáp án:** Không được bảo đảm. Khi app không có cơ chế tải/đăng ký tường minh khác, ServiceLoader không tìm provider đó qua service file; demo cho `registered=0`.

**Câu 4.** DriverManager có phải khám phá lại SPI sau mỗi `getConnection` không?

**Đáp án:** Không. DriverManager khởi tạo lazy và có registry riêng. Plugin hot-load cần quản lý discovery/registration.

**Câu 5.** `getDriver(url)` có gọi database không?

**Đáp án:** Không, nó xác định driver hiểu URL. `getConnection` mới thử tạo Connection.

**Câu 6.** Driver có nên trả null khi đã nhận URL nhưng server không truy cập được?

**Đáp án:** Không. Khi URL thuộc driver mà kết nối thất bại, báo SQLException; null dành cho URL không thuộc driver đó.

**Câu 7.** Vì sao hai callers cùng JVM có thể nhìn thấy danh sách drivers khác nhau?

**Đáp án:** `DriverManager` áp dụng classloader visibility và caller access. TCCL ở thời điểm init cũng ảnh hưởng discovery.

**Câu 8.** Dùng `DataSource` có luôn tự có connection pool không?

**Đáp án:** Không. DataSource là abstraction tạo connection; pooling cần implementation/cấu hình phù hợp.

**Câu 9.** Khi driver được deregister, Connection đang mở có chắc bị đóng?

**Đáp án:** Không. Tác động đến active connections là implementation-specific; cần quản lý connection/pool lifecycle riêng.

## 17. Tài liệu chính thức vẫn còn áp dụng

- [DriverManager — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/DriverManager.html): auto-discovery, lazy init, TCCL, `jdbc.drivers`, registry, connection APIs.
- [Driver — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Driver.html): contract `connect`/`acceptsURL`, registration advice.
- [java.sql package summary — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/package-summary.html): JDBC 4.0 auto driver discovery.
- [java.sql module — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/module-summary.html): JDBC module và `uses java.sql.Driver`.
- [ServiceLoader — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html): service descriptors, provider discovery, JPMS `provides`.
- [Connection — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Connection.html): connection lifecycle, `AutoCloseable`.
- [SQLException — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLException.html): SQLState, vendor error code và cause.
- [DataSource — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/javax/sql/DataSource.html): ưu tiên DataSource để quản lý nguồn kết nối.

**Ghi nhớ:** Tự phát hiện driver = **service metadata hoặc module `provides` + implementation có thể nạp + đăng ký với DriverManager + caller nhìn thấy driver**. Sau đó `DriverManager` chọn driver hiểu JDBC URL; mở kết nối vẫn có thể thất bại do database, credentials hoặc mạng. Không bắt buộc `Class.forName` cho JDBC 4.0+ driver được đóng gói chuẩn; với ứng dụng hiện đại nên quản lý dependency, security, classloader và cân nhắc `DataSource`/pool.
