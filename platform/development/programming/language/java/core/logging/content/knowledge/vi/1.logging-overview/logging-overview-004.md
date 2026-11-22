# Logger và backend trong Java

Khi ứng dụng Java ghi log, lệnh gọi logger mới là điểm khởi đầu. Thành phần thực sự quyết định **bản ghi có được xuất hay không, được định dạng ra sao và đi đến đâu** là hệ thống logging phía sau. Phân biệt logger, API/facade và backend giúp chọn dependency đúng, cấu hình mức log đúng và xử lý các lỗi như không thấy log hoặc log bị in hai lần.

## 1. Logger là gì và backend làm gì?

Một **log event** (sự kiện log) thường gồm mức độ (level), tên logger, thông điệp, thời điểm và có thể có exception hoặc ngữ cảnh. Ví dụ: ứng dụng cần ghi một sự kiện INFO khi tác vụ hoàn thành.

- **Logger** là đối tượng mà mã nguồn gọi để tạo sự kiện log, chẳng hạn logger gắn với lớp Java đang chạy. Tên logger thường là tên lớp hoặc package để có thể điều chỉnh mức log theo phạm vi.
- **Logging API** quy định kiểu Logger, các phương thức và level mà mã nguồn sử dụng.
- **Facade** là lớp API chung đặt trước nhiều hệ thống triển khai. Ví dụ, mã nguồn gọi SLF4J mà không phải phụ thuộc trực tiếp vào Logback hay Log4j Core.
- **Provider / binding / adapter** nối một API/facade tới hệ thống tiếp nhận phù hợp. Tên gọi và cơ chế cụ thể phụ thuộc thư viện, phiên bản.
- **Backend (implementation)** xử lý sự kiện: áp dụng level/filter, định dạng và chuyển tới đích.
- **Handler** (trong java.util.logging, viết tắt JUL) hoặc **appender** (trong Logback/Log4j 2) là thành phần xuất bản ghi tới console, file hoặc đích khác. Formatter/layout quyết định cách thể hiện.

~~~mermaid
flowchart LR
    A["Mã ứng dụng"] --> B["Logger / logging API"]
    B --> C["Provider hoặc adapter nếu cần"]
    C --> D["Backend xử lý sự kiện"]
    D --> E["Handler / appender"]
    E --> F["Console, file, hệ thống tập trung"]
~~~

Đây là mô hình khái niệm, **không phải hệ thống nào cũng có từng hộp riêng**. Với JUL, Logger và bộ xử lý logging cùng thuộc JDK; không cần thêm facade hoặc provider. Với SLF4J, API ở phía ứng dụng và cần một provider/backend tương thích tại runtime để log thực sự được xử lý.

Ví dụ luồng phổ biến:

- **JUL thuần:** mã Java → java.util.logging.Logger → bộ xử lý JUL → ConsoleHandler/FileHandler.
- **SLF4J + Logback:** mã Java → org.slf4j.Logger → SLF4J provider do Logback cung cấp → Logback appender.
- **SLF4J + Log4j 2:** mã Java → org.slf4j.Logger → adapter/provider SLF4J 2 của Log4j 2 → Log4j Core → appender.

Lệnh lấy logger như LoggerFactory.getLogger(...) hoặc Logger.getLogger(...) **không đồng nghĩa** với việc mở file log, và việc một câu lệnh log được thực thi **không đảm bảo** thông điệp sẽ xuất hiện: còn phụ thuộc cấu hình level, filter, backend và nơi xuất.

## 2. Các tên dễ nhầm lẫn

| Thành phần | Vai trò chính | Điều cần nhớ |
| --- | --- | --- |
| **java.util.logging (JUL)** | API và logging implementation có sẵn trong JDK | Dùng java.util.logging.Logger, Handler, Formatter, LogManager; không cần dependency logging bên ngoài. |
| **SLF4J** | Facade/API cho mã ứng dụng và thư viện | org.slf4j.Logger là giao diện gọi log; bản thân slf4j-api không phải backend ghi log. |
| **Logback** | Backend logging, thường đi cùng SLF4J | logback-classic cung cấp SLF4J provider; appender, encoder, cấu hình quyết định đầu ra. |
| **Log4j 2** | Bộ logging có API và Core riêng | log4j-api là API; log4j-core xử lý đầu ra; có adapter để nhận log từ SLF4J. |
| **Bridge / adapter** | Chuyển sự kiện giữa hai API/hệ thống | Phải xem **chiều chuyển tiếp** và tránh tạo vòng lặp giữa các bridge. |

Hai lớp Java có tên Logger không nhất thiết là cùng kiểu: java.util.logging.Logger khác org.slf4j.Logger và khác org.apache.logging.log4j.Logger. Phải xem **import** để biết câu lệnh log đang đi qua API nào.

Một thư viện nên ưu tiên API logging mà hệ sinh thái của nó mong đợi, phổ biến là SLF4J; **ứng dụng chạy cuối cùng** quyết định backend nào sẽ có trên runtime classpath. Thư viện dùng facade thường không nên ép ứng dụng mang theo nhiều backend cạnh tranh.

### API và backend không thay thế nhau

Ví dụ, dependency slf4j-api cho phép biên dịch mã dùng org.slf4j.Logger. Nhưng với **SLF4J 2.x**, nếu lúc chạy không tìm thấy SLF4J provider tương thích, SLF4J sẽ cảnh báo và sử dụng logger không ghi đầu ra (NOP). Thêm một backend tương thích mới hoàn thành tuyến xử lý.

Ngược lại, thêm logback-classic vào ứng dụng **không tự động chuyển mọi lệnh gọi JUL sang Logback**: mã dùng java.util.logging vẫn theo JUL, trừ khi có bridge được cài đặt và cấu hình phù hợp.

## 3. Ví dụ hoàn chỉnh không cần thư viện ngoài: JUL

JUL là lựa chọn hữu ích để hiểu mối quan hệ giữa Logger, mức log và Handler mà không cần Gradle/Maven.

Tạo tệp **JulDemo.java**:

~~~java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class JulDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getLogger(JulDemo.class.getName());

        // Tránh in thêm qua handler của logger cha/root.
        logger.setUseParentHandlers(false);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.ALL);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " | "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });

        // Sự kiện FINE phải qua được cả Logger và Handler.
        logger.setLevel(Level.FINE);
        logger.addHandler(console);

        logger.fine("cache warmup");
        logger.info("service ready");
        logger.warning("retry requested");

        console.flush();
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac JulDemo.java
java JulDemo
~~~

Ba dòng ghi ra **stderr** bởi ConsoleHandler (định dạng đã được cố định trong ví dụ):

~~~text
FINE | cache warmup
INFO | service ready
WARNING | retry requested
~~~

Cơ chế đáng chú ý:

1. Logger mang tên JulDemo tạo sự kiện với level và message.
2. **logger.setLevel(Level.FINE)** cho phép FINE và các mức nghiêm trọng hơn qua bộ lọc của Logger.
3. **console.setLevel(Level.ALL)** bảo đảm Handler không loại bỏ riêng sự kiện FINE. Nếu đặt Handler ở INFO thì FINE vẫn bị chặn dù Logger cho phép.
4. **setUseParentHandlers(false)** tắt việc chuyển tiếp sự kiện đến Handler của logger cha; nếu cùng sự kiện tới nhiều Handler thì có thể xuất hiện log trùng.
5. Formatter trong ví dụ chỉ xuất level và message để có đầu ra ổn định. Formatter production còn có thể thêm timestamp, logger name và stack trace; muốn in exception đầy đủ thì formatter tùy chỉnh phải xử lý record.getThrown().

JUL có các level như SEVERE, WARNING, INFO, CONFIG, FINE, FINER, FINEST, ALL và OFF. Đây **không phải cùng tập tên level** với SLF4J (ERROR, WARN, INFO, DEBUG, TRACE). Khi đi qua bridge, level được ánh xạ theo quy tắc của bridge; không suy luận rằng hai API có level trùng tên hoặc tương đương hoàn toàn.

## 4. Ví dụ ứng dụng dùng SLF4J và một backend Logback

Ví dụ này dùng Java 17+, Gradle và **SLF4J 2.x**. Mã ứng dụng chỉ import SLF4J; Logback được chọn tại runtime. Các phiên bản dưới đây là một bộ tương thích để minh họa, không nhằm chỉ định phiên bản mới nhất cho mọi dự án.

**build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.slf4j:slf4j-api:2.0.17'
    runtimeOnly 'ch.qos.logback:logback-classic:1.5.18'
}

application {
    mainClass = 'demo.Slf4jDemo'
}
~~~

**src/main/java/demo/Slf4jDemo.java**:

~~~java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class Slf4jDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(Slf4jDemo.class);

    public static void main(String[] args) {
        String taskName = "sync";

        LOG.info("Job {} completed", taskName);
        LOG.debug("Debug code {}", 42);
    }
}
~~~

**src/main/resources/logback.xml**:

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Chạy từ thư mục dự án bằng **gradle run** (hoặc **./gradlew run** nếu dự án có Gradle Wrapper). Bản ghi từ ứng dụng có dạng:

~~~text
INFO demo.Slf4jDemo - Job sync completed
~~~

Dòng DEBUG không được in vì backend đặt root level = INFO. Đầu ra đầy đủ của lệnh có thể còn chứa thông báo build của Gradle.

Tại sao tách dependency như vậy?

- **implementation slf4j-api:** mã nguồn biên dịch dựa trên giao diện ổn định của facade.
- **runtimeOnly logback-classic:** backend được cung cấp khi chạy; nó đăng ký SLF4J provider tương thích. Nếu ứng dụng/framework đã cung cấp backend, hãy dùng cấu hình dependency do framework quản lý thay vì thêm một backend nữa.
- **logback.xml:** backend đọc cấu hình appender và level. Đổi từ Logback sang backend SLF4J khác thường không yêu cầu sửa các lệnh gọi LOG.info(...) trong mã nguồn; tuy nhiên file cấu hình, tính năng và dependency của backend sẽ thay đổi.

Cú pháp tham số **{}** ở ví dụ là của SLF4J. Không áp dụng nguyên xi cho JUL: mỗi API có phương thức và cơ chế định dạng riêng.

### Một backend được chọn, nhiều logger có thể dùng chung

Logger thường được đặt một biến static final theo từng lớp. Nhiều logger cùng ghi thông qua hệ thống backend được cấu hình cho ứng dụng; không cần tạo một appender/file mới cho mỗi lớp. Tên logger cho phép đặt level theo package, ví dụ tăng DEBUG chỉ cho phần mã đang điều tra, trong khi phần còn lại vẫn INFO.

## 5. Level và đường đi của một sự kiện log

Không thấy một bản ghi không nhất thiết là logger bị hỏng. Sự kiện có thể bị loại ở một trong nhiều vị trí:

1. **Điểm gọi / logger:** Level chưa bật thì API có thể bỏ qua sự kiện ngay từ đầu.
2. **Cấu hình có hiệu lực:** Logger có thể kế thừa level của package/root khi bản thân nó không đặt level riêng.
3. **Filter của backend/handler/appender:** Sự kiện được Logger chấp nhận nhưng vẫn bị chặn ở bước sau.
4. **Cách phân phối:** Một sự kiện có thể được gửi tới nhiều appender/handler. Nếu cấu hình cộng dồn hoặc chuyển tiếp lên logger cha không đúng, cùng sự kiện có thể in lặp.
5. **Đích nhận:** Console có thể dùng stdout hoặc stderr, file có thể nằm ở đường dẫn tương đối, hoặc backend có thể đẩy log tới hệ thống tập trung.

Trong JUL, logger và mỗi handler đều có level; setUseParentHandlers điều khiển việc chuyển tiếp đến handler của logger cha. Trong Logback, root logger và logger theo tên có level, appender và filter xử lý tiếp; thuộc tính **additivity** quyết định việc chuyển log lên logger cha. Đây là hai cách cấu hình khác nhau cho nhu cầu tương tự, không phải một API chung.

Một sơ đồ xử lý sự kiện có thể hình dung như sau:

~~~text
logger.info(...)
   |
   +--> logger/backend có cho phép mức INFO? -- không --> bỏ qua
   |
  có
   |
   +--> filter/appender/handler có chấp nhận? -- không --> bỏ qua
   |
  có
   |
   +--> định dạng --> console / file / hệ thống thu thập
~~~

Khi điều tra, hãy xác định logger dùng API nào trước, rồi lần theo backend và đích nhận thực sự. Việc tăng level ở một chỗ không giải quyết được khi bước tiếp theo vẫn chặn sự kiện.

## 6. Bridge: khi nhiều hệ thống logging cùng xuất hiện

Ứng dụng thực tế có thể dùng SLF4J, trong khi một dependency khác tạo log qua JUL hoặc Log4j 2 API. **Bridge** nhận sự kiện từ một API và chuyển sang hệ thống khác để backend trung tâm xử lý.

| Thành phần | Chiều chuyển tiếp điển hình |
| --- | --- |
| **jul-to-slf4j** | JUL → SLF4J; cần cài SLF4JBridgeHandler và xử lý các JUL handler hiện có để tránh log trùng. |
| **log4j-to-slf4j** | Log4j 2 API → SLF4J. |
| **log4j-slf4j2-impl** | SLF4J 2.x → Log4j 2; dùng khi chọn Log4j Core làm backend. |
| **logback-classic** | Cung cấp SLF4J provider và backend Logback; đây không phải bridge JUL. |

Ví dụ, nếu chương trình và thư viện dùng SLF4J nhưng backend mong muốn là Log4j 2, tuyến hợp lý là **SLF4J API → log4j-slf4j2-impl → Log4j Core**. Trong tuyến này không thêm logback-classic như backend thứ hai.

**Không ghép log4j-to-slf4j với log4j-slf4j2-impl trong cùng tuyến runtime.** Một bên chuyển Log4j API sang SLF4J, bên kia chuyển ngược SLF4J sang Log4j 2, tạo vòng chuyển tiếp không hợp lệ. Tương tự, với các bridge khác, phải kiểm tra hướng đi trước khi thêm dependency.

Nếu muốn JUL qua SLF4J, chỉ thêm JAR jul-to-slf4j chưa đủ để mọi sự kiện JUL tự động đổi đích. Cần cài đặt bridge handler vào JUL, cân nhắc gỡ handler JUL cũ và đánh giá chi phí chuyển đổi ở các mức log chi tiết. Trong nhiều framework, phần này đã được thiết lập sẵn; không cài thủ công chồng lên cấu hình của framework.

Trong ứng dụng chỉ dùng JUL hoặc chỉ có một API/backend đã phù hợp, **không cần bridge**.

## 7. Chọn backend phù hợp với loại dự án

- **Ứng dụng Java SE nhỏ, chỉ cần log cơ bản:** JUL có sẵn trong JDK, ít phụ thuộc, đủ dùng với ConsoleHandler/FileHandler và logging.properties.
- **Ứng dụng có nhiều thư viện hoặc cần backend có thể thay thế:** dùng SLF4J làm facade chung và chọn **một** provider/backend tương thích theo môi trường triển khai, chẳng hạn Logback hoặc Log4j 2.
- **Dự án dùng framework đã thiết lập logging:** ưu tiên cấu hình sẵn của framework. Kiểm tra classpath trước khi bổ sung backend/bridge; nhiều starter đã kéo các dependency cần thiết.
- **Thư viện dùng chung:** phụ thuộc vào API/facade được chọn, không buộc mọi ứng dụng sử dụng một backend cụ thể trừ khi có lý do thiết kế rõ ràng.

Tên cấu hình cũng phụ thuộc backend: **logging.properties** thường dùng cho JUL; **logback.xml** cho Logback; **log4j2.xml** cho Log4j 2. Một file logback.xml không cấu hình được JUL thuần, và đổi backend thường kéo theo việc đổi cấu hình.

## 8. Những lỗi phổ biến và cách kiểm tra

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra hoặc sửa |
| --- | --- | --- |
| Gọi LOG.info(...) nhưng không có bản ghi | Thiếu SLF4J provider, level cao hơn INFO, filter loại bỏ hoặc đầu ra nằm nơi khác | Xem cảnh báo lúc startup, kiểm tra runtime classpath, root/logger level, appender và stdout/stderr. |
| SLF4J báo không tìm được provider | Chỉ có slf4j-api hoặc có implementation/binding không tương thích | Chọn một provider khớp major version SLF4J đang dùng; kiểm tra dependency runtime. |
| SLF4J báo có nhiều provider | Hơn một backend/provider cùng có trên runtime classpath | Chỉ giữ provider được chọn và loại dependency kéo thêm provider còn lại. |
| Một dòng log xuất hiện hai lần | JUL tiếp tục dùng parent handlers; hoặc logger/appender additivity; hoặc cùng sự kiện đi qua hai tuyến bridge | Kiểm tra logger cha, danh sách handler/appender, cấu hình bridge và đường đi sự kiện. |
| DEBUG không thấy dù đã cấu hình Logger | Backend hoặc appender vẫn đặt ngưỡng cao hơn; thay đổi nhầm file cấu hình | Xác định đúng API/backend, effective level và file cấu hình được nạp lúc chạy. |
| JUL log không đến Logback | JUL và SLF4J là hai API khác nhau; bridge JUL chưa được cài hoặc kích hoạt | Nếu thực sự cần tập trung đầu ra, cấu hình jul-to-slf4j đúng chiều và tránh handler trùng. |
| Thay backend xong lỗi khi chạy | Thiếu artifact runtime, xung đột phiên bản API/provider hoặc bridge tạo vòng | Xem dependency tree và thông báo startup; sửa classpath thay vì chỉ thay import của Logger. |

Với Gradle, có thể xem các dependency thực sự tham gia lúc chạy:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency slf4j --configuration runtimeClasspath
~~~

Các lệnh trên chỉ dùng được trong dự án Gradle có Wrapper và cấu hình tương ứng. Khi đọc kết quả, tìm **slf4j-api**, provider (ví dụ **logback-classic** hoặc **log4j-slf4j2-impl**) và các bridge; chú ý dependency transitively kéo thêm backend ngoài dự kiến.

## 9. Thực hành và lưu ý

Khi thêm logging vào một lớp Java, hãy đi theo thứ tự: **xác định API → chọn backend ở ứng dụng → cấu hình level và handler/appender → xác nhận đầu ra thực tế**. Đừng chọn implementation chỉ dựa vào tên kiểu Logger đang import.

Với log của tác vụ thường xuyên, dùng mức phù hợp (INFO cho mốc vận hành, DEBUG/TRACE cho thông tin điều tra chi tiết), ưu tiên tham số hóa thông điệp để tránh tạo chuỗi tốn kém khi level đang tắt. Khi ghi lỗi, truyền exception theo phương thức mà API hỗ trợ để backend có thể xuất stack trace. Tránh đưa mật khẩu, token hoặc dữ liệu nhạy cảm vào log bất kể backend nào đang được dùng.

**Ghi nhớ:** Logger là cửa vào tạo sự kiện; facade cung cấp giao diện gọi chung; provider/adapter nối hệ thống nếu cần; backend, filter và handler/appender mới quyết định đường đi và cách xuất log. Một tuyến logging rõ ràng giúp kiểm soát level, nơi lưu log và tránh xung đột dependency.