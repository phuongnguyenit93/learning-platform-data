# Chọn facade — Thiết kế API logging phù hợp cho dự án Java

## 1. Facade trong logging là gì?

Trong Java, **logging facade** là một **lớp API trung gian** mà mã ứng dụng hoặc thư viện gọi để phát log, trong khi việc xử lý và xuất bản ghi được giao cho một **logging backend/provider** cụ thể.

Mục tiêu của facade là giảm phụ thuộc của mã nghiệp vụ vào hệ thống logging thực tế. Lập trình viên viết:

~~~java
LOG.info("event=order.created orderId={}", orderId);
~~~

Với **SLF4J**, lời gọi này đi qua API SLF4J. Backend phía sau có thể là **Logback**, **Log4j 2** qua provider tương ứng, hoặc một triển khai khác được chọn cho ứng dụng. Đổi backend thích hợp thường không đòi hỏi thay toàn bộ lời gọi LOG.info trong source code.

Cần phân biệt ba khái niệm:

| Khái niệm | Nhiệm vụ | Ví dụ |
| --- | --- | --- |
| **Facade / logging API** | Quy định các phương thức mà mã nguồn gọi: log theo level, truyền tham số, Throwable | SLF4J API, Log4j 2 API; JUL cũng là API logging nhưng gắn với JDK |
| **Provider / binding / adapter** | Kết nối facade với hệ thống thực thi logging | Provider SLF4J của Logback; log4j-slf4j2-impl |
| **Backend** | Quyết định level, appender, filter, format và đích ghi | Logback Classic, Log4j 2 Core, JUL qua adapter thích hợp |

**SLF4J không tự là một file log, cũng không tự cung cấp đầy đủ cơ chế ghi file/rotation.** Với các phiên bản hiện đại, nếu chỉ có API nhưng không có provider phù hợp, ứng dụng có thể phát cảnh báo và các lời gọi log không được xuất như mong đợi.

### Sơ đồ cơ bản

~~~text
Application / Library
        |
        v
  org.slf4j.Logger
        |
        v
   SLF4J 2.x API
        |
        v
 Provider được chọn
        |
        v
 Backend (Logback / Log4j 2 / ...)
        |
        v
 Appender + Encoder / Formatter
        |
        v
 Console / File / Logging platform
~~~

Không nhầm **facade** với **bridge**: facade là API được code gọi trực tiếp; bridge là thành phần chuyển log phát bằng **một API khác** sang hệ thống được chọn. Ví dụ thư viện cũ dùng JUL có thể cần một bridge nếu toàn ứng dụng muốn gom sự kiện về SLF4J.

## 2. Vì sao phải chọn facade ngay từ đầu?

Một dự án có thể bắt đầu với vài dòng log, sau đó phát triển thành nhiều module, nhiều thư viện và các môi trường chạy khác nhau. Nếu mọi class gọi trực tiếp API backend, việc đổi backend hoặc thống nhất cấu hình về sau sẽ tốn công.

Ví dụ hai cách phụ thuộc:

**Phụ thuộc vào facade:**

~~~java
// Mảnh mã trong một lớp, cần SLF4J API.
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(OrderService.class);
~~~

**Phụ thuộc trực tiếp vào backend Logback:**

~~~java
// Mảnh mã minh họa, chỉ phù hợp khi thật sự cần API Logback.
ch.qos.logback.classic.Logger logger =
        (ch.qos.logback.classic.Logger)
        org.slf4j.LoggerFactory.getLogger(OrderService.class);
~~~

Đoạn thứ hai phụ thuộc vào implementation, có thể gặp **ClassCastException** nếu ứng dụng chọn provider khác. Không dùng kiểu ép như vậy cho mã nghiệp vụ thông thường.

Một facade phù hợp giúp:

1. **Giữ mã nghiệp vụ ổn định** khi backend hoặc chính sách vận hành thay đổi.
2. **Cho thư viện tái sử dụng không áp đặt đích xuất** lên ứng dụng sử dụng thư viện.
3. **Tập trung cấu hình** mức log, appenders, encoder, retention và quyền truy cập ở tầng triển khai.
4. **Hạn chế xung đột** khi nhiều module/phụ thuộc cùng muốn quản lý logging.
5. **Dễ thử nghiệm** các cách xuất log phù hợp với CLI, web service, container hoặc test.

Tuy nhiên, facade không tự làm log nhanh hơn, an toàn hơn hoặc đầy đủ hơn. Hiệu năng, ngữ cảnh, bộ lọc và độ bền cuối cùng còn phụ thuộc backend, cấu hình và hạ tầng nhận log.

## 3. Các lựa chọn facade/API đáng biết

### 3.1. SLF4J — lựa chọn thường hợp lý cho dự án Java mới

**Simple Logging Facade for Java (SLF4J)** cung cấp API **org.slf4j.Logger** và **LoggerFactory** để ứng dụng gọi log mà không phải sử dụng lớp implementation của một backend cụ thể.

Điểm mạnh:

- Hệ sinh thái Java rộng, nhiều framework và thư viện hỗ trợ.
- Phương thức **trace/debug/info/warn/error**, truyền tham số bằng **{}** và hỗ trợ Throwable.
- Dễ chọn backend riêng cho mỗi ứng dụng, trong khi thư viện chỉ phụ thuộc API.
- Có **MDC** và khả năng kết nối ngữ cảnh khi provider hỗ trợ.
- Có thể kết nối các API logging khác qua adapter/bridge khi dự án thực sự cần.

Giới hạn:

- Cần chọn **provider tương thích** với phiên bản SLF4J API và backend thực tế.
- Một số API hoặc tính năng của backend không xuất hiện đầy đủ ở facade.
- Đổi backend có thể cần đổi **file cấu hình**, pattern, encoder, appender và tính năng vận hành dù mã gọi Logger vẫn giữ nguyên.
- Một facade không xóa được chi phí đánh giá đối số Java trước khi gọi logger.

**Khuyến nghị thực hành:** Với một ứng dụng Java đa module thông thường chưa có ràng buộc đặc biệt, **SLF4J 2.x thường là điểm khởi đầu tốt cho API**; chọn một backend phù hợp sau đó. Đây là gợi ý theo nhu cầu phổ biến, không phải quy tắc bắt buộc cho mọi hệ thống.

### 3.2. java.util.logging (JUL) — tích hợp JDK

JUL nằm sẵn trong Java, dùng **java.util.logging.Logger** và các Level như **SEVERE, WARNING, INFO, CONFIG, FINE, FINER, FINEST**.

Ưu điểm:

- Không cần thêm dependency để ghi log cơ bản.
- Phù hợp với ứng dụng nhỏ, công cụ chỉ sử dụng JDK, hoặc dự án đã chuẩn hóa JUL.
- Có Handler, Formatter, Filter, LogManager và cấu hình riêng.

Hạn chế:

- API và mô hình cấu hình khác hệ SLF4J/Logback/Log4j 2.
- Các tính năng như structured fields hoặc MDC không đồng nhất như API facade SLF4J và backend hiện đại.
- Nếu hệ thống đã dùng SLF4J làm hướng thống nhất, cần cân nhắc bridge JUL → SLF4J để tập trung log của các thành phần dùng JUL.

**Không có Level.DEBUG hay Level.ERROR trong JUL**; FINE và SEVERE là các mức gần về mục đích nhưng không đồng nhất mọi hành vi với DEBUG/ERROR của SLF4J.

### 3.3. Log4j 2 API — khi dự án chọn hệ sinh thái Log4j 2

**org.apache.logging.log4j.Logger** là API của Log4j 2. Có thể viết code dựa trên API này và dùng implementation tương ứng như **Log4j 2 Core**. Hệ sinh thái Log4j 2 có nhiều khả năng cấu hình và mở rộng riêng.

Nên cân nhắc khi:

- Dự án hiện tại đã chuẩn hóa Log4j 2 API.
- Cần những chức năng API hoặc kiến trúc quan sát gắn chặt với Log4j 2.
- Quy định vận hành/dependency hiện có đã thống nhất stack này.

**Không mặc định Log4j 2 API là SLF4J.** Có adapter kết nối hai hệ, nhưng cần chọn đúng chiều, đúng phiên bản và tránh bridge vòng lặp.

### 3.4. Commons Logging (JCL) — thường gặp trong dự án cũ

**Apache Commons Logging (JCL)** là một API logging xuất hiện trong nhiều thư viện Java truyền thống. Khi bảo trì hệ thống cũ, bạn có thể gặp **org.apache.commons.logging.Log**.

Không nhất thiết phải đưa JCL vào một dự án mới chỉ để ghi log. Nếu dependency cũ sử dụng nó, có thể giữ nguyên và dùng giải pháp tương thích theo framework. Đánh giá cách logging đã được tích hợp trong hệ thống trước khi tự thêm adapter.

**Lưu ý:** nhiều framework có cơ chế tích hợp logging riêng. Nếu dự án dùng Spring Boot hoặc một nền tảng được tổ chức sẵn, hãy theo cơ chế dependency/configuration của framework thay vì ép mọi thư viện vào một thiết lập mới.

## 4. Bảng so sánh lựa chọn

| Tiêu chí | SLF4J API | JUL | Log4j 2 API |
| --- | --- | --- | --- |
| Có sẵn trong JDK? | Không | Có | Không |
| Tách code khỏi backend cụ thể? | Có, mục tiêu chính | Không theo cùng mô hình facade đa backend | Có mức độ tách API/implementation trong hệ Log4j 2 |
| Tên mức thường gặp | TRACE, DEBUG, INFO, WARN, ERROR | FINEST/FINER/FINE, CONFIG, INFO, WARNING, SEVERE | TRACE, DEBUG, INFO, WARN, ERROR và mức khác tùy API |
| Dependency cho thư viện | Thường chỉ slf4j-api | Không cần dependency ngoài JDK | log4j-api |
| Đích xuất | Do provider/backend cấu hình | Handler của JUL | Implementation/backend tương ứng |
| MDC/context | API MDC, phụ thuộc provider và propagation | Không có API MDC tương đương trực tiếp | ThreadContext/API tương ứng |
| Phù hợp | Ứng dụng/thư viện Java muốn giữ backend linh hoạt | Công cụ thuần JDK, stack chuẩn hóa JUL | Dự án đã chọn API/stack Log4j 2 |
| Điểm cần tránh | Thiếu/trùng provider, sai version, bridge vòng lặp | Mong LOG_LEVEL=DEBUG tự có tác dụng, nhầm Level.DEBUG | Nhầm adapter chiều kết nối, trộn nhiều backend |

**Tiêu chí quan trọng hơn tên thư viện:** facade có phù hợp với kiến trúc hiện tại, hợp đồng của thư viện, version đang dùng và cách vận hành không? Đừng chọn chỉ vì một benchmark riêng lẻ không phản ánh cấu hình và tải của hệ thống.

## 5. Quy trình quyết định chọn facade

Có thể dùng các câu hỏi sau theo thứ tự.

### Bước 1: Viết ứng dụng hay thư viện tái sử dụng?

- **Ứng dụng** chịu trách nhiệm chọn backend, cấu hình level, appender, retention và kết nối với hệ thống thu thập log.
- **Thư viện** nên phát log qua API phù hợp và **không tự áp đặt backend**, vì bên dùng thư viện cần kiểm soát log toàn tiến trình.

Nếu đang viết thư viện dùng chung và chưa có chuẩn bắt buộc, **chỉ phụ thuộc slf4j-api** thường hợp lý. Không thêm logback-classic hay log4j-core làm dependency runtime bắt buộc của thư viện chỉ để thư viện có thể log.

### Bước 2: Dự án đã có logging stack nào?

Kiểm tra logging dependency, framework và cấu hình hiện có. Nếu ứng dụng đã chuẩn hóa SLF4J/Logback, gọi SLF4J Logger trong mã mới thường đơn giản nhất. Nếu dự án thuần JUL và chỉ cần tính năng sẵn có, việc chuyển toàn bộ sang stack khác có thể không đáng chi phí.

Không chọn một facade mới mà không xét API mà các module hiện tại đang sử dụng; có thể tăng số bridge, xung đột backend và chi phí bảo trì.

### Bước 3: Yêu cầu triển khai có gì đặc biệt?

Các yêu cầu có thể ảnh hưởng backend/configuration, không nhất thiết buộc đổi facade:

- Xuất JSON có schema rõ ràng, tương quan request/trace ID.
- Console logging cho container, file rotation, appender bất đồng bộ.
- Thay level trong lúc chạy, lọc theo package hoặc thành phần.
- Kiểm soát độ trễ, throughput và áp lực I/O.
- Bảo mật, masking, retention và kiểm toán.

Chẳng hạn, **muốn xuất JSON chưa đủ lý do bỏ SLF4J**; chọn backend và encoder JSON thích hợp cũng có thể giải quyết. Ngược lại, nếu cần API đặc thù của backend trong mã nguồn, phải chấp nhận mức độ phụ thuộc đó hoặc thiết kế abstraction riêng.

### Bước 4: Chọn một provider/backend chính

Với SLF4J 2.x, lựa chọn có thể là:

- **Logback Classic:** backend thường gặp, hỗ trợ appender, encoder, filter và cấu hình qua logback.xml.
- **Log4j 2 qua provider tương ứng:** hữu ích nếu hạ tầng đã chuẩn hóa Log4j 2.
- **slf4j-simple:** backend nhẹ cho demo và công cụ đơn giản; không thay thế toàn bộ nhu cầu logging production.
- **slf4j-jdk14:** kết nối SLF4J sang JUL trong hệ thống cần dùng JUL làm backend.

**Không gắn nhiều provider SLF4J cùng lúc** với kỳ vọng tất cả đều ghi: môi trường có thể chọn một provider và bỏ qua provider khác, kèm cảnh báo. Một backend chính và kiến trúc routing rõ ràng thường dễ vận hành nhất.

### Bước 5: Xem thư viện dùng API khác ra sao

Một ứng dụng có thể dùng SLF4J trong mã mới nhưng dependency cũ dùng JUL, JCL hoặc Log4j 2 API. Khi cần gom output, hãy chọn **bridge đúng chiều**, kiểm tra dependency tree và tránh tạo vòng lặp.

### Bước 6: Kiểm chứng bằng chạy thật

- Log INFO/WARN/ERROR có xuất đúng đích?
- DEBUG có bị ẩn ở ngưỡng INFO và hiện ở ngưỡng DEBUG?
- Throwable có stack trace khi cần?
- Có đúng một bản ghi cho một sự kiện?
- MDC/trace context có đi đúng theo async task?
- Thông tin nhạy cảm đã được loại hoặc che chưa?

**Chọn facade là quyết định kiến trúc, nhưng phải được xác nhận bằng cách hệ thống chạy thật.**

## 6. Ví dụ đầy đủ: chọn SLF4J, triển khai bằng Logback

Mục tiêu là chứng minh mã chỉ dùng **SLF4J API**, còn backend và định dạng output được quyết định trong **logback.xml**.

Yêu cầu: **JDK 17+**, Maven 3.x và khả năng tải dependency (lần đầu cần kết nối repository, trừ khi đã cache).

### 6.1. Cấu trúc dự án

~~~text
facade-choice-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── FacadeChoiceDemo.java
        └── resources/
            └── logback.xml
~~~

### 6.2. Tạo pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>facade-choice-demo</artifactId>
    <version>1.0.0</version>

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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.FacadeChoiceDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Đây là ví dụ sử dụng các phiên bản cụ thể**, không phải tuyên bố các phiên bản mới nhất. Trong dự án thật, kiểm tra tương thích và các bản vá bảo mật theo dependency management của dự án; không tự thêm provider thứ hai.

### 6.3. Tạo src/main/resources/logback.xml

~~~xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%level | %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
~~~

Cấu hình này đặt:

- **Root INFO**: INFO, WARN và ERROR được chấp nhận theo cơ chế level thông thường; DEBUG bị lọc.
- **ConsoleAppender**: đưa sự kiện ra **System.out** theo mặc định của Logback ConsoleAppender.
- **Pattern**: in mức log, dấu phân cách và thông điệp; không in timestamp để output dễ so sánh.
- **UTF-8**: xử lý Unicode khi terminal/collector hỗ trợ.
- Appender chỉ gắn tại root, tránh cấu hình trùng appender ở logger con.

### 6.4. Tạo src/main/java/demo/FacadeChoiceDemo.java

~~~java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class FacadeChoiceDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(FacadeChoiceDemo.class);

    public static void main(String[] args) {
        String orderId = "ORD-7";

        LOG.debug("event=order.validation orderId={} passed=true", orderId);
        LOG.info("event=order.received orderId={}", orderId);
        LOG.warn("event=order.retry orderId={} attempt={}", orderId, 2);
        LOG.error("event=order.failed orderId={} code={}",
                orderId, "REMOTE_TIMEOUT");
    }
}
~~~

Mã này **chỉ import org.slf4j.Logger và LoggerFactory**, không import class Logger của Logback. Vì thế facade vẫn là SLF4J; Logback chỉ hiện diện trong dependency/configuration.

### 6.5. Biên dịch và chạy

Ở thư mục **facade-choice-demo**:

~~~bash
mvn -q compile exec:java
~~~

Với các file và cấu hình trên, **stdout do chương trình phát** (không tính thông tin riêng của Maven hoặc môi trường chạy) là:

~~~text
INFO | event=order.received orderId=ORD-7
WARN | event=order.retry orderId=ORD-7 attempt=2
ERROR | event=order.failed orderId=ORD-7 code=REMOTE_TIMEOUT
~~~

Dòng DEBUG không xuất vì root đặt INFO. Các placeholder **{}** của SLF4J được thay bằng argument, còn **%level | %msg%n** là cú pháp pattern của Logback; đây là **hai lớp định dạng khác nhau**.

### 6.6. Thử bật DEBUG mà không sửa Java

Đổi trong logback.xml:

~~~xml
<root level="DEBUG">
    <appender-ref ref="STDOUT"/>
</root>
~~~

Chạy lại ứng dụng. **Stdout của ứng dụng** có thêm dòng đầu:

~~~text
DEBUG | event=order.validation orderId=ORD-7 passed=true
INFO | event=order.received orderId=ORD-7
WARN | event=order.retry orderId=ORD-7 attempt=2
ERROR | event=order.failed orderId=ORD-7 code=REMOTE_TIMEOUT
~~~

Sự thay đổi nằm ở cấu hình backend, **không cần sửa lời gọi facade trong mã nguồn**.

## 7. Thử đổi backend: giữ API SLF4J nhưng thay Logback

Giả sử chỉ muốn logging đơn giản trong một công cụ thử nghiệm. Có thể thay dependency backend **logback-classic** bằng **slf4j-simple** tương thích SLF4J 2.x, trong khi giữ SLF4J API.

Trong pom.xml, giữ dependency slf4j-api rồi thay **toàn bộ dependency logback-classic** bằng:

~~~xml
<dependency>
    <groupId>org.slf4j</groupId>
    <artifactId>slf4j-simple</artifactId>
    <version>2.0.17</version>
</dependency>
~~~

File Java **FacadeChoiceDemo.java** không phải sửa. Cần lưu ý:

- **slf4j-simple** có cách cấu hình và định dạng riêng; **logback.xml không còn là file cấu hình được backend này đọc**.
- Output của slf4j-simple mặc định **khác mẫu Logback ở mục 6** và thường được xuất ra **stderr**, không thể lấy ba dòng mẫu trên làm stdout cam kết cho backend mới.
- Nếu cần điều chỉnh mức và format, đọc cấu hình của slf4j-simple thay vì giữ nguyên cấu hình Logback.
- Phải **loại bỏ provider Logback khỏi classpath runtime**; chỉ thêm slf4j-simple mà giữ logback-classic có thể tạo tình trạng nhiều provider.
- Việc đổi backend không tự bảo đảm những tính năng như async appender, file rotation hay JSON encoder được giữ nguyên. Những tính năng đó cần kiểm chứng lại.

Đây chính là lợi ích và giới hạn của facade: **mã gọi log giữ nguyên, còn phần triển khai/cấu hình vẫn phải được thay đổi phù hợp**.

## 8. Ứng dụng và thư viện: quyết định dependency khác nhau

### 8.1. Ứng dụng tự chọn backend

Với ứng dụng web/worker/CLI cần ghi log ở runtime, dependency điển hình:

~~~text
application code
    -> slf4j-api
    -> một SLF4J provider
    -> backend tương ứng
~~~

Ví dụ Logback Classic được chọn làm provider/backend chính. Ứng dụng quyết định log đi đâu, mức nào được ghi, retention ra sao và cách thêm requestId/traceId vào event.

### 8.2. Thư viện chỉ phụ thuộc facade

Với một thư viện dùng lại trong nhiều ứng dụng, dependency chính nên là API, ví dụ:

~~~xml
<dependency>
    <groupId>org.slf4j</groupId>
    <artifactId>slf4j-api</artifactId>
    <version>2.0.17</version>
</dependency>
~~~

Thư viện không nên đưa **logback-classic** hoặc **slf4j-simple** thành dependency runtime bắt buộc chỉ vì nó gọi logger; điều đó có thể áp đặt backend lên ứng dụng của người sử dụng. Trong test của thư viện có thể chọn provider đơn giản theo phạm vi test nếu cần xác nhận log.

Thư viện cũng không nên tự ý:

- Gọi LoggerContext.reset() làm thay đổi logging toàn ứng dụng.
- Tự gắn appender vào root logger.
- Thay level/format logging của các package không thuộc thư viện.
- Ghi dữ liệu nhạy cảm hoặc bắt ứng dụng phải tạo file log tại một đường dẫn cố định.

**Quyền sở hữu cấu hình logging tổng thể thuộc ứng dụng hoặc framework điều phối**, không thuộc từng thư viện.

### 8.3. Xử lý version

Với **SLF4J 2.x**, cơ chế tìm provider dựa trên **ServiceLoader**. Đó là thay đổi quan trọng so với cơ chế binding đời cũ của SLF4J 1.7.x.

Vì vậy:

- Không giả định **binding cho SLF4J 1.7** tự tương thích với **SLF4J 2.x**.
- Các bản của slf4j-api, provider và backend cần tương thích với nhau.
- Khi một thư viện cũ kéo bản API/provider khác, nên phân tích **dependency tree**, áp dụng dependency management và loại bỏ dependency xung đột.
- Không chữa lỗi “không có log” bằng cách ngẫu nhiên thêm nhiều binding/provider khác nhau.

Chỉ có API mà thiếu provider tương thích có thể khiến sự kiện không được ghi như mong đợi. Có nhiều provider thì runtime có thể chọn một provider và cảnh báo; không coi đó là phương pháp ghi log đồng thời ra nhiều backend.

## 9. Bridge và adapter: chọn đúng chiều

Khi thư viện hiện có dùng API logging khác, ứng dụng có thể gom log bằng cách chuyển sự kiện sang stack chính. Ví dụ một số tuyến thường gặp:

~~~text
Mã sử dụng JUL
       |
       v
jul-to-slf4j  (cần cài bridge phù hợp)
       |
       v
   SLF4J API
       |
       v
  Logback provider / backend
~~~

~~~text
Mã sử dụng SLF4J 2.x
       |
       v
log4j-slf4j2-impl
       |
       v
Log4j 2 backend
~~~

~~~text
Mã sử dụng Log4j 2 API
       |
       v
log4j-to-slf4j
       |
       v
SLF4J provider (ví dụ Logback)
~~~

**Một vài lưu ý có tính quyết định:**

| Thành phần | Chiều chuyển chính | Lưu ý |
| --- | --- | --- |
| jul-to-slf4j | JUL → SLF4J | Cần cài/thiết lập bridge thích hợp; chỉ có JAR không nhất thiết tự chuyển toàn bộ log |
| slf4j-jdk14 | SLF4J → JUL | Là provider SLF4J dùng JUL, không phải bridge ngược |
| log4j-to-slf4j | Log4j 2 API → SLF4J | Dành cho trường hợp muốn các lời gọi Log4j 2 tới SLF4J |
| log4j-slf4j2-impl | SLF4J 2.x → Log4j 2 | Là tuyến ngược lại, dùng khi Log4j 2 làm backend |
| jcl-over-slf4j | JCL API → SLF4J | Có thể phục vụ thư viện dùng Commons Logging, cần kiểm tra dependency và cách framework xử lý JCL |

**Không được lắp hai chiều đối nghịch cùng lúc để chúng trỏ vào nhau.** Đặc biệt, kết hợp **log4j-to-slf4j** với **log4j-slf4j2-impl** trong cùng cấu hình sẽ tạo một vòng chuyển tiếp không hợp lệ. Tương tự, **jul-to-slf4j** và provider SLF4J → JUL như **slf4j-jdk14** là một kiểu tổ hợp nguy hiểm khi cùng gửi bản ghi qua hai hướng.

Bridge cần được lắp ở tầng ứng dụng có quyền kiểm soát logging. Cấu hình JUL → SLF4J còn cần lưu ý ngưỡng của JUL: những sự kiện đã bị JUL lọc trước khi tới bridge sẽ không tự xuất hiện ở backend mới. Đừng mặc định cài một dependency là đủ để chuyển mọi level.

## 10. Facade khác gì adapter, wrapper và backend?

Một số hệ thống có thêm **wrapper** do dự án tự viết để thống nhất event code, trường bắt buộc, che dữ liệu nhạy cảm và cách truyền context. Khi đó có thể có:

~~~text
Business code -> ProjectLogger -> SLF4J -> Logback
~~~

Wrapper này không nhất thiết thay SLF4J; nó có thể là tầng bổ sung phục vụ quy ước nội bộ. Nhưng thiết kế wrapper quá dày có thể làm mất khả năng truyền Throwable, placeholder, marker hoặc fluent API của facade.

Bốn khái niệm nên được phân biệt:

1. **Facade/API:** hợp đồng gọi log ở mức source code.
2. **Provider/binding:** thành phần nối facade với implementation được chọn.
3. **Backend:** xử lý sự kiện và chính sách xuất.
4. **Bridge:** chuyển sự kiện từ một API logging khác sang stack chính.

Không yêu cầu mỗi thành phần phải nằm ở một JAR khác nhau; cách phân chia phụ thuộc thư viện. Quan trọng là hiểu **chiều phụ thuộc** và **nơi cấu hình**.

## 11. Dùng facade đúng cách trong mã nghiệp vụ

### 11.1. Lấy logger theo tên lớp

~~~java
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(PaymentService.class);
~~~

Đây là **mảnh mã trong lớp PaymentService**, không phải chương trình độc lập. Việc lấy theo lớp giúp tạo tên logger rõ ràng và cho phép đặt ngưỡng theo package.

Không tạo logger mới mang tên requestId hoặc orderId cho từng lần xử lý. Các ID như vậy phù hợp làm **context/field** trong event, không phải hierarchy tên logger.

### 11.2. Placeholder và chi phí đánh giá

Trong SLF4J:

~~~java
LOG.debug("event=discount.checked orderId={} matched={}",
        orderId, matched);
~~~

Dùng **{}** để backend có thể định dạng message với các argument. Tuy nhiên, Java đánh giá đối số trước khi gọi logger:

~~~java
LOG.debug("payload={}", expensiveSerialize(payload));
~~~

Dù DEBUG tắt, **expensiveSerialize(payload)** vẫn chạy. Với dữ liệu tạo rất tốn kém:

~~~java
if (LOG.isDebugEnabled()) {
    LOG.debug("payload={}", expensiveSerialize(payload));
}
~~~

Đây đều là **mảnh mã minh họa**: cần biến/method ở lớp bao quanh. Các phiên bản SLF4J mới còn có cách ghi log theo fluent API, nhưng phải kiểm tra phiên bản và cách dùng supplier mà dự án hỗ trợ; không suy ra mọi biểu thức truyền qua logger đều lazy.

**Không gắn logic nghiệp vụ bắt buộc vào lời gọi tạo thông điệp debug.** Khi level thay đổi, nhánh logic phụ thuộc vào việc ghi log có thể không chạy.

### 11.3. Ghi Throwable có ngữ cảnh

~~~java
try {
    callRemoteService();
} catch (java.io.IOException ex) {
    LOG.error("event=remote.call.failed requestId={}",
            requestId, ex);
}
~~~

Đây là **mảnh mã minh họa** trong lớp có LOG, requestId và method callRemoteService(). Truyền đối tượng **Throwable** giúp backend có thể lưu stack trace/chuỗi cause; encoder quyết định cách biểu diễn thực tế.

Không chỉ ghi ex.getMessage() rồi bỏ mất ngữ cảnh lỗi, và không log cùng một exception ở mọi tầng nếu chỉ tạo nhiều stack trace trùng.

### 11.4. MDC và trace context

SLF4J cung cấp API MDC để mang những cặp key-value phục vụ tương quan sự kiện, ví dụ requestId:

~~~java
// Đoạn minh họa trong method có LOG.
try (org.slf4j.MDC.MDCCloseable ignored =
        org.slf4j.MDC.putCloseable("requestId", "req-42")) {
    LOG.info("event=order.created outcome=success");
}
~~~

Backend cần cấu hình encoder/pattern phù hợp để đưa trường MDC ra output, ví dụ Logback dùng **%X{requestId}**. **MDC không tự truyền qua tất cả thread pool, CompletableFuture hay reactive task**; cần cơ chế propagation thích hợp và dọn ngữ cảnh đúng khi công việc kết thúc.

Không đặt password, token, session cookie hoặc dữ liệu cá nhân nhạy cảm vào MDC.

## 12. Những khác biệt khi chuyển backend

Dù mã dùng SLF4J có thể giữ nguyên, việc chuyển backend vẫn có thể làm thay đổi:

| Phần | Ví dụ cần kiểm chứng |
| --- | --- |
| Cấu hình level | Tên package, root logger và filter có còn tương đương không? |
| Destination | ConsoleAppender, FileAppender hoặc backend khác có thực sự ghi đúng nơi không? |
| Formatter/encoder | Pattern, JSON, timestamp, timezone, escaping có giống kỳ vọng không? |
| Throwable | Stack trace/cause có còn được xuất đủ không? |
| MDC/context | Các trường tương quan có được mang sang encoder và collector không? |
| Async logging | Khi queue quá tải hoặc tiến trình dừng, chính sách drop/flush ra sao? |
| File rotation | Kích thước, số file, retention và đường dẫn có còn hợp lệ không? |
| Bảo mật | Masking, quyền truy cập và thời gian lưu có bị thay đổi không? |
| Hiệu năng | Chi phí định dạng, I/O, bộ đệm và áp lực tài nguyên dưới tải thực tế |

Không có facade nào bảo đảm 100% hành vi runtime giống nhau giữa các backend. **Facade chủ yếu ổn định interface dành cho mã gọi**, không tự chuẩn hóa mọi chi tiết triển khai.

## 13. Cân nhắc với framework và dự án có sẵn

### 13.1. Ứng dụng Spring Boot

Spring Boot có hệ thống quản lý logging và dependency mặc định tùy starter, phiên bản và cấu hình dự án. Nếu đã có SLF4J + Logback làm stack chính, **không nên tự thêm một backend khác** chỉ vì muốn sử dụng Logger.

Hãy kiểm tra dependency tree và cấu hình **logging.level...**, cấu hình backend hoặc biến môi trường theo cơ chế của bản Spring Boot đang chạy. Không khẳng định một file logging.properties của JUL sẽ điều khiển trực tiếp toàn bộ log qua Logback.

### 13.2. Ứng dụng thuần JDK hoặc công cụ dòng lệnh nhỏ

Nếu chỉ là utility chạy đơn giản, không có framework và hạn chế dependency là ưu tiên cao, **JUL có thể là đủ**. Thêm SLF4J + backend là hợp lý khi mong muốn API và tính thống nhất với nhiều module, nhưng không bắt buộc cho mọi chương trình Java.

### 13.3. Thư viện được nhúng trong nhiều ứng dụng

Chọn API theo hệ sinh thái người dùng thư viện; **SLF4J** là một lựa chọn rất phổ biến. Tránh buộc người dùng thư viện phải dùng logback.xml hay một provider riêng; cung cấp thông tin về tên logger, level và event quan trọng để ứng dụng quyết định cách xuất.

### 13.4. Dự án đã chuẩn hóa Log4j 2 API

Có thể tiếp tục dùng Log4j 2 API nếu cả tổ chức/hệ thống đã dùng thống nhất và không có lý do chuyển. Nếu muốn mã mới dùng SLF4J, phải chọn **provider SLF4J → Log4j 2** phù hợp và tránh cài nhầm bridge hai chiều. Chuyển mọi source code chỉ để thống nhất tên Logger chưa chắc có lợi hơn việc cấu hình routing rõ ràng.

## 14. Bảo mật khi chọn facade và backend

**Dùng facade không làm một bản ghi log trở nên an toàn mặc định.** Bất kể API nào, cần bảo vệ:

- **Bí mật:** password, access token, API key, private key, cookie phiên.
- **Thông tin cá nhân hoặc thanh toán:** chỉ ghi phần tối thiểu được phép theo chính sách.
- **Dữ liệu đầu vào không tin cậy:** có thể chứa newline, ký tự điều khiển hoặc chuỗi giả mạo log; dùng encoder escaping chính xác.
- **Throwable/stack trace:** có thể mang path, tham số hoặc dữ liệu nội bộ; kiểm soát truy cập và masking.
- **File và hệ thống tập trung:** quyền đọc, retention, việc thu thập và xử lý dữ liệu.

Không ghi toàn bộ HTTP body, authorization header hoặc object.toString() chỉ vì DEBUG đang bật. Tính năng structured logging và MDC giúp tìm kiếm, nhưng cũng tạo nhu cầu bảo vệ dữ liệu tốt hơn.

## 15. Hiệu năng và độ tin cậy

Một lời gọi LOG.info không tự bảo đảm log đã được ghi bền vững. Provider/backend có thể lọc, buffer, drop hoặc gặp lỗi khi gửi. Vì thế:

- **Đo tải thực tế:** đặc biệt khi bật DEBUG, ghi nhiều stack trace hoặc xuất JSON.
- **Ưu tiên level phù hợp:** INFO cho cột mốc, DEBUG để điều tra, WARN/ERROR cho sự kiện bất thường quan trọng.
- **Tránh log trong vòng lặp lưu lượng cao** nếu không có giá trị chẩn đoán rõ ràng.
- **Dùng metric cho tỷ lệ/số đếm và tracing cho luồng phân tán**, thay vì tạo một dòng log cho mọi phép đo.
- **Không xem log là nơi bảo đảm lưu giao dịch/audit quan trọng** nếu hệ thống yêu cầu hợp đồng lưu trữ bền vững riêng.
- **Cân nhắc shutdown/flush** cho appender nếu backend yêu cầu, nhưng flush cục bộ cũng không cam kết collector từ xa đã lưu dữ liệu.

Hiệu năng thường do **backend và cấu hình** quyết định nhiều hơn là chỉ do tên facade. Không lựa chọn chỉ dựa trên một phép thử microbenchmark không đại diện cho tải sản xuất.

## 16. Chẩn đoán xung đột provider và thiếu log

Một checklist thực hành:

1. **Xác định Logger API thật**: import org.slf4j.Logger, java.util.logging.Logger hay org.apache.logging.log4j.Logger?
2. **Xem classpath và dependency tree**: có bao nhiêu SLF4J provider? Có logback-classic và slf4j-simple cùng lúc không?
3. **Đúng thế hệ phiên bản không**: slf4j-api 2.x có provider tương thích ServiceLoader không?
4. **Đúng chiều adapter không**: Log4j 2 API → SLF4J hay SLF4J → Log4j 2?
5. **Có bridge vòng lặp không**: log4j-to-slf4j cùng log4j-slf4j2-impl; JUL → SLF4J rồi SLF4J → JUL?
6. **Log level có cho phép không**: effective level của đúng logger và filter ở appender?
7. **Đích xuất nào đang dùng**: stdout, stderr, file hoặc collector; có đang xem sai luồng/đường dẫn không?
8. **Tệp cấu hình nào được nạp**: logback.xml, log4j2.xml, logging.properties hoặc file theo framework?
9. **Thông điệp và Throwable có được định dạng đúng**: placeholder, encoder, stack trace, timezone và charset?
10. **Có cơ chế thu thập bị trễ/drop không**: sampling, buffer, mất mạng, giới hạn lưu trữ?

Trong Maven, có thể xem phụ thuộc bằng:

~~~bash
mvn dependency:tree
~~~

Đây là lệnh phục vụ chẩn đoán Maven, không phải API logging. Kiểm tra cả dependency trực tiếp và phụ thuộc kéo theo; đôi khi một starter đã chứa backend mà ứng dụng không cần thêm nữa.

**Không thấy log không đồng nghĩa đoạn code chưa chạy**; phải xét cấu hình và đường đi sự kiện.

## 17. Những lỗi thường gặp khi chọn facade

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng class Logger của backend trong mọi service | Khó đổi backend, dễ cast sai | Mã nghiệp vụ dùng facade API thích hợp |
| Thư viện thêm logback-classic bắt buộc | Áp đặt backend cho ứng dụng | Thư viện chỉ phụ thuộc API, ứng dụng chọn provider |
| Chỉ thêm slf4j-api, không có provider runtime | Không thấy log như mong đợi | Bổ sung đúng một provider tương thích |
| Có hai SLF4J provider trên classpath | Cảnh báo, backend được chọn không như mong muốn | Kiểm tra dependency tree, loại xung đột |
| Dùng binding 1.7 với API SLF4J 2.x | Provider không được chọn đúng | Chọn đúng thế hệ version |
| Cài đồng thời bridge Log4j 2 hai chiều | Nguy cơ vòng chuyển tiếp | Chọn một chiều đúng kiến trúc |
| Cài jul-to-slf4j và slf4j-jdk14 vòng tròn | Routing sai/loop | Không cấu hình hai chiều đối nghịch |
| Đổi Logback sang Simple nhưng vẫn chờ logback.xml hoạt động | Cấu hình bị bỏ qua | Dùng file/property của backend mới |
| Nghĩ facade đảm bảo log được lưu | Có thể mất bản ghi do filter/I/O | Kiểm chứng appender, collector và retention |
| Dùng {} với JUL một cách máy móc | Message không được định dạng đúng | Phân biệt placeholder của API |
| Nối chuỗi tốn kém trước debug | Tăng CPU dù DEBUG tắt | Dùng parameterized logging và guard phù hợp |
| Ghi token/raw payload vào log | Lộ dữ liệu | Chỉ ghi trường tối thiểu, masking và kiểm soát quyền |

## 18. Bài tập ứng dụng và câu hỏi tự kiểm tra

**Bài tập 1 — Thư viện thanh toán tái sử dụng.** Một thư viện được nhúng vào ba ứng dụng; ứng dụng A dùng Logback, B dùng Log4j 2, C chưa chọn backend. Thư viện có nên tự thêm logback-classic không?

**Đáp án:** Thông thường không. Thư viện có thể chọn SLF4J API, phát sự kiện với tên logger và level phù hợp. Mỗi ứng dụng quyết định provider/backend và cấu hình xuất log.

**Bài tập 2 — Facade chưa có provider.** Mã biên dịch thành công vì có slf4j-api nhưng không thấy INFO xuất ở runtime. Nguyên nhân đầu tiên cần kiểm tra?

**Đáp án:** Xem provider SLF4J tương thích có tồn tại không và có xung đột version/classpath không, rồi xem logger level, appender và đích xuất.

**Bài tập 3 — Đổi backend.** Ứng dụng đổi logback-classic thành slf4j-simple nhưng vẫn dùng org.slf4j.Logger. Có cần đổi LOG.info trong Java không?

**Đáp án:** Thông thường không, nếu API SLF4J vẫn tương thích. Nhưng phải đổi/kiểm tra cấu hình backend, định dạng và đích xuất, đồng thời loại provider cũ khỏi runtime.

**Bài tập 4 — Bridge Log4j 2.** Một thư viện dùng Log4j 2 API, ứng dụng chọn SLF4J + Logback. Nên tìm hướng chuyển nào?

**Đáp án:** Xem adapter **Log4j 2 API → SLF4J** như log4j-to-slf4j, và tránh dùng thêm provider chiều ngược lại SLF4J → Log4j 2 trong cùng vòng routing.

**Bài tập 5 — JUL thuần.** Một công cụ nhỏ chỉ dùng JDK và không có hệ thống framework. Có bắt buộc thêm SLF4J không?

**Đáp án:** Không. JUL có thể đáp ứng nhu cầu logging cơ bản. Quyết định phụ thuộc yêu cầu triển khai, nhu cầu thống nhất nhiều module và khả năng quản lý dependency.

**Bài tập 6 — Đối số tốn chi phí.** LOG.debug("payload={}", costlySerialize(payload)) có tránh gọi costlySerialize khi DEBUG tắt không?

**Đáp án:** Không. Java đánh giá đối số trước lời gọi. Nếu phép tính đắt, dùng guard isDebugEnabled hoặc cơ chế lazy logging hợp lệ của API/phiên bản đang dùng.

**Bài tập 7 — Bảo mật.** Nếu DEBUG bị tắt ở production thì có an toàn khi đưa access token vào LOG.debug không?

**Đáp án:** Không. Level có thể thay đổi hoặc log được thu thập ở môi trường khác. Không ghi bí mật ở bất kỳ level nào.

**Bài tập 8 — Phân biệt trách nhiệm.** Ai quyết định file rotation: facade hay backend?

**Đáp án:** Backend, appender và cấu hình vận hành. Facade chỉ cung cấp API cho mã phát log; không tự thiết lập chính sách rotation.

## 19. Tổng kết và quy tắc lựa chọn

**Chọn facade là chọn API mà mã nguồn sẽ phụ thuộc lâu dài; chọn backend là chọn cách thực thi và vận hành logging.**

Với một **ứng dụng Java hiện đại chưa bị ràng buộc**, lựa chọn thường hợp lý là **SLF4J API + một provider/backend** phù hợp với framework và hạ tầng (ví dụ Logback). Với **thư viện tái sử dụng**, ưu tiên chỉ phụ thuộc facade, không ép backend. Với **công cụ Java nhỏ**, JUL sẵn trong JDK có thể là lựa chọn đủ tốt. Với **hệ thống đã chuẩn hóa Log4j 2 API**, có thể giữ lựa chọn hiện tại nếu nó đáp ứng yêu cầu.

Dù lựa chọn nào, cần giữ bốn nguyên tắc: **một kiến trúc routing rõ ràng, version tương thích, cấu hình ở đúng tầng chịu trách nhiệm, và kiểm chứng runtime về level/đích xuất/Throwable/bảo mật**. Đó là cơ sở để log hữu ích mà mã nghiệp vụ không bị khóa cứng vào một triển khai không cần thiết.
