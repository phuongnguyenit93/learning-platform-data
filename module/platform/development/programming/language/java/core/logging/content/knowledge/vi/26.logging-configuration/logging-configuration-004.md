# Classpath configuration trong Java Core Logging

## 1. Classpath configuration là gì?

**Classpath configuration** là cách đóng gói tệp cấu hình logging thành **resource** có thể được nạp qua class loader của ứng dụng. Khi chạy, framework logging hoặc chính ứng dụng tìm resource theo tên, đọc các quy tắc cấu hình và khởi tạo logger, handler/appender, formatter, filter, mức log và nơi xuất dữ liệu.

Ví dụ, dự án dùng Maven/Gradle thường lưu cấu hình ở:

```text
src/
  main/
    java/
      com/example/App.java
    resources/
      logback.xml
  test/
    resources/
      logback-test.xml
```

Sau bước build thông thường, `src/main/resources/logback.xml` xuất hiện **ở gốc resource classpath** (không phải đường dẫn có tiền tố `src/main/resources`). Ứng dụng chỉ cần tìm resource có tên `logback.xml`. Trong test, `src/test/resources` thường được thêm vào test runtime classpath, cho phép dùng cấu hình riêng.

Điểm cần phân biệt:

- **Classpath resource:** được tìm bằng class loader, chẳng hạn `getResourceAsStream("logging.properties")`; có thể nằm trong thư mục classes hoặc bên trong JAR.
- **Đường dẫn hệ thống tệp:** như `/etc/myapp/logback.xml` hoặc `C:\\config\\logging.properties`; được hệ điều hành/JVM tìm trên đĩa, không tự động trở thành classpath resource.
- **System property / biến môi trường / cấu hình framework:** có thể yêu cầu backend đọc tệp ở vị trí khác; mỗi logging framework định nghĩa khóa và thứ tự ưu tiên riêng.
- **Logger API:** lời gọi `logger.info(...)` không tự nói lên backend nào đang hoạt động. Cơ chế tìm cấu hình phụ thuộc JUL, Logback, Log4j2, Spring Boot hoặc hệ thống đang tích hợp.

**Không có một quy tắc tự động chung cho mọi thư viện Java:** việc đặt tệp tên `logging.properties` vào `resources` không bảo đảm mọi logger sẽ nhận tệp đó.

## 2. Java tìm resource trên classpath như thế nào?

Giả sử có resource `config/logging.properties` trong `src/main/resources`. Có thể mở nó bằng:

```java
try (var input = MyApplication.class.getClassLoader()
        .getResourceAsStream("config/logging.properties")) {
    if (input == null) {
        throw new IllegalStateException("Missing config/logging.properties");
    }
    // Đọc dữ liệu hoặc chuyển InputStream cho bộ cấu hình logger.
}
```

Đây là **đoạn minh họa**, cần đặt trong phương thức của một lớp `MyApplication`; nó chỉ mở resource, chưa cấu hình logger. `ClassLoader.getResourceAsStream` dùng tên **không bắt đầu bằng `/`**. Ngược lại, `MyApplication.class.getResourceAsStream("/config/logging.properties")` dùng `/` để tìm từ gốc classpath; không có `/` thì `Class.getResourceAsStream` diễn giải tương đối theo package của lớp.

Thứ tự tìm phụ thuộc **class loader thực tế**, kiểu chạy và thứ tự classpath. Resource có thể nằm ở:

```text
build/classes/java/main/com/example/App.class
build/resources/main/logback.xml
```

hoặc trong JAR:

```text
app.jar
  com/example/App.class
  logback.xml
```

Trong một executable Spring Boot JAR, cùng resource có thể được đóng trong `BOOT-INF/classes/` và được launcher của Spring Boot đưa vào classpath nội bộ. Đừng suy luận đường dẫn vật lý của resource từ đường dẫn source.

### Trùng tên resource

Nếu `logback.xml` hoặc `logging.properties` xuất hiện ở nhiều JAR/thư mục, `getResource(...)` thường trả về một bản theo thuật toán tìm của class loader. Tính quyết định và thứ tự giữa các bản **phụ thuộc runtime/class loader**; không nên coi tên file trùng là cơ chế override đáng tin trong deployment.

Có thể kiểm tra các vị trí nhìn thấy bằng:

```java
import java.net.URL;
import java.util.Enumeration;

Enumeration<URL> urls = Thread.currentThread()
        .getContextClassLoader().getResources("logback.xml");
while (urls.hasMoreElements()) {
    System.out.println(urls.nextElement());
}
```

Đoạn này chỉ để chẩn đoán, không có stdout cố định vì đường dẫn khác nhau giữa các máy và kiểu đóng gói. Thread context class loader có thể khác class loader của lớp hiện tại, nhất là trong server hoặc plugin container. Khi chẩn đoán, dùng đúng loader mà logging framework thực tế sử dụng. Nếu có nhiều resource cấu hình, hãy loại bỏ bản ngoài ý muốn hoặc chỉ rõ vị trí cần dùng theo cơ chế được framework hỗ trợ.

## 3. Mỗi logging stack đọc cấu hình ra sao?

| Logging stack | Resource cấu hình điển hình | Cơ chế quan trọng |
| --- | --- | --- |
| **java.util.logging (JUL)** của JDK | `logging.properties` | JUL **không tự động tìm một `logging.properties` bất kỳ trên classpath**. JVM thường dùng cấu hình JUL mặc định, hoặc `-Djava.util.logging.config.file=...` trỏ tới file trên hệ thống tệp; có thể nạp resource classpath bằng `LogManager.readConfiguration(InputStream)`. |
| **SLF4J 2.x** | Không tự quy định `logback.xml` hay `log4j2.xml` | SLF4J là facade. Nó tìm **provider** trên runtime classpath, rồi backend được chọn mới đọc cấu hình tương ứng. |
| **Logback Classic** (thường dùng với SLF4J) | `logback-test.xml` trong test, `logback.xml` trong ứng dụng | Logback tìm cấu hình theo quy trình của nó; file test chuyên dụng có thể được ưu tiên. Có thể chỉ rõ tệp qua system property `logback.configurationFile`. |
| **Log4j 2 Core** | `log4j2-test.xml`, `log4j2.xml` hoặc định dạng được hỗ trợ | Log4j2 tìm file cấu hình theo quy tắc riêng, có cả biến thể dành cho test; có thể chỉ rõ vị trí bằng `log4j2.configurationFile`. |

Lưu ý:

1. Cơ chế tự tìm tệp, định dạng được hỗ trợ và thứ tự ưu tiên chính xác có thể thay đổi theo phiên bản thư viện. Cần đối chiếu phiên bản backend thật trong dependency tree khi gặp sự cố.
2. SLF4J **API** và **provider** là hai vai trò khác nhau. Chỉ có `slf4j-api` mà thiếu provider phù hợp thì ứng dụng có thể dùng logger không ghi ra đâu và phát cảnh báo; đồng thời nhiều provider trên classpath cũng gây kết quả không mong muốn.
3. SLF4J 2.x sử dụng cơ chế provider khác dòng 1.7.x trước đây; một binding cũ không thể được coi là provider tương thích. Ví dụ Logback 1.4/1.5 thường đi cùng SLF4J 2.x; phải kiểm tra tương thích phiên bản thực tế.
4. `logback-test.xml` hay `log4j2-test.xml` là **tên quy ước**, không mang đặc quyền bảo mật. Nếu vô tình đưa chúng vào runtime production, chúng có thể được chọn theo quy tắc tìm cấu hình của backend.
5. Tránh đặt đồng thời các bridge/adaptor trái chiều tạo vòng chuyển log (chẳng hạn vừa chuyển Log4j API sang SLF4J, vừa chuyển SLF4J trở lại Log4j bằng tổ hợp phụ thuộc không đúng). Xác định một backend đích rõ ràng.

## 4. Ví dụ Java 17 hoàn chỉnh: nạp JUL từ classpath

Để thấy cơ chế mà không cần tải thêm thư viện, ta dùng `java.util.logging` của JDK và **chủ động** đọc file `logging.properties` qua class loader.

Cấu trúc thư mục:

```text
classpath-logging-demo/
  ClasspathLoggingDemo.java
  resources/
    logging.properties
```

Nội dung tệp `resources/logging.properties`:

```properties
handlers=java.util.logging.ConsoleHandler
.level=INFO

java.util.logging.ConsoleHandler.level=INFO
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
java.util.logging.SimpleFormatter.format=%4$s: %5$s%n

demo.app.level=FINE
```

Giải thích nhanh: logger `demo.app` nhận mức `FINE`, nhưng `ConsoleHandler` đặt mức `INFO`. Vì event phải vượt qua **cả mức logger lẫn mức handler**, `FINE` sẽ không hiển thị, còn `INFO` và `WARNING` sẽ hiển thị. `SimpleFormatter.format` chỉ in level và message, giúp output kiểm chứng chính xác.

Nội dung tệp `ClasspathLoggingDemo.java`:

```java
import java.io.IOException;
import java.io.InputStream;
import java.util.logging.LogManager;
import java.util.logging.Logger;

public final class ClasspathLoggingDemo {
    private ClasspathLoggingDemo() {}

    public static void main(String[] args) throws IOException {
        ClassLoader loader = ClasspathLoggingDemo.class.getClassLoader();

        try (InputStream config =
                     loader.getResourceAsStream("logging.properties")) {
            if (config == null) {
                throw new IllegalStateException(
                        "Missing classpath resource: logging.properties");
            }
            LogManager.getLogManager().readConfiguration(config);
        }

        Logger logger = Logger.getLogger("demo.app");
        logger.fine("detail");
        logger.info("started");
        logger.warning("slow-operation");
    }
}
```

Tại thư mục `classpath-logging-demo`, biên dịch:

```bash
javac -d out ClasspathLoggingDemo.java
```

Chạy trên Linux/macOS (dấu `:` ngăn các mục classpath):

```bash
java -cp "out:resources" ClasspathLoggingDemo
```

Chạy trên Windows (dấu `;` ngăn các mục classpath):

```powershell
java -cp "out;resources" ClasspathLoggingDemo
```

Đầu ra **stderr** chính xác của `ConsoleHandler` theo cấu hình trên:

```text
INFO: started
WARNING: slow-operation
```

Không có dòng `FINE` và chương trình không ghi gì ra stdout. Nếu bỏ `resources` khỏi `-cp`, `getResourceAsStream("logging.properties")` trả về `null`; chương trình chủ động ném `IllegalStateException` với thông báo nêu rõ tên resource thiếu. Nếu chỉ đặt file ở thư mục làm việc nhưng không thêm thư mục đó vào classpath, class loader cũng không nhất thiết nhìn thấy file.

**Điểm mấu chốt:** ví dụ phải gọi `LogManager.readConfiguration(config)` một cách tường minh. Đây là cách ứng dụng đưa `logging.properties` từ classpath vào JUL; việc đặt resource trong JAR không tự khiến JUL sử dụng nó.

### Cấu hình JUL bằng file ngoài classpath

JUL còn hỗ trợ trỏ đến **file trên hệ thống tệp** ngay khi JVM khởi động:

```bash
java -Djava.util.logging.config.file=/path/to/logging.properties -cp out ClasspathLoggingDemo
```

Tuy nhiên chương trình mẫu **vẫn tự gọi `readConfiguration`**, nên cấu hình mà nó nạp từ classpath có thể thay thế cấu hình file chỉ định bằng system property. Khi muốn chứng minh hành vi của `-Djava.util.logging.config.file`, hãy dùng một chương trình **không tự nạp lại cấu hình**. Không coi hai nguồn này là tự động merge với nhau.

## 5. Ví dụ cấu hình Logback nằm trên classpath

Ứng dụng dùng `slf4j-api` cùng `logback-classic` tương thích có thể để `src/main/resources/logback.xml` như sau:

```xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>%d{HH:mm:ss.SSS} %-5level [%thread] %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.noisy" level="WARN"/>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

Đây là **cấu hình XML cho Logback, không phải chương trình Java chạy độc lập**. Khi backend Logback được chọn và đọc tệp thành công:

- Logger gốc ở `INFO`; các logger con kế thừa mức này nếu không cấu hình riêng.
- Logger `com.example.noisy` có mức `WARN`, nên các lời gọi `INFO` thông thường của nó sẽ không tạo event.
- `STDOUT` định nghĩa console appender cùng layout gồm timestamp, level, thread name, tên logger và message.
- Nếu cấu hình thêm nhiều appender hoặc additivity, log có thể bị gửi trùng sang nhiều đích; đây là vấn đề cấu hình, không nhất thiết là hai lần gọi logger.

Để test mà không thay đổi file production, đặt `logback-test.xml` trong `src/test/resources`. Trên test runtime classpath, Logback thường ưu tiên tệp dành cho test; ngoài test, chỉ package những resource thực sự dành cho runtime. Khi cần chỉ định file ngoài classpath, Logback hỗ trợ một lựa chọn tương tự:

```bash
java -Dlogback.configurationFile=/etc/myapp/logback.xml -cp "app.jar:lib/*" com.example.App
```

Đường dẫn và cú pháp classpath ở ví dụ này dành cho Linux/macOS; Windows dùng dấu `;` khi ngăn cách phần tử. Dòng lệnh chỉ minh họa cơ chế override; phải cung cấp class, các JAR phụ thuộc và file cấu hình thực tế mới chạy được.

Với **Log4j2 Core**, ứng dụng thường đặt `src/main/resources/log4j2.xml`; có thể dùng cấu hình test như `log4j2-test.xml` và override bằng `-Dlog4j2.configurationFile=...` theo phiên bản đang sử dụng. Không đưa cấu trúc `logback.xml` cho Log4j2 hoặc `log4j2.xml` cho Logback: XML và cách khởi tạo appender của hai backend khác nhau.

## 6. Classpath trong Maven, Gradle, JAR và test

### Maven/Gradle tiêu chuẩn

Theo cấu trúc dự án Java thông thường:

| Source | Ở runtime được dùng như | Mục đích |
| --- | --- | --- |
| `src/main/java` | Class đã biên dịch | Code ứng dụng |
| `src/main/resources` | Resource trong output `classes` hoặc JAR | Cấu hình logging phát hành cùng ứng dụng |
| `src/test/java` | Class đã biên dịch của test | Code test |
| `src/test/resources` | Resource chỉ nằm trên test runtime classpath | Cấu hình và dữ liệu test |

Các plugin/build script có thể tùy chỉnh source set, resource processing, excludes hoặc tên file. Vì thế, kiểm tra **artifact được tạo thật**, không chỉ nhìn file trong source tree.

Ví dụ kiểm tra JAR thường:

```bash
jar tf build/libs/my-app.jar
```

Tìm `logback.xml`, `log4j2.xml` hay `logging.properties` ở vị trí class loader có thể tìm thấy. Với Spring Boot executable JAR, nội dung thường nằm dưới `BOOT-INF/classes/` và dependencies dưới `BOOT-INF/lib/`; launcher của Spring Boot xử lý layout này. Không áp dụng cách tìm classpath JAR phẳng một cách máy móc cho mọi packaged launcher.

### `java -cp` và `java -jar` khác nhau

- `java -cp "classes:resources:lib/*" com.example.App` đặt rõ các mục application classpath trên Linux/macOS; trong Windows thay `:` bằng `;`.
- `java -jar app.jar` chạy main class trong JAR theo manifest và **bỏ qua tùy chọn classpath `-cp` do người dùng chỉ định**. Nó không vì thế tự đọc mọi tệp ở thư mục làm việc; có thể có classpath bổ sung qua manifest hoặc cơ chế launcher.
- Một executable JAR đóng gói theo framework có thể sử dụng class loader riêng và quy tắc riêng; test cần dùng đúng cách khởi chạy production.

Classpath khi chạy test không giống classpath chạy production. Ví dụ `logback-test.xml` có mặt trong `testRuntimeClasspath`, nhưng không được vô tình đóng vào JAR phát hành. Nếu bản ghi hiện trong IDE mà biến mất khi `java -jar`, hãy kiểm tra vị trí resource, logger provider và cấu hình appender trong artifact sản xuất.

### Library khác application

Thư viện dùng chung nên ưu tiên gọi API logging (ví dụ SLF4J) và để **ứng dụng chủ** chọn provider, appender và level. Một dependency thư viện tự nhúng `logback.xml` có thể tạo xung đột resource với ứng dụng. Nếu thư viện cần cấu hình nội bộ đặc biệt, cần một hợp đồng rõ ràng thay vì tự áp cấu hình toàn cục cho các ứng dụng tiêu thụ nó.

## 7. Thứ tự ưu tiên và cấu hình ghi đè

Classpath configuration chỉ là một nguồn trong nhiều nguồn cấu hình:

```text
Cấu hình có chủ đích của ứng dụng
    |
    +-- file resource đóng gói trên classpath
    |
    +-- file ngoài JAR do system property/framework chọn
    |
    +-- code khởi tạo hoặc reconfiguration API
    |
    +-- chính sách mặc định của backend
```

Sơ đồ này là **các nguồn có thể có**, không phải thứ tự ưu tiên cố định. Thứ tự thực tế phụ thuộc từng backend và thời điểm khởi tạo. Một cách đáng tin để quản lý môi trường là xác định rõ **một nơi chịu trách nhiệm chọn cấu hình**, rồi test chính cơ chế đó.

Trong Spring Boot, cấu hình logging thường được quản lý qua `logging.*` và cơ chế chọn cấu hình của Spring Boot. `logback-spring.xml` là biến thể do Spring Boot hỗ trợ, có khả năng kết hợp tính năng cấu hình riêng của Spring; ứng dụng Java thuần với Logback không nên giả định file tên này được tự tải như `logback.xml`. `logging.config` có thể chỉ rõ vị trí file theo cơ chế Spring Boot. Cần phân biệt **Spring Boot khởi tạo logging** và **Logback tự khởi tạo** để tránh tải cấu hình sớm, bỏ qua Spring property hoặc bị cấu hình ghi đè lần nữa.

Khi cần thay đổi log level theo môi trường, có thể giữ cấu hình classpath làm **giá trị mặc định hợp lý**, rồi đặt chính sách override được phiên bản framework hỗ trợ. Đừng hardcode thông tin nhạy cảm như mật khẩu, access token hoặc khóa API trong file cấu hình đóng gói vào JAR; tài liệu đó có thể được trích xuất từ artifact.

Hot reload không tự xuất hiện chỉ vì resource ở classpath. Một số backend hỗ trợ quét thay đổi file hoặc reload qua API, nhưng tài nguyên bên trong JAR thường không phải file có thể sửa tại chỗ. Nếu cần cấu hình động, hãy thiết kế pipeline override/reload riêng với đồng bộ, khả năng quan sát và giới hạn quyền truy cập phù hợp.

## 8. Chẩn đoán lỗi không tìm thấy hoặc nạp sai logging configuration

| Hiện tượng | Nguyên nhân thường gặp | Cách xác minh |
| --- | --- | --- |
| Log không xuất hiện | Sai level, thiếu appender, chỉ có facade mà không có provider, file không được tìm thấy | Kiểm tra runtime dependencies, cảnh báo khởi động, effective level và nơi xuất |
| Dùng JUL nhưng `logging.properties` trong resources không có tác dụng | JUL không tự đọc classpath resource theo tên đó | Dùng `LogManager.readConfiguration(InputStream)` hoặc file được chỉ bởi JUL system property |
| IDE chạy đúng, packaged JAR chạy khác | Resource bị exclude, launcher khác, classpath khác hoặc thiếu backend JAR | Kiểm tra artifact bằng `jar tf`, startup command và runtime classpath |
| Logback đọc cấu hình test ở production | `logback-test.xml` vô tình nằm trong runtime classpath | Kiểm tra nội dung JAR/dependency và đường dẫn resource được chọn |
| Console có log nhưng file appender không ghi | Relative path dựa trên working directory khác; thư mục thiếu quyền; appender không start | Kiểm tra working directory, absolute path, quyền và thông báo backend |
| Log bị lặp | Nhiều appender cùng đích, logger additivity, bridge cấu hình sai | Kiểm tra cây logger/appender và phụ thuộc chuyển tiếp |
| Hai bản `logback.xml` cạnh tranh | Dependency và ứng dụng đóng cùng tên resource | Liệt kê mọi resource trùng tên bằng `getResources` |
| Đặt `-D...` nhưng không tác dụng | Sai khóa framework, đặt property sau khi logger đã khởi tạo, hoặc code/framework nạp lại config | Kiểm tra tham số JVM, startup log, điểm khởi tạo backend |
| Log thay đổi bất ngờ giữa unit test | Test dùng logger context toàn cục, nhiều test thay đổi chung appender/level | Cô lập logger context nếu stack hỗ trợ, khôi phục cấu hình sau test |

Một quy trình chẩn đoán hiệu quả:

1. **Xác định backend thật:** ứng dụng dùng JUL, Logback hay Log4j2? Với SLF4J, kiểm tra provider đang được sử dụng và warning về nhiều provider hoặc provider không tương thích.
2. **Xác định cách khởi chạy:** `java -cp`, `java -jar`, Gradle/Maven run task, IDE, Spring Boot launcher hay container? Ghi nhận classpath/resource visibility phù hợp.
3. **Tìm đúng resource:** kiểm tra tên chính xác, chữ hoa/thường, đường dẫn dưới gốc resource, và các bản trùng tên. Đừng nhầm `resources/logback.xml` (cấu trúc source) với `logback.xml` (resource name).
4. **Kiểm tra việc nạp:** bật diagnostics/status logging của backend theo tài liệu phiên bản; xác nhận file nào được chọn, có lỗi parse/cấu hình appender không.
5. **Kiểm tra event đi qua chuỗi lọc:** logger level → filter → appender/handler level → encoder/formatter → đích xuất. Một dòng không thấy có thể đã bị lọc đúng thiết kế.
6. **Tái hiện từ artifact sản xuất:** so sánh kết quả ở IDE, test và packaged runtime với cùng mức log và cùng một event dễ nhận diện.

Với JUL, có thể in `getResource("logging.properties")` ra **stderr khi chẩn đoán** để xác định vị trí resource; không biến đường dẫn phụ thuộc môi trường thành một phần của output kỳ vọng trong unit test. Với backend khác, ưu tiên status logger/diagnostic flags của chính framework.

## 9. Kiểm thử classpath configuration

Một bài test cấu hình có giá trị nên kiểm tra **hành vi**, không chỉ sự tồn tại của file:

- **Resource có trên runtime classpath:** class loader đúng trả về resource; artifact sản xuất cũng có nó.
- **Đã được backend thật đọc:** effective level, appender và formatter khớp chính sách; không có lỗi parse hoặc dependency mismatch.
- **Test config được cô lập:** file trong `src/test/resources` không vô tình xuất hiện trong production artifact.
- **Ghi đè được khi cần:** đường dẫn/system property/framework override được kiểm thử bằng đúng command line và giai đoạn khởi tạo của hệ thống.
- **Không phụ thuộc thứ tự resource trùng tên:** ứng dụng kiểm soát một nguồn cấu hình hoặc phát hiện xung đột rõ ràng.
- **Startup/shutdown:** logging hoạt động ở giai đoạn khởi động mong muốn; async appender được flush/close theo hợp đồng khi dừng.
- **Không rò rỉ dữ liệu nhạy cảm:** thông tin bí mật không bị đóng trong config; log output không chứa token hoặc mật khẩu do encoder/MDC in ngoài ý muốn.

Nếu dùng nhiều profiles như `dev`, `test` và `prod`, nên xác định file cấu hình nào được phép dùng ở từng môi trường và lưu quy tắc chọn vào deployment configuration. Tên file chung trong một JAR không đủ để đảm bảo mọi môi trường sẽ tự chọn đúng chính sách.

**Ghi nhớ:** cấu hình logging trên classpath hoạt động khi resource **thực sự có mặt trong class loader đang dùng** và **backend thực sự biết cách đọc nó**. JUL cần đọc resource một cách tường minh nếu muốn dùng file classpath tùy ý; Logback/Log4j2 có quy tắc tự khám phá riêng; SLF4J chọn provider chứ không tự định nghĩa định dạng file. Khi gặp lỗi, kiểm tra đồng thời resource name, provider/backend, đóng gói artifact, precedence và cách ứng dụng khởi động.
