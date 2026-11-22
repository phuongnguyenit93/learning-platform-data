# Facade khác backend trong Java Logging

## Mục tiêu và phạm vi

Trong Java, những tên như **SLF4J, Logback, Log4j 2** và **java.util.logging (JUL)** thường xuất hiện cùng nhau. Người mới học dễ nghĩ tất cả đều là cùng một loại thư viện ghi log. Thực tế, **logging facade** và **logging backend** có trách nhiệm khác nhau, và có những thư viện vừa cung cấp API vừa có cơ chế thực thi riêng.

Bài này tập trung trực tiếp vào **“Facade khác backend”** trong nhóm **“Facade và backend”** của Java Core Logging. Sau khi học, bạn có thể:

- Giải thích **facade là lớp API/abstraction mà code gọi**, còn **backend/provider là phần xử lý và đưa record ra các đích**.
- Vẽ được đường đi từ mã Java dùng SLF4J qua provider đến Logback, Log4j 2 hoặc JUL.
- Hiểu vì sao thư viện Java nên phụ thuộc vào **SLF4J API** thay vì ép ứng dụng sử dụng một backend cụ thể.
- Phân biệt **provider**, **binding** của đời cũ, **bridge/adapter** và **Appender/Handler**; tránh cấu hình chuyển tiếp vòng lặp.
- Xử lý tình huống **không có provider, nhiều provider, không khớp phiên bản, cấp độ log sai hoặc định dạng không như kỳ vọng**.
- Chạy cùng một chương trình **Java 17** với hai backend **Logback** và **slf4j-simple**, chỉ thay profile Maven, để tự quan sát sự khác biệt.

Ví dụ sử dụng **SLF4J 2.0.x**, tức thế hệ dùng cơ chế **ServiceLoader tìm provider**. Những ví dụ phiên bản Maven được chọn để bài thực hành có tính tái lập, không phải lời khẳng định đó là bản phát hành mới nhất.

## 1. Facade là gì?

**Facade** trong logging là **API ổn định ở phía mã ứng dụng/thư viện**. Code của bạn gọi những phương thức như:

~~~java
// Minh họa: LOG là org.slf4j.Logger được khai báo trước.
LOG.info("event=order.created orderId={}", "OD-42");
LOG.warn("event=payment.retry attempt={}", 2);
~~~

Ở đây mã đang gọi giao diện **org.slf4j.Logger** (nếu sử dụng SLF4J). Nó diễn đạt **muốn ghi thông tin gì** và **mức độ nào**, nhưng không trực tiếp chỉ định file, format, chính sách rotation hoặc cách gửi log đi đâu.

Facade có ích vì làm giảm phụ thuộc của mã nghiệp vụ vào một framework logging cụ thể. Thay vì từng thư viện tự quyết định Logback hay Log4j 2, chúng có thể phát log qua SLF4J và để **ứng dụng cuối cùng** quyết định nơi xuất.

**SLF4J** là viết tắt của *Simple Logging Facade for Java*. Nó cung cấp API như Logger, LoggerFactory, MDC, Marker và khả năng logging có tham số; SLF4J 2 còn hỗ trợ fluent logging API. SLF4J **không tự là một pipeline logging đầy đủ** nếu không có provider thích hợp.

Đừng hiểu “facade” nghĩa là có phép màu bảo đảm mọi backend giống hệt nhau. API gọi có thể giữ nguyên, nhưng format, level mặc định, MDC, khả năng structured logging, hiệu năng và policy vẫn phụ thuộc backend.

## 2. Backend là gì?

**Backend** (cũng thường gọi logging implementation) là thành phần **thực thi việc xử lý log**. Nó cung cấp các cơ chế như:

- Xác định record nào được bật theo level, logger và filter.
- Nhận sự kiện, xử lý ngữ cảnh, exception và thông tin thời gian.
- Định dạng/encode record thành text hoặc cấu trúc phù hợp.
- Đưa dữ liệu tới console, file hoặc các đích khác qua **Appender/Handler**.
- Quản lý rolling file, flush, async queue, lifecycle và những cấu hình liên quan.
- Tích hợp với công cụ thu thập và giám sát nếu triển khai phù hợp.

Các ví dụ backend và provider thông dụng:

| Công nghệ | Vai trò khi dùng với SLF4J | Ghi chú |
| --- | --- | --- |
| **Logback Classic** | Backend thực thi SLF4J trực tiếp, đồng thời làm provider SLF4J | Có LoggerContext, appender, encoder, logback.xml |
| **Log4j 2 Core + adapter SLF4J** | Backend Log4j 2, với provider chuyển API SLF4J tới Log4j 2 | Với SLF4J 2 dùng artifact log4j-slf4j2-impl |
| **java.util.logging** | Hệ logging chuẩn JDK có Logger, Handler, Formatter; có thể nhận log SLF4J qua slf4j-jdk14 | JUL cũng có API riêng, không phải bản sao của SLF4J |
| **slf4j-simple** | Provider/implementation gọn nhẹ cho ứng dụng nhỏ | Hỗ trợ tùy chỉnh cơ bản, không có mọi khả năng của Logback |
| **slf4j-nop** | Provider không phát log ra đích | Có chủ đích khi muốn bỏ toàn bộ output |
| **Không có provider** | SLF4J 2 cảnh báo rồi mặc định dùng NOP | Log có thể “im lặng” dù code gọi LOGGER |

**Khác biệt cốt lõi:** Facade định nghĩa **cách code yêu cầu ghi log**; backend quyết định **cách yêu cầu đó được thực thi**. Một backend có thể có API logging riêng, nhưng khi được dùng qua SLF4J, lớp facade giúp code nghiệp vụ không phụ thuộc trực tiếp API của backend.

## 3. Luồng đi của một dòng log

Với SLF4J và Logback:

~~~mermaid
flowchart LR
    A["Java business code"] --> B["SLF4J Logger API"]
    B --> C["SLF4J provider"]
    C --> D["Logback Classic"]
    D --> E["Logger level / Filter"]
    E --> F["Appender + Encoder/Layout"]
    F --> G["Console, file..."]
~~~

Với Log4j 2 thay cho Logback, đầu đường đi vẫn là **org.slf4j.Logger**, nhưng provider/adapter chuyển sự kiện sang **Log4j 2** và các chính sách appender/layout của Log4j 2. Đó là **hai triển khai khác nhau bên dưới cùng một API**.

Một lần gọi:

~~~java
LOG.info("event=order.created orderId={}", "OD-42");
~~~

có thể tạo ra những output khác nhau:

~~~text
INFO | event=order.created orderId=OD-42
~~~

hoặc:

~~~text
2026-11-09 10:15:30.123 INFO com.example.OrderService - event=order.created orderId=OD-42
~~~

Đây là **ví dụ định dạng minh họa**. Timestamp, logger name, khoảng trắng và nơi xuất phụ thuộc backend/config. Không thể suy ra format duy nhất chỉ từ lời gọi SLF4J.

Một điều quan trọng: **Appender/Handler không phải facade**. Chúng nằm trong backend hoặc hệ logging đích, phụ trách xuất/định tuyến record. SLF4J Logger cũng không chính là Logger của JUL hay Logback Classic dù chúng có thể được nối qua provider.

## 4. So sánh trách nhiệm bằng bảng

| Câu hỏi | Facade (ví dụ SLF4J) | Backend (ví dụ Logback) |
| --- | --- | --- |
| Code gọi phương thức nào? | Cung cấp org.slf4j.Logger.info/debug/warn/error | Triển khai cách xử lý lời gọi |
| Code có phải import Logback không? | Không, chỉ dùng org.slf4j.* | Không cần trong business code nếu dùng SLF4J |
| Ai xác định đích console/file? | Thường không; SLF4J không quy định FileAppender | Backend cấu hình appender/handler |
| Ai quyết định layout/encoder? | Không quy định một layout chung cho mọi backend | Backend quyết định formatter, encoder, pattern |
| Ai quyết định level nào được xuất? | API cung cấp level và kiểm tra isEnabled | Backend cung cấp cấu hình effective level/filter thực tế |
| Ai cung cấp MDC API? | SLF4J có org.slf4j.MDC | Cách lưu/truyền/render MDC phụ thuộc provider/backend |
| Có thể đổi backend mà giữ source Java? | Thường có thể, nếu code chỉ dùng API chung | Có thể cần thay dependencies và cấu hình |
| Thiếu backend thì sao? | SLF4J 2 phát cảnh báo, dùng NOP mặc định | Không có backend thật để xuất record |
| Công cụ vận hành cấu hình ở đâu? | Không có file layout chung do SLF4J quy định | logback.xml, log4j2.xml, logging.properties... |

**Giữ nguyên source không có nghĩa giữ nguyên output.** Một đoạn Java vẫn biên dịch với SLF4J nhưng khi thay provider, kết quả có thể khác về format, cấp độ được xuất, timestamp, MDC, exception, hiệu năng hoặc phương thức xuất.

## 5. Tại sao thư viện và ứng dụng có thể chọn phụ thuộc khác nhau?

### Thư viện Java tái sử dụng

Nếu viết thư viện như payment-client.jar, bạn thường không biết ứng dụng sử dụng thư viện đó đang chạy Logback hay Log4j 2. Một thư viện nên phụ thuộc vào **slf4j-api** và để ứng dụng chủ quyết định provider cuối cùng.

Ví dụ thư viện viết:

~~~java
// Đoạn minh họa trong lớp của thư viện.
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(PaymentClient.class);
~~~

Nó chỉ import SLF4J API, không bắt người dùng cài Logback. Nếu thư viện tự khai báo một provider runtime không cần thiết, nó có thể vô tình tạo **nhiều provider** khi ứng dụng chủ đã có provider riêng.

### Ứng dụng thực thi

Ứng dụng cuối cùng thường cần cả **facade API** (trực tiếp hoặc bắc cầu qua dependency) **và một provider/backend tương thích** để log thực sự được xuất. Ứng dụng cũng sở hữu chính sách logging: output, format, retention, rotation và quyền truy cập.

**Thiết kế hợp lý:** source nghiệp vụ chỉ dùng SLF4J, còn POM/runtime chọn một backend và file cấu hình tương ứng. Nếu đổi backend, tránh import trực tiếp các lớp cụ thể như ch.qos.logback.classic.Logger vào business logic trừ khi có nhu cầu rõ ràng và chấp nhận bị phụ thuộc backend.

## 6. Provider trong SLF4J 2 khác binding đời cũ thế nào?

Với **SLF4J 2.x**, SLF4J API tìm **SLF4JServiceProvider** bằng cơ chế **ServiceLoader** khi khởi tạo LoggerFactory. Các JAR provider như **logback-classic**, **slf4j-simple**, **slf4j-jdk14** hoặc adapter Log4j 2 cung cấp implementation phù hợp.

Ở **SLF4J 1.7.x trở về trước**, nhiều tài liệu nói đến **binding** và lớp **StaticLoggerBinder**. SLF4J 2.x **không dùng cơ chế StaticLoggerBinder đời cũ để chọn backend**. Vì thế không thể tùy tiện trộn một phiên bản API 2.x với binding 1.7.x và kỳ vọng hoạt động.

Ba trường hợp cần nhớ:

1. **Có đúng một provider tương thích:** ứng dụng có thể ghi log qua implementation đó.
2. **Không có provider:** SLF4J thường cảnh báo **No SLF4J providers were found** và dùng **NOP**. Những lời gọi log có thể chạy mà không in gì; đây không phải chứng minh business code không thực thi.
3. **Có nhiều provider:** SLF4J có thể cảnh báo về multiple providers và sử dụng một provider được phát hiện. **Không dựa vào thứ tự tình cờ trên classpath để lựa chọn backend.** Hãy loại bỏ provider dư để có một lựa chọn rõ ràng.

Bản API và provider cần phù hợp về dòng phiên bản. Ví dụ, một dự án dùng SLF4J API 2.0.x nên đi với provider hỗ trợ SLF4J 2.0.x, không dùng binding cũ chỉ dành cho 1.7.x.

## 7. Thực hành Java 17: cùng code, đổi Logback và slf4j-simple

Bài thực hành dùng **Maven**, **Java 17+**, **SLF4J API 2.0.17**, **Logback Classic 1.5.18** và **slf4j-simple 2.0.17**. Hai backend được khai báo trong hai Maven profile **loại trừ nhau về lựa chọn**, trong khi code Java không thay đổi.

Các phiên bản này là **bộ phiên bản cố định của bài học**, được thử nghiệm cùng nhau, không phải thông tin bản mới nhất của các dự án. Chạy lệnh Maven sẽ cần truy cập kho dependency hoặc cache đã có sẵn. Các ví dụ không tự chạy với javac trần vì code import org.slf4j.*, một thư viện ngoài JDK.

### Cấu trúc thư mục

~~~text
facade-backend-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/
        │       └── example/
        │           └── logging/
        │               └── FacadeBackendDemo.java
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
  <artifactId>facade-backend-demo</artifactId>
  <version>1.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.slf4j</groupId>
      <artifactId>slf4j-api</artifactId>
      <version>2.0.17</version>
    </dependency>
  </dependencies>

  <profiles>
    <profile>
      <id>logback</id>
      <activation>
        <activeByDefault>true</activeByDefault>
      </activation>
      <dependencies>
        <dependency>
          <groupId>ch.qos.logback</groupId>
          <artifactId>logback-classic</artifactId>
          <version>1.5.18</version>
        </dependency>
      </dependencies>
    </profile>

    <profile>
      <id>simple</id>
      <dependencies>
        <dependency>
          <groupId>org.slf4j</groupId>
          <artifactId>slf4j-simple</artifactId>
          <version>2.0.17</version>
        </dependency>
      </dependencies>
    </profile>
  </profiles>

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

Phần **dependencies** chung chỉ khai báo **slf4j-api** cho code. Profile **logback** mang **logback-classic** làm provider và các dependency transitive cần thiết; profile **simple** dùng provider slf4j-simple. Đối với Maven, khi bạn kích hoạt rõ ràng profile **simple** thì profile mặc định **logback** có activeByDefault không được kích hoạt cùng chỉ vì ở chung POM. Hai lệnh phía dưới cũng dùng **-Plogback** và **-Psimple** để chỉ rõ lựa chọn.

Đây là POM phục vụ mục đích học, không phải quy tắc bắt buộc cho cấu trúc build production. Dự án thực thường quản lý phiên bản qua BOM hoặc dependencyManagement; cần kiểm tra dependency tree để không bị kéo thêm provider ngoài ý muốn.

### File src/main/resources/logback.xml

~~~xml
<configuration>
  <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
    <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
      <charset>UTF-8</charset>
      <pattern>%level | requestId=%X{requestId:-none} | %msg%n</pattern>
    </encoder>
  </appender>

  <root level="DEBUG">
    <appender-ref ref="CONSOLE"/>
  </root>
</configuration>
~~~

Logback dùng file này để xuất ra console với pattern **level | requestId | message**. Level DEBUG cho phép INFO, DEBUG và WARN. **%X{requestId:-none}** lấy giá trị từ MDC; **%msg** hiển thị message đã thay placeholder; **%n** thêm xuống dòng.

Khi dùng profile **simple**, không có Logback provider nên file **logback.xml không điều khiển slf4j-simple**. Đây chính là một biểu hiện của sự khác nhau giữa facade và backend: code Java giữ nguyên nhưng hệ thống cấu hình được backend hiểu lại khác.

### File src/main/java/com/example/logging/FacadeBackendDemo.java

~~~java
package com.example.logging;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public class FacadeBackendDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(FacadeBackendDemo.class);

    public static void main(String[] args) {
        MDC.put("requestId", "req-7");
        try {
            LOG.info("event=request.started backend={}",
                    LoggerFactory.getILoggerFactory()
                            .getClass().getSimpleName());
            LOG.debug("event=branch.selected branch={}", "cache-miss");
            LOG.warn("event=dependency.retry attempt={}", 2);
            LOG.info("event=request.finished status={}", 200);
        } finally {
            MDC.remove("requestId");
        }
    }
}
~~~

Các **import duy nhất để phát log trong business code đều thuộc org.slf4j**. Không có import của Logback hoặc slf4j-simple. **LoggerFactory.getILoggerFactory().getClass().getSimpleName()** được dùng trong demo để in loại LoggerFactory backend đang được chọn; trong business code bình thường, không cần kiểm tra factory ở mỗi request.

**MDC.put** gắn requestId vào context hiện tại, và **MDC.remove** dọn trong finally. MDC có API chung nhưng việc backend lưu, hiển thị hoặc hỗ trợ MDC không hoàn toàn giống nhau. Trong ứng dụng có thread pool/async, cần truyền và dọn context đúng vòng đời, không mặc định context tự đi qua mọi task.

### Lần chạy A: Logback backend

Trong thư mục dự án, chạy bằng Maven:

~~~bash
mvn -q -Plogback compile exec:exec "-Dexec.executable=java" "-Dexec.args=-classpath %classpath com.example.logging.FacadeBackendDemo"
~~~

**Bốn dòng log của ứng dụng**, theo đúng thứ tự, không tính dòng riêng có thể xuất từ Maven:

~~~text
INFO | requestId=req-7 | event=request.started backend=LoggerContext
DEBUG | requestId=req-7 | event=branch.selected branch=cache-miss
WARN | requestId=req-7 | event=dependency.retry attempt=2
INFO | requestId=req-7 | event=request.finished status=200
~~~

Logback chọn **LoggerContext** làm LoggerFactory. Vì root Logback đặt DEBUG và có pattern lấy MDC, ta thấy cả dòng DEBUG lẫn requestId.

Ở đây dùng **exec:exec** với **exec.executable=java** để chạy JVM con; token **%classpath** được Maven Exec Plugin thay bằng classpath của dự án. Cách chạy này làm cho việc lựa chọn provider được kiểm tra trong **JVM riêng**, tránh tình huống plugin chạy trong cùng JVM với Maven và backend đã được chọn từ trước. Cú pháp với tham số được đặt trong dấu nháy chạy được với PowerShell/Bash khi dùng Maven phù hợp.

### Lần chạy B: đổi sang slf4j-simple, giữ nguyên mã nguồn

Chạy:

~~~bash
mvn -q -Psimple compile exec:exec "-Dexec.executable=java" "-Dexec.args=-classpath %classpath com.example.logging.FacadeBackendDemo"
~~~

Trong cấu hình mặc định của **slf4j-simple** ở bộ phiên bản bài học, ba dòng log của ứng dụng là:

~~~text
[main] INFO com.example.logging.FacadeBackendDemo - event=request.started backend=SimpleLoggerFactory
[main] WARN com.example.logging.FacadeBackendDemo - event=dependency.retry attempt=2
[main] INFO com.example.logging.FacadeBackendDemo - event=request.finished status=200
~~~

Dòng **DEBUG không hiển thị** vì mức mặc định của simple backend thường là INFO, trong khi Logback ở lần A được cấu hình root DEBUG. Pattern output cũng khác: simple dùng định dạng nội bộ có thread/level/logger, và không đọc file logback.xml để in **requestId=...** như Logback.

**Điểm quan trọng:** Cùng file FacadeBackendDemo.java và cùng các lời gọi LOG.info/debug/warn, nhưng số dòng, format, mức được in và khả năng thể hiện MDC khác nhau. Đó là bằng chứng trực tiếp cho việc **facade giữ API thống nhất, backend quyết định hành vi logging**.

Hai lệnh đã được thử với JDK/Maven và các phiên bản dependency nêu trong ví dụ. Nếu môi trường bạn dùng có cấu hình simpleLogger riêng, thiết lập logging qua biến hệ thống khác hoặc bị framework ghi đè, output có thể thay đổi; hãy xác nhận provider thực tế trước khi so sánh.

### Giải thích sâu kết quả

1. **Facade không tự viết ra console:** LOG là SLF4J Logger, còn Logback/slf4j-simple thực hiện chính sách ghi.
2. **LoggerFactory giúp phát hiện backend:** LoggerContext ứng với Logback Classic; SimpleLoggerFactory ứng với simple provider trong ví dụ.
3. **Không có thay đổi code Java:** thao tác đổi diễn ra trong Maven profile, không phải sửa LOG.info hoặc thay import.
4. **Mỗi backend có định dạng riêng:** Logback đọc logback.xml và PatternLayoutEncoder; simple bỏ qua file này.
5. **Level khác nhau do cấu hình:** Logback DEBUG xuất đủ 4 dòng, simple INFO chỉ xuất 3 dòng.
6. **MDC phụ thuộc backend:** SLF4J hỗ trợ API MDC nhưng backend phải có khả năng render theo cấu hình; đừng giả định mọi backend tự thêm requestId vào output.
7. **Không dùng dòng số lượng để suy luận nghiệp vụ:** cùng bốn lời gọi logging được thực hiện trong mã, nhưng chỉ ba hoặc bốn dòng được ghi ra theo backend và ngưỡng.
8. **Bản thân program output không có tác dụng phụ nghiệp vụ:** logging không được dùng để quyết định request thành công hay thất bại.

## 8. Chọn backend ở build/runtime như thế nào?

Thông thường, sau khi mã được biên dịch dựa trên **slf4j-api**, backend được lựa chọn bằng **các JAR có mặt trên classpath/module path của runtime** và cấu hình provider phù hợp. Với SLF4J 2, ServiceLoader phát hiện provider tương thích; trong những tình huống đặc biệt, các phiên bản mới còn có cơ chế chỉ định provider tường minh.

**Một ứng dụng nên có chủ ý chọn một provider SLF4J tại runtime.** Nên xem cây dependency trước khi đưa lên môi trường khác:

~~~bash
mvn dependency:tree
~~~

Đọc các artifact như **slf4j-api**, **logback-classic**, **slf4j-simple**, **slf4j-jdk14**, **log4j-slf4j2-impl** và những dependency đưa chúng vào transitively. Nếu có nhiều provider, xử lý bằng dependency exclusions phù hợp với thiết kế build. Không xóa ngẫu nhiên slf4j-api vì đây là API mà code đang dùng.

### Ví dụ thay backend bằng một provider khác

Khi dùng SLF4J với **JUL**, provider thường là **org.slf4j:slf4j-jdk14** tương thích dòng SLF4J API. JUL sẽ quyết định ngưỡng và handler bằng cơ chế riêng của java.util.logging. Nếu dùng **Log4j 2** làm backend cho code SLF4J 2.x, thường có artifact **org.apache.logging.log4j:log4j-slf4j2-impl** cùng các thành phần Log4j 2 thích hợp.

Đừng nhầm **log4j-slf4j2-impl** dành cho SLF4J 2 với **log4j-slf4j-impl** dành cho thế hệ SLF4J 1.7. Việc chọn sai adapter có thể gây cảnh báo hoặc không route log đúng.

Chuyển backend **không có nghĩa copy nguyên file cấu hình**: logback.xml không phải log4j2.xml hoặc logging.properties của JUL. Các appender, pattern, layout, async và filter phải được chuyển đổi có chủ đích khi thay implementation.

## 9. Bridge và provider khác nhau ở hướng chuyển tiếp

Khi ứng dụng dùng nhiều thư viện, không phải tất cả cùng gọi API SLF4J. Một dependency có thể ghi thẳng qua **java.util.logging.Logger**, một dependency khác gọi **Log4j API**. Khi đó người ta dùng **bridge/adapter** để gom log qua một hệ thống.

Cần phân biệt hướng:

| Thành phần | Hướng chính | Ý nghĩa |
| --- | --- | --- |
| **slf4j-jdk14** | SLF4J API → JUL | Provider gửi log SLF4J cho JUL xử lý |
| **jul-to-slf4j** | JUL API → SLF4J | Bridge chuyển các cuộc gọi JUL qua SLF4J |
| **log4j-slf4j2-impl** | SLF4J 2 API → Log4j 2 | Provider/adapter cho Log4j 2 làm backend |
| **log4j-to-slf4j** | Log4j 2 API → SLF4J | Adapter chuyển lời gọi Log4j API sang SLF4J |

Một **provider** thực thi hoặc kết nối facade SLF4J với backend. Một **bridge** thường dùng để bắt các lời gọi từ API logging khác và đưa về hệ thống bạn đang tập trung hóa.

### Cảnh báo vòng lặp nguy hiểm

Không lắp đồng thời **jul-to-slf4j** (JUL → SLF4J) và **slf4j-jdk14** (SLF4J → JUL) theo cách khiến cùng record được chuyển tới chuyển lui; đây có thể tạo vòng định tuyến và lỗi nghiêm trọng. Tương tự, không lắp đồng thời **log4j-to-slf4j** (Log4j API → SLF4J) với **log4j-slf4j2-impl** (SLF4J → Log4j 2) trên cùng đường đi; tài liệu Log4j cảnh báo vòng chuyển tiếp không có điểm dừng.

Khi cần gom log, hãy **chọn một chiều cuối cùng** và vẽ rõ đường đi cho từng API, thay vì cứ thêm tất cả bridge và provider vào classpath.

Ví dụ định hướng:

~~~text
Ứng dụng: SLF4J API
Thư viện A: JUL API --jul-to-slf4j--> SLF4J API
SLF4J provider: Logback Classic
Đích cuối: Logback Appenders
~~~

Đây là một kiến trúc có thể hợp lý nếu bridge được cấu hình và cài đặt đúng. **Không** thêm slf4j-jdk14 vào cùng pipeline khi Logback đã là provider đích.

## 10. Level, cấu hình và MDC: thống nhất API không có nghĩa đồng nhất mọi tính năng

### Level

SLF4J thường dùng **TRACE, DEBUG, INFO, WARN, ERROR**. JUL dùng **FINEST, FINER, FINE, CONFIG, INFO, WARNING, SEVERE**. Cách mapping qua provider/bridge tùy implementation; không giả định **FINE = DEBUG** theo mọi mặt hoặc tất cả custom level đều có ánh xạ tương ứng.

Một lời gọi SLF4J DEBUG có thể không xuất nếu backend đặt INFO. Facade là nơi code gọi **LOG.debug(...)**, nhưng backend là nơi effective level/filter quyết định record có tới output không. Khi đổi backend, cần kiểm tra lại ngưỡng, additivity, handler/appender và configuration precedence.

### Message template và formatting

SLF4J dùng placeholder **{}**:

~~~java
// Minh họa: LOG là org.slf4j.Logger.
LOG.info("event=order.created orderId={} items={}", "OD-42", 2);
~~~

JUL thường dùng tham số có chỉ số **{0}, {1}** khi gọi overload tương ứng với Formatter. Vì vậy, chuyển mã từ JUL trực tiếp sang SLF4J không chỉ đổi import rồi giữ nguyên mọi placeholder.

### MDC / context

SLF4J có **org.slf4j.MDC**, nhưng không phải backend nào cũng thể hiện MDC giống nhau. Logback có thể dùng **%X{requestId}** trong pattern. Simple implementation có định dạng riêng và không tự xuất mọi trường MDC theo cách của Logback.

MDC thường gắn theo thread/execution context. Trong thread pool hoặc tác vụ async, context cần được sao chép/truyền và dọn đúng lúc; không được để dữ liệu request cũ rò sang request tiếp theo. Tránh đưa thông tin nhạy cảm vào MDC.

### Throwable và stack trace

Dùng overload logging nhận Throwable khi cần giữ lỗi:

~~~java
// Minh họa: LOG và Throwable ex có sẵn.
LOG.error("event=payment.failed orderId={}", "OD-42", ex);
~~~

Backend quyết định việc hiển thị stack trace, multiline và các trường bổ sung. Một exception có thể tạo nhiều dòng output dù chỉ là **một logging event**. Đừng kết luận số dòng stack trace bằng số lượng lỗi.

### Structured logging

SLF4J 2 cung cấp API bổ trợ như fluent logging và key-value pairs. Backend vẫn quyết định cách lưu/render những cặp giá trị này. Muốn truy vấn JSON theo field có kiểu, nên chọn encoder/schema có cấu trúc phù hợp, không tự ghép chuỗi JSON thiếu escaping rồi cho rằng mọi backend đều hiểu.

## 11. Phân biệt facade/backend trong một dự án có sẵn

Khi gặp một dự án Java chưa quen, hãy trả lời lần lượt:

1. **Code import API nào?** Tìm **org.slf4j.Logger**, **java.util.logging.Logger**, **org.apache.logging.log4j.Logger** hoặc API khác.
2. **Những dependency nào cung cấp API?** SLF4J API riêng không có nghĩa log sẽ xuất.
3. **Provider SLF4J nào thực sự có mặt lúc runtime?** Dùng dependency tree, cấu hình classpath và warning từ SLF4J 2.
4. **Có bridge chuyển API khác không?** Xác định chiều để tránh vòng lặp.
5. **Backend đọc file gì?** logback.xml, log4j2.xml, JUL logging.properties hoặc cấu hình do framework tạo.
6. **Ngưỡng thực tế là gì?** Đừng chỉ xem lời gọi LOG.debug; kiểm tra logger/root level, filter, handler/appender.
7. **Dòng log đi đâu?** Console stdout/stderr, file, collector, network hoặc bị NOP.
8. **Output có khớp kỳ vọng không?** Kiểm tra formatter/layout, timezone, MDC, exception và encoding.
9. **Có nhiều provider không?** Nếu có, loại provider dư và chạy thử lại để không phụ thuộc classpath order.
10. **Có lời gọi từ thư viện bên thứ ba không?** Khi dùng bridge, chỉ chuyển theo hướng đã thiết kế và xác nhận không gây loop.

Bạn có thể quan sát lựa chọn backend SLF4J bằng:

~~~java
// Đoạn minh họa cần đặt trong một phương thức Java.
String factoryType =
        org.slf4j.LoggerFactory.getILoggerFactory()
                .getClass().getName();
System.out.println(factoryType);
~~~

Đây là **một kỹ thuật kiểm tra**, không phải API cấu hình logging. Trong production, không cần gọi và in loại factory cho mỗi request. Nếu các container hoặc class loader khác nhau, cần kiểm tra trong đúng runtime đang xử lý sự kiện.

## 12. Các tình huống lỗi thường gặp

| Triệu chứng | Giải thích có thể | Hướng khắc phục |
| --- | --- | --- |
| SLF4J cảnh báo **No SLF4J providers were found** | Có slf4j-api nhưng thiếu provider phù hợp | Thêm một provider tương thích ở runtime |
| SLF4J cảnh báo có **multiple providers** | Hai hoặc nhiều provider xuất hiện trên classpath | Loại provider dư bằng dependency management/exclusion |
| Có JAR binding đời cũ nhưng SLF4J 2 không nhận | Provider/binding không đúng thế hệ ServiceLoader | Chọn provider hỗ trợ 2.x thay cho StaticLoggerBinder 1.7 |
| Code chạy mà không có log | NOP provider, level/filter, sai đích xuất hoặc pipeline | Xem provider, level, backend config, stdout/stderr |
| LOG.debug không xuất | Backend đặt INFO hoặc filter loại record | Bật DEBUG đúng logger/package và appender |
| Đổi backend nhưng format không đổi như mong muốn | File cấu hình cũ không được backend mới đọc | Dùng file config và encoder/layout của backend mới |
| RequestId hiển thị dưới Logback nhưng không có ở Simple | MDC rendering/back-end config khác nhau | Kiểm tra implementation và các field được backend xuất |
| Cùng event bị in hai lần | Appender cộng dồn, bridge hoặc cấu hình trùng | Kiểm tra additivity, handler/appender và đường bridge |
| App xảy ra loop khi ghi log | Có các adapter hai chiều trái ngược cùng hoạt động | Thiết kế một chiều chuyển tiếp, bỏ cặp adapter xung đột |
| Log từ một thư viện không theo định dạng chung | Thư viện đó dùng JUL/Log4j API trực tiếp | Xác định API nguồn và bridge cần thiết nếu muốn gom |
| Maven exec:java khác chạy bằng java trực tiếp | Maven plugin có thể ảnh hưởng classloader/provider và cấu hình logging | Chạy JVM riêng bằng exec:exec để kiểm chứng |
| Đổi dependency nhưng không đổi output ở deployment | Runtime vẫn có artifact cũ hoặc container classpath khác build | Kiểm tra artifact đóng gói và classpath thực tế |

**Bẫy khái niệm:** “SLF4J là Logback” — sai. SLF4J cung cấp API; Logback là một backend có thể triển khai API đó. “Log4j 2 chỉ là backend” cũng chưa hoàn toàn chính xác: Log4j 2 có **Log4j API** riêng và thành phần **Core** thực thi. Khi tích hợp qua SLF4J, Log4j 2 cần adapter/provider đúng chiều.

**Bẫy về đóng gói:** một thư viện được build thành công với SLF4J API nhưng ứng dụng runtime không có provider thì có thể không ghi log nào. Compiler chỉ xác nhận có các kiểu/phương thức API cần thiết; nó không chứng minh backend runtime đã được lựa chọn đúng.

## 13. Bảo mật, hiệu năng và vận hành

Dù facade giúp đổi backend, nó **không tự bảo đảm log an toàn, nhanh hoặc đúng schema**:

- **Bảo mật dữ liệu:** không ghi password, access token, secret, cookie, OTP, thông tin thanh toán hoặc payload riêng tư; kể cả log development cũng có thể được thu thập/chia sẻ.
- **Log injection:** dữ liệu từ người dùng có newline hoặc ký tự điều khiển có thể giả mạo log record. Cần escaping và giới hạn chiều dài, nhất là khi xuất text.
- **Chi phí tạo message:** logging có tham số tránh nối chuỗi sớm cho phần format, nhưng đối số Java vẫn được đánh giá trước lời gọi. Với tác vụ tạo dữ liệu đắt đỏ, dùng kiểm tra isDebugEnabled hoặc Supplier/fluent API phù hợp.
- **Chi phí backend:** encode, serialize, file I/O, network shipping và queue async có thể gây trễ hoặc mất log khi quá tải; cần đo theo implementation thực tế.
- **Cấu hình riêng theo môi trường:** INFO trên production có thể phù hợp baseline; DEBUG/TRACE chỉ nên bật cho phần liên quan khi điều tra. Không có một cấu hình đúng cho mọi sản phẩm.
- **Correlation:** requestId/traceId và convention event name hỗ trợ phân tích nhiều service; cách truyền context qua thread pool phải được xử lý có kiểm soát.
- **Không dùng log thay audit trail:** log chẩn đoán thông thường không tự đảm bảo tính toàn vẹn, retention hoặc chứng minh commit của giao dịch.
- **Kiểm tra output sau đổi backend:** migration có thể ảnh hưởng alert, parser, dashboard, độ dài trường, timestamp, MDC, stack trace và file rotation. Đổi dependency là bước đầu, không phải bước cuối.

Lựa chọn backend phù hợp phải dựa trên yêu cầu thực tế: cấu trúc dữ liệu, tần suất log, khả năng tích hợp, bảo mật, tải, cách vận hành, chính sách của tổ chức và khả năng duy trì. Một ứng dụng nhỏ có thể dùng simple; dịch vụ cần cấu hình/rolling/structured output có thể dùng backend đầy đủ hơn.

## 14. Bài tập thực hành và câu hỏi tự kiểm tra

### Bài tập A — Đổi backend, không đổi source

Chạy hai lệnh ở mục 7 và so sánh:

- Provider/LoggerFactory: LoggerContext so với SimpleLoggerFactory.
- Số dòng được in: Logback DEBUG có 4 dòng, simple mặc định INFO có 3 dòng.
- Định dạng: Logback lấy requestId từ MDC theo logback.xml; simple dùng format riêng.
- Xác định những thứ **không đổi**: import org.slf4j.*, bốn lời gọi logger, event name và message template.

Sau đó chỉnh **root level** trong logback.xml từ DEBUG thành INFO, chạy lại profile logback và ghi nhận dòng DEBUG bị lọc. Không cần sửa dòng LOG.debug trong Java.

### Bài tập B — Thử thiếu provider

Trong một project thử nghiệm riêng, chỉ khai báo slf4j-api và **không** đưa provider lên runtime classpath. Quan sát warning của SLF4J 2 và việc logger có thể thành NOP. Đừng kết luận ứng dụng không chạy chỉ vì không có record.

### Bài tập C — Thử thông điệp có Throwable

Bổ sung một nhánh xử lý lỗi có chủ đích bằng **LOG.error(message, argument, throwable)**. So cách mỗi backend hiển thị stack trace, nhận ra một exception có thể tạo nhiều dòng log. Không ghi dữ liệu nhạy cảm vào message để thử nghiệm.

### Câu hỏi và đáp án

**1. Facade khác backend ở điểm cốt lõi nào?**  
Facade định nghĩa API để code yêu cầu ghi log; backend xử lý sự kiện, filtering, format và nơi xuất.

**2. Nếu dùng SLF4J thì có bắt buộc dùng Logback không?**  
Không. Có thể dùng một provider phù hợp khác như Log4j 2 adapter, JUL provider, slf4j-simple hoặc NOP theo mục đích.

**3. Vì sao thư viện Java thường chỉ phụ thuộc slf4j-api?**  
Để không áp đặt lựa chọn backend lên ứng dụng cuối và giảm nguy cơ multiple providers.

**4. Vì sao SLF4J 2 báo không tìm thấy provider dù có JAR SLF4J 1.7 binding?**  
SLF4J 2 dùng ServiceLoader providers; cơ chế StaticLoggerBinder cũ không được coi là provider tương thích.

**5. Đổi backend có cần sửa code LOG.info không?**  
Thông thường không, nếu source chỉ dùng API facade. Nhưng cấu hình, khả năng logging, format và integration có thể phải thay đổi.

**6. Hai adapter nào không nên dùng đồng thời để nối Log4j 2 và SLF4J?**  
Không kết hợp log4j-to-slf4j và log4j-slf4j2-impl trong một vòng định tuyến, vì một bên chuyển Log4j API → SLF4J và bên kia chuyển SLF4J → Log4j 2.

**7. Vì sao cùng LOG.debug nhưng Logback hiện còn simple không hiện ở demo?**  
Logback được cấu hình DEBUG trong logback.xml; simple mặc định INFO. Facade không quyết định format hoặc effective level độc lập với backend.

**8. Một thư viện dùng JUL trực tiếp có tự động đi qua SLF4J khi ứng dụng thêm logback-classic không?**  
Không. Cần bridge đúng hướng hoặc cấu hình phù hợp; logback-classic là provider cho cuộc gọi SLF4J, không tự bắt mọi cuộc gọi JUL.

**9. Nếu thấy hai dòng log giống nhau, có phải do source gọi hai lần?**  
Chưa chắc; còn có thể vì additivity, nhiều appender, nhiều provider/bridge hoặc collector lặp dữ liệu. Phải kiểm tra pipeline.

**10. Vì sao không đưa mọi field vào MDC rồi cho rằng tất cả backend đều xuất?**  
MDC có API chung nhưng cách hiển thị/phân phối context phụ thuộc backend và cấu hình. Việc ghi field không an toàn cũng tạo rủi ro bảo mật.

## 15. Tài liệu tham khảo

- [SLF4J User Manual](https://www.slf4j.org/manual.html): facade, provider, ví dụ LoggerFactory, liên kết backend và MDC.
- [SLF4J FAQ](https://www.slf4j.org/faq.html): tương thích API/provider, chuyển backend và cơ chế ServiceLoader trong SLF4J 2.
- [SLF4J Warning / Error Codes](https://www.slf4j.org/codes.html): không có provider, multiple providers, binding cũ và cách chẩn đoán.
- [Logback Manual](https://logback.qos.ch/manual/index.html): LoggerContext, appenders, encoder, configuration và mức log.
- [Apache Log4j — SLF4J Binding](https://logging.apache.org/log4j/2.x/log4j-slf4j-impl.html): phân biệt adapter SLF4J 1.7/2.x và cảnh báo vòng chuyển tiếp khi dùng log4j-to-slf4j.

## Tóm tắt

**Facade là API ổn định mà mã Java gọi; backend là phần thực thi và xuất log; provider/adapter là mắt xích đưa lời gọi từ facade đến implementation.** SLF4J cho phép source code không phụ thuộc trực tiếp Logback hoặc Log4j 2, nhưng mỗi backend vẫn có cấu hình, hiệu năng, định dạng và khả năng riêng. Hãy chọn **đúng một provider tương thích**, tránh các bridge vòng lặp, kiểm tra dependency/runtime classpath và thử output sau khi đổi backend. Kết quả thực hành đã minh họa: **cùng code Java, khác backend thì log hiển thị khác nhau**.
