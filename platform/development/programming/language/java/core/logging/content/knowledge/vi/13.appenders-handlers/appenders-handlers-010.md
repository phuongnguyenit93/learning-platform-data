# Đóng appender an toàn trong Java Logging

## Mục tiêu bài học

Trong ứng dụng Java, một lời gọi logger trả về **không đồng nghĩa** mọi byte log đã được ghi, gửi đi hoặc lưu bền vững. Appender có thể giữ stream, file lock, queue, worker thread hoặc kết nối mạng. Nếu tiến trình kết thúc không có trình tự shutdown đúng, bạn có thể gặp log cuối bị thiếu, file chưa đóng, worker thread còn chạy hoặc thông tin chẩn đoán quan trọng bị mất.

Bài này thuộc nhóm **Appender và handler** của **Java Core Logging**, tập trung vào **đóng appender an toàn**. Sau bài, bạn có thể:

- Giải thích **start/stop**, **flush/close** và trách nhiệm quản lý vòng đời của appender/handler.
- Chọn đúng thứ tự **dừng nhận công việc → đợi tác vụ đang chạy → ghi log kết thúc → dừng logging context → thoát tiến trình**.
- Dùng **LoggerContext.stop()** trong Logback, hiểu khi nào backend/framework nên là chủ sở hữu lifecycle.
- Đánh giá giới hạn của **AsyncAppender**, queue, discardingThreshold, neverBlock và maxFlushTime khi shutdown.
- Chạy ví dụ **Java 17 + Logback** ghi file, dừng context, đọc lại dữ liệu; so sánh với **java.util.logging.Handler.close()** qua ví dụ JDK độc lập.
- Nhận diện các tình huống không thể bảo đảm không mất log: cưỡng bức kill, crash, mất kết nối, queue quá tải hoặc thiếu acknowledgment từ hệ thống lưu trữ.

## 1. Vì sao phải đóng appender?

Một logging pipeline thông dụng:

~~~mermaid
flowchart LR
    A["Mã Java / Logger"] --> B["Level, Filter"]
    B --> C["Appender"]
    C --> D["Encoder / Layout"]
    D --> E["File, console, mạng"]
~~~

Với ghi bất đồng bộ, có thêm hàng đợi và luồng worker:

~~~mermaid
flowchart LR
    A["Logger"] --> B["AsyncAppender: queue"]
    B --> C["Worker thread"]
    C --> D["FileAppender / Network appender"]
    D --> E["Đích nhận"]
~~~

Tùy implementation, một Appender có thể sở hữu:

- **OutputStream/file descriptor** và bộ đệm I/O.
- **Lock file**, tên file đang ghi và rotation/rolling state.
- **Encoder** có cơ chế khởi tạo, header/footer và charset.
- **Queue** nhận logging event và **worker thread** chuyển record tới đích.
- **Kết nối network**, batch request hoặc công việc nén file sau rotation.
- **Tài nguyên phụ trợ** cần được giải phóng theo lifecycle.

Khi JVM dừng đột ngột, những tài nguyên trên không phải lúc nào cũng hoàn tất công việc. Đối với **đóng an toàn**, không chỉ hỏi “đã gọi stop chưa?”, mà còn phải hỏi “**còn producer nào đang tạo event, queue còn record nào, có lỗi khi đóng đích không, và hệ thống thu thập đã nhận chưa?**”.

**Giới hạn quan trọng:** đóng appender đúng trình tự giúp giảm rủi ro mất log và giải phóng tài nguyên, nhưng **không bảo đảm** log đã fsync xuống thiết bị lưu trữ, được collector tiếp nhận hoặc đạt tính bền vững như một transaction database.

## 2. Phân biệt stop, close, flush, shutdown và durability

| Thuật ngữ | Ý nghĩa cốt lõi | Điều không nên suy diễn |
| --- | --- | --- |
| **Appender.start()** | Kích hoạt appender sau khi cấu hình | Chưa chứng minh đích luôn có thể nhận log |
| **Appender.stop()** | Dừng appender và giải phóng tài nguyên do implementation quản lý | Không có bảo đảm chung mọi record đã được lưu bền vững |
| **Handler.flush()** (JUL) | Đẩy dữ liệu đang đệm tới stream đích của handler | Không đồng nghĩa file đã sync xuống ổ cứng |
| **Handler.close()** (JUL) | Flush rồi đóng handler và giải phóng tài nguyên | Không nên tiếp tục dùng handler sau close |
| **LoggerContext.stop()** (Logback) | Dừng logging context, các appender liên quan và tác vụ của context | Không thay nhiệm vụ dừng producer nghiệp vụ hoặc dịch vụ bên ngoài |
| **Async queue drain** | Worker tiêu thụ event còn xếp hàng | Có thể bị giới hạn bởi timeout, lỗi sink hoặc cơ chế drop |
| **Graceful process shutdown** | Dừng công việc và giải phóng tài nguyên có thứ tự | Không phải thao tác nào cũng xảy ra khi bị kill cưỡng bức |
| **Durable delivery** | Đích cuối đã xác nhận lưu theo hợp đồng riêng | Không được suy ra chỉ từ return của logger.info(...) |

Trong **Logback**, Appender thuộc lifecycle với các thao tác start/stop và trạng thái started. Không dùng ngẫu nhiên khái niệm Java Closeable/AutoCloseable để giả định có thể đưa mọi Appender vào try-with-resources. Cơ chế chuẩn nên dùng là **stop()** hoặc để **LoggerContext.stop()** quản lý các appender trong cùng context.

Trong **java.util.logging (JUL)**, đối tượng tương ứng là **Handler**. API Handler có **flush()** và **close()**; theo Java SE 17, close thực hiện flush và giải phóng tài nguyên, sau đó handler **không nên được dùng tiếp**. Vì JUL Handler không phải cùng loại API với Logback Appender, không dùng tên phương thức thay thế cho nhau.

## 3. Thứ tự shutdown an toàn

Một luồng kết thúc ứng dụng có chủ đích nên theo thứ tự:

~~~text
1. Nhận yêu cầu dừng: SIGTERM, lifecycle event hoặc thao tác quản trị.
2. Ngừng nhận thêm request/job mới.
3. Chờ hoặc hủy có kiểm soát công việc đang chạy, với thời hạn hợp lý.
4. Phát các bản ghi kết thúc cần thiết, bao gồm kết quả của các job đã hoàn tất.
5. Dừng logging context / async appender để xử lý hàng đợi và đóng đích xuất.
6. Xác nhận kết quả trong phạm vi có thể quan sát, rồi cho tiến trình thoát.
~~~

**Lý do bước 4 phải xảy ra trước bước 5:** nếu đã stop appender rồi mới gọi logger.info("server.stopped"), record có thể bị bỏ hoặc chỉ gây cảnh báo nội bộ. Khi đó câu lệnh log vẫn chạy trong code nhưng không còn đích hợp lệ để xuất.

**Lý do bước 2–3 phải trước bước 5:** nếu request đang xử lý tiếp tục phát log trong khi appender bị đóng, các record đó có thể mất. Việc dừng logging trước khi dừng executor hoặc HTTP server là lỗi thứ tự shutdown thường gặp.

Đây là thứ tự **logic**. Cách triển khai chi tiết phụ thuộc server/framework: Spring, Jakarta Servlet, worker consumer, command-line application, scheduler hoặc môi trường container có callback và thời hạn shutdown khác nhau. Nên chỉ định rõ **chủ sở hữu việc stop**, tránh hai thành phần tùy ý đóng cùng context giữa lúc ứng dụng còn ghi log.

## 4. Logback: ai chịu trách nhiệm đóng appender?

Logback Classic có **LoggerContext**, là context chứa các logger và cấu hình appender liên quan. Với ứng dụng thật sự dùng Logback làm SLF4J provider, bạn có thể lấy context và dừng:

~~~java
// Đoạn minh họa: chỉ phù hợp khi backend thực sự là Logback Classic.
ch.qos.logback.classic.LoggerContext context =
        (ch.qos.logback.classic.LoggerContext)
                org.slf4j.LoggerFactory.getILoggerFactory();
context.stop();
~~~

Tài liệu Logback khuyến nghị dừng context để giải phóng tài nguyên. Việc này đóng các appender được gắn với logger thuộc context, đồng thời dừng các luồng đang hoạt động của logging system theo cơ chế của Logback.

**Không phải đoạn code hoàn toàn độc lập backend:** LoggerFactory.getILoggerFactory() có thể trả implementation khác nếu provider là slf4j-simple hoặc adapter Log4j 2. Khi đó cast sang LoggerContext là sai. Facade SLF4J **không cung cấp phương thức đóng mọi backend theo một hợp đồng chung**. Shutdown thuộc trách nhiệm backend hoặc framework sở hữu nó.

**Đừng đóng appender dùng chung một cách tùy tiện.** Nếu nhiều logger cùng gửi đến appender FILE, một module không nên gọi FILE.stop() chỉ vì chức năng của nó đã xong; như vậy các module khác có thể mất đích xuất. Với ứng dụng sở hữu trọn context, việc stop context khi shutdown toàn ứng dụng thường dễ kiểm soát hơn tự đóng từng appender.

### Khi nào stop một appender riêng?

Có thể stop riêng appender khi **bạn trực tiếp tạo và quản lý nó**, biết chắc không còn producer nào sử dụng, và đang thay đổi cấu hình hoặc kết thúc một thành phần có vòng đời tách biệt. Quy trình nên có bước tách nó khỏi các logger hoặc chặn producer mới, bảo đảm không có race, rồi stop. Không stop appender đang dùng chung chỉ vì muốn xóa log cũ.

### Khi nào không cần tự stop bằng business code?

Trong nhiều application server hoặc framework, logging lifecycle đã được quản lý bởi container/framework. Khi đó, tránh để mỗi service tự gọi LoggerContext.stop(). Nên dùng callback/lifecycle của **chủ sở hữu ứng dụng** (hoặc shutdown hook phù hợp) để thực hiện một shutdown có thứ tự, và kiểm tra xem framework có tự đóng Logback khi ngừng chạy hay không.

## 5. Thực hành Java 17 + Logback: ghi file rồi dừng context

Ví dụ này chạy độc lập qua Maven với **Logback Classic 1.5.18**. Chương trình phát hai event, gọi LoggerContext.stop() trong finally, sau đó đọc file để đối chiếu kết quả và kiểm tra context đã dừng. File được đặt dưới thư mục **target** của dự án.

Mục đích là minh họa **trình tự đúng trong một ứng dụng nhỏ, có một luồng tạo log**, không phải chứng minh ứng dụng phân tán luôn giao log chính xác một lần.

### Cấu trúc dự án

~~~text
safe-appender-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/
        │       └── example/
        │           └── logging/
        │               └── SafeAppenderDemo.java
        └── resources/
            └── logback.xml
~~~

### File pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>safe-appender-demo</artifactId>
  <version>1.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>ch.qos.logback</groupId>
      <artifactId>logback-classic</artifactId>
      <version>1.5.18</version>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.3.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**Phiên bản được cố định để tái hiện bài học**, không phải tuyên bố về bản mới nhất. Dependency logback-classic mang theo các thành phần Logback và API SLF4J tương thích. Một dự án thật nên quản lý versions theo BOM/dependencyManagement và chính sách bảo mật của tổ chức.

### File src/main/resources/logback.xml

~~~xml
<configuration>
  <appender name="FILE" class="ch.qos.logback.core.FileAppender">
    <file>target/shutdown-demo.log</file>
    <append>false</append>
    <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
      <charset>UTF-8</charset>
      <pattern>%level | %msg%n</pattern>
    </encoder>
  </appender>

  <root level="INFO">
    <appender-ref ref="FILE"/>
  </root>
</configuration>
~~~

- **FILE** là appender ghi vào file, không phải ConsoleAppender. Log của demo không tự in ra terminal.
- **append=false** chỉ nhằm tạo file mới sạch cho mỗi lần chạy bài thực hành. Trong production, không vô tình dùng chế độ này với đường dẫn log cần giữ qua nhiều lần khởi động; xem xét append/rolling/retention thích hợp.
- **PatternLayoutEncoder** xuất record thành text UTF-8. Pattern in level, message và ký tự xuống dòng.
- **root INFO** cho phép hai event INFO. Không có logger khác được gắn appender trong cấu hình mẫu.

### File src/main/java/com/example/logging/SafeAppenderDemo.java

~~~java
package com.example.logging;

import ch.qos.logback.classic.LoggerContext;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class SafeAppenderDemo {
    public static void main(String[] args) throws Exception {
        Path logFile = Path.of("target", "shutdown-demo.log");
        LoggerContext context =
                (LoggerContext) LoggerFactory.getILoggerFactory();
        Logger logger = LoggerFactory.getLogger(SafeAppenderDemo.class);
        try {
            logger.info("event=job.started id={}", "job-7");
            logger.info("event=job.finished id={} result={}", "job-7", "ok");
        } finally {
            context.stop();
        }

        List<String> lines = Files.readAllLines(logFile, StandardCharsets.UTF_8);
        System.out.println("recordCount=" + lines.size());
        for (String line : lines) {
            System.out.println(line);
        }
        System.out.println("contextStarted=" + context.isStarted());
    }
}
~~~

### Biên dịch và chạy

Từ thư mục chứa pom.xml:

~~~bash
mvn -q compile exec:exec "-Dexec.executable=java" "-Dexec.args=-classpath %classpath com.example.logging.SafeAppenderDemo"
~~~

Exec Plugin khởi chạy **một JVM con** với classpath của dự án. Cách này tránh sự nhầm lẫn với môi trường logging của chính Maven khi chạy ví dụ trong cùng JVM. Các file được tạo dưới target; Maven cần có các dependency đã tải hoặc kết nối kho Maven thích hợp.

**Stdout chính xác của chương trình** với cấu hình trên, không tính các dòng riêng từ Maven hoặc môi trường:

~~~text
recordCount=2
INFO | event=job.started id=job-7
INFO | event=job.finished id=job-7 result=ok
contextStarted=false
~~~

Đây là kết quả đã kiểm thử bằng JDK và Maven trên chương trình tương ứng.

### Đọc kết quả đúng cách

1. **LoggerFactory** trả LoggerContext vì runtime sử dụng Logback Classic. Đây là cast phụ thuộc implementation, có chủ đích trong ví dụ học Logback.
2. **Hai lời gọi logger.info** được phát khi context còn hoạt động. FILE là appender nhận event và ghi text tương ứng.
3. **finally** gọi context.stop() kể cả khi code trong try có exception. Điều này giải phóng tài nguyên của logging context khi luồng thực thi đã đến khối finally.
4. **Files.readAllLines** được thực hiện **sau khi stop** để quan sát nội dung file từ một trạng thái logging đã đóng, thay vì đọc trong lúc appender còn ghi.
5. **recordCount=2** là kết quả của chính dữ liệu demo. Không dùng kết quả này làm khẳng định mọi backend/đích async đều không mất record.
6. **contextStarted=false** cho thấy context đã dừng tại thời điểm kiểm tra. Đây không phải một phép chứng minh file đã được fsync xuống thiết bị lưu trữ bền vững.
7. **System.out.println** được dùng cho báo cáo kết quả demo sau khi logging đã dừng. Trong ứng dụng thật, đừng tiếp tục phát log nghiệp vụ qua Logger đã bị stop.

Vì ví dụ đơn luồng, không có tác vụ tiếp tục tạo record khi context.stop() chạy. Trong service thực tế, **phải kiểm soát các thread/request/job còn đang chạy trước khi dừng Logback**.

## 6. AsyncAppender: nguy cơ mất log khi shutdown

**AsyncAppender** của Logback Classic đặt một queue giữa thread ứng dụng và appender đích. Thread ứng dụng có thể gửi event nhanh hơn đích ghi file/network; worker của AsyncAppender lấy event ra và chuyển cho appender con.

Hệ quả: sau khi gọi logger.info(...), **event có thể mới đang ở queue**, chưa được ghi ra file. Nếu tiến trình thoát trước khi worker xử lý xong, những event cuối có thể bị mất.

Tài liệu Logback nêu rõ: khi dừng/redeploy, **cần stop AsyncAppender**, thường bằng LoggerContext.stop(). Trong quá trình stop, AsyncAppender chờ worker xả queue tối đa theo tham số **maxFlushTime**. Nếu quá thời hạn, event còn lại có thể bị bỏ. Đặt maxFlushTime bằng **0** nghĩa là chờ worker hoàn thành mà không giới hạn thời gian theo cấu hình đó; tuy nhiên có thể làm shutdown treo nếu đích bị kẹt, không phải lời bảo đảm delivery/durability.

### Ví dụ cấu hình AsyncAppender

~~~xml
<configuration>
  <appender name="FILE" class="ch.qos.logback.core.FileAppender">
    <file>target/async-demo.log</file>
    <append>true</append>
    <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
      <charset>UTF-8</charset>
      <pattern>%d{HH:mm:ss.SSS} %-5level %msg%n</pattern>
    </encoder>
  </appender>

  <appender name="ASYNC" class="ch.qos.logback.classic.AsyncAppender">
    <queueSize>512</queueSize>
    <discardingThreshold>0</discardingThreshold>
    <neverBlock>false</neverBlock>
    <maxFlushTime>5000</maxFlushTime>
    <appender-ref ref="FILE"/>
  </appender>

  <root level="INFO">
    <appender-ref ref="ASYNC"/>
  </root>
</configuration>
~~~

**Đây là cấu hình minh họa thay thế**, không dán thêm nguyên khối này vào logback.xml của mục 5 vì sẽ có hai phần tử root. Chương trình ở mục 5 vẫn có thể dùng LoggerContext.stop(), nhưng output khi dùng cấu hình này sẽ **khác** vì timestamp, file name và append=true; không đối chiếu output của mục 5 khi đã thay config.

Ý nghĩa các tham số:

| Thuộc tính | Ý nghĩa | Khi đánh giá shutdown |
| --- | --- | --- |
| **queueSize=512** | Giới hạn số event đợi trong queue | Queue lớn giúp hấp thụ burst nhưng cần thời gian và bộ nhớ để xả |
| **discardingThreshold=0** | Vô hiệu cơ chế tự bỏ những record ưu tiên thấp khi queue gần đầy | Không giải quyết mất event do crash hoặc timeout |
| **neverBlock=false** | Khi queue đầy, đường ghi có thể chờ chỗ trống thay vì bỏ ngay theo chế độ neverBlock | Có thể tạo backpressure lên thread ứng dụng |
| **maxFlushTime=5000** | Chờ tối đa 5.000 ms khi dừng worker để xử lý queue | Event chưa xử lý khi hết hạn có thể bị bỏ |
| **appender-ref FILE** | Đích tiếp nhận event từ worker | Nếu FileAppender lỗi, việc xả queue cũng không bảo đảm lưu đúng |

Trong Logback, AsyncAppender **mặc định có thể loại TRACE/DEBUG/INFO khi queue gần đầy** (ngưỡng liên quan đến dung lượng 80%). Nếu cần giữ thông tin quan trọng, phải hiểu cơ chế **discardingThreshold** và chính sách nghẽn; đừng chỉ tăng maxFlushTime rồi nghĩ mọi event đều được giữ từ trước.

**Cấu hình không có mất mát tuyệt đối** là một mục tiêu rất khác với “đóng appender an toàn”. Khi queue đầy, network lỗi hoặc JVM bị kill, appender có thể mất record dù mã đã gọi logger đúng. Các dữ liệu đòi hỏi không được mất cần thiết kế một **hệ thống ghi nhận bền vững** riêng, không chỉ dựa vào logging queue.

### Vì sao không nên đặt maxFlushTime=0 tùy tiện?

Đặt 0 có thể phù hợp nếu bạn kiểm soát được sink, có giới hạn latency và ưu tiên chờ xả hàng đợi. Nhưng nếu sink bị treo, worker khó hoàn thành và tiến trình có thể không thoát đúng hạn. Trong container, thời gian shutdown grace period của orchestrator thường có giới hạn; hết thời hạn có thể bị buộc dừng.

Do đó phải **cân bằng** giữa lượng event cần xả, thời gian chờ cho phép, khả năng ghi của sink và chính sách vận hành. Có thể đặt timeout hữu hạn, đo thời gian drain thực tế, theo dõi tình huống shutdown có event bị bỏ và điều chỉnh cấu hình theo rủi ro cụ thể.

## 7. Shutdown hook: hữu ích nhưng không phải bảo hiểm tuyệt đối

Logback hỗ trợ shutdown hook trong cấu hình để dừng context khi JVM bắt đầu shutdown bình thường. Ví dụ:

~~~xml
<configuration>
  <shutdownHook/>
  <!-- Các appender, encoder và logger cấu hình như bình thường. -->
</configuration>
~~~

Đoạn trên chỉ minh họa **cách khai báo hook**; cần đặt trong file cấu hình Logback đầy đủ, không dùng nó thay cho toàn bộ root/appender. Tên loại hook và cơ chế có thể khác giữa phiên bản; hãy kiểm tra tài liệu version đang triển khai.

Shutdown hook có ích trong **standalone Java app** khi không có framework quản lý lifecycle riêng. Trong server/webapp, tốt hơn là chọn cơ chế shutdown theo lifecycle phù hợp và xác định rõ ai chịu trách nhiệm stop context.

Giới hạn:
- **SIGKILL**, process crash nặng hoặc tắt nguồn không đảm bảo shutdown hook được chạy.
- Một shutdown hook có thể chạy **đồng thời** với các hook khác. Nếu hook khác vẫn ghi log, thứ tự ngẫu nhiên có thể khiến log cuối bị mất.
- Hook không tự bảo đảm producer đã ngừng hoặc hệ thống bên ngoài đã nhận mọi bytes.
- Shutdown hook dùng cho dọn logging không nên tự phát thêm một chuỗi log phức tạp sau khi appender bị đóng.

**Nguyên tắc:** ưu tiên shutdown có thứ tự trong lifecycle của ứng dụng, dùng hook như cơ chế hỗ trợ khi phù hợp, và thử nghiệm trường hợp ứng dụng ngừng trong tải thực tế.

## 8. So sánh với java.util.logging.Handler.close()

Trong JUL, tên gọi thành phần nhận và xuất record thường là **Handler**, không phải Logback Appender. JUL cung cấp **flush()** và **close()** trong API Handler. Theo Java SE 17, Handler.close thực hiện flush rồi đóng và giải phóng tài nguyên, và **không nên dùng Handler sau khi đã close**.

Với handler do **mã tự tạo và sở hữu**, mẫu an toàn là:

~~~java
// Minh họa: logger và handler thuộc quyền quản lý của đoạn code này.
logger.addHandler(handler);
try {
    logger.info("event=job.finished");
} finally {
    logger.removeHandler(handler);
    handler.close();
}
~~~

Mẫu trên không có nghĩa mọi handler của ứng dụng cần đóng mỗi khi một request kết thúc. Nếu handler dùng chung cho cả service, hãy đóng nó ở **lifecycle kết thúc service**. Không đóng root ConsoleHandler của toàn JVM ngay giữa lúc các module khác còn ghi log.

### Chương trình Java 17 đầy đủ dùng JUL FileHandler

Chương trình sau chỉ dùng JDK, tạo file tạm, ghi một bản ghi, gỡ handler khỏi logger, close handler rồi mới đọc lại và xóa file.

Tạo tệp **JulHandlerCloseDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class JulHandlerCloseDemo {
    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("jul-close-", ".log");
        Logger logger = Logger.getLogger("demo.jul.close");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        FileHandler handler = new FileHandler(path.toString(), false);
        handler.setEncoding("UTF-8");
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " | "
                        + formatMessage(record) + System.lineSeparator();
            }
        });
        logger.addHandler(handler);
        try {
            logger.info("event=job.finished id=job-7");
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }

        List<String> lines = Files.readAllLines(path, StandardCharsets.UTF_8);
        System.out.println("recordCount=" + lines.size());
        for (String line : lines) {
            System.out.println(line);
        }
        Files.deleteIfExists(path);
    }
}
~~~

Chạy:

~~~bash
javac JulHandlerCloseDemo.java
java JulHandlerCloseDemo
~~~

**Stdout chính xác**:

~~~text
recordCount=1
INFO | event=job.finished id=job-7
~~~

Ví dụ đã được chạy thử trên JDK. Phần close giúp giải phóng stream/lock của FileHandler trước khi xóa file, điều đặc biệt quan trọng với hệ điều hành có cơ chế giữ file đang mở. FileHandler có cơ chế mặc định về formatter khác custom formatter của demo, nên output này chỉ đúng với cấu hình code hiển thị.

**Không suy ra JUL Handler.close() đồng nghĩa LoggerContext.stop().** Một phương thức đóng **một handler** do bạn sở hữu; phương thức kia quản lý **cả logging context** và các appender Logback liên quan. Nếu code dùng SLF4J với backend Logback, việc đóng JUL Handler không giúp stop các appender Logback.

## 9. FileAppender, RollingFileAppender và tài nguyên đi kèm

Với **FileAppender**, những vấn đề shutdown cần kiểm tra gồm file descriptor, file lock, dữ liệu đang đệm, charset/encoder và quyền ghi. Với **RollingFileAppender**, còn có rotation policy, file archive và công việc hậu xử lý như nén file; các tác vụ phụ có thể cần thời gian để kết thúc.

**Dừng context** thường là lựa chọn phù hợp khi ứng dụng sở hữu toàn bộ context, thay vì dò từng appender để đóng thủ công. Tuy nhiên, đừng khẳng định tất cả công việc phụ thuộc bên ngoài đã hoàn tất nếu không có tín hiệu xác nhận tương ứng.

Một số lỗi về file:
- **Không gọi stop trước exit** khiến file bị giữ mở lâu hơn dự kiến hoặc mất record cuối trong cấu hình có buffer/async.
- **Đổi file path khi appender còn hoạt động** không tương đương một thao tác đóng/mở an toàn; cần tuân theo lifecycle/reconfiguration của backend.
- **Đóng một appender dùng chung giữa nhiều logger** làm logger khác mất output.
- **Append=false ở production** có thể xóa dữ liệu log cũ mỗi lần khởi động; chỉ dùng khi muốn thay nội dung có chủ đích như demo.
- **Không kiểm soát disk/permission** có thể dẫn đến logging error ngay cả khi shutdown đúng trình tự.
- **Giả định console luôn lưu bền vững** là sai: stdout/stderr thường đi qua runtime/container/collector với chính sách riêng.

Khi thu log bằng sidecar hoặc agent, còn phải xét thứ tự shutdown giữa **ứng dụng phát log** và **collector nhận log**. Nếu collector đã ngừng trước khi ứng dụng xả xong, các log cuối có thể không tới nơi lưu trữ trung tâm.

## 10. Reconfiguration và redeploy

Trong hệ thống chạy lâu dài, logging config có thể được thay đổi trong lúc app đang chạy hoặc ứng dụng được redeploy. Đây là nơi lỗi “đóng appender an toàn” có thể phát sinh dù tiến trình không tắt hoàn toàn.

Những điều cần kiểm tra:
1. **Ai được quyền cấu hình lại logger context?** Tránh hai phần mềm đồng thời thêm/xóa appender không có phối hợp.
2. **Producer nào đang chạy?** Không stop appender nhận event từ thread khác khi chưa có cơ chế thay đổi an toàn.
3. **Appender cũ được stop đúng không?** Nếu chỉ tạo file/appender mới mà không dừng instance cũ, có thể giữ file descriptor và thread.
4. **Appender mới đã start hợp lệ chưa?** Nếu sink không mở được, việc đổi từ appender cũ sang mới có thể khiến toàn bộ log mất.
5. **Log trong khoảng chuyển tiếp đi đâu?** Phải hiểu hành vi implementation khi thay cấu hình, không mặc định không rơi event.
6. **Có dùng chung file giữa hai context/process không?** Việc nhiều tiến trình tranh cùng file/rotation không nên được coi là an toàn chỉ vì mỗi appender gọi stop.

Logback có các cơ chế reconfiguration riêng. Bài này không khuyến khích tự gọi reset()/stop()/start() tùy tiện trên context production: một thay đổi cấu hình cần được điều phối theo lifecycle của ứng dụng và kiểm thử bằng tải phù hợp.

## 11. Graceful shutdown trong server, job runner và container

### HTTP server

Server thường cần **ngừng tiếp nhận request mới** rồi để những request đang xử lý hoàn tất trong khoảng thời gian cho phép. Khi không còn job nghiệp vụ, mới phát log tổng kết và dừng logging system.

Nếu bạn gọi LoggerContext.stop() trong một request handler, những request song song vẫn đang chạy có thể mất log; vì thế stop context phải thuộc callback shutdown của **toàn ứng dụng** hoặc chủ sở hữu logging tương ứng.

### Executor hoặc background worker

Với thread pool, shutdown có thể là:
1. Ngừng submit task mới.
2. Gọi executor.shutdown() để ngừng nhận task mới.
3. Chờ các task đang chạy bằng awaitTermination với timeout được kiểm soát.
4. Nếu hết thời hạn, quyết định chính sách cancel/force shutdown và ghi nhận kết quả **trước khi dừng logging**.
5. Dừng LoggerContext sau khi worker không còn cần xuất log.

Mẫu thao tác:

~~~java
// Minh họa; executor và logger được tạo/quản lý ở chỗ khác.
executor.shutdown();
if (!executor.awaitTermination(10, java.util.concurrent.TimeUnit.SECONDS)) {
    logger.warn("event=workers.shutdown_timeout");
    executor.shutdownNow();
}
// Chỉ stop logging sau khi đã xử lý/kiểm soát các worker còn phát log.
~~~

**Cảnh báo:** gọi shutdownNow() gửi yêu cầu interrupt chứ không đảm bảo mọi task đã dừng ngay. Nếu task bỏ qua interrupt, vẫn có thể tạo event sau đó. Cần có chính sách chờ/hủy hoàn chỉnh thay vì coi shutdownNow là barrier hoàn tất.

### Container/orchestrator

Một container có thể nhận tín hiệu dừng rồi chỉ được phép có một khoảng thời gian để kết thúc. Cần phân bổ thời gian cho **drain request, đóng dependency, xả async queue và đóng logging**. Nếu dùng maxFlushTime quá lớn nhưng grace period quá ngắn, tiến trình có thể bị kill trước khi stop hoàn tất.

Ngược lại, đặt maxFlushTime quá nhỏ có thể khiến queue còn nhiều record bị bỏ khi shutdown. Hãy đo thông lượng sink và thử nghiệm bằng tải xấu nhất phù hợp, không lấy duy nhất lần chạy local yên tĩnh làm tiêu chuẩn.

## 12. Đóng đúng vẫn không bảo đảm lưu mọi log

Cần phân biệt các tầng bảo đảm:

~~~text
logger.info(...) được gọi
    ↓
Level/filter chấp nhận record
    ↓
Appender/AsyncAppender nhận record
    ↓
Queue drain và encoder sinh bytes
    ↓
OutputStream/OS nhận bytes
    ↓
File được flush / network gửi đi
    ↓
Collector tiếp nhận
    ↓
Backend lưu/index và có thể truy vấn
~~~

Mỗi mũi tên có thể bị ảnh hưởng bởi lỗi, timeout, filter, sampling, queue hoặc chính sách của hệ thống tiếp nhận. **Gọi stop an toàn chỉ giải quyết một phần vòng đời ở phía producer/backend hiện tại.**

Một số tình huống không có bảo đảm mất mát bằng 0:
- JVM crash, bị SIGKILL, mất điện hoặc hết bộ nhớ nghiêm trọng.
- Queue AsyncAppender đã bỏ record khi đầy hoặc ưu tiên drop mức log thấp.
- Worker chưa xả hết queue trước maxFlushTime.
- File/đĩa hết dung lượng, thay đổi permission hoặc backend bị lỗi.
- Network collector ngắt kết nối, mất acknowledgment hoặc nhận xong nhưng chưa lưu bền vững.
- Logger/Handler/Filter không cho record đi qua ngay từ đầu.
- File rotation hoặc retention khiến record cũ không còn ở vị trí đang tra cứu.

Với dữ liệu bắt buộc phải lưu theo hợp đồng nghiệp vụ (ví dụ xác nhận giao dịch, audit theo yêu cầu quản trị), không nên dùng log chẩn đoán làm nguồn sự thật duy nhất. Cần cơ chế lưu bền vững/transaction/outbox hoặc audit service chuyên dụng tùy mức bảo đảm yêu cầu.

## 13. Kiểm thử shutdown và tiêu chí nghiệm thu

Bài thực hành ở mục 5 cho thấy một trường hợp **synchronous FileAppender** có hai record được ghi đúng, context được stop và file đọc lại được. Đó là kiểm thử cơ sở; hệ thống thực cần thêm các kịch bản tải và lỗi.

Một kế hoạch QA gợi ý:

| Kịch bản | Cách kiểm tra | Điều cần đánh giá |
| --- | --- | --- |
| Shutdown bình thường | Đưa server vào trạng thái stopping, hết request rồi stop context | Log cuối có xuất trước khi stop, không có logger còn dùng sau stop |
| Shutdown khi có tải | Nhiều request/thread ghi cùng lúc | Producer đã thực sự ngừng trước khi logging context đóng |
| Async queue gần đầy | Tạo lưu lượng vượt tốc độ sink có kiểm soát | Có drop, blocking, time-to-drain và trạng thái pending |
| Sink chậm | Mô phỏng file/network chậm | maxFlushTime và grace period có phù hợp |
| Không có quyền ghi | Tạo môi trường thiếu quyền file tạm | Backend có báo lỗi/StatusManager phù hợp và ứng dụng phản ứng thế nào |
| Runtime bị buộc dừng | Mô phỏng kill cưỡng bức trong môi trường thử nghiệm | Ghi nhận giới hạn, không quảng bá đảm bảo zero-loss |
| Redeploy hoặc đổi config | Khởi động appender mới, stop cái cũ theo lifecycle | Không leak thread/descriptor, không ghi trùng |
| JUL Handler close | Ghi file rồi close và đọc/xóa file | Không giữ lock, không phát tiếp trên handler đã đóng |

**Đếm record đúng đơn vị.** Một Throwable có thể tạo nhiều dòng stack trace trong text log; đừng đếm mỗi dòng là một event. Với log async, so số event đã được **backend chấp nhận** và số event ở đích khi có cơ chế theo dõi phù hợp; không chỉ đếm số lần gọi logger nếu một số lần bị level/filter loại.

**Không kiểm thử bằng cách cố tình làm hỏng dữ liệu sản xuất.** Dùng tệp tạm, dữ liệu giả, môi trường thử nghiệm và giới hạn số record/time window khi kiểm tra tác động của shutdown.

## 14. Sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách làm phù hợp |
| --- | --- | --- |
| Gọi stop() ngay khi nhận SIGTERM | Request/worker còn chạy và ghi log sau khi đóng | Drain producer trước rồi stop logging |
| Gọi logger.info sau context.stop() | Record không còn đích đáng tin để xuất | Phát log kết thúc trước stop |
| Không stop AsyncAppender | Queue/worker chưa hoàn tất trước khi JVM thoát | Dừng qua LoggerContext.stop() hoặc lifecycle appender được quản lý |
| Nghĩ logger.info trả về là log đã đến collector | Async queue, I/O và network còn xử lý | Phân biệt acceptance với delivery/durability |
| Đặt maxFlushTime=0 cho mọi service | Shutdown có thể treo vô hạn ở sink chậm | Chọn timeout theo grace period và đánh giá rủi ro |
| Dùng neverBlock=true nhưng yêu cầu không mất event | Queue đầy có thể bỏ event | Chọn chính sách backpressure/sink thích hợp |
| Chỉ tăng maxFlushTime để chống mất log | Event có thể đã bị drop do discardingThreshold | Kiểm tra cả chính sách queue, filter, sink và shutdown |
| Đóng appender chia sẻ giữa request | Các request khác mất log | Quản lý ở cấp ứng dụng/context |
| Dùng FileAppender append=false cho file cần lưu | Ghi đè/truncate file từ lần trước | Chọn append/rolling policy rõ ràng |
| Nghĩ JUL Handler.close giống Logback Appender.stop | Khác API và khác phạm vi lifecycle | Dùng đúng cơ chế từng backend |
| Dùng thử-catch rồi bỏ qua lỗi đóng | Không biết resource có đóng hoặc log bị mất | Quan sát lỗi/status và thiết kế fallback phù hợp |
| Cho collector dừng trước producer | Log cuối không được thu | Điều phối shutdown toàn pipeline khi có thể |
| Dùng log cho audit bắt buộc phải bền vững | Logging không đảm bảo transaction/ack cuối | Dùng lưu trữ/audit chuyên dụng |

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao không được gọi LoggerContext.stop() khi request vẫn đang xử lý?

**Đáp án:** Những request còn chạy có thể tiếp tục ghi log nhưng appender đã dừng, gây thiếu record. Cần dừng nhận việc và quản lý tác vụ đang chạy trước.

**Câu 2.** AsyncAppender nhận một event rồi logger.info trả về. Event đã chắc chắn có trong file chưa?

**Đáp án:** Chưa. Event có thể còn trong queue hoặc đang chờ worker và appender đích.

**Câu 3.** maxFlushTime=5000 có nghĩa gì?

**Đáp án:** Khi stop AsyncAppender, worker có thời hạn chờ xả queue tối đa khoảng 5.000 ms theo cấu hình; nếu không hoàn tất, record chưa xử lý có thể bị bỏ.

**Câu 4.** Đặt maxFlushTime=0 có thể gây tác dụng phụ nào?

**Đáp án:** Không giới hạn thời gian chờ worker xả queue; nếu sink treo, shutdown có thể kéo dài rất lâu hoặc bị orchestrator buộc dừng.

**Câu 5.** Vì sao phải kiểm tra discardingThreshold và neverBlock bên cạnh maxFlushTime?

**Đáp án:** Vì record có thể đã bị bỏ khi queue gần đầy hoặc đầy trong lúc ứng dụng chạy; thời gian chờ lúc shutdown không thể phục hồi dữ liệu đã bị drop.

**Câu 6.** Trong ví dụ Logback, vì sao đọc file sau context.stop()?

**Đáp án:** Vì chương trình muốn đọc file sau khi appender đã đóng theo lifecycle. Kết quả kiểm thử dễ hiểu và ít chịu ảnh hưởng trạng thái file đang mở hơn.

**Câu 7.** Phương thức tương đương về ý tưởng giải phóng resource ở JUL là gì?

**Đáp án:** Handler.close(), sau khi dừng producer liên quan và gỡ Handler khỏi Logger nếu ta trực tiếp sở hữu handler. Đây không phải API giống hệt LoggerContext.stop().

**Câu 8.** Vì sao shutdown hook không bảo đảm chạy khi máy bị mất điện hoặc process bị SIGKILL?

**Đáp án:** Những tình huống này có thể không cho JVM thực thi trình tự shutdown bình thường.

**Câu 9.** Stop context thành công có bảo đảm log đã được backend trung tâm lưu bền vững không?

**Đáp án:** Không. Còn những tầng OS, network, collector, queue của dịch vụ ngoài và chính sách persistence khác.

**Câu 10.** Với backend SLF4J khác Logback, có được cast ILoggerFactory sang LoggerContext rồi stop không?

**Đáp án:** Không. Đây là API riêng của Logback. Cần xác định backend thực tế và để thành phần sở hữu lifecycle thực thi shutdown phù hợp.

## 16. Tài liệu tham khảo

- [Logback Manual — Configuration: Stopping logback-classic](https://logback.qos.ch/manual/configuration.html): dừng LoggerContext, quản lý appender và shutdown hook.
- [Logback Manual — AsyncAppender](https://logback.qos.ch/manual/appenders-async-sift.html): queue, drop policy, neverBlock, maxFlushTime và dừng worker.
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html): cơ chế start/stop và doAppend.
- [Oracle Java SE 17 — java.util.logging.Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html): flush(), close() và vòng đời Handler.
- [Oracle Java SE 17 — java.util.logging.FileHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html): file output, rotation và close().

## Ghi nhớ

**Đóng appender an toàn không phải chỉ gọi một phương thức ở cuối main.** Hãy xác định ai sở hữu logging lifecycle, dừng các luồng phát log trước, ghi các bản ghi kết thúc khi logging còn hoạt động, sau đó stop Logback LoggerContext hoặc close JUL Handler đúng phạm vi. Với AsyncAppender, phải đánh giá queue, chính sách drop/block và thời hạn xả; ngay cả shutdown sạch vẫn không tự bảo đảm delivery hoặc durability ở hệ thống ngoài. Mục tiêu của logging shutdown là **giải phóng tài nguyên đúng cách, giảm rủi ro mất record và nói rõ những giới hạn còn lại**.
