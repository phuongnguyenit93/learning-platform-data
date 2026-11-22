# Các module chuẩn của JDK: java.logging, java.sql và những module thường dùng

## 1. Module chuẩn của Java là gì?

Kể từ Java 9, Java Platform Module System (JPMS) tổ chức nhiều API của nền tảng Java thành **các module có tên**. Mỗi module khai báo những package mà nó cung cấp, những module nó cần đọc và các package được export hoặc open. Các module của nền tảng nằm trong **runtime image** của JDK/JRE được sử dụng.

Khi học Java Core, nên phân biệt ba nhóm:

- **Module chuẩn Java SE**, thường có tên **java.***: ví dụ **java.base**, **java.logging**, **java.sql**, **java.xml**, **java.desktop**, **java.net.http**. Chúng chứa các API thuộc nền tảng Java SE tương ứng với phiên bản Java đang dùng.
- **Module riêng của JDK**, thường có tên **jdk.***: ví dụ **jdk.jfr**, **jdk.management**, **jdk.compiler**, **jdk.httpserver**. Chúng cung cấp các công cụ và API của bản phân phối JDK, không nên mặc định coi tất cả là API Java SE.
- **Module của ứng dụng hoặc thư viện bên thứ ba**: ví dụ **com.example.app** và driver JDBC do nhà cung cấp cơ sở dữ liệu phân phối.

Một module của ứng dụng được mô tả bằng **module-info.java**. Trong code thuộc **named module**, để dùng public API được export bởi module khác, thông thường phải khai báo **requires** tương ứng. **java.base** là ngoại lệ đặc biệt: mọi module đều đọc java.base mà không cần khai báo.

Ví dụ:

~~~java
module com.example.app {
    requires java.logging;
    requires java.sql;
    requires java.xml;
    requires java.net.http;
}
~~~

Các khai báo trên hình thành những phụ thuộc ở **mức module**. Chúng không tải toàn bộ class của các module vào bộ nhớ ngay lập tức. Khi chương trình tham chiếu một class cụ thể, quá trình class loading vẫn diễn ra theo nhu cầu.

## 2. Bảng tra cứu nhanh các module Java SE thường gặp

| Module | API/package điển hình | Công dụng chính | Ghi chú thực tế |
|---|---|---|---|
| **java.base** | java.lang, java.util, java.io, java.nio, java.time, java.util.concurrent | Nền tảng ngôn ngữ, collection, I/O, thời gian, concurrency | Tự được yêu cầu bởi mọi module |
| **java.logging** | java.util.logging | Logging qua JUL | Dùng Logger, Level, Handler, Formatter |
| **java.sql** | java.sql, javax.sql | API JDBC, truy cập CSDL quan hệ | Chỉ có API; cần JDBC driver phù hợp để kết nối |
| **java.sql.rowset** | javax.sql.rowset | Các RowSet, hỗ trợ JDBC ở dạng thuận tiện | Dùng khi cần những RowSet API |
| **java.xml** | javax.xml.parsers, org.w3c.dom, org.xml.sax, javax.xml.transform | Parse, tạo, xử lý XML | DOM, SAX, Transformer và các API XML liên quan |
| **java.xml.crypto** | javax.xml.crypto | XML Digital Signature | Không đồng nghĩa với mọi API mật mã của Java |
| **java.net.http** | java.net.http | HTTP Client hiện đại | API ổn định từ Java 11 |
| **java.desktop** | java.awt, javax.swing, javax.imageio, java.beans | GUI AWT/Swing, hình ảnh, desktop APIs | Không phải mọi ứng dụng server đều cần |
| **java.management** | java.lang.management, javax.management | Giám sát JVM, JMX, MXBean | Hữu ích cho quản trị và observability |
| **java.naming** | javax.naming | JNDI và dịch vụ tra cứu/tên | Cần khi tích hợp các hệ thống dùng JNDI |
| **java.prefs** | java.util.prefs | Lưu lựa chọn/cấu hình dạng Preferences | Khác hệ thống config của framework |
| **java.scripting** | javax.script | ScriptEngine API | Có API không có nghĩa runtime có sẵn engine JavaScript |
| **java.compiler** | javax.tools, javax.lang.model | API trình biên dịch và mô hình ngôn ngữ | Không đồng nghĩa với module triển khai javac |
| **java.instrument** | java.lang.instrument | Java agents và instrumentation | Thường dùng với -javaagent |
| **java.rmi** | java.rmi | Remote Method Invocation | Phù hợp khi dùng RMI |
| **java.security.jgss** | org.ietf.jgss, javax.security.auth.kerberos | GSS-API, Kerberos | Các giao thức và cơ chế xác thực liên quan |
| **java.transaction.xa** | javax.transaction.xa | Giao diện XA cho giao dịch phân tán | Chỉ là API XA; không cung cấp đầy đủ transaction manager |
| **java.se** | Không phải module chứa tất cả package riêng | Module tổng hợp cho tập API Java SE | Dùng các quan hệ requires transitive để gom nhiều module SE |

Tên và sự hiện diện của module phải xét theo **phiên bản Java và runtime image** thực tế. Một image được tạo bằng **jlink** có thể chỉ chứa các module được lựa chọn. Không nên khẳng định mọi runtime đều có mọi module chỉ dựa vào danh sách module của một JDK đầy đủ.

## 3. java.logging: API logging tích hợp sẵn

Module **java.logging** cung cấp **java.util.logging** (JUL). Đây là API logging đi kèm nền tảng Java, không cần thêm dependency ngoài cho việc ghi log cơ bản.

Khai báo:

~~~java
module com.example.app {
    requires java.logging;
}
~~~

Ví dụ:

~~~java
package com.example.app;

import java.util.logging.Level;
import java.util.logging.Logger;

public class LoggingExample {
    private static final Logger LOG =
            Logger.getLogger(LoggingExample.class.getName());

    public static void main(String[] args) {
        LOG.info("Ứng dụng khởi động");
        LOG.log(Level.WARNING, "Giá trị không hợp lệ: {0}", -1);

        try {
            Integer.parseInt("abc");
        } catch (NumberFormatException ex) {
            LOG.log(Level.SEVERE, "Không phân tích được số", ex);
        }
    }
}
~~~

Những thành phần chính:

- **Logger**: tên logger và nơi phát sinh bản ghi.
- **Level**: mức độ như SEVERE, WARNING, INFO, CONFIG, FINE, FINER, FINEST.
- **Handler**: đích nhận bản ghi, ví dụ ConsoleHandler hoặc FileHandler.
- **Formatter**: quy tắc định dạng thông báo.
- **LogManager**: quản lý cấu hình hệ thống JUL.
- **Filter**: cho phép lọc LogRecord theo điều kiện.

Có thể truyền đường dẫn file cấu hình JUL qua system property:

~~~sh
java -Djava.util.logging.config.file=logging.properties --module-path mods -m com.example.app/com.example.app.LoggingExample
~~~

Ví dụ nội dung **logging.properties**:

~~~properties
handlers=java.util.logging.ConsoleHandler
.level=INFO
java.util.logging.ConsoleHandler.level=INFO
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
~~~

**Lưu ý:** JUL là một lựa chọn logging tích hợp. SLF4J là facade logging bên thứ ba, còn Logback và Log4j 2 là các giải pháp khác có dependency riêng. Không thể thay **requires java.logging** bằng tên module của một framework nếu ứng dụng vẫn import **java.util.logging**.

Trong các ứng dụng lớn, có thể tồn tại nhiều logging backend. Khi phân tích log, cần xác định rõ code đang dùng JUL trực tiếp hay qua bridge/adaptor.

## 4. java.sql: API JDBC, không phải database driver

Module **java.sql** chứa Java Database Connectivity (JDBC): những interface và class giúp Java làm việc với CSDL quan hệ. Các API thường dùng:

- **Connection**: phiên kết nối với CSDL.
- **DriverManager**: quản lý và chọn JDBC driver phù hợp với URL.
- **DataSource** (thuộc **javax.sql**): cách lấy connection thường được ưu tiên trong ứng dụng có connection pool.
- **PreparedStatement**: gửi SQL có tham số; phù hợp để truyền giá trị đầu vào.
- **ResultSet**: duyệt kết quả của truy vấn.
- **SQLException**: thông tin lỗi JDBC.
- **DatabaseMetaData** và **ResultSetMetaData**: metadata về CSDL và tập kết quả.

Khai báo:

~~~java
module com.example.app {
    requires java.sql;
}
~~~

Ví dụ JDBC với một URL, username và password được truyền từ cấu hình của ứng dụng:

~~~java
package com.example.app;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public class JdbcExample {
    public static void printCustomerName(
            String url, String username, String password, long customerId)
            throws SQLException {

        String sql = "SELECT name FROM customers WHERE id = ?";

        try (Connection conn = DriverManager.getConnection(
                    url, username, password);
             PreparedStatement ps = conn.prepareStatement(sql)) {

            ps.setLong(1, customerId);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    System.out.println(rs.getString("name"));
                }
            }
        }
    }
}
~~~

Trong ví dụ này, **try-with-resources** đóng ResultSet, PreparedStatement và Connection khi thoát scope. Dấu **?** trong PreparedStatement đại diện cho giá trị tham số; cách này phù hợp hơn việc nối chuỗi dữ liệu người dùng vào SQL.

**Điều kiện để kết nối thành công:** ngoài java.sql, runtime cần có **JDBC driver của loại CSDL tương ứng** (PostgreSQL, MySQL, MariaDB, SQL Server, v.v.) trên class path hoặc module path theo cách triển khai. Driver có thể được phát hiện thông qua cơ chế service provider. Cấu hình class loader và module có thể ảnh hưởng đến khả năng tìm driver. **java.sql không chứa sẵn tất cả driver CSDL.**

Khi xảy ra lỗi kiểu **No suitable driver**, cần kiểm tra URL JDBC, dependency của driver, cách đóng gói và cách runtime tìm provider. Lỗi này không tự chứng minh **java.sql** bị thiếu.

### java.sql và java.sql.rowset khác nhau ra sao?

**java.sql** là API JDBC lõi. **java.sql.rowset** bổ sung các RowSet API, chẳng hạn **JdbcRowSet**, **CachedRowSet** và RowSet provider. Nếu dùng **javax.sql.rowset.RowSetProvider** trong named module, cần khai báo phụ thuộc đến **java.sql.rowset**.

~~~java
module com.example.app {
    requires java.sql;
    requires java.sql.rowset;
}
~~~

## 5. java.xml: xử lý XML theo API Java SE

Module **java.xml** hỗ trợ parse, biến đổi và làm việc với XML. Một số cách thường dùng:

- **DOM**: nạp cây XML vào các đối tượng Document, Element, Node.
- **SAX**: đọc XML theo sự kiện, có thể phù hợp với tài liệu lớn.
- **StAX**: xử lý XML theo cơ chế streaming pull.
- **Transformer**: biến đổi hoặc xuất XML.

Ví dụ parse XML từ một chuỗi an toàn, tự cung cấp:

~~~java
package com.example.app;

import java.io.StringReader;
import javax.xml.parsers.DocumentBuilderFactory;
import org.xml.sax.InputSource;

public class XmlExample {
    public static void main(String[] args) throws Exception {
        String xml = "<book><title>Java Modules</title></book>";

        DocumentBuilderFactory factory =
                DocumentBuilderFactory.newInstance();
        var builder = factory.newDocumentBuilder();
        var document = builder.parse(
                new InputSource(new StringReader(xml)));

        System.out.println(
                document.getDocumentElement()
                        .getElementsByTagName("title")
                        .item(0)
                        .getTextContent());
    }
}
~~~

Với XML từ bên ngoài, cần cấu hình XML parser phù hợp để hạn chế xử lý các thực thể bên ngoài (XXE) và tài nguyên không mong muốn. Ví dụ trên dùng chuỗi XML cố định chỉ nhằm minh họa API.

Khai báo trong **module-info.java**:

~~~java
module com.example.app {
    requires java.xml;
}
~~~

Không nhầm **java.xml** (XML parser/transform APIs) với **java.xml.crypto** (API chữ ký số XML).

## 6. java.net.http: HTTP Client trong JDK hiện đại

Từ Java 11, module **java.net.http** cung cấp **HttpClient**, **HttpRequest** và **HttpResponse** để gửi yêu cầu HTTP/HTTPS đồng bộ hoặc bất đồng bộ.

~~~java
module com.example.app {
    requires java.net.http;
}
~~~

Ví dụ minh họa cách tạo request (không tự gửi request):

~~~java
package com.example.app;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;

public class HttpExample {
    public static void main(String[] args) {
        HttpClient client = HttpClient.newHttpClient();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/api/items"))
                .GET()
                .build();

        System.out.println(request.method());
        System.out.println(client.version());
    }
}
~~~

Nếu thực sự gửi yêu cầu đồng bộ:

~~~java
// Có kết nối mạng thực tế khi chạy:
var response = client.send(
        request, java.net.http.HttpResponse.BodyHandlers.ofString());
System.out.println(response.statusCode());
~~~

Đoạn thứ hai là minh họa thêm trong cùng ngữ cảnh biến **client** và **request** ở trên; nó có thể phát sinh **IOException** hoặc **InterruptedException**, và nên được đặt trong phương thức có xử lý hai loại lỗi đó.

Không nhầm module **java.net.http** với **java.net**: package **java.net** thuộc **java.base** và chứa những API nền tảng như URI, URL và Socket. Để import **java.net.http.HttpClient**, named module vẫn cần **requires java.net.http**.

## 7. java.desktop, java.management và các module hỗ trợ khác

### java.desktop

Module **java.desktop** chứa AWT, Swing, Java 2D, Image I/O và các API desktop liên quan:

~~~java
module com.example.viewer {
    requires java.desktop;
}
~~~

Ví dụ import **javax.swing.JFrame**, **java.awt.Graphics2D** hoặc **javax.imageio.ImageIO**. Môi trường headless/server có thể không hỗ trợ tạo cửa sổ; **module có mặt** không có nghĩa môi trường có giao diện đồ họa.

### java.management

Module **java.management** cung cấp API giám sát JVM và JMX:

~~~java
module com.example.monitor {
    requires java.management;
}
~~~

Ví dụ:

~~~java
import java.lang.management.ManagementFactory;

long used = ManagementFactory.getMemoryMXBean()
        .getHeapMemoryUsage()
        .getUsed();

System.out.println("Heap used (bytes): " + used);
~~~

Giá trị là lượng heap đang sử dụng được báo cáo khi đo. Với JMX từ xa, cần xem thêm cấu hình và bảo mật của tiến trình JVM.

### java.naming

Module **java.naming** chứa JNDI, dùng khi code phụ thuộc các API **javax.naming** để lookup tài nguyên hoặc dịch vụ.

### java.compiler và các module JDK liên quan

**java.compiler** cung cấp các API chuẩn như **javax.tools.JavaCompiler** và **javax.lang.model**. Một JDK đầy đủ còn có module riêng **jdk.compiler** cung cấp triển khai trình biên dịch javac. **Có API compiler** không đồng nghĩa với **có công cụ javac hoặc compiler provider** trong mọi runtime image.

### java.scripting

**java.scripting** định nghĩa **javax.script.ScriptEngineManager** và các interface script engine. Sự tồn tại của API không bảo đảm một engine cụ thể được cài. Ví dụ một số JDK hiện đại không còn tích hợp Nashorn theo cách các bản JDK cũ từng cung cấp.

### java.prefs, java.rmi, java.instrument

**java.prefs** cung cấp **Preferences**; **java.rmi** hỗ trợ Remote Method Invocation; **java.instrument** cung cấp API **Instrumentation** cho agent. Chỉ khai báo requires cho API mà module sử dụng trực tiếp; không nên thêm hàng loạt module vào descriptor không có nhu cầu.

## 8. Ví dụ ứng dụng modular sử dụng nhiều module chuẩn

Ta tạo một ứng dụng tên **demo.jdkmodules** để minh họa cách một named module dùng logging, JDBC metadata, HTTP Client và XML parser. Chương trình không thực hiện kết nối mạng hoặc CSDL.

Cấu trúc:

~~~text
src/
  demo.jdkmodules/
    module-info.java
    demo/jdkmodules/Main.java
~~~

**src/demo.jdkmodules/module-info.java**:

~~~java
module demo.jdkmodules {
    requires java.logging;
    requires java.sql;
    requires java.net.http;
    requires java.xml;
}
~~~

**src/demo.jdkmodules/demo/jdkmodules/Main.java**:

~~~java
package demo.jdkmodules;

import java.net.http.HttpClient;
import java.sql.DriverManager;
import java.util.logging.Logger;
import javax.xml.parsers.DocumentBuilderFactory;

public class Main {
    private static final Logger LOG =
            Logger.getLogger(Main.class.getName());

    public static void main(String[] args) {
        LOG.info("Đang kiểm tra những API của module chuẩn");

        System.out.println("HTTP version ưu tiên: " +
                HttpClient.newHttpClient().version());

        System.out.println("Có JDBC driver khả dụng: " +
                DriverManager.getDrivers().hasMoreElements());

        System.out.println("XML parser factory: " +
                DocumentBuilderFactory.newInstance()
                        .getClass().getName());

        System.out.println("java.sql trong boot layer: " +
                ModuleLayer.boot().findModule("java.sql").isPresent());
    }
}
~~~

Biên dịch từ thư mục chứa **src** bằng JDK 11 trở lên:

~~~sh
javac --module-source-path src -d mods -m demo.jdkmodules
~~~

Chạy ứng dụng:

~~~sh
java --module-path mods -m demo.jdkmodules/demo.jdkmodules.Main
~~~

Kết quả gồm thông tin logging và bốn dòng từ System.out. Giá trị **Có JDBC driver khả dụng** phụ thuộc driver có sẵn trong môi trường; phiên bản HTTP ưu tiên và tên XML parser cũng có thể thay đổi theo JDK và cấu hình provider. **java.sql trong boot layer** dự kiến là **true** vì module demo.jdkmodules khai báo requires java.sql.

Lỗi biên dịch điển hình khi quên khai báo **requires**:

~~~text
package java.sql is not visible
(package java.sql is declared in module java.sql,
 but module demo.jdkmodules does not read it)
~~~

Thông điệp thực tế có thể khác đôi chút theo JDK. Để sửa, thêm **requires java.sql;** vào **module-info.java**, bảo đảm môi trường có module phù hợp và biên dịch lại. Import Java package trong mã nguồn không thể thay thế khai báo phụ thuộc ở cấp module.

## 9. Các lệnh xem module của JDK

### Liệt kê module trong runtime hiện tại

~~~sh
java --list-modules
~~~

Kết quả có tên và phiên bản module, ví dụ:

~~~text
java.base@<phiên-bản>
java.logging@<phiên-bản>
java.sql@<phiên-bản>
java.xml@<phiên-bản>
~~~

Dấu **<phiên-bản>** ở trên chỉ là ký hiệu minh họa; đầu ra thực tế phụ thuộc bản Java. Danh sách của **--list-modules** thể hiện các module có thể quan sát trong runtime dùng để chạy lệnh, không chứng minh mọi module trong đó đều đã resolve vào boot layer của một ứng dụng bất kỳ.

### Xem descriptor của một module

~~~sh
java --describe-module java.logging
java --describe-module java.sql
java --describe-module java.net.http
~~~

Lệnh này hiển thị thông tin như **exports**, **requires**, **uses** và **provides** tùy module. Đây là cách kiểm tra xem module nào cung cấp package và khai báo những quan hệ phụ thuộc nào trên JDK thực tế.

### Quan sát module resolution của ứng dụng

~~~sh
java --show-module-resolution --module-path mods -m demo.jdkmodules/demo.jdkmodules.Main
~~~

**--show-module-resolution** hữu ích để xem module gốc và các phụ thuộc được giải quyết. Phân biệt với **--list-modules**: danh sách module có thể quan sát không đồng nghĩa với đồ thị của chương trình đang chạy.

### Tìm module dependencies của thư viện với jdeps

Sau khi đã biên dịch JAR, có thể phân tích phụ thuộc tĩnh bằng công cụ **jdeps**:

~~~sh
jdeps --print-module-deps path/to/library.jar
~~~

Kết quả gợi ý tập module JDK mà công cụ phát hiện theo phụ thuộc tĩnh. Phân tích này có giới hạn với reflection, class loading động, ServiceLoader và cấu hình môi trường. Không nên coi đầu ra jdeps là một danh sách bao trùm mọi module có thể cần ở runtime.

## 10. Quan hệ giữa requires, exports, opens và runtime image

Bốn khái niệm thường bị nhầm:

**requires X**: module hiện tại yêu cầu đọc module X. Ví dụ **requires java.sql;** giúp named module đọc module java.sql và dùng public API được export phù hợp.

**exports p**: module khai báo package p được dùng bởi module khác ở mức truy cập Java thông thường. Nếu một package không export, có module dependency không đủ để import class của nó từ module khác.

**opens p**: cho phép reflective access sâu theo cơ chế JPMS, hữu ích cho một số framework. **opens** không có nghĩa package đó cũng được export cho các truy cập thông thường tại thời điểm biên dịch.

**jlink runtime image**: ứng dụng có thể được đóng gói với một tập module được lựa chọn. Nếu chương trình cần **java.sql** mà image không chứa module đó, sẽ không thể resolve phụ thuộc như trên một JDK đầy đủ. Kiểm tra runtime thực tế bằng **java --list-modules**, và xem cách image đã được tạo.

Một module có thể **requires transitive** module khác. Điều này làm khả năng đọc module phụ thuộc được truyền tiếp tới những module đọc module hiện tại theo quy tắc JPMS. Khi thiết kế **module-info.java**, nên khai báo phụ thuộc trực tiếp và transitive theo API thực sự phơi bày, thay vì thêm **requires transitive** cho tất cả dependency.

**java.se** là aggregator module: nó khai báo các phụ thuộc transitive để đại diện tập module Java SE liên quan. Đối với ứng dụng thông thường, khai báo cụ thể **requires java.sql;** hoặc **requires java.logging;** thường giúp đồ thị dependency thể hiện nhu cầu thật rõ ràng hơn.

## 11. Các nhầm lẫn phổ biến và cách xử lý

| Nhầm lẫn | Thực tế | Cách xử lý |
|---|---|---|
| “Tất cả Java API thuộc java.base” | java.base là nền tảng tối thiểu, nhiều API có module riêng | Tra package và kiểm tra module chứa API |
| “Import java.sql là đủ” | Named module còn cần readability qua requires hoặc quan hệ transitive phù hợp | Khai báo requires java.sql |
| “Có java.sql là kết nối được mọi CSDL” | Cần JDBC driver và cấu hình tương ứng | Kiểm tra driver, URL, module/class path |
| “Có java.scripting thì có JavaScript engine” | API scripting và engine provider là hai thành phần khác nhau | Kiểm tra các ScriptEngineFactory thực tế |
| “Có java.desktop thì máy chủ tạo GUI được” | Môi trường headless có thể giới hạn API GUI | Kiểm tra môi trường đồ họa và nhu cầu |
| “Có module trong --list-modules thì module đã được resolve” | Observable modules khác resolved modules | Xem boot layer hoặc --show-module-resolution |
| “Mọi module jdk.* đều là Java SE API” | jdk.* thường là module gắn với công cụ và triển khai JDK | Phân biệt module Java SE với JDK-specific |
| “java.net.http có từ Java 9” | API HttpClient ổn định mang tên java.net.http từ Java 11 | Chọn JDK phù hợp với source/module |
| “jlink luôn đóng gói đầy đủ JDK” | Runtime image có thể chỉ gồm tập module được chọn | Xem tập module trong image |
| “requires luôn kéo mọi class vào RAM” | Module resolution không phải quá trình eager-load toàn bộ class | Phân biệt descriptor, graph và class loading |

## 12. Lựa chọn module theo chức năng

Nếu ứng dụng cần **ghi log đơn giản**, bắt đầu từ **java.logging**. Nếu cần **JDBC**, dùng **java.sql** và thêm driver phù hợp; nếu dùng RowSet, xem **java.sql.rowset**. Nếu cần **XML DOM/SAX/transform**, dùng **java.xml**. Nếu cần **HTTP Client** chuẩn từ Java 11, dùng **java.net.http**. Nếu cần **JMX/giám sát JVM**, dùng **java.management**; nếu làm **GUI AWT/Swing**, dùng **java.desktop**.

Trong named module, hãy khai báo **requires** cho các module chứa API mình sử dụng, kiểm tra bằng **java --describe-module** và biên dịch với JDK mục tiêu. Khi chạy trên runtime image tối giản, xác nhận các module đó thực sự có mặt. Đối với thư viện bên thứ ba và JDBC driver, cần xét thêm descriptor, Automatic-Module-Name hoặc cách đóng gói module/class path của thư viện.

**Ý chính:** Module chuẩn cung cấp những nhóm API Java theo chức năng. **java.logging** giải quyết logging; **java.sql** cung cấp JDBC; những module như **java.xml**, **java.net.http**, **java.management**, **java.desktop** mở rộng các chức năng cụ thể. Hiểu đúng ranh giới module giúp viết **module-info.java** chính xác, giảm phụ thuộc thừa và chẩn đoán lỗi resolution hoặc class loading hiệu quả hơn.